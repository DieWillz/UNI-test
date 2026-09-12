'use strict';
/* UNI Admin · Unified (v3.3 + v4) · one JS file · all features, no stubs */
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const IS_LOCAL_ADMIN=['127.0.0.1','localhost','::1'].includes(location.hostname);
const API=/^https?:$/.test(location.protocol)?location.origin:'http://127.0.0.1:8787';
const H8K=IS_LOCAL_ADMIN?'http://127.0.0.1:8000':null;
const MOONS=IS_LOCAL_ADMIN?['http://127.0.0.1:7861','http://localhost:7861']:[];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const TO=(ms)=>AbortSignal.timeout(ms);
function toast(t){const d=document.createElement('div');d.className='tst';d.textContent=t;$('#toast').appendChild(d);setTimeout(()=>d.remove(),4000);}
async function api(p,o){try{return await fetch(API+p,{...((o?.method||'GET').toUpperCase()==='GET'?{signal:TO(8000)}:{}),...o});}catch(e){return null;}}
async function j(p,o){const r=await api(p,o);if(!r)return null;try{return await r.json();}catch(e){return null;}}
async function api8k(p,o){if(!H8K)return null;try{return await fetch(H8K+p,o);}catch(e){return null;}}
async function j8k(p,o){const r=await api8k(p,o);if(!r)return null;try{return await r.json();}catch(e){return null;}}
const PJ=o=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)});
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const kv=(k,v)=>'<div class="kv"><b>'+k+'</b><span>'+v+'</span></div>';
function copyVal(sel){const v=$(sel).value;if(v&&navigator.clipboard)navigator.clipboard.writeText(v).then(()=>toast('скопировано'));}
// Функция копирования в буфер обмена (для современных браузеров)
function copyToClipboard(inputId) {
  const input = document.getElementById(inputId);
  if (!input || !input.value) {
    toast("⚠ Сначала создайте сессию!");
    return;
  }
  input.select();
  try {
    navigator.clipboard.writeText(input.value)
      .then(() => toast("✅ Ссылка скопирована!"))
      .catch(() => toast("⚠ Не удалось скопировать (используйте Ctrl+C)"));
  } catch (e) {
    toast("⚠ Не поддерживается, используйте Ctrl+C");
  }
}
// === PATTERNS ===
// Группы паттернов (для каталога)
const PATGROUPS = [
  ["Базовые", ["ramp", "hold", "pulse", "wave", "climb", "cooldown"]],
  ["Ритмичные", ["sine_wave", "square_wave", "sawtooth", "triangle", "bounce"]],
  ["Случайные", ["random", "noise", "chaos", "flicker"]],
  ["Пользовательские", ["custom_1", "custom_2", "custom_3"]]
];

// Все доступные паттерны
function allPats() {
  return PATGROUPS.flatMap(group => group[1]);
}

// Метаданные паттерна (длительность, пик)
function curveMeta(name) {
  const c = window.CURVES?.[name];
  if (c) {
    const duration = Math.round(c.reduce((a, x) => a + x[0], 0) * 10) / 10;
    const peak = Math.round(Math.max(...c.map(x => x[1])) * 100);
    return { duration, peak };
  }
  return { duration: 20, peak: 100 };
}

// Рендеринг паттернов
function renderDorchPatterns() {
  const root = document.getElementById('patBtns');
  const sel = document.getElementById('plPat');
  if (!root || !window.PATGROUPS) return;

  const search = (document.getElementById('patSearch')?.value || '').toLowerCase();
  let html = '';
  let options = '<option value="">— выберите паттерн —</option>';

  for (const [group, names] of PATGROUPS) {
    const visible = names.filter(n => allPats().includes(n) && n.toLowerCase().includes(search));
    if (!visible.length) continue;

    html += '<div class="pattern-group">' + esc(group) + '</div>';
    for (const name of visible) {
      const m = curveMeta(name);
      html += `
        <button class="pattern-tile" data-pattern="${esc(name)}" onclick="dPattern('${name}')">
          <b>${esc(name.replaceAll('_', ' '))}</b>
          <small>${m.duration} сек · пик ${m.peak}%</small>
        </button>
      `;
      options += `<option value="${esc(name)}">${esc(name.replaceAll('_', ' '))}</option>`;
    }
  }

  root.innerHTML = html || '<div class="note">Паттерны не найдены</div>';
  if (sel) sel.innerHTML = options;
}

// Запуск паттерна
function dPattern(name) {
  patStop(true);
  Dorch.stopped = false;
  Dorch.source = 'pattern';
  const pow = Math.min(Dorch.limit, +$('#pPow').value || 70);
  const scale = Math.max(0.1, +$('#pScale').value || 1);

  // Подсветка активного паттерна
  $$('.pattern-tile').forEach(b => b.classList.toggle('on', b.dataset.pattern === name));

  Dorch.patAbort = new AbortController();
  runCurve(name, pow, scale, Dorch.patAbort.signal, async v => dSend(v, 'pattern'))
    .then(() => {
      patStop(true);
      dSend(0, 'pattern');
    });
}

// Остановка паттерна
function patStop(s) {
  Dorch.patAbort?.abort();
  Dorch.patAbort = null;
  $$('.pattern-tile').forEach(b => b.classList.remove('on'));
  if (!s) bpLog('паттерн стоп');
}

// Инициализация паттернов
renderDorchPatterns();
// Обновление статуса сессии
function updateRemoteStatus(status, isActive) {
  const statusBlock = document.getElementById("remoteStatusBlock");
  const statusDot = document.getElementById("remoteStatusDot");
  const statusText = document.getElementById("remoteStatusText");

  if (statusBlock) {
    statusBlock.style.display = "block";
    statusText.textContent = status;
    statusDot.style.background = isActive ? "var(--lime)" : "var(--mute)";
  }
}
/* ── навигация ── */
let ageCb=null;
$$('.nav[data-page]').forEach(b=>b.onclick=()=>{const p=b.dataset.page,t=b.dataset.tab;
  if(p==='dorch'&&!localStorage.getItem('dorch_ok')){ageCb=()=>go(p,t);$('#ageGate').classList.add('open');return;}
  go(p,t);});
function selectPageTab(page,tab){
  page.querySelectorAll('.tab[data-t]').forEach(x=>{const active=x.dataset.t===tab;x.classList.toggle('act',active);x.setAttribute('aria-pressed',String(active));});
  page.querySelectorAll('.pane[data-t]').forEach(x=>x.classList.toggle('act',x.dataset.t===tab));
}
$$('.tab[data-t]').forEach(b=>b.onclick=()=>{const page=b.closest('.page');if(!page)return;const t=b.dataset.t;selectPageTab(page,t);if(t==='logs'){buildLogs();LOGKEYS.forEach(loadLog);}});
function setNavigationOpen(open){document.body.classList.toggle('sb',open);$('#burger').setAttribute('aria-expanded',String(open));$('#navBackdrop').hidden=!open;}
function go(p,tab){const page=$$('.page').find(s=>s.dataset.page===p);if(!page)return;
  if(p==='transfer'&&!tab)tab='logs';
  if(p==='dorch'&&!localStorage.getItem('dorch_ok')){ageCb=()=>go(p,tab);$('#ageGate').classList.add('open');return;}
  const changed=!page.classList.contains('act');
  $$('.nav[data-page]').forEach(b=>{const act=b.dataset.page===p&&(!b.dataset.tab||b.dataset.tab===tab);b.classList.toggle('act',act);if(act)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  $$('.page').forEach(s=>s.classList.toggle('act',s.dataset.page===p));
  if(tab)selectPageTab(page,tab);
  const label=$$('.nav[data-page]').find(b=>b.dataset.page===p)?.childNodes[0]?.textContent?.trim()||p;
  $('#currentSection').textContent=label;document.title='Юни — '+label;
  (INIT[p]||(()=>{}))();if(innerWidth<=900)setNavigationOpen(false);
  if(changed)window.scrollTo({top:0,behavior:'instant'});
  const heading=page.querySelector('h1');if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});}}
$('#burger').onclick=()=>setNavigationOpen(!document.body.classList.contains('sb'));
$('#navBackdrop').onclick=()=>{setNavigationOpen(false);$('#burger').focus();};
$('#navSearch').addEventListener('input',event=>{
  const query=event.target.value.trim().toLocaleLowerCase('ru');let count=0;
  $$('#adminNavigation .nav').forEach(button=>{button.hidden=!(button.textContent+' '+(button.dataset.keywords||'')).toLocaleLowerCase('ru').includes(query);if(!button.hidden)count++;});
  $$('#adminNavigation .sec').forEach(section=>{let next=section.nextElementSibling,visible=false;while(next&&!next.classList.contains('sec')){if(next.classList.contains('nav')&&!next.hidden)visible=true;next=next.nextElementSibling;}section.hidden=!visible;});
  $('#navEmpty').hidden=count>0;
});
$('#navSearch').addEventListener('keydown',event=>{if(event.key==='Enter'){const match=$$('#adminNavigation .nav').find(button=>!button.hidden);if(match){event.preventDefault();match.click();}}});
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();$('#navSearch').focus();}});
function ageOk(){if(!$('#ageChk').checked){toast('нужно 18+');return;}localStorage.setItem('dorch_ok','1');$('#ageGate').classList.remove('open');if(ageCb)ageCb();}
function ageNo(){$('#ageGate').classList.remove('open');ageCb=null;}

