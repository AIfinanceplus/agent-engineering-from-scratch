const $ = (selector) => document.querySelector(selector);
const pretty = (value) => JSON.stringify(value, null, 2);
const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));

const runButton = $('#run-btn');
const evalButton = $('#eval-btn');
const prevButton = $('#prev-btn');
const nextButton = $('#next-btn');
const autoButton = $('#auto-btn');
const resetButton = $('#reset-btn');
const goalInput = $('#goal');
const domainInput = $('#domain');
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
const qualityDetail = $('#quality-detail');
const domainDetail = $('#domain-detail');
const traceDetail = $('#trace-detail');
const evalDetail = $('#eval-detail');
const runtimeDetail = $('#runtime-detail');
const rawEvent = $('#raw-event');

let stepItems = [];
let stepIndex = -1;
let autoTimer = null;
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
  return [
    'research_question_received', 'decomposition_created', 'queries_compiled',
    'domain_lens_selected', 'plan_created', 'scheduler_tick', 'task_started',
    'evidence_registered', 'synthesis_verified', 'task_completed', 'task_failed',
    'quality_assessed', 'domain_brief_created', 'plan_completed', 'plan_failed',
  ].includes(event.type) || (
    event.type === 'task_runtime_event' &&
    ['tool_validation', 'policy_decision', 'tool_attempt', 'tool_result'].includes((event.event || {}).type)
  );
}

function renderPlan(result) {
  const blueprint = result.blueprint || {};
  const plan = result.plan || {};
  const tasks = plan.tasks || [];
  const taskById = Object.fromEntries(tasks.map((item) => [item.task_id, item]));
  const subById = Object.fromEntries((blueprint.subquestions || []).map((item) => [item.subquestion_id, item]));

  leftKicker.textContent = 'R6 PLAN';
  leftTitle.textContent = 'Queries → S1 → D1';
  legend.style.display = 'flex';
  dagHint.innerHTML = `${(blueprint.queries || []).map((q) => `<span>${esc(q.query_id)}</span>`).join('<span>+</span>')}<span>→</span><span>S1</span><span>→</span><span>D1</span>`;
  planList.innerHTML = '';

  (blueprint.queries || []).forEach((query) => {
    const task = taskById[query.query_id] || {};
    const sub = subById[query.subquestion_id] || {};
    const card = document.createElement('article');
    card.className = `blueprint-card ${task.status || 'pending'}`;
    card.innerHTML = `
      <div class="blueprint-head"><strong>${esc(query.query_id)} · ${esc(query.provider)}</strong><code>${esc(query.capability)}</code></div>
      <p>${esc(sub.question)}</p>
      <small>${esc(query.tool_name)} · ${esc((query.arguments || {}).series_id || '')}</small>`;
    planList.appendChild(card);
  });

  [['S1', 'RESEARCH SYNTHESIS', 'Evidence → quality/relations → grounded conclusion'],
   ['D1', `${String(result.domain || '').toUpperCase()} DOMAIN`, 'S1 → thesis/options/scenarios/counterevidence']]
    .forEach(([taskId, title, detail]) => {
      const task = taskById[taskId] || {};
      const card = document.createElement('article');
      card.className = `blueprint-card ${task.status || 'pending'}`;
      card.innerHTML = `<div class="blueprint-head"><strong>${taskId} · ${esc(title)}</strong><code>${esc(task.tool_name || '')}</code></div><p>${esc(detail)}</p><small>depends on: ${esc((task.depends_on || []).join(' + '))}</small>`;
      planList.appendChild(card);
    });

  const completed = tasks.filter((item) => item.status === 'completed').length;
  planStatus.textContent = plan.status || (result.ok ? 'completed' : 'failed');
  planProgress.textContent = `${completed} / ${tasks.length}`;
  planBadge.textContent = plan.status || 'planned';
  planBadge.className = `badge ${plan.status === 'completed' ? 'completed' : 'neutral'}`;
}

