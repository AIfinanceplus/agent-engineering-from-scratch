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

function pretty(value) { return JSON.stringify(value, null, 2); }

function eventMeta(event) {
  if (event.type === 'user_input') return {
    node: 'user', label: 'User Input', title: '用户目标进入 Runtime', file: 'agent.py',
    code: `_emit(on_event, "user_input", message=user_message)`,
    explanation: `<p>Trace 从用户目标开始。</p>`,
  };

  if (event.type === 'model_request' || event.type === 'model_response') return {
    node: 'model', label: event.type === 'model_request' ? 'Model Request' : 'Model Response',
    title: 'Model 提出下一动作', file: event.type === 'model_request' ? 'agent.py' : 'model_adapters.py',
    code: event.type === 'model_request' ? `response = model.start(...) / model.continue_with_tool_result(...)` : pretty(event.response),
    explanation: `<p>Model 只负责 proposal；真正能力定义仍在 Runtime 侧。</p>`,
  };

  if (['model_validation', 'runtime_step', 'duplicate_check'].includes(event.type)) return {
    node: 'guards', label: event.type, title: 'Runtime Guards', file: event.type === 'model_validation' ? 'model_validation.py' : 'agent.py',
    code: pretty(event),
    explanation: `<p>这些 guard 继续保护 Model contract、总步数和重复动作；V4 没有把安全边界交给 Tool Object。</p>`,
  };

  if (event.type === 'tool_lookup') return {
    node: event.found ? 'registry' : 'registry',
    label: event.found ? 'Tool Object Resolved' : 'Registry Miss',
    title: event.found ? 'Registry 返回完整 Tool Object' : 'Registry 找不到能力',
    file: 'tools.py',
    code: event.found
      ? `tool = resolve_tool(tool_name)\n\n# Tool metadata\n${pretty(event.tool_metadata)}`
      : `tool = resolve_tool(tool_name)\n# result = None`,
    explanation: event.found
      ? `<p>V3 返回的是 callable；V4 返回的是完整 <strong>Tool</strong>：name、description、parameters、function、max_retries、retryable_errors 都在同一对象。</p><p class="note">Registry 现在是 capability catalog。</p>`
      : `<p>未知名字没有对应 Tool Object，因此不会进入执行。</p>`,
  };

  if (event.type === 'tool_validation') return {
    node: 'toolobject', label: event.validation?.ok ? 'Tool.validate ✓' : 'Tool.validate ✕',
    title: 'Tool Object 自己提供 validation', file: 'agent.py / tools.py',
    code: `validation = tool.validate(arguments)\n\n# source = ${event.validator_source}\n# result = ${pretty(event.validation)}`,
    explanation: `<p>参数规则与 Model schema 使用同一个 <code>Tool.parameters</code>。这消除了“schema 说一套、Runtime 检查另一套”的 drift。</p>`,
  };

  if (event.type === 'tool_execute') return {
    node: 'toolobject', label: 'Tool Policy Loaded', title: 'Runtime 从 Tool 读取执行策略', file: 'agent.py',
    code: `effective_retries = tool.max_retries\nresult = _execute_tool_with_retry(tool=tool, ...)\n\n# ${pretty(event.tool_metadata)}\n# policy source = ${event.retry_policy_source}`,
    explanation: `<p>这里直接回答“为什么要 retry”：因为这个具体 Tool 声明了自己的 retry policy。</p><p class="note">普通 calculator: max_retries=0；flaky_calculator: max_retries=2。</p>`,
  };

  if (event.type === 'tool_attempt') return {
    node: 'tool', label: `Tool Attempt ${event.attempt}/${event.total_attempts}`,
    title: '调用 Tool.function', file: 'agent.py',
    code: `result = tool.function(**arguments)\n\n# retry policy\n${pretty(event.retry_policy)}`,
    explanation: `<p>这一行才是真正执行 Python function。Retry 只是 Runtime 再次调用同一个 <code>tool.function</code>。</p>`,
  };

  if (event.type === 'tool_retry') return {
    node: 'toolobject', label: `Retry → ${event.next_attempt}`, title: 'Tool policy 允许 Retry', file: 'agent.py / tools.py',
    code: `except tool.retryable_errors as exc:\n    if attempt < total_attempts:\n        continue\n\n# policy source = ${event.policy_source}`,
    explanation: `<p><strong>${event.error_type}</strong> 属于这个 Tool 声明的 retryable_errors，因此 Runtime 不问 Model，直接重复执行。</p>`,
  };

  if (event.type === 'tool_rejected') return {
    node: event.reason === 'duplicate_tool_call' ? 'guards' : 'toolobject',
    label: 'Tool Rejected', title: 'Runtime 拒绝执行', file: 'agent.py',
    code: pretty(event.error),
    explanation: `<p>Validation 或 duplicate guard 拒绝后，Python function 不会执行。</p>`,
  };

  if (event.type === 'tool_result' || event.type === 'tool_error' || event.type === 'tool_observation') return {
    node: 'observation', label: event.type, title: '结果统一进入 Observation', file: 'agent.py',
    code: pretty(event),
    explanation: `<p>成功、retry exhaustion、validation error 最终都转换成 Observation。</p>`,
  };

  if (event.type === 'runtime_stop') return {
    node: 'guards', label: 'Runtime Stop', title: 'Runtime 安全停止', file: 'agent.py',
    code: pretty(event), explanation: `<p>Tool Object 没有取代 MAX_STEPS 等全局 Runtime guard。</p>`,
  };

  if (event.type === 'final') return {
    node: 'final', label: 'Final', title: 'Agent Loop 完成', file: 'agent.py',
    code: `return ${JSON.stringify(event.content)}`,
    explanation: `<p><strong>最终输出：</strong>${event.content}</p>`,
  };

  return { node: 'guards', label: event.type, title: 'Runtime Event', file: 'agent.py', code: pretty(event), explanation: '<p>Runtime event。</p>' };
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
  document.querySelectorAll('.node').forEach((node) => node.classList.toggle('active', node.dataset.node === name));
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
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  autoButton.textContent = '自动播放';
}

function resetView() {
  stopAuto();
  events = [];
  currentIndex = -1;
  highlightNode('');
  timelineList.innerHTML = '<li class="empty">点击“运行真实 V4”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'agent.py';
  codePanel.textContent = '等待执行事件…';
  explainTitle.textContent = '为什么这样设计？';
  explainBody.innerHTML = '<p>推荐先跑普通 Calculator，再跑 Flaky Calculator，比较 Tool metadata 中的 max_retries。</p>';
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
    runButton.textContent = '运行真实 V4';
  }
}

runButton.addEventListener('click', runTrace);
prevButton.addEventListener('click', () => showStep(currentIndex - 1));
nextButton.addEventListener('click', () => showStep(currentIndex + 1));
resetButton.addEventListener('click', resetView);
autoButton.addEventListener('click', () => {
  if (!events.length) return;
  if (autoTimer) { stopAuto(); return; }
  autoButton.textContent = '停止播放';
  autoTimer = setInterval(() => {
    if (currentIndex >= events.length - 1) { stopAuto(); return; }
    showStep(currentIndex + 1);
  }, 850);
});

resetView();
