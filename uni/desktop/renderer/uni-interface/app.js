// Юни — интерфейс v4: универсальный UI-движок (Hermes 2026-08-13).
// Директива: «универсальный UI-движок Юни». Фронт НЕ решает по ключевым словам,
// какой интерфейс показать — это решает backend/LLM. Фронт только рисует
// полученную структурную специфу через диспетчер applyUiEvent + библиотеку
// из 7 компонентов (progress_task/task_steps, result_text, result_gallery,
// result_list, comparison_table, mission_card, approval_required).
// Старый вариант (canon-design/) не трогаем.
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const widget = $('#uniWidget');
const avatar = $('#avatar');
const toast = $('#toast');

// Прозрачная область пропускает мышь, сама панель всегда принимает клики.
if (window.uni?.hitTest) {
  document.addEventListener('mousemove', (event) => {
    window.uni.hitTest(Boolean(event.target.closest('#uniWidget')));
  });
  document.addEventListener('mouseleave', () => window.uni.hitTest(false));
  window.uni.hitTest(true);
}

// Базовый URL backend (WebUI на 8787). Electron loadFile → file://, нужен абсолютный URL.
const API = 'http://127.0.0.1:8787';

const state = {
  mode: 'quick', stopped: false, observing: true, listening: false,
  minimized: false, avatar: 'working', consentLevel: 'off', busy: false,
  pollTimer: null,
};

// ---------- утилиты ----------
function notify(text) {
  toast.textContent = text; toast.classList.add('show');
  clearTimeout(notify.t);
  notify.t = setTimeout(() => toast.classList.remove('show'), 1800);
}
// Аватар — 4 PNG-состояния (uni-small-*.png), накладываются поверх окна.
const AVATAR_MAP = {
  listening: 'listen', working: 'work', waiting: 'wait',
  done: 'done', idle: 'work',
};
const avatarImg = $('#avatarImg');
function setAvatar(next) {
  state.avatar = next;
  const key = AVATAR_MAP[next] || 'work';
  if (avatarImg) {
    avatarImg.src = `../assets/uni-small-${key}.png`;
    avatarImg.alt = `Юни: ${next}`;
  }
  avatar.className = `avatar avatar--${next}`;
  avatar.setAttribute('aria-label', `Состояние Юни: ${next}`);
}
function setStatus(text, avatarState = 'working') {
  $('#headerStatus').textContent = text;
  if (avatarState) setAvatar(avatarState);
}

function setAction(kind, text, mode = state.mode) {
  const mission = mode === 'mission';
  const strip = $(mission ? '#missionActionStrip' : '#quickActionStrip');
  const label = $(mission ? '#missionAction' : '#quickAction');
  if (!strip || !label) return;
  strip.classList.remove('busy', 'done', 'error');
  strip.classList.add(kind);
  label.textContent = text;
  state.busy = kind === 'busy';
}

// ---------- безопасный рендер шагов ----------
function renderSteps(target, steps) {
  if (!target) return;
  const list = Array.isArray(steps) ? steps : [];
  target.replaceChildren(...list.map((step) => {
    const row = document.createElement('div');
    const s = step || {};
    row.className = `step ${s.state || ''}`;
    row.append(document.createTextNode(s.text || ''));
    return row;
  }));
}

// ---------- контейнер динамических карточек ----------
function dynamicCards() {
  let el = $('#dynamicCards');
  if (!el) {
    el = document.createElement('div');
    el.id = 'dynamicCards';
    el.className = 'dynamic-cards';
    const qm = $('#quickMode');
    qm?.insertBefore(el, qm.querySelector(':scope > .result-card, :scope > .action-strip') || null);
  }
  return el;
}
// создаём уникальную карточку для task/mission (data-task-id для авто-сворачивания)
function makeCard(taskId) {
  const card = document.createElement('article');
  card.className = 'ui-card';
  card.dataset.taskId = taskId || '';
  dynamicCards().append(card);
  return card;
}

