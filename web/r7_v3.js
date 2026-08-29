const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const pretty = (value) => JSON.stringify(value ?? null, null, 2);

const appState = {
  selectedNav: 'workbench',
  selectedNode: 'Q',
  selectedDetailTab: 'trace',
  selectedInspectorTab: 'output',
  evidenceTab: 'evidence',
  selectedCheckpointId: null,
  run: null,
  evalSuite: null,
  health: null,
  forecastPacks: [],
  busy: false,
};

const NODE_META = {
  Q: {name:'Question', code:'serve_visualizer.py', why:'研究问题进入 Runtime 边界；这里记录用户目标、Domain Lens 与 ExecutionContext。', input:['Research Question','Domain Lens','Execution Identity'], output:['Run metadata','Question event']},
  DEC: {name:'Decomposition', code:'r3_decomposition.py', why:'把一个宽泛研究问题拆成语义子问题；它决定“需要知道什么”，但没有数据源执行权。', input:['Research Question'], output:['SubQuestions','Source Intents']},
  QC: {name:'Query Compiler', code:'r3_decomposition.py', why:'把语义 capability 映射到可信 provider / series / Tool。Model 不能提供 URL、API key 或任意 series。', input:['Source Intents','Approved capability catalog'], output:['Validated QuerySpecs']},
  QN: {name:'Q1..Qn Execution', code:'scheduler.py / agent.py', why:'Scheduler 只运行依赖满足的 Task；Runtime 负责 Tool validation、Policy、Retry 与执行。', input:['ExecutionPlan','QuerySpecs'], output:['Tool Results','Task State']},
  E: {name:'Evidence', code:'evidence.py / r5_quality.py', why:'Tool Result 先注册为 Evidence，再评估 authority、freshness、completeness、relevance 与 relations。', input:['Source Tool Results'], output:['EvidenceStore','Quality','Relations','Citations']},
  S1: {name:'S1 Research Synthesis', code:'r3_synthesis.py / r5_quality.py', why:'只使用已注册 Evidence 形成 grounded research conclusion，并保留 evidence_ids、limitations 与非概率 support score。', input:['Evidence[]','EvidenceQuality','Relations'], output:['Research Synthesis','Claims','Confidence','Limitations']},
  D1: {name:'D1 Domain Brief', code:'r6_domain.py', why:'Investment / Policy 只改变解释与决策框架，不改变前面的 Evidence collection，也不能提高 S1 confidence。', input:['S1 Research Synthesis','Domain Lens'], output:['Investment / Policy Brief','Counterevidence','Monitoring']},
  F1: {name:'F1 Forecast Pack', code:'r7_forecast.py', why:'把观点转成可结算 contract：baseline、direction、horizon、due date、Evidence lineage、invalidation 和 settlement rule。', input:['S1','D1'], output:['Forecast Pack','Scenario','Saved Forecasts']},
  EV: {name:'Eval / Tracking', code:'r7_evals.py / observability.py', why:'Trace 解释发生了什么；Eval 判断是否满足合同；Checkpoint 记录哪些状态真正落盘。', input:['Run artifacts','Trace','Forecast Pack'], output:['Eval reports','Tracking','Checkpoint snapshots']},
};

async function post(payload) {
  const response = await fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || data.error || `HTTP ${response.status}`);
  return data;
}

function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => el.classList.remove('show'), 2200);
}

function setBusy(busy, label = '') {
  appState.busy = busy;
  ['#run-btn','#health-btn','#eval-btn','#check-forecast-btn'].forEach((id) => {
    const el = $(id); if (el) el.disabled = busy;
  });
  $('#run-status').textContent = busy ? (label || 'RUNNING') : (appState.run ? (appState.run.ok ? 'COMPLETED' : 'FAILED') : 'IDLE');
  $('#run-status').className = `pill ${busy ? 'running' : appState.run?.ok ? 'done' : appState.run ? 'fail' : ''}`;
}

async function loadForecastPacks(preferId = null) {
  try {
    const payload = await post({action:'r7_packs'});
    appState.forecastPacks = payload.packs || [];
    const select = $('#forecast-pack');
    const old = preferId || select.value;
    select.innerHTML = '<option value="">none</option>';
    appState.forecastPacks.forEach((pack) => {
      const opt = document.createElement('option');
      opt.value = pack.pack_id;
      opt.textContent = `${pack.pack_id} · ${pack.scenario || '—'} · ${(pack.scoreboard || {}).resolved || 0} resolved`;
      select.appendChild(opt);
    });
    if (old && appState.forecastPacks.some((p) => p.pack_id === old)) select.value = old;
    else if (appState.forecastPacks.length) select.value = appState.forecastPacks[0].pack_id;
  } catch (error) {
    console.warn(error);
  }
}