/* ── честные пробы ── */
async function probeLLM(){
  if(!IS_LOCAL_ADMIN)return null;
  for(const port of [1235,1234]){
    try{const r=await fetch('http://127.0.0.1:'+port+'/v1/models',{signal:TO(1500)});
      if(r.ok){const d=await r.json().catch(()=>null);
        const m=d&&d.data&&d.data[0]&&(d.data[0].id||d.data[0].name);
        return{port,model:m||('порт '+port)};}}catch(e){}}
  return null;}
async function probeMoon(){
  if(!IS_LOCAL_ADMIN)return null;
  // Probe the supported paths in parallel with one shared deadline.
  const signal=TO(1500);
  const results=await Promise.all(MOONS.flatMap(M=>['/config','/gradio_api/config','/'].map(async p=>{
    try{const r=await fetch(M+p,{signal});return r.ok;}catch(e){return false;}
  })));
  return results.some(Boolean);}

/* ── статус ── */
let statusRefreshPending=false;
async function refreshStatus(){
  if(statusRefreshPending)return;statusRefreshPending=true;
  const refresh=$('#overviewRefresh');if(refresh){refresh.disabled=true;refresh.textContent='Обновляем…';}
  try{
  const readStatus=async path=>{const response=await api(path,{signal:TO(3000)});if(!response?.ok)return null;return response.json().catch(()=>null);};
  const [stack,hardware,git,llm,moon]=await Promise.all([readStatus('/api/admin/stack'),readStatus('/api/admin/hw'),readStatus('/api/admin/git'),probeLLM(),probeMoon()]);
  const d=stack&&typeof stack==='object'&&!Array.isArray(stack)?stack:{};
  const hw=hardware||{},gt=git||{};
  const received=Object.keys(d).length>0;
  $('#adminConnection').classList.toggle('offline',!received);
  $('#adminConnection .dot').className='dot '+(received?'ok':'bad');
  $('#adminConnectionText').textContent=received?'Сервер отвечает':'Нет данных сервера';
  $('#adminUpdated').textContent=received?'Обновлено '+new Date().toLocaleTimeString('ru-RU'):'Проверьте, запущен ли сервер Юни';
  // Header badges are optional in the unified layout; missing ones must not abort refresh.
  for(const [id,ok] of [['cLlm',llm],['cWeb',d.webui?.running],['cDesk',d.electron?.running],['cMoon',moon],['cBp',BP.ready]]){
    const badge=$('#'+id);if(badge)badge.className='dot '+(ok?'ok':'bad');}
  if($('#cLlmLabel'))$('#cLlmLabel').textContent='LLM :'+(llm?llm.port:'1235');
  if($('#cModel'))$('#cModel').textContent='LM: '+(llm?llm.model:(d.llama&&d.llama.model)||'—');
  renderOverview(d,hw,gt,llm);
  if($('#ctxStatus'))$('#ctxStatus').innerHTML=
    kv('LLM :'+(llm?llm.port:'1235'),llm?'✅ '+llm.model:'❌')+
    kv('WebUI :8787',(d.webui||{}).running?'✅':'❌')+
    kv('Desktop',(d.electron||{}).running?'✅':'❌')+
    kv('Moondream',moon?'✅':'❌');
  }catch(error){$('#adminConnectionText').textContent='Не удалось обновить данные';$('#adminConnection .dot').className='dot bad';$('#adminUpdated').textContent='Обновите статус или откройте логи';}
  finally{statusRefreshPending=false;if(refresh){refresh.disabled=false;refresh.textContent='Обновить статус';}}}
function renderOverview(d,hw,gt,llm){
  const pid=x=>(x&&typeof x==='object')?(x.pid??'—'):'—';
  const shown=v=>(v===0||v)?v:'—';
  const llmRunning=llm?true:(typeof d.llama?.running==='boolean'?d.llama.running:null);
  const llmPort=llm?.port||d.llama?.port||1235;
  const llmModel=llm?.model||d.llama?.model||'—';
  const card=(t,st,ex)=>'<div class="card"><h3>'+t+'<span class="tag '+(st===true?'':st===false?'amb':'g')+'">'+(st===true?'Доступен':st===false?'Не отвечает':'Нет данных')+'</span></h3>'+ex+'</div>';
  $('#ovStack').innerHTML=
    card('LLM :'+llmPort,llmRunning,kv('PID',pid(d.llama))+kv('модель',esc(llmModel)))+
    card('WebUI :8787',(d.webui||{}).running,kv('PID',pid(d.webui)))+
    card('Launcher',(d.launcher||{}).running,kv('PID',pid(d.launcher)))+
    card('Desktop',(d.electron||{}).running,kv('PID',pid(d.electron)));
  const g=hw.gpu||{};
  $('#ovHw').innerHTML=
    kv('GPU VRAM (своб.)',shown(g.vram_free))+
    kv('GPU VRAM (исп.)',shown(g.vram_used))+
    kv('GPU load',shown(g.utilization))+
    kv('RAM',shown(hw.ram))+kv('CPU',shown(hw.cpu));
  $('#hwTag').textContent=g.vram_free!=null&&g.vram_free!=='—'?'nvidia-smi':'нет данных GPU';
  $('#ovGit').innerHTML=kv('Ветка',gt.branch||'—')+kv('Коммит',gt.commit||'—')+kv('Сообщение',esc(gt.message||'—'))+kv('Время',gt.time||'—');
  $('#gitTag').textContent=gt.branch&&gt.branch!=='—'?'есть':'—';
  $('#ovRaw').textContent=JSON.stringify(d,null,1).slice(0,2000);}
async function stopAll(){dStop();const r=await api('/api/admin/stop',PJ({}));toast(r&&r.ok?'STOP отправлен':'STOP: сервер недоступен');}

/* ── участники ── */
async function loadParticipants(){
  const p=await j('/api/participants'),h=await j('/api/heartbeats'),ag=await j('/api/admin/agents');
  if(p){const list=Array.isArray(p)?p:(p.participants||[]);
    $('#ptList').innerHTML='<table>'+list.map(x=>'<tr><td>'+(x.name||x.id||x)+'</td><td>'+(x.status||x.role||'—')+'</td><td>'+(x.last_seen||x.ts||'')+'</td></tr>').join('')+'</table>';}
  else $('#ptList').textContent='⚠ /api/participants недоступен';
  const hObj=h&&(h.heartbeats||h);
  $('#ptBeats').innerHTML=hObj?(typeof hObj==='object'?'<pre class="log" style="height:320px">'+esc(JSON.stringify(hObj,null,1))+'</pre>':'<pre class="log" style="height:320px">'+esc(hObj)+'</pre>'):'<div class="note">нет данных heartbeat</div>';
  if(ag){const agents=ag.agents||[];const alive=agents.filter(a=>a.alive).length;
    $('#ptList').innerHTML+='<div class="note" style="margin-top:8px">Heartbeats ИИ: '+alive+' живых из '+agents.length+'</div>';
  }}
async function runRollCall(){
  toast('Обновляю heartbeats участников');
  return loadParticipants();
}

/* ── передача данных: QWN ── */
async function qwnSend(){const t=$('#qwnIn').value.trim();if(!t)return;$('#qwnIn').value='';
  const d=await j('/api/chat',PJ({message:t,text:t}));
  const reply=d&&(d.text||d.reply||d.response||d.message||'');
  $('#qwnLog').textContent+='[Вы] '+t+'\n[Юни] '+(reply||JSON.stringify(d||{}))+'\n\n';
  $('#qwnLog').scrollTop=$('#qwnLog').scrollHeight;}
async function qwnStatus(){const d=await j('/api/uni/status');$('#qwnStatus').innerHTML=kv('статус',d?'OK':'недоступен')+kv('эндпоинт','/api/chat');}

/* ── файловый мост 8000 ── */
let FB_ENDPOINT=null;
async function fbProbe(){const candidates=['/api/files','/api/file','/files','/bridge','/api/bridge','/api/fs'];
  if(!IS_LOCAL_ADMIN){FB_ENDPOINT=null;$('#fbOut').textContent='Порт 8000 не проверяется из удалённой админки: localhost относится к компьютеру посетителя.';$('#fbState').textContent='Нужен серверный proxy на стороне UNI; прямой loopback отключён.';return;}
  const out=[];
  for(const c of candidates){const r=await api8k(c);
    const alive=r&&r.status!==404&&r.status!==405;
    out.push((alive?'✓':'✗')+' '+c+' → '+(r?r.status:'net'));
    if(alive&&r.status===200)FB_ENDPOINT=c;}
  $('#fbOut').textContent=out.join('\n');
  $('#fbState').textContent=FB_ENDPOINT?('найден: '+FB_ENDPOINT):'ни один кандидат не ответил 200 (Hermes 8000, возможно, не поднят или API имеет другой путь)';}
async function fbExec(){const op=$('#fbOp').value,path=$('#fbPath').value,content=$('#fbContent').value,participant=$('#fbP').value;
  if(!FB_ENDPOINT)await fbProbe();
  if(!FB_ENDPOINT){$('#fbOut').textContent='⚠ нет живого эндпоинта 8000 (нажми «Проверить сервер 8000»)';return;}
  const r=await api8k(FB_ENDPOINT,PJ({op,path,content,participant}));
  if(!r){$('#fbOut').textContent='⚠ net err';return;}
  $('#fbOut').textContent='HTTP '+r.status+'\n\n'+(await r.text()).slice(0,4000);}

