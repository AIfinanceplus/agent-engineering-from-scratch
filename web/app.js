const runButton = document.querySelector('#run-btn');
const prevButton = document.querySelector('#prev-btn');
const nextButton = document.querySelector('#next-btn');
const autoButton = document.querySelector('#auto-btn');
const resetButton = document.querySelector('#reset-btn');
const promptInput = document.querySelector('#prompt');
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
      code: `_emit(on_event, "user_input", message=user_message)\n\n# 观察器只记录事实，不改变 user_message。`,
      explanation: `
        <p><strong>发生了什么：</strong>Runtime 收到用户目标，并把它记录成第一个可观察事件。</p>
        <p class="note"><strong>为什么重要：</strong>这是 Trace 的起点。以后所有 Tool Call、错误和最终答案都可以追溯回同一次请求。</p>
      `,
    };
  }

  if (event.type === 'model_request' && event.phase === 'start') {
    return {
      node: 'model',
      label: 'Model Request',
      title: 'Runtime 请求 Model 决定下一步',
      file: 'agent.py',
      code: `_emit(on_event, "model_request", phase="start", message=user_message)\n\nresponse = model.start(user_message)`,
      explanation: `
        <p><strong>职责边界：</strong>Runtime 把问题交给 Model，但并没有自己决定要调用哪个 Tool。</p>
        <p class="note"><strong>设计原则：</strong>Model 决定 <em>WHAT</em>；Runtime 保留执行权。</p>
      `,
    };
  }

  if (event.type === 'model_response' && event.response?.type === 'tool_call') {
    return {
      node: 'runtime',
      label: 'Tool Call Proposed',
      title: 'Model 提议一个 Tool Call',
      file: 'model_adapters.py',
      code: `return {\n    "type": "tool_call",\n    "tool_name": item.name,\n    "arguments": json.loads(item.arguments),\n    "call_id": item.call_id,\n}\n\n# 注意：这里只是“提议动作”，还没有执行 Python function。`,
      explanation: `
        <p><strong>Model 输出：</strong>它选择了 <code>calculator</code>，并给出参数。</p>
        <p><strong>关键区别：</strong>Tool Call 不是 Tool Execution。模型只能提出“我想调用 calculator”；真正执行要经过 Runtime。</p>
      `,
    };
  }

  if (event.type === 'tool_lookup') {
    return {
      node: 'registry',
      label: 'Registry Lookup',
      title: 'Runtime 用名字找到真实 Function',
      file: 'agent.py',
      code: `tool_name = response["tool_name"]\narguments = response["arguments"]\n\ntool = tool_registry[tool_name]\n\n# tool_registry: "calculator" -> calculator`,
      explanation: `
        <p><strong>Registry 的作用：</strong>模型只知道字符串 <code>calculator</code>；Registry 把这个名字映射到真实 Python function。</p>
        <p class="note">这一步把“不可信的模型输出”与“真正可执行的程序能力”隔开。</p>
      `,
    };
  }

  if (event.type === 'tool_execute') {
    return {
      node: 'tool',
      label: 'Tool Execute',
      title: 'Runtime 真正执行 Python Function',
      file: 'agent.py',
      code: `result = tool(**arguments)\n\n# 等价于：\n# calculator(a=10, b=20, operation="add")`,
      explanation: `
        <p><strong>真正发生副作用/计算的位置：</strong><code>tool(**arguments)</code>。</p>
        <p>现在 calculator 才真的运行。未来的权限、Sandbox、Timeout、Retry 都会围绕这一行建立，而不是交给 Model。</p>
      `,
    };
  }

  if (event.type === 'tool_result') {
    return {
      node: 'observation',
      label: 'Observation',
      title: 'Tool Result 变成 Observation',
      file: 'agent.py',
      code: `_emit(on_event, "tool_result", tool_name=tool_name, result=result)\n\n# result == 30\n# 下一步不是直接回答用户，而是把结果交回 Model。`,
      explanation: `
        <p><strong>结果：</strong>Python function 得到了 <code>30</code>。</p>
        <p class="note"><strong>Agent Loop 的核心：</strong>行动之后必须产生 Observation，让 Model 根据真实世界结果继续推理。</p>
      `,
    };
  }

  if (event.type === 'model_request' && event.phase === 'continue') {
    return {
      node: 'model',
      label: 'Model Continue',
      title: 'Runtime 把 Observation 交回 Model',
      file: 'agent.py',
      code: `response = model.continue_with_tool_result(\n    previous_response_id=response.get("response_id"),\n    call_id=response.get("call_id"),\n    tool_name=tool_name,\n    result=result,\n)`,
      explanation: `
        <p><strong>为什么要回 Model：</strong>Tool 只负责算出 30，它不知道怎样把这个结果组织成最终回答。</p>
        <p><code>call_id</code> 把 Observation 和之前那次 Tool Call 对应起来。</p>
      `,
    };
  }

  if (event.type === 'model_response' && event.response?.type === 'final') {
    return {
      node: 'runtime',
      label: 'Final Proposed',
      title: 'Model 返回 Final，而不是新的 Tool Call',
      file: 'agent.py',
      code: `if response["type"] == "final":\n    _emit(on_event, "final", content=response["content"])\n    return response["content"]`,
      explanation: `
        <p><strong>停止条件：</strong>这次 Model 没有继续要求工具，而是产生 <code>final</code>。</p>
        <p>Runtime 因此结束循环。以后加入 <code>MAX_STEPS</code> 时，还会有另一种由 Runtime 强制停止的条件。</p>
      `,
    };
  }

  if (event.type === 'final') {
    return {
      node: 'final',
      label: 'Final Answer',
      title: 'Agent Loop 完成',
      file: 'agent.py',
      code: `return response["content"]\n\n# "The result is 30."`,
      explanation: `
        <p><strong>最终结果：</strong>${event.content}</p>
        <p class="note">完整闭环：User → Model → Tool Call → Registry → Function → Observation → Model → Final。</p>
      `,
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
  timelineList.innerHTML = '<li class="empty">点击“运行真实 V0.2”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'agent.py';
  codePanel.textContent = '等待执行事件…';
  explainTitle.textContent = '为什么这样设计？';
  explainBody.innerHTML = '<p>每一步都会显示中文注释，重点解释职责边界，而不只是逐行翻译代码。</p>';
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
      body: JSON.stringify({ message: promptInput.value }),
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
    runButton.textContent = '运行真实 V0.2';
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
  }, 1200);
});

resetView();
