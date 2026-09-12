(() => {
  'use strict';

  const $ = (s) => document.querySelector(s);
  let workspaceAdminPending = null;
  let runtimeOverviewPending = null;
  let workspaceData = null;
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, ch => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));
  const arr = (v) => Array.isArray(v) ? v : (v == null || v === '' ? [] : [v]);
  const first = (...values) => values.find(v => v !== undefined && v !== null && v !== '');
  const STATUS = {
    planned:'PLANNED', open:'PLANNED', queued:'PLANNED', pending:'PLANNED',
    active:'ACTIVE', running:'ACTIVE', claimed:'ACTIVE',
    verifying:'VERIFYING', verify:'VERIFYING', done:'VERIFYING',
    waiting_owner:'WAITING OWNER', waiting_owner_review:'WAITING OWNER', owner_review:'WAITING OWNER',
    owner_verified:'OWNER VERIFIED', verified:'OWNER VERIFIED',
    blocked:'BLOCKED', conflict:'BLOCKED', stale:'STALE', failed:'FAILED', error:'FAILED'
  };
  function normalizeStatus(value, ownerVerified=false) {
    if (ownerVerified === true) return 'OWNER VERIFIED';
    const key = String(value || 'planned').trim().toLowerCase();
    return STATUS[key] || key.replaceAll('_',' ').toUpperCase();
  }
  function statusClass(value) {
    const s = normalizeStatus(value);
    if (s === 'ACTIVE' || s === 'OWNER VERIFIED') return 'workspace-status-good';
    if (s === 'WAITING OWNER' || s === 'VERIFYING') return 'workspace-status-warn';
    if (s === 'BLOCKED' || s === 'STALE' || s === 'FAILED') return 'workspace-status-bad';
    return 'workspace-status-neutral';
  }
  function empty(text) { return `<div class="workspace-empty">${esc(text)}</div>`; }
  function formatTime(value) {
    if (!value) return '—';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? esc(value) : d.toLocaleString('ru-RU', {
      day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'
    });
  }
  function isStale(item, data=workspaceData) {
    if (!item) return false;
    if (item.stale === true) return true;
    if (String(first(item.status,item.state,'')).toLowerCase() === 'stale') return true;
    if (String(item.revision_state || '').toLowerCase() === 'stale') return true;
    const itemRevision = first(item.ack_revision,item.master_revision,item.revision,item.direction_revision);
    return Boolean(data?.master_revision && itemRevision && itemRevision !== data.master_revision);
  }
  function revisionState(agent, data=workspaceData) { return isStale(agent,data) ? 'STALE' : 'CURRENT'; }
  function rawProgress(item) {
    const direct = first(item?.progress_percent,item?.progress);
    if (typeof direct === 'number' && Number.isFinite(direct)) return direct;
    if (direct && typeof direct === 'object') {
      const total = Number(first(direct.total,direct.steps_total,0));
      const done = Number(first(direct.completed,direct.done,direct.steps_done,0));
      if (total > 0) return done / total * 100;
    }
    const total = Number(first(item?.acceptance_total,item?.acceptance?.total,0));
    const done = Number(first(item?.acceptance_passed,item?.acceptance?.passed,item?.acceptance?.completed,0));
    return total > 0 ? done / total * 100 : 0;
  }
  function displayProgress(task) {
    const value = Math.max(0,Math.min(100,Math.round(rawProgress(task))));
    if (task.owner_verified === true) return 100;
    return Math.min(99,value);
  }
  function acceptance(task) {
    const total = Number(first(task.acceptance_total,task.acceptance?.total,0));
    const done = Number(first(task.acceptance_passed,task.acceptance?.passed,task.acceptance?.completed,0));
    return total > 0 ? `${done} / ${total}` : '—';
  }
  function listHtml(value) {
    const items = arr(value).filter(Boolean);
    return items.length ? `<ul>${items.map(v=>`<li>${esc(typeof v === 'string' ? v : first(v.name,v.id,JSON.stringify(v)))}</li>`).join('')}</ul>` : '<span class="workspace-muted">—</span>';
  }
  async function requestJson(url,options={}) {
    const response = await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(8000),...options});
    let data={}; try { data=await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.error || `${url}: HTTP ${response.status}`);
    return data;
  }
  function normalizeOverview(payload) {
    const data = payload?.overview || payload || {};
    return {
      ...data,
      agents:arr(first(data.agents,data.sessions)), tasks:arr(data.tasks), checkpoints:arr(data.checkpoints),
      master_revision:first(data.master_revision,data.direction_revision),
      updated_at:first(data.updated_at,data.last_update), source:data.source || 'workspace-api'
    };
  }
  function legacyAgent(session,leases) {
    const sid=first(session.id,session.session_id,session.agent_session_id);
    const owned=leases.filter(x=>first(x.agent_session_id,x.session_id)===sid).map(x=>first(x.resource_key,x.path)).filter(Boolean);
    return {...session,id:first(session.id,session.agent_id,sid),name:first(session.display_name,session.name,session.agent_id,sid),
      status:first(session.status,session.state,'active'),assigned_task:first(session.task_title,session.task_id),
      updated_at:first(session.updated_at,session.last_update,session.heartbeat_at,session.last_seen_at),
      owned_files:arr(first(session.owned_files,session.owned,owned))};
  }
  function normalizeLegacy(workspace,backlog) {
    const sessions=arr(workspace.sessions), leases=arr(workspace.leases);
    const bySession=new Map(sessions.map(s=>[first(s.id,s.session_id),s]));
    const seen=new Set(), tasks=[];
    for (const raw of [...arr(workspace.tasks),...arr(backlog.tasks)]) {
      const id=String(first(raw.id,raw.title,tasks.length)); if (seen.has(id)) continue; seen.add(id);
      const sid=first(raw.assigned_session_id,raw.session_id), session=bySession.get(sid);
      tasks.push({...raw,status:first(raw.status,raw.state,'planned'),owner_verified:raw.owner_verified===true,
        assigned_agent:first(raw.assigned_agent,raw.agent_name,session?.display_name,session?.agent_id,sid),
        updated_at:first(raw.updated_at,raw.last_update)});
    }
    const agents=sessions.map(s=>legacyAgent(s,leases));
    const timestamps=[...agents,...tasks,...arr(workspace.events)].map(x=>first(x.updated_at,x.timestamp)).filter(Boolean).sort((a,b)=>Date.parse(b)-Date.parse(a));
    return {available:workspace.available!==false || agents.length>0 || tasks.length>0,agents,tasks,checkpoints:[],leases,
      events:arr(workspace.events),critical_events:arr(workspace.critical_events),
      master_revision:first(workspace.master_revision,workspace.summary?.master_revision),updated_at:timestamps[0]||null,
      source:'legacy-live-adapter',source_warning:'Новый Workspace backend ещё не подключён; показаны live-данные текущих API.'};
  }
  const workspaceDataAdapter = {
    async overview() {
      try { return normalizeOverview(await requestJson('/api/workspace/overview')); }
      catch (primaryError) {
        const [w,b]=await Promise.allSettled([requestJson('/api/admin/workspace'),requestJson('/api/tasks')]);
        if (w.status==='rejected' && b.status==='rejected') throw primaryError;
        return normalizeLegacy(w.status==='fulfilled'?w.value:{available:false},b.status==='fulfilled'?b.value:{tasks:[]});
      }
    },
    async ownerVerification(taskId,ownerVerified,note) {
      return requestJson(`/api/workspace/tasks/${encodeURIComponent(taskId)}/owner-verification`,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({verified:ownerVerified===true,note:String(note||'').trim()})
      });
    },
    async prepareRestore(checkpointId) {
      return requestJson(`/api/workspace/checkpoints/${encodeURIComponent(checkpointId)}/restore-plan`,{
        method:'POST',headers:{'Content-Type':'application/json'},body:'{}'
      });
    }
  };
  function summaryHtml(data) {
    const agents=arr(data.agents),tasks=arr(data.tasks),checkpoints=arr(data.checkpoints);
    const activeAgents=agents.filter(a=>normalizeStatus(first(a.status,a.state))==='ACTIVE'&&!isStale(a,data)).length;
    const activeTasks=tasks.filter(t=>normalizeStatus(first(t.status,t.state),t.owner_verified)==='ACTIVE').length;
    const waiting=tasks.filter(t=>normalizeStatus(first(t.status,t.state),t.owner_verified)==='WAITING OWNER').length;
    const current=checkpoints.find(c=>c.current===true||c.is_current===true||String(c.status||'').toLowerCase()==='current');
    const rows=[['MASTER REVISION',first(data.master_revision,'—')],['ACTIVE agents',activeAgents],['ACTIVE tasks',activeTasks],
      ['WAITING OWNER REVIEW',waiting],['CURRENT KNOWN GOOD',first(current?.reference,current?.revision,current?.commit_id,current?.tree_id,'—')],
      ['last update',formatTime(data.updated_at)]];
    return rows.map(([k,v])=>`<div class="workspace-metric-card"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');
  }
  function agentCardsHtml(agents,data) {
    if (!agents.length) return empty('Активные агенты пока не опубликованы backend-ом.');
    return agents.map(agent=>{
      const status=isStale(agent,data)?'STALE':normalizeStatus(first(agent.status,agent.state));
      const name=agent.display_name || agent.name || agent.agent_id || agent.id || 'Agent';
      const task=first(agent.assigned_task,agent.task,agent.task_title,agent.task_id,'—');
      const updated=first(agent.updated_at,agent.last_update,agent.heartbeat_at,agent.last_seen_at);
      const ackRevision=first(agent.ack_revision,agent.direction_revision,agent.master_revision,'');
      const progress=Math.min(99,Math.max(0,Math.round(rawProgress(agent))));
      return `<article class="workspace-agent-card ${status==='STALE'?'is-stale':''}">
        <div class="workspace-card-head"><div><h3>${esc(name)}</h3><div class="workspace-card-task">${esc(task)}</div></div>
          <span class="workspace-status ${statusClass(status)}">${esc(status)}</span></div>
        <div class="workspace-progress-line"><div class="workspace-progress"><i style="width:${progress}%"></i></div><b>${progress}%</b></div>
        <div class="workspace-card-meta"><span>Последнее обновление: <b>${formatTime(updated)}</b></span>
          <span title="${esc(ackRevision)}">Revision: <b class="${revisionState(agent,data)==='STALE'?'workspace-text-bad':''}">${revisionState(agent,data)}</b></span></div>
        <details><summary>Детали агента</summary><div class="workspace-detail-grid">
          <div><b>Current step</b>${listHtml(first(agent.current_step,agent.step))}</div>
          <div><b>Owned files / zones</b>${listHtml(first(agent.owned_files,agent.owned_paths,agent.owned,agent.resources))}</div>
          <div><b>Dependencies</b>${listHtml(agent.dependencies)}</div><div><b>Blockers</b>${listHtml(agent.blockers)}</div>
          <div><b>Tests</b>${listHtml(first(agent.tests,agent.verification))}</div><div><b>Handoff</b>${listHtml(first(agent.handoff,agent.handoff_path))}</div>
        </div></details></article>`;
    }).join('');
  }
  function taskCardsHtml(tasks) {
    if (!tasks.length) return empty('Workspace backend пока не вернул задач.');
    return tasks.map(task=>{
      const status=isStale(task)?'STALE':normalizeStatus(first(task.status,task.state),task.owner_verified);
      const progress=displayProgress(task);
      const title=task.title || task.name || task.id || 'Task';
      const agent=first(task.assigned_agent,task.agent_name,task.agent,task.assigned_session_id,'—');
      return `<article class="workspace-task-card ${status==='STALE'?'is-stale':''}">
        <div class="workspace-card-head"><div><h3>${esc(title)}</h3><small>${esc(task.id||'')}</small></div>
          <span class="workspace-status ${statusClass(status)}">${esc(status)}</span></div>
        <div class="workspace-task-grid"><div><span>Assigned agent</span><b>${esc(agent)}</b></div>
          <div><span>Acceptance</span><b>${esc(acceptance(task))}</b></div>
          <div><span>Last update</span><b>${formatTime(first(task.updated_at,task.last_update))}</b></div>
          <div><span>Dependencies</span><b>${esc(arr(task.dependencies).filter(Boolean).join(', ')||'—')}</b></div></div>
        <div class="workspace-progress-line"><div class="workspace-progress"><i style="width:${progress}%"></i></div><b>${progress}%</b></div>
      </article>`;
    }).join('');
  }
  function ownerReviewHtml(tasks) {
    const waiting=tasks.filter(t=>normalizeStatus(first(t.status,t.state),t.owner_verified)==='WAITING OWNER');
    if (!waiting.length) return empty('Нет задач, ожидающих проверки владельца.');
    return waiting.map(task=>`<article class="workspace-review-card" data-review-card="${esc(task.id)}">
      <div class="workspace-card-head"><div><h3>${esc(task.title||task.name||task.id)}</h3><small>${esc(first(task.assigned_agent,task.agent_name,'—'))}</small></div>
        <span class="workspace-status workspace-status-warn">WAITING OWNER</span></div>
      <div class="workspace-review-actions">
        <button class="btn" type="button" data-owner-choice="true" data-task-id="${esc(task.id)}">✓ Проверил — работает</button>
        <button class="btn red" type="button" data-owner-choice="false" data-task-id="${esc(task.id)}">✕ Проверил — не работает</button>
      </div>
      <div class="workspace-review-note" data-owner-note-wrap="${esc(task.id)}" hidden>
        <label>Комментарий владельца<textarea rows="3" id="ownerReviewNote-${esc(task.id)}" data-owner-note="${esc(task.id)}"
          placeholder="Что именно проверено / что не работает"></textarea></label>
        <button class="btn" type="button" data-owner-submit="${esc(task.id)}">Сохранить проверку</button>
        <span class="workspace-muted" data-owner-result-label="${esc(task.id)}"></span>
      </div></article>`).join('');
  }
  function currentKnownGood(checkpoints) {
    const explicit=checkpoints.find(c=>c.current===true||c.is_current===true||String(c.status||'').toLowerCase()==='current');
    if(explicit)return explicit;
    const projectKnownGood=checkpoints.filter(c=>String(c.type||'').toLowerCase()==='project_known_good');
    projectKnownGood.sort((a,b)=>Date.parse(first(b.created_at,b.updated_at,0))-Date.parse(first(a.created_at,a.updated_at,0)));
    return projectKnownGood[0]||null;
  }
  function knownGoodHtml(checkpoints) {
    const c=currentKnownGood(checkpoints);
    if (!c) return empty('Current Known Good пока не опубликован backend-ом.');
    const id=first(c.id,c.revision,c.commit_id,c.tree_id);
    return `<div class="workspace-known-good-current"><div class="workspace-card-head"><div>
      <span class="workspace-kicker">★ Current Known Good</span><h3>${esc(first(c.label,c.name,c.revision,c.id,'Checkpoint'))}</h3></div>
      <span class="workspace-status workspace-status-good">OWNER VERIFIED</span></div>
      <div class="workspace-task-grid"><div><span>timestamp</span><b>${formatTime(first(c.owner_verified_at,c.created_at,c.timestamp,c.updated_at))}</b></div>
        <div><span>revision</span><b>${esc(first(c.master_revision,c.revision,c.reference,'—'))}</b></div>
        <div><span>commit / tree id</span><b>${esc(first(c.reference,c.source_git_revision,c.snapshot_ref,c.commit_id,c.tree_id,c.commit,'—'))}</b></div>
        <div><span>verified features</span><b>${esc(arr(first(c.verified_features,c.features)).join(', ')||'—')}</b></div></div>
      <button class="btn ghost" type="button" data-prepare-restore="${esc(id)}">Подготовить восстановление</button></div>`;
  }
  function checkpointHistoryHtml(checkpoints) {
    const current=currentKnownGood(checkpoints), history=checkpoints.filter(c=>c!==current);
    if (!history.length) return empty('Предыдущих Known Good checkpoints пока нет.');
    return history.map(c=>{const id=first(c.id,c.revision,c.source_git_revision,c.commit_id,c.tree_id);return `<div class="workspace-checkpoint-row"><div>
      <b>${esc(first(c.label,c.name,c.revision,c.id,'Checkpoint'))}</b><small>${formatTime(first(c.owner_verified_at,c.created_at,c.timestamp,c.updated_at))} · ${esc(first(c.reference,c.source_git_revision,c.snapshot_ref,c.commit_id,c.tree_id,c.commit,'—'))}</small></div>
      <button class="btn ghost" type="button" data-prepare-restore="${esc(id)}">Подготовить восстановление</button></div>`;}).join('');
  }
  function diagnosticsHtml(data) {
    const leases=arr(data.leases),events=arr(data.events);
    if (!leases.length&&!events.length) return empty('Дополнительная MAWC-диагностика недоступна в текущем контракте.');
    const leaseRows=leases.length?leases.map(x=>`<tr><td>${esc(first(x.resource_type,'resource'))}</td><td>${esc(first(x.resource_key,x.path,'—'))}</td><td>${esc(normalizeStatus(first(x.status,x.state)))}</td></tr>`).join(''):'<tr><td colspan="3">—</td></tr>';
    const eventRows=events.slice(0,20).map(x=>`<div class="workspace-event"><b>${esc(first(x.event,x.type,'event'))}</b><span>${esc(x.detail||'')}</span><small>${formatTime(first(x.timestamp,x.updated_at))}</small></div>`).join('');
    return `<div class="workspace-diagnostics-grid"><div><h4>Resource leases</h4><div class="workspace-table-wrap"><table>
      <tr><th>Type</th><th>Resource</th><th>Status</th></tr>${leaseRows}</table></div></div>
      <div><h4>Recent events</h4><div class="workspace-events">${eventRows||empty('Нет событий.')}</div></div></div>`;
  }
  function render(data) {
    workspaceData=data;
    $('#workspaceSummary').innerHTML=summaryHtml(data);
    $('#workspaceAgents').innerHTML=agentCardsHtml(arr(data.agents),data);
    $('#workspaceTasks').innerHTML=taskCardsHtml(arr(data.tasks));
    $('#workspaceOwnerReview').innerHTML=ownerReviewHtml(arr(data.tasks));
    $('#workspaceKnownGood').innerHTML=knownGoodHtml(arr(data.checkpoints));
    $('#workspaceCheckpointHistory').innerHTML=checkpointHistoryHtml(arr(data.checkpoints));
    $('#workspaceDiagnostics').innerHTML=diagnosticsHtml(data);
    const updated=$('#workspaceLastUpdate'); if(updated) updated.textContent=`Последнее обновление: ${formatTime(data.updated_at)}`;
    const critical=$('#workspaceCritical'), issues=arr(data.critical_events);
    if(critical){critical.textContent=data.source_warning||(issues.length?`${issues.length} критических Workspace-событий требуют внимания.`:'Критических Workspace-событий нет.');
      critical.className=`workspace-source-note${data.source_warning||issues.length?' is-warn':''}`;}
  }
  async function loadWorkspaceAdmin() {
    if (workspaceAdminPending) return workspaceAdminPending;
    workspaceAdminPending=(async()=>{const status=$('#workspaceStatus');
      if(status){status.textContent='обновление…';status.className='tag amb';}
      try {const data=await workspaceDataAdapter.overview();render(data);
        if(status){status.textContent=data.source==='workspace-api'?'LIVE':'LIVE · adapter';status.className='tag g';status.title=new Date().toLocaleTimeString('ru-RU');}}
      catch(error){if(status){status.textContent='нет данных';status.className='tag red';}
        const message=`Workspace недоступен: ${error.message}`;
        if($('#workspaceCritical')){$('#workspaceCritical').textContent=message;$('#workspaceCritical').className='workspace-source-note is-warn';}
        ['#workspaceSummary','#workspaceAgents','#workspaceTasks','#workspaceOwnerReview','#workspaceKnownGood','#workspaceCheckpointHistory','#workspaceDiagnostics']
          .forEach(s=>{const el=$(s);if(el)el.innerHTML=empty(message);});}
    })();
    try{return await workspaceAdminPending;}finally{workspaceAdminPending=null;}
  }
  function beginOwnerReview(taskId,result) {
    const wrap=[...document.querySelectorAll('[data-owner-note-wrap]')].find(n=>n.dataset.ownerNoteWrap===taskId);
    if(!wrap)return; wrap.hidden=false; wrap.dataset.ownerVerified=result===true?'true':'false';
    const label=wrap.querySelector('[data-owner-result-label]');
    if(label)label.textContent=result===true?'Результат: работает. Добавьте note и сохраните.':'Результат: не работает. Опишите проблему и сохраните.';
    wrap.querySelector('textarea')?.focus();
  }
  async function submitOwnerVerification(taskId) {
    const wrap=[...document.querySelectorAll('[data-owner-note-wrap]')].find(n=>n.dataset.ownerNoteWrap===taskId);
    if(!wrap||!('ownerVerified' in wrap.dataset))return;
    const note=wrap.querySelector('textarea')?.value||'';
    const verified=wrap.dataset.ownerVerified==='true';
    const button=wrap.querySelector('[data-owner-submit]');
    if(button)button.disabled=true;
    try {
      await workspaceDataAdapter.ownerVerification(taskId,verified,note);
      await loadWorkspaceAdmin();
    } catch(error) {
      const label=wrap.querySelector('[data-owner-result-label]');
      if(label)label.textContent=`Backend не принял проверку: ${error.message}`;
    } finally {
      if(button)button.disabled=false;
    }
  }
  function restorePlanHtml(plan,checkpointId) {
    const summary=first(plan.summary,plan.message,`Restore plan для ${checkpointId}`);
    const changed=arr(first(plan.changed_files,plan.files,plan.diff_files));
    const removed=arr(plan.files_that_would_be_removed);
    const conflicts=arr(plan.conflicts);
    const dirty=arr(plan.current_dirty_state);
    const safeTarget=first(plan.safe_target_workspace,'—');
    const targetRevision=first(plan.target_revision,'—');
    const diff=first(plan.diff,plan.patch,plan.plan);
    return `<div class="workspace-restore-result"><b>${esc(summary)}</b>
      <div class="workspace-task-grid"><div><span>Target revision</span><b>${esc(targetRevision)}</b></div><div><span>Safe target workspace</span><b>${esc(safeTarget)}</b></div></div>
      ${changed.length?`<div><span>Changed files</span>${listHtml(changed)}</div>`:''}
      ${removed.length?`<div><span>Would be removed</span>${listHtml(removed)}</div>`:''}
      ${conflicts.length?`<div><span>Conflicts</span>${listHtml(conflicts)}</div>`:''}
      ${dirty.length?`<div><span>Current dirty state</span>${listHtml(dirty)}</div>`:''}
      ${diff?`<pre>${esc(typeof diff==='string'?diff:JSON.stringify(diff,null,2))}</pre>`:''}
      <p class="workspace-muted">Это только план восстановления. Активный workspace не изменяется.</p>
    </div>`;
  }
  async function prepareRestorePlan(checkpointId) {
    const root=$('#workspaceRestorePlan');
    if(!root||!checkpointId)return;
    root.innerHTML=empty('Подготавливаю restore plan / diff…');
    try {
      const plan=await workspaceDataAdapter.prepareRestore(checkpointId);
      root.innerHTML=restorePlanHtml(plan,checkpointId);
    } catch(error) {
      root.innerHTML=empty(`Restore plan недоступен: ${error.message}`);
    }
  }
  function runtimeMetric(label,value){return `<div class="kv"><b>${esc(label)}</b><span>${esc(value)}</span></div>`;}
  async function loadRuntimeOverview(){
    if(runtimeOverviewPending)return runtimeOverviewPending;
    runtimeOverviewPending=(async()=>{
      const root=$('#runtimeOverviewMetrics'),status=$('#runtimeOverviewStatus');
      if(!root||!status)return;
      try{
        const data=await requestJson('/api/app');
        const app=data.app||{},workspace=app.workspace||{available:false},summary=workspace.summary||{};
        root.innerHTML=[runtimeMetric('Агент',app.chat?.agent_ready===true?'запущен':'нет данных'),
          runtimeMetric('Workspace',workspace.available?`${summary.active_sessions??0} активных агентов`:'нет данных')].join('');
        status.textContent=data.status==='degraded'?'DEGRADED':'OK';
        status.className=data.status==='degraded'?'tag amb':'tag g';
      }catch(error){root.innerHTML=empty(`Runtime status недоступен: ${error.message}`);status.textContent='нет данных';status.className='tag red';}
    })();
    try{return await runtimeOverviewPending;}finally{runtimeOverviewPending=null;}
  }
  document.addEventListener('click',event=>{
    const nav=event.target.closest?.('.nav[data-page]');
    if(nav?.dataset.page==='workspace')setTimeout(loadWorkspaceAdmin,0);
    if(nav?.dataset.page==='overview')setTimeout(loadRuntimeOverview,0);
    const choice=event.target.closest?.('[data-owner-choice]');
    if(choice)beginOwnerReview(choice.dataset.taskId,choice.dataset.ownerChoice==='true');
    const submit=event.target.closest?.('[data-owner-submit]');
    if(submit)submitOwnerVerification(submit.dataset.ownerSubmit);
    const restore=event.target.closest?.('[data-prepare-restore]');
    if(restore)prepareRestorePlan(restore.dataset.prepareRestore);
  });
  setInterval(()=>{
    if(document.hidden)return;
    if($('.page[data-page="workspace"]')?.classList.contains('act'))loadWorkspaceAdmin();
    if($('.page[data-page="overview"]')?.classList.contains('act'))loadRuntimeOverview();
  },15000);
  window.workspaceDataAdapter=workspaceDataAdapter;
  window.loadWorkspaceAdmin=loadWorkspaceAdmin;
  window.loadRuntimeOverview=loadRuntimeOverview;
  loadRuntimeOverview();
})();
