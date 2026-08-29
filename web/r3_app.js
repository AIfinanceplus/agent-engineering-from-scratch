const $ = (s) => document.querySelector(s);
const pretty = (value) => JSON.stringify(value, null, 2);
const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));

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

let mode = 'run';
let items = [];
let currentIndex = -1;
let timer = null;
let lastResult = null;
let lastSuite = null;

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
  if (['research_question_received','decomposition_created','queries_compiled','plan_created','scheduler_tick','task_started','task_completed','task_failed','evidence_registered','synthesis_verified','plan_completed','plan_failed'].includes(event.type)) return true;
  if (event.type !== 'task_runtime_event') return false;
  return ['tool_validation','policy_decision','tool_attempt','tool_result'].includes(event.event && event.event.type);
}

function buildRunItems(result) {
  let plan = null;
  let citations = [];
  return (result.events || []).reduce((out, event) => {
    if (event.plan) plan = JSON.parse(JSON.stringify(event.plan));
    if (event.type === 'synthesis_verified') citations = JSON.parse(JSON.stringify(event.citations || []));
    if (meaningful(event)) out.push({event, plan: plan ? JSON.parse(JSON.stringify(plan)) : null, citations: JSON.parse(JSON.stringify(citations))});
    return out;
  }, []);
}

function buildEvalItems(suite) {
  const out = [];
  (suite && suite.cases || []).forEach((entry) => {
    (entry.process || []).forEach((event) => out.push({event, entry}));
  });
  return out;
}

function queryMap(blueprint) {
  const map = {};
  (blueprint && blueprint.queries || []).forEach((query) => { map[query.query_id] = query; });
  return map;
}

function renderBlueprint(blueprint, plan) {
  leftKicker.textContent = 'RESEARCH BLUEPRINT';
  leftTitle.textContent = 'Subquestions → Queries';
  legend.style.display = 'flex';
  planList.innerHTML = '';
  if (!blueprint) {
    planList.innerHTML = '<div class="empty-state">运行后显示 Research Decomposition 与 Query Specs。</div>';
    dagHint.innerHTML = '<span>Question</span><span>→</span><span>?</span><span>→</span><span>Queries</span>';
    return;
  }

  const tasks = plan && plan.tasks || [];
  const taskById = Object.fromEntries(tasks.map((task) => [task.task_id, task]));
  const subById = Object.fromEntries((blueprint.subquestions || []).map((sub) => [sub.subquestion_id, sub]));
  const queryIds = (blueprint.queries || []).map((query) => query.query_id);
  dagHint.innerHTML = `${queryIds.map((id) => `<span>${esc(id)}</span>`).join('<span>+</span>')}<span>→</span><span>S1</span>`;

  const divider = document.createElement('div');
  divider.className = 'stage-divider';
  divider.textContent = 'COMPILED QUERIES';
  planList.appendChild(divider);

  (blueprint.queries || []).forEach((query) => {
    const task = taskById[query.query_id] || {};
    const sub = subById[query.subquestion_id] || {};
    const card = document.createElement('article');
    card.className = `blueprint-card ${task.status || 'pending'}`;
    card.innerHTML = `<div class="blueprint-head"><strong>${esc(query.query_id)} · ${esc(query.provider)}</strong><code>${esc(query.capability)}</code></div><p>${esc(sub.question)}</p><small>${esc(sub.rationale)}</small><div class="query-meta"><span>${esc(query.tool_name)}</span><span>${esc(query.arguments && query.arguments.series_id)}</span>${(query.requires_env || []).map((env) => `<span>${esc(env)}</span>`).join('')}</div>`;
    if (task.status) {
      const status = document.createElement('small');
      status.textContent = `Runtime status: ${task.status}`;
      card.appendChild(status);
    }
    planList.appendChild(card);
  });

  if (tasks.length) {
    const synth = taskById.S1;
    if (synth) {
      const card = document.createElement('article');
      card.className = `blueprint-card ${synth.status || 'pending'}`;
      card.innerHTML = `<div class="blueprint-head"><strong>S1 · SYNTHESIS</strong><code>synthesize_research_bundle</code></div><p>Consumes only the Evidence returned by compiled Query Specs.</p><small>depends on: ${esc((synth.depends_on || []).join(' + '))}</small>`;
      planList.appendChild(card);
    }
  }

  const completed = tasks.filter((task) => task.status === 'completed').length;
  planStatus.textContent = plan ? (plan.status || '—') : 'compiled';
  planProgress.textContent = plan ? `${completed} / ${tasks.length}` : `${queryIds.length} queries`;
  planBadge.textContent = plan ? (plan.status || 'planned') : 'compiled';
  planBadge.className = `badge ${plan && plan.status === 'completed' ? 'completed' : 'neutral'}`;
}

