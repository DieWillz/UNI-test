/* UNI Admin v4 — фронтенд (Hermes, 2026-08-14)
 * Полноценная админка: реально дёргает существующие endpoint'ы
 * (/api/admin/*, /api/heartbeats, /api/journal, /api/tasks, /api/global_state,
 * /api/participants_dirs, /api/desktop/consent, /api/selftest, /api/demo/mouse,
 * /api/vision/observe, /api/autonomous/*, /api/computer/*, /api/xtoys/*,
 * /api/stop-cycle, /api/config, /api/admin/actions).
 *
 * КЛЮЧЕВАЯ ИДЕЯ: честные бейджи статуса на КАЖДОМ блоке.
 *  b-ok      — данные есть и валидны
 *  b-warn    — НЕТ ДАННЫХ / ВЫКЛЮЧЕНО (endpoint вернул «—»/пусто)
 *  b-stub    — НЕ РЕАЛИЗОВАНО (заглушка/endpoint отсутствует)
 *  b-err     — ошибка fetch / API
 *  b-info    — НЕ ПРОВЕРЕНО (требует живой среды/устройства)
 *  b-unknown — в процессе загрузки
 */
const API = location.origin;
const $  = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// ── бейджи честности ─────────────────────────────────────────────
function badge(kind, text){
  const map = {ok:'b-ok', warn:'b-warn', err:'b-err', info:'b-info', stub:'b-stub', unknown:'b-unknown'};
  return `<span class="badge ${map[kind]||'b-unknown'}">${esc(text)}</span>`;
}
// обновить бейдж внутри карточки (по data-b в card-h)
function setBadge(bodyOrCardId, kind, text){
  // 🤖 Qwen (2026-08-16, thinking-mode): принимать либо ID карточки
  // (ov-hw-card, ov-git-card, ov-stats-card), либо ID тела карточки
  // (ag-list, jr-list, rp-list, tk-backlog, tk-phases, xt-cards,
  // vs-consent, au-status, rp-content). Функция сама поднимается к
  // ближайшей .card и ищет там [data-b] span в header.
  const el = $(bodyOrCardId); if(!el) return;
  const card = el.classList && el.classList.contains('card') ? el : el.closest('.card');
  if(!card) return;
  const b = card.querySelector('[data-b]'); if(b) b.outerHTML = badge(kind, text);
}
function val(v, alt){ return (v===undefined||v===null||v===''||v==='—') ? (alt??'—') : v; }

// ── сетевой слой ─────────────────────────────────────────────────
// 🤖 Qwen (2026-08-16): увеличен таймаут с 6с до 30с по умолчанию.
// 6 секунд было слишком мало для действий вроде pytest/selftest,
// которые запускают фоновые процессы и могут занимать 10-20 секунд.
// Также добавлен параметр timeout для специфических вызовов.
async function apiJson(path, opts, timeout=30000){
  const ctrl = new AbortController();
  const t = setTimeout(()=>ctrl.abort(new Error('timeout: '+timeout+'ms')), timeout);
  try{
    const r = await fetch(API+path, Object.assign({signal:ctrl.signal, headers:{'Content-Type':'application/json'}}, opts));
    clearTimeout(t);
    if(!r.ok) throw new Error('HTTP '+r.status);
    const ct = r.headers.get('content-type')||'';
    return ct.includes('json') ? await r.json() : await r.text();
  }catch(e){ clearTimeout(t); throw e; }
}
async function apiPost(path, body, opts, timeout){
  return apiJson(path, Object.assign({method:'POST', body: body?JSON.stringify(body):'{}'}, opts||{}), timeout);
}
function toast(m){ const t=$('toast'); if(!t)return; t.textContent=m; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),2600); }

// ── навигация ────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    const v = btn.dataset.view;
    document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
    const w = $('view-'+v); if(w) w.classList.add('active');
    btn.classList.add('active');
    if(v==='overview') loadOverview();
    else if(v==='agents') loadAgents();
    else if(v==='logs') loadLogs();
    else if(v==='tasks') loadTasks();
    else if(v==='journal') loadJournal();
    else if(v==='reports') loadReports();
    else if(v==='tools') loadTools();
    else if(v==='vision') loadVision();
    else if(v==='autonomous') loadAutonomous();
    else if(v==='xtoys') loadXtoys();
    else if(v==='settings') loadSettings();
  });
});
$('theme-btn')?.addEventListener('click', ()=>{
  const cur = document.body.getAttribute('data-theme');
  const next = cur==='dark'?'light':'dark';
  document.body.setAttribute('data-theme', next);
  $('theme-btn').textContent = next==='dark'?'🌙':'☀';
  localStorage.setItem('uni_theme', next);
});

