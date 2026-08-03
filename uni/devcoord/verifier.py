"""Verifier: check AI claims about the code against the real repository.

The Verifier does NOT trust a model's assertion on faith. It extracts
code-like tokens from the claim and greps the actual repository files for
them. This is exactly the class of mistake we already caught (Hermes vs
Copilot disagreeing on whether ``config.py`` had dangerous defaults) — the
fix is to verify against files, not against the model's confidence.

Design notes:
- ``ClaimVerificationResult`` lives in ``uni.devcoord.models`` to avoid a
  circular import (verifier imports models, never the reverse).
- Search is substring-based across real files; this is intentionally simple
  and dependency-free (``grep``-like), matching the task's "grep/AST" brief.
- Negated claims ("X does NOT exist") are supported: if no token matches,
  that absence is treated as confirmation of the negation.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from uni.devcoord.models import ClaimVerificationResult

# Directories that are reference-only copies (never the canonical source).
# Verifying claims against them would produce false positives.
_ARCHIVE_DIRS = {
    "Uni-Claude",
    "Uni-DeepSeek",
    "Uni-OpenCode",
    "Claude",
    "backup",
    "copilot-worktrees",
    "uni Hermes old",
    "uni-test",
    "Telegram",
}

# Stopwords that are never useful code tokens.
_STOPWORDS = {
    "уже", "есть", "нет", "существует", "существует", "находится", "файле",
    "файл", "функция", "класс", "метод", "поле", "модуль", "код", "кода",
    "the", "and", "for", "has", "with", "that", "this", "already", "exists",
    "file", "function", "class", "method", "field", "module", "code", "into",
    "from", "import", "does", "not", "will", "returns", "return", "self",
}

_TEXT_SUFFIXES = (
    ".py", ".md", ".yaml", ".yml", ".html", ".js", ".css", ".txt",
    ".json", ".toml", ".cfg", ".ini",
)

_NEGATION_RE = re.compile(
    r"\b(не|нет|отсутству|нету|никогда|never|no|not|absent|doesn't|don't)\b",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{2,}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Verifier:
    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()

    # -- corpus ---------------------------------------------------------------
    def _iter_files(self, file_hint: str | None) -> Iterable[Path]:
        if file_hint:
            candidate = self.repo_root / file_hint
            if candidate.exists():
                yield candidate
            return
        for path in self.repo_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            if "__pycache__" in path.parts:
                continue
            if any(arch in path.parts for arch in _ARCHIVE_DIRS):
                continue
            yield path

    # -- token extraction -----------------------------------------------------
    @staticmethod
    def _extract_tokens(claim: str) -> list[str]:
        raw = _TOKEN_RE.findall(claim)
        out: list[str] = []
        seen: set[str] = set()
        for tok in raw:
            low = tok.lower()
            if low in _STOPWORDS:
                continue
            if len(tok) < 3:
                continue
            # Keep tokens that look code-like: underscore, digit, or mixed case.
            looks_code = (
                "_" in tok
                or any(ch.isdigit() for ch in tok)
                or (any(c.islower() for c in tok) and any(c.isupper() for c in tok))
            )
            if not looks_code:
                continue
            if low not in seen:
                seen.add(low)
                out.append(tok)
        # Prefer more specific (longer) tokens first.
        return sorted(out, key=lambda x: -len(x))

    # -- verification ---------------------------------------------------------
    def verify_claim(
        self, claim: str, file_hint: str | None = None
    ) -> ClaimVerificationResult:
        negated = bool(_NEGATION_RE.search(claim))
        tokens = self._extract_tokens(claim)
        if not tokens:
            return ClaimVerificationResult(
                claim=claim,
                verified=False,
                evidence="не удалось извлечь проверяемые токены из утверждения",
                checked_at=_now(),
            )

        hits: list[tuple[str, int, str, str]] = []
        for tok in tokens:
            for path in self._iter_files(file_hint):
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                idx = text.find(tok)
                if idx < 0:
                    continue
                line_no = text.count("\n", 0, idx) + 1
                snippet = text.splitlines()[line_no - 1].strip()[:200]
                rel = str(path.relative_to(self.repo_root))
                hits.append((rel, line_no, snippet, tok))
                break  # move to the next token once this one matched
            if len(hits) >= 5:
                break

        if hits:
            evidence = "; ".join(
                f"{rel}:{ln} `{snippet}` (токен '{tok}')"
                for rel, ln, snippet, tok in hits
            )
            return ClaimVerificationResult(
                claim=claim,
                verified=True,
                evidence=f"найдено совпадение в репозитории: {evidence}",
                checked_at=_now(),
            )

        if negated:
            return ClaimVerificationResult(
                claim=claim,
                verified=True,
                evidence=(
                    "совпадений не найдено — это подтверждает отрицательное "
                    f"утверждение; проверяли токены: {tokens[:5]}"
                ),
                checked_at=_now(),
            )

        return ClaimVerificationResult(
            claim=claim,
            verified=False,
            evidence=f"ни один из токенов не найден в репозитории: {tokens[:8]}",
            checked_at=_now(),
        )
