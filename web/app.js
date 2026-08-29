const $ = (selector) => document.querySelector(selector);

const runButton = $('#run-btn');
const prevButton = $('#prev-btn');
const nextButton = $('#next-btn');
const autoButton = $('#auto-btn');
const resetButton = $('#reset-btn');
const goalInput = $('#goal');
const contextPreset = $('#context-preset');

const planStatus = $('#plan-status');
const planProgress = $('#plan-progress');
const evidenceCount = $('#evidence-count');
const confidence = $('#confidence');
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
const runtimeDetail = $('#runtime-detail');
const rawEvent = $('#raw-event');

let displayEvents = [];
let currentIndex = -1;
let autoTimer = null;
let lastResponse = null;

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
  let collectedEvidence = [];
  let citations = [];
  let synthesisConfidence = null;

  return events.reduce((items, event) => {
    if (event.plan) currentPlan = clone(event.plan);
    if (event.type === 'evidence_registered') {
      collectedEvidence = [...collectedEvidence, clone(event.evidence)];
    }
    if (event.type === 'synthesis_verified') {
      citations = clone(event.citations || []);
      synthesisConfidence = event.confidence;
    }
    if (!isMeaningful(event)) return items;

    items.push({
      event,
      plan: clone(currentPlan),
      evidence: clone(collectedEvidence),
      citations: clone(citations),
      confidence: synthesisConfidence,
    });
    return items;
  }, []);
}

function statusClass(status) {
  return ['ready', 'running', 'blocked', 'completed', 'failed'].includes(status) ? status : 'pending';
}

function compactResult(result) {
  if (result == null) return '';
  if (typeof result !== 'object') return String(result);
  if (result.kind === 'evidence') return `${result.evidence_id} · ${result.value} ${result.unit}`;
  if (result.kind === 'synthesis') return result.answer || 'synthesis';
  return pretty(result);
}