async function runResearch() {
  setBusy(true, 'RUNNING');
  try {
    const payload = await post({
      action:'r7_run',
      goal:$('#goal').value.trim(),
      domain:$('#domain').value,
      context_preset:$('#context-preset').value,
    });
    appState.run = payload;
    appState.evalSuite = null;
    appState.selectedNode = payload.ok ? 'F1' : 'Q';
    appState.selectedDetailTab = 'trace';
    appState.selectedInspectorTab = 'output';
    appState.selectedCheckpointId = payload.latest_checkpoint?.checkpoint_id || null;
    renderAll();
    if (payload.forecast_pack?.pack_id) await loadForecastPacks(payload.forecast_pack.pack_id);
    toast(payload.ok ? 'Research run completed' : `Run failed: ${payload.error?.message || 'unknown error'}`);
  } catch (error) {
    toast(`Run error: ${error.message}`);
  } finally {
    setBusy(false);
    renderStatusBar();
  }
}

async function runEvals() {
  setBusy(true, 'EVALUATING');
  try {
    const payload = await post({
      action:'r7_evals',
      goal:$('#goal').value.trim(),
      domain:$('#domain').value,
      context_preset:$('#context-preset').value,
    });
    appState.run = payload.research_result || null;
    appState.evalSuite = payload.eval_suite || null;
    appState.selectedNode = 'EV';
    appState.selectedInspectorTab = 'eval';
    appState.selectedDetailTab = 'trace';
    appState.selectedCheckpointId = appState.run?.latest_checkpoint?.checkpoint_id || null;
    renderAll();
    toast(`Evals: ${appState.evalSuite?.passed || 0}/${appState.evalSuite?.total || 0} passed`);
  } catch (error) {
    toast(`Eval error: ${error.message}`);
  } finally {
    setBusy(false);
    renderStatusBar();
  }
}

async function checkForecast() {
  const packId = $('#forecast-pack').value;
  if (!packId) return toast('没有 Saved Forecast 可检查');
  setBusy(true, 'CHECKING');
  try {
    const payload = await post({action:'r7_check', pack_id:packId, context_preset:$('#context-preset').value});
    if (!payload.ok) throw new Error(payload.error?.message || 'Forecast check failed');
    const run = payload.research_result || {};
    run.forecast_pack = payload.forecast_pack;
    run.final_artifact = payload.forecast_pack;
    appState.run = run;
    appState.selectedNode = 'F1';
    appState.selectedInspectorTab = 'output';
    appState.selectedDetailTab = 'logic';
    appState.selectedCheckpointId = run.latest_checkpoint?.checkpoint_id || null;
    renderAll();
    await loadForecastPacks(packId);
    toast('Forecast 已使用最新 Evidence 重新检查');
  } catch (error) {
    toast(`Forecast error: ${error.message}`);
  } finally {
    setBusy(false);
    renderStatusBar();
  }
}

async function checkHealth() {
  setBusy(true, 'SOURCE HEALTH');
  try {
    const payload = await post({action:'source_health'});
    appState.health = payload.source_health || null;
    renderSidebarHealth();
    if (appState.selectedNav === 'sources') renderDetail();
    toast(appState.health?.ready ? 'BLS / FRED / EIA READY' : '部分数据源未 READY');
  } catch (error) {
    toast(`Source health error: ${error.message}`);
  } finally {
    setBusy(false);
    renderStatusBar();
  }
}

function currentCheckpoint() {
  const cps = appState.run?.checkpoints || [];
  if (!cps.length) return null;
  return cps.find((cp) => cp.checkpoint_id === appState.selectedCheckpointId) || cps[cps.length - 1];
}

function taskMap() {
  const tasks = appState.run?.plan?.tasks || [];
  return Object.fromEntries(tasks.map((t) => [t.task_id, t]));
}

function nodeState(node) {
  const run = appState.run;
  if (!run) return 'waiting';
  const tasks = taskMap();
  if (node === 'Q' || node === 'DEC' || node === 'QC') return run.blueprint ? 'completed' : 'waiting';
  if (node === 'QN' || node === 'E') {
    const qs = Object.values(tasks).filter((t) => String(t.task_id).startsWith('Q'));
    if (!qs.length) return 'waiting';
    if (qs.some((t) => t.status === 'failed')) return 'failed';
    if (qs.every((t) => t.status === 'completed')) return 'completed';
    if (qs.some((t) => t.status === 'running')) return 'running';
    return 'waiting';
  }
  if (node === 'S1' || node === 'D1' || node === 'F1') return tasks[node]?.status || 'waiting';
  if (node === 'EV') return appState.evalSuite ? 'completed' : run.ok ? 'ready' : 'waiting';
  return 'waiting';
}

