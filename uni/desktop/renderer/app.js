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

// Only actual UI surfaces capture the mouse. Empty overlay space passes clicks
// to the browser/desktop behind the transparent Electron window.
function updateHitTest(event) {
  const target = event?.target;
  const interactive = Boolean(target?.closest?.(
    '.widget-header, button, textarea, input, select, details, .message, .ui-card, .task-card, .result-card, .mission-card, .approval-card, .chip'
  ));
  window.uni?.hitTest?.(interactive);
}
document.addEventListener('mousemove', updateHitTest, { passive: true });
document.addEventListener('mouseenter', updateHitTest, { passive: true });
document.addEventListener('mouseleave', () => window.uni?.hitTest?.(false), { passive: true });
window.uni?.hitTest?.(false);

// Базовый URL backend (WebUI на 8787). Electron loadFile → file://, нужен абсолютный URL.
const API = 'http://127.0.0.1:8787';

// Native drag-region is retained, with an explicit fallback for transparent
// frameless windows where Chromium may not start a drag reliably.
const dragHeader = document.querySelector('.widget-header');
let dragStart = null;
dragHeader?.addEventListener('pointerdown', async (e) => {
  if (e.button !== 0 || e.target.closest('button')) return;
  const b = await window.uni?.getBounds?.();
  if (!b) return;
  dragStart = { x: e.screenX, y: e.screenY, wx: b.x, wy: b.y };
  dragHeader.setPointerCapture?.(e.pointerId);
});
dragHeader?.addEventListener('pointermove', (e) => {
  if (!dragStart || !e.buttons) return;
  window.uni?.moveWindow?.(dragStart.wx + e.screenX - dragStart.x, dragStart.wy + e.screenY - dragStart.y);
});
dragHeader?.addEventListener('pointerup', () => { dragStart = null; });

const state = {
  mode: 'quick', stopped: false, observing: true, listening: false,
  mouseOnly: false,
  minimized: false, avatar: 'working', consentLevel: 'off', busy: false,
  pollTimer: null,
  startingLlm: false,
};

