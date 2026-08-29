const runButton = document.querySelector('#run-btn');
const prevButton = document.querySelector('#prev-btn');
const nextButton = document.querySelector('#next-btn');
const autoButton = document.querySelector('#auto-btn');
const resetButton = document.querySelector('#reset-btn');
const goalInput = document.querySelector('#goal');
const contextPreset = document.querySelector('#context-preset');

const planStatus = document.querySelector('#plan-status');
const planProgress = document.querySelector('#plan-progress');
const readyCount = document.querySelector('#ready-count');
const blockedCount = document.querySelector('#blocked-count');
const finalResult = document.querySelector('#final-result');
const planBadge = document.querySelector('#plan-badge');
const planList = document.querySelector('#plan-list');

const eventCounter = document.querySelector('#event-counter');
const currentAction = document.querySelector('#current-action');
const timeline = document.querySelector('#timeline');
const codeTitle = document.querySelector('#code-title');
const codeFile = document.querySelector('#code-file');
const codePanel = document.querySelector('#code-panel');
const explainBody = document.querySelector('#explain-body');
const runtimeDetail = document.querySelector('#runtime-detail');
const rawEvent = document.querySelector('#raw-event');

let rawEvents = [];
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
  if (['plan_created', 'scheduler_tick', 'task_started', 'task_completed', 'task_failed', 'plan_completed', 'plan_failed'].includes(event.type)) {
    return true;
  }
  if (event.type !== 'task_runtime_event') return false;
  const innerType = event.event && event.event.type;
  return ['model_response', 'tool_validation', 'policy_decision', 'tool_attempt', 'tool_result', 'final'].includes(innerType);
}

function buildDisplayEvents(events) {
  let currentPlan = null;
  const visible = [];

  events.forEach((event) => {
    if (event.plan) currentPlan = clone(event.plan);
    if (!isMeaningful(event)) return;
    visible.push({
      event,
      plan: clone(currentPlan),
    });
  });

  return visible;
}

function taskStatusClass(status) {
  if (['ready', 'running', 'blocked', 'completed', 'failed'].includes(status)) return status;
  return 'pending';
}

function renderPlan(plan) {
  if (!plan) {
    planStatus.textContent = '未运行';
    planProgress.textContent = '0 / 3';
    readyCount.textContent = '—';
    blockedCount.textContent = '—';
    finalResult.textContent = '—';
    planBadge.textContent = 'planned';
    planBadge.className = 'badge neutral';
    planList.innerHTML = '<div class="empty-state">运行后这里会显示 DAG Task。</div>';
    return;
  }

  const tasks = plan.tasks || [];
  const completed = tasks.filter((task) => task.status === 'completed').length;
  const ready = tasks.filter((task) => task.status === 'ready').length;
  const blocked = tasks.filter((task) => task.status === 'blocked').length;

  planStatus.textContent = plan.status;
  planProgress.textContent = `${completed} / ${tasks.length}`;
  readyCount.textContent = String(ready);
  blockedCount.textContent = String(blocked);
  planBadge.textContent = plan.status;
  planBadge.className = `badge ${plan.status === 'completed' ? 'completed' : 'neutral'}`;

  if (plan.status === 'completed' && lastResponse) {
    finalResult.textContent = String(lastResponse.final_result);
  } else {
    finalResult.textContent = '—';
  }

  planList.innerHTML = '';
  tasks.forEach((task) => {
    const card = document.createElement('article');
    card.className = `task-card ${taskStatusClass(task.status)}`;

    const head = document.createElement('div');
    head.className = 'task-head';

    const id = document.createElement('span');
    id.className = 'task-id';
    id.textContent = task.task_id;

    const status = document.createElement('span');
    status.className = `status-chip ${taskStatusClass(task.status)}`;
    status.textContent = task.status.toUpperCase();

    head.appendChild(id);
    head.appendChild(status);

    const title = document.createElement('strong');
    title.textContent = task.title;

    const dependency = document.createElement('small');
    dependency.textContent = task.depends_on && task.depends_on.length
      ? `depends on: ${task.depends_on.join(' + ')}`
      : 'no dependencies';

    card.appendChild(head);
    card.appendChild(title);
    card.appendChild(dependency);

    if (task.result !== null && task.result !== undefined) {
      const result = document.createElement('div');
      result.className = 'task-result';
      result.textContent = `result: ${typeof task.result === 'object' ? pretty(task.result) : task.result}`;
      card.appendChild(result);
    }

    planList.appendChild(card);
  });
}