/* ── логи: grid, filter, highlight, download ── */
const LOGKEYS=['llama','webui','desktop','electron','llama.err','webui.err','uni_bat','server'];
const LOGDATA={},LOGERROR={},LOGPENDING=new Set();let logLevel='ALL';
function buildLogs(){const g=$('#logsGrid');if(g.children.length)return;
  g.innerHTML=LOGKEYS.map(k=>'<div class="card"><h3>'+k+'<span class="tag g" id="lg_'+k+'">—</span><button class="btn ghost" style="margin-left:4px;padding:3px 8px" onclick="dlLog(\''+k+'\')">⬇</button></h3><pre class="log" id="log_'+k+'"></pre></div>').join('');}
function logText(d){if(!d)return '⚠ эндпоинт недоступен';
  if(typeof d==='string')return d;
  if(typeof d.log==='string')return d.log;
  if(typeof d.text==='string')return d.text;
  const arr=d.lines||d.items||d.data;
  if(Array.isArray(arr))return arr.map(x=>typeof x==='string'?x:(x.t||x.line||x.text||x.msg||x.message||x.content||JSON.stringify(x))).join('\n');
  return JSON.stringify(d,null,1);}
function fmtLine(l){const e=esc(l);
  if(/ERROR|CRITICAL|Traceback|Exception/i.test(l))return '<span class="err">'+e+'</span>';
  if(/WARN/i.test(l))return '<span class="wrn">'+e+'</span>';
  if(/INFO/i.test(l))return '<span class="inf">'+e+'</span>';return e;}
function renderLog(k){const arr=LOGDATA[k]||[];
  const f=logLevel==='ALL'?arr:arr.filter(l=>logLevel==='ERROR'?/ERROR|CRITICAL|Traceback|Exception/i.test(l):logLevel==='WARN'?/WARN/i.test(l):/INFO/i.test(l));
  const el=document.getElementById('log_'+k);if(el){const follow=el.scrollHeight-el.scrollTop-el.clientHeight<40;el.innerHTML=LOGERROR[k]?esc(LOGERROR[k]):f.length?f.map(fmtLine).join('\n'):'Нет строк для выбранного фильтра.';if(follow)el.scrollTop=el.scrollHeight;}}
