'use strict';
/* Dorch v2.1: фикс селектора — секция ищется только внутри main (кнопка меню больше не матчится) */
(function(){
const $=s=>document.querySelector(s);
const sec=document.querySelector('main section.page[data-page="dorch"]')||document.querySelector('main [data-page="dorch"]');
if(!sec)return;
const st=document.createElement('style');
st.textContent='.dgrid{display:grid;grid-template-columns:1.7fr 1fr;gap:12px}.dside{display:flex;flex-direction:column;gap:12px}#patGroups .pg{margin-bottom:6px}#patGroups .pg b{font-size:10.5px;color:var(--mute);display:block;margin-bottom:3px}.pch{margin:2px;font-size:11px}@media(max-width:1000px){.dgrid{grid-template-columns:1fr}}';
document.head.appendChild(st);

sec.innerHTML=
'<h1>Dorch · Rotary Control <span class="tag red">L4</span></h1>'+
'<div class="sub">manual → motion → pattern → auto · всё через лимит и STOP · ESC = авария</div>'+
'<div class="card" style="margin-bottom:12px"><div class="row">'+
'<span class="chip"><span class="dot" id="dBpDot"></span><span id="dBpTxt">Intiface: —</span></span>'+
'<span class="chip" id="dDevName">—</span>'+
'<span class="chip">источник: <b id="dSrc">manual</b></span>'+
'<span class="chip">сессия: <b id="dSes">выкл</b></span>'+
'<span class="chip">интенсивность <b id="dIntVal">0.0%</b><span class="bar" style="width:70px;margin-left:6px"><div id="dIntBar"></div></span></span>'+
'<span class="sp"></span>'+
'<label class="row">лимит <input id="dLimit" type="number" min="0" max="100" value="65" style="width:56px">%</label>'+
'<button class="btn ghost" onclick="dSaveLimit()">сохранить</button>'+
'<button class="btn red" onclick="dStop()">■ Стоп 0%</button></div></div>'+
'<div class="card" style="margin-bottom:12px;border:1px solid rgba(184,230,29,.4)">'+
'<h3>🌐 Remote-сессия — управление по ссылке <span class="tag">приоритет</span></h3>'+
'<div class="row"><label>max% <input id="rMax" type="number" value="40" style="width:56px"></label>'+
'<label>минут <input id="rMin" type="number" value="30" style="width:56px"></label>'+
'<button class="btn" onclick="remoteCreate()">Создать ссылку</button>'+
'<button class="btn red" onclick="remoteEnd()">Завершить</button>'+
'<span class="tag g" id="rTag">выкл</span>'+
'<button class="btn ghost" onclick="openRemote()">Открыть remote-панель ↗</button></div>'+
'<div class="row" style="margin-top:6px"><input id="rLink" readonly placeholder="ссылка гостю" style="flex:1"><button class="btn ghost" onclick="copyVal(\'#rLink\')">копир</button>'+
'<button class="btn" onclick="remotePublic(true)">Открыть из интернета</button>'+
'<button class="btn ghost" onclick="remotePublic(false)">Закрыть</button>'+
'<input id="rPub" readonly placeholder="публичная HTTPS-ссылка" style="flex:1"><button class="btn ghost" onclick="copyVal(\'#rPub\')">копир</button></div>'+
'<div class="row" style="margin-top:6px"><b style="font-size:11px">Чат с гостем:</b>'+
'<input id="rcIn" placeholder="сообщение гостю" style="flex:1"><button class="btn ghost" onclick="rcSend()">отпр</button>'+
'<label class="row"><input type="checkbox" id="rcUni"> Юни в чате гостя</label>'+
'<button class="btn ghost" onclick="streamToggle(true)">Трансляция</button>'+
'<button class="btn ghost" onclick="streamToggle(false)">стоп</button><span class="tag g" id="stTag">выкл</span></div>'+
'<pre class="log" id="rcFeed" style="height:100px;margin-top:6px">Управление машинкой по ссылке работает сразу. Чат гостя и видео загорятся, когда Hermes добавит backend (директива ниже).</pre>'+
'<details style="margin-top:6px"><summary>📋 Директива Hermes: чат+видео гостя (копировать)</summary>'+
'<pre class="log" id="rcDirective" style="height:150px"></pre>'+
'<button class="btn ghost" onclick="copyVal(\'#rcDirective\')">копировать директиву</button></details>'+
'<details style="margin-top:6px"><summary>карта /api/xtoys</summary><pre class="log" id="xtMap" style="height:110px"></pre><div class="note" id="xtState"></div></details></div>'+
'<div class="dgrid"><div class="card"><h3>🎛 Паттерны и плейлист</h3>'+
'<div class="row"><label>мощность% <input id="pPow" type="number" value="70" style="width:56px"></label>'+
'<label>масштаб времени ×<input id="pScale" type="number" value="1" step="0.1" style="width:56px"></label>'+
'<select id="plPat" style="max-width:170px"></select>'+
'<button class="btn" onclick="dPattern($(\'#plPat\').value)">▶ запустить</button>'+
'<button class="btn red" onclick="plStop()">■</button>'+
'<span class="sp"></span><span class="tag g" id="patNow">—</span></div>'+
'<div id="patGroups" style="margin-top:8px"></div>'+
'<div class="kv" style="margin-top:8px"><b>Плейлист (по порядку)</b><span id="plCount">0</span></div>'+
'<div class="row"><label>% <input id="plPow" type="number" value="70" style="width:52px"></label>'+
'<label>×<input id="plScale" type="number" value="1" step="0.1" style="width:52px"></label>'+
'<button class="btn ghost" onclick="plAdd()">+ шаг</button>'+
'<button class="btn" onclick="plRun()">▶ плейлист</button>'+
'<label class="row"><input type="checkbox" id="plLoop"> цикл</label></div>'+
'<div id="plList" class="note" style="margin-top:6px">пуст</div></div>'+
'<div class="dside">'+
'<details class="card" id="bpBox" open><summary>🔌 Intiface <span class="tag g" id="bpSumTag">не подключено</span></summary>'+
'<div class="row" style="margin-top:6px"><input id="bpUrl" value="ws://127.0.0.1:12345" style="flex:1"><button class="btn" onclick="bpConnect()">Подключить</button><button class="btn ghost" onclick="bpDisconnect()">Откл</button></div>'+
'<div class="kv"><b>Статус</b><span id="bpState">отключено</span></div>'+
'<div class="kv"><b>Устройство</b><select id="bpDevSel" style="max-width:170px"></select></div>'+
'<div class="row"><button class="btn ghost" onclick="bpScan()">Скан</button>'+
'<label class="row">osc <input type="range" class="slider" id="bpOsc" min="0" max="100" value="0" style="width:100px"></label>'+
'<button class="btn ghost" onclick="bpApplyOsc()">применить</button></div>'+
'<div class="note" id="bpDiag">—</div><div class="note" id="bpFeats">—</div><div class="note" id="dDevState">отключено</div></details>'+
'<details class="card" id="motBox"><summary>🌀 Motion → машинка <span class="tag g" id="mTag">выкл</span></summary>'+
'<div class="note" style="margin:6px 0">Машинка следует за движением в области экрана (реальная оптика).</div>'+
'<div class="row"><label>X<input id="mX" type="number" value="0" style="width:50px"></label><label>Y<input id="mY" type="number" value="0" style="width:50px"></label><label>W<input id="mW" type="number" value="640" style="width:56px"></label><label>H<input id="mH" type="number" value="480" style="width:56px"></label></div>'+
'<div class="row"><label>порог<input id="mThr" type="number" value="2.6" step="0.1" style="width:50px"></label><label>усил<input id="mGain" type="number" value="10" style="width:44px"></label><label>сглаж<input id="mSm" type="number" value="0.95" step="0.01" style="width:50px"></label><label>гамма<input id="mGam" type="number" value="3.7" step="0.1" style="width:50px"></label></div>'+
'<div class="row"><label>мс<input id="mInt" type="number" value="140" style="width:56px"></label><label>max%<input id="mMax" type="number" value="70" style="width:50px"></label>'+
'<button class="btn" onclick="motionStart()">▶</button><button class="btn red" onclick="motionStop()">■</button><span class="sp"></span><b id="mCur">0%</b></div></details>'+
'<div class="card"><h3>🎚 Manual / авто</h3>'+
'<div class="kv"><b>manual</b><span id="dManVal">0%</span></div>'+
'<input type="range" class="slider" id="dMan" min="0" max="100" value="0" oninput="dManual(this.value)">'+
'<div class="row"><button class="btn" onclick="dAutoToggle()">Авто-режим</button><span class="tag g" id="dAutoTag">выкл</span></div></div>'+
'</div></div>'+
'<div class="card" style="margin-top:12px"><h3>Журнал Dorch</h3><pre class="log" id="dLog" style="height:130px"></pre></div>';

/* ── логика ── */
let patCtl=null,plCtl=null;
window.dStop=function(soft){Dorch.stopped=true;if(patCtl)patCtl.abort();if(plCtl)plCtl.abort();
  motionStop(true);BP.stop();dSend(0);Dorch.auto=false;const a=$('#dAutoTag');if(a)a.textContent='выкл';
  const n=$('#patNow');if(n)n.textContent='—';if(!soft)bpLog('■ АВАРИЙНЫЙ СТОП');};
window.dPattern=function(name){dStop(true);Dorch.stopped=false;patCtl=new AbortController();
  $('#patNow').textContent=name;bpLog('паттерн '+name);
  runCurve(name,+$('#pPow').value||70,+$('#pScale').value||1,patCtl.signal,v=>dSend(v,'pattern'))
    .then(()=>{const n=$('#patNow');if(n&&n.textContent===name)n.textContent='—';});};
window.plAdd=function(){Dorch.pl.push({p:$('#plPat').value,w:+$('#plPow').value||70,sc:+$('#plScale').value||1});plRender();};
window.plDel=function(i){Dorch.pl.splice(i,1);plRender();};
window.plMove=function(i,d){const j=i+d;if(j<0||j>=Dorch.pl.length)return;const t=Dorch.pl[i];Dorch.pl[i]=Dorch.pl[j];Dorch.pl[j]=t;plRender();};
window.plRender=function(){$('#plCount').textContent=Dorch.pl.length;
  $('#plList').innerHTML=Dorch.pl.length?Dorch.pl.map((x,i)=>'<div class="row" style="margin:2px 0"><b>'+(i+1)+'</b> '+x.p+' · '+x.w+'% · ×'+x.sc+
  ' <button class="btn ghost" style="padding:1px 7px" onclick="plMove('+i+',-1)">↑</button>'+
  ' <button class="btn ghost" style="padding:1px 7px" onclick="plMove('+i+',1)">↓</button>'+
  ' <button class="btn ghost" style="padding:1px 7px" onclick="plDel('+i+')">✕</button></div>').join(''):'пуст';};
window.plStop=function(s){if(plCtl)plCtl.abort();if(patCtl)patCtl.abort();if(!s)bpLog('плейлист стоп');};
window.plRun=async function(){if(!Dorch.pl.length){toast('плейлист пуст');return;}
  plCtl=new AbortController();Dorch.stopped=false;bpLog('плейлист старт ('+Dorch.pl.length+')');
  do{for(const s of Dorch.pl){if(plCtl.aborted)break;$('#patNow').textContent=s.p;
    await runCurve(s.p,s.w,s.sc,plCtl.signal,v=>dSend(v,'pattern'));}}while($('#plLoop').checked&&!plCtl.aborted);
  $('#patNow').textContent='—';bpLog('плейлист завершён');};

const _bp=window.bpConnect;
window.bpConnect=async function(){const r=await _bp();
  if(BP.ready){const b=$('#bpBox');if(b)b.removeAttribute('open');const t=$('#bpSumTag');if(t)t.textContent='ok';}
  return r;};

function buildPats(){const g=$('#patGroups');if(!g||g.dataset.b)return;g.dataset.b=1;
  g.innerHTML=PATGROUPS.map(gr=>'<div class="pg"><b>'+gr[0]+'</b>'+gr[1].map(p=>'<button class="btn ghost pch" onclick="dPattern(\''+p+'\')">'+p+'</button>').join('')+'</div>').join('');
  $('#plPat').innerHTML=allPats().map(p=>'<option>'+p+'</option>').join('');}

window.openRemote=function(){let t=localStorage.getItem('dorch_token');
  if(!t){t=Math.random().toString(36).slice(2,10);localStorage.setItem('dorch_token',t);}
  window.open('/remote.html#'+t,'_blank');};
window.rcSend=async function(){const t=$('#rcIn').value.trim();if(!t)return;$('#rcIn').value='';
  rcAdd('вы → '+t);await api('/api/xtoys/message',PJ({text:t}));};
function rcAdd(t){const el=$('#rcFeed');el.textContent+='['+new Date().toLocaleTimeString().slice(0,8)+'] '+t+'\n';el.scrollTop=el.scrollHeight;}
let rcLast=0;
async function rcPoll(){setInterval(async()=>{
  const t=localStorage.getItem('dorch_token')||'';
  const d=await j('/api/xtoys/chat?token='+t+'&after='+rcLast);
  if(d&&Array.isArray(d.messages)){for(const m of d.messages){rcLast=Math.max(rcLast,m.id||0);
    if(m.from==='guest'){rcAdd('гость → '+m.text);
      if($('#rcUni').checked){const u=await j('/api/chat',PJ({message:m.text,text:m.text}));
        if(u&&(u.text||u.reply)){const r=u.text||u.reply;rcAdd('Юни → '+r);await api('/api/xtoys/message',PJ({text:'[Юни] '+r}));}}}
    else rcAdd('вы → '+m.text);}}},2500);}

$('#rcDirective').textContent=
'ДИРЕКТИВА HERMES (аддитивно, ничего не удалять): remote-сессия Dorch.\n'+
'Добавить модуль uni/webui/remote_session.py + 5 маршрутов в server.py:\n'+
'1 POST /api/xtoys/remote/start {max_intensity,minutes} -> {token,url,expires}\n'+
'2 GET  /api/xtoys/remote/status?token -> {active,max_intensity,seconds_left,uni_in_chat}\n'+
'3 POST /api/xtoys/chat {token,from:guest|coord,text} + GET /api/xtoys/chat?token&after=id (хранилище runtime/remote_chat.jsonl)\n'+
'4 POST /api/xtoys/remote/control {token,action:intensity|pattern|stop,value} — прокси в xtoys с ограничением по session max\n'+
'5 WebRTC-сигналинг трансляции: POST /api/xtoys/rtc/offer|answer|ice + GET для второй стороны (камера+микрофон координатора -> гостю)\n'+
'Пруфы по протоколу ACTION->RESULT->OBSERVATION; секреты не выводить; DEPRECATED-пометки вместо удалений.';

INIT.dorch=function(){$('#dLimit').value=Dorch.limit;dUi();plRender();buildPats();xtDiscover();rcPoll();};
})();