// ---------- утилиты ----------
function notify(text) {
  toast.textContent = text; toast.classList.add('show');
  clearTimeout(notify.t);
  notify.t = setTimeout(() => toast.classList.remove('show'), 1800);
}
// 🤖 U-04/U-08 (2026-08-13): клиентская очистка src/url — только локальные
// пути (/api, /runtime, /assets), блокируем внешние/опасные схемы.
function _cleanSrcClient(v) {
  if (typeof v !== 'string') return '';
  const s = v.trim();
  if (!s) return '';
  if (/^[a-z][a-z0-9+.\-]*:/i.test(s)) {
    if (!s.startsWith('/')) return '';  // http(s)://, javascript:, data: -> блок
  }
  if (s.startsWith('/api/') || s.startsWith('/runtime/') || s.startsWith('/assets/') ||
      s.startsWith('runtime/') || s.startsWith('assets/')) return s;
  return '';
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
    case 'task.done':     return renderTaskDone(event);
    case 'task.error':    return renderTaskError(event);
    case 'mission.started':
    case 'mission.update':return renderMissionUpdate(event);
    case 'mission.done':  return renderMissionDone(event);
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
  titleEl.append(document.createTextNode(e.title || 'Результат'));
  card.append(titleEl);
  renderComponentInto(card, ui);
  setStatus('Готово', 'done');
  // авто-сворачивание карточки в одну строку через ~1.2с (C-06 / Директива §5.3)
  if (e.task_id) {
    setTimeout(() => {
      const c = $(`[data-task-id="${CSS.escape(e.task_id)}"]`);
      c?.classList.add('collapsed');
    }, 1200);
  }
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
  // 🤖 U-01 (2026-08-13): НИКАКОГО insertAdjacentHTML — только createElement +
  // textContent. Модель НЕ контролирует разметку (U-08).
  const titleRow = document.createElement('div'); titleRow.className = 'ui-card-title';
  const titleMain = document.createElement('div');
  const titleB = document.createElement('b'); titleB.textContent = e.title || 'Миссия';
  const titleSub = document.createElement('span'); titleSub.className = 'mission-sub'; titleSub.textContent = e.subtitle || '';
  titleMain.append(titleB, titleSub);
  const titlePct = document.createElement('span'); titlePct.className = 'mission-percent'; titlePct.textContent = `${percent}%`;
  titleRow.append(titleMain, titlePct);
  card.append(titleRow);

  const layout = document.createElement('div'); layout.className = 'mission-layout';
  const stepsEl = document.createElement('div'); stepsEl.className = 'steps mission-steps';
  renderSteps(stepsEl, e.steps || []);
  const now = document.createElement('div'); now.className = 'mission-now';
  const actionStrip = document.createElement('div'); actionStrip.className = 'action-strip';
  const actionSpan = document.createElement('span'); actionSpan.className = 'mission-action'; actionSpan.textContent = e.current_action || '';
  actionStrip.append(actionSpan);
  const details = document.createElement('details'); details.open = true;
  const summary = document.createElement('summary'); summary.textContent = 'Последние действия';
  const recent = document.createElement('div'); recent.className = 'mission-recent';
  (Array.isArray(e.recent) ? e.recent : []).forEach((r) => {
    const p = document.createElement('p'); p.textContent = '• ' + r; recent.append(p);
  });
  details.append(summary, recent);
  now.append(actionStrip, details);
  layout.append(stepsEl, now);
  card.append(layout);

  const progRow = document.createElement('div'); progRow.className = 'progress-row mission-progress';
  const prog = document.createElement('div'); prog.className = 'progress';
  const progI = document.createElement('i'); progI.style.width = `${percent}%`;
  prog.append(progI);
  const stage = document.createElement('span'); stage.className = 'mission-stage'; stage.textContent = e.stage || '';
  progRow.append(prog, stage);
  card.append(progRow);

  const money = document.createElement('div'); money.className = 'money-row';
  const m1 = document.createElement('div'); const m1s = document.createElement('span'); m1s.textContent = 'Подтверждено';
  const m1b = document.createElement('b'); m1b.className = 'mission-confirmed'; m1b.textContent = `${confirmed} ₽`; m1.append(m1s, m1b);
  const m2 = document.createElement('div'); const m2s = document.createElement('span'); m2s.textContent = 'Ожидается';
  const m2b = document.createElement('b'); m2b.className = 'mission-expected'; m2b.textContent = expected; m2.append(m2s, m2b);
  const m3 = document.createElement('div'); const m3s = document.createElement('span'); m3s.textContent = 'Затраты';
  const m3b = document.createElement('b'); m3b.className = 'mission-costs'; m3b.textContent = `${spent} ₽`; m3.append(m3s, m3b);
  money.append(m1, m2, m3);
  card.append(money);

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
    case 'form':        return renderFormInto(container, s);
    case 'link_list':   return renderLinkListInto(container, s);
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
// 🤖 U-03 (2026-08-13): form — интерактивная форма (поля + submit).
function renderFormInto(c, s) {
  const form = s.form || {};
  const wrap = document.createElement('div'); wrap.className = 'ui-form';
  const fields = Array.isArray(form.fields) ? form.fields : [];
  const inputs = [];
  fields.forEach((f) => {
    const name = f.name || '';
    const label = document.createElement('label'); label.className = 'form-field';
    const span = document.createElement('span'); span.textContent = f.label || name;
    const input = document.createElement('input');
    input.type = (f.type === 'textarea') ? 'text' : (f.type || 'text');
    input.name = name; input.placeholder = f.placeholder || '';
    input.dataset.field = name;
    label.append(span, input); wrap.append(label); inputs.push(input);
  });
  const btn = document.createElement('button'); btn.className = 'result-action';
  btn.textContent = form.submit_label || 'Отправить';
  btn.onclick = () => {
    const payload = {};
    inputs.forEach((i) => { payload[i.dataset.field] = i.value; });
    // 🤖 U-05: submit_form -> form.submit в карте действий
    fetch(`${API}/api/ui/action`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: 'submit_form', task_id: s.task_id || null,
        fields: payload }) }).catch(() => {});
    btn.disabled = true; notify('Форма отправлена');
  };
  wrap.append(btn); c.append(wrap);
}
// 🤖 U-03 (2026-08-13): link_list — список ссылок (link_open в карте действий).
function renderLinkListInto(c, s) {
  const items = Array.isArray(s.items) ? s.items : [];
  if (!items.length) { const p = document.createElement('p'); p.textContent = 'Нет ссылок'; c.append(p); return; }
  const list = document.createElement('div'); list.className = 'result-list';
  items.forEach((it) => {
    const row = document.createElement('div'); row.className = 'result-item link-item';
    const b = document.createElement('b'); b.textContent = it.title || it.text || 'Ссылка';
    const d = document.createElement('small'); d.textContent = it.description || '';
    row.append(b, d);
    const url = (it.url && _cleanSrcClient(it.url)) || '';
    if (url) {
      row.style.cursor = 'pointer';
      row.onclick = () => fetch(`${API}/api/ui/action`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action_id: 'link_open', task_id: s.task_id || null,
          url }) }).catch(() => {});
    }
    list.append(row);
  });
  c.append(list);
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
function addBubble(text, who, technical = false) {
  const el = document.createElement('div');
  el.className = 'message' + (who === 'user' ? ' user' : '') + (technical ? ' technical' : '');
  el.textContent = text;            // только текст — сырой JSON в UI запрещён
  const thread = $('#chatThread');
  if (thread) {
    thread.appendChild(el);
    thread.scrollTop = thread.scrollHeight;
  } else {
    // fallback для mission mode или если thread не найден
    const panel = state.mode === 'mission' ? $('#missionMode') : $('#quickMode');
    panel.insertBefore(el, panel.querySelector(':scope > .action-strip, :scope > .mission-card, :scope > .result-card') || null);
    panel.scrollTop = panel.scrollHeight;
  }
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
  autoGrowInput();
  addBubble(text, 'user');
  hideEmptyChat();
  setStatus('Обрабатываю', 'working');
  try {
    if (state.mouseOnly) {
      const r = await fetch(`${API}/api/computer/act`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: text, max_steps: 12, mouse_only: true }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || data.ok === false) throw new Error(data.error || `HTTP ${r.status}`);
      setStatus('Выполняю мышью', 'working');
      pollComputerTask();
      return;
    }
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
    // When the backend supplies structured UI events, the reply is represented
    // by the rendered card. Adding it as a second bubble caused duplicated chat.
    const hasUi = Array.isArray(data.ui_events) || data.ui_event || data.task_id;
    if (reply && !hasUi) renderGenericMessage(reply);
    // универсальный контракт: backend присылает ui_events (или task_id для поллинга)
    if (Array.isArray(data.ui_events)) data.ui_events.forEach(applyUiEvent);
    else if (data.ui_event) applyUiEvent(data.ui_event);
    else if (data.task_id) pollTask(data.task_id);
    else if (!reply) renderGenericMessage(data.text || '');
    if (data && data.audio_url) { try { new Audio(`${API}${data.audio_url}`).play(); } catch (e) {} }
    if (!data || (!data.ui_events && !data.task_id)) setStatus('Готово', 'done');
  } catch (e) {
    addBubble('Нет связи с Юни. Запущен ли сервер на :8787?', 'uni');
    setAction('error', 'Нет связи с сервером');
    setStatus('Ошибка', 'waiting');
  }
}

