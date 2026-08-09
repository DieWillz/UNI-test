let FS=localStorage.getItem('uni_fs')||'http://127.0.0.1:8000';
let HRM=localStorage.getItem('uni_hrm')||'http://127.0.0.1:8787';
let LMS=localStorage.getItem('uni_lms')||'http://127.0.0.1:1234';
let LMS_MODEL='';
let currentRolePrompt='';
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
function showView(v,el){document.querySelectorAll('.view-wrap').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));const w=$('view-'+v);if(w)w.classList.add('active');if(el)el.classList.add('active');if(v==='xtoys'){xtoysSessionPoll();intifacePoll();xtoysPatternPoll()}}
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
const sysPrompt=currentRolePrompt||('Ты — ЮНИ, локальный ассистент проекта UNI. Роль: '+($('uniRole')?$('uniRole').value:'assistant')+'. Отвечай на русском, кратко, честно.');
const r=await fetch(LMS+'/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:LMS_MODEL,messages:[{role:'system',content:sysPrompt},{role:'user',content:text}],stream:false}),signal:ctrl.signal});
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
let _ttsAudio=null,_ttsEngines={};
const TTS_VOICE_FALLBACKS={silero:[['xenia','Xenia — спокойная'],['kseniya','Kseniya — ясная'],['baya','Baya — мягкая'],['eugene','Eugene — мужской'],['aidar','Aidar — глубокий мужской']],piper:[['ru_RU-irina-medium.onnx','Irina Medium — офлайн']],browser:[['','Системный русский голос']],xtts:[['default','XTTS-v2 — голос сервера']],fish:[['default','Fish Audio — выразительный']],qwen_vc:[['cloned','Клонированный голос (Qwen VC)'],['default','Qwen Voice Clone — стандартный']]};
function ttsPref(){return{provider:localStorage.getItem('uni_tts_provider')||'silero',voice:localStorage.getItem('uni_tts_voice')||'xenia',endpoint:localStorage.getItem('uni_tts_endpoint')||'',rate:Number(localStorage.getItem('uni_tts_rate')||1),pitch:Number(localStorage.getItem('uni_tts_pitch')||0),volume:Number(localStorage.getItem('uni_tts_volume')||1),qwenRefAudio:localStorage.getItem('uni_qwen_ref_audio')||'',qwenRefText:localStorage.getItem('uni_qwen_ref_text')||'',qwenModelSize:localStorage.getItem('uni_qwen_model_size')||'1.7B',testText:localStorage.getItem('uni_tts_test_text')||'Привет! Я Юни. Рада тебя слышать — давай сделаем что-нибудь интересное.'}}
function saveTtsPref(){
const p=$('ttsProvider').value,v=$('ttsVoice').value,endpoint=$('ttsEndpoint').value.trim(),rate=Number($('ttsRate').value),pitch=Number($('ttsPitch').value),volume=Number($('ttsVolume').value);
const qa=$('qwenRefAudio')?$('qwenRefAudio').value.trim():'',qt=$('qwenRefText')?$('qwenRefText').value.trim():'',qm=$('qwenModelSize')?$('qwenModelSize').value.trim():'1.7B';
localStorage.setItem('uni_tts_provider',p);localStorage.setItem('uni_tts_voice',v);localStorage.setItem('uni_tts_endpoint',endpoint);localStorage.setItem('uni_tts_rate',rate);localStorage.setItem('uni_tts_pitch',pitch);localStorage.setItem('uni_tts_volume',volume);localStorage.setItem('uni_qwen_ref_audio',qa);localStorage.setItem('uni_qwen_ref_text',qt);localStorage.setItem('uni_qwen_model_size',qm);localStorage.setItem('uni_tts_test_text',$('ttsTestText').value);
$('ttsRateValue').textContent=rate.toFixed(2)+'×';$('ttsPitchValue').textContent=(pitch>0?'+':'')+pitch;$('ttsVolumeValue').textContent=Math.round(volume*100)+'%';
}
function setVoiceOptions(provider,selected){const list=(_ttsEngines[provider]&&_ttsEngines[provider].voices||[]).map(x=>[x.id,x.label]);const voices=list.length?list:(TTS_VOICE_FALLBACKS[provider]||[]);$('ttsVoice').innerHTML=voices.map(x=>'<option value="'+esc(x[0])+'">'+esc(x[1])+'</option>').join('');if(voices.some(x=>x[0]===selected))$('ttsVoice').value=selected;}
function onTtsProviderChange(){const p=$('ttsProvider').value,old=ttsPref();setVoiceOptions(p,old.provider===p?old.voice:'');$('ttsEndpointRow').style.display=(p==='xtts'||p==='fish'||p==='qwen_vc')?'flex':'none';if(p==='qwen_vc'&&!$('ttsEndpoint').value.trim())$('ttsEndpoint').value='http://127.0.0.1:7860';['qwenVcRow','qwenVcRow2','qwenVcRow3'].forEach(id=>{const el=$(id);if(el)el.style.display=(p==='qwen_vc')?'flex':'none'});const info=_ttsEngines[p];$('ttsEngineDetail').textContent=info?(info.available?'● '+info.detail:'○ '+info.detail):'Состояние движка пока не проверено';saveTtsPref();}
async function loadTtsSettings(){const pr=ttsPref();$('ttsProvider').value=pr.provider;$('ttsEndpoint').value=pr.endpoint;$('ttsRate').value=pr.rate;$('ttsPitch').value=pr.pitch;$('ttsVolume').value=pr.volume;$('ttsTestText').value=pr.testText;if($('qwenRefAudio'))$('qwenRefAudio').value=pr.qwenRefAudio;if($('qwenRefText'))$('qwenRefText').value=pr.qwenRefText;if($('qwenModelSize'))$('qwenModelSize').value=pr.qwenModelSize;try{const r=await fetch(HRM+'/api/tts/engines');if(r.ok){const d=await r.json();(d.engines||[]).forEach(x=>_ttsEngines[x.id]=x)}}catch(e){}setVoiceOptions(pr.provider,pr.voice);onTtsProviderChange();$('ttsTestStatus').textContent='готов';}
function stopVoice(){if(_ttsAudio){_ttsAudio.pause();_ttsAudio.currentTime=0;_ttsAudio=null}try{speechSynthesis.cancel()}catch(e){}const st=$('ttsTestStatus');if(st){st.textContent='остановлено';st.className='pill'}}
function browserSpeak(t,pr){try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(t);u.lang='ru-RU';u.rate=pr.rate;u.pitch=Math.max(0,Math.min(2,1+pr.pitch/12));u.volume=Math.max(0,Math.min(1,pr.volume));const voices=speechSynthesis.getVoices().filter(v=>v.lang&&v.lang.toLowerCase().startsWith('ru'));if(pr.voice){const found=voices.find(v=>v.name===pr.voice);if(found)u.voice=found}speechSynthesis.speak(u);return true}catch(e){showToast('❌ Голос браузера: '+e.message);return false}}
async function requestSpeech(t,testing){const pr=ttsPref(),st=$('ttsTestStatus');if(testing){st.textContent='синтез…';st.className='pill p-warn'}
try{const r=await fetch(HRM+(testing?'/api/tts/test':'/api/tts'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t,provider:pr.provider,voice:pr.voice,endpoint:pr.endpoint,rate:pr.rate,pitch:pr.pitch,volume:pr.volume,qwen_ref_audio:pr.qwenRefAudio,qwen_ref_text:pr.qwenRefText,qwen_model_size:pr.qwenModelSize})});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||('HTTP '+r.status));stopVoice();if(d.browser){browserSpeak(t,pr)}else if(d.audio_url){_ttsAudio=new Audio(new URL(d.audio_url,HRM).href);_ttsAudio.volume=Math.max(0,Math.min(1,pr.volume));await _ttsAudio.play()}else throw new Error('сервер не вернул аудио');if(testing){st.textContent='голос работает ✓';st.className='pill p-ok';if(d.controls_note)$('ttsEngineDetail').textContent=d.controls_note}return true}catch(e){if(testing){st.textContent='ошибка: '+e.message;st.className='pill p-err'}showToast('❌ TTS: '+e.message);return false}}
function testVoice(){saveTtsPref();const t=$('ttsTestText').value.trim()||ttsPref().testText;requestSpeech(t,true)}
function speak(t){if(t&&t.trim())requestSpeech(t.trim(),false)}
/* ===== Лёгкий непрерывный голос в чате (без устройств/vision) ===== */
let _voiceTimer=null;
async function voiceLoopTick(){
try{
const prompt=(currentRolePrompt?currentRolePrompt+'\n':'')+'Скажи ОДНУ короткую (1-2 предложения) фразу в своём образе, продолжай диалог. Без пояснений, только реплика.';
const ctrl=new AbortController();
const r=await fetch(LMS+'/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:LMS_MODEL,messages:[{role:'system',content:prompt},{role:'user',content:'говори'}],stream:false}),signal:ctrl.signal});
const d=await r.json();
let text='';
if(d&&d.choices&&d.choices[0]&&d.choices[0].message)text=d.choices[0].message.content;
if(text&&text.trim()){const feed=$('sideFeed');if(feed){const m=document.createElement('div');m.className='msg uni';m.innerHTML='<div class="who">ЮНИ · '+now()+'</div>'+esc(text.trim());feed.appendChild(m);feed.scrollTop=feed.scrollHeight;}speak(text.trim());}
}catch(e){/* тихо пропускаем сбой сети */}
}
function toggleVoiceAuto(){const on=!window._voiceAutoOn;if(on)startVoiceLoop();else stopVoiceLoop();window._voiceAutoOn=on;const b=$('voiceAutoBtn'),s=$('voiceAutoStatus');if(b)b.textContent=on?'⏸ Стоп голоса':'🎙 Голосовой авторежим';if(s){s.textContent=on?'вкл':'выкл';s.className='pill '+(on?'p-ok':'p-warn');}}
function startVoiceLoop(){if(_voiceTimer)return;const sec=Math.max(4,parseInt($('voiceLoopSec').value||'25',10)||25);voiceLoopTick();_voiceTimer=setInterval(voiceLoopTick,sec*1000);showToast('🔁 Непрерывный голос включён');}
function stopVoiceLoop(){if(_voiceTimer){clearInterval(_voiceTimer);_voiceTimer=null;showToast('⏸ Непрерывный голос выключен');}}

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
/* ===== Роли: подгрузка из uni/roles/*.md через Hermes API ===== */
async function loadRoles(){
try{
const r=await api(HRM+'/api/roles');const d=await r.json();
if(!d.roles||!d.roles.length){return}
const sel=$('uniRole');sel.innerHTML=d.roles.map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('');
if(d.current)sel.value=d.current;
// жёстко подхватываем system-промпт выбранной роли из файла
try{const pr=await api(HRM+'/api/role/prompt?role='+encodeURIComponent(sel.value));const pd=await pr.json();if(pd&&pd.prompt)currentRolePrompt=pd.prompt}catch(e){}
}catch(e){showToast('⚠ Не удалось загрузить роли (Hermes 8787)')}
}
async function setRole(name){
if(!name)return;
try{await fetch(HRM+'/api/role/switch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:name})});
// жёстко подхватываем system-промпт роли из файла
try{const pr=await api(HRM+'/api/role/prompt?role='+encodeURIComponent(name));const pd=await pr.json();if(pd&&pd.prompt)currentRolePrompt=pd.prompt}catch(e){}
showToast('🎭 Роль: '+name)}catch(e){showToast('⚠ Роль не сохранена: '+e.message)}
}
/* ===== Автономный режим: слушаем SSE и показываем/озвучиваем фразы ЮНИ ===== */
function initAutonomousStream(){
const feed=$('sideFeed');if(!feed)return;
if(window._autonomousES)return; // уже подписаны
try{
const es=new EventSource(HRM+'/api/autonomous/stream');
window._autonomousES=es;
es.onmessage=ev=>{try{
const d=JSON.parse(ev.data);
if(d&&d.type==='phrase'){
const m=document.createElement('div');m.className='msg uni';
m.innerHTML='<div class="who">ЮНИ · '+now()+'</div>'+esc(d.text);
feed.appendChild(m);feed.scrollTop=feed.scrollHeight;
if(d.audio_url){const a=new Audio(d.audio_url);a.play().catch(()=>{});}
else if($('speakChk').checked)speak(d.text);
}
}catch(e){}};
es.onerror=()=>{/* сервер не запущен авто-режим — тихо ждём */};
}catch(e){}
}
/* ===== Кнопка «Авто-режим» на вкладке XToys ===== */
function toggleAutoMode(){
const btn=$('autoBtn'),st=$('autoStatus');
const starting=!window._autoOn;
btn.disabled=true;
fetch(HRM+(starting?'/api/xtoys/session/start':'/api/xtoys/session/stop'),{method:'POST'})
.then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d})
.then(d=>{
window._autoOn=starting;
if(btn)btn.textContent=starting?'⏸ Стоп сессии':'⚡ Авто-режим';
if(st){st.textContent=starting?'вкл':'выкл';st.className='pill '+(starting?'p-ok':'p-warn');}
if(starting)showToast('⚡ Сессия: ЮНИ говорит и крутит машинку');
else showToast('⏸ Сессия остановлена');
if(starting)xtoysSessionPoll();
})
.catch(e=>{showToast('⚠ Сессия: '+e.message);})
.finally(()=>{btn.disabled=false});
}
function xtoysSessionStop(){
fetch(HRM+'/api/xtoys/session/stop',{method:'POST'}).then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||('HTTP '+r.status));window._autoOn=false;const btn=$('autoBtn'),st=$('autoStatus');if(btn)btn.textContent='⚡ Авто-режим';if(st){st.textContent='выкл';st.className='pill p-warn';}$('xtSessionStatus').textContent='остановлена';showToast('■ XToys остановлен')}).catch(e=>showToast('⚠ Стоп XToys: '+e.message));
}
function xtoysSetIntensity(){
const v=parseInt($('xtIntensity').value||'0',10)||0;
fetch(HRM+'/api/xtoys/session/intensity',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:v})})
.then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok||!d.ok)throw new Error(d.error||d.message||('HTTP '+r.status));return d}).then(d=>{if(d.message)showToast('🎚 '+d.message);}).catch(e=>showToast('⚠ Интенсивность: '+e.message));
}
let _xtPoll=null;
function xtoysSessionPoll(){
if(_xtPoll)clearInterval(_xtPoll);
const poll=()=>fetch(HRM+'/api/xtoys/session/status').then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d}).then(d=>{const s=$('xtSessionStatus'),st=$('autoStatus'),btn=$('autoBtn');if(s)s.textContent=d.status||'неизвестно';window._autoOn=!!d.active;if(st){st.textContent=d.active?'вкл':'выкл';st.className='pill '+(d.active?'p-ok':'p-warn')}if(btn)btn.textContent=d.active?'⏸ Стоп сессии':'⚡ Авто-режим'}).catch(e=>{$('xtSessionStatus').textContent='ошибка: '+e.message});
poll();_xtPoll=setInterval(poll,2000);
}
function intifaceConnect(){
const url=$('intifaceUrl').value.trim()||'ws://127.0.0.1:12345';
fetch(HRM+'/api/intiface/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:url})})
.then(r=>r.ok?r.json():Promise.reject(new Error('HTTP '+r.status+(r.status===404?' (сервер старый — перезапусти start-uni.bat)':''))))
.then(d=>{
if(d&&d.connecting){showToast('🔌 подключение к Intiface…');intifacePoll();}
else if(d&&d.ok){showToast('🔌 Intiface подключён'+(d.devices?(': '+d.devices.join(', ')):''));intifacePoll();}
else{const st=$('intifaceStatus');if(st){st.textContent='ошибка';st.className='pill p-err';}showToast('⚠ Intiface: '+(d&&d.error?d.error:'не удалось'));}
})
.catch(e=>showToast('⚠ Intiface connect: '+e.message));
}
let _intfPoll=null;
function intifacePoll(){
if(_intfPoll)clearInterval(_intfPoll);
const poll=()=>{
fetch(HRM+'/api/intiface/status').then(r=>r.ok?r.json():Promise.reject()).then(d=>{
const st=$('intifaceStatus');
if(d&&d.connected&&Number.isFinite(Number(d.value))){const v=Number(d.value);$('oscRange').value=v;$('oscVal').textContent=v+'%';$('xtIntensity').value=v;$('xtIntVal').textContent=v+'%';}
if(d&&d.connected){if(st){st.textContent='подключено';st.className='pill p-ok';}if(d.devices)$('intifaceDevices').textContent=d.devices.join(', ');}
else if(st&&st.textContent!=='ошибка'){st.textContent='отключено';st.className='pill p-warn';}
if(d&&d.last_error&&st){st.textContent='ошибка';st.className='pill p-err';}
}).catch(()=>{});
};poll();_intfPoll=setInterval(poll,2000);
}
function xtoysPattern(name){
const dur=parseFloat($('patDur').value||'20')||20;
const inten=parseInt($('patInt').value||'70',10)||70;
fetch(HRM+'/api/xtoys/pattern/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,duration:dur,intensity:inten})})
.then(r=>r.ok?r.json():Promise.reject(new Error('HTTP '+r.status)))
.then(d=>{showToast('🎚 паттерн «'+name+'» запущен ('+dur+'с, '+inten+'%)');xtoysPatternPoll();})
.catch(e=>showToast('⚠ Паттерн: '+e.message));
}
function xtoysPatternStop(){
fetch(HRM+'/api/xtoys/pattern/stop',{method:'POST'}).then(()=>{const s=$('xtPatternStatus');if(s)s.textContent='выключен';}).catch(()=>{});
}
let _patPoll=null;
function xtoysPatternPoll(){
if(_patPoll)clearInterval(_patPoll);
const poll=()=>{
fetch(HRM+'/api/xtoys/pattern/status').then(r=>r.ok?r.json():Promise.reject()).then(d=>{
const s=$('xtPatternStatus');
if(Number.isFinite(Number(d.last_value))){const v=Number(d.last_value);$('oscRange').value=v;$('oscVal').textContent=v+'%';$('xtIntensity').value=v;$('xtIntVal').textContent=v+'%';}
if(s)s.textContent=d.running?(d.name+' · '+d.last_value+'% · '+d.step):'выключен';
}).catch(()=>{});
};poll();_patPoll=setInterval(poll,1500);
}
function intifaceDisconnect(){fetch(HRM+'/api/intiface/disconnect',{method:'POST'}).then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok||!d.ok)throw new Error(d.error||('HTTP '+r.status));if(_intfPoll){clearInterval(_intfPoll);_intfPoll=null}const st=$('intifaceStatus');if(st){st.textContent='отключено';st.className='pill p-warn'}$('intifaceDevices').textContent='—';showToast('Intiface отключён')}).catch(e=>showToast('⚠ Отключение: '+e.message));}
function intifaceOscillate(){
const v=parseInt($('oscRange').value||'0',10)||0;
fetch(HRM+'/api/intiface/oscillate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:v})})
.then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok||!d.ok)throw new Error(d.error||('HTTP '+r.status));return d}).then(d=>showToast('▶ '+(d.device||'устройство')+': '+v+'%')).catch(e=>showToast('⚠ Oscillate: '+e.message));
}
function intifaceStop(){fetch(HRM+'/api/intiface/stop',{method:'POST'}).then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok||!d.ok)throw new Error(d.error||('HTTP '+r.status));$('oscRange').value=0;$('oscVal').textContent='0%';showToast('■ Устройство остановлено')}).catch(e=>showToast('⚠ Стоп: '+e.message));}
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
pingServers();runRollCall();loadLogs();loadBoard();loadMail();loadDocs();loadStats();renderRules();loadRoles();initAutonomousStream();loadTtsSettings();
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