function renderPlan(plan, evidence, synthesisConfidence) {
  if (!plan) {
    planStatus.textContent = '未运行';
    planProgress.textContent = '0 / 3';
    evidenceCount.textContent = '0';
    confidence.textContent = '—';
    finalResult.textContent = '—';
    planBadge.textContent = 'planned';
    planBadge.className = 'badge neutral';
    planList.innerHTML = '<div class="empty-state">运行后显示 Evidence 与 Synthesis Task。</div>';
    return;
  }

  const tasks = plan.tasks || [];
  const completed = tasks.filter((task) => task.status === 'completed').length;
  planStatus.textContent = plan.status;
  planProgress.textContent = `${completed} / ${tasks.length}`;
  evidenceCount.textContent = String((evidence || []).length);
  confidence.textContent = synthesisConfidence == null ? '—' : `${Math.round(synthesisConfidence * 100)}%`;
  finalResult.textContent = plan.status === 'completed' && lastResponse ? lastResponse.final_result : '—';
  planBadge.textContent = plan.status;
  planBadge.className = `badge ${plan.status === 'completed' ? 'completed' : 'neutral'}`;

  planList.innerHTML = '';
  tasks.forEach((task) => {
    const card = document.createElement('article');
    card.className = `task-card ${statusClass(task.status)}`;

    const head = document.createElement('div');
    head.className = 'task-head';
    head.innerHTML = `<span class="task-id">${task.task_id}</span><span class="status-chip ${statusClass(task.status)}">${String(task.status).toUpperCase()}</span>`;

    const title = document.createElement('strong');
    title.textContent = task.title;
    const dependency = document.createElement('small');
    dependency.textContent = task.depends_on && task.depends_on.length
      ? `depends on: ${task.depends_on.join(' + ')}`
      : 'no dependencies';

    card.append(head, title, dependency);

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
    citationList.innerHTML = '<div class="empty-state">Synthesis 完成后显示引用来源。</div>';
    return;
  }

  citationTitle.textContent = `${citations.length} sources verified`;
  citations.forEach((item) => {
    const row = document.createElement('article');
    row.className = 'citation-row';
    const top = document.createElement('div');
    top.innerHTML = `<strong>${item.citation}</strong><span>${item.publisher}</span>`;
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
    title: 'Planner：先收集 Evidence，再允许 Synthesis',
    file: 'planner.py',
    code: 'plan = ResearchPlanner().plan(goal)\n\n# E1: collect energy evidence\n# E2: collect shelter evidence\n# S1: depends_on=["E1", "E2"]',
    explain: '<p>Planner 只定义研究任务和依赖。S1 被明确放在 E1/E2 后面，因此不能在证据还没收集时提前写结论。</p><p><strong>下一步：</strong>Scheduler 判断哪些 evidence task READY。</p>',
  };

  if (event.type === 'scheduler_tick') return {
    label: `Scheduler · READY ${event.ready.join(', ') || '—'}`,
    title: 'Scheduler：依赖决定 WHEN',
    file: 'scheduler.py',
    code: `dependencies_done = all(\n    task_map[dep].status == "completed"\n    for dep in task.depends_on\n)\n\n# READY  ${pretty(event.ready)}\n# BLOCKED ${pretty(event.blocked)}`,
    explain: `<p>READY：<strong>${event.ready.join(', ') || '无'}</strong>；BLOCKED：<strong>${event.blocked.join(', ') || '无'}</strong>。</p><p>Synthesis S1 只有在 E1/E2 都 COMPLETED 后才会 READY。</p>`,
  };

  if (event.type === 'task_started') return {
    label: `${event.task_id} started`,
    title: `Task ${event.task_id}：解析输入并交给 Runtime`,
    file: 'scheduler.py',
    code: `task.status = "running"\nresolved_arguments = _resolve_arguments(task.arguments, results)\n\n${pretty(event.arguments)}`,
    explain: '<p>上游 Task 的结果只在真正启动下游任务时解析。S1 收到的是 E1/E2 的完整 evidence object，而不是只有数字。</p>',
  };

  if (event.type === 'evidence_registered') return {
    label: `${event.evidence.evidence_id} provenance registered`,
    title: 'EvidenceStore：证据进入系统时就登记来源',
    file: 'evidence.py / scheduler.py',
    code: `record = EvidenceRecord.from_dict(result)\nevidence_store.add(record)\ntask.evidence_ids = [record.evidence_id]\n\n${pretty(event.evidence)}`,
    explain: '<p><strong>V10 核心：</strong>Citation 不是最后补的。Evidence 一进入 Runtime 就带 evidence_id、source、claim、confidence。</p><p><strong>下一步：</strong>下游 Synthesis 只能引用 EvidenceStore 已登记的 ID。</p>',
  };

  if (event.type === 'synthesis_verified') return {
    label: `Synthesis verified · ${(event.evidence_ids || []).join(' + ')}`,
    title: 'Synthesis：验证 citation IDs 都存在',
    file: 'scheduler.py / evidence.py',
    code: `citations = evidence_store.citations(evidence_ids)\n\ntask.evidence_ids = evidence_ids\ntask.citation_ids = [item["citation"] for item in citations]\n\n${pretty(event.citations)}`,
    explain: `<p>Synthesis 声称使用 ${event.evidence_ids.join(', ')}。Scheduler 会回到 EvidenceStore 验证这些 ID，而不是相信最终文本自己写的 [E1][E2]。</p><p>Confidence = <strong>${Math.round(event.confidence * 100)}%</strong>。</p>`,
  };

  if (event.type === 'task_completed') return {
    label: `${event.task_id} completed`,
    title: `Task ${event.task_id} 完成，产物写回 DAG`,
    file: 'scheduler.py',
    code: 'task.result = result\ntask.status = "completed"\nresults[task.task_id] = result',
    explain: `<p>${event.task_id} 的结构化产物已经进入 Plan State。下一次 Scheduler tick 会据此释放下游依赖。</p>`,
  };

  if (event.type === 'plan_completed') return {
    label: 'Research plan completed',
    title: 'Final：答案 + Evidence + Citations 一起返回',
    file: 'scheduler.py',
    code: `return {\n  "final_result": final_result,\n  "evidence": evidence_store.all(),\n  "citations": citations,\n}\n\n${pretty(event.final_artifact)}`,
    explain: `<p><strong>${event.final_result}</strong></p><p>最终产物不是一段孤立文本：它同时返回 evidence records、citation metadata 和 confidence。</p>`,
  };

  if (event.type === 'task_failed' || event.type === 'plan_failed') return {
    label: event.type,
    title: 'Research pipeline failed closed',
    file: 'scheduler.py',
    code: pretty(event.error),
    explain: '<p>缺证据、Runtime 失败或无法调度时，不应生成看似完整但没有 provenance 的研究结论。</p>',
  };

  return null;
}

function runtimeMeta(wrapper) {
  const event = wrapper.event || {};
  const taskId = wrapper.task_id;
  if (event.type === 'model_response') return {
    label: `${taskId} · Model proposal`,
    title: `${taskId}：Tool Call proposal`,
    file: 'agent.py',
    code: pretty(event.response),
    explain: '<p>Task 已由 Scheduler 选中，但 Tool Call 仍必须进入 Runtime 的 validation / policy / execution 边界。</p>',
  };
  if (event.type === 'tool_validation') return {
    label: `${taskId} · validate`,
    title: `${taskId}：Tool 参数验证`,
    file: 'tools.py',
    code: pretty(event.validation),
    explain: '<p>研究任务也不能绕过 Tool contract。尤其 S1 必须收到两个 object 类型的 evidence。</p>',
  };
  if (event.type === 'policy_decision') return {
    label: `${taskId} · Policy ${String(event.policy && event.policy.decision).toUpperCase()}`,
    title: `${taskId}：Policy`,
    file: 'policy.py',
    code: pretty(event.policy),
    explain: '<p>ExecutionContext 仍然存在。Task READY 不等于有权限执行；Policy 仍结合 identity + capability 做决定。</p>',
  };
  if (event.type === 'tool_attempt') return {
    label: `${taskId} · Tool execute`,
    title: `${taskId}：真实 Tool 执行`,
    file: 'agent.py / tools.py',
    code: `result = tool.function(**arguments)\n\n${pretty(event.arguments)}`,
    explain: '<p>这里才是真正的 capability execution。Evidence lookup 返回结构化 provenance；Synthesis tool 只组合它收到的 evidence。</p>',
  };
  if (event.type === 'tool_result') return {
    label: `${taskId} · Tool result`,
    title: `${taskId}：结构化 Observation`,
    file: 'agent.py',
    code: pretty(event.result),
    explain: '<p>Observation 不只是数值。V10 的研究 Observation 包含 kind、evidence_id/source 或 synthesis evidence_ids。</p>',
  };
  if (event.type === 'final') return {
    label: `${taskId} · Runtime final`,
    title: `${taskId}：单任务 Runtime 完成`,
    file: 'agent.py',
    code: pretty(event),
    explain: '<p>单 Task Runtime 完成后，Scheduler 才接管产物并登记 provenance / 更新 DAG。</p>',
  };
  return { label: `${taskId} · ${event.type}`, title: 'Runtime event', file: 'agent.py', code: pretty(event), explain: '<p>Runtime event。</p>' };
}

function eventMeta(event) {
  if (event.type === 'task_runtime_event') return runtimeMeta(event);
  return schedulerMeta(event) || { label: event.type, title: 'Event', file: 'scheduler.py', code: pretty(event), explain: '<p>Event。</p>' };
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
  renderPlan(item.plan, item.evidence, item.confidence);
  renderCitations(item.citations);
  eventCounter.textContent = `${currentIndex + 1} / ${displayEvents.length}`;
  currentAction.innerHTML = `<strong>${meta.title}</strong><span>${meta.label}</span>`;
  codeTitle.textContent = meta.title;
  codeFile.textContent = meta.file;
  codePanel.textContent = meta.code;
  explainBody.innerHTML = meta.explain;
  runtimeDetail.textContent = pretty({ evidence: item.evidence, citations: item.citations, plan: item.plan });
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
  renderPlan(null, [], null);
  renderCitations([]);
  eventCounter.textContent = '尚未运行';
  currentAction.innerHTML = '<strong>等待运行</strong><span>先收集 evidence，再允许 synthesis。</span>';
  timeline.innerHTML = '<li class="empty-state">点击“运行研究”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'planner.py';
  codePanel.textContent = '等待执行事件…';
  explainBody.innerHTML = '<p>这里解释当前代码为什么存在，以及 provenance 下一步流向哪里。</p>';
  runtimeDetail.textContent = '{}';
  rawEvent.textContent = '{}';
}

async function runResearch() {
  stopAuto();
  runButton.disabled = true;
  runButton.textContent = '运行中…';
  try {
    const response = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'research', goal: goalInput.value, context_preset: contextPreset.value }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
    lastResponse = data;
    displayEvents = buildDisplayEvents(data.events || []);
    currentIndex = displayEvents.length ? 0 : -1;
    if (currentIndex >= 0) showStep(currentIndex);
  } catch (error) {
    currentAction.innerHTML = `<strong>运行失败</strong><span>${error.message}</span>`;
  } finally {
    runButton.disabled = false;
    runButton.textContent = '运行研究';
  }
}

runButton.addEventListener('click', runResearch);
prevButton.addEventListener('click', () => { stopAuto(); if (currentIndex > 0) showStep(currentIndex - 1); });
nextButton.addEventListener('click', () => { stopAuto(); if (currentIndex < displayEvents.length - 1) showStep(currentIndex + 1); });
autoButton.addEventListener('click', () => {
  if (autoTimer) { stopAuto(); return; }
  if (!displayEvents.length) return;
  autoButton.textContent = '暂停';
  autoTimer = setInterval(() => {
    if (currentIndex >= displayEvents.length - 1) { stopAuto(); return; }
    showStep(currentIndex + 1);
  }, 700);
});
resetButton.addEventListener('click', resetView);

resetView();
