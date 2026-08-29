const runButton = document.querySelector('#run-btn');
const prevButton = document.querySelector('#prev-btn');
const nextButton = document.querySelector('#next-btn');
const autoButton = document.querySelector('#auto-btn');
const resetButton = document.querySelector('#reset-btn');
const promptInput = document.querySelector('#prompt');
const scenarioSelect = document.querySelector('#scenario');
const contextPresetSelect = document.querySelector('#context-preset');
const maxStepsInput = document.querySelector('#max-steps');
const timelineList = document.querySelector('#timeline-list');
const codePanel = document.querySelector('#code-panel');
const codeTitle = document.querySelector('#code-title');
const codeFile = document.querySelector('#code-file');
const explainTitle = document.querySelector('#explain-title');
const explainBody = document.querySelector('#explain-body');
const eventJson = document.querySelector('#event-json');
const stepCounter = document.querySelector('#step-counter');
const stateStatus = document.querySelector('#state-status');
const statePhase = document.querySelector('#state-phase');
const stateStep = document.querySelector('#state-step');
const stateTool = document.querySelector('#state-tool');
const stateProgressBar = document.querySelector('#state-progress-bar');
const stateLogic = document.querySelector('#state-logic');
const stateResults = document.querySelector('#state-results');
const stateStoreLabel = document.querySelector('#state-store-label');

let events = [];
let currentIndex = -1;
let autoTimer = null;

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

const phaseLogic = {
  starting: 'Runtime 正在初始化本次 Agent run。',
  received_input: 'Runtime 已接收用户目标，准备让 Model 决定下一步。',
  model_thinking: 'Runtime 正在等待 Model：继续调用 Tool，还是给出 Final Answer。',
  tool_selected: 'Model 已提出 Tool Call；Runtime 已记录 Tool 与参数，但尚未执行。',
  validating_tool: 'Runtime 正在确认 Tool 存在，而且参数满足 Tool contract。',
  checking_policy: '参数已经合法；Policy Engine 正结合 Tool risk 与 ExecutionContext 判断权限。',
  executing_tool: 'Policy 已 ALLOW；Runtime 进入真实 Python function / retry 边界。',
  observation_ready: '结果或错误已经得到并写入 observations；下一步反馈给 Model。',
  completed: 'Model 已给出 Final Answer；Agent run 正常完成。',
  stopped: 'Runtime guard 主动停止 Agent；stop_reason 记录停止原因。',
};

function latestStateAt(index) {
  for (let i = index; i >= 0; i -= 1) {
    if (events[i] && events[i].type === 'state_saved') {
      return events[i].state;
    }
  }
  return null;
}

function renderState(state, event) {
  if (!state) {
    stateStatus.textContent = '—';
    statePhase.textContent = '尚未运行';
    stateStep.textContent = '0 / 0';
    stateTool.textContent = '—';
    stateProgressBar.style.width = '0%';
    stateLogic.textContent = '等待运行…';
    stateResults.innerHTML = '<li class="empty-result">还没有结果。</li>';
    stateStoreLabel.textContent = 'InMemoryStateStore';
    return;
  }

  stateStatus.textContent = state.status;
  statePhase.textContent = state.phase;
  stateStep.textContent = `${state.step} / ${state.max_steps}`;
  stateTool.textContent = state.current_tool || '—';

  const budgetUsed = state.max_steps > 0
    ? Math.min(100, Math.round((state.step / state.max_steps) * 100))
    : 0;
  stateProgressBar.style.width = `${budgetUsed}%`;
  stateLogic.textContent = phaseLogic[state.phase] || `当前 phase: ${state.phase}`;

  if (event && event.type === 'state_saved' && event.store) {
    stateStoreLabel.textContent = event.store;
  }

  const observations = state.observations || [];
  if (observations.length === 0) {
    stateResults.innerHTML = '<li class="empty-result">还没有结果。</li>';
    return;
  }

  stateResults.innerHTML = '';
  observations.forEach((item) => {
    const li = document.createElement('li');
    const heading = document.createElement('strong');
    heading.textContent = `Step ${item.step} · ${item.tool_name}`;
    const value = document.createElement('code');
    value.textContent = typeof item.observation === 'object'
      ? pretty(item.observation)
      : String(item.observation);
    li.appendChild(heading);
    li.appendChild(value);
    stateResults.appendChild(li);
  });
}

