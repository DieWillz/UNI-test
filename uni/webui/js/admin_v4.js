/* UNI Admin v4 — интегрированный модуль (Hermes, 2026-08-16)
 * Подключается ИЗОЛИРОВАННО в корневую админку (webui/index.html).
 * Все имена префиксованы v4*, чтобы НЕ конфликтовать с каноном (js/app.js:
 * $ , toast, badge, setBadge, showView, apiGet...).
 * Логика портирована из webui/v4/app.js (честные бейджи статуса).
 */
(function(){
'use strict';
const API = location.origin;
const v4$ = (id) => document.getElementById(id);
const v4Esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// бейджи честности
function v4Badge(kind, text){
  const map = {ok:'b-ok', warn:'b-warn', err:'b-err', info:'b-info', stub:'b-stub', unknown:'b-unknown'};
  return `<span class="v4-badge ${map[kind]||'b-unknown'}">${v4Esc(text)}</span>`;
}
function v4SetBadge(bodyOrCardId, kind, text){
  const el = v4$(bodyOrCardId); if(!el) return;
  const card = el.classList && el.classList.contains('v4-card') ? el : el.closest('.v4-card');
  if(!card) return;
  const b = card.querySelector('[data-b]'); if(b) b.outerHTML = v4Badge(kind, text);
}
function v4Val(v, alt){ return (v===undefined||v===null||v===''||v==='—') ? (alt??'—') : v; }
async function v4Api(path, opts, timeout=30000){
  const ctrl = new AbortController();
  const t = setTimeout(()=>ctrl.abort(new Error('timeout: '+timeout+'ms')), timeout);
  try{
    const r = await fetch(API+path, Object.assign({signal:ctrl.signal, headers:{'Content-Type':'application/json'}}, opts||{}));
    clearTimeout(t);
    if(!r.ok) throw new Error('HTTP '+r.status);
    const ct = r.headers.get('content-type')||'';
    return ct.includes('json') ? await r.json() : await r.text();
  }catch(e){ clearTimeout(t); throw e; }
}
async function v4Post(path, body, timeout){
  return v4Api(path, Object.assign({method:'POST', body: body?JSON.stringify(body):'{}'}), timeout);
}
function v4Toast(m){
  let t = v4$('v4-toast');
  if(!t){ t = document.createElement('div'); t.id='v4-toast'; t.className='v4-toast'; document.body.appendChild(t); }
  t.textContent = m; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'), 2600);
}

// ── ОБЗОР ────────────────────────────────────────────────────────
async function v4LoadOverview(){
  const cards = v4$('v4-ov-cards'); if(!cards) return;
  cards.innerHTML = '<div class="v4-tile"><span class="v4-spinner"></span> загрузка стека…</div>';
  try{
    const s = await v4Api('/api/admin/stack');
    const comps = [
      ['LLM (llama.cpp)', s.llama, 1235, s.llama&&s.llama.model],
      ['WebUI (панель)', s.webui, 8787, null],
      ['Launcher', s.launcher, null, null],
      ['Desktop (Electron)', s.electron, null, null],
    ];
    cards.innerHTML = comps.map(([name,obj,port,extra])=>{
      const running = obj&&obj.running;
      const pid = obj&&obj.pid!=null ? obj.pid : '—';
      const model = extra ? `<div class="v4-meta">модель: ${v4Esc(extra)}</div>` : '';
      return `<div class="v4-tile"><h4>${v4Esc(name)} ${v4Badge(running?'ok':'warn', running?'работает':'остановлен')}</h4>
        <div class="v4-meta">PID: ${v4Esc(pid)}${port?` · порт ${port}`:''}</div>${model}</div>`;
    }).join('');
  }catch(e){ cards.innerHTML = `<div class="v4-tile">${v4Badge('err','ОШИБКА')} ${v4Esc(e.message)}</div>`; }

  try{
    const hw = await v4Api('/api/admin/hw'); const gpu = hw.gpu||{};
    const hasGpu = gpu.vram_free && gpu.vram_free!=='—';
    const hasRam = hw.ram && hw.ram!=='—';
    v4$('v4-ov-hw').innerHTML =
      `<div class="v4-kv"><span>GPU VRAM (своб./исп.)</span><span>${v4Esc(gpu.vram_free)} / ${v4Esc(gpu.vram_used)}</span></div>
       <div class="v4-kv"><span>GPU load</span><span>${v4Esc(gpu.utilization)}</span></div>
       <div class="v4-kv"><span>RAM</span><span>${v4Esc(hw.ram)}</span></div>
       <div class="v4-kv"><span>CPU</span><span>${v4Esc(hw.cpu)}</span></div>`;
    v4SetBadge('v4-ov-hw-card', (hasGpu||hasRam)?'ok':'warn', (hasGpu||hasRam)?'данные есть':'нет данных');
  }catch(e){ if(v4$('v4-ov-hw')) v4$('v4-ov-hw').textContent='ОШИБКА: '+e.message; v4SetBadge('v4-ov-hw-card','err','ошибка'); }

  try{
    const g = await v4Api('/api/admin/git'); const has = g.branch && g.branch!=='—';
    v4$('v4-ov-git').innerHTML =
      `<div class="v4-kv"><span>Ветка</span><span>${v4Esc(g.branch)}</span></div>
       <div class="v4-kv"><span>Коммит</span><span>${v4Esc(g.commit)}</span></div>
       <div class="v4-kv"><span>Сообщение</span><span class="v4-muted">${v4Esc(g.message)}</span></div>
       <div class="v4-kv"><span>Когда</span><span>${v4Esc(g.time)}</span></div>`;
    v4SetBadge('v4-ov-git-card', has?'ok':'warn', has?'есть':'нет git');
  }catch(e){ if(v4$('v4-ov-git')) v4$('v4-ov-git').textContent='ОШИБКА: '+e.message; v4SetBadge('v4-ov-git-card','err','ошибка'); }

  try{
    const st = await v4Api('/api/admin/stats');
    v4$('v4-ov-stats').innerHTML =
      `<div class="v4-kv"><span>STOP нажатий</span><span>${v4Esc(st.stop_count)}</span></div>
       <div class="v4-kv"><span>Демо-мышь</span><span>${v4Esc(st.demo_mouse_count)}</span></div>
       <div class="v4-kv"><span>Захватов экрана</span><span>${v4Esc(st.vision_capture_count)}</span></div>
       <div class="v4-kv"><span>Сообщений чата</span><span>${v4Esc(st.chat_messages)}</span></div>`;
    v4SetBadge('v4-ov-stats-card','ok','статистика');
  }catch(e){ if(v4$('v4-ov-stats')) v4$('v4-ov-stats').textContent='ОШИБКА: '+e.message; v4SetBadge('v4-ov-stats-card','err','ошибка'); }
}

// ── АГЕНТЫ ──────────────────────────────────────────────────────
async function v4LoadAgents(){
  const box = v4$('v4-ag-list'); if(!box) return; box.innerHTML='<span class="v4-spinner"></span> загрузка…';
  try{
    const d = await v4Api('/api/admin/agents'); const ags = d.agents||[];
    if(!ags.length){ box.innerHTML = v4Badge('warn','НЕТ ДАННЫХ')+' — heartbeat не найдены'; v4SetBadge('v4-ag-list','warn','нет данных'); return; }
    box.innerHTML = `<table class="v4-tbl"><thead><tr><th>Имя</th><th>Статус</th><th>Мин с биения</th><th>Последняя строка</th></tr></thead><tbody>`+
      ags.map(a=>`<tr><td>${v4Esc(a.name)}</td><td>${v4Badge(a.alive?'ok':'err', a.alive?'жив':'мёртв')}</td><td>${v4Esc(a.minutes_since!=null?a.minutes_since:'—')}</td><td class="v4-muted">${v4Esc(a.last_line||'—')}</td></tr>`).join('')+`</tbody></table>`;
    v4SetBadge('v4-ag-list','ok', ags.length+' аг.');
  }catch(e){ box.innerHTML = v4Badge('err','ОШИБКА')+' '+v4Esc(e.message); v4SetBadge('v4-ag-list','err','ошибка'); }
}

// ── ЛОГИ ─────────────────────────────────────────────────────────
async function v4LoadLogs(){
  const box = v4$('v4-lg-lines'); if(!box) return;
  const src = (v4$('v4-lg-source')&&v4$('v4-lg-source').value) || 'llama';
  const lvl = (v4$('v4-lg-level')&&v4$('v4-lg-level').value||'').toUpperCase();
  box.innerHTML='<span class="v4-spinner"></span> загрузка…';
  try{
    const d = await v4Api('/api/uni/logs?source='+encodeURIComponent(src)+'&since=0', {}, 15000);
    const lines = Array.isArray(d.lines)?d.lines:[];
    const filtered = lvl ? lines.filter(l=>{ const t=String(l.t||'');
      if(lvl==='ERROR') return /\b(ERROR|CRITICAL|FATAL|Traceback|Exception|AssertionError|TypeError|ValueError)\b/i.test(t);
      if(lvl==='WARN') return /\b(WARN|WARNING)\b/i.test(t);
      if(lvl==='INFO') return /\bINFO\b/i.test(t); return true; }) : lines;
    if(!filtered.length){ box.innerHTML = v4Badge('warn', lvl?'НЕТ '+lvl:'ПУСТО'); v4SetBadge('v4-lg-lines','warn', lvl?'нет '+lvl:'пусто'); return; }
    box.innerHTML = filtered.map(l=>{ const t=String(l.t||''); let cls='v4-log-info';
      if(/\b(ERROR|CRITICAL|FATAL|Traceback|Exception)\b/i.test(t)) cls='v4-log-error';
      else if(/\b(WARN|WARNING)\b/i.test(t)) cls='v4-log-warn';
      return `<div class="${cls}">${v4Esc(t)}</div>`; }).join('');
    v4SetBadge('v4-lg-lines','ok', filtered.length+' строк');
  }catch(e){ box.innerHTML = v4Badge('err','ОШИБКА')+' '+v4Esc(e.message); v4SetBadge('v4-lg-lines','err','ошибка'); }
}

// ── ЗАДАЧИ / ФАЗЫ ───────────────────────────────────────────────
async function v4LoadTasks(){
  try{
    const d = await v4Api('/api/admin/dev'); const items = d.backlog||[];
    if(!items.length) v4$('v4-tk-backlog').innerHTML = v4Badge('warn','НЕТ ДАННЫХ')+' — UNI_BACKLOG.md пуст';
    else v4$('v4-tk-backlog').innerHTML = `<table class="v4-tbl"><thead><tr><th>Статус</th><th>Задача</th></tr></thead><tbody>`+
      items.map(it=>`<tr><td>${v4Badge(it.status==='DONE'?'ok':it.status==='TODO'?'info':'warn', it.status)}</td><td>${v4Esc(it.raw)}</td></tr>`).join('')+`</tbody></table>`;
    v4SetBadge('v4-tk-backlog','ok', items.length+' пунктов');
    const ph = d.phases||[];
    if(!ph.length){ v4$('v4-tk-phases').innerHTML = v4Badge('warn','НЕТ ДАННЫХ')+' — phases.json пуст'; v4SetBadge('v4-tk-phases','warn','нет фаз'); }
    else{ v4$('v4-tk-phases').innerHTML = ph.map(p=>`<div class="v4-kv"><span>${v4Esc(p.name||p.id||'фаза')}</span><span>${v4Badge(p.done?'ok':'info', p.done?'готово':'в работе')}</span></div>`).join(''); v4SetBadge('v4-tk-phases','ok', ph.length+' фаз'); }
    v4$('v4-tk-locks').textContent = (d.locks && Object.keys(d.locks).length) ? JSON.stringify(d.locks,null,2) : '— (блокировок нет)';
  }catch(e){ if(v4$('v4-tk-backlog')) v4$('v4-tk-backlog').innerHTML = v4Badge('err','ОШИБКА')+' '+v4Esc(e.message); }
}

// ── ЖУРНАЛ ──────────────────────────────────────────────────────
async function v4LoadJournal(){
  const box = v4$('v4-jr-list'); if(!box) return; const lim = parseInt((v4$('v4-jr-limit')&&v4$('v4-jr-limit').value)||'50',10);
  box.innerHTML='<span class="v4-spinner"></span> загрузка…';
  try{
    const d = await v4Api('/api/journal');
    if(d.error){ box.innerHTML = v4Badge('warn','НЕТ ДАННЫХ')+' — '+v4Esc(d.error); v4SetBadge('v4-jr-list','warn','нет данных'); return; }
    const ents = d.entries||[];
    if(!ents.length){ box.innerHTML = v4Badge('warn','НЕТ ДАННЫХ')+' — журнал пуст'; v4SetBadge('v4-jr-list','warn','пусто'); return; }
    box.innerHTML = ents.slice(-lim).reverse().map(e=>{ const line = typeof e==='object'?JSON.stringify(e):String(e);
      return `<div style="border-bottom:1px solid var(--border);padding:5px 0;font:11px/1.4 monospace;color:var(--text2)">${v4Esc(line).slice(0,500)}</div>`; }).join('');
    v4SetBadge('v4-jr-list','ok', ents.length+' зап.');
  }catch(e){ box.innerHTML = v4Badge('err','ОШИБКА')+' '+v4Esc(e.message); v4SetBadge('v4-jr-list','err','ошибка'); }
}

// ── ОТЧЁТЫ ─────────────────────────────────────────────────────
let v4RpNames = [];
async function v4LoadReports(){
  const list = v4$('v4-rp-list'); if(!list) return; list.innerHTML='<span class="v4-spinner"></span> загрузка…';
  try{
    const d = await v4Api('/api/admin/reports'); v4RpNames = (d.reports||[]);
    if(!v4RpNames.length){ list.innerHTML = v4Badge('warn','НЕТ ДАННЫХ'); v4SetBadge('v4-rp-list','warn','нет'); return; }
    list.innerHTML = v4RpNames.map(r=>`<div class="v4-kv" style="cursor:pointer" data-rp="${encodeURIComponent(r.name)}"><span>${v4Esc(r.name)}</span><span class="v4-muted">${v4Esc(r.kind)}</span></div>`).join('');
    list.querySelectorAll('[data-rp]').forEach(el=>el.addEventListener('click', ()=>v4LoadReportContent(decodeURIComponent(el.dataset.rp))));
    v4SetBadge('v4-rp-list','ok', v4RpNames.length+' шт.');
  }catch(e){ list.innerHTML = v4Badge('err','ОШИБКА')+' '+v4Esc(e.message); v4SetBadge('v4-rp-list','err','ошибка'); }
}
async function v4LoadReportContent(name){
  const c = v4$('v4-rp-content'); if(!c) return; v4$('v4-rp-title').textContent = name; c.textContent='загрузка…';
  try{ const d = await v4Api('/api/admin/reports/'+encodeURIComponent(name));
    if(d.error){ c.textContent='❌ '+d.error; return; } c.textContent = d.content||'(пусто)'; v4SetBadge('v4-rp-content','ok','загружено');
  }catch(e){ c.textContent='ОШИБКА: '+e.message; }
}

// ── ИНСТРУМЕНТЫ ────────────────────────────────────────────────
const V4_TOOLS = [
  {id:'stop', name:'Экстренный СТОП', desc:'Создать STOP.txt — агенты остановятся.', btn:'■ STOP', cls:'danger', run:()=>v4Post('/api/admin/stop')},
  {id:'stop_cycle', name:'СТОП цикла мыши', desc:'Остановить цикл автономной мыши.', btn:'СТОП цикл', cls:'danger', run:()=>v4Post('/api/stop-cycle')},
  {id:'demo_mouse', name:'Демо мыши', desc:'Юни рисует круг + кольцо.', btn:'▶ Запустить', cls:'ok', run:()=>v4Post('/api/admin/actions',{action:'demo_mouse'})},
  {id:'selftest', name:'Самотест UNI', desc:'Прогон проверок.', btn:'▶ Прогнать', cls:'ok', run:()=>v4Post('/api/admin/actions',{action:'run_selftest'})},
  {id:'pytest', name:'pytest (фон)', desc:'Фоновый прогон тестов.', btn:'▶ Запустить', cls:'amber', run:()=>v4Post('/api/admin/actions',{action:'run_pytest'},90000)},
  {id:'arch', name:'Арх-аудит', desc:'py_compile всех uni/*.py.', btn:'▶ Проверить', cls:'amber', run:()=>v4Post('/api/admin/actions',{action:'run_arch_check'},60000)},
  {id:'capture', name:'Скриншот', desc:'pyautogui.screenshot.', btn:'📷 Снимок', cls:'', run:()=>v4Post('/api/admin/actions',{action:'vision_capture'})},
  {id:'restart_webui', name:'Рестарт WebUI', desc:'Мягкий рестарт панели.', btn:'↻ Рестарт', cls:'amber', run:()=>v4Post('/api/admin/actions',{action:'restart_webui'})},
];
function v4RenderTools(){
  const wrap = v4$('v4-tl-actions'); if(!wrap) return;
  wrap.innerHTML = V4_TOOLS.map(t=>`<div class="v4-tool" id="v4-tl-${t.id}"><h4>${v4Esc(t.name)}</h4><p>${v4Esc(t.desc)}</p>
    <div class="v4-tool-foot"><button class="v4-btn ${t.cls||''}" data-run="${t.id}">${v4Esc(t.btn)}</button><span class="v4-badge b-unknown">готов</span></div></div>`).join('');
  wrap.querySelectorAll('[data-run]').forEach(b=>b.addEventListener('click', ()=>v4RunTool(b.dataset.run)));
}
async function v4RunTool(id){
  const t = V4_TOOLS.find(x=>x.id===id); if(!t) return;
  const card = v4$('v4-tl-'+id); const foot = card.querySelector('.v4-tool-foot');
  foot.querySelector('.v4-badge').outerHTML = '<span class="v4-badge b-info"><span class="v4-spinner"></span> выполняется</span>';
  try{ const r = await t.run(); foot.querySelector('.v4-badge')&&foot.querySelector('.v4-badge').remove();
    const ok = !(r && (r.error || r.ok===false));
    foot.insertAdjacentHTML('beforeend', v4Badge(ok?'ok':'err', ok?'готово':'ошибка'));
    if(v4$('v4-tl-result')) v4$('v4-tl-result').textContent = JSON.stringify(r,null,2);
    v4Toast('✅ '+t.name);
  }catch(e){ foot.querySelector('.v4-badge')&&foot.querySelector('.v4-badge').remove();
    foot.insertAdjacentHTML('beforeend', v4Badge('err','ошибка'));
    if(v4$('v4-tl-result')) v4$('v4-tl-result').textContent='ОШИБКА: '+e.message;
    v4Toast('❌ '+t.name+': '+e.message); }
}

// ── МЫШЬ И ЗРЕНИЕ ──────────────────────────────────────────────
async function v4LoadVision(){
  const cards = v4$('v4-vs-cards'); if(!cards) return;
  try{
    const [consent, observeProbe] = await Promise.allSettled([ v4Api('/api/desktop/consent'), v4Post('/api/vision/observe').catch(e=>({error:e.message})) ]);
    const c = consent.status==='fulfilled'?consent.value:{error:'нет'}; const obsEnabled = c.observation_enabled;
    if(v4$('v4-vs-consent')) v4$('v4-vs-consent').innerHTML =
      `<div class="v4-kv"><span>observation_enabled</span><span>${v4Badge(obsEnabled?'ok':'warn', obsEnabled?'ВКЛ':'ВЫКЛ')}</span></div>
       <div class="v4-kv"><span>Уровень consent</span><span>${v4Esc(c.level!=null?c.level:'—')}</span></div>`;
    v4SetBadge('v4-vs-consent','ok','consent');
    const obs = observeProbe.status==='fulfilled'?observeProbe.value:{error:'нет'}; const skipped = obs.skipped;
    cards.innerHTML =
      `<div class="v4-tile"><h4>Наблюдение (👁)</h4><div>${v4Badge(skipped==='consent_off'?'warn':'info', skipped?('пропущено: '+skipped):(obs.initiative?'инициатива':'нет инициативы'))}</div>
        <div class="v4-meta">${obs.caption?v4Esc(obs.caption).slice(0,120):'(требует живого LLM+vision)'}</div></div>
       <div class="v4-tile"><h4>Визуальная мышь</h4><div>${v4Badge('info','НЕ ПРОВЕРЕНО')}</div>
        <div class="v4-meta">Демо мыши через HumanMouseController. Кнопка в «Инструменты».</div></div>`;
  }catch(e){ cards.innerHTML = `<div class="v4-tile">${v4Badge('err','ОШИБКА')} ${v4Esc(e.message)}</div>`; }
}

// ── АВТОНОМНОСТЬ ───────────────────────────────────────────────
async function v4LoadAutonomous(){
  const box = v4$('v4-au-status'); if(!box) return; box.innerHTML='<span class="v4-spinner"></span> …';
  try{
    const d = await v4Api('/api/config');
    const nested = d && typeof d==='object' ? (d.autonomous||{}) : {};
    const on = nested.enabled===true || (d&&d.autonomous_enabled===true);
    const verif = d&&d.verification_enabled===true;
    box.innerHTML =
      `<div class="v4-kv"><span>autonomous (config)</span><span>${v4Badge(on?'ok':'warn', on?'ВКЛ':'ВЫКЛ')}</span></div>
       <div class="v4-kv"><span>verification_enabled</span><span>${v4Badge(verif?'ok':'warn', verif?'ВКЛ':'ВЫКЛ')}</span></div>
       <div class="v4-kv"><span>Реальный рантайм</span><span>${v4Badge('info','НЕ ПРОВЕРЕНО')}</span></div>`;
    v4SetBadge('v4-au-status', on?'ok':'warn', on?'включен':'выключен');
  }catch(e){ box.innerHTML = v4Badge('err','ОШИБКА')+' '+v4Esc(e.message); v4SetBadge('v4-au-status','err','ошибка'); }
}

// ── XTOYS / INTIFACE ────────────────────────────────────────────
async function v4LoadXtoys(){
  const cards = v4$('v4-xt-cards'); if(!cards) return; cards.innerHTML='<span class="v4-spinner"></span> …';
  const probes = [['intiface','/api/intiface/status'],['xtoys session','/api/xtoys/session/status'],['xtoys motion','/api/xtoys/motion/status']];
  try{
    const results = await Promise.all(probes.map(async ([n,p])=>{
      const ctrl = new AbortController(); const t = setTimeout(()=>ctrl.abort(), 3500);
      try{ const r = await fetch(API+p, {signal:ctrl.signal}); clearTimeout(t); const v = await r.json().catch(()=>({})); return {n,ok:true,v}; }
      catch(e){ clearTimeout(t); return {n,ok:false,e:e.name==='AbortError'?'timeout':e.message}; }
    }));
    cards.innerHTML = results.map(r=>{ const empty = !r.ok||!r.v||(typeof r.v==='object'&&Object.keys(r.v).length===0);
      const note = r.ok?JSON.stringify(r.v).slice(0,140):('ошибка: '+r.e);
      return `<div class="v4-tile"><h4>${v4Esc(r.n)}</h4><div>${v4Badge(empty?'warn':'ok', r.ok?(empty?'НЕТ ДАННЫХ':'есть данные'):'ОШИБКА')}</div><div class="v4-meta">${v4Esc(note)}</div></div>`; }).join('');
    v4SetBadge('v4-xt-cards','ok','XToys');
  }catch(e){ cards.innerHTML = `<div class="v4-tile">${v4Badge('err','ОШИБКА')} ${v4Esc(e.message)}</div>`; v4SetBadge('v4-xt-cards','err','ошибка'); }
}

// ── НАСТРОЙКИ ──────────────────────────────────────────────────
async function v4LoadSettings(){
  try{ const c = await v4Api('/api/config'); const lines = ['⚠ config.yaml с секретами не отдаётся (маскировка).','Показан sanitized /api/config:',''];
    const keys = c&&typeof c==='object'?Object.keys(c):[];
    if(!keys.length) lines.push('(пустой объект)');
    else for(const k of keys){ const v=c[k]; const sv=(v&&typeof v==='object')?JSON.stringify(v):String(v); lines.push(`${k}: ${sv}`); }
    if(v4$('v4-st-config')) v4$('v4-st-config').textContent = lines.join('\n');
  }catch(e){ if(v4$('v4-st-config')) v4$('v4-st-config').textContent='ОШИБКА: '+e.message; }
}

// ── диспетчер по имени вкладки ─────────────────────────────────
window.v4Load = function(name){
  switch(name){
    case 'overview': v4LoadOverview(); break;
    case 'agents': v4LoadAgents(); break;
    case 'logs': v4LoadLogs(); break;
    case 'tasks': v4LoadTasks(); break;
    case 'journal': v4LoadJournal(); break;
    case 'reports': v4LoadReports(); break;
    case 'tools': v4RenderTools(); break;
    case 'vision': v4LoadVision(); break;
    case 'autonomous': v4LoadAutonomous(); break;
    case 'xtoys': v4LoadXtoys(); break;
    case 'settings': v4LoadSettings(); break;
  }
};

// автообновление обзора
let _v4ov = null;
window.v4StartAuto = function(){ if(_v4ov) clearInterval(_v4ov); _v4ov = setInterval(()=>{ const a=document.querySelector('.view-wrap.active'); if(a&&a.id==='view-v4_overview') v4LoadOverview(); },30000); };

// привязка кнопок внутри v4-секций (refresh и т.п.)
document.addEventListener('DOMContentLoaded', ()=>{
  const bind = (id, fn)=>{ const el=v4$(id); if(el) el.addEventListener('click', fn); };
  bind('v4-ov-refresh', v4LoadOverview);
  bind('v4-ag-refresh', v4LoadAgents);
  bind('v4-lg-refresh', v4LoadLogs);
  bind('v4-tk-refresh', v4LoadTasks);
  bind('v4-jr-refresh', v4LoadJournal);
  bind('v4-rp-refresh', v4LoadReports);
  bind('v4-vs-refresh', v4LoadVision);
  bind('v4-au-refresh', v4LoadAutonomous);
  bind('v4-xt-refresh', v4LoadXtoys);
  bind('v4-au-start', async()=>{ v4Toast('▶ старт автономности…'); try{ await v4Post('/api/autonomous/start'); v4Toast('✅ отправлено'); v4LoadAutonomous(); }catch(e){ v4Toast('❌ '+e.message); } });
  bind('v4-au-stop', async()=>{ v4Toast('■ стоп…'); try{ await v4Post('/api/autonomous/stop'); v4Toast('✅ отправлено'); v4LoadAutonomous(); }catch(e){ v4Toast('❌ '+e.message); } });
  const ls = v4$('v4-lg-source'); if(ls) ls.addEventListener('change', v4LoadLogs);
  const ll = v4$('v4-lg-level'); if(ll) ll.addEventListener('change', v4LoadLogs);
  const ov = v4$('v4-ov-stop'); if(ov) ov.addEventListener('click', async()=>{ v4Toast('⏹ STOP…'); try{ await v4Post('/api/admin/stop'); v4Toast('✅ STOP.txt создан'); }catch(e){ try{ await v4Post('/api/stop'); v4Toast('✅ СТОП отправлен'); }catch(_){ v4Toast('❌ '+e.message); } } });
});

// экспорт для вызова из inline onclick в index.html
window.v4LoadOverview = v4LoadOverview;
window.v4LoadAgents = v4LoadAgents;
window.v4LoadLogs = v4LoadLogs;
window.v4LoadTasks = v4LoadTasks;
window.v4LoadJournal = v4LoadJournal;
window.v4LoadReports = v4LoadReports;
window.v4RenderTools = v4RenderTools;
window.v4LoadVision = v4LoadVision;
window.v4LoadAutonomous = v4LoadAutonomous;
window.v4LoadXtoys = v4LoadXtoys;
window.v4LoadSettings = v4LoadSettings;
})();
