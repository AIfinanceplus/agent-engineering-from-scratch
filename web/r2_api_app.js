const $ = (s) => document.querySelector(s);

const runButton = $('#run-btn');
const evalButton = $('#eval-btn');
const prevButton = $('#prev-btn');
const nextButton = $('#next-btn');
const autoButton = $('#auto-btn');
const resetButton = $('#reset-btn');
const goalInput = $('#goal');
const contextPreset = $('#context-preset');

const planStatus = $('#plan-status');
const planProgress = $('#plan-progress');
const evidenceCount = $('#evidence-count');
const traceKpi = $('#trace-kpi');
const evalKpi = $('#eval-kpi');
const finalResult = $('#final-result');
const planBadge = $('#plan-badge');
const planList = $('#plan-list');
const leftKicker = $('#left-kicker');
const leftTitle = $('#left-title');
const dagHint = $('#dag-hint');
const legend = $('#legend');
const runKicker = $('#run-kicker');
const runTitle = $('#run-title');
const modeStrip = $('#mode-strip');
const modeLabel = $('#mode-label');
const modeHelp = $('#mode-help');
const eventCounter = $('#event-counter');
const currentAction = $('#current-action');
const timeline = $('#timeline');
const codeTitle = $('#code-title');
const codeFile = $('#code-file');
const codePanel = $('#code-panel');
const explainBody = $('#explain-body');
const supportKicker = $('#support-kicker');
const citationTitle = $('#citation-title');
const citationList = $('#citation-list');
const traceDetail = $('#trace-detail');
const evalDetail = $('#eval-detail');
const runtimeDetail = $('#runtime-detail');
const rawEvent = $('#raw-event');

let uiMode = 'api';
let displayEvents = [];
let currentIndex = -1;
let autoTimer = null;
let lastResult = null;
let lastSuite = null;

const pretty = (value) => JSON.stringify(value, null, 2);
const clone = (value) => value == null ? value : JSON.parse(JSON.stringify(value));