function checkpointForNode(node) {
  const boundary = {DEC:'after_plan_created',E:'after_evidence',S1:'after_S1',D1:'after_D1',F1:'after_F1'}[node];
  if (!boundary) return null;
  return (appState.run?.checkpoints || []).find((cp) => cp.boundary === boundary) || null;
}

function renderFlow() {
  const run = appState.run;
  $$('.node').forEach((nodeEl) => {
    const node = nodeEl.dataset.node;
    const state = nodeState(node);
    nodeEl.className = `node ${state === 'completed' ? 'completed' : state === 'failed' ? 'failed' : ''} ${appState.selectedNode === node ? 'selected' : ''}`;
    const status = nodeEl.querySelector('.node-status');
    if (state === 'completed') status.innerHTML = '<strong>✓ completed</strong>';
    else if (state === 'running') status.innerHTML = '<span class="pill running">RUNNING</span>';
    else if (state === 'failed') status.innerHTML = '<span class="pill fail">FAILED</span>';
    else if (state === 'ready') status.innerHTML = '<span class="pill ready">READY</span>';
    else status.textContent = 'waiting';
    const marker = nodeEl.querySelector('.checkpoint-marker');
    const cp = checkpointForNode(node);
    marker.textContent = cp ? `◆ ${cp.checkpoint_id}` : '';
  });

  const tasks = run?.plan?.tasks || [];
  const completed = tasks.filter((t) => t.status === 'completed').length;
  $('#run-id').textContent = run?.run_id || 'Run —';
  $('#run-progress').textContent = tasks.length ? `${completed}/${tasks.length} tasks` : '0/0 tasks';
  $('#run-status').textContent = appState.busy ? 'RUNNING' : run ? (run.ok ? 'COMPLETED' : 'FAILED') : 'IDLE';
  $('#run-status').className = `pill ${appState.busy ? 'running' : run?.ok ? 'done' : run ? 'fail' : ''}`;
}

function summarizeEvent(event) {
  const type = event.type || 'event';
  if (type === 'research_question_received') return 'Research question received';
  if (type === 'decomposition_created') return `Decomposition completed · ${(event.subquestions || []).length} subquestions`;
  if (type === 'queries_compiled') return `Query Compiler · ${(event.queries || []).length} queries`;
  if (type === 'plan_created') return 'Execution plan created';
  if (type === 'scheduler_tick') return `Scheduler · READY ${(event.ready || []).join(', ') || '—'}`;
  if (type === 'task_started') return `${event.task_id} started · ${event.title || ''}`;
  if (type === 'task_completed') return `${event.task_id} completed`;
  if (type === 'task_failed') return `${event.task_id} failed · ${event.error?.message || ''}`;
  if (type === 'evidence_registered') return `Evidence registered · ${event.evidence?.evidence_id || ''}`;
  if (type === 'synthesis_verified') return `${event.task_id} citations verified`;
  if (type === 'quality_assessed') return 'Evidence quality assessed';
  if (type === 'domain_brief_created') return `D1 ${event.domain || ''} brief created`;
  if (type === 'forecast_pack_created') return `F1 Forecast Pack · ${event.pack_id || ''}`;
  if (type === 'forecast_pack_saved') return `Forecast saved · ${event.path || ''}`;
  if (type === 'plan_completed') return 'Plan completed';
  if (type === 'task_runtime_event') return `${event.task_id} · ${event.event?.type || 'runtime event'}`;
  return type;
}

function eventClass(event) {
  const type = event.type || '';
  if (type.includes('failed') || event.event?.type === 'tool_error') return 'fail';
  if (type.includes('completed') || type.includes('registered') || type.includes('verified') || type.includes('saved')) return 'success';
  return '';
}

function renderTrace() {
  const events = appState.run?.events || [];
  if (!events.length) return '<div class="empty">运行研究后显示 Runtime / Scheduler / Evidence / Checkpoint 事件。</div>';
  return `<div class="trace-list">${events.map((event, index) => `
    <div class="trace-row">
      <span class="trace-index">#${String(index + 1).padStart(2,'0')}</span>
      <span class="trace-type ${eventClass(event)}">${esc((event.type || 'INFO').slice(0,12))}</span>
      <span class="trace-text">${esc(summarizeEvent(event))}</span>
    </div>`).join('')}</div>`;
}

