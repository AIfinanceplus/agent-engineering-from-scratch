const $ = (selector) => document.querySelector(selector);

const runButton = $('#run-btn');
const evalButton = $('#eval-btn');
const prevButton = $('#prev-btn');
const nextButton = $('#next-btn');
const autoButton = $('#auto-btn');
const resetButton = $('#reset-btn');
const goalInput = $('#goal');
const contextPreset = $('#context-preset');
const dataMode = $('#data-mode');

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

let mode = 'macro';
let displayEvents = [];
let currentIndex = -1;
let autoTimer = null;
let lastResponse = null;
let lastEvalSuite = null;

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function clone(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function post(payload) {
  return fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(async (response) => {
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  });
}

function isMacroEvent(event) {
  if ([
    'plan_created', 'scheduler_tick', 'task_started', 'task_completed',
    'task_failed', 'evidence_registered', 'synthesis_verified',
    'plan_completed', 'plan_failed',
  ].includes(event.type)) return true;
  if (event.type !== 'task_runtime_event') return false;
  const inner = event.event && event.event.type;
  return ['model_response', 'tool_validation', 'policy_decision', 'tool_attempt', 'tool_result', 'final'].includes(inner);
}

function buildMacroEvents(events) {
  let plan = null;
  let evidence = [];
  let citations = [];
  return events.reduce((items, event) => {
    if (event.plan) plan = clone(event.plan);
    if (event.type === 'evidence_registered') evidence = [...evidence, clone(event.evidence)];
    if (event.type === 'synthesis_verified') citations = clone(event.citations || []);
    if (!isMacroEvent(event)) return items;
    items.push({ event, plan: clone(plan), evidence: clone(evidence), citations: clone(citations) });
    return items;
  }, []);
}

function buildEvalEvents(suite) {
  const items = [];
  (suite.cases || []).forEach((entry) => {
    (entry.process || []).forEach((event) => items.push({ event, entry }));
  });
  return items;
}

function renderMacroPlan(plan, evidence) {
  leftKicker.textContent = 'SOURCE PLAN';
  leftTitle.textContent = 'CPI 研究任务';
  dagHint.innerHTML = '<span>H1</span><span>+</span><span>C1</span><span>→</span><span>A1</span>';
  legend.style.display = 'flex';

  if (!plan) {
    planList.innerHTML = '<div class="empty-state">运行后显示 BLS Source Tasks 与 Analysis Task。</div>';
    return;
  }

  planList.innerHTML = '';
  (plan.tasks || []).forEach((task) => {
    const card = document.createElement('article');
    card.className = `task-card ${task.status || 'pending'}`;
    const head = document.createElement('div');
    head.className = 'task-head';
    head.innerHTML = `<span class="task-id">${task.task_id}</span><span class="status-chip ${task.status}">${String(task.status).toUpperCase()}</span>`;
    const title = document.createElement('strong');
    title.textContent = task.title;
    const meta = document.createElement('small');
    if (task.tool_name === 'fetch_bls_series') {
      meta.textContent = `${task.arguments.series_id} · ${task.arguments.mode.toUpperCase()}`;
    } else {
      meta.textContent = `depends on: ${(task.depends_on || []).join(' + ') || 'none'}`;
    }
    card.append(head, title, meta);
    if (task.evidence_ids && task.evidence_ids.length) {
      const chips = document.createElement('div');
      chips.className = 'evidence-chips';
      task.evidence_ids.forEach((id) => {
        const chip = document.createElement('span');
        chip.textContent = id;
        chips.appendChild(chip);
      });
      card.appendChild(chips);
    }
    if (task.result && task.result.kind === 'synthesis') {
      const result = document.createElement('div');
      result.className = 'task-result';
      result.textContent = task.result.answer;
      card.appendChild(result);
    }
    planList.appendChild(card);
  });

  planStatus.textContent = plan.status;
  const completed = (plan.tasks || []).filter((task) => task.status === 'completed').length;
  planProgress.textContent = `${completed} / ${(plan.tasks || []).length}`;
  evidenceCount.textContent = String((evidence || []).length);
  planBadge.textContent = plan.status;
  planBadge.className = `badge ${plan.status === 'completed' ? 'completed' : 'neutral'}`;
}

function renderEvalCases(suite, activeCaseId = null) {
  leftKicker.textContent = 'EVAL DATASET';
  leftTitle.textContent = 'Eval Cases';
  dagHint.innerHTML = '<span>Case</span><span>→</span><span>Run</span><span>→</span><span>Checks</span>';
  legend.style.display = 'none';
  planList.innerHTML = '';

  (suite.cases || []).forEach((entry) => {
    const report = entry.report || {};
    const card = document.createElement('article');
    card.className = `task-card ${report.passed ? 'completed' : 'failed'}`;
    if (entry.case.case_id === activeCaseId) card.classList.add('eval-active-case');
    const head = document.createElement('div');
    head.className = 'task-head';
    const id = document.createElement('span');
    id.className = 'task-id';
    id.textContent = 'E';
    const verdict = document.createElement('span');
    verdict.className = `status-chip ${report.passed ? 'completed' : 'failed'}`;
    verdict.textContent = report.passed ? 'PASS' : 'FAIL';
    head.append(id, verdict);
    const title = document.createElement('strong');
    title.textContent = entry.case.case_id;
    const checks = report.checks || [];
    const passed = checks.filter((check) => check.passed).length;
    const meta = document.createElement('small');
    meta.textContent = `${passed}/${checks.length} deterministic checks`;
    card.append(head, title, meta);
    planList.appendChild(card);
  });

  planStatus.textContent = 'eval suite';
  planProgress.textContent = `${suite.passed} / ${suite.total}`;
  evidenceCount.textContent = `${Math.round((suite.pass_rate || 0) * 100)}%`;
  planBadge.textContent = suite.passed === suite.total ? 'PASS' : 'FAIL';
  planBadge.className = `badge ${suite.passed === suite.total ? 'completed' : 'neutral'}`;
}

function renderCitations(citations) {
  supportKicker.textContent = 'CITATIONS';
  citationList.innerHTML = '';
  if (!citations || !citations.length) {
    citationTitle.textContent = '尚未形成';
    citationList.innerHTML = '<div class="empty-state">Analysis 完成后显示来源。</div>';
    return;
  }
  citationTitle.textContent = `${citations.length} sources verified`;
  citations.forEach((item) => {
    const row = document.createElement('article');
    row.className = 'citation-row';
    const top = document.createElement('div');
    const cite = document.createElement('strong');
    cite.textContent = item.citation;
    const publisher = document.createElement('span');
    publisher.textContent = item.publisher;
    top.append(cite, publisher);
    const title = document.createElement('span');
    title.textContent = item.title;
    const uri = document.createElement('code');
    uri.textContent = item.uri;
    row.append(top, title, uri);
    citationList.appendChild(row);
  });
}

function renderCheck(check) {
  supportKicker.textContent = 'CURRENT CHECK';
  citationTitle.textContent = check.passed ? 'PASS' : 'FAIL';
  citationList.innerHTML = '';
  const row = document.createElement('article');
  row.className = `eval-check-card ${check.passed ? 'pass' : 'fail'}`;
  row.innerHTML = `<strong>${check.label}</strong><span>Actual: ${pretty(check.actual)}</span><span>Expected: ${pretty(check.expected)}</span>`;
  if (!check.passed) {
    const failure = document.createElement('span');
    failure.textContent = check.failure;
    row.appendChild(failure);
  }
  citationList.appendChild(row);
}

function macroMeta(item) {
  const event = item.event;
  if (event.type === 'plan_created') return {
    label: 'Source plan created', title: 'Planner：定义数据需求与分析依赖', file: 'planner.py',
    code: 'plan = CPIResearchPlanner().plan(goal, data_mode=data_mode)\n\n# H1: headline CPI\n# C1: core CPI\n# A1: depends_on=["H1", "C1"]',
    explain: '<p>Planner 先声明“需要哪两条 BLS series”，再声明分析依赖。A1 不允许自己重新抓数据。</p>',
  };
  if (event.type === 'scheduler_tick') return {
    label: `READY ${event.ready.join(', ') || '—'}`, title: 'Scheduler：哪些 Source / Analysis Task 现在可运行', file: 'scheduler.py',
    code: `# READY\n${pretty(event.ready)}\n\n# BLOCKED\n${pretty(event.blocked)}`,
    explain: '<p>H1/C1 没有依赖，因此先 READY；A1 要等两条 Evidence 都完成。</p>',
  };
  if (event.type === 'task_started') return {
    label: `${event.task_id} started`, title: `${event.task_id}：Task 进入既有 Runtime`, file: 'scheduler.py',
    code: `resolved_arguments = _resolve_arguments(task.arguments, results)\n\n${pretty(event.arguments)}`,
    explain: '<p>Source Task 和 Analysis Task 都没有绕过 Runtime；仍会经过 Validation、Policy、Retry、State 和 Trace。</p>',
  };
  if (event.type === 'evidence_registered') return {
    label: `${event.evidence.evidence_id} registered`, title: 'EvidenceStore：把 BLS 来源和数值绑定', file: 'macro_sources.py / evidence.py',
    code: `record = EvidenceRecord.from_dict(result)\nevidence_store.add(record)\n\n${pretty(event.evidence)}`,
    explain: '<p>Evidence ID、publisher、URI、claim 从取数时就固定下来。Analysis 后面只能引用已经登记的证据。</p>',
  };
  if (event.type === 'synthesis_verified') return {
    label: 'CPI analysis citations verified', title: 'Analysis：计算同比后回到 EvidenceStore 验证引用', file: 'macro_analysis.py / scheduler.py',
    code: `result = compare_cpi_series(headline, core)\ncitations = evidence_store.citations(result["evidence_ids"])\n\n${pretty(event.citations)}`,
    explain: '<p>A1 只使用 H1/C1 history 计算同比；最终引用必须对应已经收集的 BLS Evidence。</p>',
  };
  if (event.type === 'task_completed') return {
    label: `${event.task_id} completed`, title: `${event.task_id} 完成`, file: 'scheduler.py',
    code: 'task.result = result\ntask.status = "completed"\nresults[task.task_id] = result',
    explain: '<p>结果写回 Plan State，Scheduler 再判断下游是否可以释放。</p>',
  };
  if (event.type === 'plan_completed') return {
    label: 'CPI research completed', title: 'Final：分析 + Evidence + Citations + Trace', file: 'scheduler.py',
    code: pretty(event.final_artifact),
    explain: `<p><strong>${event.final_result}</strong></p><p>这次最终答案已经来自真实 Source Adapter 合同，而不是写死的研究结论。</p>`,
  };
  if (event.type === 'task_runtime_event') {
    const inner = event.event || {};
    if (inner.type === 'tool_attempt') return {
      label: `${event.task_id} · Tool execute`, title: `${event.task_id}：真实 capability 边界`, file: 'agent.py / tools.py',
      code: `result = tool.function(**arguments)\n\n${pretty(inner.arguments)}`,
      explain: '<p>如果 mode=live，fetch_bls_series 会从这里真正访问 BLS；ConnectionError/TimeoutError 仍交给 Runtime Retry。</p>',
    };
    if (inner.type === 'tool_result') return {
      label: `${event.task_id} · Tool result`, title: `${event.task_id}：Observation`, file: event.task_id === 'A1' ? 'macro_analysis.py' : 'macro_sources.py',
      code: pretty(inner.result),
      explain: '<p>Source Task 返回完整 history + provenance；A1 返回结构化 synthesis metrics。</p>',
    };
    if (inner.type === 'policy_decision') return {
      label: `${event.task_id} · Policy`, title: `${event.task_id}：ExecutionContext + Policy`, file: 'policy.py',
      code: pretty(inner.policy),
      explain: '<p>真实数据 Tool 也仍受原来的权限边界控制。</p>',
    };
    if (inner.type === 'tool_validation') return {
      label: `${event.task_id} · validate`, title: `${event.task_id}：Tool contract validation`, file: 'tools.py',
      code: pretty(inner.validation),
      explain: '<p>series_id、label、mode 或 evidence object 不符合 schema 时，在执行前就会失败。</p>',
    };
    if (inner.type === 'model_response') return {
      label: `${event.task_id} · proposal`, title: `${event.task_id}：Runtime 收到 Tool proposal`, file: 'agent.py', code: pretty(inner.response),
      explain: '<p>Planner 已经定义任务，但真正 Tool Call 仍进入统一 Runtime。</p>',
    };
    if (inner.type === 'final') return {
      label: `${event.task_id} · Runtime final`, title: `${event.task_id}：单 Task Runtime 完成`, file: 'agent.py', code: pretty(inner),
      explain: '<p>单 Task 完成后再返回 Scheduler，不等于整个研究计划完成。</p>',
    };
  }
  return { label: event.type, title: 'Event', file: 'scheduler.py', code: pretty(event), explain: '<p>Research event。</p>' };
}

function evalMeta(item) {
  const event = item.event;
  if (event.type === 'eval_case_started') return {
    label: `${event.case_id} · Case loaded`, title: 'EvalCase：先定义 Expected', file: 'evals.py',
    code: `EvalCase(\n  case_id=${JSON.stringify(event.case_id)},\n  ...\n)\n\n${pretty(event.expectations)}`,
    explain: '<p>评分标准在运行前定义，而不是看完答案以后再挑规则。</p>',
  };
  if (event.type === 'eval_agent_run_completed') return {
    label: `${event.case_id} · Agent run complete`, title: 'Eval：完整运行 Agent，冻结 Actual', file: 'evals.py',
    code: pretty(event.run_summary),
    explain: '<p>每个 Case 都重新运行完整 Planner → Runtime → Evidence → Citation 链，然后才开始评分。</p>',
  };
  if (event.type === 'eval_check') return {
    label: `${event.passed ? '✓' : '✕'} ${event.check_id}`, title: `Check：${event.label}`, file: 'evals.py',
    code: `# ${event.check_id}\nactual = ${pretty(event.actual)}\nexpected = ${pretty(event.expected)}\npassed = ${event.passed}`,
    explain: `<p><strong>${event.passed ? 'PASS' : 'FAIL'}</strong> · Actual 和 Expected 在这里做 deterministic comparison。</p>`,
  };
  return {
    label: `${event.case_id} · ${event.passed ? 'PASS' : 'FAIL'}`, title: 'Verdict：所有 checks 汇总', file: 'evals.py',
    code: `passed = not failures\n\n${pretty(event.failures || [])}`,
    explain: '<p>只有所有质量合同都通过，Case 才 PASS。</p>',
  };
}

function renderTimeline() {
  timeline.innerHTML = '';
  displayEvents.forEach((item, index) => {
    const meta = mode === 'eval' ? evalMeta(item) : macroMeta(item);
    const li = document.createElement('li');
    li.className = 'timeline-item';
    if (index < currentIndex) li.classList.add('done');
    if (index === currentIndex) li.classList.add('active');
    const marker = document.createElement('span');
    marker.className = 'timeline-marker';
    marker.textContent = String(index + 1);
    const label = document.createElement('span');
    label.textContent = meta.label;
    li.append(marker, label);
    li.addEventListener('click', () => showStep(index));
    timeline.appendChild(li);
  });
}

function showStep(index) {
  if (!displayEvents.length) return;
  currentIndex = Math.max(0, Math.min(index, displayEvents.length - 1));
  const item = displayEvents[currentIndex];
  const meta = mode === 'eval' ? evalMeta(item) : macroMeta(item);

  if (mode === 'eval') {
    renderEvalCases(lastEvalSuite, item.event.case_id);
    if (item.event.type === 'eval_check') renderCheck(item.event);
    else {
      supportKicker.textContent = 'EVAL';
      citationTitle.textContent = item.event.type === 'eval_case_verdict' ? (item.event.passed ? 'PASS' : 'FAIL') : item.event.case_id;
      citationList.innerHTML = `<div class="empty-state">${meta.explain.replace(/<[^>]+>/g, '')}</div>`;
    }
    traceDetail.textContent = pretty((item.entry.report || {}).trace_metrics || {});
    evalDetail.textContent = pretty(item.entry.report || {});
    runtimeDetail.textContent = pretty(item.event);
  } else {
    renderMacroPlan(item.plan, item.evidence);
    renderCitations(item.citations);
    traceDetail.textContent = pretty(lastResponse && lastResponse.trace ? lastResponse.trace : {});
    evalDetail.textContent = pretty(lastEvalSuite || {});
    runtimeDetail.textContent = pretty({
      data_mode: lastResponse && lastResponse.data_mode,
      execution_context: lastResponse && lastResponse.execution_context,
      plan_snapshot: item.plan,
      evidence_snapshot: item.evidence,
    });
  }

  eventCounter.textContent = `${currentIndex + 1} / ${displayEvents.length}`;
  currentAction.innerHTML = `<strong>${meta.title}</strong><span>${meta.label}</span>`;
  codeTitle.textContent = meta.title;
  codeFile.textContent = meta.file;
  codePanel.textContent = meta.code;
  explainBody.innerHTML = meta.explain;
  rawEvent.textContent = pretty(item.event);
  renderTimeline();
}

function renderMacroSummary(data) {
  const trace = data.trace || {};
  traceKpi.textContent = trace.span_count != null
    ? `${trace.span_count} spans · ${(trace.metrics || {}).tool_attempts || 0} tools`
    : '—';
  evalKpi.textContent = data.data_mode === 'live' ? 'LIVE BLS' : 'REPLAY';
  finalResult.textContent = data.final_result || '—';
}

function renderEvalSummary(suite) {
  traceKpi.textContent = `${(suite.cases || []).reduce((sum, item) => sum + (((item.report || {}).trace_metrics || {}).tool_attempts || 0), 0)} tools`;
  evalKpi.textContent = `${suite.passed}/${suite.total} PASS`;
  finalResult.textContent = `${Math.round((suite.pass_rate || 0) * 100)}% pass rate`;
}

function stopAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  autoButton.textContent = '自动';
}

