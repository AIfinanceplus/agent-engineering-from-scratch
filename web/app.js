const runButton = document.querySelector('#run-btn');
const prevButton = document.querySelector('#prev-btn');
const nextButton = document.querySelector('#next-btn');
const autoButton = document.querySelector('#auto-btn');
const resetButton = document.querySelector('#reset-btn');
const promptInput = document.querySelector('#prompt');
const scenarioSelect = document.querySelector('#scenario');
const maxStepsInput = document.querySelector('#max-steps');
const maxRetriesInput = document.querySelector('#max-retries');
const timelineList = document.querySelector('#timeline-list');
const codePanel = document.querySelector('#code-panel');
const codeTitle = document.querySelector('#code-title');
const codeFile = document.querySelector('#code-file');
const explainTitle = document.querySelector('#explain-title');
const explainBody = document.querySelector('#explain-body');
const eventJson = document.querySelector('#event-json');
const stepCounter = document.querySelector('#step-counter');

let events = [];
let currentIndex = -1;
let autoTimer = null;

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function eventMeta(event) {
  if (event.type === 'user_input') {
    return {
      node: 'user', label: 'User Input', title: '用户目标进入 Runtime', file: 'agent.py',
      code: `_emit(on_event, "user_input", message=user_message)`,
      explanation: `<p>Trace 从用户目标开始。输入文字本身没有执行权限。</p>`,
    };
  }

  if (event.type === 'model_request') {
    return {
      node: 'model',
      label: event.phase === 'start' ? 'Model Request' : 'Model Continue',
      title: event.phase === 'start' ? 'Runtime 请求 Model 决定下一步' : 'Observation 回到 Model',
      file: 'agent.py',
      code: event.phase === 'start'
        ? `response = model.start(user_message)`
        : `response = model.continue_with_tool_result(..., result=observation)`,
      explanation: `<p>Model 负责提出动作；Runtime 负责验证、执行和约束。</p>`,
    };
  }

  if (event.type === 'model_response') {
    return {
      node: 'model', label: `Model Response · ${event.response?.type ?? 'unknown'}`,
      title: 'Model 返回 proposal', file: 'model_adapters.py',
      code: `response = ${pretty(event.response)}`,
      explanation: `<p>这仍然只是 proposal。下一步必须通过 Model Validator。</p>`,
    };
  }

  if (event.type === 'model_validation') {
    const ok = event.validation?.ok === true;
    return {
      node: 'modelguard', label: ok ? 'Model Validation Passed' : 'Model Validation Failed',
      title: ok ? 'Model Response contract 合法' : 'Model Response contract 被拒绝',
      file: 'model_validation.py',
      code: `response_validation = validate_model_response(response)\n\n# ${pretty(event.validation)}`,
      explanation: ok
        ? `<p>Runtime 已确认 response 是可安全解释的结构。</p>`
        : `<p>协议错误发生在 Tool 层之前，因此直接 fail safely。</p>`,
    };
  }

  if (event.type === 'runtime_step') {
    return {
      node: 'budget', label: `Runtime Step ${event.step}/${event.max_steps}`,
      title: '消耗一个 Model Tool Call budget', file: 'agent.py',
      code: `tool_steps += 1\n# step = ${event.step}, max_steps = ${event.max_steps}`,
      explanation: `<p>一次 Model 提议的 Tool Call 占 1 个 step。Runtime 内部 retry 不额外占 step。</p>`,
    };
  }

  if (event.type === 'duplicate_check') {
    return {
      node: 'duplicate',
      label: event.duplicate ? 'Duplicate Detected' : 'No Duplicate',
      title: event.duplicate ? '发现完全相同的 Tool Call' : '这是新的 Model 动作',
      file: 'agent.py',
      code: `call_key = _tool_call_key(tool_name, arguments)\nis_duplicate = call_key in seen_calls\n\n# duplicate = ${event.duplicate}\n# key = ${event.call_key}`,
      explanation: event.duplicate
        ? `<p>Model 已经看到过这个动作的 Observation，却又提出完全相同的 name + arguments。</p><p class="note">这不是 retry，而是 Model-level loop。</p>`
        : `<p>这个 Model 动作之前没有出现过，因此继续进入 Tool Registry。</p>`,
    };
  }

  if (event.type === 'tool_lookup') {
    return {
      node: 'registry', label: event.found ? 'Registry Hit' : 'Registry Miss',
      title: event.found ? 'Registry 找到真实能力' : 'Registry 找不到 Tool', file: 'tools.py',
      code: `tool = resolve_tool(tool_name)\n# found = ${event.found}`,
      explanation: `<p>只有 Registry 显式注册的 callable 才能进入执行路径。</p>`,
    };
  }

  if (event.type === 'tool_validation') {
    const ok = event.validation?.ok === true;
    return {
      node: 'validator', label: ok ? 'Tool Validation Passed' : 'Tool Validation Failed',
      title: ok ? 'Tool 参数合法' : 'Tool 参数被拒绝', file: 'tools.py',
      code: `validation = validate_tool_arguments(tool_name, arguments)\n\n# ${pretty(event.validation)}`,
      explanation: `<p>Model contract 合法不代表 Tool 参数一定合法，所以需要第二层验证。</p>`,
    };
  }

  if (event.type === 'tool_execute') {
    return {
      node: 'retry', label: 'Enter Retry Executor', title: 'Runtime 准备执行 Tool', file: 'agent.py',
      code: `observation = _execute_tool_with_retry(\n    tool_name=tool_name,\n    tool=tool,\n    arguments=arguments,\n    max_retries=${event.max_retries},\n)`,
      explanation: `<p>从这里开始，Runtime 可以在不重新咨询 Model 的情况下处理 transient failure。</p>`,
    };
  }

  if (event.type === 'tool_attempt') {
    return {
      node: 'tool', label: `Tool Attempt ${event.attempt}/${event.total_attempts}`,
      title: 'Python Tool 真正执行一次', file: 'agent.py',
      code: `result = tool(**arguments)\n# attempt ${event.attempt} of ${event.total_attempts}`,
      explanation: `<p>这是一次真实 Python 调用。初次执行和 retry attempt 都会经过这里。</p>`,
    };
  }

  if (event.type === 'tool_retry') {
    return {
      node: 'retry', label: `Retry → Attempt ${event.next_attempt}`,
      title: 'Transient failure 触发 Runtime Retry', file: 'agent.py',
      code: `except RETRYABLE_ERRORS as exc:\n    if attempt < total_attempts:\n        continue\n\n# ${event.error_type}: ${event.error}`,
      explanation: `<p><strong>${event.error_type}</strong> 被定义为 retryable。Runtime 重复同一个动作，不重新问 Model。</p><p class="note">Retry = execution recovery，不是 replanning。</p>`,
    };
  }

  if (event.type === 'tool_rejected') {
    const duplicate = event.reason === 'duplicate_tool_call';
    return {
      node: duplicate ? 'duplicate' : 'validator', label: duplicate ? 'Duplicate Blocked' : 'Tool Rejected',
      title: duplicate ? '第二次真实执行被阻止' : 'Runtime 拒绝执行 Tool', file: 'agent.py',
      code: `observation = {"error": ${pretty(event.error)}}\n# 不执行新的 Python Tool`,
      explanation: duplicate
        ? `<p>第一次调用的结果已经存在，第二次完全相同的 Model proposal 不再真实执行，而是返回 structured Observation。</p>`
        : `<p>确定性验证失败，因此 Tool 不执行。</p>`,
    };
  }

  if (event.type === 'tool_result') {
    return {
      node: 'observation', label: 'Tool Result', title: 'Tool 最终成功', file: 'agent.py',
      code: `return result\n# result = ${pretty(event.result)}\n# total attempts used = ${event.attempts}`,
      explanation: `<p>最终结果是 <code>${event.result}</code>，共执行 ${event.attempts} 次。只有一个 Model step。</p>`,
    };
  }

  if (event.type === 'tool_error') {
    return {
      node: 'observation', label: 'Tool Error', title: 'Tool failure 被规范化', file: 'agent.py',
      code: `return {"error": ${pretty(event.error)}}`,
      explanation: event.retryable
        ? `<p>Retry 次数已经耗尽，failure 变成 Observation。</p>`
        : `<p>这是 non-retryable error，因此 Runtime 不重复执行同一动作。</p>`,
    };
  }

  if (event.type === 'tool_observation') {
    return {
      node: 'observation', label: 'Observation', title: '执行结果回到 Model', file: 'agent.py',
      code: `observation = ${pretty(event.observation)}`,
      explanation: `<p>无论成功、验证拒绝、duplicate，最终都统一形成 Observation。</p>`,
    };
  }

  if (event.type === 'runtime_stop') {
    const byBudget = event.reason === 'max_steps';
    return {
      node: byBudget ? 'budget' : 'modelguard',
      label: byBudget ? 'MAX_STEPS Stop' : 'Runtime Stop',
      title: byBudget ? 'MAX_STEPS 强制停止' : 'Runtime 因协议错误停止', file: 'agent.py',
      code: pretty(event),
      explanation: byBudget
        ? `<p>即使每个动作都不同且合法，整个循环仍受全局 step budget 约束。</p>`
        : `<p>Runtime 无法安全解释 Model response，因此停止。</p>`,
    };
  }

  if (event.type === 'final') {
    return {
      node: 'final', label: event.stopped ? 'Stopped Answer' : 'Final Answer',
      title: event.stopped ? 'Runtime 安全停止' : 'Agent Loop 完成', file: 'agent.py',
      code: `return ${JSON.stringify(event.content)}`,
      explanation: `<p><strong>最终输出：</strong>${event.content}</p>`,
    };
  }

  return {
    node: 'model', label: event.type, title: 'Runtime Event', file: 'agent.py',
    code: pretty(event), explanation: '<p>这是一个 Runtime 观察事件。</p>',
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

function highlightNode(nodeName) {
  document.querySelectorAll('.node').forEach((node) => {
    node.classList.toggle('active', node.dataset.node === nodeName);
  });
}

function showStep(index) {
  if (!events.length) return;
  currentIndex = Math.max(0, Math.min(index, events.length - 1));
  const event = events[currentIndex];
  const meta = eventMeta(event);

  highlightNode(meta.node);
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
  if (autoTimer) {
    clearInterval(autoTimer);
    autoTimer = null;
  }
  autoButton.textContent = '自动播放';
}

function resetView() {
  stopAuto();
  events = [];
  currentIndex = -1;
  highlightNode('');
  timelineList.innerHTML = '<li class="empty">点击“运行真实 V3”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'agent.py';
  codePanel.textContent = '等待执行事件…';
  explainTitle.textContent = '为什么这样设计？';
  explainBody.innerHTML = '<p>推荐先跑“Timeout → Retry → 成功”，再跑“重复 Tool Call → 拦截”。</p>';
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
        max_steps: Number.parseInt(maxStepsInput.value, 10),
        max_retries: Number.parseInt(maxRetriesInput.value, 10),
      }),
    });
    const data = await response.json();
    events = data.events || [];

    if (!events.length) throw new Error(data.error || 'Runtime did not emit events.');
    showStep(0);
  } catch (error) {
    explainTitle.textContent = '运行失败';
    explainBody.innerHTML = `<p class="note">${error.message}</p>`;
  } finally {
    runButton.disabled = false;
    runButton.textContent = '运行真实 V3';
  }
}

runButton.addEventListener('click', runTrace);
prevButton.addEventListener('click', () => showStep(currentIndex - 1));
nextButton.addEventListener('click', () => showStep(currentIndex + 1));
resetButton.addEventListener('click', resetView);
autoButton.addEventListener('click', () => {
  if (!events.length) return;
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