function renderCitations(result) {
  const citations = result.citations || [];
  supportKicker.textContent = 'GROUNDED CITATIONS';
  citationTitle.textContent = `${citations.length} verified`;
  citationList.innerHTML = '';
  if (!citations.length) {
    citationList.innerHTML = '<div class="empty-state">No citations yet.</div>';
    return;
  }
  citations.forEach((item) => {
    const row = document.createElement('article');
    row.className = 'citation-row';
    row.innerHTML = `<div><strong>${esc(item.citation)}</strong><span>${esc(item.publisher)}</span></div><span>${esc(item.title)}</span><code>${esc(item.evidence_id)}</code>`;
    citationList.appendChild(row);
  });
}

function renderQuality(result) {
  const s1 = result.research_synthesis || (result.results || {}).S1 || {};
  const quality = s1.quality || {};
  const rows = quality.evidence_quality || [];
  qualityDetail.innerHTML = `<div class="citation-head"><span class="kicker">S1 · EVIDENCE QUALITY</span><strong>${esc(quality.support_label || '—')} · ${esc(quality.support_score ?? '—')}</strong></div>`;
  if (!rows.length) {
    qualityDetail.innerHTML += '<div class="empty-state">No quality assessment.</div>';
    return;
  }
  rows.forEach((row) => {
    const dims = row.dimensions || {};
    qualityDetail.innerHTML += `<article class="eval-check-card pass"><strong>${esc(row.evidence_id)} · ${esc(row.quality_label)}</strong><span>score ${esc(row.quality_score)}</span><span>authority ${esc(dims.authority)} · freshness ${esc(dims.freshness)} · completeness ${esc(dims.completeness)} · relevance ${esc(dims.relevance)}</span><span>${esc(row.direction)} · ${esc((row.freshness || {}).status)}</span></article>`;
  });
  (quality.relations || []).forEach((rel) => {
    qualityDetail.innerHTML += `<article class="eval-check-card ${rel.relation === 'CONTRADICTION' ? 'fail' : 'pass'}"><strong>${esc(rel.relation)}</strong><span>${esc((rel.evidence_ids || []).join(' ↔ '))}</span><span>${esc(rel.detail)}</span></article>`;
  });
}

function renderDomain(result) {
  const d1 = result.final_artifact || (result.results || {}).D1 || {};
  const sections = d1.sections || {};
  domainDetail.innerHTML = `<div class="citation-head"><span class="kicker">D1 · ${esc(String(d1.domain || '').toUpperCase())} BRIEF</span><strong>${esc(d1.decision_status || '—')}</strong></div>`;
  domainDetail.innerHTML += `<article class="eval-check-card pass"><strong>Executive Summary</strong><span>${esc(sections.executive_summary || d1.answer || '')}</span><span>confidence ${esc(d1.confidence)} · ${esc(d1.confidence_type)}</span></article>`;

  const preferred = d1.domain === 'investment'
    ? ['thesis', 'market_channels', 'base_case', 'upside_inflation_scenario', 'downside_inflation_scenario', 'counterevidence', 'what_would_change_the_view', 'monitoring_signals', 'limitations']
    : ['policy_problem', 'evidence_posture', 'options', 'tradeoffs', 'counterevidence', 'what_would_change_the_view', 'monitoring_signals', 'limitations'];

  preferred.forEach((key) => {
    if (!(key in sections)) return;
    const card = document.createElement('article');
    card.className = 'eval-check-card pass';
    card.innerHTML = `<strong>${esc(key)}</strong><pre><code>${esc(pretty(sections[key]))}</code></pre>`;
    domainDetail.appendChild(card);
  });
}

function renderSummary(result) {
  const trace = result.trace || {};
  const final = result.final_artifact || {};
  evidenceCount.textContent = String((result.evidence || []).length);
  traceKpi.textContent = trace.trace_id ? 'TRACE ✓' : '—';
  evalKpi.textContent = String(result.domain || 'R6').toUpperCase();
  finalResult.textContent = final.decision_status || (result.ok ? 'DONE' : 'FAILED');
  modeLabel.textContent = `R6 · ${String(result.domain || '').toUpperCase()}`;
  modeHelp.textContent = 'S1 fixes the grounded research boundary; D1 applies a domain lens without new Evidence.';
  runKicker.textContent = 'R6 PROCESS';
  runTitle.textContent = 'Evidence → S1 Research → D1 Domain Brief';
}

