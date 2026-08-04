"""
step1_real_round.py — Шаг 1 из плана Claude: реальный раунд совета через
живой WebUI-сервер (http://127.0.0.1:8787), участник 'Hermes'.

ВАЖНО (отклонение от инструкции Claude):
  - В коде НЕТ demoAnswerFor() — демо-режима нет. Поэтому критерий
    «ответ не похож на шаблонные фразы из demoAnswerFor» НЕПРИМЕНИМ.
    Вместо этого проверяем: participant_done для Hermes содержит непустой
    text (реальный ответ от модели, а не пустышка).
  - Сервер 8787 НЕ поднимаем (по правилу проекта ровно один WebUI на 8787,
    и он уже запущен). Просто стучимся в живой.

Что делает:
  1. GET /api/participants — печатает статусы (для отчёта).
  2. POST /api/round/start {only:["Hermes"], topic, brief} — читает SSE
     и печатает СЫРЫЕ события до done/error.

Запуск:
  cd /c/LLM/UNI
  PYTHONPATH=/c/LLM/UNI /c/LLM/python312/python.exe tests_probe/step1_real_round.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Гарантируем импорт uni независимо от того, как запущен скрипт.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx

BASE = "http://127.0.0.1:8787"
PARTICIPANT = "Groq"  # по умолчанию локальный (-> LM Studio 1234)
TOPIC = "Короткая проверка реального пути совета"
BRIEF = "Ответь одним предложением: что такое UNI?"


def print_participants() -> None:
    print("--- GET /api/participants ---", flush=True)
    try:
        r = httpx.get(f"{BASE}/api/participants", timeout=10.0)
        print(f"HTTP {r.status_code}", flush=True)
        for p in r.json():
            print(
                f"  {p['name']:<12} {p['transport']:<8} "
                f"{p['status']:<12} {p.get('detail','')}",
                flush=True,
            )
    except Exception as exc:
        print(f"  не удалось получить статусы: {type(exc).__name__}: {exc}", flush=True)


def run_round() -> int:
    print(f"\n--- POST /api/round/start (only=[{PARTICIPANT}]) ---", flush=True)
    payload = {"topic": TOPIC, "brief": BRIEF, "only": [PARTICIPANT]}
    hermes_text = None
    hermes_ok = False
    got_done = False
    start = time.time()
    try:
        with httpx.Client(timeout=httpx.Timeout(180.0)) as client:
            with client.stream("POST", f"{BASE}/api/round/start", json=payload) as resp:
                print(f"HTTP {resp.status_code} (SSE stream open)", flush=True)
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):  # heartbeat ping
                        print(f"[ping] {line}", flush=True)
                        continue
                    if line.startswith("data:"):
                        raw = line[len("data:"):].strip()
                        print(f"[SSE] {raw}", flush=True)
                        if (
                            '"type": "participant_done"' in raw
                            and f'"name": "{PARTICIPANT}"' in raw
                        ):
                            import json as _json

                            try:
                                ev = _json.loads(raw)
                                hermes_text = ev.get("text") or ""
                                hermes_ok = bool(ev.get("ok")) and bool(hermes_text.strip())
                            except Exception:
                                pass
                        if '"type": "done"' in raw or '"type": "error"' in raw:
                            got_done = True
    except Exception as exc:
        print(f"[!] SSE чтение прервано: {type(exc).__name__}: {exc}", flush=True)
        return 2

    elapsed = time.time() - start
    print("\n" + "=" * 40, flush=True)
    print(f"Прошло: {elapsed:.1f}s | participant_done(Hermes) получен: {hermes_ok}", flush=True)
    if hermes_text is not None:
        snippet = hermes_text.strip().replace("\n", " ")[:200]
        print(f"Ответ Hermes (первые 200 симв.): {snippet!r}", flush=True)
    if hermes_ok and got_done:
        print(
            "РЕЗУЛЬТАТ ШАГА 1: ПОДТВЕРЖДЁН — интерфейс достучался до модели, "
            "получен реальный непустой ответ.",
            flush=True,
        )
        return 0
    if got_done and not hermes_ok:
        print(
            "РЕЗУЛЬТАТ ШАГА 1: раунд завершён, но Hermes вернул ошибку/пусто "
            "(см. события выше). Путь интерфейса работает, но провайдер Hermes "
            "не ответил. Смени PARTICIPANT на 'Groq' и повтори.",
            flush=True,
        )
        return 1
    print("РЕЗУЛЬТАТ ШАГА 1: поток закрылся без done/error (таймаут?).", flush=True)
    return 3


def main() -> int:
    print("=== step1_real_round ===", flush=True)
    print(f"BASE={BASE}  PARTICIPANT={PARTICIPANT}", flush=True)
    print_participants()
    return run_round()


if __name__ == "__main__":
    sys.exit(main())
