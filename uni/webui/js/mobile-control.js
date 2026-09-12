'use strict';
const $=selector=>document.querySelector(selector);
let busy=0,lastMove=0;
function show(text,error=false){$('#status').textContent=text;$('#status').dataset.kind=error?'error':'';$('#state').textContent=error?'ошибка':'готово';}
async function uniInput(action,params={}){busy++;$('#state').textContent='Юни…';try{const response=await fetch('/api/mobile/input',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,params})});const data=await response.json().catch(()=>({}));if(!response.ok||!data.ok)throw new Error(data.error||data.message||('HTTP '+response.status));show(data.message+' · '+(data.status||'not_verified'));return data;}catch(error){show(error.message,true);return null;}finally{busy--;if(busy)$('#state').textContent='Юни…';}}
function click(button='left',double=false){return uniInput('click_current',{button,clicks:double?2:1});}
async function move(dx,dy){const data=await uniInput('move_relative',{dx:Math.round(dx),dy:Math.round(dy)});if(data?.data){window._cursorX=data.data.x;window._cursorY=data.data.y;}}
function wirePad(){const pad=$('#touchpad');let pointer=null,lastX=0,lastY=0,moved=0,pendingX=0,pendingY=0;
 pad.addEventListener('pointerdown',event=>{pointer=event.pointerId;lastX=event.clientX;lastY=event.clientY;moved=0;pad.setPointerCapture(pointer);});
 pad.addEventListener('pointermove',event=>{if(event.pointerId!==pointer)return;const dx=event.clientX-lastX,dy=event.clientY-lastY;lastX=event.clientX;lastY=event.clientY;moved+=Math.abs(dx)+Math.abs(dy);pendingX+=dx*1.65;pendingY+=dy*1.65;const now=performance.now();if(now-lastMove>35){lastMove=now;const x=pendingX,y=pendingY;pendingX=pendingY=0;move(x,y);}});
 pad.addEventListener('pointerup',event=>{if(event.pointerId!==pointer)return;pointer=null;if(pendingX||pendingY){move(pendingX,pendingY);pendingX=pendingY=0;}if(moved<8)click('left');});
 pad.addEventListener('contextmenu',event=>event.preventDefault());}
function wireWheel(){const wheel=$('#wheel');let pointer=null,lastY=0,acc=0;wheel.addEventListener('pointerdown',event=>{pointer=event.pointerId;lastY=event.clientY;wheel.setPointerCapture(pointer);});wheel.addEventListener('pointermove',event=>{if(event.pointerId!==pointer)return;acc+=lastY-event.clientY;lastY=event.clientY;if(Math.abs(acc)>=18){const amount=Math.trunc(acc/18);acc-=amount*18;uniInput('scroll',{amount});}});wheel.addEventListener('pointerup',()=>{pointer=null;acc=0;});}
$('#leftBtn').onclick=()=>click('left');$('#doubleBtn').onclick=()=>click('left',true);$('#rightBtn').onclick=()=>click('right');
$('#copyBtn').onclick=async()=>{const data=await uniInput('copy_selected_text');const value=data?.data?.value;if(typeof value==='string'){$('#clipText').value=value;try{await navigator.clipboard.writeText(value);show('Юни скопировала выделенный текст; он также помещён в буфер телефона.');}catch(_){show('Юни скопировала выделенный текст в поле ниже.');}}};
$('#pasteBtn').onclick=()=>{const text=$('#clipText').value;if(!text.trim())return show('Введите текст для вставки.',true);uniInput('paste',{text});};
wirePad();wireWheel();
