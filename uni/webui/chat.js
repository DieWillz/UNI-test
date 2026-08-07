/* UNI Chat Hub — фронтенд мультимодального чата (исправленная версия).
Бэкенд: существующий сервер на :8787.
Маршруты: /api/chat, /api/camera/*, /api/vision/capture, /api/context/feed, /api/participants.
Исправлено: микрофон распознаёт живьём; камера самовключается через гейт notice→start;
нет спама ошибок и сообщений; озвучка без плавающего окна. */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const chat = $("chat");
const audioEl = $("audioEl");

let lastSys = "";          // де-дупликация одинаковых sys-сообщений
let lastUniBubble = null;  // пузырь Юни, который сейчас озвучивается
let camOn = false;
let streamTimer = null;
let rec = null;            // SpeechRecognition

// ---------- сообщения ----------
function addMsg(role, text, who) {
  const el = document.createElement("div");
  el.className = "msg " + role;
  if (who) {
    const h = document.createElement("div");
    h.className = "who"; h.textContent = who;
    el.appendChild(h);
  }
  const p = document.createElement("div");
  p.textContent = text;
  el.appendChild(p);
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
  return el;
}
function sysOnce(text) {           // одну и ту же ошибку не повторяем
  if (text === lastSys) return;
  lastSys = text;
  addMsg("sys", text);
}

// ---------- бэкенд-пинг ----------
async function ping() {
  try {
    const r = await fetch("/api/participants");
    $("backendLed").className = "led " + (r.ok ? "on" : "err");
    $("backendText").textContent = r.ok ? "бэкенд: работает" : "бэкенд: ошибка";
  } catch {
    $("backendLed").className = "led err";
    $("backendText").textContent = "бэкенд: нет";
  }
}

// ---------- озвучка: индикатор + подсветка пузыря (без плавающего окна) ----------
function stopSpeaking() {
  $("voiceIndicator").hidden = true;
  if (lastUniBubble) lastUniBubble.classList.remove("speaking");
}
audioEl.addEventListener("play", () => {
  $("voiceIndicator").hidden = false;
  if (lastUniBubble) lastUniBubble.classList.add("speaking");
});
audioEl.addEventListener("ended", stopSpeaking);
audioEl.addEventListener("error", stopSpeaking);

// ---------- чат ----------
async function send(text) {
  if (!text.trim()) return;
  addMsg("user", text, "Вы");
  $("sendBtn").disabled = true;
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, use_voice: $("voiceOn").checked }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { sysOnce("Ошибка: " + (data.error || r.status)); return; }
    if (data.style_hint) addMsg("sys", "подсказка стиля: " + data.style_hint);
    lastUniBubble = addMsg("uni", data.text || "…", "UNI 🔊");
    if (data.audio_url && $("voiceOn").checked) {
      stopSpeaking();
      audioEl.src = data.audio_url + "?t=" + Date.now();
      audioEl.play().catch(() => {});
    }
  } catch (e) {
    sysOnce("Сетевая ошибка: " + e.message);
  } finally {
    $("sendBtn").disabled = false;
  }
}
$("sendBtn").onclick = () => { send($("msg").value); $("msg").value = ""; };
$("msg").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send($("msg").value); $("msg").value = ""; }
});

// ---------- микрофон: распознавание ЖИВЬЁМ, а не после записи ----------
$("micBtn").onclick = () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { sysOnce("распознавание речи не поддерживается браузером — печатайте текстом"); return; }
  if (rec) { rec.stop(); return; }
  rec = new SR();
  rec.lang = "ru-RU";
  rec.interimResults = false;
  rec.onresult = (ev) => send(ev.results[0][0].transcript);
  rec.onerror = (e) => sysOnce("не удалось распознать речь (" + e.error + ")");
  rec.onend = () => { rec = null; $("micBtn").classList.remove("active"); };
  rec.start();
  $("micBtn").classList.add("active");
};