// ============================================================
// УНИВЕРСАЛЬНЫЙ ДИСПЕТЧЕР (Директива §4)
// ============================================================
function applyUiEvent(event) {
  if (!event || !event.type) return;
  switch (event.type) {
    case 'task.started':
    case 'task.update':   return renderTaskUpdate(event);
    case 'task.verified': return renderTaskDone(event);
    case 'task.not_verified': return renderTaskNotVerified(event);
    case 'task.failed':
    case 'task.blocked':
    case 'task.interrupted':
    case 'task.error':    return renderTaskError(event);
    case 'mission.started':
    case 'mission.update':return renderMissionUpdate(event);
    case 'mission.verified': return renderMissionDone(event);
    case 'mission.not_verified': return renderTaskNotVerified(event);
    case 'approval.required': return renderApproval(event);
    default:
      // неизвестный тип — честный текстовый пузырь, не падаем
      if (event.message) addBubble(event.message, 'uni');
      return;
  }
}

// --------- защищённые render-функции (не падают на частичном JSON) ---------
function renderTaskUpdate(event) {
  const e = event || {};
  const card = (e.task_id && $(`[data-task-id="${CSS.escape(e.task_id)}]`)) || makeCard(e.task_id);
  const title = e.title || 'Задача';
  const mode = e.mode === 'mission' ? 'mission' : 'quick';
  if (mode === 'mission') setMode('mission'); else setMode('quick');
  const steps = Array.isArray(e.steps) ? e.steps : [];
  const progress = e.progress || {};
  const done = Number(progress.done ?? 0);
  const total = Number(progress.total ?? steps.length ?? 0);
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  card.innerHTML = '';
  const titleEl = document.createElement('div');
  titleEl.className = 'ui-card-title';
  titleEl.append(document.createTextNode(title));
  card.append(titleEl);
  const stepsEl = document.createElement('div');
  stepsEl.className = 'steps';
  renderSteps(stepsEl, steps);
  card.append(stepsEl);
  if (total > 0) {
    const pr = document.createElement('div');
    pr.className = 'progress-row';
    pr.innerHTML = `<div class="progress"><i style="width:${pct}%"></i></div><span>${done}/${total}</span>`;
    card.append(pr);
  }
  if (e.status) {
    const st = document.createElement('div');
    st.className = 'action-strip busy';
    st.append(document.createTextNode(e.status));
    card.append(st);
  }
  setAction('busy', e.status || 'Выполняю…', mode);
  setStatus('Обрабатываю', 'working');
  hideEmptyChat();
}

function renderTaskDone(event) {
  const e = event || {};
  const ui = e.ui || {};
  const card = (e.task_id && $(`[data-task-id="${CSS.escape(e.task_id)}]`)) || makeCard(e.task_id);
  card.innerHTML = '';
  const titleEl = document.createElement('div');
  titleEl.className = 'ui-card-title';
  titleEl.append(document.createTextNode(e.title || 'Готово'));
  card.append(titleEl);
  renderComponentInto(card, ui);
  setAction('done', 'Готово');
  showReadyBubble('Юни готова');
  setStatus('Готово', 'done');
  // авто-сворачивание карточки в одну строку через ~1.2с (C-06 / Директива §5.3)
  if (e.task_id) {
    setTimeout(() => {
      const c = $(`[data-task-id="${CSS.escape(e.task_id)}"]`);
      c?.classList.add('collapsed');
    }, 1200);
  }
}

function renderTaskNotVerified(event) {
  const e = event || {};
  const ui = e.ui || {};
  const card = (e.task_id && $(`[data-task-id="${CSS.escape(e.task_id)}"]`)) || makeCard(e.task_id);
  card.innerHTML = '';
  const titleEl = document.createElement('div');
  titleEl.className = 'ui-card-title';
  titleEl.append(document.createTextNode(e.title || 'Результат не подтверждён'));
  card.append(titleEl);
  renderComponentInto(card, ui);
  const warning = document.createElement('p');
  warning.className = 'error-text';
  warning.textContent = 'Действие могло выполниться, но независимой проверки результата нет.';
  card.append(warning);
  setAction('error', 'Не подтверждено');
  setStatus('Не подтверждено', 'waiting');
}