function schedulerMeta(event) {
  if (event.type === 'plan_created') {
    return {
      label: 'Planner created DAG',
      title: 'Planner：把 Goal 拆成 Task + Dependency',
      file: 'planner.py',
      code: `plan = DeterministicPlanner().plan(goal)\nvalidate_plan(plan)\n\n# A: no dependency\n# B: no dependency\n# C: depends_on=["A", "B"]`,
      explain: '<p>Planner 只回答“要有哪些任务、依赖是什么”。它不决定此刻执行谁，也不直接调用 Tool。</p><p><strong>下一步：</strong>Scheduler 根据依赖计算 READY / BLOCKED。</p>',
    };
  }

  if (event.type === 'scheduler_tick') {
    return {
      label: `Scheduler tick · READY ${event.ready.join(', ') || '—'}`,
      title: 'Scheduler：根据依赖刷新 READY / BLOCKED',
      file: 'scheduler.py',
      code: `dependencies_done = all(\n    task_map[dep].status == "completed"\n    for dep in task.depends_on\n)\n\ntask.status = "ready" if dependencies_done else "blocked"\n\n# READY  = ${JSON.stringify(event.ready)}\n# BLOCKED = ${JSON.stringify(event.blocked)}`,
      explain: `<p>Scheduler 不重新规划任务，只读取 DAG 当前状态。</p><p>此刻 READY：<strong>${event.ready.join(', ') || '无'}</strong>；BLOCKED：<strong>${event.blocked.join(', ') || '无'}</strong>。</p><p><strong>下一步：</strong>从 READY 集合选择一个任务交给 Runtime。</p>`,
    };
  }

  if (event.type === 'task_started') {
    return {
      label: `Task ${event.task_id} started`,
      title: `Scheduler 选择 Task ${event.task_id}`, 
      file: 'scheduler.py',
      code: `task.status = "running"\nresolved_arguments = _resolve_arguments(\n    task.arguments,\n    results,\n)\n\n# resolved arguments\n${pretty(event.arguments)}`,
      explain: `<p>Task ${event.task_id} 已经 READY，所以 Scheduler 把它切成 RUNNING。</p><p>如果参数引用上游结果，例如 C 的 <code>{from_task: "A"}</code>，这里才解析成真实的 30。</p><p><strong>下一步：</strong>交给既有 Agent Runtime 安全执行。</p>`,
    };
  }

  if (event.type === 'task_completed') {
    return {
      label: `Task ${event.task_id} completed → ${event.result}`,
      title: `Task ${event.task_id} 完成，结果写回 DAG`,
      file: 'scheduler.py',
      code: `task.result = result\ntask.status = "completed"\nresults[task.task_id] = result`,
      explain: `<p>Scheduler 只把 Runtime 已确认的结果写回 Task。</p><p><strong>结果：</strong>${event.result}</p><p><strong>下一步：</strong>重新计算整个 DAG 的 READY / BLOCKED 状态。</p>`,
    };
  }

  if (event.type === 'task_failed') {
    return {
      label: `Task ${event.task_id} failed`,
      title: `Task ${event.task_id} 失败`,
      file: 'scheduler.py',
      code: pretty(event.error),
      explain: '<p>Task Runtime 失败后，Scheduler 不应伪造结果或继续依赖它的下游任务。</p>',
    };
  }

  if (event.type === 'plan_completed') {
    return {
      label: `Plan completed → ${event.final_result}`,
      title: 'DAG 全部完成',
      file: 'scheduler.py',
      code: `plan.status = "completed"\nfinal_result = results[plan.tasks[-1].task_id]\n\n# results\n${pretty(event.results)}`,
      explain: `<p>A、B、C 都已 COMPLETED，因此 Plan 完成。</p><p><strong>最终结果：${event.final_result}</strong></p>`,
    };
  }

  if (event.type === 'plan_failed') {
    return {
      label: 'Plan failed',
      title: 'Scheduler 无法继续',
      file: 'scheduler.py',
      code: pretty(event.error),
      explain: '<p>存在未完成任务，但没有任何 READY Task，Scheduler fail closed。</p>',
    };
  }

  return null;
}

