// UNI Desktop Companion — renderer/app.js (Hermes SOLO, 2026-08-11, блок D)
// D-05 чат->/api/chat · D-06 TTS->/api/tts · D-07 кнопки · D-09 SSE autonomous/stream
// D-10 PTT->/api/stt · D-11 настройки · D-03 click-through hit-test
const SERVER = (window.UNI_SERVER) || "http://127.0.0.1:8787";
const $ = (id) => document.getElementById(id);
// FIX-VISUAL-01 BUG#1: preload экспонирует глобальный window.uni через exposeInMainWorld('uni').
// Поэтому НЕ объявляем const uni (была ошибка 'Identifier uni has already been declared').
// Берём мост в локальную переменную U = window["uni"] и используем U везде.
const U = window["uni"] || null;
async function api(path, opts) {
  try {
    if (U && U.log) U.log("HTTP", opts && opts.method || "GET", SERVER + path);
    const r = await fetch(SERVER + path, opts);
    if (U && U.log) U.log("HTTP", path, "->", r.status);
    return r;
  } catch (e) {
    if (U && U.log) U.log("HTTP ERROR", path, e.message);
    addMsgSafe("⚠ сервер недоступен: " + e.message);
    return null;
  }
}
function addMsgSafe(t) { try { addMsg("uni", t); } catch {} }

function addMsg(role, text) {
  const m = document.createElement("div");
  m.className = "msg " + (role === "user" ? "user" : "U");
  m.textContent = text;
  $("messages").appendChild(m);
  $("messages").scrollTop = $("messages").scrollHeight;
}
async function UChat(text) {
  addMsg("user", text);
  if (window.Avatar) Avatar.setState("thinking");
  try {
    const r = await api("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    if (!r) { if (window.Avatar) Avatar.setState("idle"); return; }
    const d = await r.json();
    const reply = d.reply || d.response || d.message || JSON.stringify(d);
    addMsg("uni", reply);
    if (window.Avatar) Avatar.setState("speaking");
    try {
      // D-06: озвучка (опционально возвращает audio_url; играем локально)
      await api("/api/tts", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: reply }),
      });
    } catch (e) {}
  } catch (e) {
    addMsg("uni", "⚠ ошибка: " + e.message);
  } finally {
    if (window.Avatar) setTimeout(() => Avatar.setState("idle"), 1200);
  }
}

// D-07: кнопки
$("sendBtn").onclick = () => { const v = $("input").value.trim(); if (!v) return; $("input").value = ""; UChat(v); };
$("input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("sendBtn").click(); } });
$("btnStop").onclick = async () => { await api("/api/admin/stop", { method: "POST", body: "{}" }); showBubble("⏹ СТОП отправлен"); };
$("btnHide").onclick = () => { if (U) U.hide(); };
$("btnSettings").onclick = () => $("settings").classList.toggle("hidden");
$("btnVision").onclick = async () => {
  try { const r = await api("/api/vision/capture", { method: "POST" }); const d = await r.json(); showBubble("👁 " + (d.caption || "кадр захвачен")); }
  catch (e) { showBubble("⚠ зрение недоступно"); }
};
$("btnAuto").onclick = async () => { const lvl = prompt("Уровень автономии (off/observe/suggest/act):", "observe"); if (lvl) setConsent(lvl); };

function showBubble(text) {
  const b = $("bubble"); b.textContent = text; b.classList.remove("hidden");
  clearTimeout(showBubble._t); showBubble._t = setTimeout(() => b.classList.add("hidden"), 4000);
}
async function setConsent(level) {
  await api("/api/desktop/consent", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ observation_enabled: level !== "off", level }),
  });
  updateObs(level);
}
function updateObs(level) {
  $("obsIndicator").classList.toggle("hidden", level === "off");
  $("obsIndicator").textContent = "👁 наблюдает: " + level;
}