function eventMeta(event) {
  if (event.type === 'execution_context') {
    return {
      node: 'context',
      label: 'ExecutionContext Injected',
      title: 'Runtime 注入可信执行身份',
      file: 'context.py / agent.py',
      code: `runtime_context = ExecutionContext(...)\n\n${pretty(event.context)}\n\n# source = ${event.source}`,
      explanation: '<p>ExecutionContext 回答“谁在执行”；AgentState 回答“做到哪里、已经得到什么”。</p>',
    };
  }

  if (event.type === 'state_saved') {
    const state = event.state || {};
    return {
      node: 'state',
      label: `State Saved · ${state.phase || 'unknown'}`,
      title: `StateStore 保存进度：${state.phase || 'unknown'}`,
      file: 'state.py / agent.py',
      code: `state.phase = ${JSON.stringify(state.phase)}\nstate.step = ${state.step}\nstate.current_tool = ${JSON.stringify(state.current_tool)}\nstate_store.save(state, reason=${JSON.stringify(event.reason)})\n\n# snapshot\n${pretty(state)}`,
      explanation: `<p><strong>V7 核心：</strong>Runtime 把当前进度和累计 observations 保存成 snapshot。</p><p class="note">reason = ${event.reason}</p>`,
    };
  }

  if (event.type === 'user_input') {
    return {
      node: 'user',
      label: 'User Input',
      title: '用户目标进入 Runtime',
      file: 'agent.py',
      code: '_emit(on_event, "user_input", message=user_message)',
      explanation: '<p>用户表达目标；Runtime State 已经独立存在，不依赖 Model 自己记忆进度。</p>',
    };
  }

  if (event.type === 'model_request' || event.type === 'model_response') {
    return {
      node: 'model',
      label: event.type === 'model_request' ? 'Model Request' : 'Model Response',
      title: 'Model 决定下一动作',
      file: event.type === 'model_request' ? 'agent.py' : 'model_adapters.py',
      code: event.type === 'model_request'
        ? 'response = model.start(...) / model.continue_with_tool_result(...)'
        : pretty(event.response),
      explanation: '<p>State.phase = model_thinking 时，Runtime 等 Model 决定下一动作；Model 不拥有 StateStore。</p>',
    };
  }

  if (['model_validation', 'runtime_step', 'duplicate_check'].includes(event.type)) {
    return {
      node: 'guards',
      label: event.type,
      title: 'Runtime Guards',
      file: event.type === 'model_validation' ? 'model_validation.py' : 'agent.py',
      code: pretty(event),
      explanation: '<p>Guard 失败也不会抹掉此前 State；已有 observations 仍保留。</p>',
    };
  }

  if (event.type === 'tool_lookup') {
    return {
      node: 'registry',
      label: event.found ? 'Tool Object Resolved' : 'Registry Miss',
      title: event.found ? 'Registry 找到 Capability' : 'Registry 找不到 Capability',
      file: 'tools.py',
      code: event.found
        ? `tool = resolve_tool(tool_name)\n\n${pretty(event.tool_metadata)}`
        : 'tool = None',
      explanation: '<p>State.current_tool 已记录 Model 的选择；Registry 再判断该能力是否真实存在。</p>',
    };
  }

  if (event.type === 'tool_validation') {
    return {
      node: 'toolobject',
      label: event.validation && event.validation.ok ? 'Tool.validate ✓' : 'Tool.validate ✕',
      title: 'Tool 参数验证',
      file: 'tools.py',
      code: `validation = tool.validate(arguments)\n\n${pretty(event.validation)}`,
      explanation: '<p>State.phase = validating_tool。合法才进入 Policy；错误也会成为 Observation。</p>',
    };
  }

  if (event.type === 'policy_decision') {
    const decision = event.policy ? event.policy.decision : 'unknown';
    let label = 'Policy DENY';
    if (decision === 'allow') label = 'Policy ALLOW';
    if (decision === 'require_approval') label = 'Policy REQUIRE_APPROVAL';
    return {
      node: 'policy',
      label,
      title: 'Policy = Capability + ExecutionContext',
      file: 'policy.py',
      code: `policy_result = policy_engine.evaluate(tool, arguments, runtime_context)\n\n# Context\n${pretty(event.context)}\n# Decision\n${pretty(event.policy)}`,
      explanation: decision === 'allow'
        ? '<p>Policy ALLOW，State 下一阶段切到 executing_tool。</p>'
        : '<p>Policy 阻止执行；这个结果会作为 Observation 写入 AgentState。</p>',
    };
  }

  if (event.type === 'tool_execute') {
    return {
      node: 'toolobject',
      label: 'Execution Allowed',
      title: '准备进入真实 Tool 执行',
      file: 'agent.py',
      code: 'state.phase = "executing_tool"\n_save_state(...)\nobservation = _execute_tool_with_retry(tool=tool, ...)',
      explanation: '<p>先保存 executing_tool，再进入真实执行边界，因此进度不会只存在于临时调用栈。</p>',
    };
  }

  if (event.type === 'tool_attempt') {
    return {
      node: 'tool',
      label: `Tool Attempt ${event.attempt}/${event.total_attempts}`,
      title: 'Python Function 真正执行',
      file: 'agent.py',
      code: 'result = tool.function(**arguments)',
      explanation: '<p>这里是真正计算/side effect 边界。Retry 仍处于同一个 Agent step。</p>',
    };
  }

  if (event.type === 'tool_retry') {
    return {
      node: 'toolobject',
      label: `Retry → ${event.next_attempt}`,
      title: 'Tool-owned Retry',
      file: 'agent.py / tools.py',
      code: pretty(event),
      explanation: '<p>Retry 不增加 State.step，因为 Model 没有做新的决策。</p>',
    };
  }

  if (event.type === 'tool_rejected') {
    const policyBlock = ['require_approval', 'deny'].includes(event.reason);
    return {
      node: policyBlock ? 'policy' : (event.reason === 'duplicate_tool_call' ? 'guards' : 'toolobject'),
      label: policyBlock ? 'Policy Blocked Execution' : 'Tool Rejected',
      title: policyBlock ? 'Policy 阻止执行' : 'Runtime 拒绝执行',
      file: 'agent.py',
      code: `observation = {"error": ${pretty(event.error)}}`,
      explanation: '<p>拒绝原因也是本轮获得的信息，随后会进入 State.observations。</p>',
    };
  }

  if (event.type === 'tool_result' || event.type === 'tool_error') {
    return {
      node: 'observation',
      label: event.type,
      title: 'Tool 已产生结果',
      file: 'agent.py',
      code: pretty(event),
      explanation: '<p>结果已经产生；下一次 state.record_observation(...) 才把它正式写入 AgentState。</p>',
    };
  }

  if (event.type === 'tool_observation') {
    return {
      node: 'observation',
      label: 'Observation → Model',
      title: '已记录结果，准备反馈给 Model',
      file: 'agent.py',
      code: '_emit(on_event, "tool_observation", tool_name=tool_name, observation=observation)',
      explanation: '<p>上方“已经拿到的结果”现在包含这条 Observation；它不再只是临时 Python 变量。</p>',
    };
  }

  if (event.type === 'runtime_stop') {
    return {
      node: 'guards',
      label: 'Runtime Stop',
      title: 'Runtime 安全停止',
      file: 'agent.py',
      code: pretty(event),
      explanation: '<p>停止时 State.status = stopped，并保留 stop_reason 与此前 observations。</p>',
    };
  }

  if (event.type === 'final') {
    return {
      node: 'final',
      label: 'Final',
      title: 'Agent Loop 完成',
      file: 'agent.py',
      code: `state.status = "completed"\nstate.final_answer = response["content"]\n_save_state(...)\nreturn ${JSON.stringify(event.content)}`,
      explanation: '<p>最终 State 同时保留 Final Answer 和此前累计结果。V8 再讨论跨进程恢复。</p>',
    };
  }

  return {
    node: 'guards',
    label: event.type,
    title: 'Runtime Event',
    file: 'agent.py',
    code: pretty(event),
    explanation: '<p>Runtime event。</p>',
  };
}