function eventMeta(event) {
  if (event.type === 'research_question_received') return ['Research question', 'r6_planner.py', 'Question enters R6 with an explicit domain lens.'];
  if (event.type === 'decomposition_created') return ['Research decomposition', 'r3_decomposition.py', 'The research question is decomposed before any domain framing.'];
  if (event.type === 'queries_compiled') return ['Safe query compilation', 'r3_decomposition.py', 'Provider/series/tool mapping remains Runtime-owned and allow-listed.'];
  if (event.type === 'domain_lens_selected') return ['Domain lens selected', 'r6_planner.py', 'Investment/Policy changes D1 only; it does not change source Evidence collection.'];
  if (event.type === 'plan_created') return ['Two-stage DAG created', 'r6_planner.py', 'Dynamic source tasks feed S1, then D1 consumes only S1.'];
  if (event.type === 'evidence_registered') return ['Evidence registered', 'evidence.py', 'Source output becomes grounded Evidence before synthesis.'];
  if (event.type === 'synthesis_verified') return ['Synthesis citations verified', 'scheduler.py', 'Both S1 and D1 Evidence IDs are verified against EvidenceStore.'];
  if (event.type === 'quality_assessed') return ['S1 Evidence quality', 'r5_quality.py', 'Authority/freshness/completeness/relevance and relations are assessed before domain framing.'];
  if (event.type === 'domain_brief_created') return ['D1 Domain brief', 'r6_domain.py', 'D1 inherits evidence and confidence; it adds decision structure, not new facts.'];
  if (event.type === 'task_started') return [`${event.task_id} started`, event.task_id === 'D1' ? 'r6_domain.py' : 'scheduler.py', 'Task enters the existing Runtime validation/policy/execution path.'];
  if (event.type === 'task_completed') return [`${event.task_id} completed`, event.task_id === 'D1' ? 'r6_domain.py' : 'scheduler.py', 'Task output is durably represented in the plan result.'];
  if (event.type === 'task_failed') return [`${event.task_id} failed`, 'scheduler.py', 'Failure remains attributable to a concrete task boundary.'];
  if (event.type === 'scheduler_tick') return ['Scheduler tick', 'scheduler.py', 'Scheduler decides which dependency-satisfied task runs next.'];
  if (event.type === 'plan_completed') return ['R6 completed', 'scheduler.py', 'Final D1 artifact is returned with citations to original Evidence.'];
  if (event.type === 'task_runtime_event') return [`${event.task_id} · ${(event.event || {}).type}`, 'agent.py', 'The existing Agent Runtime still owns validation, policy, retry, and execution.'];
  return [event.type, 'serve_visualizer.py', 'R6 event.'];
}

function buildSteps(result) {
  return (result.events || []).filter(meaningful);
}

function renderTimeline(events, activeIndex) {
  timeline.innerHTML = '';
  events.forEach((event, index) => {
    const [label] = eventMeta(event);
    const li = document.createElement('li');
    li.className = index === activeIndex ? 'running' : index < activeIndex ? 'completed' : '';
    li.innerHTML = `<div class="timeline-index">${index + 1}</div><div><strong>${esc(label)}</strong><span>${esc(event.task_id || event.domain || event.type)}</span></div>`;
    timeline.appendChild(li);
  });
}

function showStep(index) {
  if (!stepItems.length) return;
  stepIndex = Math.max(0, Math.min(index, stepItems.length - 1));
  const event = stepItems[stepIndex];
  const [label, file, explanation] = eventMeta(event);
  renderTimeline(stepItems, stepIndex);
  eventCounter.textContent = `${stepIndex + 1} / ${stepItems.length}`;
  currentAction.innerHTML = `<strong>${esc(label)}</strong><span>${esc(explanation)}</span>`;
  codeTitle.textContent = label;
  codeFile.textContent = file;
  codePanel.textContent = pretty(event);
  explainBody.innerHTML = `<p>${esc(explanation)}</p>`;
  rawEvent.textContent = pretty(event);
}

function renderFailure(result) {
  const error = result.error || {};
  planStatus.textContent = 'failed';
  planBadge.textContent = 'FAILED';
  finalResult.textContent = 'FAILED';
  citationTitle.textContent = error.provider || result.stage || 'ERROR';
  citationList.innerHTML = `<article class="eval-check-card fail"><strong>${esc(error.task_id || error.code || 'error')}</strong><span>${esc(error.message || pretty(error))}</span>${error.missing_env ? `<span>Missing: ${esc(error.missing_env.join(', '))}</span>` : ''}</article>`;
}