// 🤖 Qwen (2026-08-16): компактный режим
$('compact-btn')?.addEventListener('click', ()=>{
  document.body.classList.toggle('compact');
  const isCompact = document.body.classList.contains('compact');
  localStorage.setItem('uni_compact', isCompact ? '1' : '0');
  toast(isCompact ? '📐 Компактный режим включён' : '📐 Компактный режим выключен');
});

// Восстановление настроек из localStorage
(function restoreSettings(){
  const savedTheme = localStorage.getItem('uni_theme');
  if(savedTheme){
    document.body.setAttribute('data-theme', savedTheme);
    if($('theme-btn')) $('theme-btn').textContent = savedTheme==='dark'?'🌙':'☀';
  }
  const savedCompact = localStorage.getItem('uni_compact');
  if(savedCompact === '1'){
    document.body.classList.add('compact');
  }
})();

// проверка соединения с сервером
async function pingSelf(){
  const el = $('self-state');
  try{ await apiJson('/api/heartbeats'); el.className='badge b-ok'; el.textContent='на связи'; }
  catch(e){ el.className='badge b-err'; el.textContent='нет связи'; }
}

// ── ОБЗОР ────────────────────────────────────────────────────────
async function loadOverview(){
  // стек компонентов
  const cards = $('ov-cards');
  cards.innerHTML = '<div class="tile"><span class="spinner"></span> загрузка стека…</div>';
  try{
    const s = await apiJson('/api/admin/stack');
    const comps = [
      ['LLM (llama.cpp)', s.llama, 1235, s.llama?.model],
      ['WebUI (панель)', s.webui, 8787, null],
      ['Launcher', s.launcher, null, null],
      ['Desktop (Electron)', s.electron, null, null],
    ];
    cards.innerHTML = comps.map(([name,obj,port,extra])=>{
      const running = obj?.running;
      const pid = obj?.pid ?? '—';
      const model = extra ? `<div class="stack-meta">модель: ${esc(extra)}</div>` : '';
      return `<div class="tile">
        <h4>${esc(name)} ${badge(running?'ok':'warn', running?'работает':'остановлен')}</h4>
        <div class="stack-meta">PID: ${esc(pid)}${port?` · порт ${port}`:''}</div>
        ${model}
      </div>`;
    }).join('');
    // 🤖 Qwen (2026-08-16): убран сломанный вызов setBadge('ov-cards'?.parentElement,'ok','стек') —
    // ov-cards.parentElement это <section id="view-overview"> без [data-b].
    // У каждой под-карточки стека (hw/git/stats) уже есть свой бейдж через
    // setBadge('ov-hw-card',...) / setBadge('ov-git-card',...) / setBadge('ov-stats-card',...).
  }catch(e){
    cards.innerHTML = `<div class="tile">${badge('err','ОШИБКА')} ${esc(e.message)}</div>`;
  }

  // железо
  try{
    const hw = await apiJson('/api/admin/hw');
    const gpu = hw.gpu||{};
    const hasGpu = gpu.vram_free && gpu.vram_free!=='—';
    const hasRam = hw.ram && hw.ram!=='—';
    $('ov-hw').innerHTML =
      `<div class="kv"><span>GPU VRAM (своб./исп.)</span><span>${esc(gpu.vram_free)} / ${esc(gpu.vram_used)}</span></div>
       <div class="kv"><span>GPU load</span><span>${esc(gpu.utilization)}</span></div>
       <div class="kv"><span>RAM</span><span>${esc(hw.ram)}</span></div>
       <div class="kv"><span>CPU</span><span>${esc(hw.cpu)}</span></div>`;
    setBadge('ov-hw-card', (hasGpu||hasRam)?'ok':'warn', (hasGpu||hasRam)?'данные есть':'нет данных');
  }catch(e){ $('ov-hw').textContent = 'ОШИБКА: '+e.message; setBadge('ov-hw-card','err','ошибка'); }

  // git
  try{
    const g = await apiJson('/api/admin/git');
    const has = g.branch && g.branch!=='—';
    $('ov-git').innerHTML =
      `<div class="kv"><span>Ветка</span><span>${esc(g.branch)}</span></div>
       <div class="kv"><span>Коммит</span><span>${esc(g.commit)}</span></div>
       <div class="kv"><span>Сообщение</span><span class="muted">${esc(g.message)}</span></div>
       <div class="kv"><span>Когда</span><span>${esc(g.time)}</span></div>`;
    setBadge('ov-git-card', has?'ok':'warn', has?'есть':'нет git');
  }catch(e){ $('ov-git').textContent='ОШИБКА: '+e.message; setBadge('ov-git-card','err','ошибка'); }

  // статистика
  try{
    const st = await apiJson('/api/admin/stats');
    const pytest = st.pytest;
    const pytestKind = (typeof pytest==='string' && pytest.includes('нет'))?'warn':(pytest&&pytest.passed)?'ok':'info';
    $('ov-stats').innerHTML =
      `<div class="kv"><span>События UI (по компонентам)</span><span>${Object.keys(st.ui_events_by_component||{}).length} комп.</span></div>
       <div class="kv"><span>STOP нажатий</span><span>${esc(st.stop_count)}</span></div>
       <div class="kv"><span>Демо-мышь</span><span>${esc(st.demo_mouse_count)}</span></div>
       <div class="kv"><span>Захватов экрана</span><span>${esc(st.vision_capture_count)}</span></div>
       <div class="kv"><span>Сообщений чата</span><span>${esc(st.chat_messages)}</span></div>
       <div class="kv"><span>pytest</span><span>${badge(pytestKind, typeof pytest==='object'?(pytest.passed+'✓ / '+pytest.failed+'✗'):String(pytest))}</span></div>`;
    setBadge('ov-stats-card','ok','статистика');
  }catch(e){ $('ov-stats').textContent='ОШИБКА: '+e.message; setBadge('ov-stats-card','err','ошибка'); }
}
$('ov-refresh')?.addEventListener('click', loadOverview);
$('ov-stop')?.addEventListener('click', async ()=>{
  toast('⏹ STOP: создаю STOP.txt…');
  try{ await apiPost('/api/admin/stop'); toast('✅ STOP.txt создан — агенты остановятся'); }
  catch(e){ try{ await apiPost('/api/stop'); toast('✅ запрос СТОП отправлен'); }catch(_){ toast('❌ не удалось: '+e.message); } }
});