function renderTimeline() {
  timelineList.innerHTML = '';
  events.forEach((event, index) => {
    const meta = eventMeta(event);
    const li = document.createElement('li');
    li.textContent = `${index + 1}. ${meta.label}`;
    if (index < currentIndex) li.classList.add('done');
    if (index === currentIndex) li.classList.add('active');
    li.addEventListener('click', () => showStep(index));
    timelineList.appendChild(li);
  });
}

function highlightNode(name) {
  document.querySelectorAll('.node').forEach((node) => {
    node.classList.toggle('active', node.dataset.node === name);
  });
}

function showStep(index) {
  if (events.length === 0) return;
  currentIndex = Math.max(0, Math.min(index, events.length - 1));
  const event = events[currentIndex];
  const meta = eventMeta(event);

  highlightNode(meta.node);
  renderState(latestStateAt(currentIndex), event);
  codeTitle.textContent = meta.title;
  codeFile.textContent = meta.file;
  codePanel.textContent = meta.code;
  explainTitle.textContent = meta.title;
  explainBody.innerHTML = meta.explanation;
  eventJson.textContent = pretty(event);
  stepCounter.textContent = `Trace ${currentIndex + 1}/${events.length}`;
  renderTimeline();
}

function stopAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  autoButton.textContent = '自动播放';
}

