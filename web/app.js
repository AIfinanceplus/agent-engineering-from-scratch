const runButton = document.querySelector('#run-btn');
const prevButton = document.querySelector('#prev-btn');
const nextButton = document.querySelector('#next-btn');
const autoButton = document.querySelector('#auto-btn');
const resetButton = document.querySelector('#reset-btn');
const promptInput = document.querySelector('#prompt');
const scenarioSelect = document.querySelector('#scenario');
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

function eventMeta(event) {
  if (event.type === 'user_input') {
    return {
      node: 'user',
      label: 'User Input',
      title: '用户目标进入 Runtime',
      file: 'agent.py',
      code: `_emit(on_event, "user_input", message=user_message)`,
      explanation: `
        <p><strong>发生了什么：</strong>Runtime 收到用户目标，并记录 Trace 起点。</p>
        <p class="note">用户文字与 Model 输出都属于输入数据，不等于 Runtime 权限。</p>
      `,
    };
  }

  if (event.type === 'model_request' && event.phase === 'start') {
    return {
      node: 'model',
      label: 'Model Request',
      title: 'Runtime 请求 Model 决定下一动作',
      file: 'agent.py',
      code: `response = model.start(user_message)`,
      explanation: `
        <p>Model 可以选择 Tool 和参数，但它只能<strong>提议</strong>动作。</p>
        <p class="note">Model 决定 WHAT；Runtime 决定这个 WHAT 是否允许真正发生。</p>
      `,
    };
  }

  if (event.type === 'model_response' && event.response?.type === 'tool_call') {
    return {
      node: 'runtime',
      label: 'Tool Call Proposed',
      title: 'Model 提议 Tool Call',
      file: 'model_adapters.py',
      code: `return {\n    "type": "tool_call",\n    "tool_name": item.name,\n    "arguments": json.loads(item.arguments),\n}\n\n# 这里只是 proposal，不是 execution。`,
      explanation: `
        <p>这一步最值得记住：<strong>Tool Call ≠ Tool Execution</strong>。</p>
        <p>无论 Model 多么聪明，它输出的 tool_name 和 arguments 都必须当成不可信输入处理。</p>
      `,
    };
  }

  if (event.type === 'tool_lookup') {
    const foundText = event.found ? '找到' : '没有找到';
    return {
      node: 'registry',
      label: event.found ? 'Registry Hit' : 'Registry Miss',
      title: `Tool Registry ${foundText}能力`,
      file: 'tools.py',
      code: `tool = resolve_tool(tool_name)\n\n# TOOL_REGISTRY.get(tool_name)\n# found = ${event.found}`,
      explanation: event.found
        ? `<p>Registry 把字符串 <code>${event.tool_name}</code> 解析为真正 Python function。</p><p class="note">只有 Registry 中显式注册的能力才存在。</p>`
        : `<p>Model 请求了一个系统根本没有注册的 Tool。</p><p class="note">V0 会在这里 KeyError；V1 把它转成 <code>unknown_tool</code> Observation。</p>`,
    };
  }

  if (event.type === 'tool_validation') {
    const ok = event.validation?.ok === true;
    return {
      node: 'validator',
      label: ok ? 'Validation Passed' : 'Validation Failed',
      title: ok ? '参数验证通过' : '参数验证失败',
      file: 'tools.py',
      code: `validation = validate_tool_arguments(\n    tool_name,\n    arguments,\n)\n\n# validation = ${JSON.stringify(event.validation, null, 2)}`,
      explanation: ok
        ? `<p>Runtime 已确认 Tool 存在、必需参数齐全、参数类型与 operation 合法。</p><p class="note">通过验证之后才进入真正执行。</p>`
        : `<p>Runtime 在执行 Python function <strong>之前</strong>发现问题。</p><p class="note">确定性检查应该由 Runtime 做，不应该再问 Model “你确定吗？”</p>`,
    };
  }

  if (event.type === 'tool_rejected') {
    return {
      node: 'validator',
      label: 'Tool Rejected',
      title: 'Runtime 拒绝执行 Tool',
      file: 'agent.py',
      code: `if not validation["ok"]:\n    observation = {"error": validation["error"]}\n    # 注意：没有调用 tool(**arguments)`,
      explanation: `
        <p><strong>关键行为：</strong>错误调用到这里就停止了，Calculator 根本没有运行。</p>
        <p class="note">拒绝执行不是 Agent 失败，而是 Runtime 正常履行安全边界。</p>
      `,
    };
  }

  if (event.type === 'tool_execute') {
    return {
      node: 'tool',
      label: 'Tool Execute',
      title: 'Runtime 真正执行 Python Function',
      file: 'agent.py',
      code: `observation = tool(**arguments)\n\n# 只有 Registry 命中 + Validation 通过后才会来到这里。`,
      explanation: `
        <p>这一行才是真实执行边界。以后 Timeout、Retry、Permission、Sandbox、Approval 都会包围这里。</p>
      `,
    };
  }

  if (event.type === 'tool_result') {
    return {
      node: 'observation',
      label: 'Tool Result',
      title: 'Tool 成功产生结果',
      file: 'agent.py',
      code: `_emit(\n    on_event,\n    "tool_result",\n    tool_name=tool_name,\n    result=observation,\n)`,
      explanation: `<p>真实 Python function 已经完成，本例结果是 <code>${event.result}</code>。</p>`,
    };
  }

  if (event.type === 'tool_error') {
    return {
      node: 'observation',
      label: 'Tool Execution Error',
      title: '执行期异常被规范化',
      file: 'agent.py',
      code: `except Exception as exc:\n    observation = _execution_error(tool_name, exc)`,
      explanation: `<p>即使验证通过，Tool 自己仍可能失败。Runtime 把异常转成结构化 Observation，而不是丢失上下文。</p>`,
    };
  }

  if (event.type === 'tool_observation') {
    return {
      node: 'observation',
      label: 'Observation',
      title: '结果或错误统一成为 Observation',
      file: 'agent.py',
      code: `_emit(\n    on_event,\n    "tool_observation",\n    observation=observation,\n)\n\n# observation = ${JSON.stringify(event.observation, null, 2)}`,
      explanation: `
        <p>成功结果和拒绝错误最终都进入同一个概念：<strong>Observation</strong>。</p>
        <p class="note">Tool 错误通常应该反馈给 Model，让 Model 决定下一步，而不是直接把整个 Agent 进程杀掉。</p>
      `,
    };
  }

  if (event.type === 'model_request' && event.phase === 'continue') {
    return {
      node: 'model',
      label: 'Model Continue',
      title: 'Runtime 把 Observation 交回 Model',
      file: 'agent.py',
      code: `response = model.continue_with_tool_result(\n    previous_response_id=response.get("response_id"),\n    call_id=response.get("call_id"),\n    tool_name=tool_name,\n    result=observation,\n)`,
      explanation: `<p>Model 现在看到的是 Runtime 验证后的真实结果或错误，而不是假装 Tool 已经成功。</p>`,
    };
  }

  if (event.type === 'model_response' && event.response?.type === 'final') {
    return {
      node: 'runtime',
      label: 'Final Proposed',
      title: 'Model 根据 Observation 给出最终回答',
      file: 'agent.py',
      code: `if response["type"] == "final":\n    return response["content"]`,
      explanation: `<p>正常场景会报告计算结果；错误场景会明确说明哪一层验证失败。</p>`,
    };
  }

  if (event.type === 'final') {
    return {
      node: 'final',
      label: 'Final Answer',
      title: '这一轮 Agent Loop 完成',
      file: 'agent.py',
      code: `return response["content"]`,
      explanation: `<p><strong>最终结果：</strong>${event.content}</p><p class="note">V1 的重点不是“永远成功”，而是“错误也以受控方式流经系统”。</p>`,
    };
  }

  return {
    node: 'runtime',
    label: event.type,
    title: 'Runtime Event',
    file: 'agent.py',
    code: JSON.stringify(event, null, 2),
    explanation: '<p>这是一个 Runtime 观察事件。</p>',
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
  eventJson.textContent = JSON.stringify(event, null, 2);
  stepCounter.textContent = `Step ${currentIndex + 1} / ${events.length}`;
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
  timelineList.innerHTML = '<li class="empty">点击“运行真实 V1”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'agent.py';
  codePanel.textContent = '等待执行事件…';
  explainTitle.textContent = '为什么这样设计？';
  explainBody.innerHTML = '<p>选择不同场景，观察 Tool Call 在 Registry / Validator 边界发生什么。</p>';
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
    runButton.textContent = '运行真实 V1';
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
  }, 1100);
});

resetView();
