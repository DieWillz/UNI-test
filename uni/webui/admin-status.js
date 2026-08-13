// ЮНИ — Статус и логи (Hermes 2026-08-13, директива «Единый лаунчер»)
const $ = (s) => document.querySelector(s);
let curSrc = "llama";
let lastIdx = 0;

function dot(running) { return running ? '<span class="dot green"></span>' : '<span class="dot red"></span>'; }

async function loadStatus() {
  try {
    const r = await fetch("/api/uni/status");
    const s = await r.json();
    const c = $("#cards");
    const llama = s.llama || {};
    const webui = s.webui || {};
    const desk = s.desktop || {};
    const lms = (s.lmstudio || {}).reachable;
    c.innerHTML = `
      <div class="card"><div class="name">LLM (${llama.port})</div><div class="val">${dot(llama.running)} ${llama.running ? "работает" : "остановлен"}</div><div class="name" style="margin-top:4px">${llama.model || ""}</div></div>
      <div class="card"><div class="name">WebUI (${webui.port})</div><div class="val">${dot(webui.running)} ${webui.running ? "работает" : "остановлен"}</div></div>
      <div class="card"><div class="name">Оверлей (Electron)</div><div class="val">${dot(desk.running)} ${desk.running ? "работает" : "остановлен"}</div></div>
      <div class="card"><div class="name">LM Studio (1234)</div><div class="val">${lms ? '<span class="dot green"></span> доступен' : '<span class="dot grey"></span> нет'}</div></div>
    `;
  } catch (e) { $("#cards").innerHTML = '<div class="card"><div class="val" style="color:var(--danger)">нет связи с админкой</div></div>'; }
}

async function loadLogs() {
  try {
    const r = await fetch("/api/uni/logs?source=" + curSrc + "&since=" + lastIdx);
    const d = await r.json();
    const lines = d.lines || [];
    if (lines.length) {
      const box = $("#log");
      for (const ln of lines) { box.textContent += ln.t + "\n"; lastIdx = ln.i + 1; }
      box.scrollTop = box.scrollHeight;
    }
  } catch (e) {}
}

$("#src").onchange = (e) => { curSrc = e.target.value; $("#log").textContent = ""; lastIdx = 0; };
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    curSrc = t.dataset.src; $("#src").value = curSrc; $("#log").textContent = ""; lastIdx = 0;
  };
});
$("#restartLlama").onclick = async () => {
  $("#msg").textContent = "перезапуск LLM…";
  try { await fetch("/api/admin/restart-llm", { method: "POST" }).catch(()=>{}); } catch(e){}
  // fallback: если нет отдельного эндпоинта, просто ждём
  setTimeout(() => { $("#msg").textContent = ""; }, 3000);
};
$("#stopAll").onclick = async () => {
  $("#msg").textContent = "остановка…";
  try { await fetch("/api/admin/stop", { method: "POST" }); } catch(e){}
};

loadStatus(); loadLogs();
setInterval(loadStatus, 3000);
setInterval(loadLogs, 3000);