async function post(payload) {
  const response = await fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function meaningful(event) {
  if (['plan_created','scheduler_tick','task_started','task_completed','task_failed','evidence_registered','synthesis_verified','plan_completed','plan_failed'].includes(event.type)) return true;
  if (event.type !== 'task_runtime_event') return false;
  return ['model_response','tool_validation','policy_decision','tool_attempt','tool_result','final'].includes(event.event && event.event.type);
}

function buildRunEvents(events) {
  let plan = null;
  let citations = [];
  return (events || []).reduce((items, event) => {
    if (event.plan) plan = clone(event.plan);
    if (event.type === 'synthesis_verified') citations = clone(event.citations || []);
    if (meaningful(event)) items.push({event, plan: clone(plan), citations: clone(citations)});
    return items;
  }, []);
}

function buildEvalEvents(suite) {
  const items = [];
  (suite && suite.cases || []).forEach((entry) => {
    (entry.process || []).forEach((event) => items.push({event, entry}));
  });
  return items;
}

function providerFor(task) {
  if (!task) return '—';
  if (task.task_id === 'H1' || task.task_id === 'C1') return 'BLS';
  if (task.task_id === 'F1') return 'FRED';
  if (task.task_id === 'G1') return 'EIA';
  return 'ANALYSIS';
}

function renderPlan(plan) {
  leftKicker.textContent = 'API SOURCE PLAN';
  leftTitle.textContent = 'H1 / C1 / F1 / G1 / A1';
  dagHint.innerHTML = '<span>H1</span><span>+</span><span>C1</span><span>+</span><span>F1</span><span>+</span><span>G1</span><span>→</span><span>A1</span>';
  legend.style.display = 'flex';
  planList.innerHTML = '';

  if (!plan) {
    planList.innerHTML = '<div class="empty-state">点击“运行 API 研究”。系统只访问 BLS / FRED / EIA API。</div>';
    return;
  }

  (plan.tasks || []).forEach((task) => {
    const card = document.createElement('article');
    card.className = `task-card ${task.status || 'pending'}`;
    card.innerHTML = `<div class="task-head"><span class="task-id">${task.task_id}</span><span class="status-chip ${task.status}">${String(task.status).toUpperCase()}</span></div>`;
    const title = document.createElement('strong');
    title.textContent = task.title;
    const meta = document.createElement('small');
    const series = task.arguments && task.arguments.series_id;
    meta.textContent = series ? `${providerFor(task)} · ${series} · API` : `depends on: ${(task.depends_on || []).join(' + ')}`;
    card.append(title, meta);
    if (task.result && task.result.kind === 'evidence') {
      const source = document.createElement('div');
      source.className = 'source-row';
      source.innerHTML = `<span>${providerFor(task)}</span><strong>${task.result.value} ${task.result.unit}</strong><small>as of ${task.result.as_of || '—'}</small>`;
      card.appendChild(source);
    }
    if (task.error) {
      const failure = document.createElement('div');
      failure.className = 'task-result';
      failure.textContent = `${providerFor(task)} ERROR: ${task.error.message || pretty(task.error)}`;
      card.appendChild(failure);
    }
    planList.appendChild(card);
  });

  const tasks = plan.tasks || [];
  const completed = tasks.filter((task) => task.status === 'completed').length;
  planStatus.textContent = plan.status || '—';
  planProgress.textContent = `${completed} / ${tasks.length}`;
  evidenceCount.textContent = String(tasks.filter((task) => task.result && task.result.kind === 'evidence').length);
  planBadge.textContent = plan.status || 'planned';
  planBadge.className = `badge ${plan.status === 'completed' ? 'completed' : 'neutral'}`;
}

function renderFailure(result) {
  const error = result && result.error || {};
  const provider = error.provider || (result.stage === 'credentials' ? 'CREDENTIALS' : 'UNKNOWN');
  supportKicker.textContent = 'SOURCE ERROR';
  citationTitle.textContent = provider;
  citationList.innerHTML = '';
  const card = document.createElement('article');
  card.className = 'eval-check-card fail';
  const missing = error.missing_env ? `<span>Missing: ${error.missing_env.join(', ')}</span>` : '';
  card.innerHTML = `<strong>${error.task_id ? `${error.task_id} · ` : ''}${provider}</strong><span>${error.message || pretty(error)}</span>${missing}`;
  citationList.appendChild(card);
  currentAction.innerHTML = `<strong>API 运行未完成</strong><span>${provider}: ${error.message || pretty(error)}</span>`;
  finalResult.textContent = 'SOURCE ERROR';
  planStatus.textContent = 'failed';
  planBadge.textContent = 'FAILED';
}

function renderCitations(citations) {
  supportKicker.textContent = 'CITATIONS';
  citationList.innerHTML = '';
  if (!(citations || []).length) {
    citationTitle.textContent = '等待 A1';
    citationList.innerHTML = '<div class="empty-state">A1 完成后显示四个 API 来源。</div>';
    return;
  }
  citationTitle.textContent = `${citations.length} verified`;
  citations.forEach((item) => {
    const row = document.createElement('article');
    row.className = 'citation-row';
    row.innerHTML = `<div><strong>${item.citation}</strong><span>${item.publisher}</span></div><span>${item.title}</span><code>${item.uri}</code>`;
    citationList.appendChild(row);
  });
}

function renderEvalCases(suite, activeCaseId) {
  leftKicker.textContent = 'API EVALS';
  leftTitle.textContent = 'Live Run Contracts';
  dagHint.innerHTML = '<span>Live Run</span><span>→</span><span>Checks</span><span>→</span><span>Verdict</span>';
  legend.style.display = 'none';
  planList.innerHTML = '';
  (suite && suite.cases || []).forEach((entry) => {
    const report = entry.report || {};
    const card = document.createElement('article');
    card.className = `task-card ${report.passed ? 'completed' : 'failed'}`;
    if (entry.case.case_id === activeCaseId) card.classList.add('eval-active-case');
    const checks = report.checks || [];
    card.innerHTML = `<div class="task-head"><span class="task-id">API</span><span class="status-chip ${report.passed ? 'completed' : 'failed'}">${report.passed ? 'PASS' : 'FAIL'}</span></div><strong>${entry.case.case_id}</strong><small>${checks.filter(c => c.passed).length}/${checks.length} checks · H1/C1/F1/G1/A1</small>`;
    planList.appendChild(card);
  });
  planStatus.textContent = 'api evals';
  planProgress.textContent = `${suite.passed} / ${suite.total}`;
  evidenceCount.textContent = `${Math.round((suite.pass_rate || 0) * 100)}%`;
  planBadge.textContent = suite.passed === suite.total ? 'PASS' : 'FAIL';
}

function renderCheck(check) {
  supportKicker.textContent = 'CURRENT CHECK';
  citationTitle.textContent = check.passed ? 'PASS' : 'FAIL';
  citationList.innerHTML = `<article class="eval-check-card ${check.passed ? 'pass' : 'fail'}"><strong>${check.label}</strong><span>Actual: ${pretty(check.actual)}</span><span>Expected: ${pretty(check.expected)}</span>${check.passed ? '' : `<span>${check.failure}</span>`}</article>`;
}

function runMeta(item) {
  const event = item.event;
  if (event.type === 'plan_created') return {label:'API plan created',title:'Planner：四个 API Source Tasks',file:'r2_api_planner.py',code:'H1/C1 = BLS API\nF1 = FRED API\nG1 = EIA API\nA1 depends_on all four',explain:'<p>活跃 R2 已没有 fixture/live 分支；Planner 只生成 API Tool。</p>'};
  if (event.type === 'scheduler_tick') return {label:`READY ${event.ready.join(', ') || '—'}`,title:'Scheduler：释放可执行任务',file:'scheduler.py',code:`READY = ${pretty(event.ready)}\nBLOCKED = ${pretty(event.blocked)}`,explain:'<p>H1/C1/F1/G1 可独立运行，A1 等四条 Evidence。</p>'};
  if (event.type === 'evidence_registered') return {label:`${event.evidence.evidence_id} registered`,title:'EvidenceStore：登记 API provenance',file:'evidence.py',code:pretty(event.evidence),explain:'<p>API response 被归一化后再进入 EvidenceStore。</p>'};
  if (event.type === 'synthesis_verified') return {label:'4 citations verified',title:'A1：Citation verification',file:'scheduler.py',code:pretty(event.citations),explain:'<p>A1 只能引用已经登记的四条 API Evidence。</p>'};
  if (event.type === 'plan_completed') return {label:'API research completed',title:'Final：API research artifact',file:'macro_multisource_analysis.py',code:pretty(event.final_artifact),explain:`<p><strong>${event.final_result}</strong></p>`};
  if (event.type === 'task_started') return {label:`${event.task_id} started`,title:`${event.task_id} · ${providerFor({task_id:event.task_id})}`,file:'scheduler.py',code:pretty(event.arguments),explain:'<p>Task 仍经过统一 Runtime / Validation / Policy / Retry。</p>'};
  if (event.type === 'task_completed') return {label:`${event.task_id} completed`,title:`${event.task_id} completed`,file:'scheduler.py',code:pretty(event.result),explain:'<p>结果写回 Plan State。</p>'};
  if (event.type === 'task_failed') return {label:`${event.task_id} FAILED`,title:`${providerFor({task_id:event.task_id})} source failure`,file:'serve_visualizer.py',code:pretty(event.error),explain:'<p>现在会明确指出失败的 Task / provider，而不是只看到 HTTP 500。</p>'};
  if (event.type === 'task_runtime_event') {
    const inner = event.event || {};
    if (inner.type === 'tool_attempt') return {label:`${event.task_id} · API call`,title:`${providerFor({task_id:event.task_id})} API Tool`,file:event.task_id === 'H1' || event.task_id === 'C1' ? 'api_sources.py' : 'api_sources.py',code:pretty(inner.arguments),explain:'<p>FRED/EIA key 由 Runtime 环境读取，不出现在 Tool arguments。</p>'};
    if (inner.type === 'tool_result') return {label:`${event.task_id} · API result`,title:'Normalized API observation',file:'api_sources.py',code:pretty(inner.result),explain:'<p>BLS/FRED/EIA 不同 JSON 在这里收敛成同一 Evidence contract。</p>'};
    if (inner.type === 'tool_validation') return {label:`${event.task_id} · validate`,title:'Tool validation',file:'tools.py',code:pretty(inner.validation),explain:'<p>API Tool 仍先验证 schema。</p>'};
    if (inner.type === 'policy_decision') return {label:`${event.task_id} · policy`,title:'Policy decision',file:'policy.py',code:pretty(inner.policy),explain:'<p>API-only 不等于跳过权限控制。</p>'};
    return {label:`${event.task_id} · ${inner.type}`,title:'Runtime event',file:'agent.py',code:pretty(inner),explain:'<p>单 Task Runtime 事件。</p>'};
  }
  return {label:event.type,title:'Runtime event',file:'scheduler.py',code:pretty(event),explain:'<p>底层事件。</p>'};
}

function evalMeta(item) {
  const event = item.event;
  if (event.type === 'eval_case_started') return {label:`${event.case_id} · expected`,title:'API Eval contract',file:'r2_api_evals.py',code:pretty(event.expectations),explain:'<p>任务名直接是 H1/C1/F1/G1/A1。</p>'};
  if (event.type === 'eval_agent_run_completed') return {label:`${event.case_id} · live run`,title:'Actual API run',file:'r2_api_evals.py',code:pretty(event.run_summary),explain:'<p>两个评分 profile 共享同一次 live API run，减少重复外部请求。</p>'};
  if (event.type === 'eval_check') return {label:`${event.check_id} ${event.passed ? '✓' : '✕'}`,title:event.label,file:'r2_api_evals.py',code:`actual = ${pretty(event.actual)}\nexpected = ${pretty(event.expected)}\npassed = ${event.passed}`,explain:`<p>${event.passed ? 'PASS' : event.failure}</p>`};
  return {label:`${event.case_id} · ${event.passed ? 'PASS' : 'FAIL'}`,title:'API Eval verdict',file:'r2_api_evals.py',code:pretty(event),explain:'<p>Verdict 来自显式 checks。</p>'};
}

function renderTimeline() {
  timeline.innerHTML = '';
  displayEvents.forEach((item, index) => {
    const meta = uiMode === 'eval' ? evalMeta(item) : runMeta(item);
    const li = document.createElement('li');
    li.className = 'timeline-item';
    if (index < currentIndex) li.classList.add('done');
    if (index === currentIndex) li.classList.add('active');
    li.innerHTML = `<span class="timeline-marker">${index + 1}</span><span>${meta.label}</span>`;
    li.addEventListener('click', () => showStep(index));
    timeline.appendChild(li);
  });
}

function showStep(index) {
  if (!displayEvents.length) return;
  currentIndex = Math.max(0, Math.min(index, displayEvents.length - 1));
  const item = displayEvents[currentIndex];
  const meta = uiMode === 'eval' ? evalMeta(item) : runMeta(item);
  if (uiMode === 'eval') {
    renderEvalCases(lastSuite, item.event.case_id);
    if (item.event.type === 'eval_check') renderCheck(item.event);
  } else {
    renderPlan(item.plan);
    renderCitations(item.citations);
  }
  eventCounter.textContent = `${currentIndex + 1} / ${displayEvents.length}`;
  currentAction.innerHTML = `<strong>${meta.title}</strong><span>${meta.label}</span>`;
  codeTitle.textContent = meta.title;
  codeFile.textContent = meta.file;
  codePanel.textContent = meta.code;
  explainBody.innerHTML = meta.explain;
  traceDetail.textContent = pretty(lastResult && lastResult.trace || {});
  evalDetail.textContent = pretty(lastSuite || {});
  runtimeDetail.textContent = pretty(uiMode === 'eval' ? item.entry : {plan_snapshot:item.plan,reference_date:lastResult && lastResult.reference_date});
  rawEvent.textContent = pretty(item.event);
  renderTimeline();
}

function setRunMode() {
  uiMode = 'api';
  runKicker.textContent = 'API RUN / TRACE';
  runTitle.textContent = 'BLS + FRED + EIA';
  modeStrip.className = 'mode-strip run-mode';
  modeLabel.textContent = 'R2 API-ONLY';
  modeHelp.textContent = 'One click = one POST = one API research run';
}

function setEvalMode() {
  uiMode = 'eval';
  runKicker.textContent = 'API EVAL PROCESS';
  runTitle.textContent = 'Live Run → Checks → Verdict';
  modeStrip.className = 'mode-strip eval-mode';
  modeLabel.textContent = 'R2 API EVALS';
  modeHelp.textContent = 'H1 / C1 / F1 / G1 / A1 only';
}

function stopAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  autoButton.textContent = '自动';
}

