const runButton = document.querySelector('#run-btn');
const prevButton = document.querySelector('#prev-btn');
const nextButton = document.querySelector('#next-btn');
const autoButton = document.querySelector('#auto-btn');
const resetButton = document.querySelector('#reset-btn');
const promptInput = document.querySelector('#prompt');
const scenarioSelect = document.querySelector('#scenario');
const maxStepsInput = document.querySelector('#max-steps');
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
      explanation: `<p>Trace 从用户目标开始。用户文字是输入数据，不是执行权限。</p>`,
    };
  }

  if (event.type === 'model_request') {
    return {
      node: 'model', label: event.phase === 'start' ? 'Model Request' : 'Model Continue',
      title: event.phase === 'start' ? 'Runtime 请求 Model 决定下一步' : 'Observation 回到 Model',
      file: 'agent.py',
      code: event.phase === 'start'
        ? `response = model.start(user_message)`
        : `response = model.continue_with_tool_result(..., result=observation)`,
      explanation: `<p>Model 负责提出下一动作，但它返回的内容仍然只是 proposal。</p>`,
    };
  }

  if (event.type === 'model_response') {
    const responseType = event.response?.type ?? typeof event.response;
    return {
      node: 'model', label: `Model Response · ${responseType}`,
      title: 'Model 返回 Runtime-facing response', file: 'model_adapters.py',
      code: `response = ${pretty(event.response)}\n\n# 下一步必须先经过 Model Validator。`,
      explanation: `<p><strong>V2 新规则：</strong>即使 Adapter 已经做过 normalize，Runtime 仍不直接信任 response shape。</p>`,
    };
  }

  if (event.type === 'model_validation') {
    const ok = event.validation?.ok === true;
    return {
      node: 'modelguard', label: ok ? 'Model Validation Passed' : 'Model Validation Failed',
      title: ok ? 'Model Response contract 合法' : 'Model Response contract 被拒绝',
      file: 'runtime_validation.py',
      code: `response_validation = validate_model_response(response)\n\n# ${pretty(event.validation)}`,
      explanation: ok
        ? `<p>Runtime 确认这是合法的 <code>final</code> 或 <code>tool_call</code> 结构。</p>`
        : `<p>错误发生在 Tool Registry <strong>之前</strong>。Runtime 无法安全解释这个 response，因此直接受控停止。</p><p class="note">不要用 try/except 把坏协议“糊过去”；协议错误应该明确暴露。</p>`,
    };
  }

  if (event.type === 'runtime_step') {
    return {
      node: 'budget', label: `Runtime Step ${event.step}/${event.max_steps}`,
      title: 'Runtime 消耗一个 Tool Call budget', file: 'agent.py',
      code: `if tool_steps >= max_steps:\n    stop()\n\ntool_steps += 1\n# step = ${event.step}, max_steps = ${event.max_steps}`,
      explanation: `<p>每个 Tool Call proposal 都消耗一次预算。MAX_STEPS 属于 Runtime，Model 无法提高这个上限。</p>`,
    };
  }

  if (event.type === 'tool_lookup') {
    return {
      node: 'registry', label: event.found ? 'Registry Hit' : 'Registry Miss',
      title: event.found ? 'Registry 找到真实能力' : 'Registry 找不到该 Tool', file: 'tools.py',
      code: `tool = resolve_tool(tool_name)\n# tool_name = ${JSON.stringify(event.tool_name)}\n# found = ${event.found}`,
      explanation: event.found
        ? `<p>字符串名字被解析为显式注册的 Python function。</p>`
        : `<p>不存在的能力不会被执行，而会变成错误 Observation。</p>`,
    };
  }

  if (event.type === 'tool_validation') {
    const ok = event.validation?.ok === true;
    return {
      node: 'validator', label: ok ? 'Tool Validation Passed' : 'Tool Validation Failed',
      title: ok ? 'Tool 参数合法' : 'Tool 参数被拒绝', file: 'tools.py',
      code: `validation = validate_tool_arguments(tool_name, arguments)\n\n# ${pretty(event.validation)}`,
      explanation: ok
        ? `<p>通过 Tool 层的确定性参数检查后，才允许执行。</p>`
        : `<p>Model Response 的结构可以合法，但具体 Tool 参数仍可能非法。这是两层不同验证。</p>`,
    };
  }

  if (event.type === 'tool_rejected') {
    return {
      node: 'validator', label: 'Tool Rejected', title: 'Runtime 拒绝执行 Tool', file: 'agent.py',
      code: `if not validation["ok"]:\n    observation = {"error": validation["error"]}\n    # 不执行 tool(**arguments)`,
      explanation: `<p>拒绝执行是 Runtime 的正常输出路径，不是 Python 崩溃。</p>`,
    };
  }

  if (event.type === 'tool_execute') {
    return {
      node: 'tool', label: 'Tool Execute', title: 'Python Function 真正执行', file: 'agent.py',
      code: `observation = tool(**arguments)\n# ${event.tool_name}(${pretty(event.arguments)})`,
      explanation: `<p>只有 Model contract、Step Budget、Registry、Tool Validation 全部通过，才会来到执行边界。</p>`,
    };
  }

  if (event.type === 'tool_result' || event.type === 'tool_error' || event.type === 'tool_observation') {
    const value = event.observation ?? event.result ?? event.error;
    return {
      node: 'observation', label: event.type === 'tool_observation' ? 'Observation' : event.type,
      title: '真实结果进入 Observation', file: 'agent.py',
      code: `observation = ${pretty(value)}`,
      explanation: `<p>成功或错误都被转换成 Model 下一轮可以看到的真实 Observation。</p>`,
    };
  }

  if (event.type === 'runtime_stop') {
    const byBudget = event.reason === 'max_steps';
    return {
      node: byBudget ? 'budget' : 'modelguard',
      label: byBudget ? 'MAX_STEPS Stop' : 'Invalid Response Stop',
      title: byBudget ? 'Runtime 强制终止无限循环' : 'Runtime 因协议错误停止',
      file: 'agent.py',
      code: `_stop_agent(\n    reason=${JSON.stringify(event.reason)},\n    step=${event.step},\n    max_steps=${event.max_steps},\n)\n\n# ${pretty(event.error)}`,
      explanation: byBudget
        ? `<p>前 ${event.step} 次 Tool Call 都可能完全合法，但 Runtime 仍拒绝第 ${event.step + 1} 次执行。</p><p class="note"><strong>合法 ≠ 可以无限执行。</strong></p>`
        : `<p>Response contract 不可信时，Runtime 选择 fail safely，而不是猜 Model 到底想表达什么。</p>`,
    };
  }

  if (event.type === 'final') {
    return {
      node: 'final', label: event.stopped ? 'Stopped Answer' : 'Final Answer',
      title: event.stopped ? 'Runtime 安全停止' : 'Agent Loop 正常完成', file: 'agent.py',
      code: `return ${JSON.stringify(event.content)}`,
      explanation: `<p><strong>最终输出：</strong>${event.content}</p><p class="note">V2 允许两种健康结局：正常完成，或被 Runtime 明确、安全地停止。</p>`,
    };
  }

  return {
    node: 'runtime', label: event.type, title: 'Runtime Event', file: 'agent.py',
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
  timelineList.innerHTML = '<li class="empty">点击“运行真实 V2”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'agent.py';
  codePanel.textContent = '等待执行事件…';
  explainTitle.textContent = '为什么这样设计？';
  explainBody.innerHTML = '<p>推荐先跑“Model Response 格式错误”，再跑“Model 无限 Tool Loop”。</p>';
  eventJson.textContent = '{}';
  stepCounter.textContent = '尚未运行';
}

async function runTrace() {
  stopAuto();
  runButton.disabled = true;
  runButton.textContent = 'Runtime 执行中…';

  try {
    const maxSteps = Number.parseInt(maxStepsInput.value, 10);
    const response = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: promptInput.value,
        scenario: scenarioSelect.value,
        max_steps: maxSteps,
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
    runButton.textContent = '运行真实 V2';
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
  }, 900);
});

resetView();