function runtimeMeta(wrapper) {
  const event = wrapper.event || {};
  const taskId = wrapper.task_id;

  if (event.type === 'model_response') {
    return {
      label: `${taskId} · Model proposal`,
      title: `Task ${taskId}：Runtime 收到 Model Tool proposal`,
      file: 'agent.py / scheduler.py',
      code: pretty(event.response),
      explain: '<p>Scheduler 已经选定任务，但真正的 Tool Call 仍以 Model proposal 形式进入 Runtime，因此后续 validation、Policy、MAX_STEPS 都不会被跳过。</p>',
    };
  }

  if (event.type === 'tool_validation') {
    return {
      label: `${taskId} · Tool validation`,
      title: `Task ${taskId}：Tool 参数验证`,
      file: 'tools.py',
      code: `validation = tool.validate(arguments)\n\n${pretty(event.validation)}`,
      explain: '<p>DAG Task READY 不代表 Tool 参数一定安全。Scheduler 管依赖，Runtime 仍独立验证执行输入。</p>',
    };
  }

  if (event.type === 'policy_decision') {
    return {
      label: `${taskId} · Policy ${String(event.policy && event.policy.decision).toUpperCase()}`,
      title: `Task ${taskId}：Policy 决定能否执行`,
      file: 'policy.py',
      code: `policy_result = policy_engine.evaluate(\n    tool, arguments, runtime_context\n)\n\n${pretty(event.policy)}`,
      explain: '<p>Planner/Scheduler 也没有执行权限。即使一个 Task 已经 READY，Policy 仍然可以 DENY。</p>',
    };
  }

  if (event.type === 'tool_attempt') {
    return {
      label: `${taskId} · Tool execute`,
      title: `Task ${taskId}：Python Tool 真正执行`,
      file: 'agent.py',
      code: `result = tool.function(**arguments)\n\n# arguments\n${pretty(event.arguments)}`,
      explain: '<p>这是实际计算/side-effect 边界。Planner 负责 WHAT tasks，Scheduler 负责 WHEN，只有 Runtime 到这里才真正执行 HOW。</p>',
    };
  }

  if (event.type === 'tool_result') {
    return {
      label: `${taskId} · Tool result = ${event.result}`,
      title: `Task ${taskId}：Tool 产生 Observation`,
      file: 'agent.py',
      code: `_emit(on_event, "tool_result", result=${pretty(event.result)})`,
      explain: `<p>Runtime 得到结果 <strong>${event.result}</strong>。随后结果进入 AgentState，Task Runtime 完成后才返回 Scheduler。</p>`,
    };
  }

  if (event.type === 'final') {
    return {
      label: `${taskId} · Runtime final`,
      title: `Task ${taskId}：单任务 Runtime 完成`,
      file: 'agent.py',
      code: `state.status = "completed"\nstate.final_answer = ${JSON.stringify(event.content)}`,
      explain: '<p>单个 Task 的 Runtime 已经完成。注意：这还不是整个 DAG 完成；Scheduler 还要把结果写回并检查下游依赖。</p>',
    };
  }

  return {
    label: `${taskId} · ${event.type}`,
    title: `Task ${taskId} Runtime`,
    file: 'agent.py',
    code: pretty(event),
    explain: '<p>Task Runtime event。</p>',
  };
}

