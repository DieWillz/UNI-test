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
    """OpenAI-compatible HTTP API transport (used when the model endpoint is free
    or locally hosted, or when a paid API key is configured)."""

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
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self._client = None

    async def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout_seconds,
            )
        return self._client

    async def ask(self, participant: str, prompt: str, *, max_tokens: int = 2000) -> ParticipantReply:
        import time

        start = time.perf_counter()
        error: Optional[str] = None
        text = ""
        try:
            client = await self._get_client()
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=max_tokens,
            )
            text = _strip_thinking(response.choices[0].message.content or "")
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
                await self._client.close()
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

    def __init__(
        self,
        *,
        browser_session,
        host: str,
        prompt_selector: str = "textarea, [contenteditable='true'], input[type='text']",
        submit_selector: Optional[str] = None,
        answer_selector: str = "article, main, [role='article'], .markdown, .prose",
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

    async def ask(self, participant: str, prompt: str, *, max_tokens: int = 2000) -> ParticipantReply:
        import time

        start = time.perf_counter()
        error: Optional[str] = None
        text = ""
        page = None
        try:
            page = await self.session.page_for_host(self.host, create_url=f"https://{self.host}")
            # Focus the composer and type the brief.
            box = page.locator(self.prompt_selector).first
            await box.click(timeout=8_000)
            await box.fill(prompt, timeout=8_000)
            if self.submit_selector:
                await page.locator(self.submit_selector).first.click(timeout=8_000)
            else:
                await page.keyboard.press("Enter")
            # Wait for the answer to render.
            await page.wait_for_selector(self.answer_selector, timeout=30_000)
            await page.wait_for_timeout(1_500)
            raw = (await page.locator(self.answer_selector).first.inner_text(timeout=10_000)).strip()
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


def build_provider(spec: dict[str, Any]) -> CouncilProvider:
    """Factory from a participant spec: {'transport': 'api'|'browser', ...}."""
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
            prompt_selector=spec.get("prompt_selector", BrowserProvider.prompt_selector),
            submit_selector=spec.get("submit_selector"),
            answer_selector=spec.get("answer_selector", BrowserProvider.answer_selector),
            min_interval_seconds=spec.get("min_interval_seconds", BrowserProvider.min_interval_seconds),
        )
    raise ValueError(f"Unknown council transport: {transport!r}")
