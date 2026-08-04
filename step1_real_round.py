"""
Шаг 1 плана MVP: один реальный раунд через ОДНОГО провайдера, без браузерных
участников (сознательно — см. план: браузерная автоматизация исключена из core).

Пробует Hermes (локальный, через LM Studio) первым — он не требует внешнего
API-ключа и самый дешёвый способ подтвердить, что весь путь
webui -> devcoord/council -> provider -> реальный ответ работает целиком.

Запуск (сервер uni.webui должен уже быть поднят на 127.0.0.1:8787):
    C:\\LLM\\python312\\python.exe step1_real_round.py
"""
import json
import urllib.request

URL = "http://127.0.0.1:8787/api/round/start"
PARTICIPANT = "Hermes"  # смени на "Groq" если Hermes/LM Studio не поднят

payload = {
    "topic": "Проверка статуса ИИ",
    "brief": "Кратко (1 предложение) подтвердите, что вы на связи и готовы к работе над проектом UNI.",
    "files": {},
    "tasks": [],
    "only": [PARTICIPANT],
    "enabled": [PARTICIPANT],
}

req = urllib.request.Request(
    URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

print(f"-> Отправляю раунд участнику: {PARTICIPANT}\n")

with urllib.request.urlopen(req, timeout=120) as resp:
    for raw_line in resp:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if line.startswith("data: "):
            try:
                ev = json.loads(line[6:])
            except json.JSONDecodeError:
                print("[не распарсилось]", line)
                continue
            print(f"[{ev.get('type')}]", {k: v for k, v in ev.items() if k != "type"})
            if ev.get("type") == "done":
                print("\n-> Раунд завершён. Если text/answer выше — не пустая строка")
                print("   и не совпадает с demoAnswerFor() из консоли — это реальный ответ.")