function setLogLevel(v){logLevel=v;LOGKEYS.forEach(renderLog);}
function dlLog(k){const blob=new Blob([(LOGDATA[k]||[]).join('\n')],{type:'text/plain'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='uni_'+k+'.log';a.click();}
function countErrors(){let n=0;for(const k of LOGKEYS)(LOGDATA[k]||[]).forEach(l=>{if(/ERROR|CRITICAL|Traceback/i.test(l))n++;});
  const b=$('#logBadge');if(b){b.style.display=n?'':'none';b.textContent=n;}
  const unavailable=LOGKEYS.filter(k=>LOGERROR[k]||!Object.hasOwn(LOGDATA,k)).length;
  $('#logSummary').textContent=(n?('Строк с ошибками: '+n):'В загруженных строках ошибок нет')+(unavailable?' · журналов без данных: '+unavailable:'');}
async function loadLog(k){
  if(LOGPENDING.has(k))return;LOGPENDING.add(k);
  try{
    const response=await api('/api/uni/logs?name='+encodeURIComponent(k)+'&tail=200');
    if(!response?.ok)throw new Error(response?'HTTP '+response.status:'Нет связи с сервером');
    const data=await response.json();if(data.error)throw new Error(data.error);
    LOGDATA[k]=logText(data).split('\n');delete LOGERROR[k];
    const t=document.getElementById('lg_'+k);if(t)t.textContent=new Date().toLocaleTimeString('ru-RU');
  }catch(error){LOGERROR[k]='Журнал недоступен: '+error.message;const t=document.getElementById('lg_'+k);if(t)t.textContent='Нет данных';}
  finally{LOGPENDING.delete(k);renderLog(k);countErrors();}}
setInterval(()=>{if(!document.hidden&&$('.page[data-page="transfer"]').classList.contains('act')&&$('.pane[data-t="logs"]').classList.contains('act'))LOGKEYS.forEach(loadLog);},5000);

/* ── браузер ── */
async function browserProbe(){
  $('#browserLog').textContent='Проверяю /api/browser/status…';
  const api1=await j('/api/browser/status').catch(()=>null);
  let cdpText='не проверяется из удалённой админки (нужен backend proxy)';
  if(IS_LOCAL_ADMIN){const cdp=await fetch('http://127.0.0.1:9222/json/version',{signal:TO(1500)}).catch(()=>null);cdpText=cdp?(cdp.ok?'доступен':'HTTP '+cdp.status):'недоступен';}
  $('#browserLog').textContent='CDP 9222: '+cdpText+'\n/api/browser/status: '+(api1?JSON.stringify(api1,null,1):'нет ответа')+'\n\nОсновной статус браузера идёт через origin админки; прямой CDP доступен только локально.';}
async function browserTabs(){
  if(!IS_LOCAL_ADMIN){$('#browserLog').textContent+='\nПрямой CDP не читается удалённо без серверного proxy.';return;}
  const r=await fetch('http://127.0.0.1:9222/json/list',{signal:TO(1500)}).catch(()=>null);
  if(!r){$('#browserLog').textContent+='⚠ CDP не отвечает\n';return;}
  const list=await r.json().catch(()=>[]);
  $('#browserLog').textContent+='вкладки:\n'+list.map(x=>'• '+x.title+'  '+(x.url||'')).join('\n')+'\n';}
async function browserDemo(){const d=await j('/api/admin/actions',PJ({action:'demo_mouse',params:{}}));
  $('#browserLog').textContent+='demo_mouse: '+(d?JSON.stringify(d):'недоступно')+'\n';}

/* ── DORCH ── */
const Dorch={limit:+(localStorage.getItem('dorch_limit')||65),stopped:true,source:'manual',current:0,
  motionTimer:null,patTimer:null,pl:[],prev:null,smooth:0,auto:false};
function bpLog(t){const el=$('#dLog');el.textContent+='['+new Date().toLocaleTimeString().slice(0,8)+'] '+t+'\n';el.scrollTop=el.scrollHeight;}
function dUi(){$('#dIntVal').textContent=(Dorch.current*100).toFixed(1)+'%';$('#dIntBar').style.width=(Dorch.current*100)+'%';
  $('#dSrc').textContent=Dorch.stopped?'STOP':Dorch.source;}
async function dSend(v,src){v=Math.max(0,Math.min(1,v));
  const val=Dorch.stopped?0:Math.min(v,Dorch.limit/100);
  Dorch.current=val;if(src)Dorch.source=src;dUi();
  if(BP.ready&&BP.devices.length){BP.cmd(val);}
  else{const r=await api('/api/xtoys/intensity',PJ({intensity:val}));if(!r||r.status===404)$('#dCtl').textContent='Intiface offline / нет эндпоинта';}}
function dStop(){Dorch.stopped=true;motionStop(true);plStop(true);BP.stop();dSend(0);Dorch.auto=false;$('#dAutoTag').textContent='выкл';bpLog('■ АВАРИЙНЫЙ СТОП');toast('■ Dorch: стоп');}
function dSaveLimit(){Dorch.limit=Math.max(0,Math.min(100,+$('#dLimit').value||0));localStorage.setItem('dorch_limit',Dorch.limit);api('/api/xtoys/limit',PJ({max_intensity:Dorch.limit}));bpLog('лимит '+Dorch.limit+'%');dUi();}
function dManual(v){$('#dManVal').textContent=v+'%';if(!Dorch.stopped&&!Dorch.motionTimer&&!Dorch.patTimer&&!Dorch.auto)dSend(v/100,'manual');}
function dAutoToggle(){Dorch.auto=!Dorch.auto;$('#dAutoTag').textContent=Dorch.auto?'вкл':'выкл';if(Dorch.auto){Dorch.stopped=false;motionStart(true);}else motionStop(true);bpLog('авто: '+(Dorch.auto?'вкл':'выкл'));}
const PATTERNS={ramp:t=>t,climb:t=>Math.floor(t*5)/5,pulse:t=>(t%0.5<0.25?1:0.15),wave:t=>0.5+0.5*Math.sin(t*Math.PI*2-Math.PI/2),hold:()=>1,cooldown:t=>1-t};
function patStop(s){if(Dorch.patTimer){clearInterval(Dorch.patTimer);Dorch.patTimer=null;}$$('#patBtns .patbtn').forEach(b=>b.classList.remove('on'));if(!s)bpLog('паттерн стоп');}
function dPattern(name){patStop(true);Dorch.stopped=false;Dorch.source='pattern';
  const secs=Math.max(1,+$('#pSecs').value||20),pow=(+$('#pPow').value||70)/100;
  const btn=$$('#patBtns .patbtn').find(b=>b.textContent.toLowerCase().startsWith(name.slice(0,4)));if(btn)btn.classList.add('on');
  const t0=Date.now();bpLog('паттерн '+name+' '+secs+'с');
  Dorch.patTimer=setInterval(()=>{const t=(Date.now()-t0)/1000/secs;
    if(t>=1){patStop();dSend(0,'pattern');return;}
    let v=PATTERNS[name](t)*pow;if(Dorch.auto)v*=(0.7+0.3*Math.sin(Date.now()/900));
    dSend(v,'pattern');},120);}
function plAdd(){Dorch.pl.push({p:$('#plPat').value,s:+$('#plSec').value||20,w:+$('#plPow').value||70});plRender();}
function plRender(){$('#plCount').textContent=Dorch.pl.length;
  $('#plList').innerHTML=Dorch.pl.length?Dorch.pl.map((x,i)=>(i+1)+'. '+x.p+' '+x.s+'с '+x.w+'%').join('<br>'):'пуст';}
async function plRun(){if(!Dorch.pl.length){toast('плейлист пуст');return;}plStop(true);Dorch.stopped=false;
  for(let i=0;i<Dorch.pl.length;i++){await new Promise(res=>{patStop(true);const t0=Date.now(),x=Dorch.pl[i];
    Dorch.patTimer=setInterval(()=>{const t=(Date.now()-t0)/1000/x.s;if(t>=1){patStop(true);res();return;}dSend(PATTERNS[x.p](t)*x.w/100,'pattern');},120);});}
  dSend(0);bpLog('плейлист завершён');}
function plStop(s){patStop(true);if(!s)bpLog('плейлист стоп');}
function motionMetric(){const d=Screen.region(+$('#mX').value,+$('#mY').value,+$('#mW').value,+$('#mH').value,48);
  if(!d)return null;if(!Dorch.prev||Dorch.prev.length!==d.length){Dorch.prev=d;return 0;}
  let s=0;for(let i=0;i<d.length;i+=16)s+=Math.abs(d[i]-Dorch.prev[i]);Dorch.prev=d;return (s/(d.length/16))/255;}
function motionStop(s){if(Dorch.motionTimer){clearInterval(Dorch.motionTimer);Dorch.motionTimer=null;}$('#mTag').textContent='выкл';$('#mTag').className='tag g';if(!s)bpLog('motion стоп');}
async function motionStart(s){if($('#mSource').value==='screen'&&!Screen.track){if(!(await Screen.enable())){motionStop();return;}}
  motionStop(true);Dorch.stopped=false;Dorch.source='motion';$('#mTag').textContent='вкл';$('#mTag').className='tag';
  const int=Math.max(40,+$('#mInt').value||140);if(!s)bpLog('motion старт');
  Dorch.motionTimer=setInterval(()=>{const m=motionMetric();if(m===null)return;
    const thr=(+$('#mThr').value||2.6)/100,gain=(+$('#mGain').value||10),gam=(+$('#mGam').value||3.7)||1,sm=Math.min(0.99,+$('#mSm').value||0.95),max=(+$('#mMax').value||70)/100;
    let x=Math.max(0,m-thr)*gain;x=Math.pow(Math.min(1,x),1/gam);
    Dorch.smooth=Dorch.smooth*sm+x*(1-sm);
    let v=Math.min(Dorch.smooth,max);if(Dorch.auto)v*=(0.75+0.25*Math.sin(Date.now()/800));
    $('#mCur').textContent=(v*100).toFixed(1)+'%';dSend(v,'motion');},int);}

/* Buttplug с фолбэк-хендшейком (объект → массив → v2) */
const BP={ws:null,wrap:m=>m,ready:false,devices:[],id:10,
 connect(){return new Promise((res,rej)=>{
  if(this.ws&&this.ws.readyState===1)return res(true);
  const url=$('#bpUrl').value||'ws://127.0.0.1:12345';
  let ws;try{ws=new WebSocket(url);}catch(e){return rej(e);}
  const to=setTimeout(()=>{ws.close();rej(new Error('таймаут — Intiface не запущен?'));},9000);
  let got=false,stage=0;
  const hs=()=>({RequestServerInfo:{Id:this.id++,ClientName:'UNI Admin',MessageVersion:3}});
  $('#bpDiag').textContent='WS open → хендшейк (массив v3)';
  ws.onopen=()=>ws.send(JSON.stringify([hs()]));
  const retry=()=>{if(got||ws.readyState!==1)return;stage++;
    if(stage===1){$('#bpDiag').textContent='нет ответа → пробую объект';ws.send(JSON.stringify(hs()));}
    else if(stage===2){$('#bpDiag').textContent='пробую массив v2';ws.send(JSON.stringify([{RequestServerInfo:{Id:this.id++,ClientName:'UNI Admin',MessageVersion:2}}]));}
    else{$('#bpDiag').textContent='хендшейк не прошёл (см. лог Intiface)';}};
  setTimeout(retry,2500);setTimeout(retry,5000);setTimeout(retry,7000);
  ws.onmessage=e=>{let m;try{m=JSON.parse(e.data);}catch(err){return;}
    const arr=Array.isArray(m)?m[0]:m;
    if(arr&&arr.ServerInfo){got=true;this.wrap=Array.isArray(m)?x=>[x]:x=>x;this.ready=true;
      $('#bpDiag').textContent='ServerInfo spec v'+arr.ServerInfo.MessageVersion+' · форма: '+(Array.isArray(m)?'массив':'объект');
      bpLog('Intiface handshake ok (spec v'+arr.ServerInfo.MessageVersion+')');
      this.send({RequestDeviceList:{Id:this.id++}});}
    if(arr&&arr.DeviceList){this.devices=arr.DeviceList.Devices||[];clearTimeout(to);bpRender();res(true);}};
  ws.onerror=()=>{clearTimeout(to);rej(new Error('WS ошибка'));};
  ws.onclose=()=>{this.ws=null;this.ready=false;bpState('отключено');};
  this.ws=ws;});},
 send(m){if(this.ws&&this.ws.readyState===1)this.ws.send(JSON.stringify(this.wrap(m)));},
 cmd(val){const di=+($('#bpDevSel').value||0),d=this.devices[di],ms=(d&&d.DeviceMessages)||[];
  if(ms.includes('RotateCmd'))this.send({RotateCmd:{Id:this.id++,DeviceIndex:di,Rotators:[{Index:0,Speed:val,Clockwise:true}]}});
  if(ms.includes('VibrateCmd'))this.send({VibrateCmd:{Id:this.id++,DeviceIndex:di,Vibrators:[{Index:0,Speed:val}]}});
  if(!ms.length){this.send({VibrateCmd:{Id:this.id++,DeviceIndex:di,Vibrators:[{Index:0,Speed:val}]}});
    this.send({RotateCmd:{Id:this.id++,DeviceIndex:di,Rotators:[{Index:0,Speed:val,Clockwise:true}]}});}},
 stop(){this.send({StopAllDevices:{Id:this.id++}});}};
async function bpConnect(){try{await BP.connect();bpState('подключено');$('#dBpDot').className='dot ok';$('#dBpTxt').textContent='Intiface: ok';}
  catch(e){bpState('ошибка: '+e.message);$('#dBpDot').className='dot bad';bpLog('Intiface: '+e.message);}refreshStatus();}
function bpDisconnect(){if(BP.ws)BP.ws.close();bpState('отключено');}
function bpScan(){BP.send({StartScanning:{Id:BP.id++}});setTimeout(()=>BP.send({RequestDeviceList:{Id:BP.id++}}),1500);setTimeout(bpRender,1700);}
function bpState(t){$('#bpState').textContent=t;$('#dDevState').textContent=t;}
function bpRender(){bpState(BP.ws&&BP.ws.readyState===1?'подключено':'отключено');
  $('#bpDevSel').innerHTML=BP.devices.map((d,i)=>'<option value="'+i+'">'+esc(d.DeviceName||('dev '+i))+'</option>').join('');
  $('#dDevName').textContent=BP.devices.length?BP.devices.map(d=>d.DeviceName).join(', '):'—';
  $('#dBpTxt').textContent='Intiface: '+(BP.devices.length?BP.devices.length+' устр.':'ok');
  const d=BP.devices[+($('#bpDevSel').value||0)];
  $('#bpFeats').textContent=d?('команды: '+((d.DeviceMessages||[]).join(', ')||'—')):'нет устройств';}
function bpApplyOsc(){Dorch.stopped=false;dSend((+$('#bpOsc').value)/100,'manual');bpLog('oscillate '+$('#bpOsc').value+'%');}

/* discovery xtoys */
let XT={};
async function xtDiscover(){
  const list=[['POST','/api/xtoys/remote/start'],['POST','/api/xtoys/remote/create'],['POST','/api/xtoys/remote/control'],['POST','/api/xtoys/remote/stop'],['GET','/api/xtoys/status'],['POST','/api/xtoys/public/open'],['POST','/api/xtoys/public/close'],['POST','/api/xtoys/stream/start'],['POST','/api/xtoys/stream/stop'],['POST','/api/xtoys/message'],['POST','/api/xtoys/limit'],['POST','/api/xtoys/intensity']];
  XT={};const rows=[];
  for(const[m,p]of list){const r=await api(p,m==='POST'?PJ({}):undefined);
    const alive=r&&r.status!==404&&r.status!==405;
    if(alive)XT[p]=1;rows.push((alive?'✓':'✗')+' '+p+' → '+(r?r.status:'net'));}
  $('#xtMap').textContent=rows.join('\n');
  const n=Object.keys(XT).length;bpLog('xtoys discovery: '+n+' живых');}
async function xtCall(paths,body){for(const p of paths)if(XT[p]){const r=await api(p,PJ(body));if(r)return r;}return null;}
async function remoteCreate(){const r=await xtCall(['/api/xtoys/remote/start','/api/xtoys/remote/create'],{max_intensity:+$('#rMax').value,minutes:+$('#rMin').value});
  const d=r?await r.json().catch(()=>null):null;
  if(d&&(d.url||d.link||d.token)){$('#rLink').value=d.url||d.link||(location.origin+'/remote#'+d.token);$('#rTag').textContent='активна';$('#dSes').textContent='активна';bpLog('remote создана');}
  else{$('#rTag').textContent='нет эндпоинта';bpLog('remote: живого эндпоинта нет');}}
async function remoteEnd(){await xtCall(['/api/xtoys/remote/stop'],{});$('#rTag').textContent='выкл';$('#dSes').textContent='выкл';}
async function remotePublic(open){
  const r=await j(open?'/api/xtoys/remote/public/start':'/api/xtoys/remote/public/stop',PJ({}));
  const d=r?await r.json().catch(()=>null):null;
  if(d){
    if(d.cloudflare_url)$('#rPub').value=d.cloudflare_url;
    if(d.ngrok_url)$('#rNgrok').value=d.ngrok_url;
    if(d.errors&&Object.keys(d.errors).length){
      const e=Object.entries(d.errors).map(([k,v])=>k+': '+v).join(' | ');
      bpLog('public: '+e);$('#rPubNote').textContent=e;
    } else if(open){$('#rPubNote').textContent='оба туннеля подняты';}
  }}
async function streamToggle(on){const r=await xtCall([on?'/api/xtoys/stream/start':'/api/xtoys/stream/stop'],{});$('#stTag').textContent=(r&&r.ok)?(on?'вкл':'выкл'):'нет эндпоинта';}
async function streamMsg(){const r=await xtCall(['/api/xtoys/message'],{text:$('#stMsg').value});bpLog('сообщение: '+(r?r.status:'нет'));}
async function camStart(){const d=await j('/api/camera/start',PJ({}));$('#camState')&&($('#camState').textContent=d&&d.ok?'включена':'backend: '+(d?d.status||'':'нет'));camFrame();}
async function camFrame(){const d=await j('/api/vision/capture',PJ({}));if(d&&d.image_b64)$('#camShot').src=d.image_b64;}
async function camStop(){await api('/api/camera/stop',PJ({}));}
document.addEventListener('keydown',e=>{if(e.key==='Escape')dStop();});

/* ── настройки ── */
async function loadSettings(){
  // DEPRECATED 2026-08-28: filling options without current/readback left a false role.
  // const roles=await j('/api/roles'); roleSel.innerHTML=options;
  try{await ChatControls.loadRoles();}catch(e){toast('Роли недоступны: '+e.message);}
  const eng=await j('/api/tts/engines');let vo='';(eng&&eng.engines||[]).forEach(e=>(e.voices||[]).forEach(v=>{vo+='<option value="'+v.id+'">'+e.id+' / '+esc(v.label||v.name||v.id)+'</option>';}));
  if($('#setVoice'))$('#setVoice').innerHTML=vo||'<option>default</option>';
  if($('#ttsVoice'))$('#ttsVoice').innerHTML=vo||'<option value="ru_RU-irina-medium.onnx">Piper Irina</option>';
  loadTtsVoices();
  const cfg=await j('/api/config');if(cfg&&cfg.llm){$('#provLM').value=cfg.llm.base_url||$('#provLM').value;}
  /* интеграции */
  const intList=[['LM Studio',()=>probeLLM().then(x=>!!x)],['WebUI 8787',()=>api('').then(x=>!!x)],['Hermes 8000',()=>api8k('/').then(x=>!!x)],['Intiface',()=>BP.ws&&BP.ws.readyState===1]];
  let html='';for(const[name,chk]of intList){const ok=await Promise.resolve(chk());html+=kv(name,ok?'✅':'❌');}
  $('#intStatus').innerHTML=html;}
async function saveSettings(){await applyRole($('#setRole').value);}
async function loadTtsVoices(){
  const p=$('#ttsProvider')?.value||'silero'; const d=await j('/api/tts/engines');
  const voices=(d?.engines||[]).find(x=>x.id===p)?.voices||[];
  const el=$('#ttsVoice'); if(!el)return;
  el.innerHTML=(voices.length?voices.map(v=>'<option value="'+esc(v.id)+'">'+esc(v.label||v.name||v.id)+'</option>').join(''):'<option value="ru_RU-irina-medium.onnx">Piper Irina</option>');
  const saved=JSON.parse(localStorage.getItem('uni_tts')||'{}'); if(saved.voice)el.value=saved.voice;
}
async function saveTtsSettings(){
  const data={provider:$('#ttsProvider').value,voice:$('#ttsVoice').value,endpoint:$('#ttsEndpoint').value.trim(),rate:+$('#ttsRate').value,pitch:+$('#ttsPitch').value,volume:+$('#ttsVolume').value,testText:$('#ttsTestText').value};
  localStorage.setItem('uni_tts',JSON.stringify(data)); toast('TTS настройки сохранены');
}
async function testTtsSettings(){await saveTtsSettings(); const d=JSON.parse(localStorage.getItem('uni_tts')||'{}');
  const r=await api('/api/tts',PJ({provider:d.provider,voice:d.voice,endpoint:d.endpoint,rate:d.rate,pitch:d.pitch,volume:d.volume,text:d.testText}));
  if(!r||!r.ok){toast('TTS не проверен: HTTP '+(r?.status||'нет ответа'));return;}
  const body=await r.json(); if(body.audio_url){const a=new Audio(new URL(body.audio_url,location.href).href); await a.play(); toast('TTS VERIFIED');} else toast('TTS not_verified: нет audio_url');
}
async function checkProviders(){
  const lm=await probeLLM();const h=await api8k('/');const o=$('#provOR').value?await fetch('https://openrouter.ai/api/v1/models',{headers:{'Authorization':'Bearer '+$('#provOR').value}}).catch(()=>null):null;
  toast('LM: '+(lm?'ok :'+lm.port:'нет')+' | Hermes: '+(h?'ok':'нет')+' | OpenRouter: '+(o&&o.ok?'ok':'нет'));}

/* ── задачи ── */
async function loadTasks(){const d=await j('/api/admin/dev');
  if(!d){$('#blBody').textContent='⚠ /api/admin/dev недоступен';return;}
  const bl=d.backlog||[];
  $('#blBody').innerHTML='<table>'+bl.slice(0,40).map(x=>'<tr><td><span class="tag '+(x.status==='DONE'?'':'amb')+'">'+x.status+'</span></td><td>'+esc(x.raw)+'</td></tr>').join('')+'</table>';
  const ph=d.phases||[];
  $('#phBody').innerHTML='<table>'+ph.map(x=>'<tr><td>'+(x.name||x.id||'—')+'</td><td>'+(x.status||'—')+'</td><td>'+(x.note||'')+'</td></tr>').join('')+'</table>'||'<div class="note">нет фаз</div>';
  $('#locksBody').textContent=JSON.stringify(d.locks||{},null,1);}

/* ── консенсус ── */
async function loadConsensus(){
  const r=await j('/api/council/rounds')||await j('/api/admin/journal');
  if(r){$('#csBody').textContent=JSON.stringify(r,null,1);$('#csState').textContent='OK';}
  else{$('#csBody').textContent='— раундов нет (council не запускался) —';$('#csState').textContent='нет данных';}}

/* ── документы ── */
async function loadDocs(){const d=await j('/api/admin/reports');
  if(!d||!d.reports){$('#docsList').innerHTML='<div class="note">⚠ /api/admin/reports недоступен</div>';return;}
  const list=$('#docsList');list.replaceChildren();
  if(!d.reports.length){list.textContent='Документов пока нет.';return;}
  for(const report of d.reports){const button=document.createElement('button');button.className='card document-link';button.type='button';button.textContent=report.name;button.addEventListener('click',()=>loadDoc(report.name));list.appendChild(button);}}
async function loadDoc(name){$('#docName').textContent=name;
  const d=await j('/api/admin/reports/'+encodeURIComponent(name));
  if($('#docName').textContent!==name)return;
  $('#docBody').textContent=d?.error?'Не удалось открыть документ: '+d.error:d?.content??'Документ пуст или недоступен.';}

/* ── статистика ── */
async function loadStats(){const d=await j('/api/admin/stats');
  if(d){const u=d.ui_events_by_component||{};
    $('#stUi').innerHTML='<table>'+Object.keys(u).map(k=>'<tr><td>'+esc(k)+'</td><td><b>'+u[k]+'</b></td></tr>').join('')+'</table>'||'<div class="note">нет событий</div>';
    $('#stCount').innerHTML=kv('stop_count',d.stop_count)+kv('demo_mouse',d.demo_mouse_count)+kv('vision_capture',d.vision_capture_count)+kv('chat_messages',d.chat_messages);
    $('#stPy').textContent=typeof d.pytest==='string'?d.pytest:JSON.stringify(d.pytest,null,1);}
  const s8=await api8k('/stats').then(r=>r?r.text().catch(()=>''):null).catch(()=>null);
  $('#st8k').textContent=s8||'— сервер 8000 не отвечает /stats —';}

/* ── расписания ── */
async function loadSchedules(){const d=await j('/api/uni/logs?name=uni-qwen%2Fdispatcher.log&tail=100')||await j('/api/admin/logs/dispatcher');
  $('#schLog').textContent=d?logText(d):'dispatcher.log не найден / не ведётся';}

/* ── правила (localStorage) ── */
function ruleLoad(){try{return JSON.parse(localStorage.getItem('uni_rules')||'[]');}catch(e){return [];}}
function ruleRender(){const r=ruleLoad();const el=$('#rulesList');
  el.innerHTML=r.length?r.map((x,i)=>'<div class="rule" contenteditable="true" data-i="'+i+'">'+esc(x)+'</div>').join(''):'<div class="note">нет правил — нажми ＋ Добавить</div>';
  el.querySelectorAll('.rule').forEach(d=>d.addEventListener('blur',()=>{const i=+d.dataset.i;const r=ruleLoad();r[i]=d.textContent.trim();localStorage.setItem('uni_rules',JSON.stringify(r));}));}
function ruleAdd(){const r=ruleLoad();r.push('Новое правило');localStorage.setItem('uni_rules',JSON.stringify(r));ruleRender();}
function ruleSave(){const r=[];$$('.rule').forEach(d=>r.push(d.textContent.trim()));localStorage.setItem('uni_rules',JSON.stringify(r));toast('сохранено');}

/* ── компьютер ── */
function feedAdd(t){const el=$('#compFeed');el.textContent+='['+new Date().toLocaleTimeString().slice(0,8)+'] '+t+'\n';el.scrollTop=el.scrollHeight;}
async function runGoal(){const goal=$('#goal').value.trim();if(!goal)return;
  if($('#compState').getAttribute('aria-busy')==='true')return;
  $('#compState').setAttribute('aria-busy','true');
  try{
  feedAdd('▶ цель: '+goal);$('#compState').textContent='работает';$('#compState').className='tag amb';
  const d=await j('/api/computer/act',PJ({goal}));
  feedAdd(d?(d.message||d.status||JSON.stringify(d)):'⚠ /api/computer/act недоступен');
  await sleep(2500);const after=Screen.frame(720);if(after){$('#afterShot').src=after;$('#afterShot').style.display='block';}
  if($('#verifyChk').checked&&after){try{feedAdd('Визуальный комментарий (не решение проверяющего): '+String(await gradioAsk(after,'Цель: '+goal+'. Что изменилось на экране?')));}
    catch(e){feedAdd('Визуальный анализ недоступен: '+e.message);}}
  }catch(error){feedAdd('Ошибка выполнения: '+error.message);}
  finally{
    // A returned tool call or model narration is not independent verification.
    $('#compState').textContent='Не подтверждено (not_verified)';$('#compState').className='tag amb';
    $('#compState').setAttribute('aria-busy','false');
  }}
(function(){try{const es=new EventSource(API+'/api/uni/events');
  es.onopen=()=>{$('#sseState').textContent='SSE подключено';};
  es.onmessage=e=>{try{const ev=JSON.parse(e.data);feedAdd('⚡ '+(ev.type||'')+': '+(ev.text||ev.message||''));ChatControls.onEvent(ev);}catch(err){}};
  es.onerror=()=>{$('#sseState').textContent='SSE: переподключение…';};}catch(e){}})();

/* ── чат ── */
let msgs=[];
function addMsg(role,text,image){msgs.push({role,text,image,t:new Date().toLocaleTimeString().slice(0,5)});renderMsgs();}
function renderMsgs(){const html=msgs.map(m=>'<div class="msg '+m.role+'"><small>'+(m.role==='user'?'Вы':m.role==='uni'?'ЮНИ':'система')+' · '+m.t+'</small>'+esc(m.text)+(m.image&&/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(m.image)?'<br><img alt="Отправленное изображение" src="'+m.image+'" style="max-width:100%;max-height:220px">':'')+'</div>').join('');
  const empty='<div class="chat-empty"><b>С чего начнём?</b><p>Напишите задачу или вопрос Юни. Ответ и состояние запроса появятся здесь.</p></div>';
  const b=$('#chatBox');if(b){b.innerHTML=html||empty;b.scrollTop=b.scrollHeight;}const d=$('#dwLog');if(d){d.innerHTML=html||empty;d.scrollTop=d.scrollHeight;}}
function clearChat(){msgs=[];renderMsgs();}
// DEPRECATED 2026-08-28: j('/api/chat') ignored HTTP errors; speak() duplicated backend TTS.
async function sendChat(text){return ChatControls.send(text);}
async function sendFromInput(){const text=$('#chatIn').value;if(await sendChat(text)&&$('#chatIn').value===text)$('#chatIn').value='';}
async function dwSend(){const text=$('#dwIn').value;if(await sendChat(text)&&$('#dwIn').value===text)$('#dwIn').value='';}
function toggleDrawer(){const open=$('#drawer').classList.toggle('open');$('#chatFab').setAttribute('aria-expanded',String(open));if(open)$('#dwIn').focus();else $('#chatFab').focus();}
// DEPRECATED: api('/api/tts',PJ({text:t})); // response audio_url was never played.
function speak(t){return ChatControls.playSpeech(t);}
function speakTest(){speak('Привет! Это Юни. Проверка голоса.');}
$('#chatIn').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendFromInput();}});
$('#dwIn').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();dwSend();}});
// Microphone input is owned by ChatControls and local /api/stt/listen.
const Screen={track:null,video:null,timer:null,_rc:null,
 async enable(){if(this.track)return true;
  try{const st=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:4}});
   this.track=st.getVideoTracks()[0];this.video=document.createElement('video');this.video.muted=true;this.video.srcObject=st;await this.video.play();
   this.track.onended=()=>this.disable();
   this.timer=setInterval(()=>{const f=this.frame(760);if(f)['#ctxShot','#vShot'].forEach(s=>{const i=$(s);if(i){i.src=f;i.style.display='block';}});},3000);
   $('#scrTag')&&($('#scrTag').textContent='вкл');$('#scrTag')&&($('#scrTag').className='tag');$('#vScrTag')&&($('#vScrTag').textContent='вкл');$('#vScrTag')&&($('#vScrTag').className='tag');return true;
  }catch(e){toast('экран: '+e.message);return false;}},
 frame(w){if(!this.track||this.track.readyState!=='live')return null;
  const v=this.video,c=document.createElement('canvas');const sc=w/(v.videoWidth||w);c.width=w;c.height=Math.round((v.videoHeight||0)*sc)||450;
  c.getContext('2d').drawImage(v,0,0,c.width,c.height);return c.toDataURL('image/png');},
 region(x,y,w,h,sw){if(!this.track||this.track.readyState!=='live')return null;
  const v=this.video,k=v.videoWidth/((screen&&screen.width)||v.videoWidth);
  const c=this._rc||(this._rc=document.createElement('canvas'));c.width=sw;c.height=Math.max(8,Math.round(h/w*sw));
  const ctx=c.getContext('2d',{willReadFrequently:true});
  try{ctx.drawImage(v,x*k,y*k,Math.max(8,w*k),Math.max(8,h*k),0,0,c.width,c.height);return ctx.getImageData(0,0,c.width,c.height).data;}catch(e){return null;}},
 disable(){if(this.track)this.track.stop();this.track=null;if(this.timer)clearInterval(this.timer);this.timer=null;
  $('#scrTag')&&($('#scrTag').textContent='выкл');$('#scrTag')&&($('#scrTag').className='tag g');$('#vScrTag')&&($('#vScrTag').textContent='выкл');$('#vScrTag')&&($('#vScrTag').className='tag g');}};