async function pollComputerTask() {
  let shown = 0;
  for (let i = 0; i < 80; i++) {
    await new Promise(resolve => setTimeout(resolve, 1000));
    try {
      const r = await fetch(`${API}/api/computer/status`, { cache: 'no-store' });
      const d = await r.json();
      const history = Array.isArray(d.history) ? d.history : [];
      for (; shown < history.length; shown++) addBubble(history[shown], 'uni');
      if (!d.active) {
        const status = d.status || (d.stopped ? 'interrupted' : 'готово');
        if (d.message && status !== 'success' && status !== 'готово') addBubble(d.message, 'uni');
        setStatus(status === 'success' ? 'Готово' : status === 'interrupted' ? 'Остановлено' : 'Ошибка', status === 'success' ? 'done' : 'waiting');
        return;
      }
      setStatus(`Выполняю мышью · шаг ${d.steps || shown + 1}`, 'working');
    } catch (_) {}
  }
  setStatus('Ожидаю результат', 'working');
}

function autoGrowInput() {
  const input = $('#messageInput');
  if (!input) return;
  input.style.height = 'auto';
  const max = Math.min(150, Math.max(42, input.scrollHeight));
  input.style.height = `${max}px`;
  input.style.overflowY = input.scrollHeight > max ? 'auto' : 'hidden';
  const footer = document.querySelector('.composer');
  const base = state.mode === 'mission' ? 368 : 500;
  const extra = Math.max(0, max - 42);
  if (footer) footer.style.height = `${58 + extra}px`;
  if (widget) widget.style.height = `${base + extra}px`;
}
$('#messageInput').addEventListener('input', autoGrowInput);
function renderGenericMessage(text) {
  if (!text) return;
  addBubble(text, 'uni');
  setStatus('Готово', 'done');
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
    const lmReady = s.lmstudio && s.lmstudio.reachable && s.lmstudio.model_loaded;
    const llmReady = s.llama && s.llama.running;
    const healthy = (llmReady || lmReady) && s.webui && s.webui.running;
    const key = !healthy ? 'err' : (state.stopped ? 'busy' : 'ok');
    const m = STATUS_MAP[key];
    if (!healthy) hideReadyBubble();
    if (!state.busy && state.avatar !== 'done' && state.avatar !== 'waiting') $('#headerStatus').textContent = state.stopped ? 'Остановлена' : m.text;
    const dot = $('.live-status i');
    if (dot) { dot.style.background = key === 'err' ? 'var(--stop)' : (key === 'ok' ? 'var(--accent)' : 'var(--amber)'); }
    if (!state.stopped && !state.listening && state.avatar !== 'done' && state.avatar !== 'waiting') setAvatar(m.avatar);
    const sp = $('#statusPopover');
    if (sp) {
      sp.innerHTML = `<b>Состояние Юни</b>` +
        `<span><i class="${healthy ? 'ok' : ''}" style="background:${healthy ? 'var(--accent)' : 'var(--stop)'}"></i> ` +
        `${llmReady || lmReady ? (lmReady ? 'LM Studio на связи' : 'LLM на связи') : 'LLM недоступен'}</span>` +
        `<span><i class="${s.webui && s.webui.running ? 'ok' : ''}" style="background:${s.webui && s.webui.running ? 'var(--accent)' : 'var(--stop)'}"></i> ` +
        `${s.webui && s.webui.running ? 'WebUI на связи' : 'WebUI недоступен'}</span>`;
      if (!llmReady && !lmReady) {
        const btn = document.createElement('button');
        btn.className = 'status-start-llm';
        btn.textContent = state.startingLlm ? 'Запускаю LLM…' : '▶ Запустить LLM';
        btn.disabled = state.startingLlm;
        btn.onclick = startLlmFromOverlay;
        sp.append(btn);
      }
    }
  } catch (e) {
    $('#headerStatus').textContent = 'Ошибка';
    const dot = $('.live-status i'); if (dot) dot.style.background = 'var(--stop)';
    $('#connectionDot')?.classList.remove('online');
    $('#connectionDot')?.classList.add('offline');
  }
}
async function startLlmFromOverlay() {
  if (state.startingLlm) return;
  state.startingLlm = true;
  $('#headerStatus').textContent = 'Запускаю…';
  setStatus('Запускаю…', 'working');
  notify('Запускаю LLM-сервер…');
  try {
    const r = await fetch(`${API}/api/admin/restart-llm`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || d.ok === false) throw new Error(d.error || `HTTP ${r.status}`);
    const deadline = Date.now() + 30000;
    let ready = false;
    while (Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 1200));
      try {
        const sr = await fetch(`${API}/api/uni/status`, { cache: 'no-store' });
        const s = await sr.json();
        if (s.llama?.running) { ready = true; break; }
      } catch (_) {}
    }
    if (!ready) throw new Error('LLM не вышел на связь за 30 секунд');
    notify('LLM запущен и отвечает');
    $('#headerStatus').textContent = 'Готово';
    await pollStatus();
  } catch (e) {
    $('#headerStatus').textContent = 'Ошибка';
    notify(`LLM не запущен: ${e.message}`);
    await pollStatus();
  } finally {
    state.startingLlm = false;
  }
}
async function startWebuiFromOverlay() {
  notify('Запускаю WebUI на 8787…');
  try {
    const r = await fetch(`${API}/api/admin/start-webui`, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    const d = await r.json().catch(()=>({}));
    if (!r.ok || d.ok === false) throw new Error(d.error || `HTTP ${r.status}`);
    notify('WebUI запущен');
    await pollStatus();
  } catch (e) { notify(`WebUI не запущен: ${e.message}`); }
}
async function restoreAppearance() {
  try {
    const saved = await window.uni?.loadState?.();
    if (!saved) return;
    const theme = saved.theme === 'light' ? 'light' : 'dark';
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.setProperty('--opacity', String(Math.min(1, Math.max(.55, Number(saved.opacity) || .72))));
    document.documentElement.style.setProperty('--shell', theme === 'light' ? '235,240,238' : '11,17,21');
    document.documentElement.style.setProperty('--text', theme === 'light' ? '#18201c' : '#f2f4ef');
    document.documentElement.style.setProperty('--muted', theme === 'light' ? '#68736e' : '#8d989a');
    if ($('#opacityInput')) $('#opacityInput').value = Math.round(Number(saved.opacity || .72) * 100);
    if ($('#motionInput')) $('#motionInput').checked = saved.motion !== false;
    if (saved.transparent_overlay) {
      document.body.classList.add('transparent-overlay');
      $('#overlayButton')?.classList.add('active');
    }
    if ($('#themeButton')) $('#themeButton').textContent = theme === 'light' ? '☀ Светлая' : '☾ Тёмная';
  } catch (e) { window.uni?.log?.('restore appearance failed', e.message); }
}
restoreAppearance();
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

// ---------- режим мыши 🖱️ (Hermes, 2026-08-14): /api/set_mouse_mode ----------
// Включает визуально-управляемую мышь Юни (поиск иконок через внешний
// Moondream-endpoint + подсветка перед кликом). Аддитивно к 👁, не дублирует.
$('#uniMouseButton')?.addEventListener('click', async () => {
  state.mouseMode = !state.mouseMode;
  $('#uniMouseButton').classList.toggle('active', state.mouseMode);
  try {
    await fetch(`${API}/api/set_mouse_mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: state.mouseMode }),
    });
  } catch (e) {}
  notify(state.mouseMode ? 'Режим мыши Юни включён' : 'Режим мыши Юни выключен');
  persist();
});

// ---------- зрение 👁: периодический тик наблюдения (восстановлено) ----------
// Пока state.observing === true, раз в ~18с спрашиваем backend, не увидел ли
// он на рабочем столе что-то, требующее внимания (/api/vision/observe —
// агент сам снимает экран, бюджет инициатив внутри uni/desktop/observe.py).
let observeTimer = null;
async function visionObserveTick() {
  if (!state.observing) return;
  try {
    const r = await fetch(`${API}/api/vision/observe`, { method: 'POST' });
    const d = await r.json().catch(() => ({}));
    const initiative = d && d.initiative;
    if (initiative && initiative.initiative && initiative.text) {
      addBubble(initiative.text, 'uni');
      notify(initiative.text);
    }
  } catch (e) { /* тихо: наблюдение не должно шуметь ошибками */ }
}
function startObserveLoop() {
  clearInterval(observeTimer);
  observeTimer = setInterval(visionObserveTick, 18000);
}
startObserveLoop();

// SSE-события от backend (main.js прокидывает через desktop-event), включая
// инициативы от /api/vision/observe и смену согласия из трея.
window.uni?.onEvent?.((raw) => {
  let data = null;
  try { data = JSON.parse(raw); } catch (e) { return; }
  if (!data || !data.type) return;
  if (data.type === 'initiative' && data.text) {
    addBubble(data.text, 'uni');
    notify(data.text);
  } else if (data.type === 'assistant_message' && data.text) {
    addBubble(data.text, 'uni', data.source === 'dorch');
  } else if (data.type === 'consent_changed' && data.consent) {
    state.observing = !!data.consent.observation_enabled;
    $('#visionButton')?.classList.toggle('active', state.observing);
  }
});
$('#cameraButton').onclick = () => {
  const button = $('#cameraButton');
  const active = !button.classList.contains('active');
  button.classList.toggle('active', active);
  button.querySelector('img').src = active
    ? '../assets/icons/computer-camera-svgrepo-com.svg'
    : '../assets/icons/computer-camera-off-svgrepo-com.svg';
  button.title = active ? 'Камера включена' : 'Камера выключена';
  notify(active ? 'Камера включена' : 'Камера выключена');
};
async function toggleMouseOnly() {
  state.mouseOnly = !state.mouseOnly;
  const button = $('#mouseModeButton');
  button?.classList.toggle('active', state.mouseOnly);
  button?.setAttribute('aria-pressed', String(state.mouseOnly));
  if (button) button.title = state.mouseOnly ? 'Физический режим мыши включён' : 'Физический режим мыши выключен';
  try {
    const r = await fetch(`${API}/api/desktop/control-mode`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode: state.mouseOnly ? 'mouse_only' : 'auto'})
    });
    if (!r.ok) throw new Error('backend отказал');
    notify(state.mouseOnly ? 'Физический режим: только экран, мышь и клавиатура' : 'Обычный режим Юни');
  } catch (e) {
    state.mouseOnly = !state.mouseOnly;
    button?.classList.toggle('active', state.mouseOnly);
    button?.setAttribute('aria-pressed', String(state.mouseOnly));
    notify('Не удалось изменить режим мыши');
  }
  persist();
}
$('#mouseModeButton').onclick = toggleMouseOnly;
$('#overlayButton').onclick = () => {
  const active = !document.body.classList.contains('transparent-overlay');
  document.body.classList.toggle('transparent-overlay', active);
  $('#overlayButton').classList.toggle('active', active);
  $('#overlayButton').title = active ? 'Обычный режим' : 'Прозрачный режим';
  $('#overlayButton').setAttribute('aria-label', $('#overlayButton').title);
  persist();
  notify(active ? 'Прозрачный режим включён' : 'Обычный режим включён');
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
          if (d && d.text) { $('#messageInput').value = d.text; autoGrowInput(); $('#messageInput').focus(); notify('Распознано: ' + d.text); }
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

// ---------- фоновое голосовое управление ----------
// Постоянно держим микрофон открытым, но отправляем на STT только фразу:
// речь начинается при превышении RMS-порога и заканчивается после 3.2 с тишины.
let autoVoiceStream = null, autoVoiceContext = null, autoVoiceAnalyser = null;
let autoVoiceRecorder = null, autoVoiceChunks = [], autoVoiceSpeaking = false;
let autoVoiceLastSpeech = 0, autoVoiceStarted = 0;
const AUTO_VOICE_SILENCE_MS = 3200;
const AUTO_VOICE_THRESHOLD = 0.018;

async function startAutoVoice() {
  if (autoVoiceStream || state.listening) return;
  try {
    autoVoiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    autoVoiceContext = new AudioContext();
    autoVoiceAnalyser = autoVoiceContext.createAnalyser();
    autoVoiceAnalyser.fftSize = 1024;
    autoVoiceContext.createMediaStreamSource(autoVoiceStream).connect(autoVoiceAnalyser);
    const data = new Uint8Array(autoVoiceAnalyser.fftSize);
    const tick = () => {
      if (!autoVoiceStream || state.listening) return;
      autoVoiceAnalyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const value of data) { const n = (value - 128) / 128; sum += n * n; }
      const rms = Math.sqrt(sum / data.length);
      const nowMs = Date.now();
      if (rms >= AUTO_VOICE_THRESHOLD) {
        autoVoiceLastSpeech = nowMs;
        if (!autoVoiceSpeaking) {
          autoVoiceSpeaking = true;
          autoVoiceStarted = nowMs;
          autoVoiceChunks = [];
          autoVoiceRecorder = new MediaRecorder(autoVoiceStream);
          autoVoiceRecorder.ondataavailable = e => { if (e.data.size) autoVoiceChunks.push(e.data); };
          autoVoiceRecorder.onstop = submitAutoVoice;
          autoVoiceRecorder.start();
          setStatus('Слушаю', 'listening');
        }
      } else if (autoVoiceSpeaking && nowMs - autoVoiceLastSpeech >= AUTO_VOICE_SILENCE_MS && nowMs - autoVoiceStarted > 350) {
        autoVoiceSpeaking = false;
        if (autoVoiceRecorder && autoVoiceRecorder.state !== 'inactive') autoVoiceRecorder.stop();
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    notify('Фоновое голосовое управление включено');
  } catch (e) {
    autoVoiceStream = null;
    notify('Микрофон не разрешён: включите его в настройках Windows');
  }
}
async function submitAutoVoice() {
  const blob = new Blob(autoVoiceChunks, { type: 'audio/webm' });
  if (blob.size < 1200) return;
  try {
    const r = await fetch(`${API}/api/stt`, { method: 'POST', headers: { 'Content-Type': 'audio/webm' }, body: await blob.arrayBuffer() });
    const d = await r.json();
    const text = String(d.text || '').trim();
    if (text) { $('#messageInput').value = text; autoGrowInput(); send(); }
  } catch (_) { notify('Не удалось расшифровать голосовую команду'); }
}
window.addEventListener('beforeunload', () => {
  autoVoiceStream?.getTracks().forEach(track => track.stop());
  autoVoiceContext?.close();
});
setTimeout(startAutoVoice, 1200);

// ---------- свернуть ----------
$('#minimizeButton').onclick = () => {
  state.minimized = !state.minimized;
  widget.classList.toggle('minimized', state.minimized);
  const button = $('#minimizeButton');
  const image = button.querySelector('img');
  button.title = state.minimized ? 'Развернуть окно' : 'Свернуть окно';
  button.setAttribute('aria-label', button.title);
  image.src = state.minimized ? '../assets/icons/fullscreen-2-svgrepo-com.svg' : '../assets/icons/fullscreen-exit-2-svgrepo-com.svg';
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
      transparent_overlay: document.body.classList.contains('transparent-overlay'),
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
// 🤖 M-04 (2026-08-13): кнопка «Демо мыши» в оверлее -> POST /api/demo/mouse.
// Бэкенд сам делает 3 клика в safe-зоне + рисует фигуру с лайм-кольцом «Юни».
$('#demoMouseButton').onclick = async () => {
  try {
    setAvatar('thinking');
    const resp = await fetch('/api/demo/mouse', { method: 'POST' });
    const data = await resp.json();
    if (data && data.ok) {
      notify('Демо мыши выполнено: 3 клика + фигура «Юни»');
      setAvatar('idle');
    } else {
      notify('Демо мыши недоступно: ' + (data && data.error ? data.error : 'нет дисплея'));
      setAvatar('idle');
    }
  } catch (err) {
    notify('Ошибка демо мыши: ' + err);
    setAvatar('idle');
  }
};
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
function hideReadyBubble() {
  const b = $('#readyBubble'); if (b) b.style.display = 'none';
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
