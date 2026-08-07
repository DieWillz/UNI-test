let FS=localStorage.getItem('uni_fs')||'http://127.0.0.1:8000';
let HRM=localStorage.getItem('uni_hrm')||'http://127.0.0.1:8787';
let LMS=localStorage.getItem('uni_lms')||'http://127.0.0.1:1234';
let LMS_MODEL='';
const COLORS={QWN:'#16a34a',DPS:'#2563eb',GMN:'#ea580c',MST:'#4f46e5',GRK:'#ca8a04',CLD:'#7c3aed',GPT:'#0891b2',KMI:'#dc2626',ZAI:'#059669',HRM:'#dc2626',LMS:'#6b7280',USR:'#f59e0b'};
const BASE_PARTS=[{n:'DeepSeek',c:'DPS',m:'browser',src:'chat.deepseek.com'},{n:'QWEN',c:'QWN',m:'browser',src:'chat.qwen.ai'},{n:'Claude',c:'CLD',m:'browser',src:'claude.ai'},{n:'ChatGPT',c:'GPT',m:'codex',src:'codex.local'},{n:'Grok',c:'GRK',m:'browser',src:'grok.com'},{n:'Gemini',c:'GMN',m:'api',src:'gemini.google.com'},{n:'Mistral',c:'MST',m:'browser',src:'chat.mistral.ai'},{n:'Kimi',c:'KMI',m:'browser',src:'kimi.com'},{n:'Hermes',c:'HRM',m:'api',src:'hermes.local'},{n:'OpenRouter',c:'OR',m:'free',src:'openrouter.ai'}];
let liveParts={},seenReplies=new Set(),micOn=false,recog=null;
const $=id=>document.getElementById(id);
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function now(){const d=new Date();return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')+':'+String(d.getSeconds()).padStart(2,'0')}
function showToast(m){const t=$('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2600)}
function setTheme(v){document.documentElement.setAttribute('data-theme',v);localStorage.setItem('uni_theme',v);$('themeSel').value=v;$('themeBtn').textContent=v==='dark'?'☀ Тема':'🌙 Тема'}
function toggleTheme(){setTheme(document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark')}
function toggleChatPanel(){$('chatPanel').classList.toggle('collapsed')}
function showView(v,el){document.querySelectorAll('.view-wrap').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));const w=$('view-'+v);if(w)w.classList.add('active');if(el)el.classList.add('active')}
function setStep(n){document.querySelectorAll('.pstep').forEach((el,i)=>{el.classList.remove('active','done');if(n>=0){if(i<n)el.classList.add('done');if(i===n)el.classList.add('active')}})}
async function api(url,ms){const c=new AbortController();const t=setTimeout(()=>c.abort(),ms||2500);try{const r=await fetch(url,{signal:c.signal});clearTimeout(t);return r}catch(e){clearTimeout(t);throw e}}
async function pingServers(){
try{await api(FS+'/ping');$('dotFs').className='dot on';$('qwSrv').textContent='онлайн';$('qwSrv').className='qw-ok';$('intFs').className='pill p-ok';$('intFs').textContent='онлайн'}catch(e){$('dotFs').className='dot err';$('qwSrv').textContent='офлайн';$('qwSrv').className='qw-bad';$('intFs').className='pill p-err';$('intFs').textContent='офлайн'}
try{await api(HRM+'/api/participants');$('dotHermes').className='dot on';$('intHrm').className='pill p-ok';$('intHrm').textContent='онлайн'}catch(e){$('dotHermes').className='dot err';$('intHrm').className='pill p-err';$('intHrm').textContent='офлайн'}
try{
const r=await api(LMS+'/v1/models',1800);const d=await r.json();
if(d.data&&d.data.length){LMS_MODEL=d.data[0].id;$('dotLms').className='dot on';$('lmsLabel').textContent=LMS_MODEL;$('chatModel').textContent=LMS_MODEL;$('intLms').className='pill p-ok';$('intLms').textContent=LMS_MODEL;$('rchatDot').className='dot on';$('rchatStatus').textContent='LM: '+LMS_MODEL}
else{$('dotLms').className='dot err';$('lmsLabel').textContent='LM: нет модели';$('chatModel').textContent='модель не загружена';$('intLms').className='pill p-warn';$('intLms').textContent='сервер онлайн, модель не загружена';$('rchatStatus').textContent='LM без модели → письма Qwen'}
}catch(e){$('dotLms').className='dot err';$('lmsLabel').textContent='LM офлайн';$('chatModel').textContent='офлайн';$('intLms').className='pill p-err';$('intLms').textContent='офлайн (письма Qwen)';$('rchatDot').className='dot on';$('rchatStatus').textContent='LM офлайн → письма Qwen'}
}
async function runRollCall(){
showToast('🔄 Roll call: чтение heartbeat-логов…');
liveParts={};
try{
const r=await api(FS+'/list?path=.');const d=await r.json();
if(d.ok){const dirs=d.items.filter(i=>i.endsWith('/')&&i.startsWith('uni-'));
for(const dir of dirs){const name=dir.replace('/','').replace('uni-','');
try{const hr=await api(FS+'/read?path=uni-'+name+'/heartbeat.log');const hd=await hr.json();
if(hd.ok){const lines=hd.content.trim().split('\n');const last=lines[lines.length-1]||'';liveParts[name]={last:last.slice(0,120),online:/auto|ok|ready|готов/i.test(last)}}}catch(e){liveParts[name]={last:'heartbeat недоступен',online:false}}}}
}catch(e){showToast('❌ Файловый сервер недоступен')}
renderParticipants();
}
function renderParticipants(){
const rows=BASE_PARTS.map(p=>{
const lp=liveParts[p.n.toLowerCase()];
const st=lp?(lp.online?'ready':'stale'):'—';
const pill=st==='ready'?'p-ok':st==='stale'?'p-warn':'p-out';
const src=lp?lp.last:p.src;
return `<div class="prow"><div class="ag-name"><div class="ag-av" style="background:${COLORS[p.c]||'#6b7280'}">${p.c[0]}</div>${p.n}</div><div><span class="pill ${pill}">${st}</span></div><div><span class="pill p-out">${p.m}</span></div><div style="color:var(--text3);font-size:10px" title="${esc(src)}">${esc((src||'').slice(0,40))}</div></div>`}).join('');
$('partList').innerHTML=rows;$('partListFull').innerHTML=rows;
const on=Object.values(liveParts).filter(x=>x.online).length;
$('stAgents').textContent=on+' / '+BASE_PARTS.length;
$('qwParts').innerHTML=BASE_PARTS.slice(0,6).map(p=>{const lp=liveParts[p.n.toLowerCase()];return `<div class="qw-row"><span>${p.n}</span><span class="${lp?(lp.online?'qw-ok':'qw-warn'):'qw-bad'}">${lp?(lp.online?'готов':'stale'):'нет heartbeat'}</span></div>`}).join('');
}
async function loadLogs(){
try{const r=await api(FS+'/log?lines=60');const d=await r.json();
if(d.ok){$('logBox').innerHTML=d.lines.map(l=>{const p=l.split(' | ');const tag=/WRITE/.test(l)?(/DENY|ERROR/.test(l)?'err':'ok'):/READ|LIST/.test(l)?'ok':'info';return `<div class="log-line"><span class="log-time">${esc(p[0]||'')}</span><span class="log-tag ${tag}">[${esc(p[1]||'')}]</span><span class="log-msg">${esc(p.slice(2).join(' | '))}</span></div>`}).join('')||'лог пуст'}
}catch(e){$('logBox').textContent='❌ fileserver.log недоступен (сервер 8000 офлайн)'}
}
function filterLogs(tag,btn){document.querySelectorAll('.log-filters button').forEach(b=>b.classList.remove('on'));btn.classList.add('on');document.querySelectorAll('#logBox .log-line').forEach(l=>{l.style.display=(tag==='all'||l.textContent.includes(tag))?'flex':'none'})}
async function loadBoard(){
try{const r=await api(FS+'/read?path=uni-qwen/UNI_BOARD.md');const d=await r.json();
if(d.ok){const i=d.content.indexOf('ЗАМЕТКИ КООРДИНАТОРА');$('boardNotes').textContent=i>=0?d.content.slice(i,i+1800):d.content.slice(-1800);
const t=d.content.indexOf('ЗАДАЧИ');$('tasksBody').innerHTML='<pre style="white-space:pre-wrap;font:11px/1.5 var(--mono)">'+esc(d.content.slice(t>=0?t:0,(t>=0?t:0)+2500))+'</pre>'}
}catch(e){$('boardNotes').textContent='❌ UNI_BOARD.md недоступен'}
}
async function loadMail(){
try{const r=await api(FS+'/list?path=uni-qwen/outbox');const d=await r.json();
if(d.ok){const files=d.items.filter(f=>f.endsWith('.md')).slice(-6).reverse();
$('hubMail').innerHTML=files.map(f=>`<div class="hub-msg"><div class="hub-head"><div class="hub-av">Q</div><span class="hub-from">outbox</span><span class="hub-time">${esc(f.slice(0,26))}</span></div><div class="hub-body">${esc(f)}</div></div>`).join('')||'писем нет'}
}catch(e){$('hubMail').textContent='❌ outbox недоступен'}
}
async function loadDocs(){try{const r=await api(FS+'/list?path=.');const d=await r.json();if(d.ok)$('docsBody').innerHTML='<pre style="font:11px/1.6 var(--mono)">'+esc(d.items.join('\n'))+'</pre>'}catch(e){$('docsBody').textContent='❌ недоступно'}}
async function loadStats(){try{const r=await api(FS+'/stats');const d=await r.json();if(d.ok)$('statsBody').innerHTML='<pre style="font:12px/1.6 var(--mono)">'+esc(JSON.stringify(d.stats,null,1))+'</pre>'}catch(e){$('statsBody').textContent='❌ /stats недоступен'}}
function addMsg(feed,role,text){const m=document.createElement('div');m.className='msg '+role;m.innerHTML=(role!=='sys'?`<div class="who">${role==='user'?'Вы':'ЮНИ'} · ${now()}</div>`:'')+esc(text);feed.appendChild(m);feed.scrollTop=feed.scrollHeight}
async function uniSend(text,feeds){
feeds=(feeds||[]).filter(f=>f&&f.nodeType);
if(!feeds.length){console.warn('uniSend: нет валидного фида');return}
feeds.forEach(f=>addMsg(f,'user',text));
feeds.forEach(f=>addMsg(f,'sys','⏳ обработка…'));
let reply=null,err=null;
if(LMS_MODEL){
try{
const ctrl=new AbortController();const to=setTimeout(()=>ctrl.abort(),20000);
const r=await fetch(LMS+'/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:LMS_MODEL,messages:[{role:'system',content:'Ты — ЮНИ, локальный ассистент проекта UNI. Роль: '+($('uniRole')?$('uniRole').value:'assistant')+'. Отвечай на русском, кратко, честно.'},{role:'user',content:text}],stream:false}),signal:ctrl.signal});
clearTimeout(to);
if(r.ok){const d=await r.json();reply=d.choices&&d.choices[0]&&d.choices[0].message?d.choices[0].message.content:null;if(!reply)err='LM Studio вернул пустой ответ'}
else{const t=await r.text().catch(()=>'');err='LM Studio HTTP '+r.status+': '+t.slice(0,160)}
}catch(e){err='LM Studio недоступен: '+e.message}
}
if(reply){feeds.forEach(f=>{f.lastChild.remove();addMsg(f,'uni',reply)});try{if($('speakChk').checked)speak(reply)}catch(e){};return}
try{
const ts=Date.now();
const body='# Чат с ЮНИ\nfrom: user\nto: qwen\ntitle: Чат\n\n'+text+'\n';
const w=await fetch(FS+'/write',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:'uni-qwen/outbox/chat_'+ts+'.md',content:body,participant:'qwen'})});
if(w.ok){feeds.forEach(f=>{f.lastChild.remove();addMsg(f,'sys',(err?err+'. ':'')+'Письмо Qwen отправлено через мост (до 2 мин)…')});pollReply(feeds);return}
}catch(e){}
feeds.forEach(f=>{f.lastChild.remove();addMsg(f,'sys','❌ '+(err||'нет ответа')+'. Файл-сервер 8000 тоже недоступен.')});
}
function pollReply(feeds){
const known=new Set();let tries=0;
const iv=setInterval(async()=>{
tries++;
try{
const r=await api(FS+'/list?path=uni-qwen/outbox');const d=await r.json();
if(d.ok){
if(!known.size)d.items.forEach(f=>known.add(f));
const fresh=d.items.filter(f=>!known.has(f)&&/reply|panel|chat/.test(f));
for(const f of fresh){
if(seenReplies.has(f))continue;seenReplies.add(f);
const rr=await api(FS+'/read?path=uni-qwen/outbox/'+encodeURIComponent(f));const dd=await rr.json();
if(dd.ok){clearInterval(iv);const body=dd.content.replace(/^(from|to|title):.*$/gm,'').trim();feeds.forEach(x=>{const l=x.lastChild;if(l&&l.classList.contains('sys'))l.remove();addMsg(x,'uni','[Qwen через мост] '+body.slice(0,900))});if($('speakChk').checked)speak(body.slice(0,300));return}
}}}catch(e){}
if(tries>24){clearInterval(iv);feeds.forEach(f=>addMsg(f,'sys','⚠ Ответа от Qwen нет 2 минуты. Возможно, вкладка Qwen спит — диспетчер AHK разбудит.'))}
},5000);
}
function speak(t){try{const u=new SpeechSynthesisUtterance(t);u.lang='ru-RU';speechSynthesis.speak(u)}catch(e){}}
function uniSendMain(){const i=$('mainInput');if(!i)return;const v=i.value.trim();if(!v)return;i.value='';uniSend(v,[$('mainFeed')].filter(Boolean).concat([$('sideFeed')].filter(Boolean)))}
function uniSendSide(){const i=$('sideInput');if(!i)return;const v=i.value.trim();if(!v)return;i.value='';uniSend(v,[$('sideFeed')])}
function toggleMic(){
if(!('webkitSpeechRecognition'in window)&&!('SpeechRecognition'in window)){showToast('❌ Браузер не поддерживает голосовой ввод');return}
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(micOn){ // выключаем
  micOn=false;$('micBtn').classList.remove('active');
  if(recog){try{recog.stop()}catch(e){}}
  return;
}
micOn=true;$('micBtn').classList.add('active');
recog=new SR();recog.lang='ru-RU';recog.interimResults=true;recog.continuous=false;
const inp=$('sideInput');
recog.onresult=e=>{
  let t='';for(let i=0;i<e.results.length;i++)t+=e.results[i][0].transcript;
  if(inp)inp.value=t;
};
recog.onerror=e=>{micOn=false;$('micBtn').classList.remove('active');showToast('🎤 '+(e.error==='not-allowed'?'нет доступа к микрофону':e.error==='no-speech'?'не услышал':'ошибка '+e.error))};
recog.onend=()=>{micOn=false;$('micBtn').classList.remove('active')};
try{recog.start()}catch(e){micOn=false;$('micBtn').classList.remove('active');showToast('🎤 не удалось запустить')}
}
async function startRound(){
showToast('▶ Запуск раунда через Hermes 8787…');setStep(0);
try{
const r=await fetch(HRM+'/api/round/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:$('qwTheme').value,brief:$('qwBrief').value})});
if(r.ok){$('stRound').textContent='запущен';$('qwJournal').textContent+=`\n[${now()}] раунд запущен через Hermes`;
try{const es=new EventSource(HRM+'/api/round/progress');es.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.step!=null)setStep(d.step);if(d.msg)$('qwJournal').textContent+='\n'+d.msg}catch(_){}};es.onerror=()=>{es.close()}}catch(e){}
}else{$('stRound').textContent='ошибка';showToast('❌ Hermes вернул '+r.status)}
}catch(e){setStep(-1);$('stRound').textContent='Hermes офлайн';showToast('❌ Hermes 8787 недоступен — раунд не запущен (без симуляции)')}
}
function qwStartRound(){startRound()}
function qwSendChat(){const i=$('qwCin');const v=i.value.trim();if(!v)return;i.value='';uniSend(v,[$('qwChat')])}
function emergencyStop(){setStep(-1);$('stRound').textContent='остановлен';showToast('🛑 Аварийная остановка')}
/* ===== XToys → Intiface (Buttplug JSON v4 over WebSocket) ===== */
let xtWS=null,xtId=1,xtDevices=[],xtPat=null,intensity=0.45;
function xtSend(type,msg){if(xtWS&&xtWS.readyState===1){const m={Id:++xtId};m[type]=msg;xtWS.send(JSON.stringify([m]))}}
function xtoySet(s,cls){const m=$('xStatus');m.textContent='статус: '+s;m.className='pill '+(cls||'p-warn')}
function xtoysConnect(){
if(xtWS&&xtWS.readyState===1){try{xtWS.close()}catch(e){};return}
const host=$('xtoysHost').value.trim()||'ws://127.0.0.1:12345';
xtoySet('подключение…');
try{xtWS=new WebSocket(host)}catch(e){xtoySet('ошибка: '+e.message,'p-err');return}
xtWS.onopen=()=>{xtoySet('рукопожатие…');xtSend('RequestServerInfo',{ClientName:'UNI Panel',MessageVersion:3})};
xtWS.onmessage=ev=>{let arr;try{arr=JSON.parse(ev.data)}catch(e){return}
arr.forEach(m=>{if(m.ServerInfo){xtoySet('онлайн','p-ok');$('xtoysBtn').textContent='⏸ Отключить';xtSend('RequestDeviceList',{});renderXtDevices()}
else if(m.DeviceAdded){const d=m.DeviceAdded;if(!xtDevices.find(x=>x.DeviceIndex===d.DeviceIndex))xtDevices.push(d);renderXtDevices();xtoySet('устройство: '+(d.DeviceName||'#'+d.DeviceIndex),'p-ok')}
else if(m.DeviceRemoved){xtDevices=xtDevices.filter(x=>x.DeviceIndex!==m.DeviceRemoved.DeviceIndex);renderXtDevices()}
else if(m.DeviceList){xtDevices=m.DeviceList.Devices||[];renderXtDevices()}
else if(m.Error){const em=m.Error.ErrorMessage||JSON.stringify(m.Error);if(!/DeviceList|unknown message/i.test(em))showToast('⚠ Intiface: '+em.slice(0,120))}})};
xtWS.onerror=()=>xtoySet('ошибка соединения','p-err');
xtWS.onclose=()=>{xtoySet('отключено');$('xtoysBtn').textContent='🔌 Подключить';xtDevices=[];renderXtDevices();if(xtPat){clearInterval(xtPat);xtPat=null}}
}
function renderXtDevices(){
const box=$('xtoysDevices');
if(!xtDevices.length){box.innerHTML='<span style="color:var(--text3)">устройства не обнаружены</span>';return}
box.innerHTML=xtDevices.map(d=>{const f=d.DeviceMessages||{};const caps=Object.keys(f).join(', ');return `<div style="padding:4px 0;border-top:1px solid var(--border)"><b>${esc(d.DeviceName||'device')}</b> (#${d.DeviceIndex})<br><span style="color:var(--text3)">${esc(caps)}</span></div>`}).join('')
}
function xtDeviceIdx(){const d=xtDevices.find(x=>(x.DeviceMessages&&(x.DeviceMessages.OscillateCmd||x.DeviceMessages.RotateCmd))||(x.DeviceName||'').toLowerCase().includes('rotary'));return d?d.DeviceIndex:null}
function xtoyOsc(v){const i=xtDeviceIdx();if(i===null)return false;v=Math.max(0,Math.min(1,v));xtSend('OscillateCmd',{DeviceIndex:i,Speeds:[{Index:0,Intensity:v}]});return true}
function xtoysSetIntensity(v){intensity=v;if(xtDeviceIdx()===null)return;xtoyOsc(v);xtoySet('поршень · '+Math.round(v*100)+'%','p-ok')}
function xtoysStop(){if(xtPat){clearInterval(xtPat);xtPat=null}intensity=0;xtoyOsc(0);xtoySet('стоп','p-warn')}
/* ===== Роли: подгрузка из uni/roles/*.md через Hermes API ===== */
async function loadRoles(){
try{
const r=await api(HRM+'/api/roles');const d=await r.json();
if(!d.roles||!d.roles.length){return}
const sel=$('uniRole');sel.innerHTML=d.roles.map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('');
if(d.current)sel.value=d.current;
}catch(e){showToast('⚠ Не удалось загрузить роли (Hermes 8787)')}
}
async function setRole(name){
if(!name)return;
try{await fetch(HRM+'/api/role/switch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:name})});showToast('🎭 Роль: '+name)}catch(e){showToast('⚠ Роль не сохранена: '+e.message)}
}
async function fbExec(){
const op=$('fbOp').value,path=$('fbPath').value,part=$('fbPart').value,content=$('fbContent').value,out=$('fbResult');
out.textContent='['+now()+'] '+op+' '+path+'\n';
try{
if(op==='FILE_READ'){const r=await api(FS+'/read?path='+encodeURIComponent(path));const d=await r.json();out.textContent+=d.ok?('READ_OK '+d.size+' bytes\n\n'+d.content.slice(0,3000)):('❌ '+JSON.stringify(d))}
else if(op==='FILE_LIST'){const r=await api(FS+'/list?path='+encodeURIComponent(path));const d=await r.json();out.textContent+=d.ok?('LIST_OK\n\n'+d.items.join('\n')):('❌ '+JSON.stringify(d))}
else{const r=await fetch(FS+'/write',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path,content:content,participant:part})});const d=await r.json();out.textContent+=d.ok?('WRITE_OK '+path):('❌ '+JSON.stringify(d))}
}catch(e){out.textContent+='❌ сервер 8000 недоступен: '+e.message}
}
function saveCfg(){localStorage.setItem('uni_lms',$('cfgLms').value);localStorage.setItem('uni_fs',$('cfgFs').value);localStorage.setItem('uni_hrm',$('cfgHrm').value);LMS=$('cfgLms').value;FS=$('cfgFs').value;HRM=$('cfgHrm').value;showToast('💾 Конфиг сохранён');pingServers()}
const RULES_KEY='uni_rules';
const DEFAULT_RULES=['канон uni/ только чтение','артефакты <КОД>_','статус только с доказательством','процессы не убивать','L3/L4 — явное подтверждение'];
function getRules(){try{const r=JSON.parse(localStorage.getItem(RULES_KEY));if(Array.isArray(r))return r}catch(e){}return DEFAULT_RULES.slice()}
function renderRules(){const list=$('rulesList');if(!list)return;const rules=getRules();list.innerHTML=rules.map((t,i)=>`<div class="rule-row"><span class="rule-text" ondblclick="editRule(${i})">${esc(t)}</span><button class="rbtn" onclick="editRule(${i})">✎</button><button class="rbtn del" onclick="delRule(${i})">🗑</button></div>`).join('')||'<div style="font-size:12px;color:var(--text3)">нет правил</div>'}
function saveRules(r){localStorage.setItem(RULES_KEY,JSON.stringify(r));renderRules();showToast('⚖ Правила сохранены')}
function addRule(){const t=(prompt('Новое правило, которому следует ЮНИ:')||'').trim();if(!t)return;const r=getRules();r.push(t);saveRules(r)}
function editRule(i){const r=getRules();const v=(prompt('Изменить правило:',r[i])||'').trim();if(!v)return;r[i]=v;saveRules(r)}
function delRule(i){const r=getRules();if(!confirm('Удалить правило «'+r[i]+'»?'))return;r.splice(i,1);saveRules(r)}
function moveCursor(x,y){const c=$('uniCursor');c.classList.add('moving');c.style.left=x+'%';c.style.top=y+'%';setTimeout(()=>c.classList.remove('moving'),600)}
setInterval(()=>{if($('view-browser').classList.contains('active'))moveCursor(15+Math.random()*70,15+Math.random()*60)},5000);
setInterval(()=>{pingServers();loadLogs();loadMail()},15000);
setTheme(localStorage.getItem('uni_theme')||'light');
pingServers();runRollCall();loadLogs();loadBoard();loadMail();loadDocs();loadStats();renderRules();loadRoles();
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='l'){e.preventDefault();startRound()}});
/* ===== Анимированная favicon: U → N → i (смена href у <link rel=icon>) ===== */
(function(){
  const favEl=document.getElementById('dynFav');
  if(!favEl)return;
  const seq=['convertico-256-ico-uni.ico','convertico-256-ico-uni-2.ico','convertico-256-ico-uni-3.ico'];
  let i=0;
  setInterval(()=>{
    i=(i+1)%seq.length;
    favEl.href=seq[i]+'?t='+Date.now(); // ?t= обходит кэш браузера
  },3600);
})();
showToast('UNI Platform v3.3: темы #c4e534/#032121 + авто-детект модели LM Studio');