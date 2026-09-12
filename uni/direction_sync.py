from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import tempfile
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

_TOML_BEGIN = "<!-- UNI_ACTIVE_WORK_TOML_BEGIN -->"
_TOML_END = "<!-- UNI_ACTIVE_WORK_TOML_END -->"
_REQUIRED_ASSIGNMENT_FIELDS = (
    "agent",
    "task",
    "status",
    "exclusive_paths",
    "read_only_paths",
    "dependencies",
    "updated_at",
)


@dataclass(frozen=True)
class SyncCheck:
    ok: bool
    reason: str
    revision: str
    conflicts: list[dict[str, str]] = field(default_factory=list)


class DirectionSyncError(RuntimeError):
    pass


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DirectionSyncError(f"cannot_read:{path}:{exc}") from exc


def _active_machine_block(text: str) -> str:
    start = text.find(_TOML_BEGIN)
    end = text.find(_TOML_END)
    if start < 0 or end <= start:
        raise DirectionSyncError("active_work_machine_block_missing")
    block = text[start + len(_TOML_BEGIN) : end].strip()
    if block.startswith("```toml"):
        block = block[len("```toml") :].strip()
    if block.endswith("```"):
        block = block[:-3].strip()
    return block


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DirectionSyncError(f"active_work_invalid_field:{field_name}")
    return list(value)


def _parse_assignments(active_text: str) -> list[dict[str, Any]]:
    try:
        data = tomllib.loads(_active_machine_block(active_text))
    except tomllib.TOMLDecodeError as exc:
        raise DirectionSyncError(f"active_work_toml_invalid:{exc}") from exc

    if data.get("schema_version") != 1:
        raise DirectionSyncError("active_work_schema_unsupported")
    raw_assignments = data.get("assignment")
    if not isinstance(raw_assignments, list):
        raise DirectionSyncError("active_work_assignments_missing")

    assignments: list[dict[str, Any]] = []
    seen_agents: set[str] = set()
    for raw in raw_assignments:
        if not isinstance(raw, dict):
            raise DirectionSyncError("active_work_assignment_invalid")
        missing = [name for name in _REQUIRED_ASSIGNMENT_FIELDS if name not in raw]
        if missing:
            raise DirectionSyncError(f"active_work_assignment_missing:{','.join(missing)}")
        agent = raw["agent"]
        task = raw["task"]
        status = raw["status"]
        updated_at = raw["updated_at"]
        if not all(isinstance(value, str) and value.strip() for value in (agent, task, status, updated_at)):
            raise DirectionSyncError("active_work_assignment_scalar_invalid")
        if agent in seen_agents:
            raise DirectionSyncError(f"active_work_duplicate_agent:{agent}")
        seen_agents.add(agent)
        assignments.append(
            {
                "agent": agent,
                "task": task,
                "status": status,
                "exclusive_paths": _string_list(raw["exclusive_paths"], "exclusive_paths"),
                "read_only_paths": _string_list(raw["read_only_paths"], "read_only_paths"),
                "dependencies": _string_list(raw["dependencies"], "dependencies"),
                "updated_at": updated_at,
            }
        )
    return assignments


def _canonical_assignments(assignments: Sequence[dict[str, Any]]) -> str:
    canonical: list[dict[str, Any]] = []
    for item in assignments:
        canonical.append(
            {
                "agent": item["agent"],
                "task": item["task"],
                "status": item["status"],
                "exclusive_paths": sorted(item["exclusive_paths"]),
                "read_only_paths": sorted(item["read_only_paths"]),
                "dependencies": sorted(item["dependencies"]),
                "updated_at": item["updated_at"],
            }
        )
    canonical.sort(key=lambda item: item["agent"])
    payload = {"schema_version": 1, "assignment": canonical}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _revision(master_text: str, assignments: Sequence[dict[str, Any]]) -> str:
    payload = master_text.rstrip() + "\n---ACTIVE_ASSIGNMENTS---\n" + _canonical_assignments(assignments)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalized_path(value: str) -> str:
    return str(value).replace("\\", "/").lstrip("./")


def _matches(path: str, pattern: str) -> bool:
    path_n = _normalized_path(path)
    pattern_n = _normalized_path(pattern)
    if pattern_n.endswith("/**"):
        prefix = pattern_n[:-3].rstrip("/")
        return path_n == prefix or path_n.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path_n, pattern_n)