function setMacroMode() {
  mode = 'macro';
  modeStrip.className = 'mode-strip run-mode';
  modeLabel.textContent = 'MACRO RUN';
  modeHelp.textContent = 'Source → Evidence → Analysis → Citation';
  runKicker.textContent = 'RUN / TRACE';
  runTitle.textContent = '真实研究过程';
}

function setEvalMode() {
  mode = 'eval';
  modeStrip.className = 'mode-strip eval-mode';
  modeLabel.textContent = 'EVAL MODE';
  modeHelp.textContent = 'Case → Agent Run → Checks → Verdict';
  runKicker.textContent = 'EVAL PROCESS';
  runTitle.textContent = '评分过程';
}

async function runMacro() {
  stopAuto();
  runButton.disabled = true;
  setMacroMode();
  try {
    const data = await post({
      action: 'macro',
      goal: goalInput.value,
      context_preset: contextPreset.value,
      data_mode: dataMode.value,
    });
    lastResponse = data;
    displayEvents = buildMacroEvents(data.events || []);
    currentIndex = -1;
    renderMacroPlan(data.plan, data.evidence || []);
    renderMacroSummary(data);
    if (displayEvents.length) showStep(0);
  } catch (error) {
    currentAction.innerHTML = `<strong>运行失败</strong><span>${error.message}</span>`;
  } finally {
    runButton.disabled = false;
  }
}

