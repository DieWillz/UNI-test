from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ParticipantReply:
    """One participant's raw, UNTRUSTED response in a consensus round.

    Per UNI MANIFESTO v2.5 / COUNCIL-002: advisor output is treated as
    untrusted data. It can never invoke a UNI tool and is never executed.
    """

    participant: str
    text: str
    via: str  # "api" or "browser"
    model: Optional[str]
    error: Optional[str] = None
    latency_seconds: float = 0.0


class CouncilProvider:
    """Base transport. Subclasses know how to deliver a prompt and read text back."""

    scheme: str = "base"

    async def ask(self, participant: str, prompt: str, *, max_tokens: int = 2000) -> ParticipantReply:
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None


def _strip_thinking(text: str) -> str:
    """Drop common chain-of-thought wrappers from untrusted advisor output.

    We keep only the visible answer. We never persist hidden reasoning.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


class ApiProvider(CouncilProvider):
    """OpenAI-compatible HTTP API transport (free local endpoint, OpenRouter, Groq,
    or any OpenAI-compatible paid API configured by the user). Uses plain httpx so it
    does not depend on the optional `openai` SDK."""

    scheme = "api"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        temperature: float = 0.7,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    async def ask(self, participant: str, prompt: str, *, max_tokens: int = 2000) -> ParticipantReply:
        import time

        start = time.perf_counter()
        error: Optional[str] = None
        text = ""
        try:
            client = await self._get_client()
            resp = await client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": self.temperature,
                    "max_tokens": max_tokens,
                },
            )
            if resp.status_code != 200:
                if resp.status_code in (401, 403):
                    error = (
                        f"HTTP {resp.status_code}: доступ запрещён — проверьте API-ключ "
                        f"(OpenRouter/Hermes-local) и квоту. Ответ: {resp.text[:200]}"
                    )
                else:
                    error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            else:
                data = resp.json()
                text = _strip_thinking(
                    data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
                )
        except Exception as exc:  # network/timeout/auth -> report, never crash the round
            error = f"{type(exc).__name__}: {exc}"
        return ParticipantReply(
            participant=participant,
            text=text,
            via="api",
            model=self.model,
            error=error,
            latency_seconds=round(time.perf_counter() - start, 2),
        )

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None


class BrowserProvider(CouncilProvider):
    """Browser automation transport for free web-AI chats (no API key / no payment).

    Uses the shared BrowserSession but a SEPARATE profile per MANIFESTO v2.6 §7:
    web-AI answers are untrusted data and must not mix with the user's bank,
    mail or intimate sessions. The provider only navigates, types the prompt,
    reads the answer and returns text. It cannot invoke any UNI tool.

    Fair-use conditions (MANIFESTO v2.6 §7):
    - targets FREE web tiers only (never a paid consumer subscription as API stand-in);
    - respects `min_interval_seconds` pauses between requests (rate limiting);
    - the runner is responsible for informing the user that automation may breach a
      service ToS and for obtaining their acknowledgement.
    """

    scheme = "browser"
    DEFAULT_PROMPT_SELECTOR = "textarea, [contenteditable='true'], input[type='text']"
    DEFAULT_ANSWER_SELECTOR = "article, main, [role='article'], .markdown, .prose"

    def __init__(
        self,
        *,
        browser_session,
        host: str,
        prompt_selector: str = DEFAULT_PROMPT_SELECTOR,
        submit_selector: Optional[str] = None,
        answer_selector: str = DEFAULT_ANSWER_SELECTOR,
        max_chars: int = 8000,
        min_interval_seconds: float = 8.0,
    ) -> None:
        self.session = browser_session
        self.host = host
        self.prompt_selector = prompt_selector
        self.submit_selector = submit_selector
        self.answer_selector = answer_selector
        self.max_chars = max_chars
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))

    @staticmethod
    async def _composer_is_empty(box) -> bool:
        return bool(await box.evaluate(
            "e => e.tagName === 'TEXTAREA' || e.tagName === 'INPUT' "
            "? !e.value.trim() : !(e.innerText || e.textContent || '').trim()"
        ))

    async def _send_and_verify(self, page, box) -> None:
        """Send once and require the composer to clear before reporting success."""
        await box.press("Enter")
        for _ in range(20):
            if await self._composer_is_empty(box):
                return
            await page.wait_for_timeout(250)

        if self.submit_selector:
            buttons = page.locator(self.submit_selector)
            if await buttons.count() == 1:
                button = buttons.first
                if await button.is_enabled():
                    if getattr(self.session, "agent_cursor_enabled", True):
                        from uni.agent_cursor import click_with_cursor

                        await click_with_cursor(
                            page,
                            button,
                            label=getattr(self.session, "agent_cursor_label", "UNI"),
                            move_ms=getattr(self.session, "agent_cursor_move_ms", 220),
                            timeout=8_000,
                        )
                    else:
                        await button.click(timeout=8_000)
                    for _ in range(20):
                        if await self._composer_is_empty(box):
                            return
                        await page.wait_for_timeout(250)
        raise RuntimeError("message was typed but the chat did not confirm sending it")

    async def _wait_for_new_answer(self, page, previous_count: int) -> str:
        answers = page.locator(self.answer_selector)
        last_text = ""
        stable_reads = 0
        for _ in range(120):
            count = await answers.count()
            if count > previous_count:
                candidate = (await answers.nth(count - 1).inner_text(timeout=10_000)).strip()
                if candidate:
                    if candidate == last_text:
                        stable_reads += 1
                    else:
                        last_text = candidate
                        stable_reads = 0
                    if stable_reads >= 3:
                        return candidate
            await page.wait_for_timeout(500)
        raise TimeoutError("the message was sent, but no completed answer appeared")

    async def ask(self, participant: str, prompt: str, *, max_tokens: int = 2000) -> ParticipantReply:
        import time

        start = time.perf_counter()
        error: Optional[str] = None
        text = ""
        page = None
        try:
            page = await self.session.page_for_host(self.host, create_url=f"https://{self.host}")
            # Focus the composer and type the brief (UNI cursor overlay if enabled).
            box = page.locator(self.prompt_selector).first
            answer_count = await page.locator(self.answer_selector).count()
            if getattr(self.session, "agent_cursor_enabled", True) and not getattr(
                self.session, "headless", False
            ):
                from uni.agent_cursor import fill_with_cursor, click_with_cursor

                await fill_with_cursor(
                    page,
                    box,
                    prompt,
                    label=getattr(self.session, "agent_cursor_label", "UNI"),
                    move_ms=getattr(self.session, "agent_cursor_move_ms", 220),
                    timeout=8_000,
                )
            else:
                await box.click(timeout=8_000)
                await box.fill(prompt, timeout=8_000)
            await self._send_and_verify(page, box)
            raw = await self._wait_for_new_answer(page, answer_count)
            text = _strip_thinking(raw)[: self.max_chars]
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        # Rate-limit: pause at least min_interval_seconds before the next call (fair use).
        elapsed = time.perf_counter() - start
        if self.min_interval_seconds > elapsed:
            await asyncio.sleep(self.min_interval_seconds - elapsed)
        return ParticipantReply(
            participant=participant,
            text=text,
            via="browser",
            model=self.host,
            error=error,
            latency_seconds=round(time.perf_counter() - start, 2),
        )

    async def close(self) -> None:  # session lifecycle owned by the caller
        return None


class CodexProvider(CouncilProvider):
    """Local Codex CLI participant (ChatGPT/Codex auth reused, no API key needed).

    Runs ``codex exec --json`` as a subprocess and reads its JSONL event stream. Codex
    uses the saved ChatGPT/Codex login (``codex login``), has workspace_write access to
    the project, and returns a structured result. Per COUNCIL rules it only reads/writes
    files inside the allowed paths and never invokes UNI tools directly.

    The command can be overridden via ``command`` (e.g. to point at a specific codex.exe).
    """

    scheme = "codex"

    def __init__(
        self,
        *,
        sandbox: str = "workspace-write",
        command: Optional[str] = None,
        cwd: Optional[str] = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.sandbox = sandbox
        self.command = command or "codex"
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds
        self._proc = None

    async def ask(self, participant: str, prompt: str, *, max_tokens: int = 2000) -> ParticipantReply:
        import asyncio
        import json as _json
        import time

        start = time.perf_counter()
        error: Optional[str] = None
        text = ""
        try:
            cmd = [
                self.command, "exec",
                "--sandbox", self.sandbox,
                "--json",
                prompt,
            ]
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                self._proc.communicate(), timeout=self.timeout_seconds
            )
            # Parse JSONL: collect message/response events into the answer text.
            chunks: list[str] = []
            for raw_line in (stdout or b"").decode("utf-8", "replace").splitlines():
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    ev = _json.loads(raw_line)
                except _json.JSONDecodeError:
                    continue
                # Current `codex exec --json` emits item.completed events whose item
                # is an agent_message. Keep the older shapes as compatibility input.
                etype = ev.get("type")
                if etype == "item.completed":
                    item = ev.get("item") or {}
                    if item.get("type") == "agent_message" and item.get("text"):
                        chunks.append(str(item["text"]))
                elif etype == "message":
                    for part in ev.get("msg", {}).get("content", []) or []:
                        if isinstance(part, dict) and part.get("type") == "output_text":
                            chunks.append(part.get("text", ""))
                elif etype == "result":
                    if ev.get("final_response"):
                        chunks.append(ev["final_response"])
                elif "response" in ev and isinstance(ev["response"], str):
                    chunks.append(ev["response"])
            if chunks:
                text = _strip_thinking("\n".join(chunks)).strip()
            elif self._proc.returncode not in (0, None):
                error = (stderr or b"").decode("utf-8", "replace")[:400] or f"codex exited {self._proc.returncode}"
            else:
                error = "Codex completed without a final agent message"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        return ParticipantReply(
            participant=participant,
            text=text,
            via="codex",
            model="codex-cli",
            error=error,
            latency_seconds=round(time.perf_counter() - start, 2),
        )

    async def close(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None


def build_provider(spec: dict[str, Any]) -> CouncilProvider:
    """Factory from a participant spec: {'transport': 'api'|'browser'|'codex', ...}."""
    transport = spec.get("transport", "api")
    if transport == "api":
        return ApiProvider(
            base_url=spec["base_url"],
            api_key=spec.get("api_key", "lm-studio"),
            model=spec["model"],
            timeout_seconds=spec.get("timeout_seconds", 60.0),
            temperature=spec.get("temperature", 0.7),
        )
    if transport == "browser":
        # browser_session is injected by the runner, not from the spec
        browser_session = spec.get("browser_session")
        if browser_session is None:
            raise ValueError("browser transport requires an injected browser_session")
        return BrowserProvider(
            browser_session=browser_session,
            host=spec["host"],
            prompt_selector=spec.get("prompt_selector", BrowserProvider.DEFAULT_PROMPT_SELECTOR),
            submit_selector=spec.get("submit_selector"),
            answer_selector=spec.get("answer_selector", BrowserProvider.DEFAULT_ANSWER_SELECTOR),
            min_interval_seconds=spec.get("min_interval_seconds", 8.0),
        )
    if transport == "codex":
        # Local Codex CLI (ChatGPT/Codex auth reused). command/cwd are optional.
        from pathlib import Path

        return CodexProvider(
            sandbox=spec.get("sandbox", "workspace-write"),
            command=spec.get("command"),
            cwd=spec.get("cwd") or str(Path.cwd()),
            timeout_seconds=spec.get("timeout_seconds", 120.0),
        )
    raise ValueError(f"Unknown council transport: {transport!r}")