// D-09: SSE автономных фраз
async function streamAutonomous() {
  try {
    const r = await api("/api/autonomous/stream", { method: "POST", body: "{}" });
    const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      buf += dec.decode(value);
      let i; while ((i = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, i); buf = buf.slice(i + 2);
        const m = frame.match(/^data: (.+)$/m);
        if (m) { try { const ev = JSON.parse(m[1]); if (ev.phrase) { addMsg("uni", ev.phrase); showBubble(ev.phrase); } } catch (e) {} }
      }
    }
  } catch (e) {}
}
streamAutonomous();

// события от main (desktop-event SSE)
if (U) {
  U.onEvent((data) => {
    try {
      const ev = JSON.parse(data);
      if (ev.type === "consent_changed") updateObs(ev.consent.level);
      if (ev.type === "initiative") showBubble(ev.text || "Юни хочет что-то сказать");
    } catch (e) {}
  });
  U.onPTT((on) => { document.body.classList.toggle("recording", on); if (on) startRecording(); else stopRecording(); });
}

// D-10: PTT запись -> /api/stt
let mediaRecorder = null, chunks = [];
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream); chunks = [];
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: "audio/webm" });
      const buf = await blob.arrayBuffer();
      const r = await api("/api/stt", { method: "POST", headers: { "Content-Type": "audio/webm" }, body: buf });
      const d = await r.json();
      if (d.text) UChat(d.text); else showBubble("⚠ STT: " + (d.error || "нет текста"));
    };
    mediaRecorder.start();
  } catch (e) { showBubble("⚠ микрофон: " + e.message); }
}
function stopRecording() { if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop(); }

// D-11: настройки
async function loadSettings() {
  try {
    const r = await api("/api/roles"); const roles = await r.json();
    (roles.roles || []).forEach((role) => { const o = document.createElement("option"); o.value = role.id; o.textContent = role.name; $("roleSel").appendChild(o); });
  } catch (e) {}
  try {
    const r = await api("/api/tts/engines"); const d = await r.json();
    (d.engines || []).forEach((e) => (e.voices || []).forEach((v) => { const o = document.createElement("option"); o.value = v.id; o.textContent = e.id + " / " + v.name; $("voiceSel").appendChild(o); }));
  } catch (e) {}
  try {
    const r = await api("/api/desktop/consent"); const c = await r.json();
    updateObs(c.level || "off"); $("obsChk").checked = !!c.observation_enabled;
  } catch (e) {}
  if (U) { const st = await U.loadState(); if (st) { $("autostartChk").checked = !!st.autostart; $("opacity").value = st.opacity || 1; } }
}
$("saveSettings").onclick = async () => {
  const role = $("roleSel").value;
  try { await api("/api/role/switch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role }) }); } catch (e) {}
  await setConsent($("autoSel").value);
  const autostart = $("autostartChk").checked; const opacity = parseFloat($("opacity").value) || 1;
  if (U) { U.saveState({ autostart, opacity }); U.setOpacity(opacity); }
  showBubble("✅ настройки сохранены");
};
// D-12: observe-цикл — только если согласие включено (опрос скриншотов раз в 10с)
let observeTimer = null;
async function startObserveLoop() {
  if (observeTimer) clearInterval(observeTimer);
  observeTimer = setInterval(async () => {
    if (!U) return;
    let consent;
    try { const r = await api("/api/desktop/consent"); consent = await r.json(); } catch (e) { return; }
    if (!consent.observation_enabled) { updateObs("off"); return; }
    updateObs(consent.level || "observe");
    try {
      const res = await U.observeTick();
      if (res && res.ok && res.caption) {
        // suggest-уровень: показываем пузырь с тем, что увидели (бюджет не реализован — MVP)
        if ((consent.level || "observe") !== "observe") showBubble("👁 " + res.caption);
      }
    } catch (e) {}
  }, 10000);
}

loadSettings();
startObserveLoop();

// D-03: click-through — сообщаем main, интерактивен ли пиксель под курсором
document.addEventListener("mousemove", (e) => {
  const el = document.elementFromPoint(e.clientX, e.clientY);
  const interactive = !!el && !!el.closest("#chatPanel, #toolbar, #settings, button, textarea, select, input");
  if (U) U.hitTest(interactive);
});
