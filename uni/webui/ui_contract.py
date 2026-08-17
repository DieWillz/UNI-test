"""Серверный контракт универсального UI-движка Юни (Директива §3, U-04/U-05).

Здесь сосредоточена ВСЯ валидация и композиция ui_events на бэкенде:
- белый список типов компонентов (canon);
- нормализация алиасов (progress_task -> task_steps и т.п.);
- очистка/валидация полей (никакого HTML/скриптов от модели — фронт и так
  рендерит через textContent, но бэкенд дублирует защиту: src только
  /api|runtime, actions только из карты);
- карта action_id -> реальное действие (U-05), чтобы не было «мёртвых кнопок».

Фронт (uni/desktop/renderer/app.js) НЕ классифицирует по ключевым словам и
НЕ генерирует HTML — он только рисует эту специфу.
"""
from __future__ import annotations

import re
from typing import Any

# ── Канон компонентов (U-03) ────────────────────────────────────────────────
CANON_COMPONENTS = (
    "task_steps",
    "result_text",
    "result_gallery",
    "result_list",
    "comparison_table",
    "mission_card",
    "approval_required",
    "form",
    "link_list",
)

# Алиасы -> канон (U-02). Фронт и бэкенд нормализуют одинаково.
_ALIASES = {
    "progress_task": "task_steps",
    "gallery": "result_gallery",
    "text": "result_text",
    "table": "comparison_table",
    "mission": "mission_card",
    "list": "result_list",
    "approval": "approval_required",
}

# Типы событий (dispatcher-ключи фронта).
CANON_EVENT_TYPES = (
    "task.started", "task.update", "task.verified", "task.not_verified",
    "task.failed", "task.blocked", "task.interrupted", "task.error",
    "mission.started", "mission.update", "mission.verified", "mission.not_verified",
    "approval.required",
)

# Разрешённые префиксы для src изображений/ссылок (U-04).
_ALLOWED_SRC_PREFIXES = ("/api/", "/runtime/", "/assets/", "runtime/", "assets/")

# Карта действий (U-05): id -> человекочитаемое описание реального действия.
# Значение — не исполняемый код (сервер однопоточный HTTP), а маршрут/флаг,
# который оркестратор в реальном агенте трактует однозначно. Здесь для каждого
# id возвращаем {"action_id", "handler", "params"} — оркестратор вызывает
# handler. Кнопка without соответствующего id НЕ рендерится (см. фронт).
ACTION_MAP = {
    "approve":        {"handler": "mission.approve",        "params": {}},
    "confirm":        {"handler": "mission.confirm",        "params": {}},
    "reject":         {"handler": "mission.reject",         "params": {}},
    "open_all":       {"handler": "gallery.open_all",       "params": {}},
    "open":           {"handler": "gallery.open",           "params": {"index": "__arg__"}},
    "save":           {"handler": "result.save",            "params": {}},
    "copy":           {"handler": "result.copy",            "params": {}},
    "dismiss":        {"handler": "card.dismiss",           "params": {}},
    "retry":          {"handler": "task.retry",             "params": {}},
    "more":           {"handler": "result.more",            "params": {}},
    "link_open":      {"handler": "link.open",              "params": {"url": "__arg__"}},
    "submit_form":    {"handler": "form.submit",            "params": {"fields": "__arg__"}},
}


def normalize_component(name: str) -> str:
    if not name:
        return "result_text"
    n = str(name).strip()
    return _ALIASES.get(n, n)


def _clean_src(value: Any) -> str:
    """Очищает src/url: только разрешённые локальные префиксы, иначе ''."""
    if not isinstance(value, str):
        return ""
    v = value.strip()
    if not v:
        return ""
    # Блокируем абсолютные внешние URL и протоколы (javascript:, data:, http(s)://)
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", v):
        if v.startswith(("http://", "https://", "javascript:", "data:", "file://")):
            return ""
    if any(v.startswith(p) for p in _ALLOWED_SRC_PREFIXES):
        return v
    # относительный путь без схемы — разрешаем только если выглядит локально
    if v.startswith(("/", "runtime/", "assets/")):
        return v
    return ""