function renderFailure(result) {
  const error = result && result.error || {};
  supportKicker.textContent = result.stage === 'credentials' ? 'CREDENTIALS' : 'SOURCE / COMPILE ERROR';
  citationTitle.textContent = error.provider || result.stage || 'ERROR';
  citationList.innerHTML = `<article class="eval-check-card fail"><strong>${esc(error.task_id || error.code || 'error')}</strong><span>${esc(error.message || pretty(error))}</span>${error.missing_env ? `<span>Missing: ${esc(error.missing_env.join(', '))}</span>` : ''}</article>`;
  finalResult.textContent = 'FAILED';
  planStatus.textContent = 'failed';
  planBadge.textContent = 'FAILED';
}

function renderCitations(citations) {
  supportKicker.textContent = 'CITATIONS';
  citationList.innerHTML = '';
  if (!(citations || []).length) {
    citationTitle.textContent = 'waiting';
    citationList.innerHTML = '<div class="empty-state">S1 完成后显示 grounded citations。</div>';
    return;
  }
  citationTitle.textContent = `${citations.length} verified`;
  citations.forEach((item) => {
    const row = document.createElement('article');
    row.className = 'citation-row';
    row.innerHTML = `<div><strong>${esc(item.citation)}</strong><span>${esc(item.publisher)}</span></div><span>${esc(item.title)}</span><code>${esc(item.uri)}</code>`;
    citationList.appendChild(row);
  });
}

function renderEvalCases(suite, activeId) {
  leftKicker.textContent = 'R3 EVALS';
  leftTitle.textContent = 'Blueprint + Execution Contracts';
  legend.style.display = 'none';
  dagHint.innerHTML = '<span>Blueprint</span><span>→</span><span>Checks</span><span>→</span><span>Verdict</span>';
  planList.innerHTML = '';
  (suite && suite.cases || []).forEach((entry) => {
    const report = entry.report || {};
    const card = document.createElement('article');
    card.className = `task-card ${report.passed ? 'completed' : 'failed'}`;
    if (entry.case.case_id === activeId) card.classList.add('eval-active-case');
    const checks = report.checks || [];
    card.innerHTML = `<div class="task-head"><span class="task-id">R3</span><span class="status-chip ${report.passed ? 'completed' : 'failed'}">${report.passed ? 'PASS' : 'FAIL'}</span></div><strong>${esc(entry.case.case_id)}</strong><small>${checks.filter((c) => c.passed).length}/${checks.length} checks</small>`;
    planList.appendChild(card);
  });
  planStatus.textContent = 'r3 evals';
  planProgress.textContent = `${suite.passed} / ${suite.total}`;
  evidenceCount.textContent = `${Math.round((suite.pass_rate || 0) * 100)}%`;
  planBadge.textContent = suite.passed === suite.total ? 'PASS' : 'FAIL';
}

function renderCheck(check) {
  supportKicker.textContent = 'CURRENT CHECK';
  citationTitle.textContent = check.passed ? 'PASS' : 'FAIL';
  citationList.innerHTML = `<article class="eval-check-card ${check.passed ? 'pass' : 'fail'}"><strong>${esc(check.label)}</strong><span>Actual: ${esc(pretty(check.actual))}</span><span>Expected: ${esc(pretty(check.expected))}</span>${check.passed ? '' : `<span>${esc(check.failure)}</span>`}</article>`;
}