function nodePayload(node) {
  const run = appState.run || {};
  const tasks = run.plan?.tasks || [];
  const qTasks = tasks.filter((t) => String(t.task_id).startsWith('Q'));
  if (node === 'Q') return {question:run.question || $('#goal').value, domain:run.domain || $('#domain').value, execution_context:run.execution_context || null};
  if (node === 'DEC') return {subquestions:run.blueprint?.subquestions || [], intents:run.blueprint?.intents || []};
  if (node === 'QC') return {queries:run.blueprint?.queries || []};
  if (node === 'QN') return {tasks:qTasks, results:Object.fromEntries(qTasks.map((t) => [t.task_id, run.results?.[t.task_id]]))};
  if (node === 'E') return {evidence:run.evidence || [], citations:run.citations || [], quality:run.research_synthesis?.quality || null};
  if (node === 'S1') return run.research_synthesis || null;
  if (node === 'D1') return run.domain_brief || null;
  if (node === 'F1') return run.forecast_pack || run.final_artifact || null;
  if (node === 'EV') return {eval_suite:appState.evalSuite, trace:run.trace, checkpoints:run.checkpoints || []};
  return null;
}

function renderLogic() {
  const meta = NODE_META[appState.selectedNode];
  const payload = nodePayload(appState.selectedNode);
  return `<div class="logic-grid">
    <div class="logic-card">
      <div class="kicker">${esc(appState.selectedNode)} · ${esc(meta.name)}</div>
      <h4>WHY</h4><p>${esc(meta.why)}</p>
      <h4>INPUT</h4><ul>${meta.input.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
      <h4>OUTPUT</h4><ul>${meta.output.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
      <h4>RELATED CODE</h4><p><strong>${esc(meta.code)}</strong></p>
    </div>
    <pre class="codebox">${esc(pretty(payload))}</pre>
  </div>`;
}

function renderEvidence() {
  const run = appState.run;
  if (!run) return '<div class="empty">等待 Evidence。</div>';
  const evidence = run.evidence || [];
  const citations = run.citations || [];
  const quality = run.research_synthesis?.quality || {};
  const buttons = `<div class="tabs" style="padding:0 0 9px;border:0">
    <button class="tab ${appState.evidenceTab==='evidence'?'active':''}" data-evidence-sub="evidence">Evidence</button>
    <button class="tab ${appState.evidenceTab==='citations'?'active':''}" data-evidence-sub="citations">Citations</button>
    <button class="tab ${appState.evidenceTab==='quality'?'active':''}" data-evidence-sub="quality">Quality</button>
  </div>`;
  if (appState.evidenceTab === 'citations') {
    return buttons + `<div class="evidence-list">${citations.map((c) => `<article class="evidence-card"><h4>${esc(c.citation)} · ${esc(c.evidence_id)}</h4><div class="card-meta"><span>${esc(c.publisher)}</span><span>${esc(c.title)}</span></div></article>`).join('') || '<div class="empty">No citations.</div>'}</div>`;
  }
  if (appState.evidenceTab === 'quality') {
    const rows = quality.evidence_quality || [];
    return buttons + `<div class="evidence-list">${rows.map((q) => { const d=q.dimensions||{}; return `<article class="evidence-card"><h4>${esc(q.evidence_id)} · ${esc(q.quality_label)} · ${esc(q.quality_score)}</h4><div class="quality-grid"><div class="quality-cell"><span>Authority</span><strong>${esc(d.authority)}</strong></div><div class="quality-cell"><span>Freshness</span><strong>${esc(d.freshness)}</strong></div><div class="quality-cell"><span>Complete</span><strong>${esc(d.completeness)}</strong></div><div class="quality-cell"><span>Relevance</span><strong>${esc(d.relevance)}</strong></div></div></article>`; }).join('') || '<div class="empty">No quality rows.</div>'}</div>`;
  }
  return buttons + `<div class="evidence-list">${evidence.map((e) => `<article class="evidence-card"><h4>${esc(e.evidence_id)} · ${esc(e.source?.title || e.claim || '')}</h4><div class="card-meta"><span>${esc(e.source?.publisher || e.provider)}</span><span>as_of ${esc(e.as_of)}</span><span>${esc(e.unit || '')}</span><span>value ${esc(e.value)}</span></div></article>`).join('') || '<div class="empty">No Evidence.</div>'}</div>`;
}

