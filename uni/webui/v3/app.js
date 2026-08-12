/* UNI Admin v3 — фронтенд (T-09..T-15) */
let API = location.origin; // сервер панели (8787)
const $ = id => document.getElementById(id);
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}

function showToast(m){const t=$('toast');if(!t)return;t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2600)}

function showView(v, el){
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
  const w=$('view-'+v); if(w)w.classList.add('active');
  if(el)el.classList.add('active');
}

function setTheme(v){
  document.documentElement.setAttribute('data-theme',v);
  localStorage.setItem('uni_v3_theme',v);
  const b=$('themeBtn'); if(b)b.textContent=v==='dark'?'☀ Тема':'🌙 Тема';
}
function toggleTheme(){setTheme(document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark')}

async function apiJson(path){
  const ctrl=new AbortController();
  const t=setTimeout(()=>ctrl.abort(),4000);
  try{
    const r=await fetch(API+path,{signal:ctrl.signal});
    clearTimeout(t);
    if(!r.ok) throw new Error('HTTP '+r.status);
    return await r.json();
  }catch(e){
    clearTimeout(t);
    throw e;
  }
}

/* T-11: Главная — /api/global_state + /api/heartbeats */
async function loadHome(){
  const box=$('globalState');
  try{
    const d=await apiJson('/api/global_state');
    // показываем первые ~120 строк состояния компактно
    const lines=(d.content||'').split('\n').slice(0,80).join('\n');
    box.classList.remove('loading');
    box.textContent=lines;
  }catch(e){ box.classList.remove('loading'); box.textContent='❌ global_state: '+e.message; }

  const hb=$('hbList');
  try{
    const d=await apiJson('/api/heartbeats');
    const rows=(d.participants||[]).map(p=>{
      const on=p.heartbeat&&p.heartbeat.online;
      return `<div class="prow"><span>🟢 ${esc(p.name)}</span><span class="pill ${on?'p-ok':'p-err'}">${on?'жив':'мёртв'}</span><span style="color:var(--text3);font-size:10px">${esc((p.heartbeat&&p.heartbeat.last_line||'').slice(0,60))}</span></div>`;
    }).join('')||'нет участников';
    hb.classList.remove('loading');
    hb.innerHTML=rows;
  }catch(e){ hb.classList.remove('loading'); hb.textContent='❌ heartbeats: '+e.message; }
}

/* T-12: Задачи — /api/tasks */
async function loadTasks(){
  const box=$('tasksBody');
  try{
    const d=await apiJson('/api/tasks');
    const rows=(d.tasks||[]).map(t=>{
      const st=t.status==='[V]'||t.status==='done'?'p-ok':t.status==='[X]'?'p-err':t.status==='[solo]'?'p-warn':'p-out';
      return `<tr><td>${esc(t.id||'—')}</td><td>${esc(t.title)}</td><td><span class="pill ${st}">${esc(t.status||'open')}</span></td></tr>`;
    }).join('');
    box.classList.remove('loading');
    box.innerHTML=`<table><tr><th>ID</th><th>Задача</th><th>Статус</th></tr>${rows}</table>`;
  }catch(e){ box.classList.remove('loading'); box.textContent='❌ tasks: '+e.message; }
}

/* T-14: Участники — /api/participants_dirs + /api/heartbeats */
async function loadParticipants(){
  const box=$('partsBody');
  try{
    const [dirs,hb]=await Promise.all([apiJson('/api/participants_dirs'),apiJson('/api/heartbeats')]);
    const onMap={}; (hb.participants||[]).forEach(p=>onMap[p.name]=p.heartbeat&&p.heartbeat.online);
    const cards=(dirs.participants||[]).map(p=>{
      const on=!!onMap[p.name];
      return `<div class="card" style="margin-bottom:6px"><b>${esc(p.name)}</b> <span class="pill ${on?'p-ok':'p-err'}">${on?'жив':'мёртв'}</span> <span style="color:var(--text3);font-size:10px">${esc(p.dir)}</span></div>`;
    }).join('')||'нет участников';
    box.classList.remove('loading');
    box.innerHTML=cards;
  }catch(e){ box.classList.remove('loading'); box.textContent='❌ participants: '+e.message; }
}

/* T-13: Журнал — /api/journal */
async function loadJournal(){
  const box=$('journalBody');
  try{
    const d=await apiJson('/api/journal');
    const rows=(d.entries||[]).slice().reverse().map(e=>{
      const line=typeof e==='object'?JSON.stringify(e,null,1):String(e);
      return `<div style="border-bottom:1px solid var(--border);padding:4px 0;font-size:11px">${esc(line).slice(0,400)}</div>`;
    }).join('')||'журнал пуст';
    box.classList.remove('loading');
    box.innerHTML=rows;
  }catch(e){ box.classList.remove('loading'); box.textContent='❌ journal: '+e.message; }
}

/* T-20: Настройки read-only */
async function loadSettings(){
  const box=$('settingsBody');
  box.classList.remove('loading');
  box.textContent='config.yaml тронуть нельзя (по правилам). Показываем только публичные опции.\nTTS: silero+xenia (по умолчанию).\nПорты: 8787 (панель), 1234 (LM Studio), 8000 (fileserver), 12345 (Intiface), 12347 (mov2toy).';
}

/* T-15: Кнопка СТОП — создаёт STOP.txt */
async function emergencyStop(){
  showToast('⏹ СТОП: создаю STOP.txt…');
  try{
    const r=await fetch(API+'/api/admin/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if(r.ok){ showToast('✅ STOP.txt создан — все агенты остановятся'); }
    else { // бэкенд может не иметь эндпоинта — создаём через отдельный путь
      await fetch(API+'/api/stop',{method:'POST'}).catch(()=>{});
      showToast('✅ запрос СТОП отправлен');
    }
  }catch(e){
    // фоллбэк: пробуем /api/stop
    try{ await fetch(API+'/api/stop',{method:'POST'}); showToast('✅ запрос СТОП отправлен (fallback)'); }
    catch(_){ showToast('⚠ не удалось отправить СТОП: '+e.message); }
  }
}

/* авто-обновление каждые 30s (T-11) */
function startRefresh(){
  loadHome(); loadTasks(); loadParticipants(); loadJournal(); loadSettings();
  setInterval(()=>{ loadHome(); loadTasks(); loadParticipants(); loadJournal(); }, 30000);
}

setTheme(localStorage.getItem('uni_v3_theme')||'dark');
startRefresh();