function meta(item) {
  const event = item.event;
  if (event.type === 'research_question_received') return {label:'Research question received',title:'Question enters Research Intelligence',file:'r3_decomposition.py',code:`question = ${pretty(event.question)}`,explain:'<p>R3 从自然语言研究问题开始，而不是从写死的 API Task 开始。</p>'};
  if (event.type === 'decomposition_created') return {label:`Decomposed into ${(event.subquestions || []).length} subquestions`,title:'ResearchDecomposer：WHAT do we need to know?',file:'r3_decomposition.py',code:pretty(event.subquestions),explain:'<p>Decomposer 只提出 capability intent，不拥有 URL、series ID 或 credential。</p>'};
  if (event.type === 'queries_compiled') return {label:`Compiled ${(event.queries || []).length} safe queries`,title:'QueryCompiler：intent → approved query',file:'r3_decomposition.py',code:pretty(event.queries),explain:'<p>Query Compiler 从白名单 catalog 映射 provider / series / Tool；这一步才产生可执行 Query Spec。</p>'};
  if (event.type === 'plan_created') return {label:'Dynamic DAG created',title:'R3 Planner：Query Specs → DAG',file:'r3_planner.py',code:pretty(event.plan),explain:'<p>Source Task 数量来自 Query Specs。S1 依赖所有已编译查询，而不是固定 H1/C1/F1/G1。</p>'};
  if (event.type === 'scheduler_tick') return {label:`READY ${event.ready.join(', ') || '—'}`,title:'Scheduler：which compiled queries can run now?',file:'scheduler.py',code:`READY = ${pretty(event.ready)}\nBLOCKED = ${pretty(event.blocked)}`,explain:'<p>Planner 决定 WHAT；Scheduler 决定 WHEN；Runtime 仍决定 HOW。</p>'};
  if (event.type === 'task_started') return {label:`${event.task_id} started`,title:`${event.task_id} enters Runtime`,file:'scheduler.py',code:pretty(event.arguments),explain:'<p>编译后的 Query Spec 仍需经过 Tool validation、Policy、Retry。</p>'};
  if (event.type === 'evidence_registered') return {label:`${event.evidence.evidence_id} registered`,title:'EvidenceStore：provenance starts here',file:'evidence.py',code:pretty(event.evidence),explain:'<p>Tool Result 只有归一化并登记后才成为 Evidence。</p>'};
  if (event.type === 'synthesis_verified') return {label:`${(event.evidence_ids || []).length} Evidence IDs verified`,title:'S1：variable Evidence bundle',file:'r3_synthesis.py',code:pretty({answer:event.answer,evidence_ids:event.evidence_ids,citations:event.citations}),explain:'<p>S1 不知道“必须有四个来源”；它只消费本次 Query Compiler 实际选择的 Evidence bundle。</p>'};
  if (event.type === 'plan_completed') return {label:'Research completed',title:'Final research artifact',file:'r3_synthesis.py',code:pretty(event.final_artifact),explain:`<p><strong>${esc(event.final_result)}</strong></p>`};
  if (event.type === 'task_failed') return {label:`${event.task_id} FAILED`,title:'Source / Runtime failure',file:'serve_visualizer.py',code:pretty(event.error),explain:'<p>失败仍映射回具体 Query ID 与 provider。</p>'};
  if (event.type === 'task_runtime_event') {
    const inner = event.event || {};
    if (inner.type === 'tool_attempt') return {label:`${event.task_id} · Tool attempt`,title:'Runtime executes compiled query',file:'agent.py',code:pretty(inner.arguments),explain:'<p>Model proposal 仍不等于执行权限；Runtime 才调用 Tool。</p>'};
    if (inner.type === 'tool_result') return {label:`${event.task_id} · Tool result`,title:'Source Adapter result',file:'api_sources.py',code:pretty(inner.result),explain:'<p>不同公共 API 在 adapter 层收敛成统一 Evidence contract。</p>'};
    if (inner.type === 'tool_validation') return {label:`${event.task_id} · validate`,title:'Tool validation',file:'tools.py',code:pretty(inner.validation),explain:'<p>Query Compiler 白名单之外，Runtime 仍进行参数 schema 验证。</p>'};
    if (inner.type === 'policy_decision') return {label:`${event.task_id} · policy`,title:'Policy decision',file:'policy.py',code:pretty(inner.policy),explain:'<p>Query Generation 不绕过 Policy Engine。</p>'};
  }
  return {label:event.type,title:event.type,file:'serve_visualizer.py',code:pretty(event),explain:'<p>R3 event.</p>'};
}

