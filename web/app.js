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
const eventCounter = $('#event-counter');
const currentAction = $('#current-action');
const timeline = $('#timeline');
const codeTitle = $('#code-title');
const codeFile = $('#code-file');
const codePanel = $('#code-panel');
const explainBody = $('#explain-body');
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

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function clone(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
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

function buildDisplayEvents(events) {
  let currentPlan = null;
  let evidence = [];
  let citations = [];

  return events.reduce((items, event) => {
    if (event.plan) currentPlan = clone(event.plan);
    if (event.type === 'evidence_registered') evidence = [...evidence, clone(event.evidence)];
    if (event.type === 'synthesis_verified') citations = clone(event.citations || []);
    if (!isMeaningful(event)) return items;

    items.push({
      event,
      plan: clone(currentPlan),
      evidence: clone(evidence),
      citations: clone(citations),
    });
    return items;
  }, []);
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

function renderSummary(plan, evidence) {
  if (!plan) {
    planStatus.textContent = '未运行';
    planProgress.textContent = '0 / 3';
    evidenceCount.textContent = '0';
    traceKpi.textContent = '—';
    evalKpi.textContent = lastEvalSuite ? `${lastEvalSuite.passed}/${lastEvalSuite.total}` : '—';
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
  if (report) {
    evalKpi.textContent = report.passed ? 'PASS' : 'FAIL';
  } else if (lastEvalSuite) {
    evalKpi.textContent = `${lastEvalSuite.passed}/${lastEvalSuite.total}`;
  } else {
    evalKpi.textContent = '—';
  }

  finalResult.textContent = plan.status === 'completed' && lastResponse
    ? (lastResponse.final_result || '—')
    : '—';
}

function renderPlan(plan, evidence) {
  renderSummary(plan, evidence);

  if (!plan) {
    planBadge.textContent = 'planned';
    planBadge.className = 'badge neutral';
    planList.innerHTML = '<div class="empty-state">运行后显示任务。</div>';
    return;
  }

  planBadge.textContent = plan.status;
  planBadge.className = `badge ${plan.status === 'completed' ? 'completed' : 'neutral'}`;
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
    explain: '<p>Scheduler 的决定仍然来自 DAG；Trace 只记录/计数，不参与业务决策。</p>',
  };

  if (event.type === 'task_started') return {
    label: `${event.task_id} started`,
    title: `Task ${event.task_id}：开始 child span`,
    file: 'scheduler.py / observability.py',
    code: `task_span = trace.start_span(\n  "task.${event.task_id}",\n  parent_span_id=root_span,\n  task_id="${event.task_id}",\n)`,
    explain: '<p>每个 DAG Task 对应一个 child span。这样可以比较哪一个任务慢、失败或产生了多少 Runtime events。</p>',
  };

  if (event.type === 'evidence_registered') return {
    label: `${event.evidence.evidence_id} provenance registered`,
    title: 'Evidence 登记，同时增加观测指标',
    file: 'scheduler.py / evidence.py',
    code: `evidence_store.add(record)\ntrace.increment("evidence_registered")\n\n${pretty(event.evidence)}`,
    explain: '<p>EvidenceStore 负责事实；Trace metric 只记录“登记了几条证据”。两层职责分开。</p>',
  };

  if (event.type === 'synthesis_verified') return {
    label: `Synthesis verified · ${(event.evidence_ids || []).join(' + ')}`,
    title: 'Citation 验证也进入 metrics',
    file: 'scheduler.py / evals.py',
    code: `citations = evidence_store.citations(evidence_ids)\ntrace.increment("citations_verified", len(citations))`,
    explain: '<p>Trace 告诉我们验证了多少 citations；Eval 再判断这些 citations 是否达到预期完整性。</p>',
  };

  if (event.type === 'task_completed') return {
    label: `${event.task_id} completed`,
    title: `Task ${event.task_id}：结束 span`,
    file: 'scheduler.py / observability.py',
    code: `trace.increment("tasks_completed")\ntrace.end_span(task_span, status="ok")`,
    explain: '<p>Span 在任务完成时封口，duration_ms 从同一 TraceRecorder 的 clock 计算。</p>',
  };

  if (event.type === 'plan_completed') return {
    label: 'Research plan completed',
    title: 'Root span 完成，Eval 开始评分',
    file: 'scheduler.py / evals.py',
    code: `trace.end_span(root_span, status="ok")\nreport = score_result(eval_case, result)\n\n# final\n${pretty(event.final_artifact)}`,
    explain: '<p>Trace 到这里回答“这次发生了什么”；Eval 使用固定期望检查 success、coverage、citations、confidence。</p>',
  };

  if (event.type === 'task_failed' || event.type === 'plan_failed') return {
    label: event.type,
    title: '失败也必须进入 Trace / Eval',
    file: 'scheduler.py / evals.py',
    code: pretty(event.error),
    explain: '<p>失败不会被隐藏。Span 标记 error，Eval 的 success 与 completion rate 会下降。</p>',
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
    explain: '<p>Runtime 仍然负责真实执行。TraceRecorder 只监听事件并增加 tool_attempts，不改变 retry / policy 行为。</p>',
  };

  if (event.type === 'tool_validation') return {
    label: `${taskId} · validate`,
    title: `${taskId}：Tool validation`,
    file: 'tools.py',
    code: pretty(event.validation),
    explain: '<p>Eval 不应绕过 Runtime 安全层；即使只是 benchmark case，也必须走同一 validation。</p>',
  };

  if (event.type === 'policy_decision') return {
    label: `${taskId} · Policy ${String(event.policy && event.policy.decision).toUpperCase()}`,
    title: `${taskId}：Policy`,
    file: 'policy.py',
    code: pretty(event.policy),
    explain: '<p>ExecutionContext 仍参与权限决策。Eval 测的是完整系统，不是一个绕过 Policy 的特殊测试路径。</p>',
  };

  if (event.type === 'model_response') return {
    label: `${taskId} · Model proposal`,
    title: `${taskId}：Model proposal`,
    file: 'agent.py',
    code: pretty(event.response),
    explain: '<p>Trace 可以定位 Model proposal；后续可增加 token/cost 指标，而不改变 Model→Runtime 合同。</p>',
  };

  if (event.type === 'tool_result') return {
    label: `${taskId} · Tool result`,
    title: `${taskId}：Observation`,
    file: 'agent.py',
    code: pretty(event.result),
    explain: '<p>Observation 继续进入 State/Evidence；Trace 只是旁路观测。</p>',
  };

  if (event.type === 'final') return {
    label: `${taskId} · Runtime final`,
    title: `${taskId}：单任务 Runtime 完成`,
    file: 'agent.py',
    code: pretty(event),
    explain: '<p>单任务结束不等于 Plan 完成；Scheduler 仍负责下一个 READY Task。</p>',
  };

  return {
    label: `${taskId} · ${event.type}`,
    title: 'Runtime event',
    file: 'agent.py',
    code: pretty(event),
    explain: '<p>Runtime event。</p>',
  };
}

function eventMeta(event) {
  if (event.type === 'task_runtime_event') return runtimeMeta(event);
  return schedulerMeta(event) || {
    label: event.type,
    title: 'Event',
    file: 'scheduler.py',
    code: pretty(event),
    explain: '<p>Event。</p>',
  };
}

function renderTimeline() {
  timeline.innerHTML = '';
  displayEvents.forEach((item, index) => {
    const meta = eventMeta(item.event);
    const li = document.createElement('li');
    li.className = 'timeline-item';
    if (index < currentIndex) li.classList.add('done');
    if (index === currentIndex) li.classList.add('active');

    const marker = document.createElement('span');
    marker.className = 'timeline-marker';
    marker.textContent = String(index + 1);
    const text = document.createElement('span');
    text.textContent = meta.label;
    li.append(marker, text);
    li.addEventListener('click', () => showStep(index));
    timeline.appendChild(li);
  });
}

function showStep(index) {
  if (!displayEvents.length) return;
  currentIndex = Math.max(0, Math.min(index, displayEvents.length - 1));
  const item = displayEvents[currentIndex];
  const meta = eventMeta(item.event);

  renderPlan(item.plan, item.evidence);
  renderCitations(item.citations);
  eventCounter.textContent = `${currentIndex + 1} / ${displayEvents.length}`;
  currentAction.innerHTML = `<strong>${meta.title}</strong><span>${meta.label}</span>`;
  codeTitle.textContent = meta.title;
  codeFile.textContent = meta.file;
  codePanel.textContent = meta.code;
  explainBody.innerHTML = meta.explain;
  traceDetail.textContent = pretty(lastResponse && lastResponse.trace ? lastResponse.trace : {});
  evalDetail.textContent = pretty(lastResponse && lastResponse.eval_report ? lastResponse.eval_report : (lastEvalSuite || {}));
  runtimeDetail.textContent = pretty({
    plan_snapshot: item.plan,
    evidence_snapshot: item.evidence,
    execution_context: lastResponse && lastResponse.execution_context,
  });
  rawEvent.textContent = pretty(item.event);
  renderTimeline();
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
  renderPlan(null, []);
  renderCitations([]);
  eventCounter.textContent = '尚未运行';
  currentAction.innerHTML = '<strong>等待运行</strong><span>Trace 记录一次运行；Eval 用固定规则评分。</span>';
  timeline.innerHTML = '<li class="empty-state">点击“运行研究”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'observability.py';
  codePanel.textContent = '等待执行事件…';
  explainBody.innerHTML = '<p>这里解释当前事件如何进入 Trace / Eval。</p>';
  traceDetail.textContent = '{}';
  evalDetail.textContent = pretty(lastEvalSuite || {});
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
    lastResponse = data;
    displayEvents = buildDisplayEvents(data.events || []);
    currentIndex = -1;
    traceDetail.textContent = pretty(data.trace || {});
    evalDetail.textContent = pretty(data.eval_report || {});
    if (displayEvents.length) showStep(0);
    else renderPlan(data.plan || null, data.evidence || []);
  } catch (error) {
    currentAction.innerHTML = `<strong>运行失败</strong><span>${error.message}</span>`;
  } finally {
    runButton.disabled = false;
  }
}

async function runEvals() {
  evalButton.disabled = true;
  try {
    const data = await post({ action: 'evals', context_preset: contextPreset.value });
    lastEvalSuite = data.eval_suite;
    evalKpi.textContent = `${lastEvalSuite.passed}/${lastEvalSuite.total}`;
    evalDetail.textContent = pretty(lastEvalSuite);
    currentAction.innerHTML = `<strong>Eval suite 完成</strong><span>Pass rate ${(lastEvalSuite.pass_rate * 100).toFixed(0)}%</span>`;
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
  }, 850);
});

runButton.addEventListener('click', runResearch);
evalButton.addEventListener('click', runEvals);
resetButton.addEventListener('click', resetView);

resetView();
