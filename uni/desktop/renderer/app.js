// Юни — интерфейс v4: реальная логика (Hermes 2026-08-13, директива «НОВЫЙ ИНТЕРФЕЙС»).
// Заменяет демо-заглушки на боевые вызовы backend (http://127.0.0.1:8787).
// Старый вариант (canon-design/) не трогаем.
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const widget = $('#uniWidget');
const avatar = $('#avatar');
const toast = $('#toast');

// Базовый URL backend (WebUI на 8787). Electron loadFile → file://, нужен абсолютный URL.
const API = 'http://127.0.0.1:8787';

const state = {
  mode: 'quick', stopped: false, observing: true, listening: false,
  minimized: false, avatar: 'working', consentLevel: 'off',
};

// ---------- утилиты ----------
function notify(text) {
  toast.textContent = text; toast.classList.add('show');
  clearTimeout(notify.t);
  notify.t = setTimeout(() => toast.classList.remove('show'), 1800);
}
function setAvatar(next) {
  state.avatar = next;
  avatar.className = `avatar avatar--${next}`;
  avatar.setAttribute('aria-label', `Состояние Юни: ${next}`);
}
function setStatus(text, avatarState = 'working') {
  $('#headerStatus').textContent = text;
  if (avatarState) setAvatar(avatarState);
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
  panel.insertBefore(el, panel.querySelector('.action-strip, .mission-card, .result-card') || null);
  panel.scrollTop = panel.scrollHeight;
}
async function send() {
  const input = $('#messageInput');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addBubble(text, 'user');
  setStatus('Обрабатываю', 'working');
  try {
    const r = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) { addBubble('Не удалось получить ответ (ошибка сервера).', 'uni'); return; }
    const data = await r.json();
    const reply = (data && (data.text || data.message)) || '';
    if (reply) addBubble(reply, 'uni');
    if (data && data.audio_url) {
      try { new Audio(`${API}${data.audio_url}`).play(); } catch (e) {}
    }
    setStatus(state.mode === 'quick' ? 'Выполняю' : 'Работаю', 'done');
  } catch (e) {
    addBubble('Нет связи с Юни. Запущен ли сервер на :8787?', 'uni');
    setStatus('Ошибка', 'waiting');
  }
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
    // «Ошибка», если упал любой критичный компонент
    const healthy = s.llama && s.llama.running && s.webui && s.webui.running;
    const key = !healthy ? 'err' : (state.stopped ? 'busy' : 'ok');
    const m = STATUS_MAP[key];
    $('#headerStatus').textContent = state.stopped ? 'Остановлена' : m.text;
    const dot = $('.live-status i');
    if (dot) { dot.style.background = key === 'err' ? 'var(--stop)' : (key === 'ok' ? 'var(--accent)' : 'var(--amber)'); }
    if (!state.stopped && !state.listening) setAvatar(m.avatar);
    // поповер состояния
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
  }
}
setInterval(pollStatus, 3000); pollStatus();

// ---------- STOP (P0): лёгкая остановка цикла ----------
$('#stopButton').onclick = async () => {
  state.stopped = !state.stopped;
  $('#stopButton').textContent = state.stopped ? 'ПУСК' : 'STOP';
  if (state.stopped) {
    try { await fetch(`${API}/api/stop-cycle`, { method: 'POST' }); } catch (e) {}
    setStatus('Остановлена', 'waiting');
    notify('Задача остановлена');
  } else {
    // снять STOP.txt, возобновить
    try { await fetch(`${API}/api/admin/stop`, { method: 'POST' }); } catch (e) {}
    setStatus(state.mode === 'quick' ? 'Выполняю' : 'Работаю', 'working');
    notify('Задача продолжена');
  }
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

// ---------- микрофон PTT (P0): /api/stt ----------
let mediaRecorder = null, micChunks = [];
async function toggleListening() {
  state.listening = !state.listening;
  $('#micButton').classList.toggle('active', state.listening);
  $('#composerMic').classList.toggle('active', state.listening);
  setStatus(state.listening ? 'Слушаю' : (state.mode === 'quick' ? 'Выполняю' : 'Работаю'),
            state.listening ? 'listening' : 'working');
  if (state.listening) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
        stream.getTracks().forEach(t => t.stop());
      };
      mediaRecorder.start();
    } catch (e) { notify('Нет доступа к микрофону'); state.listening = false;
      $('#micButton').classList.remove('active'); $('#composerMic').classList.remove('active'); }
  } else if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
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

// ---------- отправка ----------
$('#sendButton').onclick = send;
$('#messageInput').onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };

// ---------- мост для backend/Electron (UNIInterface) ------------
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
