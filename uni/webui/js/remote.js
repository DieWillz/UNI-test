'use strict';
/* Remote-гость: большой слайдер, паттерны, плейлист, чат, видео */
(function(){
const $=s=>document.querySelector(s);
const token=(location.hash||'').replace('#','')||'';
const sl=ms=>new Promise(r=>setTimeout(r,ms));
async function api(p,o){try{return await fetch(p,o);}catch(e){return null;}}
async function j(p,o){const r=await api(p,o);if(!r)return null;try{return await r.json();}catch(e){return null;}}
const PJ=o=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)});
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');

/* транспорт интенсивности: первый живой эндпоинт */
let INT_EP=null;
async function probeInt(){
  const cands=[
    [ '/api/xtoys/remote/control', v=>PJ({token,action:'intensity',value:Math.round(v*100)}) ],
    [ '/api/xtoys/intensity',      v=>PJ({value:Math.round(v*100)}) ],
    [ '/api/xtoys/oscillate',      v=>PJ({value:Math.round(v*100)}) ]];
  for(const[p,mk]of cands){const r=await api(p,mk(0));if(r&&r.status!==404&&r.status!==405){INT_EP=[p,mk];return;}}
}
async function sendInt(v){if(!INT_EP)return;await api(INT_EP[0],INT_EP[1](v));}

/* статус сессии */
async function status(){const d=await j('/api/xtoys/remote/status?token='+token);
  if(d&&d.active!==undefined){$('#rSes').textContent='сессия: '+(d.active?'активна':'выкл');
    $('#rMax').textContent='max: '+(d.max_intensity??'—')+'%';
    $('#bigSlider').max=d.max_intensity||100;
    $('#uniTag').textContent='Юни: '+(d.uni_in_chat?'в чате':'—');}
  else{$('#rSes').textContent='сессия: локальная';}}
setInterval(status,5000);status();

/* большой слайдер (троттлинг 250мс) */
let lastSend=0;
$('#bigSlider').addEventListener('input',e=>{
  const v=+e.target.value;$('#bigVal').textContent=v+'%';
  const now=Date.now();if(now-lastSend<250)return;lastSend=now;sendInt(v/100);});
window.rStop=async function(){ $('#bigSlider').value=0;$('#bigVal').textContent='0%';
  if(patCtl)patCtl.abort();await sendInt(0);
  await api('/api/xtoys/remote/control',PJ({token,action:'stop'}));
  await api('/api/xtoys/remote/stop',PJ({token}));};

/* паттерны (кривые крутятся тут, интенсивность шлётся на сервер) */
let patCtl=null,plCtl=null,PL=[];
function buildPats(){$('#patGroups').innerHTML=PATGROUPS.map(g=>'<div class="pg"><b>'+g[0]+'</b>'+
  g[1].map(p=>'<button class="btn ghost pch" style="margin:2px;font-size:11px" onclick="rPat(\''+p+'\')">'+p+'</button>').join('')+'</div>').join('');
  $('#plPat').innerHTML=allPats().map(p=>'<option>'+p+'</option>').join('');}
window.rPat=function(name){if(patCtl)patCtl.abort();patCtl=new AbortController();
  $('#patNow').textContent=name;
  runCurve(name,+$('#pPow').value||70,+$('#pScale').value||1,patCtl.signal,sendInt)
    .then(()=>{$('#patNow').textContent='—';});};
window.plAdd=function(){PL.push({p:$('#plPat').value,w:+$('#plPow').value||70,sc:+$('#plScale').value||1});
  $('#plCount').textContent=PL.length;
  $('#plList').innerHTML=PL.map((x,i)=>(i+1)+'. '+x.p+' '+x.w+'% ×'+x.sc).join('<br>')||'пуст';};
window.plRun=async function(){if(!PL.length)return;plCtl=new AbortController();
  for(const s of PL){if(plCtl.aborted)break;$('#patNow').textContent=s.p;
    await runCurve(s.p,s.w,s.sc,plCtl.signal,sendInt);}$('#patNow').textContent='—';};

/* чат */
let lastId=0;
function addMsg(t){const el=$('#chatFeed');el.innerHTML+=esc(t)+'\n';el.scrollTop=el.scrollHeight;}
window.chatSend=async function(){const t=$('#chatIn').value.trim();if(!t)return;$('#chatIn').value='';
  addMsg('вы → '+t);
  const r=await api('/api/xtoys/chat',PJ({token,from:'guest',text:t}));
  if(!r||r.status===404)addMsg('⚠ чат-эндпоинт появится после директивы Hermes');};
setInterval(async()=>{const d=await j('/api/xtoys/chat?token='+token+'&after='+lastId);
  if(d&&Array.isArray(d.messages))for(const m of d.messages){lastId=Math.max(lastId,m.id||0);
    addMsg((m.from==='coord'?'координатор → ':'Юни → ')+m.text);}},2500);

/* видео: пробуем WebRTC-сигналинг, иначе честная заглушка-статус */
async function tryVideo(){const off=await j('/api/xtoys/rtc/offer?token='+token);
  if(off&&off.sdp){try{
    const pc=new RTCPeerConnection();$('#vid').srcObject=pc;
    await pc.setRemoteDescription({type:'offer',sdp:off.sdp});
    const ans=await pc.createAnswer();await pc.setLocalDescription(ans);
    await api('/api/xtoys/rtc/answer',PJ({token,sdp:ans.sdp}));
    $('#vidState').textContent='трансляция подключена';return;}catch(e){}}
  $('#vidState').textContent='Трансляция появится, когда координатор нажмёт «Трансляция» и Hermes добавит WebRTC-сигналинг.';}
setTimeout(tryVideo,1500);

probeInt().then(()=>{buildPats();addMsg('remote-панель готова; управление: '+(INT_EP?'работает':'эндпоинт интенсивности не найден — сообщите координатору'));});
})();