// ── АГЕНТЫ ──────────────────────────────────────────────────────
async function loadAgents(){
  const box = $('ag-list'); box.innerHTML = '<span class="spinner"></span> загрузка…';
  try{
    const d = await apiJson('/api/admin/agents');
    const ags = d.agents||[];
    if(!ags.length){ box.innerHTML = badge('warn','НЕТ ДАННЫХ')+' — файлы heartbeat не найдены'; setBadge('ag-list','warn','нет данных'); return; }
    box.innerHTML = `<table><thead><tr><th>Имя</th><th>Статус</th><th>Мин с биения</th><th>Последняя строка</th></tr></thead><tbody>`+
      ags.map(a=>`<tr>
        <td>${esc(a.name)}</td>
        <td>${badge(a.alive?'ok':'err', a.alive?'жив':'мёртв/протух')}</td>
        <td>${esc(a.minutes_since??'—')}</td>
        <td class="muted">${esc(a.last_line??'—')}</td>
      </tr>`).join('')+`</tbody></table>`;
    setBadge('ag-list','ok', ags.length+' аг.');
  }catch(e){ box.innerHTML = badge('err','ОШИБКА')+' '+esc(e.message); setBadge('ag-list','err','ошибка'); }
}
$('ag-refresh')?.addEventListener('click', loadAgents);

