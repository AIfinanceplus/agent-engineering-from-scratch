const runButton = document.querySelector('#run-btn');
const crashButton = document.querySelector('#crash-btn');
const resumeButton = document.querySelector('#resume-btn');
const clearButton = document.querySelector('#clear-btn');
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
const checkpointStatus = document.querySelector('#checkpoint-status');
const checkpointPhase = document.querySelector('#checkpoint-phase');
const checkpointResults = document.querySelector('#checkpoint-results');
const checkpointFile = document.querySelector('#checkpoint-file');
const checkpointNote = document.querySelector('#checkpoint-note');

let events = [];
let currentIndex = -1;
let autoTimer = null;

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function basename(path) {
  if (!path) return '—';
  const parts = String(path).split('/');
  return parts[parts.length - 1] || path;
}

const phaseLogic = {
  starting: 'Runtime 正在初始化。',
  received_input: '用户目标已经进入 Runtime，准备请求 Model。',
  model_thinking: 'Runtime 正在等待 Model 决定下一动作。',
  tool_selected: 'Model 已选择 Tool；Runtime 记录了 Tool、参数与 continuation ID。',
  validating_tool: 'Runtime 正在验证 Tool 与参数。',
  checking_policy: 'Policy Engine 正结合 Capability 与 ExecutionContext 判断权限。',
  executing_tool: 'Policy 已允许，Runtime 正处于真实 Tool 执行边界。',
  observation_ready: 'Tool 结果已经记录。V8 把这里作为安全恢复边界。',
  completed: 'Agent 已完成，Final Answer 也已写入 checkpoint。',
  stopped: 'Runtime guard 主动停止，已有结果仍保留。',
};

function stateFromEvent(event) {
  if (!event) return null;
  if (event.type === 'state_saved' || event.type === 'checkpoint_loaded' || event.type === 'simulated_crash') {
    return event.state || null;
  }
  return null;
}

function latestStateAt(index) {
  for (let i = index; i >= 0; i -= 1) {
    const state = stateFromEvent(events[i]);
    if (state) return state;
  }
  return null;
}

function renderState(state) {
  if (!state) {
    stateStatus.textContent = '—';
    statePhase.textContent = '尚未运行';
    stateStep.textContent = '0 / 0';
    stateTool.textContent = '—';
    stateProgressBar.style.width = '0%';
    stateLogic.textContent = '等待运行…';
    stateResults.innerHTML = '<li class="empty-result">还没有结果。</li>';
    return;
  }

  stateStatus.textContent = state.status || '—';
  statePhase.textContent = state.phase || '—';
  stateStep.textContent = `${state.step || 0} / ${state.max_steps || 0}`;
  stateTool.textContent = state.current_tool || '—';
  stateLogic.textContent = phaseLogic[state.phase] || `当前 phase: ${state.phase}`;

  const maxSteps = state.max_steps || 0;
  const used = maxSteps > 0 ? Math.min(100, Math.round(((state.step || 0) / maxSteps) * 100)) : 0;
  stateProgressBar.style.width = `${used}%`;

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
    value.textContent = typeof item.observation === 'object' ? pretty(item.observation) : String(item.observation);
    li.appendChild(heading);
    li.appendChild(value);
    stateResults.appendChild(li);
  });
}

function renderCheckpoint(data) {
  const exists = Boolean(data && data.checkpoint_exists);
  const state = data ? data.latest_state : null;
  checkpointStatus.textContent = exists ? 'checkpoint 已存在' : '尚无 checkpoint';
  checkpointPhase.textContent = state && state.phase ? state.phase : '—';
  checkpointResults.textContent = state && state.observations ? String(state.observations.length) : '0';
  checkpointFile.textContent = data ? basename(data.checkpoint_path) : '—';

  if (!data) {
    checkpointNote.textContent = '先点击“① 运行到 Crash”。Runtime 会在第一个 Observation=30 已经写入磁盘之后模拟崩溃。';
  } else if (data.crashed) {
    checkpointNote.textContent = '模拟进程已经崩溃，但 checkpoint 仍在磁盘：phase=observation_ready，第一步结果 30 已保存。现在点击“② 从 Checkpoint 恢复”。';
  } else if (data.action === 'resume' && state && state.status === 'completed') {
    checkpointNote.textContent = '新的 Runtime 已从磁盘恢复并完成任务。恢复阶段没有重新执行 10+20；只继续执行第二步 6×7。';
  } else if (data.action === 'clear') {
    checkpointNote.textContent = 'Checkpoint 已清除。';
  } else if (exists) {
    checkpointNote.textContent = `最新 durable state: status=${state ? state.status : 'unknown'}, phase=${state ? state.phase : 'unknown'}.`;
  }
}