function renderRun(result) {
  lastResult = result;
  lastSuite = null;
  renderPlan(result);
  renderSummary(result);
  renderCitations(result);
  renderQuality(result);
  renderDomain(result);
  runtimeDetail.textContent = pretty({blueprint: result.blueprint, results: result.results, final_artifact: result.final_artifact});
  traceDetail.textContent = pretty(result.trace || {});
  evalDetail.textContent = '{}';
  if (!result.ok) renderFailure(result);
  stepItems = buildSteps(result);
  showStep(stepItems.length ? 0 : -1);
}

function renderEval(payload) {
  const suite = payload.eval_suite || {};
  const result = payload.research_result || {};
  lastResult = result;
  lastSuite = suite;
  renderPlan(result);
  renderSummary(result);
  renderCitations(result);
  renderQuality(result);
  renderDomain(result);
  leftKicker.textContent = 'R6 EVALS';
  leftTitle.textContent = 'Blueprint · S1 · D1 Contracts';
  legend.style.display = 'none';
  planList.innerHTML = '';
  (suite.cases || []).forEach((entry) => {
    const report = entry.report || {};
    const card = document.createElement('article');
    card.className = `task-card ${report.passed ? 'completed' : 'failed'}`;
    const checks = report.checks || [];
    card.innerHTML = `<div class="task-head"><span class="task-id">R6</span><span class="status-chip ${report.passed ? 'completed' : 'failed'}">${report.passed ? 'PASS' : 'FAIL'}</span></div><strong>${esc(report.case_id)}</strong><small>${checks.filter((item) => item.passed).length}/${checks.length} checks</small>`;
    planList.appendChild(card);
  });
  planStatus.textContent = 'r6 evals';
  planProgress.textContent = `${suite.passed || 0} / ${suite.total || 0}`;
  evidenceCount.textContent = `${Math.round((suite.pass_rate || 0) * 100)}%`;
  evalKpi.textContent = `${String(payload.domain || '').toUpperCase()} EVAL`;
  finalResult.textContent = suite.passed === suite.total ? 'PASS' : 'FAIL';
  planBadge.textContent = suite.passed === suite.total ? 'PASS' : 'FAIL';
  evalDetail.textContent = pretty(suite);
  runtimeDetail.textContent = pretty({research_result: result});
  traceDetail.textContent = pretty(result.trace || {});

  stepItems = [];
  (suite.cases || []).forEach((entry) => {
    (entry.process || []).forEach((event) => stepItems.push(event));
  });
  const evalEventMeta = (event) => {
    if (event.type === 'eval_case_started') return [`Case ${event.case_id}`, 'r6_evals.py', 'Expected contract is fixed before scoring.'];
    if (event.type === 'eval_check') return [`${event.passed ? '✓' : '✕'} ${event.label}`, 'r6_evals.py', event.passed ? 'Actual satisfies expected contract.' : event.failure];
    if (event.type === 'eval_case_verdict') return [`Verdict ${event.passed ? 'PASS' : 'FAIL'}`, 'r6_evals.py', (event.failures || []).join(' | ') || 'All checks passed.'];
    return [event.type, 'r6_evals.py', 'R6 eval event.'];
  };
  const originalMeta = eventMeta;
  if (stepItems.length) {
    stepIndex = 0;
    const renderEvalStep = (index) => {
      stepIndex = Math.max(0, Math.min(index, stepItems.length - 1));
      const event = stepItems[stepIndex];
      const [label, file, explanation] = evalEventMeta(event);
      timeline.innerHTML = '';
      stepItems.forEach((item, idx) => {
        const [itemLabel] = evalEventMeta(item);
        const li = document.createElement('li');
        li.className = idx === stepIndex ? 'running' : idx < stepIndex ? 'completed' : '';
        li.innerHTML = `<div class="timeline-index">${idx + 1}</div><div><strong>${esc(itemLabel)}</strong><span>${esc(item.case_id || item.type)}</span></div>`;
        timeline.appendChild(li);
      });
      eventCounter.textContent = `${stepIndex + 1} / ${stepItems.length}`;
      currentAction.innerHTML = `<strong>${esc(label)}</strong><span>${esc(explanation)}</span>`;
      codeTitle.textContent = label;
      codeFile.textContent = file;
      codePanel.textContent = pretty(event);
      explainBody.innerHTML = `<p>${esc(explanation)}</p>`;
      rawEvent.textContent = pretty(event);
      window.__r6EvalStep = renderEvalStep;
    };
    renderEvalStep(0);
  }
  void originalMeta;
}