// 🤖 Qwen (2026-08-16): ЛОГИ — объединено из v3 (раньше в v4 не было).
// Читает /api/uni/logs (бэкенд уже существует), фильтрует уровень на клиенте
// (бэкенд отдаёт все строки без фильтра), раскрашивает ERROR/WARN/INFO.
async function loadLogs(){
  const box = $('lg-lines');
  const src = $('lg-source')?.value || 'llama';
  const lvl = ($('lg-level')?.value || '').toUpperCase();
  $('lg-title').textContent = 'Лог: ' + src + (lvl ? ' (только ' + lvl + ')' : '');
  box.innerHTML = '<span class="spinner"></span> загрузка ' + esc(src) + '…';
  try{
    const d = await apiJson('/api/uni/logs?source=' + encodeURIComponent(src) + '&since=0', {}, 15000);
    const lines = Array.isArray(d.lines) ? d.lines : [];
    // клиентский фильтр: если выбран уровень, оставляем только строки с этим словом
    const filtered = lvl
      ? lines.filter(l => {
          const t = String(l.t || '');
          if(lvl === 'ERROR') return /\b(ERROR|CRITICAL|FATAL|Traceback|Exception|AssertionError|TypeError|ValueError)\b/i.test(t);
          if(lvl === 'WARN') return /\b(WARN|WARNING)\b/i.test(t);
          if(lvl === 'INFO') return /\bINFO\b/i.test(t);
          return true;
        })
      : lines;
    if(!filtered.length){
      box.innerHTML = badge('warn', lvl ? 'НЕТ ' + lvl : 'ПУСТО') + ' — ' +
        (lines.length ? 'в логе нет строк с уровнем ' + lvl : 'лог пуст или файл отсутствует на диске');
      setBadge('lg-lines', 'warn', lvl ? 'нет ' + lvl : 'пусто');
      return;
    }
    box.innerHTML = filtered.map(l => {
      const t = String(l.t || '');
      let cls = 'log-info';
      if(/\b(ERROR|CRITICAL|FATAL|Traceback|Exception|AssertionError|TypeError|ValueError)\b/i.test(t)) cls = 'log-error';
      else if(/\b(WARN|WARNING)\b/i.test(t)) cls = 'log-warn';
      return '<div class="log-line ' + cls + '">' +
        '<span class="log-idx">' + (l.i ?? '') + '</span>' +
        esc(t) +
        '</div>';
    }).join('');
    setBadge('lg-lines', 'ok', filtered.length + ' строк');
  }catch(e){
    box.innerHTML = badge('err', 'ОШИБКА') + ' ' + esc(e.message);
    setBadge('lg-lines', 'err', 'ошибка');
  }
}
$('lg-refresh')?.addEventListener('click', loadLogs);
$('lg-source')?.addEventListener('change', loadLogs);
$('lg-level')?.addEventListener('change', loadLogs);

// ── ЗАДАЧИ / ФАЗЫ ───────────────────────────────────────────────
async function loadTasks(){
  try{
    const d = await apiJson('/api/admin/dev');
    const items = d.backlog||[];
    if(!items.length) $('tk-backlog').innerHTML = badge('warn','НЕТ ДАННЫХ')+' — UNI_BACKLOG.md пуст';
    else $('tk-backlog').innerHTML = `<table><thead><tr><th>Статус</th><th>Задача</th></tr></thead><tbody>`+
      items.map(it=>`<tr><td>${badge(it.status==='DONE'?'ok':it.status==='TODO'?'info':'warn', it.status)}</td><td>${esc(it.raw)}</td></tr>`).join('')+`</tbody></table>`;
    setBadge('tk-backlog','ok', items.length+' пунктов');

    // 🤖 Qwen (2026-08-16): фазы как таблица (как в v3) если есть id/name/proof,
    // иначе fallback на простой kv-список.
    const ph = d.phases||[];
    if(!ph.length){
      $('tk-phases').innerHTML = badge('warn','НЕТ ДАННЫХ')+' — runtime/admin/phases.json пуст';
      setBadge('tk-phases','warn','нет фаз');
    }else{
      const hasDetail = ph.some(p => p.id || p.name || p.title || p.proof);
      if(hasDetail){
        $('tk-phases').innerHTML = `<table><thead><tr>
          <th>ID</th><th>Название</th><th>Статус</th><th>Доказательство</th>
          </tr></thead><tbody>` +
          ph.map(p=>{
            const done = p.done || p.status==='done' || p.status==='[V]';
            const proof = (p.proof || p.proof_path || '—').toString();
            return `<tr>
              <td>${esc(p.id||p.id_num||'—')}</td>
              <td>${esc(p.name||p.title||'—')}</td>
              <td>${badge(done?'ok':'info', done?'готово':'в работе')}</td>
              <td class="muted">${esc(proof.slice(0,80))}</td>
            </tr>`;
          }).join('') + '</tbody></table>';
      }else{
        $('tk-phases').innerHTML = ph.map(p=>`<div class="kv"><span>${esc(p.name||p.id||'фаза')}</span><span>${badge(p.done?'ok':'info', p.done?'готово':'в работе')}</span></div>`).join('');
      }
      setBadge('tk-phases','ok', ph.length+' фаз');
    }

    $('tk-locks').textContent = (d.locks && Object.keys(d.locks).length) ? JSON.stringify(d.locks,null,2) : '— (блокировок нет)';
  }catch(e){
    $('tk-backlog').innerHTML = badge('err','ОШИБКА')+' '+esc(e.message);
  }
}
$('tk-refresh')?.addEventListener('click', loadTasks);