// ---------- камера: самовключение через гейт notice → start ----------
function setCam(state, cls) {
  $("camLed").className = "led " + (cls || "");
  $("camText").textContent = "камера: " + state;
}
async function ensureCamera() {
  if (camOn) return true;
  let r = await fetch("/api/camera/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  if (r.status === 403) {                       // гейт: сначала уведомление
    await fetch("/api/camera/notice", { method: "POST" });
    r = await fetch("/api/camera/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  }
  if (r.ok) { camOn = true; setCam("вкл", "on"); return true; }
  const d = await r.json().catch(() => ({}));
  sysOnce("не удалось включить камеру: " + (d.error || r.status));
  return false;
}
function showPreview(b64) {
  const prev = $("preview");
  prev.innerHTML = "";
  const img = document.createElement("img");
  img.src = b64;
  prev.appendChild(img);
}
async function grab(silent) {
  if (!(await ensureCamera())) return null;
  const r = await fetch("/api/vision/capture", { method: "POST" });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { sysOnce("снимок не удался: " + (d.error || r.status)); return null; }
  showPreview(d.image_b64);
  if (!silent) addMsg("sys", "📷 система: кадр с камеры получен");
  return d.image_b64;
}
$("camNotice").onclick = async () => {
  const r = await fetch("/api/camera/notice", { method: "POST" });
  addMsg("sys", r.ok ? "🔔 звуковое уведомление отправлено — камеру можно включать" : "уведомление не прошло");
};
$("camStart").onclick = async () => { await ensureCamera(); };
$("camSnap").onclick = async () => {
  const img = await grab(false);
  if (img) send("Я сделала снимок с камеры, посмотри и скажи, что видишь.");
};
$("camStop").onclick = async () => {
  if (streamTimer) { clearInterval(streamTimer); streamTimer = null; $("camStream").checked = false; }
  await fetch("/api/camera/stop", { method: "POST" });
  camOn = false;
  setCam("выкл", "");
  $("preview").innerHTML = '<div class="empty">камера выключена</div>';
};
// стрим: только превью, БЕЗ сообщений в чат на каждый кадр
$("camStream").onchange = async (e) => {
  if (e.target.checked) {
    if (!(await ensureCamera())) { e.target.checked = false; return; }
    addMsg("sys", "🎥 стрим включён — кадры обновляются, чат не спамится");
    streamTimer = setInterval(() => grab(true), 5000);
  } else if (streamTimer) {
    clearInterval(streamTimer); streamTimer = null;
  }
};

// ---------- контекст-фид (без изменений логики) ----------
async function refreshFeeds() {
  const r = await fetch("/api/context/feed");
  const d = await r.json().catch(() => ({}));
  $("feedEnabled").checked = !!d.enabled;
  $("feedScrape").checked = !!d.allow_external_scrape;
  $("injectRate").value = Math.round((d.injection_rate || 0) * 100);
  $("rateVal").textContent = $("injectRate").value + "%";
  $("tonalMode").value = d.tonal_mode || "playful";
  const box = $("feeds"); box.innerHTML = "";
  (d.feeds || []).forEach((url) => {
    const row = document.createElement("div"); row.className = "feed";
    const u = document.createElement("span"); u.className = "url"; u.textContent = url;
    const x = document.createElement("button"); x.textContent = "✕";
    x.onclick = async () => {
      await fetch("/api/context/feed", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ remove: url }) });
      refreshFeeds();
    };
    row.appendChild(u); row.appendChild(x); box.appendChild(row);
  });
  if (!d.feeds || !d.feeds.length) box.innerHTML = '<div class="empty">нет фидов</div>';
}
$("feedAdd").onclick = async () => {
  const url = $("feedUrl").value.trim();
  if (!url) return;
  await fetch("/api/context/feed", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ add: url }) });
  $("feedUrl").value = ""; refreshFeeds();
};
$("injectRate").oninput = (e) => { $("rateVal").textContent = e.target.value + "%"; };
$("hintsSave").onclick = async () => {
  const hints = $("localHints").value.split("\n").map((s) => s.trim()).filter(Boolean);
  await fetch("/api/context/feed", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ hints }) });
  addMsg("sys", "локальные подсказки стиля сохранены");
};
["feedEnabled", "feedScrape", "injectRate", "tonalMode"].forEach((id) => {
  $(id).onchange = async () => {
    await fetch("/api/context/feed", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: $("feedEnabled").checked,
        allow_external_scrape: $("feedScrape").checked,
        injection_rate: Number($("injectRate").value) / 100,
        tonal_mode: $("tonalMode").value,
      }),
    });
    refreshFeeds();
  };
});

// ---------- старт ----------
ping(); refreshFeeds();
setInterval(ping, 15000);
})();