function renderState() {
  const run = appState.run;
  if (!run) return '<div class="empty">State appears after a run.</div>';
  const tasks = run.plan?.tasks || [];
  const running = tasks.filter((t) => t.status === 'running').map((t) => t.task_id);
  const completed = tasks.filter((t) => t.status === 'completed').map((t) => t.task_id);
  const cp = currentCheckpoint();
  return `<div class="state-grid">
    <section class="state-card"><div class="kicker">STATE · NOW</div><h4>Current Runtime View</h4><dl class="kv"><dt>plan.status</dt><dd>${esc(run.plan?.status)}</dd><dt>current task</dt><dd>${esc(running[0] || (run.ok ? 'completed' : '—'))}</dd><dt>completed</dt><dd>${esc(completed.join(', ') || '—')}</dd><dt>Evidence</dt><dd>${(run.evidence || []).length}</dd><dt>selected node</dt><dd>${esc(appState.selectedNode)}</dd></dl></section>
    <section class="state-card"><div class="kicker">CHECKPOINT · SURVIVES DEATH</div><h4>Latest Durable Snapshot</h4><dl class="kv"><dt>checkpoint</dt><dd>${esc(cp?.checkpoint_id || '—')}</dd><dt>boundary</dt><dd>${esc(cp?.boundary || '—')}</dd><dt>resume candidate</dt><dd>${esc(cp?.recovery?.resume_candidate || '—')}</dd><dt>durable</dt><dd>${cp?.durable ? 'true' : '—'}</dd><dt>restore wired</dt><dd>${cp?.restore_enabled ? 'true' : 'false'}</dd></dl></section>
  </div>`;
}

function renderCheckpointDetail() {
  const cp = currentCheckpoint();
  if (!cp) return '<div class="empty">当前 Run 尚无 Checkpoint。</div>';
  return `<div class="logic-grid">
    <div class="logic-card"><div class="kicker">${esc(cp.checkpoint_id)} · ${esc(cp.boundary)}</div><h4>Durable Snapshot</h4><dl class="kv"><dt>created_at</dt><dd>${esc(cp.created_at)}</dd><dt>run_id</dt><dd>${esc(cp.run_id)}</dd><dt>completed</dt><dd>${esc((cp.plan?.completed_tasks || []).join(', ') || '—')}</dd><dt>ready</dt><dd>${esc((cp.plan?.ready_tasks || []).join(', ') || '—')}</dd><dt>blocked</dt><dd>${esc((cp.plan?.blocked_tasks || []).join(', ') || '—')}</dd><dt>Evidence IDs</dt><dd>${esc((cp.evidence_ids || []).join(', ') || '—')}</dd><dt>S1 / D1 / F1</dt><dd>${cp.artifacts?.S1?'✓':'—'} / ${cp.artifacts?.D1?'✓':'—'} / ${cp.artifacts?.F1?'✓':'—'}</dd><dt>resume candidate</dt><dd>${esc(cp.recovery?.resume_candidate || '—')}</dd></dl><p style="margin-top:10px;color:#8a6319"><strong>Restore NOT WIRED:</strong> snapshot is durable and inspectable, but orchestration resume is not implemented yet.</p></div>
    <pre class="codebox">${esc(pretty(cp))}</pre>
  </div>`;
}