function eventMeta(event) {
  if (event.type === 'process_restart') {
    return {
      node: 'checkpoint', label: 'NEW PROCESS / RUNTIME', title: '旧进程已死：启动新的 Runtime', file: 'serve_visualizer.py',
      code: 'new_store = JsonCheckpointStore(...)\nnew_model = FakeModel("multi_step")\nrun_agent(..., resume=True)',
      explanation: '<p>这里故意用新的 Store 对象和新的 Model 对象模拟新进程。唯一跨进程保留下来的 Runtime 进度来自磁盘 checkpoint。</p>',
    };
  }

  if (event.type === 'execution_context') {
    return {
      node: 'context', label: 'ExecutionContext Injected', title: 'Runtime 注入可信身份', file: 'context.py / agent.py',
      code: `runtime_context = ExecutionContext(...)\n\n${pretty(event.context)}\n# ${event.source}`,
      explanation: '<p>恢复时身份重新由 Runtime 注入，而不是从 Model 输出里恢复。</p>',
    };
  }

  if (event.type === 'state_saved') {
    const state = event.state || {};
    return {
      node: event.store === 'JsonCheckpointStore' ? 'checkpoint' : 'state',
      label: `Checkpoint Saved · ${state.phase || 'unknown'}`,
      title: `保存 durable state：${state.phase || 'unknown'}`,
      file: 'checkpoint.py / agent.py',
      code: `state.phase = ${JSON.stringify(state.phase)}\nstate_store.save(state, reason=${JSON.stringify(event.reason)})\n\n${pretty(state)}`,
      explanation: `<p>这次 save 不只存在内存；JsonCheckpointStore 把 snapshot 写到磁盘。</p><p class="note">reason = ${event.reason}</p>`,
    };
  }

  if (event.type === 'checkpoint_loaded') {
    return {
      node: 'checkpoint', label: 'Checkpoint Loaded', title: '新 Runtime 从磁盘恢复 AgentState', file: 'checkpoint.py / agent.py',
      code: `state = state_store.load(runtime_context.task_id)\n\n${pretty(event.state)}`,
      explanation: '<p>旧 Python 进程已经不存在。新的 Runtime 通过 task_id 找回 step、observations、call_id、response_id 和 duplicate history。</p>',
    };
  }

  if (event.type === 'resume_boundary') {
    return {
      node: 'checkpoint', label: 'Resume Boundary', title: '跳过已经完成的 Tool', file: 'agent.py',
      code: `# saved Observation already exists\ncompleted_tool = ${JSON.stringify(event.tool_name)}\nsaved_observation = ${pretty(event.observation)}\n# DO NOT execute completed Tool again`,
      explanation: '<p><strong>这是 V8 核心：</strong>checkpoint 证明第一步结果已经记录，所以恢复后直接把保存的 Observation 交回 Model，不重算第一步。</p>',
    };
  }

  if (event.type === 'simulated_crash') {
    return {
      node: 'checkpoint', label: '💥 Simulated Crash', title: '进程在安全 checkpoint 之后死亡', file: 'agent.py',
      code: `state.phase = "observation_ready"\n_save_state(...)\nraise SimulatedCrash(...)`,
      explanation: '<p>Crash 发生在 Observation 已经 durable save 之后，因此恢复时知道第一步完成了。</p><p class="note">如果真实 side effect 已发生但 checkpoint 还没写，Checkpoint 本身不能保证 exactly-once。</p>',
    };
  }

  if (event.type === 'user_input') {
    return {
      node: 'state', label: 'User Input', title: '开始新的 Agent run', file: 'agent.py',
      code: '_emit(on_event, "user_input", message=user_message)',
      explanation: '<p>新 run 从空 State 开始；resume 则不会重新走这里。</p>',
    };
  }

  if (event.type === 'model_request' || event.type === 'model_response') {
    return {
      node: 'model', label: event.type === 'model_request' ? `Model Request · ${event.phase || ''}` : 'Model Response',
      title: event.type === 'model_request' && event.phase === 'resume' ? '用保存的 Observation 恢复 Model continuation' : 'Model 决定下一动作',
      file: event.type === 'model_request' ? 'agent.py' : 'model_adapters.py',
      code: event.type === 'model_request' ? pretty(event) : pretty(event.response),
      explanation: event.type === 'model_request' && event.phase === 'resume'
        ? '<p>Runtime 使用 checkpoint 中的 previous_response_id、call_id 和 30 继续，而不是重新执行第一步。</p>'
        : '<p>Model 负责决定 WHAT；durable progress 仍由 Runtime State/Checkpoint 管理。</p>',
    };
  }

  if (['model_validation', 'runtime_step', 'duplicate_check', 'tool_lookup', 'tool_validation', 'policy_decision', 'tool_execute', 'tool_rejected', 'runtime_stop'].includes(event.type)) {
    return {
      node: 'runtime', label: event.type, title: 'Runtime deterministic control', file: event.type === 'policy_decision' ? 'policy.py' : 'agent.py',
      code: pretty(event),
      explanation: '<p>恢复之后仍然重新经过 validation、Policy、MAX_STEPS 与 duplicate guard；Checkpoint 不绕过安全边界。</p>',
    };
  }

  if (event.type === 'tool_attempt') {
    return {
      node: 'tool', label: `Tool Attempt ${event.attempt}/${event.total_attempts}`, title: '真实 Python Tool 执行', file: 'agent.py',
      code: `result = tool.function(**arguments)\n\n# arguments\n${pretty(event.arguments)}`,
      explanation: '<p>在 Resume Trace 里，你应该只看到 6×7 的 Tool Attempt；不会再看到 10+20。</p>',
    };
  }

  if (event.type === 'tool_retry') {
    return {
      node: 'tool', label: `Retry → ${event.next_attempt}`, title: 'Tool Retry', file: 'agent.py', code: pretty(event),
      explanation: '<p>Retry 与 crash recovery 不同：Retry 是同一进程内重新尝试 Tool；Resume 是新 Runtime 从 durable state 继续。</p>',
    };
  }

  if (event.type === 'tool_result' || event.type === 'tool_error' || event.type === 'tool_observation') {
    return {
      node: 'observation', label: event.type, title: 'Observation 形成并进入 State', file: 'agent.py', code: pretty(event),
      explanation: '<p>Observation 是我们选择的 durable recovery anchor：先记录结果，再允许后续 Model continuation。</p>',
    };
  }

  if (event.type === 'final') {
    return {
      node: 'final', label: 'Final', title: 'Agent 完成', file: 'agent.py',
      code: `state.status = "completed"\nstate.final_answer = ${JSON.stringify(event.content)}\n_save_state(...)`,
      explanation: `<p><strong>最终输出：</strong>${event.content}</p><p>最终答案也进入 durable checkpoint。</p>`,
    };
  }

  return {
    node: 'runtime', label: event.type, title: 'Runtime Event', file: 'agent.py', code: pretty(event), explanation: '<p>Runtime event。</p>',
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
  renderState(latestStateAt(currentIndex));
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
  currentIndex = -1;
  highlightNode('');
  renderState(null);
  timelineList.innerHTML = events.length
    ? '<li class="empty">Trace 已保留，点击上一步/下一步或重新执行。</li>'
    : '<li class="empty">点击“① 运行到 Crash”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'agent.py';
  codePanel.textContent = '等待执行事件…';
  explainTitle.textContent = '代码进度与逻辑';
  explainBody.innerHTML = '<p>推荐：① Crash → 查看 checkpoint=observation_ready/30 → ② Resume → 确认只执行 6×7。</p>';
  eventJson.textContent = '{}';
  stepCounter.textContent = '尚未选中 Trace';
}

async function callRuntime(action) {
  stopAuto();
  [runButton, crashButton, resumeButton, clearButton].forEach((button) => { button.disabled = true; });

  try {
    const response = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        message: promptInput.value,
        scenario: scenarioSelect.value,
        context_preset: contextPresetSelect.value,
        max_steps: Number.parseInt(maxStepsInput.value, 10),
      }),
    });
    const data = await response.json();
    renderCheckpoint(data);

    if (!response.ok) {
      throw new Error(data.error || 'Runtime request failed.');
    }

    if (action === 'clear') {
      events = [];
      resetView();
      return;
    }

    if (action === 'resume' && events.length > 0) {
      events = events.concat([{ type: 'process_restart' }], data.events || []);
    } else {
      events = data.events || [];
    }

    if (events.length > 0) {
      showStep(0);
    }
  } catch (error) {
    explainTitle.textContent = '运行失败';
    explainBody.innerHTML = `<p class="note">${error.message}</p>`;
  } finally {
    [runButton, crashButton, resumeButton, clearButton].forEach((button) => { button.disabled = false; });
  }
}

runButton.addEventListener('click', () => callRuntime('run'));
crashButton.addEventListener('click', () => callRuntime('crash'));
resumeButton.addEventListener('click', () => callRuntime('resume'));
clearButton.addEventListener('click', () => callRuntime('clear'));
prevButton.addEventListener('click', () => showStep(currentIndex - 1));
nextButton.addEventListener('click', () => showStep(currentIndex + 1));
resetButton.addEventListener('click', resetView);
autoButton.addEventListener('click', () => {
  if (events.length === 0) return;
  if (autoTimer) {
    stopAuto();
    return;
  }
  if (currentIndex < 0) showStep(0);
  autoButton.textContent = '停止播放';
  autoTimer = setInterval(() => {
    if (currentIndex >= events.length - 1) {
      stopAuto();
      return;
    }
    showStep(currentIndex + 1);
  }, 850);
});

stateStoreLabel.textContent = 'JsonCheckpointStore';
renderCheckpoint(null);
resetView();