async function runEvals() {
  stopAuto();
  evalButton.disabled = true;
  setEvalMode();
  try {
    const data = await post({ action: 'evals', context_preset: contextPreset.value });
    lastEvalSuite = data.eval_suite;
    displayEvents = buildEvalEvents(lastEvalSuite);
    currentIndex = -1;
    renderEvalCases(lastEvalSuite);
    renderEvalSummary(lastEvalSuite);
    if (displayEvents.length) showStep(0);
  } catch (error) {
    currentAction.innerHTML = `<strong>Eval 失败</strong><span>${error.message}</span>`;
  } finally {
    evalButton.disabled = false;
  }
}

function resetView() {
  stopAuto();
  setMacroMode();
  displayEvents = [];
  currentIndex = -1;
  lastResponse = null;
  planStatus.textContent = '未运行';
  planProgress.textContent = '0 / 3';
  evidenceCount.textContent = '0';
  traceKpi.textContent = '—';
  evalKpi.textContent = '—';
  finalResult.textContent = '—';
  planBadge.textContent = 'planned';
  renderMacroPlan(null, []);
  renderCitations([]);
  eventCounter.textContent = '尚未运行';
  currentAction.innerHTML = '<strong>等待运行</strong><span>先用 Fixture Replay 理解流程，再切到 Live BLS。</span>';
  timeline.innerHTML = '<li class="empty-state">点击“运行 CPI 研究”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'macro_sources.py';
  codePanel.textContent = '等待执行事件…';
  explainBody.innerHTML = '<p>R1 学习目标：Source Adapter 如何进入既有 Agent Runtime。</p>';
  traceDetail.textContent = '{}';
  evalDetail.textContent = pretty(lastEvalSuite || {});
  runtimeDetail.textContent = '{}';
  rawEvent.textContent = '{}';
}

prevButton.addEventListener('click', () => {
  stopAuto();
  if (currentIndex > 0) showStep(currentIndex - 1);
});
nextButton.addEventListener('click', () => {
  stopAuto();
  if (currentIndex < displayEvents.length - 1) showStep(currentIndex + 1);
});
autoButton.addEventListener('click', () => {
  if (autoTimer) return stopAuto();
  if (!displayEvents.length) return;
  autoButton.textContent = '停止';
  autoTimer = setInterval(() => {
    if (currentIndex >= displayEvents.length - 1) return stopAuto();
    showStep(currentIndex + 1);
  }, 800);
});
runButton.addEventListener('click', runMacro);
evalButton.addEventListener('click', runEvals);
resetButton.addEventListener('click', resetView);

resetView();