// ── ЖУРНАЛ ──────────────────────────────────────────────────────
async function loadJournal(){
  const box = $('jr-list'); const lim = parseInt($('jr-limit')?.value||'50', 10);
  box.innerHTML = '<span class="spinner"></span> загрузка…';
  try{
    // NOTE: маршрут сервера — точное совпадение "/api/journal" (без query).
    // Сервер отдаёт последние 100 записей; лимит режем на клиенте.
    const d = await apiJson('/api/journal');
    if(d.error){ box.innerHTML = badge('warn','НЕТ ДАННЫХ')+' — '+esc(d.error); setBadge('jr-list','warn','нет данных'); return; }
    const ents = d.entries||[];
    if(!ents.length){ box.innerHTML = badge('warn','НЕТ ДАННЫХ')+' — журнал пуст'; setBadge('jr-list','warn','пусто'); return; }
    box.innerHTML = `<div class="card-b" style="padding:0">`+ ents.slice(-lim).reverse().map(e=>{
      const line = typeof e==='object'? JSON.stringify(e): String(e);
      return `<div style="border-bottom:1px solid var(--border);padding:5px 0;font:11px/1.4 monospace;color:var(--text2)">${esc(line).slice(0,500)}</div>`;
    }).join('')+`</div>`;
    setBadge('jr-list','ok', ents.length+' зап.');
  }catch(e){ box.innerHTML = badge('err','ОШИБКА')+' '+esc(e.message); setBadge('jr-list','err','ошибка'); }
}
$('jr-refresh')?.addEventListener('click', loadJournal);

// ── ОТЧЁТЫ ─────────────────────────────────────────────────────
let rpNames = [];
async function loadReports(){
  const list = $('rp-list'); list.innerHTML = '<span class="spinner"></span> загрузка…';
  try{
    const d = await apiJson('/api/admin/reports');
    rpNames = (d.reports||[]);
    if(!rpNames.length){ list.innerHTML = badge('warn','НЕТ ДАННЫХ'); setBadge('rp-list','warn','нет'); return; }
    list.innerHTML = rpNames.map(r=>`<div class="kv" style="cursor:pointer" data-rp="${encRep(r.name)}"><span>${esc(r.name)}</span><span class="muted">${esc(r.kind)}</span></div>`).join('');
    list.querySelectorAll('[data-rp]').forEach(el=>el.addEventListener('click', ()=>loadReportContent(decodeURIComponent(el.dataset.rp))));
    setBadge('rp-list','ok', rpNames.length+' шт.');
  }catch(e){ list.innerHTML = badge('err','ОШИБКА')+' '+esc(e.message); setBadge('rp-list','err','ошибка'); }
}
// 🤖 Qwen (2026-08-16): автообновление каждые 30 секунд на странице Обзор
let _ovInterval = null;
function startAutoRefresh(){
  if(_ovInterval) clearInterval(_ovInterval);
  _ovInterval = setInterval(()=>{
    const activeView = document.querySelector('.view.active');
    if(activeView && activeView.id === 'view-overview') loadOverview();
  }, 30000);
}
function stopAutoRefresh(){
  if(_ovInterval){ clearInterval(_ovInterval); _ovInterval = null; }
}
function encRep(n){ return encodeURIComponent(n); }
async function loadReportContent(name){
  const c = $('rp-content'); $('rp-title').textContent = name; c.textContent='загрузка…';
  try{
    const d = await apiJson('/api/admin/reports/'+encRep(name));
    if(d.error){ c.textContent='❌ '+d.error; return; }
    c.textContent = d.content||'(пусто)';
    setBadge('rp-content','ok','загружено');
  }catch(e){ c.textContent='ОШИБКА: '+e.message; }
}
$('rp-refresh')?.addEventListener('click', loadReports);