function eventMeta(event) {
  if (event.type === 'task_runtime_event') return runtimeMeta(event);
  return schedulerMeta(event) || {
    label: event.type,
    title: 'Runtime event',
    file: 'scheduler.py',
    code: pretty(event),
    explain: '<p>事件。</p>',
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

    li.appendChild(marker);
    li.appendChild(text);
    li.addEventListener('click', () => showStep(index));
    timeline.appendChild(li);
  });
}

function showStep(index) {
  if (!displayEvents.length) return;
  currentIndex = Math.max(0, Math.min(index, displayEvents.length - 1));
  const item = displayEvents[currentIndex];
  const meta = eventMeta(item.event);

  renderPlan(item.plan);
  eventCounter.textContent = `${currentIndex + 1} / ${displayEvents.length}`;
  currentAction.innerHTML = `<strong>${meta.title}</strong><span>${meta.label}</span>`;
  codeTitle.textContent = meta.title;
  codeFile.textContent = meta.file;
  codePanel.textContent = meta.code;
  explainBody.innerHTML = meta.explain;

  const runtime = item.event.type === 'task_runtime_event'
    ? {
        task_id: item.event.task_id,
        runtime_event: item.event.event,
        task_plan_snapshot: item.plan && item.plan.tasks
          ? item.plan.tasks.find((task) => task.task_id === item.event.task_id)
          : null,
      }
    : {
        plan_snapshot: item.plan,
      };
  runtimeDetail.textContent = pretty(runtime);
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
  rawEvents = [];
  displayEvents = [];
  currentIndex = -1;
  lastResponse = null;
  renderPlan(null);
  eventCounter.textContent = '尚未运行';
  currentAction.innerHTML = '<strong>等待运行</strong><span>Scheduler 会先判断哪些 Task READY。</span>';
  timeline.innerHTML = '<li class="empty-state">点击“运行计划”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'planner.py';
  codePanel.textContent = '等待执行事件…';
  explainBody.innerHTML = '<p>每次选中一个进度事件，这里解释这段代码为什么存在，以及下一步由哪个组件负责。</p>';
  runtimeDetail.textContent = '{}';
  rawEvent.textContent = '{}';
}

async function runPlan() {
  stopAuto();
  runButton.disabled = true;
  runButton.textContent = '运行中…';

  try {
    const response = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'plan',
        goal: goalInput.value,
        context_preset: contextPreset.value,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(typeof data.error === 'string' ? data.error : pretty(data.error));
    }

    lastResponse = data;
    rawEvents = data.events || [];
    displayEvents = buildDisplayEvents(rawEvents);
    if (!displayEvents.length) throw new Error('No visible planner events were emitted.');
    showStep(0);
  } catch (error) {
    currentAction.innerHTML = `<strong>运行失败</strong><span>${error.message}</span>`;
    explainBody.innerHTML = `<p>${error.message}</p>`;
  } finally {
    runButton.disabled = false;
    runButton.textContent = '运行计划';
  }
}

runButton.addEventListener('click', runPlan);
prevButton.addEventListener('click', () => showStep(currentIndex - 1));
nextButton.addEventListener('click', () => showStep(currentIndex + 1));
resetButton.addEventListener('click', resetView);
autoButton.addEventListener('click', () => {
  if (!displayEvents.length) return;
  if (autoTimer) {
    stopAuto();
    return;
  }
  autoButton.textContent = '停止';
  autoTimer = setInterval(() => {
    if (currentIndex >= displayEvents.length - 1) {
      stopAuto();
      return;
    }
    showStep(currentIndex + 1);
  }, 700);
});

resetView();