function renderTaskError(event) {
  const e = event || {};
  const card = makeCard(e.task_id);
  card.innerHTML = '';
  const p = document.createElement('p');
  p.className = 'error-text';
  p.textContent = e.message || 'Задача завершилась с ошибкой.';
  card.append(p);
  setAction('error', 'Ошибка');
  setStatus('Ошибка', 'waiting');
}

function renderMissionUpdate(event) {
  const e = event || {};
  setMode('mission');
  const card = (e.mission_id && $(`[data-task-id="${CSS.escape(e.mission_id)}"]`)) || makeCard(e.mission_id);
  const percent = Number(e.percent ?? 0);
  const metrics = e.metrics || {};
  const confirmed = metrics.confirmed_rub ?? 0;
  const expected = (metrics.expected_rub == null) ? '—' : `${metrics.expected_rub} ₽`;
  const spent = metrics.spent_rub ?? 0;
  card.innerHTML = '';
  card.insertAdjacentHTML('beforeend', `
    <div class="ui-card-title"><div><b></b><span class="mission-sub"></span></div><span class="mission-percent">${percent}%</span></div>
    <div class="mission-layout">
      <div class="steps mission-steps"></div>
      <div class="mission-now"><div class="action-strip"><span class="mission-action"></span></div>
        <details open><summary>Последние действия</summary><div class="mission-recent"></div></details>
      </div>
    </div>
    <div class="progress-row mission-progress"><div class="progress"><i style="width:${percent}%"></i></div><span class="mission-stage"></span></div>
    <div class="money-row">
      <div><span>Подтверждено</span><b class="mission-confirmed">${confirmed} ₽</b></div>
      <div><span>Ожидается</span><b class="mission-expected">${expected}</b></div>
      <div><span>Затраты</span><b class="mission-costs">${spent} ₽</b></div>
    </div>
  `);
  card.querySelector('.ui-card-title b').textContent = e.title || 'Миссия';
  card.querySelector('.mission-sub').textContent = e.subtitle || '';
  card.querySelector('.mission-stage').textContent = e.stage || '';
  card.querySelector('.mission-action').textContent = e.current_action || '';
  renderSteps(card.querySelector('.mission-steps'), e.steps || []);
  const recent = card.querySelector('.mission-recent');
  (Array.isArray(e.recent) ? e.recent : []).forEach((r) => {
    const p = document.createElement('p'); p.textContent = '• ' + r; recent.append(p);
  });
  // money-row реально заполняется из metrics (§5.2 — не дефолт «0 ₽/—/0 ₽» если данные есть)
  if (e.requires_confirmation) {
    const ap = document.createElement('div');
    ap.className = 'approval-card';
    ap.textContent = 'Для запуска потребуется подтверждение';
    card.append(ap);
  }
  setAction('busy', e.current_action || 'Работаю…', 'mission');
  setStatus('Работаю', 'working');
  hideEmptyChat();
}

function renderMissionDone(event) {
  const e = event || {};
  const card = (e.mission_id && $(`[data-task-id="${CSS.escape(e.mission_id)}"]`)) || makeCard(e.mission_id);
  // оставляем карточку миссии, обновляем статус
  setAction('done', e.title || 'Миссия завершена', 'mission');
  showReadyBubble('Юни ждёт решения');
  setStatus('Жду решения', 'waiting');
}