async function runResearch() {
  runButton.disabled = true;
  currentAction.innerHTML = '<strong>运行 R6</strong><span>先完成 source Evidence 与 S1，再进入 D1。</span>';
  try {
    const result = await post({
      action: 'r6_run',
      goal: goalInput.value,
      domain: domainInput.value,
      context_preset: contextPreset.value,
    });
    renderRun(result);
  } catch (error) {
    currentAction.innerHTML = `<strong>R6 request failed</strong><span>${esc(error.message)}</span>`;
  } finally {
    runButton.disabled = false;
  }
}

async function runEvals() {
  evalButton.disabled = true;
  currentAction.innerHTML = '<strong>运行 R6 Evals</strong><span>检查 Blueprint、S1 研究质量、D1 domain discipline。</span>';
  try {
    const payload = await post({
      action: 'r6_evals',
      goal: goalInput.value,
      domain: domainInput.value,
      context_preset: contextPreset.value,
    });
    renderEval(payload);
  } catch (error) {
    currentAction.innerHTML = `<strong>R6 eval request failed</strong><span>${esc(error.message)}</span>`;
  } finally {
    evalButton.disabled = false;
  }
}

function stopAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  autoButton.textContent = '自动';
}

runButton.addEventListener('click', runResearch);
evalButton.addEventListener('click', runEvals);
prevButton.addEventListener('click', () => {
  stopAuto();
  if (window.__r6EvalStep && lastSuite) window.__r6EvalStep(stepIndex - 1);
  else showStep(stepIndex - 1);
});
nextButton.addEventListener('click', () => {
  stopAuto();
  if (window.__r6EvalStep && lastSuite) window.__r6EvalStep(stepIndex + 1);
  else showStep(stepIndex + 1);
});
autoButton.addEventListener('click', () => {
  if (autoTimer) { stopAuto(); return; }
  autoButton.textContent = '停止';
  autoTimer = setInterval(() => {
    if (!stepItems.length || stepIndex >= stepItems.length - 1) { stopAuto(); return; }
    if (window.__r6EvalStep && lastSuite) window.__r6EvalStep(stepIndex + 1);
    else showStep(stepIndex + 1);
  }, 900);
});
resetButton.addEventListener('click', () => {
  stopAuto();
  window.__r6EvalStep = null;
  stepItems = [];
  stepIndex = -1;
  lastResult = null;
  lastSuite = null;
  planStatus.textContent = '未运行';
  planProgress.textContent = '0';
  evidenceCount.textContent = '0';
  traceKpi.textContent = '—';
  evalKpi.textContent = 'R6';
  finalResult.textContent = '—';
  planBadge.textContent = 'planned';
  planList.innerHTML = '<div class="empty-state">运行 R6 后显示 Q → S1 → D1。</div>';
  timeline.innerHTML = '<li class="empty-state">运行研究后观察两层 synthesis。</li>';
  currentAction.innerHTML = '<strong>等待运行</strong><span>Investment / Policy 只改变 D1 lens。</span>';
  citationList.innerHTML = '<div class="empty-state">等待 citations。</div>';
  qualityDetail.innerHTML = '<div class="citation-head"><span class="kicker">S1 · EVIDENCE QUALITY</span><strong>等待研究</strong></div>';
  domainDetail.innerHTML = '<div class="citation-head"><span class="kicker">D1 · DOMAIN BRIEF</span><strong>等待研究</strong></div>';
  traceDetail.textContent = '{}';
  evalDetail.textContent = '{}';
  runtimeDetail.textContent = '{}';
  rawEvent.textContent = '{}';
});