async function toggleScreen(){Screen.track?Screen.disable():(await Screen.enable());}
function manualShot(){const f=Screen.frame(960);if(!f){toast('включите живой экран');return;}['#vShot','#afterShot','#ctxShot'].forEach(s=>{const i=$(s);if(i){i.src=f;i.style.display='block';}});}
async function visionSnapshot(){if(await Screen.enable())manualShot();}
async function sendToBackend(){const f=Screen.frame(960);if(!f){toast('нет кадра');return;}
  const d=await j('/api/vision/capture',PJ({image_b64:f}));
  $('#vBackend').textContent='backend: '+(d?('ok, source='+(d.source||'?')):'недоступен');}

/* Moondream + fallback */
async function gradioAsk(dataUrl,prompt){
  const file={name:'screen.png',data:dataUrl.split(',')[1]};let lastErr='';
  for(const M of MOONS){
    try{const r=await fetch(M+'/gradio_api/call/answer_question',PJ({data:[file,prompt]}));
      if(r.ok){const cj=await r.json();
        if(cj.event_id){for(let i=0;i<120;i++){await sleep(500);
          const g=await fetch(M+'/gradio_api/call/answer_question/'+cj.event_id);const gj=await g.json();
          if(gj.status==='successful')return gj.data[0];if(gj.status==='failed')throw new Error('fail');}}
        else if(cj.data)return cj.data[0];}}catch(e){lastErr=e.message;}
    try{const r2=await fetch(M+'/run/predict',PJ({data:[file,prompt]}));
      if(r2.ok){const j2=await r2.json();if(j2.data&&j2.data[0])return j2.data[0];}}catch(e){lastErr=e.message;}}
  throw new Error(lastErr||'Moondream2 недоступен');}