function renderArchitecture() {
  if (appState.selectedNav === 'sources') {
    const rows = appState.health?.results || [];
    return `<div class="kicker">DATA SOURCES</div><h3>BLS / FRED / EIA operational contract</h3><div class="evidence-list" style="margin-top:10px">${rows.map((r) => `<article class="evidence-card"><h4>${esc(r.provider)} · ${esc(r.status)}</h4><div class="card-meta"><span>${esc(r.endpoint)}</span><span>as_of ${esc(r.as_of)}</span><span>${esc(r.freshness)}</span><span>${esc(r.latency_ms)} ms</span></div></article>`).join('') || '<div class="empty">点击“测试数据源 API”加载真实 Source Health。</div>'}</div>`;
  }
  if (appState.selectedNav === 'tools') {
    const queries = appState.run?.blueprint?.queries || [];
    const names = [...new Set([...queries.map((q) => q.tool_name),'synthesize_research_bundle','synthesize_domain_brief','build_forecast_pack'])];
    return `<div class="kicker">TOOL REGISTRY</div><h3>Capability ≠ Permission</h3><div class="design-list">${names.map((n) => `<div class="design-item"><strong>${esc(n)}</strong><p>Model/Planner proposes capability use; Runtime owns validation, Policy, retry and execution.</p></div>`).join('')}</div>`;
  }
  if (appState.selectedNav === 'settings') {
    return `<div class="kicker">RUNTIME SETTINGS</div><h3>Current safe configuration</h3><div class="state-grid" style="margin-top:10px"><div class="state-card"><h4>Domain</h4><p>${esc($('#domain').value)}</p></div><div class="state-card"><h4>Identity</h4><p>${esc($('#context-preset').value)}</p></div></div><p class="muted" style="font-size:9px">V3 keeps settings read-only in this stage; no credential values are exposed to the browser.</p>`;
  }
  return `<div class="kicker">ARCHITECTURE</div><h3>项目设计逻辑</h3><div class="architecture-flow"><span class="arch-node">Question</span><span class="arch-arrow">→</span><span class="arch-node">Decomposer</span><span class="arch-arrow">→</span><span class="arch-node">QueryCompiler</span><span class="arch-arrow">→</span><span class="arch-node">Scheduler</span><span class="arch-arrow">→</span><span class="arch-node">Runtime</span><span class="arch-arrow">→</span><span class="arch-node">Tools</span><span class="arch-arrow">→</span><span class="arch-node">Evidence</span><span class="arch-arrow">→</span><span class="arch-node">S1</span><span class="arch-arrow">→</span><span class="arch-node">D1</span><span class="arch-arrow">→</span><span class="arch-node">F1</span><span class="arch-arrow">→</span><span class="arch-node">Eval / Checkpoint</span></div><div class="design-list">
    <div class="design-item"><strong>Runtime 与 Tool 解耦</strong><p>Model output 是 proposal，不是执行权限。</p></div>
    <div class="design-item"><strong>Evidence 先于 Synthesis</strong><p>Tool Result → Evidence → Quality → Synthesis → Citation。</p></div>
    <div class="design-item"><strong>Domain Lens 不改变抓取</strong><p>Investment / Policy 只改变 D1。</p></div>
    <div class="design-item"><strong>Forecast 必须可证伪</strong><p>baseline / direction / horizon / due date / settlement 缺一不可。</p></div>
    <div class="design-item"><strong>Trace ≠ Eval</strong><p>Trace 解释一次运行；Eval 判断行为是否符合合同。</p></div>
    <div class="design-item"><strong>State ≠ Checkpoint</strong><p>State shows NOW；Checkpoint shows WHAT SURVIVES DEATH。</p></div>
  </div>`;
}

function renderDetail() {
  $$('.detail-tab').forEach((b) => b.classList.toggle('active', b.dataset.detailTab === appState.selectedDetailTab));
  const body = $('#detail-body');
  if (appState.selectedDetailTab === 'trace') body.innerHTML = renderTrace();
  else if (appState.selectedDetailTab === 'logic') body.innerHTML = renderLogic();
  else if (appState.selectedDetailTab === 'evidence') body.innerHTML = renderEvidence();
  else if (appState.selectedDetailTab === 'state') body.innerHTML = renderState();
  else if (appState.selectedDetailTab === 'checkpoint') body.innerHTML = renderCheckpointDetail();
  else body.innerHTML = renderArchitecture();

  $$('[data-evidence-sub]').forEach((b) => b.addEventListener('click', () => { appState.evidenceTab = b.dataset.evidenceSub; renderDetail(); }));
}

function renderOutputInspector() {
  const run = appState.run;
  if (!run) return '<div class="empty">运行研究后，这里显示用户可读的 S1 → D1 → F1 输出。</div>';
  const s1 = run.research_synthesis || {};
  const d1 = run.domain_brief || {};
  const f1 = run.forecast_pack || run.final_artifact || {};
  const score = f1.scoreboard || {};
  const scenario = f1.scenario_tracker?.current_state || '—';
  const thesis = d1.sections?.thesis || d1.sections?.evidence_posture || '—';
  return `<div class="output-stage"><div><div class="kicker">F1 FORECAST PACK</div><strong>${esc(scenario)}</strong></div><span class="pill ${run.ok?'done':'fail'}">${run.ok?'GROUNDED':'FAILED'}</span></div>
    <section class="output-section"><h3>综合答案 / Executive Summary</h3><p>${esc(d1.sections?.executive_summary || d1.answer || s1.answer || '—')}</p></section>
    <section class="output-section"><h3>${d1.domain === 'policy' ? 'Policy Posture' : 'Investment Thesis'}</h3><p>${esc(thesis)}</p></section>
    <section class="output-section"><h3>结构化状态</h3><ul><li>S1 support: ${esc(s1.confidence)} · ${esc(s1.confidence_type)}</li><li>D1 decision: ${esc(d1.decision_status)} · domain=${esc(d1.domain)}</li><li>F1 scenario: ${esc(scenario)}</li><li>Evidence: ${(run.evidence || []).length} · Citations: ${(run.citations || []).length}</li></ul></section>
    <section class="output-section"><h3>Forecast Scoreboard</h3><div class="metric-strip"><div class="metric"><span>OPEN</span><strong>${score.open || 0}</strong></div><div class="metric"><span>HIT</span><strong>${score.hits || 0}</strong></div><div class="metric"><span>MISS</span><strong>${score.misses || 0}</strong></div></div><p>${esc(score.accuracy_type || 'historical_direction_hit_rate_not_probability')}</p></section>`;
}

