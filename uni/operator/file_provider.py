from __future__ import annotations

import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Any


class FileProvider:
    """Direct filesystem provider for bounded deterministic file operations."""

    def __init__(self, *, max_read_chars: int = 200_000, max_list_entries: int = 200) -> None:
        self.max_read_chars = max(1_000, min(int(max_read_chars), 2_000_000))
        self.max_list_entries = max(1, min(int(max_list_entries), 2_000))

    @staticmethod
    def _path(value: Any) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("path_required")
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("absolute_path_required")
        return path.resolve()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    @classmethod
    def _stat(cls, path: Path) -> dict[str, Any]:
        stat = path.stat()
        data = {
            "path": str(path),
            "exists": True,
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
        if path.is_file():
            data["sha256"] = cls._sha256(path)
        return data

    async def _read(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise ValueError("file_not_found")
        text = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
        data = await asyncio.to_thread(self._stat, path)
        data["text"] = text[: self.max_read_chars]
        data["truncated"] = len(text) > self.max_read_chars
        return data

    async def _list(self, path: Path) -> dict[str, Any]:
        if not path.is_dir():
            raise ValueError("directory_not_found")
        entries = sorted(path.iterdir(), key=lambda item: item.name.casefold())
        limited = entries[: self.max_list_entries]
        return {
            "path": str(path),
            "entries": [{"name": item.name, "path": str(item), "is_dir": item.is_dir()}
                        for item in limited],
            "truncated": len(entries) > len(limited),
        }
    async def act(self, action: str, **params: Any) -> dict[str, Any]:
        path = self._path(params.get("path", ""))
        if action == "exists":
            if not path.exists():
                return {"path": str(path), "exists": False}
            return await asyncio.to_thread(self._stat, path)
        if action == "read":
            return await self._read(path)
        if action == "list":
            return await self._list(path)
        if action == "mkdir":
            path.mkdir(exist_ok=False)
            return await asyncio.to_thread(self._stat, path)
        if action == "write_text":
            if not path.parent.is_dir():
                raise ValueError("parent_directory_missing")
            text = params.get("text")
            if not isinstance(text, str):
                raise ValueError("text_required")
            await asyncio.to_thread(path.write_text, text, encoding="utf-8")
            return await asyncio.to_thread(self._stat, path)
        if action in {"copy", "move"}:
            destination = self._path(params.get("destination", ""))
            if not path.exists():
                raise ValueError("source_not_found")
            if destination.exists():
                raise ValueError("destination_exists")
            if not destination.parent.is_dir():
                raise ValueError("parent_directory_missing")
            operation = shutil.copy2 if action == "copy" else shutil.move
            await asyncio.to_thread(operation, str(path), str(destination))
            return await asyncio.to_thread(self._stat, destination)
        if action == "delete":
            if not path.exists():
                return {"path": str(path), "removed": False, "already_absent": True}
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError as exc:
                    raise ValueError("directory_not_empty") from exc
            else:
                path.unlink()
            return {"path": str(path), "removed": True}
        raise ValueError(f"unsupported_file_action: {action}")
