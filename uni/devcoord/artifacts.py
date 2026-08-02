from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path

from uni.devcoord.models import ArtifactRef


class ArtifactCollector:
    def __init__(self, workspace: str | Path, *, max_text_chars: int = 50_000) -> None:
        self.workspace = Path(workspace).resolve()
        self.max_text_chars = max_text_chars

    def collect(self, relative_paths: list[str]) -> list[ArtifactRef]:
        return [self._collect_one(path) for path in relative_paths]

    def _collect_one(self, value: str) -> ArtifactRef:
        candidate = (self.workspace / value).resolve()
        try:
            relative = candidate.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError(f"artifact escapes workspace: {value}") from exc
        if not candidate.is_file():
            raise FileNotFoundError(f"artifact not found: {relative.as_posix()}")
        if candidate.name.casefold() in {".env", "credentials.json", "secrets.json"}:
            raise ValueError(f"secret-bearing artifact is not allowed: {relative.as_posix()}")
        content = candidate.read_bytes()
        media_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        excerpt = None
        if media_type.startswith("text/") or candidate.suffix.casefold() in {
            ".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt"
        }:
            excerpt = content.decode("utf-8", errors="replace")[: self.max_text_chars]
            if re.search(
                r"(?i)(-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
                r"(?:api[_-]?key|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,})",
                excerpt,
            ):
                raise ValueError(f"possible secret detected in artifact: {relative.as_posix()}")
        return ArtifactRef(
            path=relative.as_posix(),
            sha256=hashlib.sha256(content).hexdigest(),
            size=len(content),
            media_type=media_type,
            text_excerpt=excerpt,
        )