// ── ИНСТРУМЕНТЫ (действия) ─────────────────────────────────────
const TOOLS = [
  {id:'stop', name:'Экстренный СТОП', desc:'Создать STOP.txt — все агенты и циклы остановятся.', btn:'■ STOP', cls:'danger', run:async()=>apiPost('/api/admin/stop')},
  {id:'stop_cycle', name:'СТОП цикла мыши', desc:'Остановить цикл автономной мыши (не убивает серверы).', btn:'СТОП цикл', cls:'danger', run:async()=>apiPost('/api/stop-cycle')},
  {id:'demo_mouse', name:'Демо мыши', desc:'Юни рисует круг + лайм-кольцо (HumanMouseController). Требует дисплея.', btn:'▶ Запустить', cls:'ok', run:async()=>apiPost('/api/admin/actions',{action:'demo_mouse'})},
  {id:'selftest', name:'Самотест UNI', desc:'Прогон встроенных проверок (selftest.run_all).', btn:'▶ Прогнать', cls:'ok', run:async()=>apiPost('/api/admin/actions',{action:'run_selftest'})},
  {id:'pytest', name:'pytest (фон)', desc:'Фоновый прогон тестов, результат в runtime/pytest_last.json.', btn:'▶ Запустить', cls:'amber', run:async()=>apiPost('/api/admin/actions',{action:'run_pytest'},undefined,90000)},
  {id:'arch', name:'Арх-аудит', desc:'py_compile всех uni/*.py (uni.check_architecture --strict).', btn:'▶ Проверить', cls:'amber', run:async()=>apiPost('/api/admin/actions',{action:'run_arch_check'},undefined,60000)},
  {id:'capture', name:'Скриншот экрана', desc:'pyautogui.screenshot → outbox/admin_capture_*.png.', btn:'📷 Снимок', cls:'', run:async()=>apiPost('/api/admin/actions',{action:'vision_capture'})},
  {id:'restart_webui', name:'Рестарт WebUI', desc:'Мягкий рестарт панели (если есть launcher).', btn:'↻ Рестарт', cls:'amber', run:async()=>apiPost('/api/admin/actions',{action:'restart_webui'})},
];
function renderTools(){
  const wrap = $('tl-actions');
  wrap.innerHTML = TOOLS.map(t=>`
    <div class="tool" id="tl-${t.id}">
      <h4>${esc(t.name)}</h4>
      <p>${esc(t.desc)}</p>
      <div class="tool-foot">
        <button class="btn ${t.cls||''}" data-run="${t.id}">${esc(t.btn)}</button>
        <span class="badge b-unknown">готов</span>
      </div>
    </div>`).join('');
  wrap.querySelectorAll('[data-run]').forEach(b=>b.addEventListener('click', ()=>runTool(b.dataset.run)));
}
async function runTool(id){
  const t = TOOLS.find(x=>x.id===id); if(!t) return;
  const card = $('tl-'+id); const foot = card.querySelector('.tool-foot');
  foot.querySelector('.badge').outerHTML = '<span class="badge b-info"><span class="spinner"></span> выполняется</span>';
  try{
    // 🤖 Qwen (2026-08-16): для инструментов увеличен таймаут до 90 секунд.
    // pytest и selftest могут занимать 30-60 секунд на первом запуске.
    const r = await t.run();
    foot.querySelector('.badge')?.remove();
    const ok = !(r && (r.error || r.ok===false));
    foot.insertAdjacentHTML('beforeend', badge(ok?'ok':'err', ok?'готово':'ошибка'));
    $('tl-result').textContent = JSON.stringify(r,null,2);
    toast('✅ '+t.name+': выполнено');
  }catch(e){
    foot.querySelector('.badge')?.remove();
    foot.insertAdjacentHTML('beforeend', badge('err','ошибка'));
    $('tl-result').textContent = 'ОШИБКА: '+e.message;
    toast('❌ '+t.name+': '+e.message);
  }
}
$('tl-refresh')?.addEventListener('click', renderTools);