function resetView() {
  stopAuto();
  events = [];
  currentIndex = -1;
  highlightNode('');
  renderState(null, null);
  timelineList.innerHTML = '<li class="empty">点击“运行真实 V7”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'agent.py';
  codePanel.textContent = '等待执行事件…';
  explainTitle.textContent = '代码进度与逻辑';
  explainBody.innerHTML = '<p>推荐先跑“两步任务”，按“下一步”观察 State.phase、Step 和 observations 怎样同步变化。</p>';
  eventJson.textContent = '{}';
  stepCounter.textContent = '尚未运行';
}

async function runTrace() {
  stopAuto();
  runButton.disabled = true;
  runButton.textContent = 'Runtime 执行中…';

  try {
    const response = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: promptInput.value,
        scenario: scenarioSelect.value,
        context_preset: contextPresetSelect.value,
        max_steps: Number.parseInt(maxStepsInput.value, 10),
      }),
    });
    const data = await response.json();
    events = data.events || [];
    if (events.length === 0) throw new Error(data.error || 'Runtime did not emit events.');
    showStep(0);
  } catch (error) {
    explainTitle.textContent = '运行失败';
    explainBody.innerHTML = `<p class="note">${error.message}</p>`;
  } finally {
    runButton.disabled = false;
    runButton.textContent = '运行真实 V7';
  }
}

runButton.addEventListener('click', runTrace);
prevButton.addEventListener('click', () => showStep(currentIndex - 1));
nextButton.addEventListener('click', () => showStep(currentIndex + 1));
resetButton.addEventListener('click', resetView);
autoButton.addEventListener('click', () => {
  if (events.length === 0) return;
  if (autoTimer) {
    stopAuto();
    return;
  }

  autoButton.textContent = '停止播放';
  autoTimer = setInterval(() => {
    if (currentIndex >= events.length - 1) {
      stopAuto();
      return;
    }
    showStep(currentIndex + 1);
  }, 850);
});

resetView();