async function runAPI() {
  stopAuto(); setRunMode(); runButton.disabled = true;
  try {
    const data = await post({action:'api_run', goal:goalInput.value, context_preset:contextPreset.value});
    lastResult = data;
    lastSuite = null;
    displayEvents = buildRunEvents(data.events || []);
    currentIndex = -1;
    renderPlan(data.plan);
    const trace = data.trace || {};
    traceKpi.textContent = `${trace.span_count || 0} spans · ${(trace.metrics && trace.metrics.tool_attempts) || 0} tools`;
    evalKpi.textContent = 'API ONLY';
    finalResult.textContent = data.final_result || (data.ok ? 'completed' : 'SOURCE ERROR');
    if (!data.ok) renderFailure(data);
    else if (displayEvents.length) showStep(0);
  } catch (error) {
    currentAction.innerHTML = `<strong>Web server error</strong><span>${error.message}</span>`;
  } finally { runButton.disabled = false; }
}

async function runEvals() {
  stopAuto(); setEvalMode(); evalButton.disabled = true;
  try {
    const data = await post({action:'api_evals', goal:goalInput.value, context_preset:contextPreset.value});
    lastResult = data.research_result;
    lastSuite = data.eval_suite;
    displayEvents = buildEvalEvents(lastSuite);
    currentIndex = -1;
    traceKpi.textContent = `${(lastResult && lastResult.trace && lastResult.trace.span_count) || 0} spans`;
    evalKpi.textContent = `${lastSuite.passed}/${lastSuite.total} PASS`;
    finalResult.textContent = `${Math.round(lastSuite.pass_rate * 100)}% pass rate`;
    if (!lastResult.ok) renderFailure(lastResult);
    if (displayEvents.length) showStep(0);
  } catch (error) {
    currentAction.innerHTML = `<strong>Eval web error</strong><span>${error.message}</span>`;
  } finally { evalButton.disabled = false; }
}