function evalMeta(item) {
  const event = item.event;
  if (event.type === 'eval_case_started') return {label:`Case ${event.case_id}`,title:'Eval case started',file:'r3_evals.py',code:pretty(event.check_ids),explain:'<p>Expected contract 在评分前固定。</p>'};
  if (event.type === 'eval_check') return {label:`${event.passed ? '✓' : '✕'} ${event.label}`,title:event.label,file:'r3_evals.py',code:pretty({actual:event.actual,expected:event.expected,passed:event.passed}),explain:event.passed ? '<p>Actual 满足 expected contract。</p>' : `<p>${esc(event.failure)}</p>`};
  if (event.type === 'eval_case_verdict') return {label:`Verdict ${event.passed ? 'PASS' : 'FAIL'}`,title:'Eval verdict',file:'r3_evals.py',code:pretty(event),explain:'<p>Verdict 是 checks 的聚合，不是一个模糊总分。</p>'};
  return {label:event.type,title:event.type,file:'r3_evals.py',code:pretty(event),explain:'<p>Eval process.</p>'};
}

function renderTimeline() {
  timeline.innerHTML = '';
  items.forEach((item, index) => {
    const info = mode === 'eval' ? evalMeta(item) : meta(item);
    const li = document.createElement('li');
    li.className = index === currentIndex ? 'active' : '';
    if (item.event.type === 'decomposition_created') li.classList.add('decomposition-event');
    if (item.event.type === 'queries_compiled') li.classList.add('query-event');
    li.textContent = info.label;
    li.addEventListener('click', () => { currentIndex = index; renderCurrent(); });
    timeline.appendChild(li);
  });
}

function renderCurrent() {
  renderTimeline();
  if (currentIndex < 0 || currentIndex >= items.length) return;
  const item = items[currentIndex];
  const info = mode === 'eval' ? evalMeta(item) : meta(item);
  eventCounter.textContent = `${currentIndex + 1} / ${items.length}`;
  currentAction.innerHTML = `<strong>${esc(info.label)}</strong><span>${esc(info.title)}</span>`;
  codeTitle.textContent = info.title;
  codeFile.textContent = info.file;
  codePanel.textContent = info.code;
  explainBody.innerHTML = info.explain;
  rawEvent.textContent = pretty(item.event);

  if (mode === 'run') {
    renderBlueprint(lastResult && lastResult.blueprint, item.plan || (lastResult && lastResult.plan));
    renderCitations(item.citations && item.citations.length ? item.citations : (lastResult && lastResult.citations));
  } else {
    renderEvalCases(lastSuite, item.event.case_id);
    if (item.event.type === 'eval_check') renderCheck(item.event);
  }
}