function renderApproval(event) {
  const e = event || {};
  const card = makeCard(e.task_id || 'approval');
  card.innerHTML = '';
  const ap = document.createElement('div');
  ap.className = 'approval-card';
  const t = document.createElement('b'); t.textContent = e.title || 'Требуется подтверждение';
  ap.append(t);
  if (e.text) { const p = document.createElement('p'); p.textContent = e.text; ap.append(p); }
  const actions = Array.isArray(e.actions) ? e.actions : [];
  actions.forEach((a) => {
    const btn = document.createElement('button');
    btn.className = 'approval-action';
    btn.textContent = a.label || a.id || 'OK';
    btn.onclick = () => {
      // единый endpoint действий (Директива U-07)
      fetch(`${API}/api/ui/action`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action_id: a.id, task_id: e.task_id || null }),
      }).catch(() => {});
      btn.disabled = true; notify('Действие отправлено на подтверждение');
    };
    ap.append(btn);
  });
  if (!actions.length) {
    const btn = document.createElement('button');
    btn.className = 'approval-action';
    btn.textContent = 'Подтвердить';
    btn.onclick = () => { fetch(`${API}/api/ui/action`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: 'approve', task_id: e.task_id || null }) }).catch(() => {});
      btn.disabled = true; };
    ap.append(btn);
  }
  card.append(ap);
  setStatus('Ожидает подтверждения', 'waiting');
}

// --------- библиотека компонентов (ровно 7, Директива §2) ---------
// нормализация алиасов (U-02): progress_task → task_steps
function normalizeComponent(name) {
  const map = { progress_task: 'task_steps', gallery: 'result_gallery',
    text: 'result_text', table: 'comparison_table', mission: 'mission_card',
    list: 'result_list', approval: 'approval_required' };
  return map[name] || name;
}
function renderComponentInto(container, spec) {
  const s = spec || {};
  const comp = normalizeComponent(s.component || 'result_text');
  container.classList.add('ui-component-' + comp.replace(/_/g, '-'));
  switch (comp) {
    case 'task_steps':   return renderTaskStepsInto(container, s);
    case 'result_text':  return renderResultTextInto(container, s);
    case 'result_gallery':return renderResultGalleryInto(container, s);
    case 'result_list':  return renderResultListInto(container, s);
    case 'comparison_table': return renderComparisonInto(container, s);
    case 'approval_required': return renderApprovalSpecInto(container, s);
    case 'mission_card': return renderMissionSpecInto(container, s);
    default:            return renderResultTextInto(container, s);
  }
}
function renderTaskStepsInto(c, s) {
  const stepsEl = document.createElement('div'); stepsEl.className = 'steps';
  renderSteps(stepsEl, s.steps || []);
  c.append(stepsEl);
  const p = s.progress || {}; const total = Number(p.total || 0);
  if (total > 0) { const pr = document.createElement('div'); pr.className = 'progress-row';
    pr.innerHTML = `<div class="progress"><i style="width:${Math.round((Number(p.done||0)/total)*100)}%"></i></div><span>${p.done||0}/${total}</span>`; c.append(pr); }
}
function renderResultTextInto(c, s) {
  const p = document.createElement('p');
  p.textContent = s.text || s.message || 'Готово.';
  c.append(p);
}
function renderResultGalleryInto(c, s) {
  const items = Array.isArray(s.items) ? s.items : [];
  if (!items.length) { const p = document.createElement('p'); p.textContent = 'Результат без вложений'; c.append(p); return; }
  const gal = document.createElement('div'); gal.className = 'result-gallery';
  items.forEach((it) => {
    const cell = document.createElement('div'); cell.className = 'gallery-item';
    const img = document.createElement('img');
    img.src = it.image_url || it.src || ''; img.alt = it.title || '';
    cell.append(img);
    if (it.title) { const cap = document.createElement('small'); cap.textContent = it.title; cell.append(cap); }
    gal.append(cell);
  });
  c.append(gal);
  if (Array.isArray(s.actions) && s.actions.length) renderActionButtons(c, s.actions, s.task_id);
}
function renderResultListInto(c, s) {
  const items = Array.isArray(s.items) ? s.items : [];
  if (!items.length) { const p = document.createElement('p'); p.textContent = 'Список пуст'; c.append(p); return; }
  const list = document.createElement('div'); list.className = 'result-list';
  items.forEach((it) => {
    const row = document.createElement('div'); row.className = 'result-item';
    const t = document.createElement('b'); t.textContent = it.title || '';
    const d = document.createElement('small'); d.textContent = it.description || it.text || '';
    row.append(t, d); list.append(row);
  });
  c.append(list);
}
function renderComparisonInto(c, s) {
  // в окне 336px рисуем КАРТОЧКАМИ, не широкой таблицей (Директива §2)
  const rows = Array.isArray(s.rows) ? s.rows : (Array.isArray(s.items) ? s.items : []);
  if (!rows.length) { const p = document.createElement('p'); p.textContent = 'Нет данных для сравнения'; c.append(p); return; }
  const wrap = document.createElement('div'); wrap.className = 'comparison-cards';
  rows.forEach((r) => {
    const card = document.createElement('div'); card.className = 'comparison-card';
    const obj = (typeof r === 'object' && r) ? r : { text: String(r) };
    Object.entries(obj).forEach(([k, v]) => {
      const row = document.createElement('div'); row.className = 'cmp-row';
      const kk = document.createElement('span'); kk.className = 'cmp-key'; kk.textContent = k;
      const vv = document.createElement('span'); vv.className = 'cmp-val'; vv.textContent = (v == null ? '' : String(v));
      row.append(kk, vv); card.append(row);
    });
    wrap.append(card);
  });
  c.append(wrap);
}
function renderApprovalSpecInto(c, s) {
  const ap = document.createElement('div'); ap.className = 'approval-card';
  const t = document.createElement('b'); t.textContent = s.title || 'Требуется подтверждение';
  ap.append(t);
  if (s.text) { const p = document.createElement('p'); p.textContent = s.text; ap.append(p); }
  c.append(ap);
}
function renderMissionSpecInto(c, s) {
  const e = s || {};
  renderMissionUpdate({ mission_id: e.mission_id, title: e.title, subtitle: e.subtitle,
    percent: e.percent, stage: e.stage, steps: e.steps, current_action: e.current_action,
    recent: e.recent, metrics: e.metrics, requires_confirmation: e.requires_confirmation });
}
function renderActionButtons(c, actions, taskId) {
  const bar = document.createElement('div'); bar.className = 'result-actions';
  (actions || []).forEach((a) => {
    const btn = document.createElement('button');
    btn.className = 'result-action'; btn.textContent = a.label || a.id;
    btn.onclick = () => fetch(`${API}/api/ui/action`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: a.id, task_id: taskId || null }) }).catch(() => {});
    bar.append(btn);
  });
  c.append(bar);
}