// ── МЫШЬ И ЗРЕНИЕ ──────────────────────────────────────────────
async function loadVision(){
  const cards = $('vs-cards');
  try{
    const [consent, observeProbe] = await Promise.allSettled([
      apiJson('/api/desktop/consent'),
      apiPost('/api/vision/observe').catch(e=>({error:e.message})),
    ]);
    const c = consent.status==='fulfilled' ? consent.value : {error:'нет'};
    const obsEnabled = c.observation_enabled;
    $('vs-consent').innerHTML =
      `<div class="kv"><span>observation_enabled</span><span>${badge(obsEnabled?'ok':'warn', obsEnabled?'ВКЛ':'ВЫКЛ')}</span></div>
       <div class="kv"><span>Уровень consent</span><span>${esc(c.level??'—')}</span></div>
       <div class="kv"><span>Последнее изменение</span><span class="muted">${esc(c.last_change??'—')}</span></div>`;
    setBadge('vs-consent','ok','consent');

    const obs = observeProbe.status==='fulfilled'?observeProbe.value:{error:'нет'};
    const skipped = obs.skipped;
    cards.innerHTML =
      `<div class="tile"><h4>Наблюдение (👁)</h4>
        <div>${badge(skipped==='consent_off'?'warn':'info', skipped?('пропущено: '+skipped):(obs.initiative?'инициатива':'нет инициативы'))}</div>
        <div class="stack-meta" style="margin-top:6px">${obs.caption?esc(obs.caption).slice(0,120):'(требует живого LLM+vision)'}</div></div>
       <div class="tile"><h4>Визуальная мышь</h4>
        <div>${badge('info','НЕ ПРОВЕРЕНО')}</div>
        <div class="stack-meta" style="margin-top:6px">Демо мыши через HumanMouseController. Кнопка в «Инструменты».</div></div>
       <div class="tile"><h4>Moondream / поиск иконок</h4>
        <div>${badge('warn','НЕ РЕАЛИЗОВАНО в UI')}</div>
        <div class="stack-meta" style="margin-top:6px">Бэкенд uni/mouse/* готов, но нет кнопки в интерфейсе. Эндпоинт /api/click_at добавлен.</div></div>`;
  }catch(e){
    cards.innerHTML = `<div class="tile">${badge('err','ОШИБКА')} ${esc(e.message)}</div>`;
  }
}
$('vs-refresh')?.addEventListener('click', loadVision);

// ── АВТОНОМНОСТЬ ───────────────────────────────────────────────
// 🤖 Qwen (2026-08-16, thinking-mode): бэкенд отдаёт /api/config как
// sanitized dict. Имена ключей в истории проекта разнились:
//   - d.autonomous.enabled (nested)
//   - d.autonomous_enabled (top-level boolean)
//   - d.verification_enabled (top-level boolean)
// Пробуем обе формы и честно показываем что есть, без хардкода.
async function loadAutonomous(){
  const box = $('au-status'); box.innerHTML = '<span class="spinner"></span> …';
  try{
    const d = await apiJson('/api/config');
    const nested = d && typeof d === 'object' ? (d.autonomous || {}) : {};
    const on = nested.enabled === true || d?.autonomous_enabled === true;
    const verif = d?.verification_enabled === true;
    const hasAnyKey = 'autonomous_enabled' in (d||{}) || 'autonomous' in (d||{}) || 'verification_enabled' in (d||{});
    box.innerHTML =
      `<div class="kv"><span>autonomous (config)</span><span>${badge(on?'ok':'warn', on?'ВКЛ':'ВЫКЛ')}</span></div>
       <div class="kv"><span>verification_enabled</span><span>${badge(verif?'ok':'warn', verif?'ВКЛ':'ВЫКЛ')}</span></div>
       <div class="kv"><span>Ключи в /api/config</span><span class="muted">${hasAnyKey?'найдены':'нет совпадений — см. «Настройки» для полного дампа'}</span></div>
       <div class="kv"><span>Реальный рантайм</span><span>${badge('info','НЕ ПРОВЕРЕНО')}</span></div>`;
    setBadge('au-status', on?'ok':'warn', on?'включен':'выключен');
  }catch(e){ box.innerHTML = badge('err','ОШИБКА')+' '+esc(e.message); setBadge('au-status','err','ошибка'); }
}
$('au-refresh')?.addEventListener('click', loadAutonomous);
$('au-start')?.addEventListener('click', async()=>{ toast('▶ запрос старта автономности…'); try{ await apiPost('/api/autonomous/start'); toast('✅ отправлено'); loadAutonomous(); }catch(e){ toast('❌ '+e.message); } });
$('au-stop')?.addEventListener('click', async()=>{ toast('■ запрос стопа…'); try{ await apiPost('/api/autonomous/stop'); toast('✅ отправлено'); loadAutonomous(); }catch(e){ toast('❌ '+e.message); } });