function renderCheckpointInspector() {
  const cps = appState.run?.checkpoints || [];
  const cp = currentCheckpoint();
  if (!cps.length) return '<div class="empty">当前 Run 尚无 durable research checkpoint。</div>';
  return `<section class="checkpoint-summary"><div class="checkpoint-status"><div><div class="kicker">LATEST CHECKPOINT</div><h3>${esc(cp?.checkpoint_id)}</h3></div><span class="pill done">DURABLE</span></div><dl class="kv"><dt>boundary</dt><dd>${esc(cp?.boundary)}</dd><dt>created</dt><dd>${esc(cp?.created_at)}</dd><dt>resume candidate</dt><dd>${esc(cp?.recovery?.resume_candidate || '—')}</dd><dt>Evidence</dt><dd>${(cp?.evidence_ids || []).length}</dd></dl><div class="checkpoint-warning">Snapshot 已真实落盘，但 orchestration restore/resume 目前明确为 NOT WIRED。</div></section><div class="checkpoint-list">${cps.map((item) => `<button class="checkpoint-button ${item.checkpoint_id===cp?.checkpoint_id?'active':''}" data-checkpoint-id="${esc(item.checkpoint_id)}"><strong>${esc(item.checkpoint_id)} · ${esc(item.boundary)}</strong><span>${esc(item.created_at)} · completed ${(item.plan?.completed_tasks || []).length}/${item.state?.task_count || 0}</span></button>`).join('')}</div>`;
}

function renderEvalInspector() {
  const suite = appState.evalSuite;
  if (!suite) return '<div class="empty">点击“运行 Evals”查看当前版本的 contract checks。</div>';
  return `<div class="output-stage"><div><div class="kicker">EVALUATION</div><strong>${suite.passed}/${suite.total} PASS</strong></div><span class="pill ${suite.passed===suite.total?'pass':'fail'}">${Math.round((suite.pass_rate || 0)*100)}%</span></div><div class="eval-list">${(suite.cases || []).map((entry) => { const r=entry.report||{}; return `<article class="eval-card"><h4>${esc(r.case_id)} <span class="pill ${r.passed?'pass':'fail'}">${r.passed?'PASS':'FAIL'}</span></h4>${(r.checks || []).map((c) => `<div class="card-meta"><span>${c.passed?'✓':'✕'} ${esc(c.check_id)}</span><span>${esc(c.label)}</span></div>`).join('')}</article>`; }).join('')}</div>`;
}

function renderInspector() {
  $$('.inspector-tab').forEach((b) => b.classList.toggle('active', b.dataset.inspectorTab === appState.selectedInspectorTab));
  const body = $('#inspector-body');
  if (appState.selectedInspectorTab === 'output') body.innerHTML = renderOutputInspector();
  else if (appState.selectedInspectorTab === 'checkpoint') body.innerHTML = renderCheckpointInspector();
  else if (appState.selectedInspectorTab === 'eval') body.innerHTML = renderEvalInspector();
  else body.innerHTML = `<pre class="rawbox">${esc(pretty({run:appState.run, eval_suite:appState.evalSuite, health:appState.health}))}</pre>`;

  $$('[data-checkpoint-id]').forEach((b) => b.addEventListener('click', () => {
    appState.selectedCheckpointId = b.dataset.checkpointId;
    appState.selectedInspectorTab = 'checkpoint';
    appState.selectedDetailTab = 'checkpoint';
    renderInspector(); renderDetail(); renderStatusBar();
  }));
}

function renderSidebarHealth() {
  const results = appState.health?.results || [];
  ['BLS','FRED','EIA'].forEach((name) => {
    const row = results.find((r) => r.provider === name);
    const el = $(`#health-${name.toLowerCase()}`);
    el.textContent = row ? (row.ready ? `${name} ✓` : `${name} !`) : name;
    el.className = `health-chip ${row?.ready ? 'ready' : ''}`;
  });
  $('#system-status-text').textContent = appState.health ? (appState.health.ready ? 'ALL SYSTEMS OPERATIONAL' : 'SOURCE ATTENTION') : 'SYSTEM READY';
}

