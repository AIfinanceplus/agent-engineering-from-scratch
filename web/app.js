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

let events = [];
let currentIndex = -1;
let autoTimer = null;

function pretty(value) { return JSON.stringify(value, null, 2); }

function eventMeta(event) {
  if (event.type === 'execution_context') return {
    node: 'context', label: 'ExecutionContext Injected', title: 'Runtime 注入可信执行身份', file: 'context.py / agent.py',
    code: `runtime_context = ExecutionContext(...)\n\n${pretty(event.context)}\n\n# source = ${event.source}`,
    explanation: `<p>这些字段不是 Model 生成的。Runtime 在调用 Model 之前已经知道 tenant、user、agent、task、trace。</p><p class="note">Model Context 是“模型看到什么”；ExecutionContext 是“系统知道谁在执行”。</p>`,
  };

  if (event.type === 'user_input') return {
    node: 'user', label: 'User Input', title: '用户目标进入 Runtime', file: 'agent.py',
    code: `_emit(on_event, "user_input", message=user_message)`,
    explanation: `<p>用户输入表达目标，但不能声明自己拥有什么执行身份或权限。</p>`,
  };

  if (event.type === 'model_request' || event.type === 'model_response') return {
    node: 'model', label: event.type === 'model_request' ? 'Model Request' : 'Model Response',
    title: 'Model 只提出下一动作', file: event.type === 'model_request' ? 'agent.py' : 'model_adapters.py',
    code: event.type === 'model_request' ? `response = model.start(...) / model.continue_with_tool_result(...)` : pretty(event.response),
    explanation: `<p>Model 返回 Tool name + arguments。它不会得到修改 ExecutionContext 的接口。</p>`,
  };

  if (['model_validation', 'runtime_step', 'duplicate_check'].includes(event.type)) return {
    node: 'guards', label: event.type, title: 'Runtime Guards', file: event.type === 'model_validation' ? 'model_validation.py' : 'agent.py',
    code: pretty(event), explanation: `<p>协议、步数、重复动作仍由 Runtime 的确定性 guard 保护。</p>`,
  };

  if (event.type === 'tool_lookup') return {
    node: 'registry', label: event.found ? 'Tool Object Resolved' : 'Registry Miss',
    title: event.found ? 'Registry 返回 Capability' : 'Registry 找不到 Capability', file: 'tools.py',
    code: event.found ? `tool = resolve_tool(tool_name)\n\n${pretty(event.tool_metadata)}` : `tool = None`,
    explanation: event.found ? `<p>Tool Object 描述这个能力自身的 schema、risk、retry、function。</p>` : `<p>不存在的 Tool 不进入 Policy。</p>`,
  };

  if (event.type === 'tool_validation') return {
    node: 'toolobject', label: event.validation?.ok ? 'Tool.validate ✓' : 'Tool.validate ✕',
    title: 'Capability 参数验证', file: 'tools.py',
    code: `validation = tool.validate(arguments)\n\n${pretty(event.validation)}`,
    explanation: `<p>Policy 接收到的是一个已经结构合法的 Tool request。</p>`,
  };

  if (event.type === 'policy_decision') {
    const decision = event.policy?.decision;
    const label = decision === 'allow' ? 'Policy ALLOW' : decision === 'require_approval' ? 'Policy REQUIRE_APPROVAL' : 'Policy DENY';
    return {
      node: 'policy', label, title: 'Policy = Capability + ExecutionContext', file: 'policy.py',
      code: `policy_result = policy_engine.evaluate(\n    tool,\n    arguments,\n    runtime_context,\n)\n\n# Tool risk = ${event.tool_risk}\n# Context\n${pretty(event.context)}\n\n# Decision\n${pretty(event.policy)}`,
      explanation: decision === 'allow'
        ? `<p><strong>ALLOW：</strong>当前 agent 身份与 Tool risk 的组合允许自动执行。</p>`
        : decision === 'require_approval'
          ? `<p><strong>REQUIRE_APPROVAL：</strong>general-agent 可以请求 medium-risk 动作，但还需要人工批准。</p>`
          : `<p><strong>DENY：</strong>当前执行身份没有资格让这个动作继续。试着把 general-agent 与 read-only-agent 来回切换。</p>`,
    };
  }

  if (event.type === 'tool_execute') return {
    node: 'toolobject', label: 'Execution Allowed', title: 'Policy 已允许执行', file: 'agent.py',
    code: `# context.agent_id = ${JSON.stringify(event.context?.agent_id)}\nobservation = _execute_tool_with_retry(tool=tool, ...)`,
    explanation: `<p>只有 Policy ALLOW 后，真实 function 才能执行。Trace 同时保留是哪一个 agent 执行的。</p>`,
  };

  if (event.type === 'tool_attempt') return {
    node: 'tool', label: `Tool Attempt ${event.attempt}/${event.total_attempts}`, title: 'Python Function 真正执行', file: 'agent.py',
    code: `result = tool.function(**arguments)`,
    explanation: `<p>这里是真正的 side effect / compute 边界。权限不通过的请求永远到不了这里。</p>`,
  };

  if (event.type === 'tool_retry') return {
    node: 'toolobject', label: `Retry → ${event.next_attempt}`, title: 'Tool-owned Retry', file: 'agent.py / tools.py',
    code: pretty(event), explanation: `<p>Retry 仍然只处理执行故障，与身份/权限是独立层。</p>`,
  };

  if (event.type === 'tool_rejected') {
    const policyBlock = ['require_approval', 'deny'].includes(event.reason);
    return {
      node: policyBlock ? 'policy' : (event.reason === 'duplicate_tool_call' ? 'guards' : 'toolobject'),
      label: policyBlock ? 'Policy Blocked Execution' : 'Tool Rejected',
      title: policyBlock ? 'Policy 阻止真实执行' : 'Runtime 拒绝执行', file: 'agent.py',
      code: `observation = {"error": ${pretty(event.error)}}\n# tool.function(...) 不会运行`,
      explanation: policyBlock ? `<p>Capability 存在且参数合法，但当前 ExecutionContext 不满足执行条件。</p>` : `<p>其它 Runtime guard 或 validation 阻止了执行。</p>`,
    };
  }

  if (event.type === 'tool_result' || event.type === 'tool_error' || event.type === 'tool_observation') return {
    node: 'observation', label: event.type, title: '结果统一进入 Observation', file: 'agent.py',
    code: pretty(event), explanation: `<p>执行结果或权限错误都会统一回到 Model。</p>`,
  };

  if (event.type === 'runtime_stop') return {
    node: 'guards', label: 'Runtime Stop', title: 'Runtime 安全停止', file: 'agent.py', code: pretty(event),
    explanation: `<p>ExecutionContext 没有替代 MAX_STEPS 等全局 guard。</p>`,
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
  timelineList.innerHTML = '<li class="empty">点击“运行真实 V6”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'agent.py';
  codePanel.textContent = '等待执行事件…';
  explainTitle.textContent = '为什么这样设计？';
  explainBody.innerHTML = '<p>固定 send_message 场景，先用 general-agent，再切换 read-only-agent，比较 Policy Decision。</p>';
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
    if (!events.length) throw new Error(data.error || 'Runtime did not emit events.');
    showStep(0);
  } catch (error) {
    explainTitle.textContent = '运行失败';
    explainBody.innerHTML = `<p class="note">${error.message}</p>`;
  } finally {
    runButton.disabled = false;
    runButton.textContent = '运行真实 V6';
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