// ---------- режимы ----------
function setMode(mode) {
  state.mode = mode;
  widget.classList.toggle('mode-quick', mode === 'quick');
  widget.classList.toggle('mode-mission', mode === 'mission');
  $('#quickMode').classList.toggle('hidden', mode !== 'quick');
  $('#missionMode').classList.toggle('hidden', mode !== 'mission');
  $$('.demo-switcher button').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  $('#headerStatus').textContent = state.stopped ? 'Остановлена' : (mode === 'quick' ? 'Выполняю' : 'Работаю');
  setAvatar('working');
  window.dispatchEvent(new CustomEvent('uni:mode-change', { detail: { mode } }));
}

// ---------- чат (P0) ----------
function addBubble(text, who) {
  const el = document.createElement('div');
  el.className = 'message' + (who === 'user' ? ' user' : '');
  el.textContent = text;            // только текст — сырой JSON в UI запрещён
  const panel = state.mode === 'mission' ? $('#missionMode') : $('#quickMode');
  panel.insertBefore(el, panel.querySelector(':scope > .action-strip, :scope > .mission-card, :scope > .result-card') || null);
  panel.scrollTop = panel.scrollHeight;
}

// поллинг ui_events по task_id (Директива §3 — для долгих задач)
function pollTask(taskId) {
  if (!taskId) return;
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    try {
      const r = await fetch(`${API}/api/task/${encodeURIComponent(taskId)}/status`, { method: 'GET' });
      if (!r.ok) return;
      const d = await r.json();
      (d.events || []).forEach(applyUiEvent);
      if (d.finished) { clearInterval(state.pollTimer); state.pollTimer = null; }
    } catch (e) { /* тихо */ }
  }, 1500);
}