async function askMoon(){const p=$('#vPrompt').value;
  const f=Screen.frame(960)||($('#vShot').src.startsWith('data:')?$('#vShot').src:null);
  if(!f){toast('нужен кадр');return;}
  $('#vState').textContent='думаю…';$('#vState').className='tag amb';
  try{$('#vAnswer').textContent='[Moondream2]\n'+String(await gradioAsk(f,p));$('#vState').textContent='ответ';$('#vState').className='tag';}
  catch(e){const d=await j('/api/chat',PJ({message:'Посмотри на экран и ответь коротко: '+p,text:p}));
    const t=d&&(d.text||d.reply);
    if(t){$('#vAnswer').textContent='[backend /api/chat + vision]\n'+t;$('#vState').textContent='backend';$('#vState').className='tag amb';}
    else{$('#vAnswer').textContent='⚠ '+e.message;$('#vState').textContent='ошибка';$('#vState').className='tag red';}}}

/* автономность */
let autoCtl=null,safetyLevel=null;
async function setSafety(l){await j('/api/safety',PJ({level:l}));safetyLevel=l;$('#safetyNow').textContent=l;refreshStatus();}
async function autoConnect(){autoDisconnect();$('#autoTag').textContent='LIVE';$('#autoTag').className='tag';
  try{const r=await fetch(API+'/api/autonomous/stream',PJ({}));
    if(!r.ok){$('#autoTag').textContent='ERR '+r.status;$('#autoTag').className='tag red';return;}
    const rd=r.body.getReader(),dec=new TextDecoder();let buf='';autoCtl=rd;
    while(true){const{done,value}=await rd.read();if(done)break;buf+=dec.decode(value);
      const ls=buf.split('\n');buf=ls.pop();
      for(const ln of ls)if(ln.startsWith('data:')){try{const ev=JSON.parse(ln.slice(5));const el=$('#autoFeed');el.textContent+='['+new Date().toLocaleTimeString().slice(0,8)+'] '+(ev.text||ev.phrase||JSON.stringify(ev))+'\n';el.scrollTop=el.scrollHeight;}catch(e){}}}}
  catch(e){$('#autoTag').textContent='ERR';$('#autoTag').className='tag red';}}