function renderStatusBar() {
  const run = appState.run;
  const cp = currentCheckpoint();
  const tasks = run?.plan?.tasks || [];
  const completed = tasks.filter((t) => t.status === 'completed').length;
  const readyCount = (appState.health?.results || []).filter((r) => r.ready).length;
  $('#status-current').textContent = NODE_META[appState.selectedNode].name;
  $('#status-tasks').textContent = tasks.length ? `${completed}/${tasks.length}` : '—';
  $('#status-evidence').textContent = (run?.evidence || []).length;
  $('#status-trace').textContent = (run?.events || []).length;
  $('#status-checkpoint').textContent = cp?.checkpoint_id || '—';
  $('#status-save').textContent = cp?.created_at ? cp.created_at.split('T')[1]?.slice(0,8) || '—' : '—';
  $('#status-health').textContent = appState.health ? `${readyCount}/3` : '—';
}

function renderHeaderAndInput() {
  const run = appState.run;
  $('#visible-run-id').textContent = run?.run_id || 'No active run';
  $('#input-output-hint').textContent = `${$('#domain').value} · ${$('#context-preset option:checked').textContent}`;
}

function renderAll() {
  renderHeaderAndInput();
  renderFlow();
  renderDetail();
  renderInspector();
  renderSidebarHealth();
  renderStatusBar();
  $$('.nav-btn').forEach((b) => b.classList.toggle('active', b.dataset.nav === appState.selectedNav));
}

function selectNav(nav) {
  appState.selectedNav = nav;
  if (nav === 'workbench') { appState.selectedDetailTab = 'trace'; appState.selectedInspectorTab = 'output'; }
  else if (nav === 'architecture') appState.selectedDetailTab = 'architecture';
  else if (nav === 'sources') { appState.selectedDetailTab = 'architecture'; if (!appState.health) checkHealth(); }
  else if (nav === 'tools') appState.selectedDetailTab = 'architecture';
  else if (nav === 'evidence') { appState.selectedDetailTab = 'evidence'; appState.selectedNode = 'E'; }
  else if (nav === 'forecasts') { appState.selectedNode = 'F1'; appState.selectedInspectorTab = 'output'; appState.selectedDetailTab = 'logic'; }
  else if (nav === 'eval') { appState.selectedNode = 'EV'; appState.selectedInspectorTab = 'eval'; }
  else if (nav === 'trace') appState.selectedDetailTab = 'trace';
  else if (nav === 'checkpoints') { appState.selectedInspectorTab = 'checkpoint'; appState.selectedDetailTab = 'checkpoint'; }
  else if (nav === 'settings') appState.selectedDetailTab = 'architecture';
  renderAll();
}

function exportJson() {
  if (!appState.run) return toast('没有可导出的 run');
  const blob = new Blob([pretty({run:appState.run, eval_suite:appState.evalSuite})], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = `${appState.run.run_id || 'r7-run'}.json`; a.click(); URL.revokeObjectURL(url);
}

async function copyOutput() {
  const text = $('#inspector-body').innerText;
  try { await navigator.clipboard.writeText(text); toast('Output 已复制'); } catch { toast('浏览器未允许 clipboard'); }
}

function bindEvents() {
  $('#run-btn').addEventListener('click', runResearch);
  $('#health-btn').addEventListener('click', checkHealth);
  $('#eval-btn').addEventListener('click', runEvals);
  $('#check-forecast-btn').addEventListener('click', checkForecast);
  $('#export-btn').addEventListener('click', exportJson);
  $('#copy-output').addEventListener('click', copyOutput);
  $('#collapse-sidebar').addEventListener('click', () => $('#app').classList.toggle('sidebar-collapsed'));
  $('#domain').addEventListener('change', renderHeaderAndInput);
  $('#context-preset').addEventListener('change', renderHeaderAndInput);

  $$('.node').forEach((node) => node.addEventListener('click', () => {
    appState.selectedNode = node.dataset.node;
    appState.selectedDetailTab = 'logic';
    renderFlow(); renderDetail(); renderStatusBar();
  }));
  $$('.detail-tab').forEach((tab) => tab.addEventListener('click', () => { appState.selectedDetailTab = tab.dataset.detailTab; renderDetail(); }));
  $$('.inspector-tab').forEach((tab) => tab.addEventListener('click', () => { appState.selectedInspectorTab = tab.dataset.inspectorTab; renderInspector(); }));
  $$('.nav-btn').forEach((btn) => btn.addEventListener('click', () => selectNav(btn.dataset.nav)));

  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') { event.preventDefault(); runResearch(); }
  });
}

async function init() {
  bindEvents();
  renderAll();
  await loadForecastPacks();
  renderHeaderAndInput();
}

init();
