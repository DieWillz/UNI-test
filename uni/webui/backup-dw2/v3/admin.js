/* uni/webui/v3/admin.js — Админка полного контроля (ADM-03..ADM-08, 2026-08-13)
   Токены совпадают с оверлеем. Никаких lorem/заглушек: нет данных -> «—»/«нет данных». */
(function () {
  const API = "";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const dash = (s) => (s === undefined || s === null || s === "" ? "—" : s);

  // навигация
  $$(".nav-btn").forEach((b) =>
    b.addEventListener("click", () => {
      $$(".nav-btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      $$(".view").forEach((v) => v.classList.remove("active"));
      $("#view-" + b.dataset.view).classList.add("active");
      refresh();
    })
  );

  async function getj(path) {
    try {
      const r = await fetch(API + path);
      if (!r.ok) return { _error: r.status };
      return await r.json();
    } catch (e) {
      return { _error: String(e) };
    }
  }

  function statusClass(b) {
    return b ? "ok" : "bad";
  }

  async function renderDashboard() {
    const [stack, hw, git, stats, agents] = await Promise.all([
      getj("/api/admin/stack"), getj("/api/admin/hw"),
      getj("/api/admin/git"), getj("/api/admin/stats"), getj("/api/admin/agents"),
    ]);
    const cards = [];
    // stack
    const st = stack._error ? {} : stack;
    cards.push(`<div class="card"><h3>Стек</h3>
      <div class="kv"><span>llama</span><span class="${statusClass(st.llama && st.llama.running)}">${dash(st.llama && st.llama.running ? "pid " + st.llama.pid : "нет")}</span></div>
      <div class="kv"><span>модель</span><span>${dash(st.llama && st.llama.model)}</span></div>
      <div class="kv"><span>webui</span><span class="${statusClass(st.webui && st.webui.running)}">${dash(st.webui && st.webui.running ? "pid " + st.webui.pid : "нет")}</span></div>
      <div class="kv"><span>electron</span><span class="${statusClass(st.electron && st.electron.running)}">${dash(st.electron && st.electron.running ? "pid " + st.electron.pid : "нет")}</span></div>
      <div class="kv"><span>launcher</span><span class="${statusClass(st.launcher && st.launcher.running)}">${dash(st.launcher && st.launcher.running ? "pid " + st.launcher.pid : "нет")}</span></div>
    </div>`);
    // hw
    const h = hw._error ? { gpu: {} } : hw;
    cards.push(`<div class="card"><h3>Железо</h3>
      <div class="kv"><span>VRAM free</span><span>${dash(h.gpu && h.gpu.vram_free)}</span></div>
      <div class="kv"><span>VRAM used</span><span>${dash(h.gpu && h.gpu.vram_used)}</span></div>
      <div class="kv"><span>GPU util</span><span>${dash(h.gpu && h.gpu.utilization)}</span></div>
      <div class="kv"><span>RAM</span><span>${dash(h.ram)}</span></div>
      <div class="kv"><span>CPU</span><span>${dash(h.cpu)}</span></div>
    </div>`);
    // git
    const g = git._error ? {} : git;
    cards.push(`<div class="card"><h3>Git</h3>
      <div class="kv"><span>ветка</span><span>${dash(g.branch)}</span></div>
      <div class="kv"><span>коммит</span><span>${dash(g.commit)}</span></div>
      <div class="kv"><span>сообщение</span><span>${dash(g.message)}</span></div>
      <div class="kv"><span>время</span><span>${dash(g.time)}</span></div>
    </div>`);
    // pytest + stats
    const s = stats._error ? {} : stats;
    let pytest = "нет данных";
    if (s.pytest && typeof s.pytest === "object") pytest = `passed ${dash(s.pytest.passed)} / failed ${dash(s.pytest.failed)} (${dash(s.pytest.time_s)}s)`;
    else pytest = dash(s.pytest);
    cards.push(`<div class="card"><h3>Тесты и счётчики</h3>
      <div class="kv"><span>pytest</span><span>${pytest}</span></div>
      <div class="kv"><span>STOP</span><span>${dash(s.stop_count)}</span></div>
      <div class="kv"><span>демо-мышь</span><span>${dash(s.demo_mouse_count)}</span></div>
      <div class="kv"><span>vision-capture</span><span>${dash(s.vision_capture_count)}</span></div>
      <div class="kv"><span>чат-сообщений</span><span>${dash(s.chat_messages)}</span></div>
    </div>`);
    // audio (из /api/uni/status)
    const uni = await getj("/api/uni/status");
    const au = uni._error ? {} : uni.audio || {};
    cards.push(`<div class="card"><h3>Аудио (INT-03)</h3>
      <div class="kv"><span>STT</span><span class="${au.stt && au.stt.indexOf('отключён') >= 0 ? 'bad' : 'ok'}">${dash(au.stt)}</span></div>
      <div class="kv"><span>TTS</span><span class="${au.tts && au.tts.indexOf('отключён') >= 0 ? 'bad' : 'ok'}">${dash(au.tts)}</span></div>
    </div>`);
    // agents summary
    const a = agents._error ? { count: 0 } : agents;
    cards.push(`<div class="card"><h3>Агенты</h3>
      <div class="big">${dash(a.count)}</div><div class="kv"><span>живых</span><span>${dash((a.agents || []).filter((x) => x.alive).length)}</span></div>
    </div>`);
    $("#dash-cards").innerHTML = cards.join("");
  }

  async function renderPhases() {
    const dev = await getj("/api/admin/dev");
    if (dev._error) { $("#phases-block").textContent = "нет данных"; return; }
    let html = '<table><thead><tr><th>Фаза</th><th>Задача</th><th>Статус</th><th>Время</th><th>Пруф</th></tr></thead><tbody>';
    (dev.phases || []).forEach((p) => {
      html += `<tr><td>${esc(p.phase)}</td><td>${esc(p.task_id)}</td><td><span class="pill ${esc(p.status)}">${esc(p.status)}</span></td><td>${esc(p.ts)}</td><td>${esc(p.proof || "—")}</td></tr>`;
    });
    html += "</tbody></table>";
    $("#phases-block").innerHTML = html;
    let bl = '<table><thead><tr><th>Статус</th><th>Элемент</th></tr></thead><tbody>';
    (dev.backlog || []).forEach((b) => {
      bl += `<tr><td><span class="pill ${esc(b.status)}">${esc(b.status)}</span></td><td>${esc(b.raw)}</td></tr>`;
    });
    bl += "</tbody></table>";
    $("#backlog-block").innerHTML = bl;
    $("#locks-block").textContent = JSON.stringify(dev.locks || {}, null, 2);
  }

  async function renderLogs() {
    const src = $("#log-source").value;
    const lvl = $("#log-level").value;
    const data = await getj("/api/uni/logs?source=" + src);
    let lines = (data && data.lines) || [];
    if (lvl) lines = lines.filter((l) => l.t && l.t.indexOf("[" + lvl + "]") >= 0);
    $("#log-view").textContent = lines.length ? lines.map((l) => l.t).join("\n") : "нет данных";
    $("#log-view").scrollTop = $("#log-view").scrollHeight;
  }

  async function renderReports() {
    const list = await getj("/api/admin/reports");
    if (list._error) return;
    $("#reports-list").innerHTML = list
      .map((r) => `<div class="card" data-report="${esc(r.name)}" style="cursor:pointer"><h3>${esc(r.kind)}</h3><div>${esc(r.name)}</div></div>`)
      .join("");
    $$("#reports-list .card").forEach((c) =>
      c.addEventListener("click", async () => {
        const content = await getj("/api/admin/reports/" + c.dataset.report);
        $("#report-content").textContent = content.content || content.error || "нет данных";
      })
    );
  }

  async function renderAgents() {
    const a = await getj("/api/admin/agents");
    if (a._error) return;
    const tb = $("#agents-table tbody");
    tb.innerHTML = (a.agents || [])
      .map((x) => `<tr><td>${esc(x.name)}</td><td class="${x.alive ? "ok" : "dead"}">${x.alive ? "жив" : "мёртв"}</td><td>${dash(x.minutes_since)}</td><td>${esc(x.last_line || "—")}</td></tr>`)
      .join("");
  }

  async function adminAction(action, params, confirm) {
    const body = { action, params: params || {}, confirm: !!confirm };
    const r = await fetch(API + "/api/admin/actions", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    return await r.json();
  }

  // STOP
  $("#stop-btn").addEventListener("click", async () => {
    if (!confirm("Остановить ВЕСЬ стек Юни?")) return;
    const res = await adminAction("stop_stack", {}, true);
    alert("stop_stack: " + JSON.stringify(res));
  });

  // settings
  $("#apply-settings").addEventListener("click", async () => {
    await adminAction("set_ui_variant", { v: $("#set-ui_variant").value });
    await adminAction("set_role", { r: $("#set-role").value });
    await adminAction("set_consent", { L: $("#set-consent").value });
    await adminAction("set_autostart", { on: $("#set-autostart").checked });
    await adminAction("set_opacity", { opacity: $("#set-opacity").value });
    $("#settings-result").textContent = "применено " + new Date().toLocaleTimeString();
  });
  $("#open-overlay").addEventListener("click", () => adminAction("show_overlay", {}));
  $("#shot-overlay").addEventListener("click", async () => {
    const r = await adminAction("vision_capture", {});
    alert("скриншот: " + JSON.stringify(r));
  });

  // logs controls
  $("#log-refresh").addEventListener("click", renderLogs);
  $("#log-source").addEventListener("change", renderLogs);
  $("#log-level").addEventListener("change", renderLogs);

  async function refresh() {
    const active = $(".view.active").id.replace("view-", "");
    if (active === "dashboard") await renderDashboard();
    else if (active === "phases") await renderPhases();
    else if (active === "logs") await renderLogs();
    else if (active === "reports") await renderReports();
    else if (active === "agents") await renderAgents();
  }

  // первичная загрузка + автообновление 3с
  refresh();
  setInterval(refresh, 3000);
})();
