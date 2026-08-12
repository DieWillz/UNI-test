/* UNI Desktop Companion — renderer (Hermes SOLO, 2026-08-11)
Чат -> /api/chat, озвучка -> /api/tts, SSE -> /api/autonomous/stream,
события оверлея -> /api/desktop/events (из main), PTT -> /api/stt.
*/
const SERVER = (window.UNI_SERVER) || "http://127.0.0.1:8787";
const $ = (id) => document.getElementById(id);

function addMsg(role, text) {
  const m = document.createElement("div");
  m.className = "msg " + (role === "user" ? "user" : "uni");
  m.textContent = text;
  $("messages").appendChild(m);
  $("messages").scrollTop = $("messages").scrollHeight;
}

async function uniChat(text) {
  addMsg("user", text);
  try {
    const r = await fetch(SERVER + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const d = await r.json();
    const reply = d.reply || d.response || d.message || JSON.stringify(d);
    addMsg("uni", reply);
    // озвучиваем
    try {
      await fetch(SERVER + "/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: reply }),
      });
    } catch (e) {}
  } catch (e) {
    addMsg("uni", "⚠ ошибка: " + e.message);
  }
}

/* кнопки */
$("sendBtn").onclick = () => {
  const v = $("input").value.trim();
  if (!v) return;
  $("input").value = "";
  uniChat(v);
};
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("sendBtn").click(); }
});
$("btnStop").onclick = async () => {
  await fetch(SERVER + "/api/admin/stop", { method: "POST", body: "{}" });
  showBubble("⏹ СТОП отправлен");
};
$("btnHide").onclick = () => { if (window.electron) window.electron.hide(); else window.close(); };
$("btnSettings").onclick = () => $("settings").classList.toggle("hidden");
$("btnAuto").onclick = async () => {
  const lvl = prompt("Уровень автономии (off/observe/suggest/act):", "observe");
  if (lvl) setConsent(lvl);
};
$("btnVision").onclick = async () => {
  try {
    const r = await fetch(SERVER + "/api/vision/capture", { method: "POST" });
    const d = await r.json();
    showBubble("👁 " + (d.caption || "кадр захвачен"));
  } catch (e) { showBubble("⚠ зрение недоступно"); }
};

async function setConsent(level) {
  await fetch(SERVER + "/api/desktop/consent", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ observation_enabled: level !== "off", level }),
  });
  updateObs(level);
}
function updateObs(level) {
  $("obsIndicator").classList.toggle("hidden", level === "off");
  $("obsIndicator").textContent = "👁 наблюдает: " + level;
}

function showBubble(text) {
  const b = $("bubble");
  b.textContent = text;
  b.classList.remove("hidden");
  clearTimeout(showBubble._t);
  showBubble._t = setTimeout(() => b.classList.add("hidden"), 4000);
}

/* SSE автономных фраз (через fetch-stream) */
async function streamAutonomous() {
  try {
    const r = await fetch(SERVER + "/api/autonomous/stream", { method: "POST", body: "{}" });
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value);
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, i); buf = buf.slice(i + 2);
        const m = frame.match(/^data: (.+)$/m);
        if (m) {
          try {
            const ev = JSON.parse(m[1]);
            if (ev.phrase) { addMsg("uni", ev.phrase); showBubble(ev.phrase); }
          } catch (e) {}
        }
      }
    }
  } catch (e) {}
}
streamAutonomous();

/* события от main (desktop-event SSE) */
if (window.electron && window.electron.onEvent) {
  window.electron.onEvent((data) => {
    try {
      const ev = JSON.parse(data);
      if (ev.type === "consent_changed") updateObs(ev.consent.level);
      if (ev.type === "initiative") showBubble(ev.text || "Юни хочет что-то сказать");
    } catch (e) {}
  });
  window.electron.onPTT((on) => {
    document.body.classList.toggle("recording", on);
    if (on) startRecording(); else stopRecording();
  });
}

/* PTT запись -> /api/stt */
let mediaRecorder = null, chunks = [];
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    chunks = [];
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: "audio/webm" });
      const buf = await blob.arrayBuffer();
      const r = await fetch(SERVER + "/api/stt", {
        method: "POST", headers: { "Content-Type": "audio/webm" }, body: buf,
      });
      const d = await r.json();
      if (d.text) uniChat(d.text);
      else showBubble("⚠ STT: " + (d.error || "нет текста"));
    };
    mediaRecorder.start();
  } catch (e) { showBubble("⚠ микрофон: " + e.message); }
}
function stopRecording() { if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop(); }

/* настройки: роли и голоса */
async function loadSettings() {
  try {
    const r = await fetch(SERVER + "/api/roles"); const roles = await r.json();
    (roles.roles || []).forEach((role) => {
      const o = document.createElement("option"); o.value = role.id; o.textContent = role.name; $("roleSel").appendChild(o);
    });
  } catch (e) {}
  try {
    const r = await fetch(SERVER + "/api/tts/engines"); const d = await r.json();
    (d.engines || []).forEach((e) => {
      (e.voices || []).forEach((v) => {
        const o = document.createElement("option"); o.value = v.id; o.textContent = e.id + " / " + v.name; $("voiceSel").appendChild(o);
      });
    });
  } catch (e) {}
  try {
    const r = await fetch(SERVER + "/api/desktop/consent"); const c = await r.json();
    updateObs(c.level || "off");
    $("obsChk").checked = !!c.observation_enabled;
  } catch (e) {}
}
$("saveSettings").onclick = async () => {
  const role = $("roleSel").value;
  try { await fetch(SERVER + "/api/role/switch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role }) }); } catch (e) {}
  const level = $("autoSel").value;
  await setConsent(level);
  showBubble("✅ настройки сохранены");
};
loadSettings();

/* click-through: сообщаем main, интерактивен ли пиксель под курсором */
document.addEventListener("mousemove", (e) => {
  const el = document.elementFromPoint(e.clientX, e.clientY);
  const interactive = !!el && (el.closest("#chatPanel, #toolbar, #settings, button, textarea, select, input"));
  if (window.electron && window.electron.hitTest) window.electron.hitTest(interactive);
});