async function runResearch() {
  stopAuto();
  mode = 'run';
  currentAction.innerHTML = '<strong>运行中</strong><span>Decompose → Compile → Dynamic DAG → Runtime</span>';
  const result = await post({action:'r3_run', goal:goalInput.value, context_preset:contextPreset.value});
  lastResult = result;
  traceDetail.textContent = pretty(result.trace || {});
  runtimeDetail.textContent = pretty({blueprint:result.blueprint, plan:result.plan, error:result.error});
  evalDetail.textContent = '{}';
  traceKpi.textContent = result.trace ? `${result.trace.span_count || 0} spans` : '—';
  evalKpi.textContent = 'R3 RUN';
  evidenceCount.textContent = String((result.evidence || []).length);
  finalResult.textContent = result.ok ? (result.final_result || 'completed') : 'FAILED';
  renderBlueprint(result.blueprint, result.plan);
  if (!result.ok) renderFailure(result); else renderCitations(result.citations || []);
  items = buildRunItems(result);
  currentIndex = items.length ? 0 : -1;
  renderCurrent();
}

async function runEvals() {
  stopAuto();
  mode = 'eval';
  const data = await post({action:'r3_evals', goal:goalInput.value, context_preset:contextPreset.value});
  lastResult = data.research_result;
  lastSuite = data.eval_suite;
  evalDetail.textContent = pretty(lastSuite || {});
  traceDetail.textContent = pretty(lastResult && lastResult.trace || {});
  runtimeDetail.textContent = pretty({blueprint:lastResult && lastResult.blueprint, plan:lastResult && lastResult.plan});
  modeLabel.textContent = 'R3 EVAL MODE';
  modeHelp.textContent = 'Decomposition contract + execution/evidence contract';
  evalKpi.textContent = `${lastSuite.passed}/${lastSuite.total}`;
  finalResult.textContent = lastSuite.passed === lastSuite.total ? 'PASS' : 'FAIL';
  items = buildEvalItems(lastSuite);
  currentIndex = items.length ? 0 : -1;
  renderEvalCases(lastSuite, items[0] && items[0].event.case_id);
  renderCurrent();
}

function step(delta) {
  if (!items.length) return;
  currentIndex = Math.max(0, Math.min(items.length - 1, currentIndex + delta));
  renderCurrent();
}

function stopAuto() {
  if (timer) clearInterval(timer);
  timer = null;
  autoButton.textContent = '自动';
}

function toggleAuto() {
  if (timer) { stopAuto(); return; }
  if (!items.length) return;
  autoButton.textContent = '停止';
  timer = setInterval(() => {
    if (currentIndex >= items.length - 1) { stopAuto(); return; }
    step(1);
  }, 900);
}

function reset() {
  stopAuto();
  mode = 'run';
  items = [];
  currentIndex = -1;
  lastResult = null;
  lastSuite = null;
  planStatus.textContent = '未运行';
  planProgress.textContent = '0';
  evidenceCount.textContent = '0';
  traceKpi.textContent = '—';
  evalKpi.textContent = 'R3';
  finalResult.textContent = '—';
  modeLabel.textContent = 'R3 RESEARCH INTELLIGENCE';
  modeHelp.textContent = 'Question → Subquestions → Query Specs → Dynamic DAG';
  currentAction.innerHTML = '<strong>等待运行</strong><span>先观察问题如何被拆成可执行查询。</span>';
  timeline.innerHTML = '<li class="empty-state">点击“运行 R3 研究”开始。</li>';
  codePanel.textContent = '等待执行事件…';
  explainBody.innerHTML = '<p>R3 重点：Decomposer 决定 WHAT，Query Compiler 决定安全的 HOW。</p>';
  traceDetail.textContent = '{}';
  evalDetail.textContent = '{}';
  runtimeDetail.textContent = '{}';
  rawEvent.textContent = '{}';
  renderBlueprint(null, null);
  renderCitations([]);
}

runButton.addEventListener('click', () => runResearch().catch((err) => { currentAction.textContent = err.message; }));
evalButton.addEventListener('click', () => runEvals().catch((err) => { currentAction.textContent = err.message; }));
prevButton.addEventListener('click', () => step(-1));
nextButton.addEventListener('click', () => step(1));
autoButton.addEventListener('click', toggleAuto);
resetButton.addEventListener('click', reset);

reset();
