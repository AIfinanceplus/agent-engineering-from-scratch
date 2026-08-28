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
    explanation: `<p>用户输入只是目标，不携带执行权限。</p>`,
  };

  if (event.type === 'model_request' || event.type === 'model_response') return {
    node: 'model', label: event.type === 'model_request' ? 'Model Request' : 'Model Response',
    title: 'Model 提出下一动作', file: event.type === 'model_request' ? 'agent.py' : 'model_adapters.py',
    code: event.type === 'model_request' ? `response = model.start(...) / model.continue_with_tool_result(...)` : pretty(event.response),
    explanation: `<p>Model 只能提出 proposal；不能自己授权执行。</p>`,
  };

  if (['model_validation', 'runtime_step', 'duplicate_check'].includes(event.type)) return {
    node: 'guards', label: event.type, title: 'Runtime Guards', file: event.type === 'model_validation' ? 'model_validation.py' : 'agent.py',
    code: pretty(event),
    explanation: `<p>这些 guard 继续负责协议、总步数和重复动作。</p>`,
  };

  if (event.type === 'tool_lookup') return {
    node: 'registry', label: event.found ? 'Tool Object Resolved' : 'Registry Miss',
    title: event.found ? 'Registry 返回完整 Tool Object' : 'Registry 找不到能力',
    file: 'tools.py',
    code: event.found ? `tool = resolve_tool(tool_name)\n\n${pretty(event.tool_metadata)}` : `tool = None`,
    explanation: event.found
      ? `<p>Tool Object 现在包含 <strong>risk</strong>。注意：risk 是事实，不是最终 permission。</p>`
      : `<p>不存在的能力直接在 Registry 边界结束。</p>`,
  };

  if (event.type === 'tool_validation') return {
    node: 'toolobject', label: event.validation?.ok ? 'Tool.validate ✓' : 'Tool.validate ✕',
    title: 'Tool 参数验证', file: 'tools.py',
    code: `validation = tool.validate(arguments)\n\n${pretty(event.validation)}`,
    explanation: `<p>Policy 只处理一个已经可以安全解释的 Tool request，所以先做确定性参数验证。</p>`,
  };

  if (event.type === 'policy_decision') {
    const decision = event.policy?.decision;
    const label = decision === 'allow' ? 'Policy ALLOW' : decision === 'require_approval' ? 'Policy REQUIRE_APPROVAL' : 'Policy DENY';
    return {
      node: 'policy', label, title: 'Policy Engine 做出权限决定', file: 'policy.py',
      code: `policy_result = policy_engine.evaluate(tool, arguments)\n\n# Tool risk = ${event.tool_risk}\n# ${pretty(event.policy)}`,
      explanation: decision === 'allow'
        ? `<p><strong>ALLOW：</strong>当前规则允许这个 low-risk capability 自动执行。</p>`
        : decision === 'require_approval'
          ? `<p><strong>REQUIRE_APPROVAL：</strong>Tool 存在且参数合法，但 medium-risk 动作不能自动执行。</p><p class="note">V5 只返回 approval_required；真正 pause/resume approval 以后再做。</p>`
          : `<p><strong>DENY：</strong>当前 policy 明确禁止 high-risk 动作。Model 不能绕过这个决定。</p>`,
    };
  }

  if (event.type === 'tool_execute') return {
    node: 'toolobject', label: 'Execution Policy Loaded', title: 'Policy 已允许，加载 Tool 执行策略', file: 'agent.py',
    code: `# PolicyDecision.ALLOW 已通过\nobservation = _execute_tool_with_retry(tool=tool, ...)\n\n${pretty(event.tool_metadata)}`,
    explanation: `<p>只有 Policy 返回 ALLOW 后，Runtime 才进入 retry/function 执行路径。</p>`,
  };

  if (event.type === 'tool_attempt') return {
    node: 'tool', label: `Tool Attempt ${event.attempt}/${event.total_attempts}`,
    title: 'Python Function 真正执行', file: 'agent.py',
    code: `result = tool.function(**arguments)`,
    explanation: `<p>这是实际执行边界。Policy 的价值就是保证不该执行的请求永远到不了这一行。</p>`,
  };

  if (event.type === 'tool_retry') return {
    node: 'toolobject', label: `Retry → ${event.next_attempt}`, title: 'Tool-owned Retry', file: 'agent.py / tools.py',
    code: pretty(event),
    explanation: `<p>Retry 仍由 Tool 自己的执行策略控制，与 Policy permission 是两层不同问题。</p>`,
  };

  if (event.type === 'tool_rejected') {
    const policyBlock = ['require_approval', 'deny'].includes(event.reason);
    return {
      node: policyBlock ? 'policy' : (event.reason === 'duplicate_tool_call' ? 'guards' : 'toolobject'),
      label: policyBlock ? 'Policy Blocked Execution' : 'Tool Rejected',
      title: policyBlock ? 'Policy 阻止真实执行' : 'Runtime 拒绝执行',
      file: 'agent.py',
      code: `observation = {"error": ${pretty(event.error)}}\n# tool.function(...) 不会运行`,
      explanation: policyBlock
        ? `<p>能力存在、参数合法，但 permission 不通过，所以 Python function 完全不会执行。</p>`
        : `<p>其它 Runtime guard 或 validation 阻止了执行。</p>`,
    };
  }

  if (event.type === 'tool_result' || event.type === 'tool_error' || event.type === 'tool_observation') return {
    node: 'observation', label: event.type, title: '结果统一进入 Observation', file: 'agent.py',
    code: pretty(event),
    explanation: `<p>ALLOW 的执行结果，以及 REQUIRE_APPROVAL / DENY 的结构化错误，最终都成为 Observation。</p>`,
  };

  if (event.type === 'runtime_stop') return {
    node: 'guards', label: 'Runtime Stop', title: 'Runtime 安全停止', file: 'agent.py',
    code: pretty(event), explanation: `<p>全局 Runtime guard 仍然独立于 Policy Engine。</p>`,
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
  timelineList.innerHTML = '<li class="empty">点击“运行真实 V5”开始。</li>';
  codeTitle.textContent = '对应代码';
  codeFile.textContent = 'agent.py';
  codePanel.textContent = '等待执行事件…';
  explainTitle.textContent = '为什么这样设计？';
  explainBody.innerHTML = '<p>推荐依次跑 LOW → ALLOW、MEDIUM → REQUIRE_APPROVAL、HIGH → DENY。</p>';
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
    runButton.textContent = '运行真实 V5';
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