def _clean_text(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    return str(value)[:limit]


def validate_component(spec: dict) -> dict | None:
    """Валидирует и нормализует ОДИН компонент-спек. None -> отбросить."""
    if not isinstance(spec, dict):
        return None
    comp = normalize_component(spec.get("component") or spec.get("type") or "")
    if comp not in CANON_COMPONENTS:
        comp = "result_text"
    out: dict[str, Any] = {"component": comp}
    # текстовые/строковые поля
    for k in ("title", "subtitle", "text", "message", "stage", "current_action",
              "mission_id", "task_id", "summary"):
        if k in spec:
            out[k] = _clean_text(spec[k])
    # числа
    if "percent" in spec:
        try: out["percent"] = max(0, min(100, int(spec["percent"])))
        except (TypeError, ValueError): out["percent"] = 0
    # items (галерея/список/сравнение/ссылки)
    items = spec.get("items")
    if isinstance(items, list):
        cleaned = []
        for it in items[:24]:
            if isinstance(it, dict):
                ci = {"title": _clean_text(it.get("title")),
                      "description": _clean_text(it.get("description") or it.get("text")),
                      "text": _clean_text(it.get("text") or it.get("description"))}
                src = _clean_src(it.get("image_url") or it.get("src") or it.get("url") or it.get("href"))
                if src:
                    ci["src"] = src
                if it.get("url") or it.get("href"):
                    u = _clean_src(it.get("url") or it.get("href"))
                    if u:
                        ci["url"] = u
                cleaned.append(ci)
            elif isinstance(it, str):
                cleaned.append({"text": _clean_text(it)})
        out["items"] = cleaned
    # comparison_table: rows (список словарей)
    rows = spec.get("rows")
    if isinstance(rows, list) and not out.get("items"):
        out["items"] = [
            {_clean_text(k): _clean_text(v) for k, v in (r.items() if isinstance(r, dict) else [("text", str(r))])}
            for r in rows[:24]
        ]
    # actions — ТОЛЬКО из карты (U-05): мёртвых кнопок нет
    actions = spec.get("actions")
    if isinstance(actions, list):
        out_actions = []
        for a in actions[:8]:
            aid = (a.get("id") or a.get("action_id") or "") if isinstance(a, dict) else str(a)
            if aid in ACTION_MAP:
                entry = {"id": aid, "label": _clean_text(a.get("label") if isinstance(a, dict) else aid, 60)}
                out_actions.append(entry)
        if out_actions:
            out["actions"] = out_actions
    # requires_confirmation — булев флаг (U-05: approval_required ТОЛЬКО при нём)
    if "requires_confirmation" in spec:
        out["requires_confirmation"] = bool(spec["requires_confirmation"])
    # metrics (миссия) — числа
    metrics = spec.get("metrics")
    if isinstance(metrics, dict):
        out["metrics"] = {
            "confirmed_rub": _num(metrics.get("confirmed_rub")),
            "expected_rub": _num(metrics.get("expected_rub")),
            "spent_rub": _num(metrics.get("expected_rub") if False else metrics.get("spent_rub")),
        }
    # form (U-03): поля формы
    form = spec.get("form")
    if isinstance(form, dict) and comp == "form":
        fields = []
        for f in (form.get("fields") or [])[:16]:
            if isinstance(f, dict):
                fields.append({
                    "name": _clean_text(f.get("name"), 60),
                    "label": _clean_text(f.get("label"), 120),
                    "type": _clean_text(f.get("type"), 20) or "text",
                    "placeholder": _clean_text(f.get("placeholder"), 120),
                })
        out["form"] = {"fields": fields, "submit_label": _clean_text(form.get("submit_label"), 60) or "Отправить"}
    return out


def _num(v: Any) -> int | float:
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return 0


def validate_ui_events(events: Any) -> list[dict]:
    """Валидирует список ui_events. Невалидные -> честный текстовый пузырь."""
    if not isinstance(events, list):
        return []
    out = []
    for ev in events[:16]:
        if not isinstance(ev, dict) or not ev.get("type"):
            continue
        if ev["type"] not in CANON_EVENT_TYPES:
            # неизвестный тип — фронт сам упадёт в текстовый пузырь; пропускаем
            continue
        clean = {"type": ev["type"]}
        for k in ("task_id", "mission_id", "title", "message", "subtitle", "status"):
            if k in ev:
                clean[k] = _clean_text(ev[k])
        if ev["type"] == "approval.required":
            # 🤖 approval_required — самостоятельное событие (без ui-спека).
            # actions ТОЛЬКО из карты (U-05); нет в карте -> дефолт approve.
            clean["title"] = _clean_text(ev.get("title") or "Требуется подтверждение")
            clean["text"] = _clean_text(ev.get("text"))
            acts = []
            for a in (ev.get("actions") or [])[:8]:
                aid = (a.get("id") or a.get("action_id") or "") if isinstance(a, dict) else str(a)
                if aid in ACTION_MAP:
                    acts.append({"id": aid, "label": _clean_text(a.get("label") if isinstance(a, dict) else aid, 60)})
            clean["actions"] = acts or [{"id": "approve", "label": "Подтвердить"}]
        elif ev.get("ui") is not None:
            vc = validate_component(ev["ui"]) if isinstance(ev["ui"], dict) else None
            if vc is not None:
                clean["ui"] = vc
        verification = ev.get("verification")
        if isinstance(verification, dict):
            clean_evidence = []
            for item in (verification.get("evidence") or [])[:16]:
                if isinstance(item, dict):
                    clean_evidence.append({
                        "id": _clean_text(item.get("id"), 80),
                        "source": _clean_text(item.get("source"), 160),
                        "summary": _clean_text(item.get("summary"), 1000),
                        "timestamp": _clean_text(item.get("timestamp"), 80),
                    })
            clean["verification"] = {
                "status": _clean_text(verification.get("status"), 40),
                "method": _clean_text(verification.get("method"), 160),
                "reason": _clean_text(verification.get("reason"), 1000),
                "evidence": clean_evidence,
            }
        out.append(clean)
    return out


def resolve_action(action_id: str, task_id: str | None = None) -> dict:
    """U-05: карта id -> реальное действие. Нет в карте -> честная ошибка."""
    aid = str(action_id or "").strip()
    if aid not in ACTION_MAP:
        return {"ok": False, "error": f"unknown action_id: {aid!r}",
                "known": sorted(ACTION_MAP)}
    entry = ACTION_MAP[aid]
    return {"ok": True, "action_id": aid, "handler": entry["handler"],
            "params": entry["params"], "task_id": task_id or None,
            "accepted": True}
