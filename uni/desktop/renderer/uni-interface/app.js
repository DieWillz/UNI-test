const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const widget = $('#uniWidget');
const avatar = $('#avatar');
const toast = $('#toast');
const state = { mode:'quick', stopped:false, observing:true, listening:false, minimized:false, avatar:'working' };

function notify(text){toast.textContent=text;toast.classList.add('show');clearTimeout(notify.t);notify.t=setTimeout(()=>toast.classList.remove('show'),1800)}
function setAvatar(next){state.avatar=next;avatar.className=`avatar avatar--${next}`;avatar.setAttribute('aria-label',`Состояние Юни: ${next}`)}
function setMode(mode){
  state.mode=mode; widget.classList.toggle('mode-quick',mode==='quick');widget.classList.toggle('mode-mission',mode==='mission');
  $('#quickMode').classList.toggle('hidden',mode!=='quick');$('#missionMode').classList.toggle('hidden',mode!=='mission');
  $$('.demo-switcher button').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));
  $('#headerStatus').textContent=state.stopped?'Остановлена':mode==='quick'?'Выполняю':'Работаю';setAvatar('working');
  window.dispatchEvent(new CustomEvent('uni:mode-change',{detail:{mode}}));
}
function setStatus(text, avatarState='working'){ $('#headerStatus').textContent=text; setAvatar(avatarState); }
function setQuickTask(data={}){if(data.action)$('#quickAction').textContent=data.action;if(data.progress!=null)$('#quickProgress').style.width=`${data.progress}%`;setStatus(data.status||'Выполняю',data.avatar||'working')}
function setMission(data={}){if(data.action)$('#missionAction').textContent=data.action;if(data.percent!=null)$('#missionPercent').textContent=`${data.percent}%`;setStatus(data.status||'Работаю',data.avatar||'working')}

$$('.demo-switcher button').forEach(b=>b.onclick=()=>setMode(b.dataset.mode));
$$('.collapse-button').forEach(b=>b.onclick=()=>{const el=document.getElementById(b.dataset.collapse);el.classList.toggle('hidden');b.textContent=el.classList.contains('hidden')?'⌄':'⌃'});
$('#stopButton').onclick=()=>{state.stopped=!state.stopped;$('#stopButton').textContent=state.stopped?'ПУСК':'STOP';setStatus(state.stopped?'Остановлена':'Продолжаю',state.stopped?'waiting':'working');notify(state.stopped?'Задача остановлена':'Задача продолжена');window.dispatchEvent(new CustomEvent('uni:stop',{detail:{stopped:state.stopped}}))};
$('#visionButton').onclick=()=>{state.observing=!state.observing;$('#visionButton').classList.toggle('active',state.observing);notify(state.observing?'Наблюдение включено':'Наблюдение выключено')};
function toggleListening(){state.listening=!state.listening;$('#micButton').classList.toggle('active',state.listening);$('#composerMic').classList.toggle('active',state.listening);setStatus(state.listening?'Слушаю':state.mode==='quick'?'Выполняю':'Работаю',state.listening?'listening':'working')}
$('#micButton').onclick=toggleListening;$('#composerMic').onclick=toggleListening;
$('#minimizeButton').onclick=()=>{state.minimized=!state.minimized;widget.classList.toggle('minimized',state.minimized);$('#minimizeButton').textContent=state.minimized?'□':'−';setAvatar(state.minimized?'idle':'working')};
function togglePopover(selector,button){const p=$(selector);p.classList.toggle('hidden');button?.setAttribute('aria-expanded',String(!p.classList.contains('hidden')))}
$('#statusButton').onclick=()=>togglePopover('#statusPopover',$('#statusButton'));$('#settingsButton').onclick=()=>togglePopover('#settingsPopover');
$('#themeButton').onclick=()=>{const light=document.documentElement.dataset.theme!=='light';document.documentElement.dataset.theme=light?'light':'dark';$('#themeButton').textContent=light?'☀ Светлая':'☾ Тёмная';document.documentElement.style.setProperty('--shell',light?'235,240,238':'11,17,21');document.documentElement.style.setProperty('--text',light?'#18201c':'#f2f4ef');document.documentElement.style.setProperty('--muted',light?'#68736e':'#8d989a');notify('Тема переключена')};
$('#opacityInput').oninput=e=>document.documentElement.style.setProperty('--opacity',e.target.value/100);
$('#motionInput').onchange=e=>document.body.classList.toggle('no-motion',!e.target.checked);
$('#notifyButton').onclick=()=>{setAvatar('waiting');notify('Юни сообщит, когда понадобится решение')};
function send(){const input=$('#messageInput');const text=input.value.trim();if(!text)return;input.value='';notify('Сообщение отправлено');setStatus('Обрабатываю','working');window.dispatchEvent(new CustomEvent('uni:message',{detail:{text}}))}
$('#sendButton').onclick=send;$('#messageInput').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}};

// Публичный мост: реальный backend/Electron может обновлять UI без доступа к DOM.
window.UNIInterface={setMode,setStatus,setAvatar,setQuickTask,setMission,notify,getState:()=>({...state})};