// ── XTOYS / INTIFACE ────────────────────────────────────────────
async function loadXtoys(){
  const cards = $('xt-cards'); cards.innerHTML = '<span class="spinner"></span> …';
  const probes = [
    ['intiface', '/api/intiface/status'],
    ['xtoys session', '/api/xtoys/session/status'],
    ['xtoys motion', '/api/xtoys/motion/status'],
  ];
  try{
    const results = await Promise.all(probes.map(async ([n,p])=>{
      // короткий таймаут: xtoys может висеть без реального устройства
      const ctrl = new AbortController();
      const t = setTimeout(()=>ctrl.abort(), 3500);
      try{
        const r = await fetch(API+p, {signal:ctrl.signal});
        clearTimeout(t);
        const v = await r.json().catch(()=>({}));
        return {n, ok:true, v};
      }catch(e){ clearTimeout(t); return {n, ok:false, e:e.name==='AbortError'?'timeout':e.message}; }
    }));
    cards.innerHTML = results.map(r=>{
      const empty = !r.ok || !r.v || (typeof r.v==='object' && Object.keys(r.v).length===0);
      const note = r.ok ? JSON.stringify(r.v).slice(0,140) : ('ошибка: '+r.e);
      return `<div class="tile"><h4>${esc(r.n)}</h4>
        <div>${badge(empty?'warn':'ok', r.ok?(empty?'НЕТ ДАННЫХ':'есть данные'):'ОШИБКА')}</div>
        <div class="stack-meta" style="margin-top:6px">${esc(note)}</div></div>`;
    }).join('');
    setBadge('xt-cards','ok','XToys');
  }catch(e){ cards.innerHTML = `<div class="tile">${badge('err','ОШИБКА')} ${esc(e.message)}</div>`; setBadge('xt-cards','err','ошибка'); }
}
$('xt-refresh')?.addEventListener('click', loadXtoys);

// ── НАСТРОЙКИ ──────────────────────────────────────────────────
// 🤖 Qwen (2026-08-16, thinking-mode): /api/config возвращает
// sanitized dict с реальными ключами из config.yaml (секреты маскируются
// на бэкенде). Раньше фронтенд читал несуществующие поля (c.webui, c.llm,
// c.council, c.vision, c.autonomous) и всегда показывал «—». Теперь
// показываем то, что реально вернул сервер.
async function loadSettings(){
  try{
    const c = await apiJson('/api/config');
    const lines = [];
    lines.push('⚠ config.yaml с секретами не отдаётся (маскировка на бэкенде).');
    lines.push('Показан sanitized ответ /api/config:');
    lines.push('');
    if(c && typeof c === 'object'){
      const keys = Object.keys(c);
      if(!keys.length){
        lines.push('(пустой объект)');
      }else{
        for(const k of keys){
          const v = c[k];
          const sv = (v && typeof v === 'object') ? JSON.stringify(v) : String(v);
          lines.push(`${k}: ${sv}`);
        }
      }
    }else{
      lines.push(String(c));
    }
    $('st-config').textContent = lines.join('\n');
    // setBadge('st-config',...) невозможен — у карточки st-config в
    // v4/index.html нет [data-b] span в header. Статус читается
    // по содержимому pre: «загрузка…» / реальный дамп / «ОШИБКА: …».
  }catch(e){ $('st-config').textContent='ОШИБКА: '+e.message; }
}
$('st-apply')?.addEventListener('click', async()=>{
  const v = $('st-ui_variant').value, r=$('st-role').value, l=$('st-consent').value,
        a=$('st-autostart').checked, o=$('st-opacity').value;
  try{
    await apiPost('/api/admin/actions',{action:'set_ui_variant', v});
    await apiPost('/api/admin/actions',{action:'set_role', r});
    await apiPost('/api/admin/actions',{action:'set_consent', L:l});
    await apiPost('/api/admin/actions',{action:'set_autostart', on:a});
    await apiPost('/api/admin/actions',{action:'set_opacity', opacity:o});
    $('st-result').textContent='✅ настройки применены (state.json)';
    toast('✅ настройки сохранены');
  }catch(e){ $('st-result').textContent='❌ '+e.message; }
});

// ── старт ───────────────────────────────────────────────────────
renderTools();
pingSelf();
loadOverview();
startAutoRefresh();
setInterval(pingSelf, 15000);

// 🤖 Qwen (2026-08-16): горячие клавиши
// Ctrl+K — фокус на поиск (пока нет поля поиска, просто toast)
// Esc — закрыть активный toast
document.addEventListener('keydown', (e)=>{
  if(e.ctrlKey && e.key === 'k'){
    e.preventDefault();
    toast('🔍 Поиск пока не реализован (P2)');
  }
  if(e.key === 'Escape'){
    const t = $('toast');
    if(t && t.classList.contains('show')) t.classList.remove('show');
  }
});
