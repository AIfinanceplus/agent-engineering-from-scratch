const $ = (selector) => document.querySelector(selector);

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

let displayEvents = [];
let currentIndex = -1;
let autoTimer = null;
let lastResponse = null;
let lastEvalSuite = null;
let viewMode = 'run';

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function clone(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function summaryLabel(element, text) {
  const label = element.parentElement && element.parentElement.querySelector('span');
  if (label) label.textContent = text;
}

function setMode(mode) {
  viewMode = mode;
  const isEval = mode === 'eval';

  leftKicker.textContent = isEval ? 'EVAL DATASET' : 'PLAN';
  leftTitle.textContent = isEval ? 'Eval Cases' : '研究任务';
  dagHint.style.display = isEval ? 'none' : 'flex';
  legend.style.display = isEval ? 'none' : 'flex';
  runKicker.textContent = isEval ? 'EVAL PIPELINE' : 'RUN / TRACE';
  runTitle.textContent = isEval ? '评分过程' : '执行过程';
  modeStrip.className = `mode-strip ${isEval ? 'eval-mode' : 'run-mode'}`;
  modeLabel.textContent = isEval ? 'EVAL MODE' : 'RUN MODE';
  modeHelp.textContent = isEval
    ? 'Case → Agent Run → deterministic checks → Verdict'
    : 'Planner → Scheduler → Runtime → Evidence';
  supportKicker.textContent = isEval ? 'CHECKS' : 'CITATIONS';

  if (isEval) {
    summaryLabel(planStatus, 'Suite');
    summaryLabel(planProgress, 'Cases');
    summaryLabel(evidenceCount, 'Checks');
    summaryLabel(traceKpi, 'Tools');
    summaryLabel(evalKpi, 'Pass Rate');
    summaryLabel(finalResult, 'Verdict');
  } else {
    summaryLabel(planStatus, 'Plan');
    summaryLabel(planProgress, 'Progress');
    summaryLabel(evidenceCount, 'Evidence');
    summaryLabel(traceKpi, 'Trace');
    summaryLabel(evalKpi, 'Eval');
    summaryLabel(finalResult, 'Final');
  }
}

function isMeaningful(event) {
  if ([
    'plan_created', 'scheduler_tick', 'task_started', 'task_completed',
    'task_failed', 'evidence_registered', 'synthesis_verified',
    'plan_completed', 'plan_failed',
  ].includes(event.type)) return true;

  if (event.type !== 'task_runtime_event') return false;
  const inner = event.event && event.event.type;
  return ['model_response', 'tool_validation', 'policy_decision', 'tool_attempt', 'tool_result', 'final'].includes(inner);
}

function buildRunEvents(events) {
  let currentPlan = null;
  let evidence = [];
  let citations = [];

  return events.reduce((items, event) => {
    if (event.plan) currentPlan = clone(event.plan);
    if (event.type === 'evidence_registered') evidence = [...evidence, clone(event.evidence)];
    if (event.type === 'synthesis_verified') citations = clone(event.citations || []);
    if (!isMeaningful(event)) return items;

    items.push({
      kind: 'run',
      event,
      plan: clone(currentPlan),
      evidence: clone(evidence),
      citations: clone(citations),
    });
    return items;
  }, []);
}

function buildEvalEvents(suite) {
  const items = [];
  (suite.cases || []).forEach((entry, caseIndex) => {
    (entry.process || []).forEach((event) => {
      items.push({
        kind: 'eval',
        event: clone(event),
        caseEntry: clone(entry),
        caseIndex,
      });
    });
  });
  return items;
}

function statusClass(status) {
  return ['ready', 'running', 'blocked', 'completed', 'failed'].includes(status)
    ? status
    : 'pending';
}

function compactResult(result) {
  if (result == null) return '';
  if (typeof result !== 'object') return String(result);
  if (result.kind === 'evidence') return `${result.evidence_id} · ${result.value} ${result.unit}`;
  if (result.kind === 'synthesis') return result.answer || 'synthesis';
  return pretty(result);
}

function renderRunSummary(plan, evidence) {
  if (!plan) {
    planStatus.textContent = '未运行';
    planProgress.textContent = '0 / 3';
    evidenceCount.textContent = '0';
    traceKpi.textContent = '—';
    evalKpi.textContent = '—';
    finalResult.textContent = '—';
    return;
  }

  const tasks = plan.tasks || [];
  const completed = tasks.filter((task) => task.status === 'completed').length;
  planStatus.textContent = plan.status;
  planProgress.textContent = `${completed} / ${tasks.length}`;
  evidenceCount.textContent = String((evidence || []).length);

  const trace = lastResponse && lastResponse.trace;
  if (trace) {
    const attempts = trace.metrics ? trace.metrics.tool_attempts : 0;
    traceKpi.textContent = `${trace.span_count} spans · ${attempts} tools`;
  } else {
    traceKpi.textContent = '—';
  }

  const report = lastResponse && lastResponse.eval_report;
  evalKpi.textContent = report ? (report.passed ? 'PASS' : 'FAIL') : '—';
  finalResult.textContent = plan.status === 'completed' && lastResponse
    ? (lastResponse.final_result || '—')
    : '—';
}

function renderPlan(plan, evidence) {
  renderRunSummary(plan, evidence);
  planBadge.textContent = plan ? plan.status : 'planned';
  planBadge.className = `badge ${plan && plan.status === 'completed' ? 'completed' : 'neutral'}`;

  if (!plan) {
    planList.innerHTML = '<div class="empty-state">运行后显示研究 Task。</div>';
    return;
  }

  planList.innerHTML = '';
  (plan.tasks || []).forEach((task) => {
    const card = document.createElement('article');
    card.className = `task-card ${statusClass(task.status)}`;

    const head = document.createElement('div');
    head.className = 'task-head';
    const id = document.createElement('span');
    id.className = 'task-id';
    id.textContent = task.task_id;
    const status = document.createElement('span');
    status.className = `status-chip ${statusClass(task.status)}`;
    status.textContent = String(task.status).toUpperCase();
    head.append(id, status);

    const title = document.createElement('strong');
    title.textContent = task.title;
    const deps = document.createElement('small');
    deps.textContent = task.depends_on && task.depends_on.length
      ? `depends on: ${task.depends_on.join(' + ')}`
      : 'no dependencies';
    card.append(head, title, deps);

    if (task.evidence_ids && task.evidence_ids.length) {
      const chips = document.createElement('div');
      chips.className = 'evidence-chips';
      task.evidence_ids.forEach((evidenceId) => {
        const chip = document.createElement('span');
        chip.textContent = evidenceId;
        chips.appendChild(chip);
      });
      card.appendChild(chips);
    }

    if (task.result != null) {
      const result = document.createElement('div');
      result.className = 'task-result';
      result.textContent = compactResult(task.result);
      card.appendChild(result);
    }
    planList.appendChild(card);
  });
}

function renderEvalSuite(activeCaseId = null) {
  const suite = lastEvalSuite;
  if (!suite) {
    planStatus.textContent = '未运行';
    planProgress.textContent = '0 / 0';
    evidenceCount.textContent = '0';
    traceKpi.textContent = '—';
    evalKpi.textContent = '—';
    finalResult.textContent = '—';
    planBadge.textContent = 'dataset';
    planBadge.className = 'badge neutral';
    planList.innerHTML = '<div class="empty-state">点击“运行 Evals”后显示每个 Case。</div>';
    return;
  }

  const allChecks = (suite.cases || []).flatMap((entry) => entry.report.checks || []);
  const passedChecks = allChecks.filter((check) => check.passed).length;
  const toolAttempts = (suite.cases || []).reduce(
    (total, entry) => total + Number((entry.report.trace_metrics || {}).tool_attempts || 0),
    0,
  );

  planStatus.textContent = 'eval suite';
  planProgress.textContent = `${suite.passed} / ${suite.total}`;
  evidenceCount.textContent = `${passedChecks} / ${allChecks.length}`;
  traceKpi.textContent = String(toolAttempts);
  evalKpi.textContent = `${Math.round(suite.pass_rate * 100)}%`;
  finalResult.textContent = suite.passed === suite.total ? 'PASS' : 'FAIL';
  planBadge.textContent = `${suite.passed}/${suite.total}`;
  planBadge.className = `badge ${suite.passed === suite.total ? 'completed' : 'failed'}`;

  planList.innerHTML = '';
  (suite.cases || []).forEach((entry, index) => {
    const report = entry.report || {};
    const checks = report.checks || [];
    const passed = checks.filter((check) => check.passed).length;
    const card = document.createElement('article');
    card.className = `eval-case-card ${report.passed ? 'passed' : 'failed'} ${entry.case.case_id === activeCaseId ? 'active-case' : ''}`;

    const head = document.createElement('div');
    head.className = 'task-head';
    const id = document.createElement('span');
    id.className = 'eval-case-number';
    id.textContent = `CASE ${index + 1}`;
    const verdict = document.createElement('span');
    verdict.className = `eval-verdict ${report.passed ? 'passed' : 'failed'}`;
    verdict.textContent = report.passed ? 'PASS' : 'FAIL';
    head.append(id, verdict);

    const title = document.createElement('strong');
    title.textContent = entry.case.case_id;
    const goal = document.createElement('small');
    goal.textContent = entry.case.goal;
    const progress = document.createElement('div');
    progress.className = 'eval-case-progress';
    progress.textContent = `${passed}/${checks.length} checks passed`;
    card.append(head, title, goal, progress);
    planList.appendChild(card);
  });
}

function renderCitations(citations) {
  citationList.innerHTML = '';
  if (!citations || !citations.length) {
    citationTitle.textContent = '尚未形成';
    citationList.innerHTML = '<div class="empty-state">完成后显示引用。</div>';
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

function renderEvalChecks(entry, activeCheckId = null) {
  const report = entry && entry.report ? entry.report : null;
  citationList.innerHTML = '';
  if (!report) {
    citationTitle.textContent = '等待 Case';
    citationList.innerHTML = '<div class="empty-state">选择一个 Eval Case。</div>';
    return;
  }

  const checks = report.checks || [];
  const passed = checks.filter((check) => check.passed).length;
  citationTitle.textContent = `${passed}/${checks.length} checks · ${report.passed ? 'PASS' : 'FAIL'}`;

  checks.forEach((check) => {
    const row = document.createElement('article');
    row.className = `eval-check-row ${check.passed ? 'passed' : 'failed'} ${check.check_id === activeCheckId ? 'active-check' : ''}`;
    const top = document.createElement('div');
    const mark = document.createElement('strong');
    mark.textContent = check.passed ? '✓' : '✕';
    const id = document.createElement('code');
    id.textContent = check.check_id;
    top.append(mark, id);
    const label = document.createElement('span');
    label.textContent = check.label;
    const compare = document.createElement('small');
    compare.textContent = `actual: ${String(check.actual)} · expected: ${String(check.expected)}`;
    row.append(top, label, compare);
    citationList.appendChild(row);
  });
}

function schedulerMeta(event) {
  if (event.type === 'plan_created') return {
    label: 'ResearchPlanner created DAG',
    title: 'Planner：定义研究任务与依赖',
    file: 'planner.py',
    code: 'plan = ResearchPlanner().plan(goal)\n\n# E1 + E2 -> S1',
    explain: '<p>Planner 定义 WHAT。Trace root span 从整个 plan 外层观察运行，而不是替代 Planner。</p><p><strong>下一步：</strong>Scheduler 计算 READY / BLOCKED。</p>',
  };
  if (event.type === 'scheduler_tick') return {
    label: `Scheduler · READY ${event.ready.join(', ') || '—'}`,
    title: 'Scheduler：刷新依赖状态',
    file: 'scheduler.py',
    code: `trace.increment("scheduler_ticks")\n_refresh_statuses(plan)\n\n# READY ${pretty(event.ready)}\n# BLOCKED ${pretty(event.blocked)}`,
    explain: '<p>Scheduler 的决定来自 DAG；Trace 只记录/计数，不参与业务决策。</p>',
  };
  if (event.type === 'task_started') return {
    label: `${event.task_id} started`,
    title: `Task ${event.task_id}：开始 child span`,
    file: 'scheduler.py / observability.py',
    code: `task_span = trace.start_span(\n  "task.${event.task_id}",\n  parent_span_id=root_span,\n  task_id="${event.task_id}",\n)`,
    explain: '<p>每个 DAG Task 对应一个 child span，可以比较哪个任务慢、失败或产生更多 Runtime events。</p>',
  };
  if (event.type === 'evidence_registered') return {
    label: `${event.evidence.evidence_id} provenance registered`,
    title: 'Evidence 登记，同时增加观测指标',
    file: 'scheduler.py / evidence.py',
    code: `evidence_store.add(record)\ntrace.increment("evidence_registered")\n\n${pretty(event.evidence)}`,
    explain: '<p>EvidenceStore 负责事实；Trace metric 只记录“登记了几条证据”。</p>',
  };
  if (event.type === 'synthesis_verified') return {
    label: `Synthesis verified · ${(event.evidence_ids || []).join(' + ')}`,
    title: 'Citation 验证也进入 metrics',
    file: 'scheduler.py / evals.py',
    code: 'citations = evidence_store.citations(evidence_ids)\ntrace.increment("citations_verified", len(citations))',
    explain: '<p>Trace 告诉我们验证了多少 citation；Eval 再判断 citation 是否完整、是否 grounded。</p>',
  };
  if (event.type === 'task_completed') return {
    label: `${event.task_id} completed`,
    title: `Task ${event.task_id}：结束 span`,
    file: 'scheduler.py / observability.py',
    code: 'trace.increment("tasks_completed")\ntrace.end_span(task_span, status="ok")',
    explain: '<p>Span 在任务完成时封口，duration_ms 由 TraceRecorder 计算。</p>',
  };
  if (event.type === 'plan_completed') return {
    label: 'Research plan completed',
    title: 'Root span 完成，交给 Eval scorer',
    file: 'scheduler.py / evals.py',
    code: `trace.end_span(root_span, status="ok")\nreport = score_result(eval_case, result)\n\n${pretty(event.final_artifact)}`,
    explain: '<p>Trace 到这里回答“发生了什么”；Eval 接下来按固定合同逐项检查，而不是凭感觉评价答案。</p>',
  };
  if (event.type === 'task_failed' || event.type === 'plan_failed') return {
    label: event.type,
    title: '失败进入 Trace / Eval',
    file: 'scheduler.py / evals.py',
    code: pretty(event.error),
    explain: '<p>失败不会隐藏。Span 标记 error，Eval 的 success 与 completion rate 会反映出来。</p>',
  };
  return null;
}

function runtimeMeta(wrapper) {
  const event = wrapper.event || {};
  const taskId = wrapper.task_id;
  if (event.type === 'tool_attempt') return {
    label: `${taskId} · Tool execute`,
    title: `${taskId}：Tool attempt 进入 metric`,
    file: 'agent.py / observability.py',
    code: `trace.observe_runtime_event(event)\n# tool_attempts += 1\n\n${pretty(event.arguments)}`,
    explain: '<p>Runtime 负责真实执行。TraceRecorder 旁路监听，不改变 retry / policy 行为。</p>',
  };
  if (event.type === 'tool_validation') return {
    label: `${taskId} · validate`,
    title: `${taskId}：Tool validation`,
    file: 'tools.py',
    code: pretty(event.validation),
    explain: '<p>Eval case 走的仍是同一套 Runtime，不是绕过安全层的特殊测试路径。</p>',
  };
  if (event.type === 'policy_decision') return {
    label: `${taskId} · Policy ${String(event.policy && event.policy.decision).toUpperCase()}`,
    title: `${taskId}：Policy`,
    file: 'policy.py',
    code: pretty(event.policy),
    explain: '<p>ExecutionContext 仍参与权限决策。</p>',
  };
  if (event.type === 'model_response') return {
    label: `${taskId} · Model proposal`,
    title: `${taskId}：Model proposal`,
    file: 'agent.py',
    code: pretty(event.response),
    explain: '<p>Trace 定位 Model proposal；未来可以增加 token/cost 指标。</p>',
  };
  if (event.type === 'tool_result') return {
    label: `${taskId} · Tool result`,
    title: `${taskId}：Observation`,
    file: 'agent.py',
    code: pretty(event.result),
    explain: '<p>Observation 进入 State/Evidence；Trace 只是旁路观测。</p>',
  };
  if (event.type === 'final') return {
    label: `${taskId} · Runtime final`,
    title: `${taskId}：单任务 Runtime 完成`,
    file: 'agent.py',
    code: pretty(event),
    explain: '<p>单任务结束不等于 Plan 完成；Scheduler 继续处理下一 READY Task。</p>',
  };
  return { label: `${taskId} · ${event.type}`, title: 'Runtime event', file: 'agent.py', code: pretty(event), explain: '<p>Runtime event。</p>' };
}

function runEventMeta(event) {
  if (event.type === 'task_runtime_event') return runtimeMeta(event);
  return schedulerMeta(event) || {
    label: event.type,
    title: 'Event',
    file: 'scheduler.py',
    code: pretty(event),
    explain: '<p>Event。</p>',
  };
}

function checkCode(event) {
  const snippets = {
    success: 'success = bool(result.get("ok")) and plan.get("status") == "completed"',
    task_completion_rate: 'task_completion_rate = completed / expected_task_count\npassed = task_count == expected_task_count and task_completion_rate >= 1',
    evidence_coverage: 'evidence_coverage = len(expected_evidence & collected_evidence_ids) / len(expected_evidence)',
    citation_completeness: 'citation_completeness = len(expected_citations & actual_citation_ids) / len(expected_citations)',
    citations_grounded: 'citations_grounded = cited_evidence_ids.issubset(collected_evidence_ids)',
    confidence: 'passed = artifact["confidence"] >= case.min_confidence',
  };
  return snippets[event.check_id] || 'passed = deterministic_check(actual, expected)';
}

function evalEventMeta(event) {
  if (event.type === 'eval_case_started') return {
    label: `${event.case_id} · Case loaded`,
    title: `Eval Case：先定义“什么叫做对”`,
    file: 'evals.py',
    code: `case = EvalCase(\n  case_id=${JSON.stringify(event.case_id)},\n  expected_evidence_ids=${pretty(event.expectations.expected_evidence_ids)},\n  expected_citation_ids=${pretty(event.expectations.expected_citation_ids)},\n  min_confidence=${event.expectations.min_confidence},\n  expected_task_count=${event.expectations.expected_task_count},\n)`,
    explain: '<p>Eval 在 Agent 运行前就固定期望。这样评分标准不会看完答案以后再临时改变。</p><p><strong>下一步：</strong>用这个 Goal 跑完整 Research Agent。</p>',
  };
  if (event.type === 'eval_agent_run_completed') return {
    label: `${event.case_id} · Agent run complete`,
    title: 'Agent Run 完成：冻结实际结果',
    file: 'evals.py / scheduler.py',
    code: `result = DAGScheduler().run(...)\n\n# observed\n${pretty(event.run_summary)}`,
    explain: '<p>到这里 Eval 还没有判 PASS/FAIL，只是获得实际输出：Plan、Evidence、Citations、Confidence 和 Trace metrics。</p><p><strong>下一步：</strong>逐项执行 deterministic checks。</p>',
  };
  if (event.type === 'eval_check') {
    const mark = event.passed ? 'PASS ✓' : 'FAIL ✕';
    return {
      label: `${event.passed ? '✓' : '✕'} ${event.check_id}`,
      title: `${mark} · ${event.label}`,
      file: 'evals.py',
      code: `${checkCode(event)}\n\n# actual   = ${pretty(event.actual)}\n# expected = ${pretty(event.expected)}\n# passed   = ${event.passed}`,
      explain: event.passed
        ? `<p><strong>Actual:</strong> ${String(event.actual)}<br><strong>Expected:</strong> ${String(event.expected)}</p><p>这一项通过，继续检查下一条质量合同。</p>`
        : `<p><strong>Actual:</strong> ${String(event.actual)}<br><strong>Expected:</strong> ${String(event.expected)}</p><p class="eval-failure"><strong>Failure:</strong> ${event.failure}</p>`,
    };
  }
  if (event.type === 'eval_case_verdict') return {
    label: `${event.case_id} · ${event.passed ? 'PASS' : 'FAIL'}`,
    title: `Case Verdict：${event.passed ? 'PASS' : 'FAIL'}`,
    file: 'evals.py',
    code: `failures = [check["failure"] for check in checks if not check["passed"]]\npassed = not failures\n\n# failures\n${pretty(event.failures)}`,
    explain: event.passed
      ? '<p>所有 deterministic checks 都通过，因此这个 Case 才是 PASS。</p>'
      : `<p>至少一项 check 失败，所以 Case FAIL。</p><p class="eval-failure">${event.failures.join('<br>')}</p>`,
  };
  return { label: event.type, title: 'Eval event', file: 'evals.py', code: pretty(event), explain: '<p>Eval event。</p>' };
}

function eventMeta(item) {
  return item.kind === 'eval' ? evalEventMeta(item.event) : runEventMeta(item.event);
}

function renderTimeline() {
  timeline.innerHTML = '';
  displayEvents.forEach((item, index) => {
    const meta = eventMeta(item);
    const li = document.createElement('li');
    li.className = `timeline-item ${item.kind === 'eval' ? 'eval-item' : ''}`;
    if (index < currentIndex) li.classList.add('done');
    if (index === currentIndex) li.classList.add('active');

    const marker = document.createElement('span');
    marker.className = 'timeline-marker';
    marker.textContent = item.kind === 'eval' && item.event.type === 'eval_check'
      ? (item.event.passed ? '✓' : '✕')
      : String(index + 1);
    const text = document.createElement('span');
    text.textContent = meta.label;
    li.append(marker, text);
    li.addEventListener('click', () => showStep(index));
    timeline.appendChild(li);
  });
}

function showRunStep(item, meta) {
  renderPlan(item.plan, item.evidence);
  renderCitations(item.citations);
  traceDetail.textContent = pretty(lastResponse && lastResponse.trace ? lastResponse.trace : {});
  evalDetail.textContent = pretty(lastResponse && lastResponse.eval_report ? lastResponse.eval_report : {});
  runtimeDetail.textContent = pretty({
    plan_snapshot: item.plan,
    evidence_snapshot: item.evidence,
    execution_context: lastResponse && lastResponse.execution_context,
  });
}

function showEvalStep(item, meta) {
  const event = item.event;
  const entry = item.caseEntry;
  renderEvalSuite(event.case_id);
  renderEvalChecks(entry, event.type === 'eval_check' ? event.check_id : null);
  traceDetail.textContent = pretty(entry.report ? entry.report.trace_metrics : {});
  evalDetail.textContent = pretty(entry.report || {});
  runtimeDetail.textContent = pretty({
    case: entry.case,
    current_eval_step: event,
  });
}

function showStep(index) {
  if (!displayEvents.length) return;
  currentIndex = Math.max(0, Math.min(index, displayEvents.length - 1));
  const item = displayEvents[currentIndex];
  const meta = eventMeta(item);

  if (item.kind === 'eval') showEvalStep(item, meta);
  else showRunStep(item, meta);

  eventCounter.textContent = `${currentIndex + 1} / ${displayEvents.length}`;
  currentAction.innerHTML = `<strong>${meta.title}</strong><span>${meta.label}</span>`;
  codeTitle.textContent = meta.title;
  codeFile.textContent = meta.file;
  codePanel.textContent = meta.code;
  explainBody.innerHTML = meta.explain;
  rawEvent.textContent = pretty(item.event);
  renderTimeline();

  const active = timeline.children[currentIndex];
  if (active && active.scrollIntoView) active.scrollIntoView({ block: 'nearest' });
}

function stopAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  autoButton.textContent = '自动';
}

function resetView() {
  stopAuto();
  displayEvents = [];
  currentIndex = -1;
  lastResponse = null;
  lastEvalSuite = null;
  setMode('run');
  renderPlan(null, []);
  renderCitations([]);
  eventCounter.textContent = '尚未运行';
  currentAction.innerHTML = '<strong>等待运行</strong><span>Trace 记录一次运行；Eval 对固定 Case 逐项评分。</span>';
  timeline.innerHTML = '<li class="empty-state">点击“运行研究”或“运行 Evals”。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'observability.py';
  codePanel.textContent = '等待执行事件…';
  explainBody.innerHTML = '<p>Eval Mode 会显式展示 Case → Agent Run → Checks → Verdict。</p>';
  traceDetail.textContent = '{}';
  evalDetail.textContent = '{}';
  runtimeDetail.textContent = '{}';
  rawEvent.textContent = '{}';
}

async function post(payload) {
  const response = await fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function runResearch() {
  stopAuto();
  runButton.disabled = true;
  try {
    const data = await post({
      action: 'research',
      goal: goalInput.value,
      context_preset: contextPreset.value,
    });
    setMode('run');
    lastResponse = data;
    displayEvents = buildRunEvents(data.events || []);
    currentIndex = -1;
    if (displayEvents.length) showStep(0);
    else renderPlan(data.plan || null, data.evidence || []);
  } catch (error) {
    currentAction.innerHTML = `<strong>运行失败</strong><span>${error.message}</span>`;
  } finally {
    runButton.disabled = false;
  }
}

async function runEvals() {
  stopAuto();
  evalButton.disabled = true;
  try {
    const data = await post({ action: 'evals', context_preset: contextPreset.value });
    setMode('eval');
    lastEvalSuite = data.eval_suite;
    displayEvents = buildEvalEvents(lastEvalSuite);
    currentIndex = -1;
    renderEvalSuite();
    evalDetail.textContent = pretty(lastEvalSuite);
    if (displayEvents.length) showStep(0);
  } catch (error) {
    currentAction.innerHTML = `<strong>Eval 失败</strong><span>${error.message}</span>`;
  } finally {
    evalButton.disabled = false;
  }
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
  if (autoTimer) {
    stopAuto();
    return;
  }
  if (!displayEvents.length) return;
  autoButton.textContent = '停止';
  autoTimer = setInterval(() => {
    if (currentIndex >= displayEvents.length - 1) {
      stopAuto();
      return;
    }
    showStep(currentIndex + 1);
  }, viewMode === 'eval' ? 1050 : 850);
});

runButton.addEventListener('click', runResearch);
evalButton.addEventListener('click', runEvals);
resetButton.addEventListener('click', resetView);

resetView();
