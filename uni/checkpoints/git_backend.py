from __future__ import annotations

import json
import subprocess
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .models import EmergencySnapshot


@dataclass(frozen=True)
class GitStatusEntry:
    code: str
    path: str


GitRunner = Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]]


class GitBackend:
    """Read-mostly Git adapter. Destructive workspace commands are not permitted."""

    _SAFE_COMMANDS = frozenset({"rev-parse", "status", "diff", "ls-tree"})

    def __init__(self, repo_root: Path | str, *, runner: GitRunner | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._runner = runner

    def _run(self, *args: str) -> str:
        if not args or args[0] not in self._SAFE_COMMANDS:
            raise ValueError(f"unsafe git command blocked: {args!r}")
        argv = tuple(args)
        if self._runner is not None:
            result = self._runner(argv)
        else:
            result = subprocess.run(
                ["git", "-C", str(self.repo_root), *argv],
                check=True,
                capture_output=True,
                text=True,
            )
        return result.stdout

    def head_revision(self) -> str:
        return self._run("rev-parse", "HEAD").strip()

    def tree_revision(self, revision: str) -> str:
        return self._run("rev-parse", f"{revision}^{{tree}}").strip()

    def status_entries(self) -> tuple[GitStatusEntry, ...]:
        output = self._run(
            "status", "--porcelain=v1", "--untracked-files=all"
        )
        entries: list[GitStatusEntry] = []
        for line in output.splitlines():
            if len(line) < 4:
                continue
            code = line[:2]
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            entries.append(GitStatusEntry(code=code, path=path))
        return tuple(entries)

    def is_clean(self) -> bool:
        return not self.status_entries()

    def diff_name_status(
        self, target_revision: str, current_revision: str = "HEAD"
    ) -> tuple[tuple[str, str], ...]:
        output = self._run(
            "diff", "--name-status", target_revision, current_revision
        )
        changes: list[tuple[str, str]] = []
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            status = fields[0]
            path = fields[-1]
            changes.append((status, path))
        return tuple(changes)

    def resolve_repo_path(self, relative_path: str) -> Path:
        candidate = (self.repo_root / relative_path).resolve()
        try:
            candidate.relative_to(self.repo_root)
        except ValueError as exc:
            raise ValueError(f"path escapes repository: {relative_path}") from exc
        return candidate

    def create_emergency_snapshot(
        self, destination_root: Path | str, label: str
    ) -> EmergencySnapshot:
        created_at = datetime.now(timezone.utc).isoformat()
        snapshot_id = f"emergency-{uuid4().hex}"
        location = Path(destination_root) / snapshot_id
        location.mkdir(parents=True, exist_ok=False)

        head = self.head_revision()
        dirty_entries = self.status_entries()
        patch_path = location / "tracked.patch"
        patch_path.write_text(
            self._run("diff", "--binary", "HEAD"), encoding="utf-8"
        )

        archive_path = location / "untracked.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            for entry in dirty_entries:
                if entry.code != "??":
                    continue
                source = self.resolve_repo_path(entry.path)
                if source.exists():
                    archive.add(source, arcname=entry.path, recursive=False)

        dirty_state = tuple(
            f"{entry.code} {entry.path}" for entry in dirty_entries
        )
        metadata_path = location / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "id": snapshot_id,
                    "label": label,
                    "created_at": created_at,
                    "head_revision": head,
                    "dirty_state": list(dirty_state),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return EmergencySnapshot(
            id=snapshot_id,
            label=label,
            created_at=created_at,
            head_revision=head,
            location=str(location),
            patch_file=str(patch_path),
            untracked_archive=str(archive_path),
            dirty_state=dirty_state,
        )
