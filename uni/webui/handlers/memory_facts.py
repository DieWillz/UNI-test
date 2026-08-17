"""Извлечение фактов из диалогов (P-07, 2026-08-17).

Эндпоинты:
  POST /api/memory/extract_facts — извлечь (subject, predicate, object) из последних реплик
  GET  /api/memory/facts         — список фактов
  POST /api/memory/compact       — удалить старые диалоги и дубли
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from . import registry

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_WORKING = _ROOT / "memory" / "working.json"


def _load_working() -> dict[str, Any]:
    if not _WORKING.is_file():
        return {"facts": {}, "dialogue": []}
    try:
        return json.loads(_WORKING.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"facts": {}, "dialogue": []}


def _save_working(data: dict[str, Any]) -> None:
    _WORKING.parent.mkdir(parents=True, exist_ok=True)
    _WORKING.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_body(handler) -> dict:
    try:
        return json.loads(
            (handler.rfile.read(int(handler.headers.get("Content-Length") or 0)) or b"{}").decode("utf-8")
        )
    except Exception:
        return {}


def _list_facts(handler) -> None:
    data = _load_working()
    handler._json(200, {
        "facts": data.get("facts") or {},
        "count": sum(len(v) for v in (data.get("facts") or {}).values()),
        "dialogue_turns": len(data.get("dialogue") or []),
    })


_PATTERNS = [
    (r"меня зовут\s+([А-ЯЁа-яёA-Za-z ]+)", "пользователь", "имя"),
    (r"я живу в\s+([А-ЯЁа-яёA-Za-z -]+)", "пользователь", "живёт в"),
    (r"я работаю\s+([А-ЯЁа-яёA-Za-z ]+)", "пользователь", "работает"),
    (r"мне\s+(\d+)\s*(?:лет|год|года)", "пользователь", "возраст"),
    (r"любим(?:ый|ая|ое)\s+([А-ЯЁа-яёA-Za-z ]+)", "пользователь", "любимое"),
]


def extract_facts_from_text(text: str) -> list[dict[str, str]]:
    """Rule-based извлечение. Публичный API (можно использовать вне HTTP)."""
    extracted: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for pat, subj, pred in _PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            obj = " ".join(m.group(1).strip().split())[:100]
            key = (subj.casefold(), pred.casefold(), obj.casefold())
            if not obj or key in seen:
                continue
            seen.add(key)
            extracted.append({
                "subject": subj, "predicate": pred,
                "object": obj, "ts": time.time(),
            })
    return extracted


def _extract_facts(handler) -> None:
    body = _read_body(handler)
    n = max(1, min(50, int(body.get("n", 5))))
    data = _load_working()
    dialogue = data.get("dialogue") or []
    if not dialogue:
        handler._json(200, {"ok": True, "extracted": 0, "reason": "empty_dialogue"}); return
    recent = dialogue[-n:]
    text = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in recent)

    extracted = extract_facts_from_text(text)

    facts = data.get("facts") or {}
    for f in extracted:
        subj = f["subject"]
        bucket = facts.setdefault(subj, [])
        if not any(b.get("predicate") == f["predicate"] and b.get("object") == f["object"] for b in bucket):
            bucket.append({"predicate": f["predicate"], "object": f["object"], "ts": f["ts"]})
    data["facts"] = facts
    _save_working(data)

    handler._json(200, {
        "ok": True, "extracted": len(extracted),
        "facts_total": sum(len(v) for v in facts.values()), "samples": extracted[:5],
    })


def _compact(handler) -> None:
    body = _read_body(handler)
    max_age_days = max(1, min(365, int(body.get("max_age_days", 30))))
    cutoff = time.time() - max_age_days * 86400
    data = _load_working()
    dialogue = data.get("dialogue") or []
    before = len(dialogue)
    seen: set[str] = set()
    kept: list[dict] = []
    for m in dialogue:
        ts = m.get("ts")
        if isinstance(ts, (int, float)) and ts < cutoff:
            continue
        key = f"{m.get('role')}:{m.get('content','')[:200]}"
        if key in seen:
            continue
        seen.add(key)
        kept.append(m)
    data["dialogue"] = kept
    _save_working(data)
    handler._json(200, {"ok": True, "removed": before - len(kept), "remaining": len(kept)})


registry.register("GET", "/api/memory/facts", _list_facts, "список фактов")
registry.register("POST", "/api/memory/extract_facts", _extract_facts, "извлечь факты из диалога")
registry.register("POST", "/api/memory/compact", _compact, "компактизация диалога")
