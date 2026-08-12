"use strict";
const $=s=>document.querySelector(s);
const el=(t,c)=>{const e=document.createElement(t);if(c)e.className=c;return e;};
const esc=s=>String(s??"").replace(/[&<>"]/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));
const transportLabel=t=>t==="api"?"API":t==="codex"?"Codex CLI":"браузер · free";
const statusLabel=s=>({ready:"готов",configured:"настроен",unavailable:"недоступен",disabled:"отключён"}[s]||s||"неизвестно");
const PAL=["#f6a11c","#4ade80","#6fc3ef","#c4b5fd","#f472b6","#facc15","#2dd4bf","#fb7185"];
const tag=(txt,cls)=>{const s=el("span","tag "+cls);s.textContent=txt;return s;};

const TEMPLATES={
status:{topic:"Проверка статуса ИИ",brief:"Ответь одной короткой фразой (до 15 слов): подтверди, что ты на связи и готов работать в совете UNI. Формат: «<Имя>: доступен, готов». Без пояснений."},
concept:{topic:"Согласование концепции",brief:"Проверьте концепцию. Если согласны — поставьте подпись: Имя = ваша редакция; подписываюсь под концепцией."},
audit:{topic:"Аудит кода",brief:"Проведите аудит предложенного кода. Найдите риски, уязвимости и что можно улучшить."},
feature:{topic:"Разработка функции",brief:"Предложите реализацию функции. Опишите API, крайние случаи и тесты."},
bug:{topic:"Поиск ошибки",brief:"Найдите причину ошибки в описанном сценарии и предложите фикс."},
free:{topic:"Свободное задание",brief:"Опишите задачу свободно — что нужно сделать или обсудить."}
};
/* демо-состав (если бэкенд не отвечает) */
const FALLBACK_AGENTS=[
{name:"DeepSeek", role:"Algorithms Engineer", transport:"browser",status:"ready", host:"chat.deepseek.com",cdp:true, tab:true},
{name:"QWEN", role:"Consensus editor", transport:"browser",status:"ready", host:"chat.qwen.ai", cdp:true, tab:true},
{name:"Qwen Coder", role:"Code implementation", transport:"browser",status:"ready", host:"chat.qwen.ai", cdp:true, tab:true},
{name:"Claude", role:"Critic / ethics", transport:"browser",status:"ready", host:"claude.ai", cdp:true, tab:true},
{name:"ChatGPT", role:"General reviewer", transport:"codex", status:"unavailable",detail:"Codex CLI не установлен",cdp:false,tab:false},
{name:"Grok", role:"Reality-check", transport:"browser",status:"ready", host:"grok.com", cdp:true, tab:true},
{name:"Gemini", role:"Risk analyst", transport:"api", status:"ready", cdp:false,tab:false},
{name:"Groq", role:"Fast inference", transport:"api", status:"ready", cdp:false,tab:false},
{name:"OpenRouter", role:"Fallback model", transport:"api", status:"ready", cdp:false,tab:false},
{name:"HuggingFace", role:"Open weights", transport:"api", status:"ready", cdp:false,tab:false},
{name:"Hermes", role:"Local server", transport:"api", status:"ready", host:"127.0.0.1:11434",cdp:false,tab:false}
];
let AGENTS=[],EP_CONFIG={},BACKEND_OK=false;
const state={};
let running=false;
let currentRound={id:null,synthesis:"",reportPath:null,signatures:{},errors:{}};
let reportViewing=false,newAnswersWhileViewing=0;
let autoMode="off";
let activeNames=null;
let doneCount=0,totalCount=0;
let pendingSummary=0;
const files=[];
const demoReports={};
let localHistory=[];
/* =====================================================================
ЖИВАЯ ПРОВЕРКА CDP: реальный probe порта 9222 + список вкладок DevTools
===================================================================== */
let cdpProbeOk=false;
async function probeCDP(){
try{
const ctl=new AbortController();const to=setTimeout(()=>ctl.abort(),1500);
await fetch("http://127.0.0.1:9222/json/version",{mode:"no-cors",cache:"no-store",signal:ctl.signal});
clearTimeout(to);return true;
}catch(e){return false;}
}
async function fetchCDPTabs(){
try{
const ctl=new AbortController();const to=setTimeout(()=>ctl.abort(),1500);
const r=await fetch("http://127.0.0.1:9222/json",{cache:"no-store",signal:ctl.signal});
clearTimeout(to);
if(!r.ok)return null;
const j=await r.json();return Array.isArray(j)?j:null;
}catch(e){return null;}
}
async function refreshBrowserStatus(){
const [probe,tabs]=await Promise.all([probeCDP(),fetchCDPTabs()]);
cdpProbeOk=probe||!!tabs;
AGENTS.forEach(a=>{
const st=state[a.name];if(!st||a.transport!=="browser")return;
const d=String(a.detail||"");
const host=String(a.host||"");
const tabByCdp=(tabs&&host)?tabs.some(t=>String(t.url||"").includes(host)):false;
const tabOk=a.tab===true||tabByCdp||
(host&&d.toLowerCase().includes(host.toLowerCase()))||
/open tab|вкладка найдена/i.test(d);
const cdpOk=a.cdp===true||cdpProbeOk||/open tab found|вкладка найдена/i.test(d);
st.cdpOk=cdpOk;st.tabOk=tabOk;
st.browserSetup.cdp=cdpOk?"OK":"—";
st.browserSetup.tab=tabOk?"найдена":"—";
});
renderAgents();
}
/* =====================================================================
ТЕМЫ
===================================================================== */
const BUILTIN_THEMES=["Glassmorphism","Cyberpunk","Monokai"];
const THEME_INFO={
"default":{desc:"тёплый графит + янтарь",sw:"linear-gradient(135deg,#f6a11c,#3a2c14)"},
"Glassmorphism":{desc:"стекло, блюр, полупрозрачность",sw:"linear-gradient(135deg,#8ec5ff,#c4b5fd)"},
"Cyberpunk":{desc:"неон: магента + циан",sw:"linear-gradient(135deg,#ff2d78,#22d3ee)"},
"Monokai":{desc:"классическая палитра Monokai",sw:"linear-gradient(135deg,#fd971f,#a6e22e)"}
};
let themeNames=[];
let customThemes={};
function loadCustomThemes(){try{customThemes=JSON.parse(localStorage.getItem("uni_custom_themes")||"{}");}catch(e){customThemes={};}}
function saveCustomThemes(){try{localStorage.setItem("uni_custom_themes",JSON.stringify(customThemes));}catch(e){log("Не удалось сохранить тему (лимит хранилища)","warn");}}
async function discoverThemes(){
const found=new Set();
try{const r=await fetch("/api/themes");if(r.ok){const d=await r.json();(Array.isArray(d)?d:[]).forEach(n=>found.add(String(n)));}}catch(e){}
try{const r=await fetch("css/themes/index.json",{cache:"no-store"});if(r.ok){const d=await r.json();(Array.isArray(d)?d:[]).forEach(n=>found.add(String(n)));}}catch(e){}
await Promise.all(BUILTIN_THEMES.map(async n=>{
try{const r=await fetch(css/themes/${n}.css,{cache:"no-store"});if(r.ok)found.add(n);}
catch(e){found.add(n);}
}));
themeNames=[...found];
Object.keys(customThemes).forEach(n=>{if(!themeNames.includes(n))themeNames.push(n);});
renderThemeList();
}
function currentTheme(){try{return localStorage.getItem("uni_theme")||"default";}catch(e){return "default";}}
function applyTheme(name){
const link=("#themeLink");const html=document.documentElement;
if(!name||name==="default"){
link.removeAttribute("href");html.removeAttribute("data-theme");
}else if(customThemes[name]){
html.dataset.theme=name;
const blob=new Blob([customThemes[name]],{type:"text/css"});
link.href=URL.createObjectURL(blob);
}else{
html.dataset.theme=name;
link.href="css/themes/"+name+".css";
}
try{localStorage.setItem("uni_theme",name||"default");}catch(e){}
renderThemeList();
}
function renderThemeList(){
const wrap=("#themeList");if(!wrap)return;
wrap.innerHTML="";
const cur=currentTheme();
const all=["default",...themeNames.filter(n=>n!=="default")];
all.forEach(n=>{
const info=THEME_INFO[n]||{desc:"своя тема (загружена)",sw:"linear-gradient(135deg,#9ca3af,#374151)"};
const card=el("button","theme-card"+(cur===n?" active":""));card.type="button";
const sw=el("span","sw");sw.style.background=info.sw;
const tt=el("span","tt");
const b=el("b");b.textContent=n==="default"?"По умолчанию":n;
const s=el("span");s.textContent=info.desc;
tt.append(b,s);
card.append(sw,tt);
if(cur===n){const chk=el("span","chk");chk.textContent="✓";card.append(chk);}
card.onclick=()=>{applyTheme(n);log("Тема: "+(n==="default"?"по умолчанию":n),"ok");};
wrap.append(card);
});
}
("#themeUploadBtn").onclick=()=>("#themeUpload").click();
("#themeUpload").onchange=async e=>{
const f=e.target.files[0];if(!f)return;
const css=await f.text();
const name=f.name.replace(/\.css/i,"")||"custom";
customThemes[name]=css;saveCustomThemes();
if(!themeNames.includes(name))themeNames.push(name);
applyTheme(name);renderThemeList();
log("Тема загружена и применена: "+name,"ok");
e.target.value="";
};
/* =====================================================================
Участники
===================================================================== */
async function loadParticipants(){
try{
const r=await fetch("/api/participants");
if(!r.ok)throw new Error("HTTP "+r.status);
const data=await r.json();
if(!Array.isArray(data)||!data.length)throw new Error("пустой список");
AGENTS=data;BACKEND_OK=true;
}catch(e){
AGENTS=FALLBACK_AGENTS.map(a=>({...a}));BACKEND_OK=false;
log("Бэкенд 127.0.0.1:8787 недоступен — включён демо-режим","warn");
}
setBackendPill();
AGENTS.forEach(a=>{
if(!(a.name in state)){
const una=a.status==="unavailable"||a.status==="disabled";
state[a.name]={on:!una,status:statusLabel(a.status),answer:"",sig:"",via:a.transport,
error:"",warn:"",expanded:false,latency:null,browserStage:"",
browserSetup:{enabled:a.transport==="browser",cdp:a.cdp?"OK":"—",tab:a.tab?"найдена":"—",auth:"—",url:a.host?("https://"+a.host):""}};
}
});
renderAgents();updateReadiness();
refreshBrowserStatus();
}
function setBackendPill(){
const led=("#backendLed"),txt=("#backendText");
led.className="led"+(BACKEND_OK?"":" amber");
txt.textContent=BACKEND_OK?"бэкенд: онлайн":"демо-режим";
("#backendPill").title=BACKEND_OK?"Бэкенд Юни отвечает":"Бэкенд недоступен — консоль эмулирует ответы";
}
function liveStatus(a,st){
if(a.status==="unavailable"||a.status==="disabled")return{cls:"off",lv:"lv-off",text:statusLabel(a.status)};
if(st.status==="опрос…")return{cls:"think",lv:"lv-think",text:"Думает…"};
if(st.error||st.status==="ошибка")return{cls:"err",lv:"lv-err",text:"Ошибка"};
return{cls:"ready",lv:"lv-ready",text:"Готов"};
}
function renderAgents(){
const wrap=("#agents");wrap.innerHTML="";
AGENTS.forEach((a,i)=>{
const st=state[a.name]||{on:false};
const una=a.status==="unavailable"||a.status==="disabled";
const card=el("div","agent-card"+(st.on?" active":" off")+(una?" unavailable":""));
1234567891011121314151617181920212223242526272829303132333435
});
const n=AGENTS.filter(a=>state[a.name]&&state[a.name].on).length;
("#agentCount").textContent=`{n}/{AGENTS.length}`;
}
("#deselectAll").onclick=()=>{
AGENTS.forEach(a=>{if(state[a.name])state[a.name].on=false;});
renderAgents();updateReadiness();
log("Выделение снято со всех участников");
};
function updateReadiness(){
const ready=AGENTS.filter(a=>state[a.name]&&state[a.name].on&&a.status!=="unavailable"&&a.status!=="disabled").length;
const una=AGENTS.filter(a=>a.status==="unavailable"||a.status==="disabled").length;
const dis=AGENTS.filter(a=>state[a.name]&&!state[a.name].on&&a.status!=="unavailable"&&a.status!=="disabled").length;
("#miniReadiness").textContent=`готовы{ready} · недоступны 
𝑢
𝑛
𝑎
⋅
отключены
una⋅отключены{dis}`;
updatePlan();
}
/* =====================================================================
Файлы (компактный блок)
===================================================================== */
function renderFiles(){
const wrap=("#files");wrap.innerHTML="";
("#filesCount").textContent=(${files.length});
files.forEach((f,i)=>{
const c=el("div","filechip");
const name=el("span");name.textContent=" "+f.name;
const meta=el("span","meta");meta.textContent=Math.ceil(f.size/1024)+" КБ";
const sync=el("span","sync");sync.textContent="✓ синхр.";
const x=el("span","x");x.textContent="✕";x.onclick=()=>{files.splice(i,1);renderFiles();updatePlan();};
c.append(name,meta,sync,x);wrap.append(c);
});
}
async function addFiles(list){
for(const file of list){
if(files.length>=12){log("Максимум 12 файлов","warn");break;}
if(file.size>300000){log(${file.name}: файл больше 300 КБ,"warn");continue;}
if(files.some(f=>f.name===file.name)){log(${file.name}: уже добавлен,"warn");continue;}
const content=await file.text();
if(content.includes("\u0000")){log(${file.name}: бинарный файл не поддерживается,"warn");continue;}
files.push({name:file.name,content,size:file.size});
}
renderFiles();updatePlan();
}
("#filesToggle").onclick=()=>{
const p=("#filesPanel");const open=p.style.display!=="none";
p.style.display=open?"none":"block";
("#filesToggle").classList.toggle("open",!open);
};
("#drop").onclick=()=>("#fileInput").click();
("#fileInput").onchange=async e=>{await addFiles(e.target.files);e.target.value="";};
const drop=("#drop");
["dragover","dragenter"].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add("hover");}));
["dragleave","drop"].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove("hover");}));
drop.addEventListener("drop",async e=>{await addFiles(e.dataTransfer.files);});
const fmini=("#filesMini");
["dragover","dragenter"].forEach(ev=>fmini.addEventListener(ev,e=>{e.preventDefault();fmini.classList.add("hover");}));
["dragleave","drop"].forEach(ev=>fmini.addEventListener(ev,e=>{e.preventDefault();fmini.classList.remove("hover");}));
fmini.addEventListener("drop",async e=>{
e.preventDefault();
("#filesPanel").style.display="block";("#filesToggle").classList.add("open");
await addFiles(e.dataTransfer.files);
});
/* =====================================================================
Шаблон / план
===================================================================== */
("#template").onchange=()=>{const t=TEMPLATES[("#template").value];if(t){("#topic").value=t.topic;("#brief").value=t.brief;updatePlan();}};
("#topic").oninput=updatePlan;("#brief").oninput=updatePlan;
function updatePlan(){
const t=("#topic").value.trim()||"(не задана)";
const b=("#brief").value.trim()||"(пусто)";
const on=AGENTS.filter(a=>state[a.name]&&state[a.name].on);
("#planText").textContent=`Тема:{t}\nБриф: 
𝑏
.
𝑠
𝑙
𝑖
𝑐
𝑒
(
0
,
200
)
b.slice(0,200){b.length>200?"…":""}\nУчастников: 
𝑜
𝑛
.
𝑙
𝑒
𝑛
𝑔
𝑡
ℎ
(
on.length({on.map(a=>a.name).join(", ")})`;
}
/* =====================================================================
Журнал (один поток)
===================================================================== */
function log(msg,cls=""){
const t=new Date().toLocaleTimeString("ru-RU");
const node=("#logFull");
if(node){
const d=el("div");
d.innerHTML=`<span class="t">{t}</span> <span class="${cls}">{esc(msg)}</span>`;
node.append(d);node.scrollTop=node.scrollHeight;
}
const hint=("#runHint");if(hint)hint.textContent=msg;
}
/* =====================================================================
Сетка ответов
===================================================================== */
function buildGrid(names){
const grid=("#grid");grid.innerHTML="";
let i=0;
names.forEach(nm=>{
const a=AGENTS.find(x=>x.name===nm);if(!a)return;
const box=el("div","mbox");box.dataset.name=nm;
const head=el("div","mhead");
const av=el("div","mava");av.style.background=PAL[i++%PAL.length];av.textContent=nm[0].toUpperCase();
const nmBox=el("div");const n1=el("div","mname");n1.textContent=nm;const n2=el("div","mrole");n2.textContent=a.role||"";nmBox.append(n1,n2);
const led=el("div","mled");led.dataset.led="1";
head.append(av,nmBox,led);
const body=el("div","mbody");body.dataset.body="1";
const foot=el("div","mfoot");foot.dataset.foot="1";
box.append(head,body,foot);grid.append(box);
renderCardFromState(nm);
});
}
function cardBox(name){return document.querySelector(`.mbox[data-name="{CSS.escape(name)}"]);} function renderCardFromState(name){ const st=state[name];if(!st)return; const box=cardBox(name);if(!box)return; setLed(name, st.status==="опрос…"?"run":st.error?"err":st.answer?"ok":""); const errHtml=st.error?<div class="err"> 
𝑒
𝑠
𝑐
(
𝑠
𝑡
.
𝑒
𝑟
𝑟
𝑜
𝑟
)
.
𝑠
𝑙
𝑖
𝑐
𝑒
(
0
,
400
)
<
/
𝑑
𝑖
𝑣
>
‘
:
"
"
;
𝑐
𝑜
𝑛
𝑠
𝑡
𝑤
𝑎
𝑟
𝑛
𝐻
𝑡
𝑚
𝑙
=
𝑠
𝑡
.
𝑤
𝑎
𝑟
𝑛
?
‘
<
𝑑
𝑖
𝑣
𝑐
𝑙
𝑎
𝑠
𝑠
=
"
𝑤
𝑎
𝑟
𝑛
𝑙
𝑖
𝑛
𝑒
"
>
⚠
esc(st.error).slice(0,400)</div>‘:"";constwarnHtml=st.warn?‘<divclass="warnline">⚠{esc(st.warn).slice(0,300)}</div>:""; const sigHtml=st.sig?<div class="sig"><b>Подпись 
𝑒
𝑠
𝑐
(
𝑛
𝑎
𝑚
𝑒
)
:
<
/
𝑏
>
esc(name):</b>{esc(st.sig)}</div>:""; const textHtml=st.answer?<div>
𝑒
𝑠
𝑐
(
𝑠
𝑡
.
𝑎
𝑛
𝑠
𝑤
𝑒
𝑟
)
<
/
𝑑
𝑖
𝑣
>
‘
:
‘
<
𝑑
𝑖
𝑣
𝑐
𝑙
𝑎
𝑠
𝑠
=
"
𝑒
𝑚
𝑝
𝑡
𝑦
"
>
esc(st.answer)</div>‘:‘<divclass="empty">{st.error?"нет ответа":"ожидает запуска · транспорт: "+transportLabel(st.via)}</div>; let stageHtml=""; if(st.via==="browser"&&st.status!=="готов"){stageHtml=<div class="stage"><span class="wait">{esc(st.browserStage||"ожидание браузерной сессии…")}</span></div>`;}
const body=box.querySelector("[data-body]");
body.innerHTML=textHtml+sigHtml+warnHtml+errHtml+stageHtml;
body.classList.toggle("expanded",!!st.expanded);
const foot=box.querySelector("[data-foot]");
foot.innerHTML=`<span>{esc(transportLabel(st.via))}{st.latency?` ·{st.latency}s:""}${st.error?" · ошибка":""}</span>+
(st.answer&&st.answer.length>500?<span class="expand-btn" data-exp="1">${st.expanded?"Свернуть":"Развернуть"}</span>:"");
const eb=foot.querySelector("[data-exp]");
if(eb)eb.onclick=()=>{st.expanded=!st.expanded;renderCardFromState(name);};
}
function setLed(name,cls){
const box=cardBox(name);if(!box)return;
box.className="mbox"+(cls?" "+cls:"");
const led=box.querySelector("[data-led]");if(led)led.className="mled"+(cls?" "+cls:"");
}
/* =====================================================================
Прогресс / кнопки
===================================================================== */
function setProgress(p){const bar=("#progress").firstElementChild;if(bar)bar.style.width=Math.min(100,Math.max(0,p))+"%";}
function finishProgress(){const p=("#progress");setProgress(100);
setTimeout(()=>{p.classList.remove("show");setTimeout(()=>setProgress(0),300);},700);}
const busySel=["#runBtn","#runBtn2","#runApiBtn"];
function setBusy(b){busySel.forEach(s=>{const btn=$(s);if(btn)btn.disabled=b;});}
function resetRoundState(){
AGENTS.forEach(a=>{const s=state[a.name];if(s){s.answer="";s.sig="";s.error="";s.warn="";s.status="готов";s.expanded=false;s.latency=null;s.browserStage="";}});
currentRound={id:null,synthesis:"",reportPath:null,signatures:{},errors:{}};
}
/* =====================================================================
Бейдж вкладки «Итог»
===================================================================== */
function bumpSummaryBadge(){pendingSummary++;const b=("#summaryDot");b.textContent=pendingSummary;b.classList.add("show");}
function clearSummaryBadge(){pendingSummary=0;("#summaryDot").classList.remove("show");}
/* =====================================================================
Запуск раунда
===================================================================== */
async function runRound(opts={}){
if(running)return;
const apiOnly=!!opts.apiOnly;
let enabled=AGENTS.filter(a=>{
if(!(state[a.name]&&state[a.name].on))return false;
if(apiOnly&&a.transport==="browser")return false;
return true;
}).map(a=>a.name);
if(!("#topic").value.trim()){log("Укажите тему раунда","warn");return;}
if(!enabled.length){log("Включите хотя бы одного доступного участника","warn");return;}
const hadBrowser=enabled.some(n=>AGENTS.find(a=>a.name===n)?.transport==="browser");
const tosAck=localStorage.getItem("uni_tos_ack")==="1";
if(hadBrowser&&!tosAck){
enabled=enabled.filter(n=>AGENTS.find(a=>a.name===n)?.transport!=="browser");
log("ToS не подтверждён — браузерные участники пропущены. Используйте «Только API».","warn");
if(!enabled.length)return;
}
running=true;setBusy(true);
("#progress").classList.add("show");setProgress(3);
clearSummaryBadge();
("#preRound").style.display="none";("#gridWrap").style.display="block";
resetRoundState();
activeNames=enabled;doneCount=0;totalCount=enabled.length;
buildGrid(enabled);updateSigCount();
const topic=("#topic").value.trim();
const attachments=Object.fromEntries(files.map(f=>[f.name,f.content]));
("#roundId").textContent="run…";
log(Старт раунда · участников: ${enabled.length}${hadBrowser&&!tosAck?" (браузерные пропущены)":""});
if(!BACKEND_OK){
simulateRound(enabled,{
answerFor:a=>({text:demoAnswerFor(a,topic),sig:«${topic}» — согласовано. ${a.name}}),
done:(s,e)=>makeDemoDone(topic,("#brief").value,enabled,s,e)
});
return;
}
try{
await streamRound({topic,brief:("#brief").value,files:attachments,tasks:[],only:enabled,enabled});
}catch(e){log("Ошибка соединения: "+e.message,"warn");}
finally{running=false;setBusy(false);finishProgress();}
}
/* Устойчивый SSE-парсер: построчно, работает и с "\n\n", и с одинарным "\n" */
async function streamRound(payload){
const res=await fetch("/api/round/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
if(!res.ok){const b=await res.json().catch(()=>({}));throw new Error(b.error||("HTTP "+res.status));}
const reader=res.body.getReader();const dec=new TextDecoder();let buf="";
const consume=chunk=>{
buf+=chunk;
const lines=buf.split(/\r?\n/);
buf=lines.pop();
for(const raw of lines){
const l=raw.trim();
if(!l.startsWith("data:"))continue;
const p=l.slice(5).trim();
if(!p)continue;
try{handleEvent(JSON.parse(p));}catch(e){}
}
};
while(true){
const{done,value}=await reader.read();
if(done)break;
consume(dec.decode(value,{stream:true}));
}
if(buf.trim()){consume("\n");}
}
/* ---------------- демо-эмуляция ---------------- /
function simulateRound(names,cfg){
handleEvent({type:"init",participants:names.map(n=>({name:n}))});
const sigMap={},errMap={};
let lastEnd=0;
names.forEach((nm,i)=>{
const a=AGENTS.find(x=>x.name===nm)||{name:nm,transport:"api",role:""};
const t0=350+i430,dur=1400+Math.random()*2400;
lastEnd=Math.max(lastEnd,t0+dur);
setTimeout(()=>handleEvent({type:"participant_start",name:nm,via:a.transport,
stage:a.transport==="browser"?"CDP: открытие вкладки → ввод брифа → ожидание ответа":""}),t0);
setTimeout(()=>{
const r=cfg.answerFor(a);
if(r.sig)sigMap[nm]=r.sig;
handleEvent({type:"participant_done",name:nm,ok:true,text:r.text,signature:r.sig||"",via:a.transport,latency:+(dur/1000).toFixed(1)});
},t0+dur);
});
setTimeout(()=>{handleEvent(cfg.done(sigMap,errMap));running=false;setBusy(false);finishProgress();},lastEnd+700);
}
function demoAnswerFor(a,topic){
const t=(topic||"").trim()||"базовая задача";const role=a.role||"";
if(/Проверка статуса/.test(t))return ${a.name}: доступен, готов. На связи, очередь пуста.;
if(/Algorithm/.test(role))return Разобрал «${t}». Декомпозиция: 1) спецификация интерфейсов, 2) прототип ядра, 3) нагрузочные тесты.;
if(/Consensus/.test(role))return Вижу формирующийся консенсус по «${t}». После сбора подписей соберу единую редакцию решения.;
if(/Code implementation/.test(role))return Готов реализовать «${t}». План: модуль ядра + тонкий API-слой.;
if(/Critic/.test(role))return По «${t}»: требую явный kill-switch и логирование каждого шага. В остальном — поддерживаю.;
if(/Reality/.test(role))return Reality-check по «${t}»: сроки реалистичны при скоупе без «приятных мелочей».;
if(/Risk/.test(role))return Риски по «${t}»: рассинхронизация версий, rate-limit, потеря контекста. Митигация: чекпоинты.;
if(/Fast/.test(role))return Быстрый проход по «${t}»: формулировка ясная, блокеров не вижу.;
if(/Fallback/.test(role))return Как fallback-модель готова подхватить «${t}» при отказе основных эндпоинтов.;
if(/Open weights/.test(role))return По «${t}»: предложу open-weights альтернативы для локального инференса.;
if(/Local/.test(role))return Локальный сервер для «${t}» в норме: память ок, очередь пуста.;
if(/General/.test(role))return Общее ревью «${t}»: структура брифа понятна, критичных замечаний нет.;
return Подтверждаю участие в раунде по теме «${t}». Замечаний нет.;
}
function makeDemoDone(topic,brief,names,sigMap,errMap){
const rid="demo-"+Date.now().toString(36).toUpperCase();
const sigCount=Object.keys(sigMap).length;
const synthesis=Демо-итог: по теме «${topic||"—"}» опрошено ${names.length}, подписей ${sigCount}, ошибок ${Object.keys(errMap).length}. Общий вектор согласован.;
demoReports[rid]=buildDemoReport(rid,topic,brief,names,sigMap);
localHistory.unshift({round_id:rid,topic:topic||"(без темы)",signatures:sigCount,errors:Object.keys(errMap).length});
return {type:"done",round_id:rid,synthesis,report_path:".uni-council/"+rid+"/report.md",signatures:sigMap,errors:errMap};
}
function buildDemoReport(rid,topic,brief,names,sigMap){
const L=[];
L.push(# Отчёт раунда ${rid},"",Тема: ${topic||"—"},"","Бриф:",«${(brief||"").trim()||"(пусто)"}»,"","## Ответы участников","");
names.forEach(n=>{const st=state[n];if(!st)return;
L.push(### ${n},"",st.answer||"(нет ответа)","");
if(st.sig)L.push(> Подпись: ${st.sig},"");});
L.push("## Итог","",Подписей: ${Object.keys(sigMap).length}/${names.length}.,"","(демо-режим: ответы сгенерированы локально)");
return L.join("\n");
}
/* =====================================================================
События SSE (с алиасами и терпимой обработкой ошибок)
===================================================================== /
function handleEvent(ev){
let t=ev.type;
if(["answer","participant_answer","result","participant_result"].includes(t))t="participant_done";
else if(["round_done","complete","completed","finish","finished","round_complete"].includes(t))t="done";
else if(["participant_begin","participant_started"].includes(t))t="participant_start";
switch(t){
case "init":
log("Участники: "+ev.participants.map(p=>p.name).join(", "),"ok");break;
case "start":break;
case "participant_start":{
setLed(ev.name,"run");
const st=state[ev.name];
if(st){st.status="опрос…";st.error="";st.warn="";if(st.via==="browser"&&ev.stage)st.browserStage=ev.stage;}
renderCardFromState(ev.name);renderAgents();
log(→ ${ev.name} [${ev.via}] запрос отправлен);break;}
case "participant_done":{
const st=state[ev.name];
if(st){
const txt=String(ev.text??ev.answer??ev.response??ev.output??"");
const sig=String(ev.signature??ev.sig??"");
const errRaw=String(ev.error||ev.err||"");
const hasText=txt.trim().length>0;
const ok=hasText||ev.ok===true;
st.answer=txt;
st.sig=sig;
st.error=hasText?"":errRaw;
st.warn=(hasText&&errRaw)?errRaw:"";
st.status=ok?"готов":"ошибка";
st.via=ev.via||st.via;
st.latency=ev.latency;
}
doneCount++;if(totalCount>0)setProgress(Math.round(doneCount/totalCount100));
renderCardFromState(ev.name);renderAgents();updateSigCount();
bumpSummaryBadge();
log(← ${ev.name} ответ${(st&&st.warn)?" (с предупреждением)":ev.ok?"":" (ошибка)"}${ev.signature||st?.sig?" + подпись":""},
(st&&st.answer)?"ok":(st&&st.warn)?"ok":"warn");
if(reportViewing){newAnswersWhileViewing++;showNotify(Новый ответ: ${ev.name});}
break;}
case "done":{
currentRound.id=ev.round_id??ev.id??null;
currentRound.synthesis=String(ev.synthesis??ev.summary??ev.consensus??ev.synthesis_text??"");
currentRound.reportPath=ev.report_path??ev.report??ev.report_file??null;
currentRound.signatures=ev.signatures||{};currentRound.errors=ev.errors||{};
("#roundId").textContent=currentRound.id||"—";
log("Раунд завершён · отчёт: "+(currentRound.reportPath||"—"),"ok");
("#summaryFull").textContent=currentRound.synthesis||"Общая сводка не создана; откройте полный отчёт.";
bumpSummaryBadge();
("#runHint").textContent="Готово · отчёт в "+(currentRound.reportPath||".uni-council/");
updateReportLink();
loadHistory();break;}
case "error":log("Ошибка: "+(ev.msg||ev.error||"?"),"warn");break;
}
}
function updateSigCount(){
const list=activeNames||AGENTS.filter(a=>state[a.name]&&state[a.name].on).map(a=>a.name);
const got=list.filter(n=>state[n]&&state[n].sig).length;
("#sigCount").textContent=${got}/${list.length};
}
/* ---------------- ссылка на отчёт (во вкладке «Итог») ---------------- */
function updateReportLink(){
const a=("#reportLink");
if(currentRound.reportPath&&currentRound.id){
a.style.display="inline-flex";
a.textContent="📄 "+currentRound.reportPath;
a.title="Открыть полный отчёт";
}else a.style.display="none";
}
("#reportLink").onclick=()=>{if(currentRound.id)openReport(currentRound.id);};
/* =====================================================================
Полный отчёт
===================================================================== */
function openReport(roundId){
reportViewing=true;newAnswersWhileViewing=0;hideNotify();
("#reportTitle").textContent="Полный отчёт · "+roundId;
("#reportBody").textContent="Загрузка…";
("#reportDrawer").classList.add("show");
if(!BACKEND_OK){
("#reportBody").textContent=demoReports[roundId]||"Отчёт не найден (демо-режим).";
return;
}
fetch(/api/report?id=${encodeURIComponent(roundId)})
.then(r=>r.json())
.then(d=>{if(d.error)throw new Error(d.error);("#reportBody").textContent=d.markdown||"(пусто)";})
.catch(e=>{("#reportBody").textContent=demoReports[roundId]||("Ошибка: "+e.message);});
}
function closeReport(){reportViewing=false;hideNotify();("#reportDrawer").classList.remove("show");}
("#reportClose").onclick=closeReport;
("#reportBack").onclick=closeReport;
async function copyText(txt){
try{await navigator.clipboard.writeText(txt);return true;}
catch(e){
try{const ta=document.createElement("textarea");ta.value=txt;ta.style.position="fixed";ta.style.opacity="0";
document.body.append(ta);ta.select();const ok=document.execCommand("copy");ta.remove();return ok;}
catch(e2){return false;}
}
}
("#reportCopyClose").onclick=async()=>{
const txt=("#reportBody").textContent||"";
const ok=await copyText(txt);
closeReport();
log(ok?"Отчёт скопирован в буфер обмена":"Не удалось скопировать",ok?"ok":"warn");
};
("#notifyGo").onclick=()=>{closeReport();switchTab("current");};
("#copySummary").onclick=async()=>{
const ok=await copyText(("#summaryFull").textContent||"");
log(ok?"Итог скопирован":"Не удалось скопировать",ok?"ok":"warn");
};
("#openReport").onclick=()=>{if(currentRound.id)openReport(currentRound.id);else log("Сначала запустите раунд","warn");};
function showNotify(msg){("#notifyText").textContent=msg;("#notify").classList.add("show");}
function hideNotify(){("#notify").classList.remove("show");}
/* =====================================================================
Табы центра
===================================================================== */
function switchTab(name){
document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("active",t.dataset.tab===name));
document.querySelectorAll(".tabpane").forEach(p=>p.classList.remove("active"));
("#paneCurrent").classList.toggle("active",name==="current");
("#paneSummary").classList.toggle("active",name==="summary");
$("#paneLog").classList.toggle("active",name==="log");
if(name==="summary")clearSummaryBadge();
}
document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>switchTab(t.dataset.tab));
/* =====================================================================
История
===================================================================== */
function openHistory(){("#historyDrawer").classList.add("show");loadHistory();}
("#historyBtn").onclick=openHistory;
("#historyClose").onclick=()=>("#historyDrawer").classList.remove("show");
async function loadHistory(){
const wrap=("#history");
let items=null;
if(BACKEND_OK){
try{const res=await fetch("/api/history");if(res.ok)items=await res.json();}catch(e){}
}
if(!items)items=localHistory;
let items2=items;
const q=("#histSearch").value.trim().toLowerCase();
const f=("#histFilter").value;
if(q)items2=items2.filter(it=>(it.topic||"").toLowerCase().includes(q)||(it.round_id||"").toLowerCase().includes(q));
if(f==="ok")items2=items2.filter(it=>it.errors===0);
if(f==="err")items2=items2.filter(it=>it.errors>0);
wrap.innerHTML="";
if(!items2.length){wrap.innerHTML='<div class="empty" style="padding:14px">Нет раундов по фильтру</div>';return;}
for(const item of items2){
const row=el("div","history-item");
const title=el("b");title.textContent=item.topic||item.round_id;
const meta=el("span");
const ok=item.errors===0;
meta.innerHTML=`{esc(item.round_id)} · <span class="${ok?'ok':'err'}">подписи 
𝑖
𝑡
𝑒
𝑚
.
𝑠
𝑖
𝑔
𝑛
𝑎
𝑡
𝑢
𝑟
𝑒
𝑠
⋅
ошибки
item.signatures⋅ошибки{item.errors}</span>; const del=el("span","del");del.textContent="🗑";del.title="Удалить раунд"; del.onclick=async e=>{ e.stopPropagation(); if(!confirm(Удалить раунд {item.round_id}?`))return;
if(BACKEND_OK){
try{const r=await fetch("/api/history/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({round_id:item.round_id})});
if(!r.ok)throw new Error(await r.text());}
catch(err){log("Не удалось удалить: "+err.message,"warn");return;}
}else{
localHistory=localHistory.filter(x=>x.round_id!==item.round_id);
delete demoReports[item.round_id];
}
log("Раунд удалён: "+item.round_id,"ok");loadHistory();
};
row.append(title,meta,del);
row.onclick=()=>openReport(item.round_id);
wrap.append(row);
}
}
("#histSearch").oninput=loadHistory;
("#histFilter").onchange=loadHistory;
("#histClear").onclick=async()=>{
if(!confirm("Удалить ВСЕ сохранённые раунды?"))return;
if(BACKEND_OK){
try{const r=await fetch("/api/history/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({round_id:"all"})});
if(!r.ok)throw new Error(await r.text());}
catch(err){log("Не удалось очистить: "+err.message,"warn");return;}
}else{localHistory=[];for(const k in demoReports)delete demoReports[k];}
log("История очищена","ok");loadHistory();
};
/* =====================================================================
Настройки
===================================================================== */
const modal=("#settingsModal");
function defaultCfg(){return{browser_enabled:true,free_tier_only:true,min_interval_seconds:8,timeout_seconds:90,concurrency:3,
url_check:true,autonomous:{enabled:false,auto_start_session:false},
endpoints:{
Gemini:{base_url:"https://generativelanguage.googleapis.com/v1beta",api_key_set:false},
Groq:{base_url:"https://api.groq.com/openai/v1",api_key_set:false},
OpenRouter:{base_url:"https://openrouter.ai/api/v1",api_key_set:false},
HuggingFace:{base_url:"https://api-inference.huggingface.co",api_key_set:false},
Hermes:{base_url:"http://127.0.0.1:11434/v1",api_key_set:false}
}};}
function storedCfg(){try{return JSON.parse(localStorage.getItem("uni_cfg")||"null")||defaultCfg();}catch(e){return defaultCfg();}}
async function openSettings(){
if(BACKEND_OK){
try{const r=await fetch("/api/config");EP_CONFIG=await r.json();}catch(e){EP_CONFIG=storedCfg();}
}else EP_CONFIG=storedCfg();
("#t_browser_enabled").classList.toggle("on",EP_CONFIG.browser_enabled!==false);
("#t_free_tier_only").classList.toggle("on",EP_CONFIG.free_tier_only!==false);
("#t_autonomous").classList.toggle("on",!!EP_CONFIG.autonomous?.enabled);
("#t_auto_start").classList.toggle("on",!!EP_CONFIG.autonomous?.auto_start_session);
("#t_url_check").classList.toggle("on",EP_CONFIG.url_check!==false);
("#i_min_interval").value=EP_CONFIG.min_interval_seconds??8;
("#i_timeout").value=EP_CONFIG.timeout_seconds??90;
("#i_concurrency").value=EP_CONFIG.concurrency??3;
renderEndpoints(EP_CONFIG.endpoints||{});
renderThemeList();
modal.classList.add("show");switchMtab("general");
}
function renderEndpoints(ep){
const wrap=("#endpoints");wrap.innerHTML="";
const entries=Object.entries(ep);
if(!entries.length){wrap.innerHTML='<div class="empty">Эндпоинты не настроены</div>';return;}
for(const[name,info]of entries){
const box=el("div","ep");
const t=el("div","ept");
t.innerHTML=<span>${esc(name)}</span><span class="set">${info.api_key_set?"ключ установлен":"ключ пуст"}</span>;
const r1=el("div","epr");
const l1=el("label");l1.textContent="Base URL";
const i1=el("input");i1.type="text";i1.value=info.base_url||"";i1.dataset.url=name;
r1.append(l1,i1);
const r2=el("div","epr");
const l2=el("label");l2.textContent="API key";
const i2=el("input");i2.type="password";i2.placeholder=info.api_key_set?"•••••• (не меняй, чтобы оставить)":"вставьте ключ";i2.dataset.key=name;
r2.append(l2,i2);
box.append(t,r1,r2);wrap.append(box);
}
}
function switchMtab(name){
document.querySelectorAll(".modal-tab").forEach(t=>t.classList.toggle("active",t.dataset.mtab===name));
document.querySelectorAll(".mtab").forEach(p=>p.style.display=p.dataset.mtab===name?"block":"none");
}
document.querySelectorAll(".modal-tab").forEach(t=>t.onclick=()=>switchMtab(t.dataset.mtab));
["#t_browser_enabled","#t_free_tier_only","#t_autonomous","#t_auto_start","#t_url_check"].forEach(s=>{
(
𝑠
)
.
𝑜
𝑛
𝑐
𝑙
𝑖
𝑐
𝑘
=
(
)
=
>
(s).onclick=()=>(s).classList.toggle("on");
});
("#settingsBtn").onclick=openSettings;
("#settingsCancel").onclick=()=>modal.classList.remove("show");
modal.onclick=e=>{if(e.target===modal)modal.classList.remove("show");};
("#settingsSave").onclick=async()=>{
const endpoints={};
for(const inp of document.querySelectorAll("#endpoints input[data-key]")){
const name=inp.dataset.key;
const key=inp.value.trim();
const urlEl=document.querySelector(`#endpoints input[data-url="{CSS.escape(name)}"]); const url=urlEl?urlEl.value.trim():""; if($("#t_url_check").classList.contains("on")&&/[?&](api_key|key|token|secret|access_token)=/i.test(url)){ log(Ошибка: Base URL {name} содержит секрет в параметрах — сохранение отменено`,"warn");return;
}
endpoints[name]={base_url:url,api_key:key,api_key_set:!!key||(EP_CONFIG.endpoints?.[name]?.api_key_set||false)};
}
const payload={
browser_enabled:("#t_browser_enabled").classList.contains("on"),
free_tier_only:("#t_free_tier_only").classList.contains("on"),
min_interval_seconds:parseFloat(("#i_min_interval").value)||8,
timeout_seconds:parseFloat(("#i_timeout").value)||90,
concurrency:parseInt(("#i_concurrency").value)||3,
url_check:("#t_url_check").classList.contains("on"),
autonomous_enabled:("#t_autonomous").classList.contains("on"),
auto_start_session:$("#t_auto_start").classList.contains("on"),
endpoints
};
if(BACKEND_OK){
try{
const res=await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
const body=await res.json().catch(()=>({}));
if(!res.ok)throw new Error(body.error||("HTTP "+res.status));
log("Настройки сохранены в локальный config.yaml","ok");
}catch(e){log("Ошибка сохранения: "+e.message,"warn");return;}
}else{
const cfg={...payload,autonomous:{enabled:payload.autonomous_enabled,auto_start_session:payload.auto_start_session}};
try{localStorage.setItem("uni_cfg",JSON.stringify(cfg));}catch(e){}
EP_CONFIG=cfg;
log("Демо-режим: настройки сохранены локально (ключи не сохраняются в браузере)","ok");
}
modal.classList.remove("show");
await loadParticipants();updateReadiness();renderAgents();
};
/* =====================================================================
Автоматизация (UI-состояние)
===================================================================== */
function setAuto(mode){
autoMode=mode;
("#autoState").textContent=mode==="on"?"включена":mode==="paused"?"пауза":"выключена";
("#autoTask").textContent=mode==="on"?"анализ → реализация → тестирование → ревью":"—";
("#autoOn").classList.toggle("on",mode==="on");
("#autoPause").classList.toggle("on",mode==="paused");
("#autoStop").classList.toggle("on",mode==="off");
log("Автоматизация: "+("#autoState").textContent,"ok");
}
("#autoOn").onclick=()=>setAuto("on");
("#autoPause").onclick=()=>setAuto("paused");
$("#autoStop").onclick=()=>setAuto("off");
/* =====================================================================
Горячие клавиши / мобильное меню / привязки / старт
===================================================================== */
document.addEventListener("keydown",e=>{
if(e.key==="Escape"){
if(("#reportDrawer").classList.contains("show"))closeReport();
("#historyDrawer").classList.remove("show");
("#settingsModal").classList.remove("show");
("#leftCol").classList.remove("show");
}
});
("#menuBtn").onclick=()=>("#leftCol").classList.toggle("show");
("#runBtn").onclick=()=>runRound();
("#runBtn2").onclick=()=>runRound();
$("#runApiBtn").onclick=()=>runRound({apiOnly:true});
/* старт */
loadCustomThemes();
applyTheme(currentTheme());
discoverThemes();
("#template").value="status";
("#topic").value=TEMPLATES.status.topic;
$("#brief").value=TEMPLATES.status.brief;
loadParticipants();
loadHistory();
updatePlan();
setInterval(()=>{refreshBrowserStatus();},20000);
log("Консоль загружена · UNI v2.7");