async function send() {
  const input = $('#messageInput');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addBubble(text, 'user');
  hideEmptyChat();
  setStatus('Обрабатываю', 'working');
  try {
    const r = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        // фронт заявляет поддерживаемые компоненты — НЕ классифицирует сам (Директива §3/§4)
        client_capabilities: [
          'progress_task', 'result_text', 'result_gallery', 'result_list',
          'comparison_table', 'approval_required', 'mission_card'
        ],
      }),
    });
    if (!r.ok) { addBubble('Не удалось получить ответ (ошибка сервера).', 'uni'); setAction('error', 'Ошибка выполнения'); setStatus('Ошибка', 'waiting'); return; }
    const data = await r.json();
    const reply = (data && (data.reply || data.text || data.message || data.response)) || '';
    if (reply) addBubble(reply, 'uni');
    // универсальный контракт: backend присылает ui_events (или task_id для поллинга)
    if (Array.isArray(data.ui_events)) data.ui_events.forEach(applyUiEvent);
    else if (data.ui_event) applyUiEvent(data.ui_event);
    else if (data.task_id) pollTask(data.task_id);
    else renderGenericMessage(reply || data.text || '');
    if (data && data.audio_url) { try { new Audio(`${API}${data.audio_url}`).play(); } catch (e) {} }
    if (!data || (!data.ui_events && !data.task_id)) setStatus('Готово', 'done');
  } catch (e) {
    addBubble('Нет связи с Юни. Запущен ли сервер на :8787?', 'uni');
    setAction('error', 'Нет связи с сервером');
    setStatus('Ошибка', 'waiting');
  }
}
function renderGenericMessage(text) {
  if (!text) return;
  const card = makeCard();
  const p = document.createElement('p'); p.textContent = text; card.append(p);
  setAction('done', 'Готово'); showReadyBubble('Юни готова'); setStatus('Готово', 'done');
}

// ---------- статус (P0): поллинг /api/uni/status ----------
const STATUS_MAP = {
  ok:   { text: 'На связи',   dot: 'ok',   avatar: 'working' },
  busy: { text: 'Работаю',    dot: 'busy', avatar: 'working' },
  err:  { text: 'Ошибка',     dot: 'err',  avatar: 'waiting' },
};
async function pollStatus() {
  try {
    const r = await fetch(`${API}/api/uni/status`, { method: 'GET' });
    if (!r.ok) throw new Error('status ' + r.status);
    const s = await r.json();
    $('#connectionDot')?.classList.add('online');
    $('#connectionDot')?.classList.remove('offline');
    const healthy = s.llama && s.llama.running && s.webui && s.webui.running;
    const key = !healthy ? 'err' : (state.stopped ? 'busy' : 'ok');
    const m = STATUS_MAP[key];
    if (!state.busy && state.avatar !== 'done' && state.avatar !== 'waiting') $('#headerStatus').textContent = state.stopped ? 'Остановлена' : m.text;
    const dot = $('.live-status i');
    if (dot) { dot.style.background = key === 'err' ? 'var(--stop)' : (key === 'ok' ? 'var(--accent)' : 'var(--amber)'); }
    if (!state.stopped && !state.listening && state.avatar !== 'done' && state.avatar !== 'waiting') setAvatar(m.avatar);
    const sp = $('#statusPopover');
    if (sp) {
      sp.innerHTML = `<b>Состояние Юни</b>` +
        `<span><i class="${healthy ? 'ok' : ''}" style="background:${healthy ? 'var(--accent)' : 'var(--stop)'}"></i> ` +
        `${s.llama && s.llama.running ? 'LLM на связи' : 'LLM недоступен'}</span>` +
        `<span><i class="${s.webui && s.webui.running ? 'ok' : ''}" style="background:${s.webui && s.webui.running ? 'var(--accent)' : 'var(--stop)'}"></i> ` +
        `${s.webui && s.webui.running ? 'WebUI на связи' : 'WebUI недоступен'}</span>`;
    }
  } catch (e) {
    $('#headerStatus').textContent = 'Ошибка';
    const dot = $('.live-status i'); if (dot) dot.style.background = 'var(--stop)';
    $('#connectionDot')?.classList.remove('online');
    $('#connectionDot')?.classList.add('offline');
  }
}
setInterval(pollStatus, 3000); pollStatus();
initEmptyChat();