class DirectionSyncGate:
    def __init__(
        self,
        master_path: Path | str,
        active_path: Path | str,
        state_path: Path | str,
    ) -> None:
        self.master_path = Path(master_path)
        self.active_path = Path(active_path)
        self.state_path = Path(state_path)

    def _snapshot(self) -> tuple[str, list[dict[str, Any]]]:
        master = _read_text(self.master_path)
        active = _read_text(self.active_path)
        assignments = _parse_assignments(active)
        return _revision(master, assignments), assignments

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"agents": {}}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DirectionSyncError("invalid_ack_state") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("agents"), dict):
            raise DirectionSyncError("invalid_ack_state")
        return raw

    def acknowledge(self, agent: str) -> dict[str, str]:
        revision, assignments = self._snapshot()
        names = {str(item["agent"]) for item in assignments}
        if agent not in names:
            raise DirectionSyncError(f"agent_not_assigned:{agent}")
        state = self._load_state()
        record = {
            "revision": revision,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        }
        state["agents"][agent] = record
        self._write_state(state)
        return record

    def _write_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.state_path.parent,
                prefix=f".{self.state_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                json.dump(state, tmp, ensure_ascii=False, indent=2, sort_keys=True)
                tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_name = tmp.name
            os.replace(tmp_name, self.state_path)
        except OSError as exc:
            if tmp_name:
                try:
                    Path(tmp_name).unlink(missing_ok=True)
                except OSError:
                    pass
            raise DirectionSyncError(f"ack_write_failed:{exc}") from exc

    def check(self, agent: str, *, paths: list[str] | tuple[str, ...] = ()) -> SyncCheck:
        try:
            revision, assignments = self._snapshot()
        except DirectionSyncError as exc:
            reason = "invalid_active_work" if str(exc).startswith("active_work_") else "direction_unavailable"
            return SyncCheck(False, reason, "")

        own = next((item for item in assignments if item["agent"] == agent), None)
        if own is None:
            return SyncCheck(False, "agent_not_assigned", revision)

        try:
            state = self._load_state()
        except DirectionSyncError:
            return SyncCheck(False, "invalid_ack_state", revision)
        ack = state["agents"].get(agent)
        if ack is None:
            return SyncCheck(False, "not_acknowledged", revision)
        if not isinstance(ack, dict) or not isinstance(ack.get("revision"), str):
            return SyncCheck(False, "invalid_ack_state", revision)
        if ack["revision"] != revision:
            return SyncCheck(False, "stale_direction", revision)

        conflicts: list[dict[str, str]] = []
        for path in paths:
            foreign_conflict = False
            for item in assignments:
                if item is own or str(item["status"]).upper() != "ACTIVE":
                    continue
                if any(_matches(path, pattern) for pattern in item["exclusive_paths"]):
                    conflicts.append(
                        {
                            "path": path,
                            "owner": str(item["agent"]),
                            "task": str(item["task"]),
                            "restriction": "exclusive",
                        }
                    )
                    foreign_conflict = True
                    break
            if foreign_conflict:
                continue
            if any(_matches(path, pattern) for pattern in own["read_only_paths"]):
                conflicts.append(
                    {
                        "path": path,
                        "owner": agent,
                        "task": str(own["task"]),
                        "restriction": "read_only",
                    }
                )
        if conflicts:
            return SyncCheck(False, "ownership_conflict", revision, conflicts)
        return SyncCheck(True, "current", revision)


def _default_paths() -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parents[1]
    return (
        root / "docs" / "handoffs" / "UNI_MASTER_DIRECTION.md",
        root / "docs" / "handoffs" / "UNI_ACTIVE_WORK.md",
        root / ".uni-dev" / "coordination" / "direction_ack.json",
    )


def _build_parser() -> argparse.ArgumentParser:
    master, active, state = _default_paths()
    parser = argparse.ArgumentParser(description="UNI project direction synchronization gate")
    parser.add_argument("--master", default=str(master))
    parser.add_argument("--active", default=str(active))
    parser.add_argument("--state", default=str(state))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show")
    ack = sub.add_parser("ack")
    ack.add_argument("--agent", required=True)
    check = sub.add_parser("check")
    check.add_argument("--agent", required=True)
    check.add_argument("--path", action="append", default=[])
    return parser


def _error_reason(exc: DirectionSyncError) -> str:
    message = str(exc)
    if message.startswith("active_work_"):
        return "INVALID_ACTIVE_WORK"
    if message.startswith("agent_not_assigned"):
        return "AGENT_NOT_ASSIGNED"
    if message == "invalid_ack_state":
        return "INVALID_ACK_STATE"
    return "DIRECTION_UNAVAILABLE"


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    gate = DirectionSyncGate(args.master, args.active, args.state)

    if args.command == "show":
        try:
            revision, assignments = gate._snapshot()
        except DirectionSyncError as exc:
            print(f"DENIED / {_error_reason(exc)} / {exc}")
            return 2
        print(f"REVISION / {revision}")
        for item in assignments:
            print(f"ASSIGNMENT / {item['agent']} / {item['status']} / {item['task']}")
        return 0

    if args.command == "ack":
        try:
            record = gate.acknowledge(args.agent)
        except DirectionSyncError as exc:
            print(f"DENIED / {_error_reason(exc)} / {exc}")
            return 2
        print(f"ACK / {args.agent} / {record['revision']}")
        return 0

    check = gate.check(args.agent, paths=args.path)
    if check.ok:
        print(f"ALLOW / CURRENT / {check.revision}")
        return 0
    print(f"DENIED / {check.reason.upper()} / {check.revision or '-'}")
    for conflict in check.conflicts:
        print(
            "CONFLICT / "
            f"{conflict.get('path', '')} / {conflict.get('owner', '')} / "
            f"{conflict.get('restriction', '')}"
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