function autoDisconnect(){if(autoCtl){try{autoCtl.cancel();}catch(e){}autoCtl=null;}$('#autoTag').textContent='OFF';$('#autoTag').className='tag g';}

/* память */
async function loadMemory(){const tries=['/api/memory','/api/memory/facts','/api/admin/memory'];
  for(const p of tries){const d=await j(p);if(d){$('#memBody').textContent=JSON.stringify(d,null,1);$('#memInfo').innerHTML=kv('эндпоинт',p);return;}}
  $('#memBody').textContent='⚠ HTTP-эндпоинты памяти не найдены.\nФайлы: uni/memory/working.json, trajectories.jsonl, .FAKE';}

/* тестер */
async function apiTest(){const m=$('#tMethod').value,p=$('#tPath').value,b=$('#tBody').value;
  let payload={};
  if(m==='POST'&&b.trim()){try{payload=JSON.parse(b);}catch(error){$('#tOut').textContent='Некорректный JSON: '+error.message;return;}}
  const o=m==='POST'?PJ(payload):undefined;const r=await api(p,o);
  if(!r){$('#tOut').textContent='⚠ сервер недоступен';return;}
  $('#tOut').textContent='HTTP '+r.status+'\n\n'+(await r.text()).slice(0,4000);}

/* Карта эндпоинтов: каталог безопасен, автопроба только для GET */
const PROBES=[['GET','/api/admin/stack'],['GET','/api/admin/hw'],['GET','/api/admin/git'],['GET','/api/admin/dev'],['GET','/api/admin/agents'],['GET','/api/admin/stats'],['GET','/api/admin/reports'],['POST','/api/admin/actions'],['GET','/api/uni/status'],['GET','/api/heartbeats'],['GET','/api/participants'],['GET','/api/roles'],['GET','/api/tts/engines'],['GET','/api/safety'],['GET','/api/desktop/consent'],['POST','/api/vision/capture'],['POST','/api/chat'],['GET','/api/uni/logs?name=llama&tail=5'],['GET','/v3'],['GET','/v4/'],['POST','/api/computer/act'],['GET','/api/config'],['POST','/api/xtoys/remote/control']];
function renderProbeCatalog(results={}){const t=$('#probeTbl');if(!t)return;t.innerHTML='<tr><th>Метод</th><th>Путь</th><th>Статус</th></tr>'+PROBES.map(([m,p])=>{const key=m+' '+p,r=results[key];let status;if(m!=='GET')status='<span class="tag g">только вручную</span>';else if(!r)status='<span class="tag g">не проверен</span>';else status=r.network?'<span class="tag red">net</span>':'<span class="tag '+(r.ok?'':'red')+'">'+r.status+'</span>';return '<tr><td>'+m+'</td><td><code>'+esc(p)+'</code></td><td>'+status+'</td></tr>';}).join('');}
async function probeAll(){const results={};renderProbeCatalog(results);
  for(const[m,p]of PROBES){if(m!=='GET')continue;const r=await api(p);results[m+' '+p]=r?{ok:r.ok,status:r.status}:{network:true};renderProbeCatalog(results);}
}
function filterProbe(q){q=(q||'').toLowerCase();$$('#probeTbl tr').forEach((tr,i)=>{if(i===0)return;tr.style.display=!q||tr.textContent.toLowerCase().includes(q)?'':'none';});}

/* admin/actions (белый список) */
async function adminAction(action,params){
  const r=await j('/api/admin/actions',PJ({action,params:params||{}}));
  const map={run_pytest:'#aPytest',run_arch_check:'#aArch',run_selftest:'#aSelf',demo_mouse:'#aMouse',vision_capture:'#aShot',create_stop_txt:'#aStop',run_packaging:'#aPack'};
  const sel=map[action];if(sel){$(sel).textContent=r?JSON.stringify(r,null,1):'⚠ нет ответа';}
  else{toast(r?'действие выполнено':'ошибка: '+(r&&r.error?r.error:'нет ответа'));}}

/* INIT */
const INIT={
  overview:refreshStatus,
  participants:loadParticipants,
  transfer:()=>{buildLogs();LOGKEYS.forEach(loadLog);qwnStatus();},
  browser:browserProbe,
  dorch:()=>{$('#dLimit').value=Dorch.limit;dUi();plRender();xtDiscover();},
  settings:()=>{loadSettings();loadConfigSettings();},
  tasks:loadTasks,
  consensus:loadConsensus,
  docs:loadDocs,
  stats:loadStats,
  processes:()=>{$('#pcSync').textContent='—';$('#pcCi').textContent='—';$('#pcCs').textContent='—';$('#pcTst').textContent='—';},
  schedules:loadSchedules,
  rules:ruleRender,
  computer:()=>{},
  chat:loadSettings,
  vision:()=>{j('/api/desktop/consent').then(d=>{$('#vConsent').textContent=d?('enabled='+d.observation_enabled+', level='+(d.level||'—')):'—';});},
  auto:()=>{j('/api/safety').then(d=>{if(d){safetyLevel=d.level||null;$('#safetyNow').textContent=safetyLevel||'—';}});},
  memory:loadMemory,
  plugins:renderProbeCatalog};

$('#dLimit').value=Dorch.limit;
refreshStatus();setInterval(()=>{if(!document.hidden)refreshStatus();},15000);
loadSettings();renderMsgs();dUi();ruleRender();
// Technical build labels belong in diagnostics, not in the conversation.

