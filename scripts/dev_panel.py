"""
UNI Dev Panel — локальная панель разработчика.

Показывает: задачи devcoord (создание/статус/шаги), живой лог текущей сессии,
факты working memory. НЕ подменяет собой продуктовый GUI — это инструмент
для тебя, чтобы видеть, что происходит внутри, и отправлять задачи руками,
пока ядро (uni/) не стабилизировано под манифест.

Установка (доп. зависимости, которых нет в requirements.txt):
    pip install fastapi uvicorn

Запуск из корня репозитория UNI-test:
    python scripts/dev_panel.py

Откроется на http://127.0.0.1:8765

Важно: панель работает поверх той же CoordinationStore (.uni-dev/coordination/state.json),
что и uni/devcoord — то есть создание задачи здесь реально ставит её в очередь.
"RUN" на провайдере с transport=browser запускает тот самый BrowserProvider
из uni/council/provider.py — я предупреждал раньше, что автоматизация чужих
платных веб-чатов, скорее всего, нарушает их условия использования. Панель
это не блокирует технически, но помечает такие шаги жёлтым — решение за тобой.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from uni.devcoord.config import load_development_config
from uni.devcoord.coordinator import DevelopmentCoordinator
from uni.devcoord.models import DevelopmentTask
from uni.devcoord.providers import ProviderRegistry
from uni.devcoord.store import CoordinationStore
from uni.working_memory import WorkingMemory

DEV_CONFIG_PATH = REPO_ROOT / "uni-dev.yaml"
LOGS_ROOT = REPO_ROOT / ".uni-logs"
MEMORY_PATH = REPO_ROOT / "memory" / "working.json"

app = FastAPI(title="UNI Dev Panel")

# ---------------------------------------------------------------------------
# Wiring — reuse the real devcoord objects, not a re-implementation.
# ---------------------------------------------------------------------------
if DEV_CONFIG_PATH.exists():
    dev_config = load_development_config(DEV_CONFIG_PATH)
else:
    from uni.devcoord.config import DevelopmentCoordinatorConfig
    dev_config = DevelopmentCoordinatorConfig()  # defaults, no providers configured yet

store = CoordinationStore(REPO_ROOT / dev_config.state_path)
providers = ProviderRegistry(dev_config.providers, allow_paid_api=dev_config.allow_paid_api)
coordinator = DevelopmentCoordinator(REPO_ROOT, store, providers)
memory = WorkingMemory(path=MEMORY_PATH) if MEMORY_PATH.exists() else None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class NewTaskRequest(BaseModel):
    title: str
    goal: str
    instructions: str
    required_capabilities: list[str] = []
    provider_sequence: list[str] = []
    requested_provider_count: int = 1


@app.get("/api/tasks")
def list_tasks():
    tasks = sorted(store.list_tasks(), key=lambda t: t.updated_at, reverse=True)
    return [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "provider_sequence": t.provider_sequence,
            "next_provider_index": t.next_provider_index,
            "updated_at": t.updated_at,
        }
        for t in tasks
    ]


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    try:
        task = store.get_task(task_id)
    except KeyError:
        raise HTTPException(404, "task not found")
    events = store.events_for(task_id)
    provider_meta = {p.id: {"transport": p.transport, "cost": p.api_cost} for p in dev_config.providers}
    return {
        "task": task.model_dump(mode="json"),
        "events": [e.model_dump(mode="json") for e in events],
        "provider_meta": provider_meta,
    }


@app.post("/api/tasks")
def create_task(req: NewTaskRequest):
    task = DevelopmentTask(
        title=req.title,
        goal=req.goal,
        instructions=req.instructions,
        required_capabilities=req.required_capabilities,
        provider_sequence=req.provider_sequence,
        requested_provider_count=req.requested_provider_count,
    )
    try:
        created = coordinator.create_task(task)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return created.model_dump(mode="json")


@app.post("/api/tasks/{task_id}/run_next")
async def run_next(task_id: str):
    try:
        task = await coordinator.run_next(task_id)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return task.model_dump(mode="json")


@app.post("/api/tasks/{task_id}/run_all")
async def run_all(task_id: str):
    try:
        task = await coordinator.run_all(task_id)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    return task.model_dump(mode="json")


@app.get("/api/providers")
def list_providers():
    return [p.model_dump(mode="json") for p in dev_config.providers]


@app.get("/api/logs/sessions")
def list_sessions():
    if not LOGS_ROOT.exists():
        return []
    sessions = sorted((d.name for d in LOGS_ROOT.iterdir() if d.is_dir()), reverse=True)
    return sessions[:30]


@app.get("/api/logs/{session}/tail")
def tail_log(session: str, lines: int = 200):
    log_path = LOGS_ROOT / session / "session.log"
    if not log_path.exists():
        raise HTTPException(404, "log not found")
    text_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return text_lines[-lines:]


@app.get("/api/memory")
def get_memory():
    if memory is None:
        return {"facts": {}, "note": f"{MEMORY_PATH} ещё не создан — запусти UNI хотя бы раз"}
    return {"facts": memory.data["facts"], "recent_dialogue": memory.data["dialogue"][-10:]}


# ---------------------------------------------------------------------------
# Frontend — one static page, polls the API above.
# ---------------------------------------------------------------------------
INDEX_HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>UNI Dev Panel</title>
<style>
  :root { --bg:#0f1117; --panel:#171a23; --border:#2a2e3a; --text:#e6e8ee; --muted:#8b90a0;
          --accent:#5b8cff; --ok:#3ecf8e; --warn:#e6b450; --err:#ef5a5a; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }
  header { padding:14px 20px; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:12px; }
  header h1 { font-size:16px; margin:0; font-weight:600; }
  header .dot { width:8px; height:8px; border-radius:50%; background:var(--ok); }
  main { display:grid; grid-template-columns: 340px 1fr 380px; gap:16px; padding:16px; height:calc(100vh - 53px); }
  .panel { background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:14px; overflow-y:auto; }
  .panel h2 { font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); margin:0 0 10px; }
  .task { padding:10px; border:1px solid var(--border); border-radius:8px; margin-bottom:8px; cursor:pointer; }
  .task:hover { border-color: var(--accent); }
  .task.active { border-color: var(--accent); background:#1b2030; }
  .task .title { font-weight:600; margin-bottom:4px; }
  .badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600; }
  .badge.pending { background:#2a2e3a; color:var(--muted); }
  .badge.running { background:#2a3550; color:var(--accent); }
  .badge.awaiting_review { background:#2a4436; color:var(--ok); }
  .badge.failed { background:#442a2a; color:var(--err); }
  textarea, input { width:100%; background:#0d0f15; border:1px solid var(--border); border-radius:6px;
                     color:var(--text); padding:8px; font-family:inherit; margin-bottom:8px; }
  textarea { min-height:60px; resize:vertical; }
  button { background:var(--accent); border:none; color:#fff; padding:8px 14px; border-radius:6px;
           cursor:pointer; font-weight:600; font-size:13px; }
  button.secondary { background:#2a2e3a; }
  button:hover { opacity:.9; }
  button:disabled { opacity:.4; cursor:not-allowed; }
  .log-line { font-family:Consolas,monospace; font-size:12px; white-space:pre-wrap; word-break:break-all;
              border-bottom:1px solid #1c2029; padding:3px 0; color:var(--muted); }
  .event { font-size:12px; padding:6px 0; border-bottom:1px solid #1c2029; }
  .event .kind { color:var(--accent); font-weight:600; }
  select { width:100%; background:#0d0f15; border:1px solid var(--border); color:var(--text);
           padding:8px; border-radius:6px; margin-bottom:8px; }
  .transport-browser { color: var(--warn); }
  .transport-api { color: var(--ok); }
  .muted { color: var(--muted); }
  .row { display:flex; gap:8px; }
  .fact { font-family:Consolas,monospace; font-size:12px; padding:4px 0; border-bottom:1px solid #1c2029; }
</style>
</head>
<body>
<header><span class="dot"></span><h1>UNI Dev Panel</h1><span class="muted" id="clock"></span></header>
<main>
  <section class="panel" id="tasks-panel">
    <h2>Новая задача</h2>
    <input id="new-title" placeholder="Заголовок">
    <textarea id="new-goal" placeholder="Цель (goal)"></textarea>
    <textarea id="new-instructions" placeholder="Инструкции для исполнителя"></textarea>
    <input id="new-capabilities" placeholder="required_capabilities через запятую (или пусто)">
    <button onclick="createTask()">Создать задачу</button>
    <h2 style="margin-top:18px">Задачи</h2>
    <div id="task-list">Загрузка…</div>
  </section>

  <section class="panel" id="detail-panel">
    <h2>Детали задачи</h2>
    <div id="task-detail" class="muted">Выбери задачу слева</div>
    <h2 style="margin-top:18px">Живой лог сессии</h2>
    <select id="session-select" onchange="loadLog()"></select>
    <div id="log-view"></div>
  </section>

  <section class="panel" id="memory-panel">
    <h2>Working memory — факты</h2>
    <div id="memory-view">Загрузка…</div>
  </section>
</main>

<script>
let activeTaskId = null;

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) { alert(await r.text()); throw new Error(r.status); }
  return r.json();
}

function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

async function refreshTasks() {
  const tasks = await api('/api/tasks');
  const list = document.getElementById('task-list');
  list.innerHTML = tasks.map(t => `
    <div class="task ${t.id === activeTaskId ? 'active' : ''}" onclick="selectTask('${t.id}')">
      <div class="title">${t.title}</div>
      ${badge(t.status)}
      <span class="muted"> · шаг ${t.next_provider_index}/${t.provider_sequence.length}</span>
    </div>`).join('') || '<div class="muted">Пока нет задач</div>';
}

async function createTask() {
  const caps = document.getElementById('new-capabilities').value
    .split(',').map(s => s.trim()).filter(Boolean);
  const body = {
    title: document.getElementById('new-title').value || 'Без названия',
    goal: document.getElementById('new-goal').value,
    instructions: document.getElementById('new-instructions').value,
    required_capabilities: caps,
  };
  if (!body.goal || !body.instructions) { alert('Заполни goal и instructions'); return; }
  const task = await api('/api/tasks', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  document.getElementById('new-title').value = '';
  document.getElementById('new-goal').value = '';
  document.getElementById('new-instructions').value = '';
  await refreshTasks();
  selectTask(task.id);
}

async function selectTask(id) {
  activeTaskId = id;
  await refreshTasks();
  const data = await api(`/api/tasks/${id}`);
  const t = data.task;
  const meta = data.provider_meta;
  const stepsHtml = t.provider_sequence.map((p, i) => {
    const m = meta[p] || {};
    const cls = m.transport === 'browser' ? 'transport-browser' : 'transport-api';
    const mark = i < t.next_provider_index ? '✓' : (i === t.next_provider_index ? '→' : '·');
    return `<div class="${cls}">${mark} ${p} <span class="muted">(${m.transport || '?'}, ${m.cost || '?'})</span></div>`;
  }).join('');
  const resultsHtml = t.results.map(r => `
    <div class="event"><span class="kind">${r.provider_id}</span> — ${r.error ? '<span style="color:var(--err)">' + r.error + '</span>' : (r.content.slice(0,300) + (r.content.length>300?'…':''))}</div>
  `).join('');
  document.getElementById('task-detail').innerHTML = `
    <div><b>${t.title}</b> ${badge(t.status)}</div>
    <div class="muted" style="margin:6px 0">${t.goal}</div>
    <div style="margin:8px 0">${stepsHtml || '<span class="muted">providers не назначены</span>'}</div>
    <div class="row" style="margin:10px 0">
      <button onclick="runNext('${t.id}')" ${t.status==='running'?'disabled':''}>Run next step</button>
      <button class="secondary" onclick="runAll('${t.id}')" ${t.status==='running'?'disabled':''}>Run all</button>
    </div>
    <h2>Результаты</h2>
    ${resultsHtml || '<div class="muted">Пока нет результатов</div>'}
  `;
}

async function runNext(id) { await api(`/api/tasks/${id}/run_next`, {method:'POST'}); selectTask(id); }
async function runAll(id) { await api(`/api/tasks/${id}/run_all`, {method:'POST'}); selectTask(id); }

async function loadSessions() {
  const sessions = await api('/api/logs/sessions');
  const sel = document.getElementById('session-select');
  sel.innerHTML = sessions.map(s => `<option value="${s}">${s}</option>`).join('') || '<option>нет логов</option>';
  if (sessions.length) loadLog();
}

async function loadLog() {
  const sel = document.getElementById('session-select');
  if (!sel.value) return;
  const lines = await api(`/api/logs/${sel.value}/tail?lines=150`);
  document.getElementById('log-view').innerHTML = lines.map(l => `<div class="log-line">${l.replace(/</g,'&lt;')}</div>`).join('');
}

async function loadMemory() {
  const mem = await api('/api/memory');
  const facts = Object.entries(mem.facts || {});
  document.getElementById('memory-view').innerHTML = facts.length
    ? facts.map(([k,v]) => `<div class="fact"><b>${k}</b>: ${String(v).slice(0,200)}</div>`).join('')
    : `<div class="muted">${mem.note || 'Пока нет фактов'}</div>`;
}

function tickClock() {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('ru-RU');
}

setInterval(refreshTasks, 4000);
setInterval(loadLog, 4000);
setInterval(loadMemory, 6000);
setInterval(tickClock, 1000);
refreshTasks(); loadSessions(); loadMemory(); tickClock();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