// ---------- STOP (P0): лёгкая остановка цикла ----------
$('#stopButton').onclick = async () => {
  state.stopped = true;
  $('#stopButton').textContent = 'STOP';
  try { await fetch(`${API}/api/stop-cycle`, { method: 'POST' }); } catch (e) {}
  try { await fetch(`${API}/api/admin/stop`, { method: 'POST' }); } catch (e) {}
  setAction('error', 'Остановлено пользователем');
  setStatus('Остановлена', 'waiting');
  notify('Задача остановлена');
  window.dispatchEvent(new CustomEvent('uni:stop', { detail: { stopped: state.stopped } }));
};

// ---------- наблюдение 👁 (P0): /api/desktop/consent ----------
$('#visionButton').onclick = async () => {
  state.observing = !state.observing;
  $('#visionButton').classList.toggle('active', state.observing);
  const level = state.observing ? 'observe' : 'off';
  try {
    await fetch(`${API}/api/desktop/consent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ observation_enabled: state.observing, level }),
    });
  } catch (e) {}
  notify(state.observing ? 'Наблюдение включено' : 'Наблюдение выключено');
  persist();
};

// ---------- микрофон PTT (P0): /api/stt — try/finally для треков (Директива §5.5) ----------
let mediaRecorder = null, micChunks = [];
async function toggleListening() {
  state.listening = !state.listening;
  $('#micButton').classList.toggle('active', state.listening);
  $('#composerMic').classList.toggle('active', state.listening);
  setStatus(state.listening ? 'Слушаю' : (state.mode === 'quick' ? 'Выполняю' : 'Работаю'),
            state.listening ? 'listening' : 'working');
  let stream = null;
  try {
    if (state.listening) {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      micChunks = [];
      mediaRecorder.ondataavailable = (e) => micChunks.push(e.data);
      mediaRecorder.onstop = async () => {
        const blob = new Blob(micChunks, { type: 'audio/webm' });
        const buf = await blob.arrayBuffer();
        try {
          const r = await fetch(`${API}/api/stt`, { method: 'POST',
            headers: { 'Content-Type': 'audio/webm' }, body: buf });
          const d = await r.json();
          if (d && d.text) { $('#messageInput').value = d.text; notify('Распознано: ' + d.text); }
          else if (r.status === 501) notify('STT недоступен (Whisper не установлен)');
        } catch (e) { notify('STT недоступен'); }
      };
      mediaRecorder.start();
    } else if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
  } catch (e) {
    notify('Нет доступа к микрофону');
    state.listening = false;
    $('#micButton').classList.remove('active'); $('#composerMic').classList.remove('active');
  } finally {
    // 🤖 §5.5: трек микрофона ЗАКРЫВАЕТСЯ всегда, даже при обрыве getUserMedia
    if (stream) stream.getTracks().forEach(t => t.stop());
  }
}
$('#micButton').onclick = toggleListening;
$('#composerMic').onclick = toggleListening;

// ---------- свернуть ----------
$('#minimizeButton').onclick = () => {
  state.minimized = !state.minimized;
  widget.classList.toggle('minimized', state.minimized);
  $('#minimizeButton').textContent = state.minimized ? '□' : '−';
  setAvatar(state.minimized ? 'idle' : 'working');
};

// ---------- поповеры ----------
function togglePopover(selector, button) {
  const p = $(selector); p.classList.toggle('hidden');
  button && button.setAttribute('aria-expanded', String(!p.classList.contains('hidden')));
}
$('#statusButton').onclick = () => togglePopover('#statusPopover', $('#statusButton'));
$('#settingsButton').onclick = () => togglePopover('#settingsPopover');

// ---------- настройки (P0): persist в state.json через preload ----------
function persist() {
  if (window.uni && window.uni.saveState) {
    window.uni.saveState({
      theme: document.documentElement.dataset.theme,
      opacity: getComputedStyle(document.documentElement).getPropertyValue('--opacity').trim(),
      motion: !document.body.classList.contains('no-motion'),
      observing: state.observing, avatar: 'png-live', interface: 'v4',
    });
  }
}
$('#themeButton').onclick = () => {
  const light = document.documentElement.dataset.theme !== 'light';
  document.documentElement.dataset.theme = light ? 'light' : 'dark';
  $('#themeButton').textContent = light ? '☀ Светлая' : '☾ Тёмная';
  document.documentElement.style.setProperty('--shell', light ? '235,240,238' : '11,17,21');
  document.documentElement.style.setProperty('--text', light ? '#18201c' : '#f2f4ef');
  document.documentElement.style.setProperty('--muted', light ? '#68736e' : '#8d989a');
  notify('Тема переключена'); persist();
};
$('#opacityInput').oninput = (e) => {
  document.documentElement.style.setProperty('--opacity', e.target.value / 100); persist();
};
$('#motionInput').onchange = (e) => { document.body.classList.toggle('no-motion', !e.target.checked); persist(); };
$('#notifyButton').onclick = () => { setAvatar('waiting'); notify('Юни сообщит, когда понадобится решение'); };
$('#attachButton').onclick = () => notify('Прикрепление файлов появится после выбора безопасного хранилища');
$$('[data-collapse]').forEach((button) => button.onclick = () => {
  const target = document.getElementById(button.dataset.collapse);
  target.classList.toggle('hidden');
  button.textContent = target.classList.contains('hidden') ? '⌄' : '⌃';
});

// ---------- пустой чат / готовность (ФИНАЛ §3) ----------
function greetingByTime() {
  const h = new Date().getHours();
  if (h < 6) return 'Доброй ночи';
  if (h < 12) return 'Доброе утро';
  if (h < 18) return 'Добрый день';
  return 'Добрый вечер';
}
function hideEmptyChat() { $('#emptyChat')?.classList.add('hidden'); }
function showReadyBubble(text) {
  const strip = state.mode === 'mission' ? $('#missionActionStrip') : $('#quickActionStrip');
  if (strip) strip.style.display = 'none';
  let b = $('#readyBubble');
  if (!b) {
    b = document.createElement('div'); b.id = 'readyBubble'; b.className = 'ready-bubble';
    (state.mode === 'mission' ? $('#missionMode') : $('#quickMode')).append(b);
  }
  b.textContent = text || 'Юни готова';
  b.style.display = '';
}
function hideReadyBubble() {
  const b = $('#readyBubble'); if (b) b.style.display = 'none';
  const strip = state.mode === 'mission' ? $('#missionActionStrip') : $('#quickActionStrip');
  if (strip) strip.style.display = '';
}
function initEmptyChat() {
  const g = $('#greetingText'); if (g) g.textContent = greetingByTime();
  const ec = $('#emptyChat'); if (ec) ec.classList.remove('hidden');
  $$('.chip').forEach((chip) => {
    chip.onclick = () => {
      const q = chip.dataset.q || chip.textContent;
      $('#messageInput').value = q;
      send();
    };
  });
}

// ---------- отправка ----------
$('#sendButton').onclick = send;
$('#messageInput').onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };

// ---------- мост для backend/Electron (UNIInterface) -----------
window.UNIInterface = {
  setMode, setStatus, setAvatar,
  setQuickTask: (d = {}) => {
    if (d.action) $('#quickAction').textContent = d.action;
    if (d.progress != null) $('#quickProgress').style.width = `${d.progress}%`;
    setStatus(d.status || 'Выполняю', d.avatar || 'working');
  },
  setMission: (d = {}) => {
    if (d.action) $('#missionAction').textContent = d.action;
    if (d.percent != null) $('#missionPercent').textContent = `${d.percent}%`;
    setStatus(d.status || 'Работаю', d.avatar || 'working');
  },
  notify, getState: () => ({ ...state }),
};