function resetView() {
  stopAuto(); setRunMode(); displayEvents = []; currentIndex = -1; lastResult = null; lastSuite = null;
  renderPlan(null); renderCitations([]);
  planStatus.textContent = '未运行'; planProgress.textContent = '0 / 5'; evidenceCount.textContent = '0'; traceKpi.textContent = '—'; evalKpi.textContent = 'API ONLY'; finalResult.textContent = '—';
  eventCounter.textContent = '尚未运行'; timeline.innerHTML = '<li class="empty-state">点击“运行 API 研究”开始。</li>';
  currentAction.innerHTML = '<strong>等待运行</strong><span>只使用 BLS / FRED / EIA API。</span>';
  codeTitle.textContent = '对应代码'; codeFile.textContent = 'r2_api_planner.py'; codePanel.textContent = '等待执行事件…';
  explainBody.innerHTML = '<p>活跃 R2 已移除用户可见的 Fixture/Live 双模式。</p>';
  traceDetail.textContent = '{}'; evalDetail.textContent = '{}'; runtimeDetail.textContent = '{}'; rawEvent.textContent = '{}';
}

prevButton.addEventListener('click', () => { stopAuto(); if (currentIndex > 0) showStep(currentIndex - 1); });
nextButton.addEventListener('click', () => { stopAuto(); if (currentIndex < displayEvents.length - 1) showStep(currentIndex + 1); });
autoButton.addEventListener('click', () => {
  if (autoTimer) { stopAuto(); return; }
  if (!displayEvents.length) return;
  autoButton.textContent = '停止';
  autoTimer = setInterval(() => {
    if (currentIndex >= displayEvents.length - 1) { stopAuto(); return; }
    showStep(currentIndex + 1);
  }, 700);
});
resetButton.addEventListener('click', resetView);
runButton.addEventListener('click', runAPI);
evalButton.addEventListener('click', runEvals);

resetView();