/* Restored unified theme and Dorch workspace. Later declarations override legacy handlers. */
function applyTheme(theme){document.body.classList.toggle('light',theme==='light');const b=$('#themeBtn');if(b)b.textContent=theme==='light'?'☀':'☾';localStorage.setItem('uni_theme',theme);}
applyTheme(localStorage.getItem('uni_theme')||'dark');
$('#themeBtn')?.addEventListener('click',()=>applyTheme(document.body.classList.contains('light')?'dark':'light'));
$('#settingsBtn')?.addEventListener('click',()=>go('settings'));
$$('.dorch-tabs .tab').forEach(b=>b.addEventListener('click',()=>{const name=b.dataset.dt;$$('.dorch-tabs .tab').forEach(x=>x.classList.toggle('act',x===b));$$('.dorch-pane').forEach(x=>x.classList.toggle('act',x.dataset.dt===name));}));
function dArmManual(){Dorch.stopped=false;Dorch.source='manual';dUi();}
function dSetManual(v){dArmManual();$('#dMan').value=Math.min(v,Dorch.limit);dManual($('#dMan').value);}
function curveMeta(name){const c=window.CURVES?.[name];return c?{duration:Math.round(c.reduce((a,x)=>a+x[0],0)),peak:Math.max(...c.map(x=>x[1]))}:{duration:20,peak:100};}
function renderDorchPatterns(){const root=$('#patBtns'),sel=$('#plPat');if(!root||!window.PATGROUPS)return;const q=($('#patSearch')?.value||'').toLowerCase();let html='',options='';for(const [group,names] of PATGROUPS){const visible=names.filter(n=>allPats().includes(n)&&n.toLowerCase().includes(q));if(!visible.length)continue;html+='<div class="pattern-group">'+esc(group)+'</div>';for(const name of visible){const m=curveMeta(name);html+='<button class="pattern-tile" data-pattern="'+esc(name)+'" onclick="dPattern(\''+name+'\')"><b>'+esc(name.replaceAll('_',' '))+'</b><small>'+m.duration+' сек · пик '+m.peak+'%</small></button>';options+='<option value="'+esc(name)+'">'+esc(name.replaceAll('_',' '))+'</option>';}}root.innerHTML=html;if(sel)sel.innerHTML=options;}
function dPattern(name){patStop(true);Dorch.stopped=false;Dorch.source='pattern';const pow=Math.min(Dorch.limit,+$('#pPow').value||70),scale=Math.max(.1,+$('#pScale').value||1);Dorch.patAbort=new AbortController();$$('.pattern-tile').forEach(b=>b.classList.toggle('on',b.dataset.pattern===name));runCurve(name,pow,scale,Dorch.patAbort.signal,async v=>dSend(v,'pattern')).then(()=>{patStop(true);dSend(0,'pattern');});}
function patStop(s){Dorch.patAbort?.abort();Dorch.patAbort=null;$$('.pattern-tile').forEach(b=>b.classList.remove('on'));}
function plAdd(){Dorch.pl.push({p:$('#plPat').value,s:Math.max(1,+$('#plSec').value||20),w:Math.min(Dorch.limit,+$('#plPow').value||70),repeat:Math.max(1,+$('#plRepeat').value||1)});plRender();}
function plRemove(i){Dorch.pl.splice(i,1);plRender();}
function plRender(){$('#plCount').textContent=Dorch.pl.length;$('#plDuration').textContent=Dorch.pl.reduce((a,x)=>a+x.s*x.repeat,0)+' сек';$('#plList').innerHTML=Dorch.pl.length?Dorch.pl.map((x,i)=>'<div class="playlist-step"><b>'+(i+1)+'</b><span>'+esc(x.p.replaceAll('_',' '))+'</span><input value="'+x.s+'" type="number"><input value="'+x.w+'" type="number"><input value="'+x.repeat+'" type="number"><button class="icon-btn" onclick="plRemove('+i+')">×</button></div>').join(''):'Плейлист пуст';}
async function plRun(){if(!Dorch.pl.length)return toast('Плейлист пуст');plStop(true);Dorch.stopped=false;Dorch.plAbort=new AbortController();for(const step of Dorch.pl)for(let n=0;n<step.repeat;n++){if(Dorch.plAbort.signal.aborted)return;await runCurve(step.p,step.w,Math.max(.1,step.s/curveMeta(step.p).duration),Dorch.plAbort.signal,async v=>dSend(v,'playlist'));}await dSend(0,'playlist');}
function plStop(s){Dorch.plAbort?.abort();Dorch.plAbort=null;patStop(true);dSend(0,'playlist');}
function plSave(){localStorage.setItem('dorch_playlist',JSON.stringify(Dorch.pl));toast('Preset сохранен локально');}
try{Dorch.pl=JSON.parse(localStorage.getItem('dorch_playlist')||'[]');}catch(e){Dorch.pl=[];}

let remoteToken='',remoteAfter=0,ownerPc=null,ownerStream=null;
function tokenFromUrl(url){try{return new URL(url,location.href).hash.match(/(?:token=)?([^&]+)/)?.[1]||'';}catch(e){return '';}}
async function remoteCreate(){const r=await api('/api/xtoys/remote/session/start',PJ({max_intensity:+$('#rMax').value,ttl:(+$('#rMin').value||150)*60,uni_in_chat:$('#rUniMode').value}));const d=r?await r.json().catch(()=>null):null;if(!r?.ok||!d?.url){$('#rTag').textContent='ошибка';return;}remoteToken=tokenFromUrl(d.url);$('#rLink').value=d.url;$('#rTag').textContent='активна';$('#dSes').textContent='активна';$('#remoteChatFeed').textContent='Сессия создана. Ожидание гостя…';remotePoll();}
async function remoteEnd(){await api('/api/xtoys/remote/session/stop',PJ({}));await stopOwnerBroadcast();remoteToken='';$('#rTag').textContent='выкл';$('#dSes').textContent='выкл';$('#rLink').value='';$('#rPub').value='';}
async function remotePublic(open){const r=await api(open?'/api/xtoys/remote/public/start':'/api/xtoys/remote/public/stop',PJ({}));const d=r?await r.json().catch(()=>null):null;if(open){const cf=d?.cloudflare_url||d?.url||'';const ng=d?.ngrok_url||'';$('#rPub').value=cf;$('#rNgrok').value=ng;if(!cf&&!ng)toast('Публичная ссылка не создана');else if(d?.errors&&Object.keys(d.errors).length){const e=Object.entries(d.errors).map(([k,v])=>k+': '+v).join(' | ');bpLog('public: '+e);$('#rPubNote').textContent=e;}else $('#rPubNote').textContent='оба туннеля подняты (на всякий случай)';}else{$('#rPub').value='';$('#rNgrok').value='';$('#rPubNote').textContent='публичные ссылки закрыты';}}
async function remoteRoom(action,kind,payload){if(!remoteToken)return null;return j('/api/xtoys/remote/room',PJ({token:remoteToken,role:'owner',action,kind,payload,after:remoteAfter}));}
function remoteAdd(who,text){const f=$('#remoteChatFeed');if(f.textContent.startsWith('Сессия'))f.textContent='';f.textContent+='\n'+who+': '+text;f.scrollTop=f.scrollHeight;}
async function streamMsg(){const text=$('#stMsg').value.trim();if(!text||!remoteToken)return;const d=await remoteRoom('send','chat',text);if(d?.ok){remoteAdd('Вы',text);$('#stMsg').value='';}}
async function remotePoll(){if(!remoteToken)return;const d=await remoteRoom('poll');for(const e of d?.events||[]){remoteAfter=Math.max(remoteAfter,e.id||0);if(e.kind==='chat')remoteAdd('Гость',String(e.payload||''));else if(e.kind==='answer'&&ownerPc)await ownerPc.setRemoteDescription(e.payload);else if(e.kind==='ice'&&ownerPc)await ownerPc.addIceCandidate(e.payload).catch(()=>{});else if(e.kind==='hangup')stopOwnerBroadcast();}setTimeout(remotePoll,800);}
async function startOwnerBroadcast(){if(!remoteToken)return toast('Сначала создайте Remote-сессию');try{ownerStream=await navigator.mediaDevices.getUserMedia({video:true,audio:true});$('#ownerPreview').srcObject=ownerStream;ownerPc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});ownerStream.getTracks().forEach(t=>ownerPc.addTrack(t,ownerStream));ownerPc.onicecandidate=e=>{if(e.candidate)remoteRoom('send','ice',e.candidate.toJSON());};const offer=await ownerPc.createOffer();await ownerPc.setLocalDescription(offer);await remoteRoom('send','offer',ownerPc.localDescription.toJSON());$('#stTag').textContent='ожидание гостя';}catch(e){toast('Трансляция не запущена: '+e.message);}}
async function stopOwnerBroadcast(){ownerStream?.getTracks().forEach(t=>t.stop());ownerStream=null;ownerPc?.close();ownerPc=null;$('#ownerPreview').srcObject=null;$('#stTag').textContent='выкл';if(remoteToken)await remoteRoom('send','hangup',{});}

async function bpConnect(){const url=$('#bpUrl').value||'ws://127.0.0.1:12345';const d=await j('/api/intiface/connect',PJ({url}));if(!d?.ok)return bpState('ошибка');bpState('подключение…');for(let i=0;i<20;i++){await sleep(500);const s=await j('/api/intiface/status');if(s?.connected){renderBackendIntiface(s);return;}if(s?.last_error)return bpState('ошибка: '+s.last_error);}bpState('not_verified: таймаут');}
async function bpDisconnect(){await j('/api/intiface/disconnect',PJ({}));renderBackendIntiface({connected:false,devices:[],value:0});}
async function bpScan(){renderBackendIntiface(await j('/api/intiface/status')||{});}
function renderBackendIntiface(s){BP.ready=!!s.connected;bpState(s.connected?'подключено':'отключено');$('#bpDevSel').innerHTML=(s.devices||[]).map((name,i)=>'<option value="'+i+'">'+esc(name)+'</option>').join('');$('#dDevName').textContent=(s.devices||[]).join(', ')||'—';$('#dBpTxt').textContent='Intiface: '+(s.connected?((s.devices||[]).length+' устр.'):'нет');$('#dBpDot').className='dot '+(s.connected?'ok':'bad');$('#bpDiag').textContent=s.connected?'backend IntifaceBridge · connected':(s.last_error||'не подключено');Dorch.current=(+s.value||0)/100;dUi();}
async function dSend(v,src){v=Math.max(0,Math.min(1,v));const value=Math.round((Dorch.stopped?0:Math.min(v,Dorch.limit/100))*100);if(src)Dorch.source=src;const r=await api('/api/intiface/oscillate',PJ({value}));const d=r?await r.json().catch(()=>null):null;if(r?.ok&&d?.ok){Dorch.current=value/100;dUi();return true;}bpLog('RESULT rejected: '+(d?.error||r?.status||'нет ответа'));return false;}
async function dStop(){
  Dorch.stopped=true;Dorch.auto=false;
  // Send the latched stop before any local producer cleanup can wait or fail.
  const stopping=api('/api/xtoys/emergency-stop',PJ({}));
  motionStop(true);plStop(true);$('#dAutoTag').textContent='выкл';
  const response=await stopping;const data=response?await response.json().catch(()=>null):null;
  Dorch.source='STOP';dUi();
  toast(response?.ok&&data?.ok?'STOP отправлен. Проверьте физическую остановку.':'STOP не подтверждён — используйте физический пульт!');
}
async function xtDiscover(){const s=await j('/api/intiface/status');$('#xtMap').textContent='Intiface: '+(s?.connected?'connected':'not connected')+'\nRemote API: canonical session/room/control';}
renderDorchPatterns();plRender();
