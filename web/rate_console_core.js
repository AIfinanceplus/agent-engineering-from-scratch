/* Pure event reducer shared by the browser and executable Node contract tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RateConsole = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const NODES = [
    { id: 'G1', title: 'Goal', description: '一次可审计的利率模拟' },
    { id: 'P1', title: 'Planner', description: '生成固定计划 · 非 LLM' },
    { id: 'R1', title: 'Runtime', description: '注册表 · 校验 · 调度 · 重试' },
    { id: 'D1', title: 'Fetch rates', description: 'Tool · 获取并对齐利率数据' },
    { id: 'S1', title: 'Simulate strategy', description: 'Tool · 信号与一次模拟交易' },
    { id: 'E1', title: 'Evaluate', description: 'Eval · 校验输出与安全边界' }
  ];
  const PARALLEL_NODES = [
    NODES[0],
    { id: 'RG1', title: 'Retriever', description: 'Query · 召回 · 排名 · Top-K' },
    { id: 'CG1', title: 'Citation gate', description: '来源 · 版本 · 双序列覆盖' },
    { id: 'TG1', title: 'Taint guard', description: '不可信内容 · 指令检测 · 隔离' },
    { id: 'CT1', title: 'Context builder', description: '筛选 · 冲突消解 · 压缩 · 打包' },
    { id: 'MR1', title: 'Model router', description: '选路 · token 预算 · 有界 fallback' },
    { id: 'M1', title: 'Model gateway', description: '生成提议 · 无执行权限' },
    NODES[1],
    { id: 'R1', title: 'Runtime', description: '调度 · 容错 · 单线程归集事件' },
    { id: 'L1', title: 'Lease coordinator', description: '所有权 · TTL · fencing token' },
    { id: 'H1', title: 'Human approval', description: '高风险权限升级 · 人工决定' },
    { id: 'AZ1', title: 'Capability gate', description: '签名票据 · 最小 scope · 单次使用' },
    { id: 'C1', title: 'Circuit breaker', description: '连续失败时阻止新 Tool 调用' },
    NODES[3],
    { id: 'V1', title: 'Observation gate', description: '不通过 ↺ P1 · 通过 ↓ Q1' },
    { id: 'Q1', title: 'Admission queue', description: '限速 · 有界排队 · 过载拒绝' },
    { id: 'A2', title: '2Y series', description: 'Tool · 校验 2Y 序列' },
    { id: 'A10', title: '10Y series', description: 'Tool · 校验 10Y 序列' },
    { id: 'J1', title: 'Join', description: '两个分支均成功才放行' },
    NODES[4],
    { id: 'O1', title: 'Outbox dispatcher', description: '持久化命令 · 重试 · 幂等 Sink' },
    { id: 'LG1', title: 'Paper Ledger', description: '事件写入 · 重放 · P&L 对账' },
    NODES[5]
  ];
  const PARALLEL_ROWS = [['G1'], ['RG1'], ['CG1'], ['TG1'], ['CT1'], ['MR1'], ['M1'], ['P1'], ['R1'], ['L1'], ['H1'], ['AZ1'], ['C1'], ['D1'], ['V1'], ['Q1'], ['A2', 'A10'], ['J1'], ['S1'], ['O1'], ['LG1'], ['E1']];
  const ORCHESTRATION_NODES = [
    NODES[0],
    { id: 'OS1', title: 'Orchestrator', description: '分配 · 退回 · 重分配 · 停止' },
    NODES[1],
    { id: 'L1', title: 'Risk review', description: '独立限额验证 · 不改写策略' },
    { id: 'R1', title: 'Paper Runtime', description: '只映射已批准固定任务图' },
    NODES[5],
  ];
  const ORCHESTRATION_ROWS = ORCHESTRATION_NODES.map(node => [node.id]);
  const DECOMPOSITION_NODES = [
    NODES[0], { id: 'DG1', title: 'Decomposer', description: '目标 → 有类型的动态子任务' },
    { id: 'GV1', title: 'Graph validator', description: '引用完整 · 无环 · 先验约' },
    { id: 'W1', title: 'Curve worker', description: '2Y/10Y 证据与利差' },
    { id: 'W2', title: 'Regime worker', description: '市场状态分析' },
    { id: 'W3', title: 'Stress worker', description: '纸面风险边界' },
    { id: 'J1', title: 'Dynamic join', description: '3/3 类型输出才放行' },
    { id: 'SY1', title: 'Synthesizer', description: '汇总为纸面研究简报' }, NODES[5],
  ];
  const DECOMPOSITION_ROWS = [['G1'], ['DG1'], ['GV1'], ['W1', 'W2', 'W3'], ['J1'], ['SY1'], ['E1']];
  const AGENT_TOOL_NODES = [
    NODES[0], { id: 'MG1', title: 'Manager', description: '保留控制权与最终回答权' },
    { id: 'AT1', title: 'Curve specialist', description: 'Agent-as-Tool · 只分析曲线' },
    { id: 'AT2', title: 'Risk specialist', description: 'Agent-as-Tool · 只检查限额' },
    { id: 'J1', title: 'Tool results', description: '结构化结果回到 Manager' },
    { id: 'R1', title: 'Paper Runtime', description: '仅接收 Manager 的已验约提议' }, NODES[5],
  ];
  const AGENT_TOOL_ROWS = [['G1'], ['MG1'], ['AT1', 'AT2'], ['J1'], ['R1'], ['E1']];
  const OBSERVABILITY_NODES = [
    NODES[0], { id: 'TR1', title: 'Root trace', description: 'Trace ID · 隐私采集策略' },
    { id: 'SP1', title: 'Plan span', description: '父子关系 · latency · tokens' },
    { id: 'SP2', title: 'Curve span', description: '父子关系 · latency · tokens' },
    { id: 'SP3', title: 'Risk span', description: '父子关系 · latency · tokens' },
    { id: 'SLO1', title: 'SLO gate', description: '延迟 · token · 副作用门禁' },
    { id: 'R1', title: 'Paper Runtime', description: 'SLO 通过后才激活' }, NODES[5],
  ];
  const OBSERVABILITY_ROWS = [['G1'], ['TR1'], ['SP1', 'SP2', 'SP3'], ['SLO1'], ['R1'], ['E1']];
  const DURABLE_NODES = [
    NODES[0], { id: 'DW1', title: 'Durable workflow', description: '版本绑定的多 Agent 运行' },
    { id: 'CP1', title: 'Checkpoint', description: '原子提交 · fsync · 输出收据' },
    { id: 'RV1', title: 'Resume validator', description: 'Run · 图版本 · 输入指纹 · Guardrail' },
    { id: 'W1', title: 'Restored W1', description: '从 Checkpoint 恢复 · 不重跑' },
    { id: 'W2', title: 'Restored W2', description: '从 Checkpoint 恢复 · 不重跑' },
    { id: 'W3', title: 'Resumed W3', description: '只继续未完成任务' },
    { id: 'J1', title: 'Recovery join', description: '恢复与新结果全部到齐' },
    { id: 'RC1', title: 'Recovery terminal', description: '完成或拒绝旧 Checkpoint' }, NODES[5],
  ];
  const DURABLE_ROWS = [['G1'], ['DW1'], ['CP1'], ['RV1'], ['W1', 'W2', 'W3'], ['J1'], ['RC1'], ['E1']];
  const SAGA_NODES = [
    NODES[0], { id: 'SG1', title: 'Saga coordinator', description: '正向步骤与补偿契约' },
    { id: 'F1', title: 'Reserve risk', description: '纸面风险额度' },
    { id: 'F2', title: 'Create intent', description: '追加纸面意图' },
    { id: 'F3', title: 'Ledger write', description: '教学故障点' },
    { id: 'C2', title: 'Compensate intent', description: '追加补偿记录' },
    { id: 'C1', title: 'Release risk', description: '恢复纸面风险额度' },
    { id: 'RC1', title: 'Reconcile', description: 'COMPENSATED 或人工介入' }, NODES[5],
  ];
  const SAGA_ROWS = SAGA_NODES.map(node => [node.id]);
  const RELEASE_NODES = [
    NODES[0], { id: 'RB1', title: 'Release bundle', description: 'Model · Prompt · Graph · Policy' },
    { id: 'GE1', title: 'Golden gate', description: '行为合约回归评测' },
    { id: 'SH1', title: 'Shadow', description: '同输入 · 0% 结果权限' },
    { id: 'CA1', title: '5% Canary', description: '少量纸面 Run 灰度' },
    { id: 'RG1', title: 'Release gate', description: '晋级或自动回滚' }, NODES[5],
  ];
  const RELEASE_ROWS = RELEASE_NODES.map(node => [node.id]);
  const STUDIO_ROLES = [
    {
      id: 'orchestration_supervisor', name: '编排主管', type: '确定性 Supervisor', icon: 'S',
      tasks: ['OS1', 'DG1', 'SY1', 'MG1', 'DW1', 'SG1'],
      mission: '分配、退回、重分配或停止有界任务',
      input: 'Goal · Task Result · Worker Health', output: 'orchestration_decision_v1',
      functions: ['选择下一责任人', '跟踪 Revision 与 Token 预算', '检测循环和超时'],
      constraints: ['不能改写策略', '不能批准风险', '不能执行 Tool 或扩大权限'],
      idle: '等待可编排的 2s10s 目标',
    },
    {
      id: 'strategy_analyst', name: '策略分析师', type: 'LLM + 规则', icon: 'A',
      tasks: ['G1', 'RG1', 'CT1', 'MR1', 'M1', 'P1', 'D1', 'A2', 'A10', 'J1', 'S1', 'W1', 'W2', 'AT1'],
      mission: '研究 2s10s，并提出有证据的纸面策略',
      input: '目标 · DGS2/DGS10 · Context', output: 'strategy_handoff_v1',
      functions: ['解释数据', '生成策略提议', '绑定 Evidence IDs'],
      constraints: ['不能批准自己的提议', '不能选择 Runtime Tool', '不能下真实订单'],
      idle: '等待目标和已验证数据',
    },
    {
      id: 'risk_controller', name: '风险主管', type: '确定性规则', icon: 'R',
      tasks: ['CG1', 'TG1', 'H1', 'AZ1', 'C1', 'V1', 'Q1', 'E1', 'GV1', 'W3', 'AT2', 'SLO1', 'RV1', 'F1', 'GE1', 'RG1'],
      mission: '独立验约，只决定 ALLOW 或 BLOCK',
      input: 'strategy_handoff_v1', output: 'risk_handoff_v1 / REJECT',
      functions: ['检查 Schema 与路由', '核对证据和 Hash', '执行 Paper-only 门禁'],
      constraints: ['不能改写策略', '不能执行 Tool', '拒绝时副作用必须为 0'],
      idle: '等待分析师交接',
    },
    {
      id: 'runtime_supervisor', name: '执行主管', type: 'Runtime', icon: 'E',
      tasks: ['R1', 'L1', 'O1', 'LG1', 'TR1', 'SP1', 'SP2', 'SP3', 'CP1', 'F2', 'F3', 'C2', 'SH1', 'CA1', 'RC1'],
      mission: '只把已批准合约映射到固定纸面任务图',
      input: 'risk_handoff_v1', output: 'runtime_decision_v1 · Trace',
      functions: ['重新验证交接', '映射固定 DAG', '持久化完整终态'],
      constraints: ['paper_only=true', 'automatic_execution=false', '不能修改批准的 Payload'],
      idle: '等待风险主管放行',
    },
  ];
  const RISK_EVENT = /(citation|taint|injection|capability|approval|permission|privacy|memory_write_blocked|handoff_validation|handoff_rejected|authority_violation|scope_rejected|graph_rejected|checkpoint_binding|stale_checkpoint|compensation_failed|reconciliation_required|canary_gate|rolled_back|slo_|safe_stop|loop_detected|orchestration_stopped|circuit|admission|backpressure|rate_limit|lease|fence|portfolio_fill|ledger_mismatch|eval_)/;
  const DECISION_EVENT = /(orchestration|task_graph|dynamic_|manager_|agent_tool|durable_|checkpoint_|task_restored|unfinished_task|resume_|recovery_|saga_|compensation_|release_|shadow_|canary_|task_ownership|task_returned|model_intent|model_plan|model_regression|intent_validation|plan_validation|plan_created|plan_revised|replan|route_|routing|agent_role|handoff_contract|handoff_accepted|join_|run_completed)/;
  function flowForEvent(event) {
    const name = event?.event || '';
    if (RISK_EVENT.test(name)) return 'risk';
    if (DECISION_EVENT.test(name)) return 'decision';
    return 'information';
  }
  function roleForEvent(event) {
    if (STUDIO_ROLES.some(role => role.id === event?.actor_role)) return event.actor_role;
    const task = event?.task_id;
    if (event?.event === 'model_response_received') return 'strategy_analyst';
    const role = STUDIO_ROLES.find(candidate => candidate.tasks.includes(task));
    return role?.id || 'runtime_supervisor';
  }
  function handoffForEvent(event) {
    const name = event?.event || '';
    const flow = flowForEvent(event);
    if (name === 'goal_received') return { from: '你', to: /^(orchestration_|decomposition_|agent_tool_)/.test(String(event.scenario || '')) ? 'orchestration_supervisor' : 'strategy_analyst', flow, title: '提交 2s10s 教学目标' };
    if (name === 'task_graph_proposed') return { from: 'orchestration_supervisor', to: 'risk_controller', flow: 'decision', title: '提交动态任务图验约' };
    if (name === 'task_graph_validated') return { from: 'risk_controller', to: 'runtime_supervisor', flow: 'risk', title: '任务图无环，可以派发 Worker' };
    if (name === 'task_graph_rejected') return { from: 'risk_controller', to: 'orchestration_supervisor', flow: 'risk', title: '任务图有环，Worker 派发为零' };
    if (name === 'dynamic_worker_dispatched') return { from: 'orchestration_supervisor', to: event.actor_role, flow: 'decision', title: `派发 ${event.task_id} 类型任务` };
    if (name === 'dynamic_worker_completed') return { from: event.actor_role, to: 'runtime_supervisor', flow: 'information', title: `${event.task_id} 返回 ${event.output_type}` };
    if (name === 'manager_control_started') return { from: '你', to: 'orchestration_supervisor', flow: 'decision', title: 'Manager 接管最终回答权' };
    if (name === 'agent_tool_call_started') return { from: 'orchestration_supervisor', to: event.actor_role, flow: 'decision', title: `调用专家 ${event.tool_name}` };
    if (name === 'agent_tool_result_received') return { from: event.actor_role, to: 'orchestration_supervisor', flow: 'information', title: `${event.tool_name} 返回结构化结果` };
    if (name === 'agent_tool_scope_rejected') return { from: event.actor_role, to: 'orchestration_supervisor', flow: 'risk', title: '专家越权请求被拒绝' };
    if (name === 'span_completed') return { from: 'runtime_supervisor', to: 'risk_controller', flow: 'information', title: `${event.span_name} 指标已上报` };
    if (name === 'slo_evaluation_completed') return { from: 'risk_controller', to: event.passed ? 'runtime_supervisor' : '你', flow: 'risk', title: event.passed ? 'SLO 门禁通过' : 'SLO 门禁拒绝运行' };
    if (name === 'checkpoint_committed') return { from: 'runtime_supervisor', to: 'runtime_supervisor', flow: 'information', title: '原子提交恢复点' };
    if (name === 'checkpoint_binding_validated') return { from: 'runtime_supervisor', to: 'risk_controller', flow: 'risk', title: event.passed ? 'Checkpoint 绑定有效' : 'Checkpoint 已过期' };
    if (name === 'task_restored_from_checkpoint') return { from: 'runtime_supervisor', to: 'orchestration_supervisor', flow: 'information', title: `${event.task_id} 从收据恢复，不重跑 Tool` };
    if (name === 'unfinished_task_resumed') return { from: 'orchestration_supervisor', to: event.actor_role, flow: 'decision', title: `只恢复未完成任务 ${event.task_id}` };
    if (name === 'saga_step_failed') return { from: event.actor_role, to: 'orchestration_supervisor', flow: 'risk', title: '正向步骤失败，启动逆序补偿' };
    if (name === 'compensation_applied') return { from: event.actor_role, to: 'orchestration_supervisor', flow: 'decision', title: `补偿完成：${event.action}` };
    if (name === 'compensation_failed') return { from: event.actor_role, to: '你', flow: 'risk', title: '补偿失败，需要人工对账' };
    if (name === 'shadow_comparison_completed') return { from: 'runtime_supervisor', to: 'risk_controller', flow: 'information', title: 'Shadow 指标交付 Release Gate' };
    if (name === 'canary_gate_evaluated') return { from: 'risk_controller', to: 'orchestration_supervisor', flow: 'risk', title: event.passed ? 'Canary 可以晋级' : 'Canary 必须回滚' };
    if (name === 'release_promoted' || name === 'release_rolled_back') return { from: 'orchestration_supervisor', to: '你', flow: 'decision', title: name === 'release_promoted' ? 'Candidate 晋级为 Active' : '流量切回 Current' };
    if (name === 'orchestration_started') return { from: '你', to: 'orchestration_supervisor', flow: 'decision', title: '启动有界编排策略' };
    if (name === 'orchestration_decision_recorded') return { from: 'orchestration_supervisor', to: event.to_owner || '你', flow, title: `${event.action} · ${event.reason}` };
    if (name === 'task_ownership_changed') return { from: event.from_owner || 'orchestration_supervisor', to: event.assignee_role, flow: 'decision', title: `任务所有权 v${event.ownership_version}` };
    if (name === 'task_returned_for_revision') return { from: 'risk_controller', to: 'strategy_analyst', flow: 'decision', title: `退回修改 · revision ${event.revision}` };
    if (name === 'agent_timeout_detected') return { from: event.actor_role, to: 'orchestration_supervisor', flow: 'risk', title: 'Worker 超时且没有提交输出' };
    if (name === 'orchestration_loop_detected') return { from: 'orchestration_supervisor', to: '你', flow: 'risk', title: '重复退回循环已被停止' };
    if (name === 'orchestration_authority_violation_detected') return { from: event.actor_role, to: 'orchestration_supervisor', flow: 'risk', title: '越权请求被编排层阻断' };
    if (name === 'context_pack_created' || name === 'model_request_started') return { from: '系统设施', to: 'strategy_analyst', flow: 'information', title: name === 'context_pack_created' ? '交付 Context Pack' : '调用受限 LLM 能力' };
    if (name === 'model_response_received') return { from: 'LLM 能力', to: 'strategy_analyst', flow: 'information', title: '返回未经信任的模型输出' };
    if (['model_intent_accepted', 'model_plan_accepted'].includes(name)) return { from: 'strategy_analyst', to: 'risk_controller', flow: 'decision', title: '提交结构化策略提议' };
    if (name === 'model_repair_requested') return { from: 'risk_controller', to: 'strategy_analyst', flow: 'decision', title: '退回并请求一次有界修复' };
    if (name === 'plan_created') return { from: 'strategy_analyst', to: 'risk_controller', flow: 'decision', title: '提交固定 2s10s 任务图' };
    if (name === 'tool_execution_started' || name === 'tool_observation') return { from: 'runtime_supervisor', to: 'strategy_analyst', flow: 'information', title: name === 'tool_execution_started' ? `调用 ${event.tool_name || 'Tool'}` : `返回 ${event.tool_name || 'Tool'} Observation` };
    if (name === 'human_approval_requested') return { from: 'risk_controller', to: '你', flow: 'risk', title: '请求一次人工批准' };
    if (name === 'human_approval_resolved') return { from: '你', to: 'risk_controller', flow: 'risk', title: `人工决定：${event.decision || '已提交'}` };
    if (name === 'handoff_validation_started') return { from: event.sender_role, to: event.actor_role, flow: 'risk', title: '接收方开始独立验证交接' };
    if (name === 'handoff_validation_completed') return { from: 'Contract Gate', to: event.actor_role, flow: 'risk', title: event.passed ? '所有交接规则通过' : '交接规则不通过' };
    if (name === 'handoff_contract_created') return event.recipient_role === 'risk_controller'
      ? { from: 'strategy_analyst', to: 'risk_controller', flow: 'decision', title: '发送 strategy_handoff_v1' }
      : { from: 'risk_controller', to: 'runtime_supervisor', flow: 'decision', title: '发送 risk_handoff_v1' };
    if (name === 'handoff_accepted') return { from: event.sender_role, to: event.actor_role, flow: 'decision', title: '接收方验约后接受交接' };
    if (name === 'handoff_rejected') return { from: event.actor_role, to: event.sender_role, flow: 'risk', title: '拒绝越权交接；下游未激活' };
    if (RISK_EVENT.test(name) && /(completed|rejected|blocked|verified|detected|resolved)/.test(name)) return { from: 'risk_controller', to: 'runtime_supervisor', flow: 'risk', title: name.replaceAll('_', ' ') };
    if (name === 'ledger_event_appended') return { from: 'runtime_supervisor', to: 'risk_controller', flow: 'information', title: `纸面事件已持久化：${event.event_type || 'event'}` };
    if (name === 'ledger_reconciliation_completed') return { from: 'runtime_supervisor', to: 'risk_controller', flow: 'risk', title: event.passed ? '重放对账通过' : '重放对账失败' };
    if (name === 'golden_trace_loaded') return { from: 'runtime_supervisor', to: 'risk_controller', flow: 'information', title: '载入已批准的 Golden Trace' };
    if (name === 'short_term_memory_created') return { from: '你', to: 'strategy_analyst', flow: 'information', title: '创建本次 Run 的短期状态' };
    if (name === 'privacy_redaction_completed') return { from: 'strategy_analyst', to: 'risk_controller', flow: 'risk', title: '长期写入前完成隐私脱敏' };
    if (name === 'long_term_memory_written') return { from: 'risk_controller', to: 'runtime_supervisor', flow: 'information', title: '批准写入脱敏长期记忆' };
    if (name === 'long_term_memory_retrieved') return { from: 'runtime_supervisor', to: 'strategy_analyst', flow: 'information', title: '按 Scope 召回有来源的记忆' };
    if (name === 'memory_write_blocked') return { from: 'risk_controller', to: 'runtime_supervisor', flow: 'risk', title: '敏感长期写入被阻断，副作用为零' };
    if (name === 'run_completed') return { from: event.lesson === 'orchestration' ? 'orchestration_supervisor' : 'runtime_supervisor', to: '你', flow: 'decision', title: '交付完整运行终态' };
    return null;
  }
  function modeForScenario(scenario = '') {
    const value = String(scenario);
    if (value.startsWith('decomposition_')) return 'decomposition';
    if (value.startsWith('agent_tool_')) return 'agent_tool';
    if (value.startsWith('observability_')) return 'observability';
    if (value.startsWith('durable_')) return 'durable';
    if (value.startsWith('saga_')) return 'saga';
    if (value.startsWith('release_')) return 'release';
    return value.startsWith('orchestration_') ? 'orchestration' : 'parallel';
  }
  function createState(mode = 'serial') {
    const graphs = { parallel: PARALLEL_NODES, orchestration: ORCHESTRATION_NODES,
      decomposition: DECOMPOSITION_NODES, agent_tool: AGENT_TOOL_NODES,
      observability: OBSERVABILITY_NODES, durable: DURABLE_NODES,
      saga: SAGA_NODES, release: RELEASE_NODES };
    const definitions = graphs[mode] || NODES;
    return { mode, phase: 'idle', runId: null, events: [], nodes: Object.fromEntries(definitions.map(n => [n.id, 'waiting'])), agentStates: Object.fromEntries(STUDIO_ROLES.map(role => [role.id, 'waiting'])), activeTasks: [], activeTask: null, join: { completed: [], waitingFor: ['A2', 'A10'], required: 2 }, approval: null, result: null, error: null, terminal: false, stopConfirmed: false, stopReason: null, cancelSupported: false, budgetMs: null, replayed: false };
  }
  function failState(state, error) {
    const uncertain = state.phase === 'cancelling' && !state.stopConfirmed;
    state.error = typeof error === 'string' ? { message: error } : error;
    state.phase = 'failed';
    state.terminal = true;
    const active = state.error.task_id || state.activeTask;
    if (active in state.nodes) state.nodes[active] = uncertain ? 'unknown' : 'failed';
    if (state.nodes.R1 !== 'waiting') state.nodes.R1 = uncertain ? 'unknown' : 'failed';
    for (const id of Object.keys(state.nodes)) {
      if (state.nodes[id] === 'cancelling') state.nodes[id] = 'unknown';
      if (['waiting', 'ready', 'running'].includes(state.nodes[id])) state.nodes[id] = 'blocked';
    }
    state.activeTasks = [];
    state.activeTask = null;
    return state;
  }
  function applyEvent(state, event) {
    if (!event || event.run_id !== state.runId || event.sequence !== state.events.length + 1 || typeof event.event !== 'string' || !Number.isFinite(Date.parse(event.timestamp))) throw new Error('事件序号、时间或 run_id 不匹配，流已中断。');
    state.events.push(event);
    const id = event.task_id;
    switch (event.event) {
      case 'goal_received': state.nodes.G1 = 'completed'; break;
      case 'orchestration_started':
        state.nodes.OS1 = 'running';
        if (event.actor_role in state.agentStates) state.agentStates[event.actor_role] = 'active';
        break;
      case 'task_envelope_created': state.nodes.OS1 = 'proposed'; break;
      case 'orchestration_decision_recorded': state.nodes.OS1 = event.action === 'STOP' ? 'abstained' : 'running'; break;
      case 'task_ownership_changed': state.nodes.OS1 = 'running'; break;
      case 'orchestration_budget_updated': state.nodes.OS1 = 'running'; break;
      case 'task_ownership_revoked': state.nodes.OS1 = 'verifying'; break;
      case 'agent_timeout_detected':
        if (id in state.nodes) state.nodes[id] = 'timed_out';
        if (event.actor_role in state.agentStates) state.agentStates[event.actor_role] = 'failed';
        break;
      case 'agent_task_started':
        if (id in state.nodes) state.nodes[id] = 'running';
        if (event.actor_role in state.agentStates) state.agentStates[event.actor_role] = 'active';
        break;
      case 'agent_task_completed':
        if (id in state.nodes) state.nodes[id] = 'completed';
        if (event.actor_role in state.agentStates) state.agentStates[event.actor_role] = 'completed';
        break;
      case 'risk_review_completed':
        state.nodes.L1 = event.approved ? 'completed' : 'rejected';
        state.agentStates.risk_controller = event.approved ? 'completed' : 'rejected';
        break;
      case 'task_returned_for_revision': state.nodes.OS1 = 'replan'; break;
      case 'orchestration_loop_detected': state.nodes.OS1 = 'budget_blocked'; break;
      case 'orchestration_authority_violation_detected': state.nodes.OS1 = 'rejected'; break;
      case 'paper_runtime_mapped':
        state.nodes.R1 = 'completed';
        state.agentStates.runtime_supervisor = 'completed';
        break;
      case 'orchestration_stopped': state.nodes.OS1 = 'abstained'; break;
      case 'task_graph_proposed': state.nodes.DG1 = 'completed'; state.nodes.GV1 = 'ready'; break;
      case 'task_graph_validation_started': state.nodes.GV1 = 'verifying'; break;
      case 'task_graph_validated': state.nodes.GV1 = 'completed'; break;
      case 'task_graph_rejected':
        state.nodes.GV1 = 'rejected';
        for (const worker of ['W1', 'W2', 'W3', 'J1', 'SY1']) if (worker in state.nodes) state.nodes[worker] = 'blocked';
        break;
      case 'dynamic_worker_dispatched': state.nodes[id] = 'running'; state.agentStates[event.actor_role] = 'active'; break;
      case 'dynamic_worker_completed': state.nodes[id] = 'completed'; state.agentStates[event.actor_role] = 'completed'; break;
      case 'dynamic_join_released': state.nodes.J1 = 'completed'; break;
      case 'dynamic_synthesis_completed': state.nodes.SY1 = 'completed'; break;
      case 'manager_control_started': state.nodes.MG1 = 'running'; state.agentStates.orchestration_supervisor = 'active'; break;
      case 'agent_tool_registered': state.nodes.MG1 = 'ready'; break;
      case 'agent_tool_call_started': state.nodes[id] = 'running'; state.agentStates[event.actor_role] = 'active'; break;
      case 'agent_tool_result_received':
        state.nodes[id] = 'completed';
        state.agentStates[event.actor_role] = 'completed';
        if (['AT1', 'AT2'].every(task => !(task in state.nodes) || state.nodes[task] === 'completed')) state.nodes.J1 = 'completed';
        break;
      case 'agent_tool_scope_rejected': state.nodes[id] = 'rejected'; state.nodes.J1 = 'blocked'; state.nodes.R1 = 'blocked'; state.agentStates[event.actor_role] = 'rejected'; break;
      case 'manager_synthesis_completed': state.nodes.MG1 = 'completed'; break;
      case 'manager_run_stopped': state.nodes.MG1 = 'abstained'; break;
      case 'trace_root_started': state.nodes.TR1 = 'running'; state.agentStates.runtime_supervisor = 'active'; break;
      case 'span_started': state.nodes[id] = 'running'; break;
      case 'span_completed': state.nodes[id] = 'completed'; break;
      case 'telemetry_aggregated': state.nodes.TR1 = 'completed'; state.nodes.SLO1 = 'ready'; break;
      case 'slo_evaluation_started': state.nodes.SLO1 = 'verifying'; break;
      case 'slo_evaluation_completed': state.nodes.SLO1 = event.passed ? 'completed' : 'rejected'; break;
      case 'slo_breach_detected': state.nodes.SLO1 = 'rejected'; state.nodes.R1 = 'blocked'; break;
      case 'observability_safe_stop': state.nodes.SLO1 = 'abstained'; break;
      case 'durable_run_started': state.nodes.DW1 = 'running'; break;
      case 'durable_task_completed': state.nodes[id] = 'completed'; break;
      case 'checkpoint_committed': state.nodes.CP1 = 'completed'; break;
      case 'runtime_interrupted': state.nodes.CP1 = 'failed'; break;
      case 'run_paused_for_restart': state.nodes.DW1 = 'paused'; state.nodes.CP1 = 'paused'; state.nodes.RV1 = 'ready'; break;
      case 'resume_requested': state.nodes.RV1 = 'running'; break;
      case 'checkpoint_loaded': state.nodes.RV1 = 'verifying'; break;
      case 'checkpoint_binding_validated': state.nodes.RV1 = event.passed ? 'completed' : 'rejected'; break;
      case 'stale_checkpoint_rejected':
        state.nodes.RV1 = 'rejected';
        for (const task of ['W1', 'W2', 'W3', 'J1', 'RC1']) state.nodes[task] = 'blocked';
        break;
      case 'task_restored_from_checkpoint': state.nodes[id] = 'completed'; break;
      case 'unfinished_task_resumed': state.nodes[id] = 'running'; break;
      case 'resume_join_released': state.nodes.J1 = 'completed'; break;
      case 'recovery_completed': state.nodes.RC1 = 'completed'; state.nodes.DW1 = 'completed'; break;
      case 'saga_started': state.nodes.SG1 = 'running'; break;
      case 'saga_step_applied': state.nodes[id] = 'completed'; break;
      case 'saga_step_failed': state.nodes[id] = 'failed'; break;
      case 'compensation_started': state.nodes.C2 = 'running'; break;
      case 'compensation_applied': state.nodes[id] = 'completed'; break;
      case 'compensation_failed': state.nodes[id] = 'failed'; break;
      case 'saga_compensated': state.nodes.RC1 = 'completed'; state.nodes.SG1 = 'completed'; break;
      case 'reconciliation_required': state.nodes.RC1 = 'waiting_human'; state.nodes.SG1 = 'abstained'; break;
      case 'release_bundle_created': state.nodes.RB1 = 'completed'; break;
      case 'release_golden_eval_completed': state.nodes.GE1 = event.passed ? 'completed' : 'rejected'; break;
      case 'shadow_run_started': state.nodes.SH1 = 'running'; break;
      case 'shadow_comparison_completed': state.nodes.SH1 = event.passed ? 'completed' : 'rejected'; break;
      case 'canary_started': state.nodes.CA1 = 'running'; break;
      case 'canary_gate_evaluated': state.nodes.RG1 = event.passed ? 'ready' : 'rejected'; break;
      case 'canary_allocation_stopped': state.nodes.CA1 = 'abstained'; break;
      case 'release_promoted': state.nodes.RG1 = 'completed'; break;
      case 'release_rolled_back': state.nodes.RG1 = 'completed'; break;
      case 'retrieval_bypassed': state.nodes.RG1 = 'completed'; break;
      case 'retrieval_query_created': state.nodes.RG1 = 'retrieving'; break;
      case 'retrieval_candidate_scored': state.nodes.RG1 = 'ranking'; break;
      case 'retrieval_topk_selected': state.nodes.RG1 = 'topk'; break;
      case 'retrieval_completed': state.nodes.RG1 = 'completed'; break;
      case 'citation_gate_bypassed': state.nodes.CG1 = 'completed'; break;
      case 'citation_gate_started': state.nodes.CG1 = 'verifying'; break;
      case 'citation_checked': state.nodes.CG1 = event.passed ? 'verifying' : 'rejected'; break;
      case 'citation_gate_completed': state.nodes.CG1 = event.passed ? 'completed' : 'failed'; break;
      case 'taint_guard_bypassed': state.nodes.TG1 = 'completed'; break;
      case 'taint_guard_started': state.nodes.TG1 = 'scanning'; break;
      case 'retrieved_content_inspected': state.nodes.TG1 = event.tainted ? 'quarantining' : 'scanning'; break;
      case 'taint_guard_completed': state.nodes.TG1 = event.passed ? 'completed' : 'failed'; break;
      case 'capability_bypassed': state.nodes.AZ1 = 'completed'; break;
      case 'capability_policy_started': state.nodes.AZ1 = 'issuing'; break;
      case 'capability_minted': state.nodes.AZ1 = 'issued'; break;
      case 'capability_check_started': state.nodes.AZ1 = 'authorizing'; break;
      case 'capability_verified': state.nodes.AZ1 = 'verified'; break;
      case 'capability_consumed': state.nodes.AZ1 = 'completed'; break;
      case 'capability_rejected': state.nodes.AZ1 = 'failed'; break;
      case 'human_approval_bypassed': state.nodes.H1 = 'completed'; break;
      case 'human_approval_requested':
        state.nodes.H1 = 'waiting_human';
        state.approval = { ...event, pending: true };
        break;
      case 'human_approval_resolved':
        state.nodes.H1 = event.decision === 'approve' ? 'approved' : 'failed';
        state.approval = { ...(state.approval || {}), ...event, pending: false };
        break;
      case 'permission_elevation_approved': state.nodes.H1 = 'completed'; break;
      case 'approval_checkpoint_saved': state.nodes.H1 = 'waiting_human'; break;
      case 'approval_runtime_restarted': state.nodes.H1 = 'restarting'; break;
      case 'approval_checkpoint_loaded': state.nodes.H1 = 'restoring'; break;
      case 'approval_binding_validated': state.nodes.H1 = event.passed ? 'approved' : 'failed'; break;
      case 'context_bypassed': state.nodes.CT1 = 'completed'; break;
      case 'context_collection_started': state.nodes.CT1 = 'running'; break;
      case 'context_item_scored': state.nodes.CT1 = 'selecting'; break;
      case 'context_item_selected': state.nodes.CT1 = 'selecting'; break;
      case 'context_item_compressed': state.nodes.CT1 = 'compressing'; break;
      case 'context_item_dropped': state.nodes.CT1 = 'selecting'; break;
      case 'context_pack_created': state.nodes.CT1 = 'completed'; break;
      case 'model_routing_bypassed': state.nodes.MR1 = 'completed'; break;
      case 'model_routing_started': state.nodes.MR1 = 'running'; break;
      case 'model_route_selected': state.nodes.MR1 = 'selected'; break;
      case 'model_budget_reserved': state.nodes.MR1 = 'reserved'; break;
      case 'model_provider_failed':
        state.nodes.M1 = 'failed';
        break;
      case 'model_fallback_requested': state.nodes.MR1 = 'fallback'; break;
      case 'model_budget_rejected': state.nodes.MR1 = 'budget_blocked'; break;
      case 'model_route_abstained': state.nodes.MR1 = 'failed'; break;
      case 'model_route_completed': state.nodes.MR1 = 'completed'; break;
      case 'model_bypassed': state.nodes.M1 = 'completed'; break;
      case 'model_request_started': state.nodes.M1 = 'running'; break;
      case 'model_response_received': state.nodes.M1 = 'proposed'; break;
      case 'model_repair_requested': state.nodes.M1 = 'repairing'; break;
      case 'intent_parse_started': state.nodes.P1 = 'running'; break;
      case 'intent_parse_failed': state.nodes.P1 = 'repairing'; break;
      case 'model_intent_parsed': state.nodes.P1 = 'running'; break;
      case 'intent_validation_started': state.nodes.P1 = 'running'; break;
      case 'intent_validation_completed': state.nodes.P1 = event.accepted ? 'ready' : 'failed'; break;
      case 'model_intent_accepted':
        state.nodes.M1 = 'completed';
        state.nodes.P1 = event.intent === 'ABSTAIN' ? 'abstained' : 'completed';
        break;
      case 'model_intent_rejected':
      case 'model_intent_abstained':
        state.nodes.M1 = 'completed';
        state.nodes.P1 = 'failed';
        break;
      case 'plan_parse_started': state.nodes.P1 = 'running'; break;
      case 'plan_parse_failed': state.nodes.P1 = 'repairing'; break;
      case 'plan_parsed': state.nodes.P1 = 'running'; break;
      case 'plan_validation_started': state.nodes.P1 = 'running'; break;
      case 'plan_validation_completed': state.nodes.P1 = event.accepted ? 'ready' : 'failed'; break;
      case 'model_plan_accepted':
        state.nodes.M1 = 'completed';
        state.nodes.P1 = 'completed';
        break;
      case 'model_plan_rejected':
        state.nodes.M1 = 'completed';
        state.nodes.P1 = 'failed';
        break;
      case 'golden_trace_loaded': state.nodes.E1 = 'running'; break;
      case 'model_regression_started': state.nodes.E1 = 'running'; break;
      case 'model_eval_assertion_checked': state.nodes.E1 = event.passed ? 'verifying' : 'rejected'; break;
      case 'model_regression_completed': state.nodes.E1 = event.passed ? 'completed' : 'failed'; break;
      case 'short_term_memory_created': state.nodes.CT1 = 'running'; break;
      case 'privacy_redaction_completed': state.nodes.TG1 = event.passed ? 'completed' : 'failed'; break;
      case 'long_term_memory_written': state.nodes.LG1 = 'writing'; break;
      case 'long_term_memory_retrieved': state.nodes.RG1 = 'completed'; state.nodes.LG1 = 'completed'; break;
      case 'memory_write_blocked': state.nodes.TG1 = event.passed ? 'completed' : 'failed'; break;
      case 'short_term_memory_discarded': state.nodes.CT1 = 'completed'; break;
      case 'agent_role_activated':
        if (id in state.nodes) state.nodes[id] = 'running';
        if (event.actor_role in state.agentStates) state.agentStates[event.actor_role] = 'active';
        break;
      case 'handoff_contract_created':
        if (id in state.nodes) state.nodes[id] = 'proposed';
        if (event.actor_role in state.agentStates) state.agentStates[event.actor_role] = 'sending';
        break;
      case 'handoff_validation_started':
        if (id in state.nodes) state.nodes[id] = 'verifying';
        if (event.actor_role in state.agentStates) state.agentStates[event.actor_role] = 'validating';
        break;
      case 'handoff_validation_completed':
        if (id in state.nodes) state.nodes[id] = event.passed ? 'ready' : 'rejected';
        if (event.actor_role in state.agentStates) state.agentStates[event.actor_role] = event.passed ? 'ready' : 'rejected';
        break;
      case 'handoff_accepted':
        if (id in state.nodes) state.nodes[id] = 'completed';
        if (event.sender_role in state.agentStates) state.agentStates[event.sender_role] = 'completed';
        if (event.actor_role in state.agentStates) state.agentStates[event.actor_role] = 'active';
        break;
      case 'handoff_rejected':
        if (id in state.nodes) state.nodes[id] = 'rejected';
        if (event.sender_role in state.agentStates) state.agentStates[event.sender_role] = 'completed';
        if (event.actor_role in state.agentStates) state.agentStates[event.actor_role] = 'rejected';
        break;
      case 'plan_created': state.nodes.P1 = 'completed'; break;
      case 'runtime_started': state.nodes.R1 = 'running'; break;
      case 'lease_bypassed': state.nodes.L1 = 'completed'; break;
      case 'lease_acquire_started': state.nodes.L1 = 'running'; break;
      case 'lease_acquired': state.nodes.L1 = 'acquired'; break;
      case 'lease_renewal_started': state.nodes.L1 = 'renewing'; break;
      case 'lease_renewed': state.nodes.L1 = 'acquired'; break;
      case 'lease_expired': state.nodes.L1 = 'expired'; break;
      case 'lease_takeover_started': state.nodes.L1 = 'taking_over'; break;
      case 'lease_fence_rejected': state.nodes.L1 = 'fenced'; break;
      case 'lease_fence_verified': state.nodes.L1 = 'verified'; break;
      case 'lease_side_effect_blocked': state.nodes.L1 = 'fenced'; break;
      case 'lease_released': state.nodes.L1 = 'completed'; break;
      case 'outbox_bypassed': state.nodes.O1 = 'completed'; break;
      case 'outbox_enqueued': state.nodes.O1 = 'running'; break;
      case 'outbox_dispatch_started': state.nodes.O1 = 'running'; break;
      case 'outbox_ack_lost': state.nodes.O1 = 'retrying'; break;
      case 'outbox_dispatch_rejected': state.nodes.O1 = 'fenced'; break;
      case 'outbox_side_effect_blocked': state.nodes.O1 = 'fenced'; break;
      case 'outbox_effect_applied': state.nodes.O1 = 'writing'; break;
      case 'outbox_effect_deduplicated': state.nodes.O1 = 'deduplicated'; break;
      case 'outbox_acknowledged': state.nodes.O1 = 'writing'; break;
      case 'outbox_completed': state.nodes.O1 = 'completed'; break;
      case 'ledger_replay_started': state.nodes.LG1 = 'running'; break;
      case 'ledger_event_appending':
      case 'ledger_event_appended': state.nodes.LG1 = 'writing'; break;
      case 'ledger_snapshot_rebuilt': state.nodes.LG1 = 'verifying'; break;
      case 'portfolio_snapshot_rebuilt': state.nodes.LG1 = 'verifying'; break;
      case 'portfolio_fill_preflight': state.nodes.LG1 = 'verifying'; break;
      case 'portfolio_fill_blocked': state.nodes.LG1 = 'verifying'; break;
      case 'ledger_reconciliation_started': state.nodes.LG1 = 'verifying'; break;
      case 'ledger_reconciliation_completed': state.nodes.LG1 = event.passed ? 'completed' : 'failed'; break;
      case 'ledger_mismatch_detected': state.nodes.LG1 = 'failed'; break;
      case 'task_started':
      case 'tool_execution_started':
      case 'eval_started':
        if (id in state.nodes) state.nodes[id] = state.phase === 'cancelling' ? 'cancelling' : 'running';
        if (!state.activeTasks.includes(id)) state.activeTasks.push(id);
        state.activeTask = state.activeTasks[0] || null;
        break;
      case 'tool_execution_failed':
        if (id in state.nodes) state.nodes[id] = event.retryable ? 'running' : 'failed';
        break;
      case 'tool_validation':
        if (event.passed === false && id in state.nodes) state.nodes[id] = 'failed';
        break;
      case 'task_completed':
      case 'task_skipped_from_checkpoint':
        if (id in state.nodes) state.nodes[id] = 'completed';
        state.activeTasks = state.activeTasks.filter(task => task !== id);
        state.activeTask = state.activeTasks[0] || null;
        break;
      case 'task_failed':
        if (id in state.nodes) state.nodes[id] = 'failed';
        state.activeTasks = state.activeTasks.filter(task => task !== id);
        state.activeTask = state.activeTasks[0] || null;
        break;
      case 'observation_validation_started': state.nodes.V1 = 'running'; break;
      case 'observation_validation_completed': state.nodes.V1 = event.passed ? 'completed' : 'replan'; break;
      case 'task_invalidated':
        if (id in state.nodes) state.nodes[id] = 'invalidated';
        break;
      case 'replan_requested':
        state.nodes.P1 = 'running';
        state.nodes.V1 = 'replan';
        break;
      case 'plan_revision_registered': state.nodes.P1 = 'completed'; break;
      case 'plan_revised': state.nodes.P1 = 'completed'; break;
      case 'replan_loop_detected': state.nodes.P1 = 'failed'; break;
      case 'replan_budget_exhausted': state.nodes.P1 = 'failed'; break;
      case 'join_waiting':
        state.join = { completed: event.completed_dependencies, waitingFor: event.waiting_for, required: event.required };
        break;
      case 'join_released': state.nodes.J1 = 'ready'; break;
      case 'join_blocked': state.nodes.J1 = 'blocked'; break;
      case 'task_blocked': if (id in state.nodes) state.nodes[id] = 'blocked'; break;
      case 'eval_completed':
        state.nodes.E1 = event.passed ? 'completed' : 'failed';
        state.activeTask = null;
        state.activeTasks = [];
        break;
      case 'run_completed':
        if (state.mode === 'orchestration') {
          state.nodes.OS1 = 'completed';
          if (state.nodes.R1 === 'waiting') state.nodes.R1 = 'blocked';
          state.agentStates.orchestration_supervisor = 'completed';
        } else if (state.mode === 'decomposition') {
          if (state.nodes.SY1 === 'waiting') state.nodes.SY1 = 'blocked';
          state.agentStates.orchestration_supervisor = state.nodes.SY1 === 'completed' ? 'completed' : 'rejected';
        } else if (state.mode === 'agent_tool') {
          if (state.nodes.MG1 !== 'abstained') state.nodes.MG1 = 'completed';
          if (state.nodes.R1 === 'waiting') state.nodes.R1 = 'blocked';
        } else if (state.mode === 'observability') {
          if (state.nodes.R1 === 'waiting') state.nodes.R1 = 'blocked';
        } else if (['durable', 'saga', 'release'].includes(state.mode)) {
          // Their terminal nodes already encode COMPLETE, STOP, ESCALATE, PROMOTE, or ROLLBACK.
        } else {
          state.nodes.R1 = 'completed';
          if (state.agentStates.runtime_supervisor !== 'waiting') state.agentStates.runtime_supervisor = 'completed';
        }
        break;
      case 'run_budget_started': state.budgetMs = event.budget_ms; break;
      case 'circuit_bypassed': state.nodes.C1 = 'completed'; break;
      case 'circuit_call_allowed': state.nodes.C1 = event.state === 'half_open' ? 'half_open' : 'running'; break;
      case 'circuit_failure_recorded': state.nodes.C1 = event.snapshot?.state || 'running'; break;
      case 'circuit_state_changed': state.nodes.C1 = event.to_state === 'closed' ? 'completed' : event.to_state; break;
      case 'circuit_success_recorded': state.nodes.C1 = 'completed'; break;
      case 'circuit_call_rejected': state.nodes.C1 = 'open'; break;
      case 'admission_bypassed': state.nodes.Q1 = 'completed'; break;
      case 'admission_requested': state.nodes.Q1 = 'running'; break;
      case 'rate_limit_granted': state.nodes.Q1 = 'running'; break;
      case 'backpressure_queued': state.nodes.Q1 = 'queued'; break;
      case 'rate_limit_waiting': state.nodes.Q1 = 'throttling'; break;
      case 'backpressure_released': state.nodes.Q1 = 'running'; break;
      case 'admission_rejected': state.nodes.Q1 = 'rejected'; break;
      case 'admission_cycle_completed': state.nodes.Q1 = 'completed'; break;
      case 'cancellation_requested':
        state.phase = 'cancelling';
        state.stopReason = event.reason;
        state.nodes.R1 = 'cancelling';
        for (const task of event.active_tasks) {
          if (task in state.nodes && state.nodes[task] !== 'completed') state.nodes[task] = 'cancelling';
        }
        break;
      case 'task_cancelled':
        if (event.worker_stopped !== true) throw new Error('缺少 Tool 停止确认。');
        if (id in state.nodes) state.nodes[id] = event.reason === 'deadline' ? 'timed_out' : 'cancelled';
        state.activeTasks = state.activeTasks.filter(task => task !== id);
        state.activeTask = state.activeTasks[0] || null;
        break;
      case 'run_stopped':
        if (event.workers_stopped !== true) throw new Error('缺少 Runtime 停止确认。');
        state.stopConfirmed = true;
        state.stopReason = event.reason;
        state.nodes.R1 = event.status;
        break;
    }
  }
  function applyMessage(state, message) {
    if (!message || message.protocol !== 'rate-ndjson-v1' || typeof message.run_id !== 'string' || !message.run_id) throw new Error('无法识别的 Agent stream 协议。');
    if (state.terminal) throw new Error('终态之后仍收到消息。');
    if (message.type === 'start') {
      if (state.runId) throw new Error('重复的 stream start。');
      if (message.execution_mode && message.execution_mode !== state.mode) {
        Object.assign(state, createState(message.execution_mode));
      }
      state.runId = message.run_id;
      state.phase = 'running';
      state.replayed = message.replayed === true;
      state.cancelSupported = message.cancel_supported === true;
      state.budgetMs = message.budget_ms ?? null;
    } else {
      if (!state.runId || message.run_id !== state.runId) throw new Error('流式消息来自不同的运行。');
      if (message.type === 'event') applyEvent(state, message.event);
      else if (message.type === 'result') {
        if (state.stopReason) throw new Error('停止请求后不能接受成功结果。');
        const result = message.result;
        const waitingForRestart = result?.status === 'WAITING_FOR_RESTART';
        const expectedTerminalEvent = waitingForRestart ? 'run_paused_for_restart' : 'run_completed';
        if (!result || result.run_id !== state.runId || !Array.isArray(result.trace) || JSON.stringify(result.trace) !== JSON.stringify(state.events) || state.events.at(-1)?.event !== expectedTerminalEvent) throw new Error('最终结果与已接收的事件流不一致。');
        state.result = result;
        state.phase = waitingForRestart ? 'paused' : result.eval?.passed === true ? 'completed' : 'failed';
        state.terminal = true;
      } else if (message.type === 'error') {
        if (['RUN_CANCELLED', 'RUN_DEADLINE_EXCEEDED'].includes(message.error?.code)) {
          const status = message.error.code === 'RUN_CANCELLED' ? 'cancelled' : 'timed_out';
          if (!state.stopConfirmed || state.events.at(-1)?.event !== 'run_stopped' || state.events.at(-1)?.status !== status) throw new Error('未收到完整停止确认，不能标记已停止。');
          state.phase = status;
          state.terminal = true;
          state.error = message.error;
          state.activeTasks = [];
          state.activeTask = null;
        } else failState(state, message.error || { message: 'Agent 执行失败' });
      } else throw new Error(`未知消息类型：${message.type}`);
    }
    return state;
  }
  function finishStream(state) {
    if (!state.terminal) throw new Error('连接已结束，但未收到最终结果。保留已收到的事件，请重试。');
    return state;
  }
  function describe(event) {
    const common = { kind: 'node', label: 'NODE', title: event.event, description: '', detailLabel: '完整事件', payload: event };
    switch (event.event) {
      case 'goal_received': return { ...common, label: 'INPUT', title: 'Goal received', description: event.goal, detailLabel: '目标与运行参数' };
      case 'task_graph_proposed': return { ...common, kind: 'handoff', label: 'TASK GRAPH', title: `${event.tasks.length} typed tasks · ${event.edges.length} edges`, description: 'Decomposer 只提出拓扑；Graph Validator 通过前不得派发 Worker。', detailLabel: '动态任务与依赖', payload: event };
      case 'task_graph_validation_started': return { ...common, kind: 'security', label: 'GRAPH GATE', title: 'Validate before dispatch', description: event.checks.join(' · '), detailLabel: '图验证规则', payload: event };
      case 'task_graph_validated': return { ...common, kind: 'result', label: 'DAG PASS', title: event.topological_order.join(' → '), description: '引用完整且无环；现在才允许并行派发。', detailLabel: '拓扑排序与检查', payload: event };
      case 'task_graph_rejected': return { ...common, kind: 'error', label: 'CYCLE BLOCK', title: event.reasons.join(' · '), description: `Worker 派发 ${event.workers_dispatched} · 副作用 ${event.effect_count}`, detailLabel: '拒绝的完整任务图', payload: event };
      case 'dynamic_worker_dispatched': return { ...common, kind: 'call', label: 'DYNAMIC WORKER', title: `${event.task_id} → ${event.actor_role}`, description: `${event.task_contract.output} · ${event.input_scope}`, detailLabel: 'Worker 输入输出合约', payload: event };
      case 'dynamic_worker_completed': return { ...common, kind: 'result', label: 'WORKER RESULT', title: `${event.task_id} · ${event.output_type}`, description: '结构化结果返回 Join；Worker 不能自行启动下一任务。', detailLabel: '完整 Worker 输出', payload: event.output };
      case 'dynamic_join_released': return { ...common, kind: 'result', label: '3/3 JOIN', title: event.received.join(' + '), description: '所有必需的类型化结果到齐，Synthesizer 才能运行。', detailLabel: 'Join 条件', payload: event };
      case 'dynamic_synthesis_completed': return { ...common, kind: 'result', label: 'SYNTHESIS', title: 'Paper research brief ready', description: '只汇总为研究提议，不产生订单或自动执行。', detailLabel: '综合结果', payload: event.synthesis };
      case 'manager_control_started': return { ...common, kind: 'handoff', label: 'MANAGER', title: 'Control stays with manager', description: '专家是可调用能力，不接管对话，也不能交付最终答案。', detailLabel: '控制权合约', payload: event };
      case 'agent_tool_registered': return { ...common, kind: 'capability', label: 'AGENT TOOL', title: event.tool.tool_name, description: `${event.tool.input} → ${event.tool.output} · ${event.tool.authority.join(' · ')}`, detailLabel: '专家能力声明', payload: event.tool };
      case 'agent_tool_call_started': return { ...common, kind: 'call', label: 'DELEGATE', title: event.tool_name, description: `Manager 保留控制权 · scope ${event.requested_scope.join(' · ')}`, detailLabel: '委派请求', payload: event };
      case 'agent_tool_result_received': return { ...common, kind: 'result', label: 'RETURN TO MANAGER', title: `${event.tool_name} · ${event.output_schema}`, description: '专家结果回到 Manager，不能直接进入 Runtime。', detailLabel: '结构化专家输出', payload: event.output };
      case 'agent_tool_scope_rejected': return { ...common, kind: 'error', label: 'SCOPE BLOCK', title: `${event.tool_name} cannot ${event.requested_action}`, description: `允许：${event.allowed_actions.join(' · ')} · 副作用 ${event.effect_count}`, detailLabel: '越权请求', payload: event };
      case 'manager_synthesis_completed': return { ...common, kind: 'result', label: 'MANAGER SYNTHESIS', title: event.sources.join(' + '), description: 'Manager 组合专家结果并承担最终提议责任。', detailLabel: 'Manager 输出', payload: event.proposal };
      case 'manager_run_stopped': return { ...common, kind: 'error', label: 'SAFE STOP', title: event.reason, description: `Manager 保留控制并停止 · 副作用 ${event.effect_count}`, detailLabel: '停止终态', payload: event };
      case 'trace_root_started': return { ...common, kind: 'observability', label: 'ROOT TRACE', title: event.trace_id, description: '只采集结构化指标；Prompt 与 Secret 均不进入 Trace。', detailLabel: 'Trace 与隐私策略', payload: event };
      case 'span_started': return { ...common, kind: 'observability', label: 'SPAN START', title: event.span_name, description: `${event.span_id} ← ${event.parent_span_id}`, detailLabel: 'Span 上下文', payload: event };
      case 'span_completed': return { ...common, kind: 'observability', label: 'SPAN END', title: event.span_name, description: `${event.latency_ms}ms · ${event.tokens} tokens · content captured=${event.content_captured}`, detailLabel: 'Span 指标', payload: event };
      case 'telemetry_aggregated': return { ...common, kind: 'observability', label: 'METRICS', title: `${event.metrics.span_count} spans aggregated`, description: `p95 ${event.metrics.p95_latency_ms}ms · ${event.metrics.tokens_used} tokens · effects ${event.metrics.effect_count}`, detailLabel: '聚合指标', payload: event.metrics };
      case 'slo_evaluation_started': return { ...common, kind: 'security', label: 'SLO GATE', title: 'Operational policy check', description: `p95 ≤ ${event.policy.p95_latency_ms_max}ms · tokens ≤ ${event.policy.token_budget_max}`, detailLabel: 'SLO 策略', payload: event.policy };
      case 'slo_evaluation_completed': return { ...common, kind: event.passed ? 'result' : 'error', label: event.passed ? 'SLO PASS' : 'SLO BREACH', title: event.passed ? 'Runtime may activate' : 'Runtime remains blocked', description: Object.entries(event.checks).map(([key, ok]) => `${ok ? '✓' : '✕'} ${key}`).join(' · '), detailLabel: 'SLO 检查', payload: event };
      case 'slo_breach_detected': return { ...common, kind: 'error', label: 'BREACH', title: event.failed_metrics.join(' · '), description: `违反运行政策 · 副作用 ${event.effect_count}`, detailLabel: '超标指标', payload: event };
      case 'observability_safe_stop': return { ...common, kind: 'error', label: 'SAFE STOP', title: event.reason, description: `Paper Runtime 未激活 · 副作用 ${event.effect_count}`, detailLabel: '停止终态', payload: event };
      case 'durable_run_started': return { ...common, kind: 'durable', label: 'DURABLE RUN', title: event.graph_version, description: `任务：${event.tasks.join(' · ')}；完成状态必须先持久化才能恢复。`, detailLabel: '运行身份', payload: event };
      case 'durable_task_completed': return { ...common, kind: 'result', label: 'COMMITTED OUTPUT', title: `${event.task_id} · ${event.output_receipt.output_type}`, description: '输出收据带内容哈希，可在恢复时验证而无需重跑 Tool。', detailLabel: '输出收据', payload: event.output_receipt };
      case 'checkpoint_committed': return { ...common, kind: 'durable', label: 'CHECKPOINT', title: event.checkpoint.checkpoint_id, description: '先原子追加并 fsync，再承认恢复点存在。', detailLabel: '完整 Checkpoint', payload: event.checkpoint };
      case 'runtime_interrupted': return { ...common, kind: 'error', label: 'PROCESS CRASH', title: event.reason, description: `没有已提交输出：${event.committed_output_absent_for.join(' · ')}`, detailLabel: '中断边界', payload: event };
      case 'run_paused_for_restart': return { ...common, kind: 'control', label: 'WAITING RESTART', title: 'Checkpoint 已保存', description: '当前请求到此结束；请点击“从断点重启”启动新的恢复请求。', detailLabel: '可恢复终态', payload: event };
      case 'resume_requested': return { ...common, kind: 'durable', label: 'NEW PROCESS', title: `Resume ${event.checkpoint_id}`, description: `新的 HTTP 请求恢复逻辑 Run ${event.workflow_run_id}。`, detailLabel: '恢复入口', payload: event };
      case 'checkpoint_loaded': return { ...common, kind: 'durable', label: 'LOAD', title: event.checkpoint_id, description: '加载不等于信任；下一步必须重新校验所有绑定。', detailLabel: '恢复请求', payload: event };
      case 'checkpoint_binding_validated': return { ...common, kind: event.passed ? 'result' : 'error', label: event.passed ? 'BINDING PASS' : 'STALE', title: event.passed ? 'Checkpoint may resume' : 'Checkpoint cannot resume', description: Object.entries(event.checks).map(([name, ok]) => `${ok ? '✓' : '✕'} ${name}`).join(' · '), detailLabel: '绑定对比', payload: event };
      case 'stale_checkpoint_rejected': return { ...common, kind: 'error', label: 'STALE BLOCK', title: event.reasons.join(' · '), description: `恢复任务 ${event.resumed_tasks} · 副作用 ${event.effect_count}`, detailLabel: '拒绝终态', payload: event };
      case 'task_restored_from_checkpoint': return { ...common, kind: 'durable', label: 'RESTORED', title: `${event.task_id} · 0 repeated calls`, description: '验证输出收据后恢复节点状态，不重新调用已完成 Tool。', detailLabel: '恢复证据', payload: event };
      case 'unfinished_task_resumed': return { ...common, kind: 'call', label: 'RESUME', title: `${event.task_id} · attempt ${event.resume_attempt}`, description: event.reason, detailLabel: '恢复范围', payload: event };
      case 'resume_join_released': return { ...common, kind: 'result', label: 'RECOVERY JOIN', title: `${event.required}/${event.required} dependencies`, description: `恢复 ${event.restored.join(' + ')} · 新完成 ${event.newly_completed.join(' + ')}`, detailLabel: 'Join 状态', payload: event };
      case 'recovery_completed': return { ...common, kind: 'result', label: 'RECOVERED', title: `Resumed ${event.resumed_tasks.join(' · ')}`, description: `已完成 Tool 重复调用 ${event.repeated_tool_calls} 次 · paper-only`, detailLabel: '恢复终态', payload: event };
      case 'saga_started': return { ...common, kind: 'handoff', label: 'SAGA', title: event.saga_id, description: '每个正向步骤都声明对应补偿；失败时按相反顺序执行。', detailLabel: 'Saga 步骤', payload: event };
      case 'saga_step_applied': return { ...common, kind: 'ledger', label: 'FORWARD', title: event.action, description: `纸面效果累计 ${event.paper_effect_count} · 补偿 ${event.compensation}`, detailLabel: '正向步骤', payload: event };
      case 'saga_step_failed': return { ...common, kind: 'error', label: 'STEP FAILED', title: event.action, description: `${event.error_type} · 真实订单效果 ${event.real_order_effect_count}`, detailLabel: '失败边界', payload: event };
      case 'compensation_started': return { ...common, kind: 'control', label: 'REVERSE', title: 'Compensation starts', description: event.pending.join(' → '), detailLabel: '逆序补偿计划', payload: event };
      case 'compensation_applied': return { ...common, kind: 'result', label: 'COMPENSATE', title: event.action, description: `追加记录，不删除历史 · 未补偿纸面效果 ${event.open_paper_effects}`, detailLabel: '补偿结果', payload: event };
      case 'compensation_failed': return { ...common, kind: 'error', label: 'COMPENSATION FAILED', title: event.action, description: `仍有 ${event.open_paper_effects} 个未解决纸面效果；不得宣称恢复。`, detailLabel: '补偿故障', payload: event };
      case 'saga_compensated': return { ...common, kind: 'result', label: 'COMPENSATED', title: event.status, description: `未解决纸面效果 ${event.open_paper_effects} · 真实订单效果 ${event.real_order_effect_count}`, detailLabel: 'Saga 终态', payload: event };
      case 'reconciliation_required': return { ...common, kind: 'error', label: 'MANUAL REVIEW', title: event.status, description: '自动补偿失败；冻结继续执行并要求人工对账。', detailLabel: '升级终态', payload: event };
      case 'release_bundle_created': return { ...common, kind: 'durable', label: 'RELEASE BUNDLE', title: event.candidate.release_id, description: 'Model、Prompt、Graph 与 Risk Policy 绑定为不可变版本。', detailLabel: 'Current 与 Candidate', payload: event };
      case 'release_golden_eval_completed': return { ...common, kind: event.passed ? 'eval' : 'error', label: 'GOLDEN GATE', title: `${event.release_id} · score ${event.score}`, description: '行为回归通过后才允许进入 Shadow。', detailLabel: '发布前 Eval', payload: event };
      case 'shadow_run_started': return { ...common, kind: 'observability', label: 'SHADOW', title: `${event.release_id} · 0% authority`, description: '接收相同输入，但 Candidate 结果不能发布。', detailLabel: 'Shadow 边界', payload: event };
      case 'shadow_comparison_completed': return { ...common, kind: event.passed ? 'result' : 'error', label: 'SHADOW COMPARE', title: event.passed ? 'Candidate may enter canary' : 'Candidate blocked', description: `发布结果 ${event.metrics.published_results} · p95 ${event.metrics.p95_latency_ms}ms`, detailLabel: '对比指标', payload: event.metrics };
      case 'canary_started': return { ...common, kind: 'control', label: 'CANARY', title: `${event.traffic_percent}% → ${event.release_id}`, description: `其余流量继续使用 ${event.current_release_id}`, detailLabel: '灰度配置', payload: event };
      case 'canary_gate_evaluated': return { ...common, kind: event.passed ? 'result' : 'error', label: event.passed ? 'CANARY PASS' : 'CANARY BREACH', title: event.passed ? 'Eligible for promotion' : 'Automatic rollback required', description: Object.entries(event.checks).map(([name, ok]) => `${ok ? '✓' : '✕'} ${name}`).join(' · '), detailLabel: '发布门禁', payload: event };
      case 'canary_allocation_stopped': return { ...common, kind: 'error', label: 'STOP TRAFFIC', title: event.release_id, description: `失败项：${event.failed_checks.join(' · ')}`, detailLabel: '停止分配', payload: event };
      case 'release_promoted': return { ...common, kind: 'result', label: 'PROMOTE', title: `${event.from_release} → ${event.to_release}`, description: `Candidate 获得 ${event.traffic_percent}% 纸面流量 · 仍为 paper-only`, detailLabel: '晋级决定', payload: event };
      case 'release_rolled_back': return { ...common, kind: 'result', label: 'ROLLBACK', title: `Active: ${event.active_release}`, description: `Candidate 新流量 ${event.candidate_traffic_percent}% · 失败 Trace 保留`, detailLabel: '回滚终态', payload: event };
      case 'golden_trace_loaded': return { ...common, kind: 'eval', label: 'GOLDEN TRACE', title: event.golden.golden_id, description: '固定必须满足的事件顺序、Guardrails、禁用 Tool 与最低分；不要求模型逐字复现答案。', detailLabel: '批准的行为基准', payload: event.golden };
      case 'model_regression_started': return { ...common, kind: 'eval', label: 'REGRESSION', title: `${event.candidate_version} vs ${event.golden_id}`, description: '候选版本在同一行为合约上接受评测。', detailLabel: '评测身份', payload: event };
      case 'model_eval_assertion_checked': return { ...common, kind: event.passed ? 'eval' : 'error', label: event.passed ? 'ASSERT PASS' : 'ASSERT FAIL', title: event.assertion, description: event.passed ? '候选行为满足 Golden Trace。' : '检测到行为退化；不会用总分掩盖硬性安全失败。', detailLabel: '断言结果', payload: event };
      case 'model_regression_completed': return { ...common, kind: event.passed ? 'result' : 'error', label: event.passed ? 'EVAL PASS' : 'REGRESSION FOUND', title: `Score ${event.score} / ${event.threshold}`, description: event.passed ? '候选模型可继续进入纸面研究环境。' : `退化项：${event.regressions.join(' · ')}`, detailLabel: '完整回归报告', payload: event };
      case 'short_term_memory_created': return { ...common, kind: 'memory', label: 'SHORT-TERM', title: 'Run-scoped working state', description: `只活在本次运行；检测到敏感字段但不把值写入 Trace。字段：${event.field_names.join(' · ')}`, detailLabel: '生命周期与字段名', payload: event };
      case 'privacy_redaction_completed': return { ...common, kind: 'memory', label: 'REDACT', title: `${event.redacted_fields.length} sensitive fields removed`, description: '先脱敏，再允许长期保存；API Key、邮箱和账户标识不会进入记忆库。', detailLabel: '脱敏审计', payload: event };
      case 'long_term_memory_written': return { ...common, kind: 'memory', label: 'LONG-TERM WRITE', title: event.memory.memory_id, description: '只保存脱敏内容、Scope、来源和内容哈希；使用追加式 JSONL。', detailLabel: '实际持久化记录', payload: event.memory };
      case 'long_term_memory_retrieved': return { ...common, kind: 'memory', label: 'MEMORY RETRIEVAL', title: event.memory.scope, description: `按明确 Scope 召回 · 来源 ${event.provenance.source} · 不把记忆当成事实真相。`, detailLabel: '召回记录与来源', payload: event };
      case 'memory_write_blocked': return { ...common, kind: 'error', label: 'PRIVACY BLOCK', title: 'Raw memory rejected before disk write', description: `副作用 ${event.effect_count} 次 · 拒绝字段：${event.rejected_fields.join(' · ')}`, detailLabel: '隐私门禁结果', payload: event };
      case 'short_term_memory_discarded': return { ...common, kind: 'memory', label: 'FORGET', title: 'Short-term state discarded', description: 'Run 结束后工作状态被清除；只有已脱敏的长期记录可以继续存在。', detailLabel: '清除边界', payload: event };
      case 'agent_role_activated': return { ...common, kind: 'handoff', label: 'ROLE', title: event.role_contract.role_id, description: event.role_contract.mission, detailLabel: '完整角色合约', payload: event.role_contract };
      case 'handoff_contract_created': return { ...common, kind: 'handoff', label: 'HANDOFF', title: `${event.actor_role} → ${event.recipient_role}`, description: '发送方只能提交结构化合约；接收方不会继承发送方的隐含权限。', detailLabel: '交接信封、Payload 与哈希', payload: event.handoff };
      case 'handoff_validation_started': return { ...common, kind: 'handoff', label: 'VERIFY', title: `${event.actor_role} validates ${event.sender_role}`, description: '接收方先检查 Schema、角色路由、证据、Paper-only 与合约哈希。', detailLabel: '验证边界', payload: event };
      case 'handoff_validation_completed': return { ...common, kind: event.passed ? 'handoff' : 'error', label: event.passed ? 'CONTRACT PASS' : 'CONTRACT FAIL', title: event.passed ? 'Handoff may activate recipient' : 'Recipient remains inactive', description: event.passed ? '所有交接断言通过。' : event.reasons.join(' · '), detailLabel: '交接校验结果', payload: event };
      case 'handoff_accepted': return { ...common, kind: 'handoff', label: 'ACCEPTED', title: `${event.sender_role} → ${event.actor_role}`, description: '接收方只接受合约内声明的 Payload 与权限。', detailLabel: '接受凭证', payload: event };
      case 'handoff_rejected': return { ...common, kind: 'error', label: 'HANDOFF REJECTED', title: 'Unsafe authority escalation stopped', description: `${event.reasons.join(' · ')} · 副作用 ${event.effect_count} 次`, detailLabel: '拒绝原因', payload: event };
      case 'orchestration_started': return { ...common, kind: 'handoff', label: 'SUPERVISOR', title: 'Bounded orchestration policy loaded', description: `最多 ${event.policy.max_assignments} 次分配 · ${event.policy.max_revisions} 次修改 · ${event.policy.token_budget} tokens · 单一 Owner`, detailLabel: '编排策略', payload: event.policy };
      case 'task_envelope_created': return { ...common, kind: 'handoff', label: 'TASK ENVELOPE', title: event.assignment_id, description: `只允许 ${event.allowed_roles.join(' → ')}；任务携带 Paper-only Guardrail。`, detailLabel: '任务信封', payload: event };
      case 'orchestration_decision_recorded': return { ...common, kind: event.action === 'STOP' ? 'error' : 'handoff', label: event.action, title: event.reason, description: `${event.from_owner || 'Supervisor'} → ${event.to_owner || '释放所有权'} · 权限未变化`, detailLabel: 'Supervisor 决策与剩余预算', payload: event };
      case 'task_ownership_changed': return { ...common, kind: 'handoff', label: 'OWNERSHIP', title: `${event.to_owner} owns ${event.assignment_id}`, description: `所有权 v${event.ownership_version} · role ${event.assignee_role} · single_owner=${event.single_owner}`, detailLabel: '所有权变更', payload: event };
      case 'orchestration_budget_updated': return { ...common, kind: 'handoff', label: 'BUDGET', title: `${event.assignments_remaining} assignments · ${event.tokens_remaining} tokens left`, description: `${event.revisions_remaining} 次 Revision 剩余。`, detailLabel: '预算计数器', payload: event };
      case 'agent_task_started': return { ...common, kind: 'handoff', label: 'WORK START', title: `${event.worker_id} · ${event.actor_role}`, description: `只处理 ${event.assignment_id} 中声明的职责。`, detailLabel: 'Worker 输入边界', payload: event };
      case 'agent_task_completed': return { ...common, kind: 'handoff', label: 'WORK RESULT', title: `${event.worker_id} submitted output`, description: '结果返回 Supervisor；提交者不能自行选择下一步。', detailLabel: 'Agent 输出', payload: event.output };
      case 'risk_review_completed': return { ...common, kind: event.approved ? 'handoff' : 'error', label: event.approved ? 'RISK PASS' : 'RETURN', title: event.approved ? `DV01 ${event.proposed_dv01} <= ${event.limit_dv01}` : (event.reason || `DV01 ${event.proposed_dv01} > ${event.limit_dv01}`), description: 'Risk 只能批准或拒绝，不能替分析师改写策略。', detailLabel: '独立风险判断', payload: event };
      case 'task_returned_for_revision': return { ...common, kind: 'handoff', label: 'REVISION', title: `${event.reason_code} · revision ${event.revision}`, description: event.requested_change, detailLabel: '有界退回要求', payload: event };
      case 'agent_timeout_detected': return { ...common, kind: 'error', label: 'TIMEOUT', title: `${event.worker_id} produced no committed output`, description: 'Supervisor 必须先撤销旧 Owner，才能把相同任务交给健康 Worker。', detailLabel: '超时证据', payload: event };
      case 'task_ownership_revoked': return { ...common, kind: 'error', label: 'REVOKE', title: `${event.owner} no longer owns the task`, description: event.reason, detailLabel: '撤销凭证', payload: event };
      case 'orchestration_loop_detected': return { ...common, kind: 'error', label: 'LOOP GUARD', title: `${event.signature} repeated ${event.occurrences} times`, description: 'Revision 预算已到边界；停止而不是继续消耗。', detailLabel: '循环签名', payload: event };
      case 'orchestration_authority_violation_detected': return { ...common, kind: 'error', label: 'AUTHORITY BLOCK', title: event.requested, description: `允许范围：${event.allowed} · 权限未扩大 · 副作用 ${event.effect_count} 次`, detailLabel: '越权请求', payload: event };
      case 'paper_runtime_mapped': return { ...common, kind: 'result', label: 'PAPER RUNTIME', title: event.graph, description: '只有 Risk 批准后的合约进入固定任务图；没有真实执行。', detailLabel: 'Runtime 映射', payload: event };
      case 'orchestration_stopped': return { ...common, kind: 'error', label: 'SAFE STOP', title: event.reason, description: `安全停止 · 副作用 ${event.effect_count} 次 · Runtime 未激活`, detailLabel: '停止终态', payload: event };
      case 'retrieval_bypassed': return { ...common, kind: 'retrieval', label: 'RETRIEVER', title: 'Retrieval bypassed', description: event.reason };
      case 'retrieval_query_created': return { ...common, kind: 'retrieval', label: 'QUERY', title: event.query, description: `确定性 lexical retrieval · Top-K ${event.top_k} · 语料 ${event.corpus_size} chunks · 无伪造 embedding`, detailLabel: 'Query 与检索配置', payload: event };
      case 'retrieval_candidate_scored': return { ...common, kind: 'retrieval', label: 'RANK', title: `#${event.rank} ${event.chunk_id} · ${event.lexical_score}`, description: `${event.matched_terms.join(', ') || '无匹配词'}${event.selected_top_k ? ' · 进入 Top-K' : ' · 未进入 Top-K'}`, detailLabel: '完整 Chunk、来源与内容哈希', payload: event };
      case 'retrieval_topk_selected': return { ...common, kind: 'retrieval', label: 'TOP-K', title: `${event.selected_chunk_ids.length}/${event.top_k} chunks selected`, description: event.selected_chunk_ids.join(' · '), detailLabel: '候选引用', payload: event };
      case 'retrieval_completed': return { ...common, kind: 'retrieval', label: 'RETRIEVED', title: `${event.result_count} chunks forwarded`, description: '这只是检索候选；尚未通过来源门禁。' };
      case 'citation_gate_bypassed': return { ...common, kind: 'retrieval', label: 'SOURCE GATE', title: 'Citation gate bypassed', description: event.reason };
      case 'citation_gate_started': return { ...common, kind: 'retrieval', label: 'SOURCE GATE', title: `${event.candidate_count} citations under review`, description: `必须覆盖 ${event.required_series.join(' + ')}，且来源域名、版本、内容哈希完整。`, detailLabel: '门禁规则', payload: event };
      case 'citation_checked': return { ...common, kind: event.passed ? 'retrieval' : 'error', label: event.passed ? 'CITATION PASS' : 'CITATION REJECT', title: `${event.chunk_id} · ${event.domain || 'no source domain'}`, description: event.passed ? `${event.citation_id} · ${event.series.join(' + ')}` : event.reasons.join(' · '), detailLabel: '引用验证结果', payload: event };
      case 'citation_gate_completed': return { ...common, kind: event.passed ? 'result' : 'error', label: event.passed ? 'EVIDENCE READY' : 'ABSTAIN', title: event.passed ? `${event.accepted_citation_ids.length} verified citations` : `Missing ${event.missing_series.join(' + ')}`, description: event.passed ? `覆盖 ${event.coverage.join(' + ')}，允许进入 CT1。` : '证据不完整；CT1、模型、Runtime 与 Tools 都不会启动。', detailLabel: '来源门禁终态', payload: event };
      case 'taint_guard_bypassed': return { ...common, kind: 'security', label: 'TRUST GUARD', title: 'Taint guard bypassed', description: event.reason };
      case 'taint_guard_started': return { ...common, kind: 'security', label: 'UNTRUSTED', title: `${event.candidate_count} retrieved chunks enter the boundary`, description: '来源可信不等于内容有执行权；每个 chunk 默认带 taint 标记。', detailLabel: 'Trust boundary policy', payload: event };
      case 'retrieved_content_inspected': return { ...common, kind: event.tainted ? 'security-block' : 'security', label: event.tainted ? 'QUARANTINE' : 'PROMOTE AS DATA', title: `${event.chunk_id} · ${event.action}`, description: event.tainted ? `检测到 ${event.matched_rules.join(' · ')}；整段隔离，不做局部删除。` : '未检测到控制指令；仅作为证据数据进入 CT1。', detailLabel: event.tainted ? '原始恶意内容与命中规则' : '通过检查的只读内容', payload: event };
      case 'taint_guard_completed': return { ...common, kind: event.passed ? 'result' : 'error', label: event.passed ? 'SAFE DATA' : 'ABSTAIN', title: event.passed ? `${event.promoted_citation_ids.length} promoted · ${event.quarantined_citation_ids.length} quarantined` : 'Safe evidence coverage incomplete', description: event.passed ? '只有 promoted 内容可以进入 Context Pack；隔离内容不再传播。' : `隔离后缺少 ${event.missing_series.join(' + ')}；CT1、Model、Runtime、Tools 全部阻塞。`, detailLabel: 'Taint propagation terminal state', payload: event };
      case 'capability_bypassed': return { ...common, kind: 'capability', label: 'AUTHZ', title: 'Capability gate bypassed', description: event.reason };
      case 'capability_policy_started': return { ...common, kind: 'capability', label: 'DENY DEFAULT', title: 'Runtime starts capability authority', description: `票据绑定 ${event.bindings.join(' · ')}`, detailLabel: '授权政策', payload: event };
      case 'capability_minted': return { ...common, kind: 'capability', label: 'MINT', title: `${event.target_task} · ${event.capability.tool_name}`, description: `${event.capability.scope} · max ${event.capability.max_uses} use · secret 不进入票据`, detailLabel: '签名 Capability claims', payload: event };
      case 'capability_check_started': return { ...common, kind: 'capability', label: 'AUTH CHECK', title: `${event.target_task} requests ${event.tool_name}`, description: `需要 ${event.required_scope}；校验签名、run、task、tool、scope、有效期与使用次数。`, detailLabel: '请求与票据对照', payload: event };
      case 'capability_verified': return { ...common, kind: 'capability', label: 'VERIFIED', title: `${event.cap_id} permits ${event.tool_name}`, description: `${event.required_scope} · ALLOW_ONCE；仍未调用函数。`, detailLabel: '授权决定', payload: event };
      case 'capability_consumed': return { ...common, kind: 'capability', label: 'CONSUMED', title: `${event.target_task} · ${event.consumed_uses}/${event.max_uses}`, description: '逻辑调用权已消费；后续 Runtime retry 沿用同一已授权调用，不重新签发。', detailLabel: '使用计数', payload: event };
      case 'capability_rejected': return { ...common, kind: 'capability-block', label: 'DENIED', title: `${event.target_task} cannot call ${event.tool_name}`, description: `${event.reasons.join(' · ')}；函数尚未执行，副作用为零。`, detailLabel: '拒绝原因', payload: event };
      case 'human_approval_bypassed': return { ...common, kind: 'approval', label: 'HITL', title: 'Human approval bypassed', description: event.reason };
      case 'human_approval_requested': return { ...common, kind: 'approval-wait', label: 'WAITING HUMAN', title: `${event.tool_name} requests elevated scope`, description: `${event.scope} · 参数指纹 ${event.arguments_sha256.slice(0, 12)}… · 请使用页面 Approve/Deny 按钮。`, detailLabel: '完整审批请求', payload: event };
      case 'human_approval_resolved': return { ...common, kind: event.decision === 'approve' ? 'approval' : 'error', label: event.decision === 'approve' ? 'APPROVED' : event.decision === 'deny' ? 'DENIED BY HUMAN' : 'APPROVAL TIMEOUT', title: `${event.approval_id} · ${event.decision}`, description: event.decision === 'approve' ? '批准只绑定当前 run、Tool、scope 与参数指纹。' : '未签发高风险 Capability；后续 Tool 不执行。', detailLabel: '人工决定', payload: event };
      case 'permission_elevation_approved': return { ...common, kind: 'approval', label: 'ELEVATE ONCE', title: `${event.tool_name} · ${event.scope}`, description: '允许 Runtime 为本次 paper-only 运行签发一次性 Capability。', detailLabel: '权限提升边界', payload: event };
      case 'approval_checkpoint_saved': return { ...common, kind: 'durable', label: 'CHECKPOINT SAVED', title: `${event.approval_id} · fsync complete`, description: '等待状态与参数指纹已原子写入磁盘；内存丢失后仍可恢复。', detailLabel: '持久化边界', payload: event };
      case 'approval_runtime_restarted': return { ...common, kind: 'durable', label: 'RUNTIME RESTART', title: 'Fresh ApprovalRegistry instance', description: '教学流中丢弃旧 Registry 内存并创建全新实例；跨进程读取另有自动化验证。', detailLabel: '重启边界', payload: event };
      case 'approval_checkpoint_loaded': return { ...common, kind: 'durable', label: 'APPROVAL RESTORED', title: `${event.approval_id} · ${event.stored_decision}`, description: `从磁盘恢复批准及参数指纹 ${event.arguments_sha256.slice(0, 12)}…`, detailLabel: '恢复内容', payload: event };
      case 'approval_binding_validated': return { ...common, kind: event.passed ? 'durable' : 'error', label: event.passed ? 'RESUME SAFE' : 'STALE APPROVAL', title: event.passed ? 'Stored approval matches resumed command' : 'Parameter fingerprint changed', description: event.passed ? 'run、Tool、scope、参数指纹全部一致；允许继续签发 Capability。' : '旧批准不能覆盖新参数；需要重新审批。', detailLabel: '恢复后绑定校验', payload: event };
      case 'context_bypassed': return { ...common, kind: 'context', label: 'CONTEXT', title: 'Context builder bypassed', description: event.reason };
      case 'context_collection_started': return { ...common, kind: 'context', label: 'COLLECT', title: `${event.candidate_count} context candidates`, description: `Context budget ${event.max_tokens} teaching tokens · 尚未交给模型`, detailLabel: '候选来源与预算', payload: event };
      case 'context_item_scored': return { ...common, kind: 'context', label: 'SCORE', title: `${event.item_id} · ${event.score}`, description: `相关性 ${event.relevance} · 权威性 ${event.authority} · 新鲜度 ${event.freshness}${event.mandatory ? ' · 必选' : ''}`, detailLabel: '候选内容与评分', payload: event };
      case 'context_item_selected': return { ...common, kind: 'context', label: 'KEEP', title: `${event.item_id} · ${event.used_tokens} tokens`, description: `完整保留 · Context 剩余 ${event.remaining_tokens}`, detailLabel: '保留决策', payload: event };
      case 'context_item_compressed': return { ...common, kind: 'context', label: 'COMPRESS', title: `${event.item_id} · ${event.full_tokens} → ${event.used_tokens}`, description: `使用声明的有损摘要 · 释放 ${event.released_tokens} teaching tokens`, detailLabel: '压缩前后与决策', payload: event };
      case 'context_item_dropped': {
        const reasons = { low_relevance: '相关性不足', context_budget_exceeded: '剩余预算不足', superseded_by_fresher_authoritative_context: `与 ${event.winner} 冲突且已过期` };
        return { ...common, kind: 'context', label: 'DROP', title: `${event.item_id} excluded`, description: reasons[event.reason] || event.reason, detailLabel: '丢弃决策', payload: event };
      }
      case 'context_pack_created': return { ...common, kind: 'context', label: 'PACK', title: `${event.used_tokens}/${event.max_tokens} context tokens`, description: `只把 ${event.context_pack.items.length} 项交给模型 · 排除 ${event.excluded_item_ids.length} 项`, detailLabel: '模型实际收到的 Context Pack', payload: event.context_pack };
      case 'model_routing_bypassed': return { ...common, kind: 'route', label: 'ROUTER', title: 'Model routing bypassed', description: event.reason };
      case 'model_routing_started': return { ...common, kind: 'route', label: 'ROUTE START', title: `Token budget · ${event.budget.total_tokens}`, description: `${event.candidates.join(' → ')} · fallback 最多 ${event.max_fallbacks} 次`, detailLabel: 'Model catalog 与预算', payload: event };
      case 'model_route_selected': return { ...common, kind: 'route', label: 'SELECT', title: `${event.model} · ${event.tier}`, description: `${event.provider} · ${event.reason}`, detailLabel: '路由决策', payload: event };
      case 'model_budget_reserved': return { ...common, kind: 'route', label: 'RESERVE', title: `Reserve ${event.reservation.reserved_tokens} tokens`, description: `调用前预留最坏情况；剩余 ${event.reservation.budget.remaining_tokens}。`, detailLabel: 'Token reservation', payload: event.reservation };
      case 'model_provider_failed': return { ...common, kind: 'error', label: 'PROVIDER FAIL', title: `${event.model} unavailable`, description: `${event.error_message} · 同模型不重试`, detailLabel: '失败与已消耗 token', payload: event };
      case 'model_budget_settled': return { ...common, kind: 'route', label: 'CHARGE', title: `Charged ${event.settlement.charged_tokens} tokens`, description: `释放 ${event.settlement.released_tokens} · 预算剩余 ${event.settlement.budget.remaining_tokens}`, detailLabel: 'Token ledger', payload: event.settlement };
      case 'model_fallback_requested': return { ...common, kind: 'route', label: `FALLBACK ${event.fallback_number}/${event.max_fallbacks}`, title: `${event.from_model} → ${event.to_model}`, description: '只切换到 Model Registry 中声明的下一个候选；不会无限升级。', detailLabel: 'Fallback 决策', payload: event };
      case 'model_budget_rejected': return { ...common, kind: 'error', label: 'BUDGET STOP', title: `${event.model} not called`, description: `需预留 ${event.required_tokens}，仅剩 ${event.remaining_tokens}；调用前 ABSTAIN。`, detailLabel: '预算拒绝', payload: event };
      case 'model_route_abstained': return { ...common, kind: 'error', label: 'ABSTAIN', title: 'No model call permitted', description: event.reason, detailLabel: '路由终态', payload: event };
      case 'model_route_completed': return { ...common, kind: 'route', label: 'ROUTE END', title: `${event.selected_model} completed`, description: `fallback ${event.fallback_count} 次 · 已用 ${event.budget.spent_tokens}/${event.budget.total_tokens} token`, detailLabel: '最终路由与预算', payload: event };
      case 'model_bypassed': return { ...common, kind: 'model', label: 'MODEL', title: 'Model gateway bypassed', description: event.reason };
      case 'model_request_started': return { ...common, kind: 'model', label: 'MODEL INPUT', title: `${event.model} · proposal ${event.attempt}`, description: event.is_real_llm ? '真实模型调用；模型只能生成提议。' : '可重复的教学模型；不是外部 LLM，也没有执行权限。', detailLabel: '完整 prompt 与权限声明', payload: event.prompt };
      case 'model_response_received': return { ...common, kind: 'model', label: 'RAW OUTPUT', title: `${event.output_characters} characters received`, description: '这是未经信任的模型文本；尚未成为 Plan。', detailLabel: '原始模型输出', payload: { raw_output: event.raw_output, model: event.model, is_real_llm: event.is_real_llm } };
      case 'intent_parse_started': return { ...common, kind: 'model', label: 'PARSE INTENT', title: 'Parse model output as JSON', description: '解析只证明 JSON 可读，不代表 Intent 被允许。' };
      case 'intent_parse_failed': return { ...common, kind: 'error', label: 'INTENT PARSE FAILED', title: event.error_type, description: event.error_message, detailLabel: '损坏的原始输出', payload: event.raw_output };
      case 'model_intent_parsed': return { ...common, kind: 'model', label: 'INTENT JSON', title: 'Intent parsed', description: '模型仍没有 Tool、参数或订单权限。', detailLabel: '解析后的 Intent', payload: event.proposal };
      case 'intent_validation_started': return { ...common, kind: 'model', label: 'RUNTIME MAP', title: 'Runtime validates Intent', description: event.checks.join(' · '), detailLabel: 'Intent 校验项目', payload: event.checks };
      case 'intent_validation_completed': return { ...common, kind: event.accepted ? 'result' : 'error', label: event.accepted ? 'INTENT ACCEPTED' : 'INTENT REJECTED', title: event.accepted ? 'Runtime owns the mapping decision' : 'Runtime refuses this Intent', description: event.accepted ? '模型只选择允许的意图；固定任务图仍由 Runtime 创建。' : event.reasons.join(' · '), detailLabel: 'Intent 校验结果', payload: event.output || event.reasons };
      case 'model_intent_accepted': return { ...common, kind: 'model', label: 'INTENT BOUNDARY', title: event.intent, description: event.intent === 'ABSTAIN' ? 'Runtime 不会启动任何 Tool。' : 'Runtime 将此 Intent 映射为固定的 2s10s 纸面任务图。', detailLabel: '获准的 Intent', payload: event };
      case 'model_intent_abstained': return { ...common, kind: 'error', label: 'ABSTAIN', title: 'No Tool starts', description: event.reason, detailLabel: '受控无动作终态', payload: event };
      case 'model_intent_rejected': return { ...common, kind: 'error', label: 'INTENT REJECTED', title: 'Unsafe Intent stopped before Runtime', description: event.reasons.join(' · '), detailLabel: '拒绝原因', payload: event.reasons };
      case 'plan_parse_started': return { ...common, kind: 'model', label: 'PARSE', title: 'Parse model output as JSON', description: '解析只证明 JSON 可读，不代表内容安全。' };
      case 'plan_parse_failed': return { ...common, kind: 'error', label: 'PARSE FAILED', title: event.error_type, description: event.error_message, detailLabel: '损坏的原始输出', payload: event.raw_output };
      case 'model_repair_requested': return { ...common, kind: 'model', label: 'REPAIR 1/1', title: event.repair_kind === 'semantic_contract' ? 'Request one bounded contract repair' : 'Request one bounded format repair', description: '只修复 JSON 或已声明的合约字段；不扩大 Tool 权限。', detailLabel: '修复约束', payload: event };
      case 'plan_parsed': return { ...common, kind: 'model', label: 'JSON', title: 'Proposal parsed', description: '进入 Runtime 校验；仍不可执行。', detailLabel: '解析后的提议', payload: event.proposal };
      case 'plan_validation_started': return { ...common, kind: 'model', label: 'AUTHORITY', title: 'Runtime validates proposal', description: event.checks.join(' · '), detailLabel: '校验项目', payload: event.checks };
      case 'plan_validation_completed': return { ...common, kind: event.accepted ? 'result' : 'error', label: event.accepted ? 'PLAN ACCEPTED' : 'PLAN REJECTED', title: event.accepted ? 'Runtime permits execution' : 'Runtime refuses execution', description: event.accepted ? 'Schema、Tool allowlist、DAG、paper-only 与执行模板全部通过。' : event.reasons.join(' · '), detailLabel: '完整校验结果', payload: event.output || event.reasons };
      case 'model_plan_accepted': return { ...common, kind: 'model', label: 'BOUNDARY', title: 'Proposal promoted to executable Plan', description: '决定权属于 Runtime，不属于模型。', detailLabel: '获准执行的提议', payload: event.proposal };
      case 'model_plan_rejected': return { ...common, kind: 'error', label: 'ABSTAIN', title: 'Unsafe proposal stopped before Runtime', description: event.reasons.join(' · '), detailLabel: '拒绝原因', payload: event.reasons };
      case 'plan_created': return { ...common, title: 'Plan created', description: event.graph ? 'C1 保护 D1；V1 验证 Observation；Q1 控制分支准入' : '固定计划 · D1 → S1，随后 E1 校验', detailLabel: '完整计划与依赖' };
      case 'runtime_started': return { ...common, title: 'Runtime started', description: '从 Tool Registry 解析能力，并执行参数校验和重试策略。', detailLabel: 'Runtime 与 Tool Registry' };
      case 'lease_bypassed': return { ...common, kind: 'lease', label: 'LEASE', title: 'Lease coordinator bypassed', description: event.reason };
      case 'lease_acquire_started': return { ...common, kind: 'lease', label: 'ACQUIRE', title: `${event.owner} requests ${event.resource}`, description: `TTL ${event.ttl_ms}ms；只有持有者才能继续本次 Run。`, detailLabel: 'Lease 请求', payload: event };
      case 'lease_acquired': return { ...common, kind: 'lease', label: 'LEASE ACQUIRED', title: `${event.owner} · token ${event.fencing_token}`, description: `租约有效至 ${event.expires_at}；后续副作用必须携带当前 fencing token。`, detailLabel: 'Lease 授予', payload: event };
      case 'lease_renewal_started': return { ...common, kind: 'lease', label: 'RENEW', title: `${event.owner} renews token ${event.fencing_token}`, description: '在 TTL 到期前续租，保持 Runtime 所有权。', detailLabel: '续租请求', payload: event };
      case 'lease_renewed': return { ...common, kind: 'lease', label: 'RENEWED', title: `${event.owner} · token ${event.fencing_token}`, description: `新的 TTL ${event.ttl_ms}ms。`, detailLabel: '续租结果', payload: event };
      case 'lease_expired': return { ...common, kind: 'lease', label: 'LEASE EXPIRED', title: `${event.owner} · token ${event.fencing_token}`, description: '旧 Runtime 不再拥有执行权；它即使继续运行也必须被挡住。', detailLabel: '过期边界', payload: event };
      case 'lease_takeover_started': return { ...common, kind: 'lease', label: 'TAKEOVER', title: `${event.owner} takes over`, description: `新 owner 接管 ${event.resource}，旧 token ${event.previous_fencing_token} 立即变旧。`, detailLabel: '接管请求', payload: event };
      case 'lease_fence_rejected': return { ...common, kind: 'lease-block', label: 'FENCED', title: `${event.owner} blocked`, description: `token ${event.fencing_token} 已落后于当前 token ${event.current_fencing_token}；副作用为零。`, detailLabel: 'Fencing 拒绝', payload: event };
      case 'lease_fence_verified': return { ...common, kind: 'lease', label: 'FENCE PASS', title: `${event.owner} · token ${event.fencing_token}`, description: '当前 owner 与 token 匹配；允许进入下一步 Tool 边界。', detailLabel: 'Fencing 校验', payload: event };
      case 'lease_side_effect_blocked': return { ...common, kind: 'lease-block', label: 'SIDE EFFECT BLOCKED', title: 'Stale Runtime cannot write', description: '旧 Runtime 被 Fencing Token 拦截，没有执行 Tool 或写入结果。', detailLabel: '副作用边界', payload: event };
      case 'lease_released': return { ...common, kind: 'lease', label: 'RELEASE', title: `${event.owner} released token ${event.fencing_token}`, description: 'Run 结束，主动释放所有权。', detailLabel: '释放结果', payload: event };
      case 'outbox_bypassed': return { ...common, kind: 'outbox', label: 'OUTBOX', title: 'Outbox bypassed', description: event.reason };
      case 'outbox_enqueued': return { ...common, kind: 'outbox', label: 'ENQUEUE', title: `${event.idempotency_key} · PENDING`, description: '先持久化要做什么，再由 Dispatcher 异步发送；不会把调用当作已成功。', detailLabel: 'Outbox command', payload: event };
      case 'outbox_dispatch_started': return { ...common, kind: 'outbox', label: 'DISPATCH', title: `${event.owner} · attempt ${event.attempt}`, description: `at-least-once delivery · fencing token ${event.fencing_token}`, detailLabel: '发送尝试', payload: event };
      case 'outbox_ack_lost': return { ...common, kind: 'outbox', label: 'ACK LOST', title: 'Effect may already be applied', description: '模拟崩溃发生在 Sink 成功与 Outbox ACK 之间；恢复时必须用同一个 idempotency key 重试。', detailLabel: '崩溃窗口', payload: event };
      case 'outbox_dispatch_rejected': return { ...common, kind: 'outbox-block', label: 'FENCED', title: `${event.owner} cannot dispatch`, description: `旧 token ${event.fencing_token} < 当前 token ${event.current_fencing_token}；Sink 尚未执行。`, detailLabel: 'Outbox 发送拒绝', payload: event };
      case 'outbox_side_effect_blocked': return { ...common, kind: 'outbox-block', label: 'SIDE EFFECT BLOCKED', title: 'No sink write', description: '旧 Runtime 被挡在副作用边界之外。', detailLabel: '副作用边界', payload: event };
      case 'outbox_effect_applied': return { ...common, kind: 'outbox', label: 'EFFECT APPLIED', title: `${event.owner} · effect count ${event.effect_count}`, description: '幂等 Sink 首次应用这条命令。', detailLabel: 'Sink 结果', payload: event };
      case 'outbox_effect_deduplicated': return { ...common, kind: 'outbox', label: 'DEDUPLICATED', title: `${event.idempotency_key} · effect count ${event.effect_count}`, description: '第二次投递被 Sink 识别为同一个命令；没有产生第二个副作用。', detailLabel: '去重结果', payload: event };
      case 'outbox_acknowledged': return { ...common, kind: 'outbox', label: 'ACK', title: `${event.status} · ${event.attempts} attempts`, description: `Sink effect count = ${event.effect_count}；发送可以重复，效果只保留一份。`, detailLabel: '确认结果', payload: event };
      case 'outbox_completed': return { ...common, kind: 'result', label: 'OUTBOX DONE', title: `effect count ${event.effect_count}`, description: '本课不宣称分布式 exactly-once；保证的是 at-least-once + 幂等目标。', detailLabel: 'Outbox 终态', payload: event };
      case 'ledger_replay_started': return { ...common, kind: 'ledger', label: 'LEDGER START', title: 'Replay paper ledger', description: 'LG1 不直接相信 S1 内存结果；从追加事件重建纸面交易。', detailLabel: '账本边界', payload: event };
      case 'ledger_event_appending':
      case 'ledger_event_appended': return { ...common, kind: 'ledger', label: 'LEDGER WRITE', title: event.event_type, description: '事件先追加并 fsync；写入成功后才向 Live Stream 发布状态。', detailLabel: '写入命令', payload: event };
      case 'ledger_snapshot_rebuilt': return { ...common, kind: 'ledger', label: 'REBUILD', title: `${event.event_count} events · ${event.status}`, description: '按序重放 JSONL hash chain，生成可复算的账本快照。', detailLabel: '重建快照', payload: event };
      case 'portfolio_snapshot_rebuilt': return { ...common, kind: 'ledger', label: 'PORTFOLIO', title: event.risk_status, description: `2s10s 未结算 ${event.summary?.open_curve_trade_count ?? 0} 笔 · 净平行 DV01 ${event.summary?.net_parallel_dv01_usd_per_bp ?? 0} USD/bp；聚合来源是重放后的追加腿账本。`, detailLabel: '2s10s 组合投影与明确限额', payload: event };
      case 'portfolio_fill_preflight': return { ...common, kind: 'ledger', label: 'PREFLIGHT PASS', title: 'Projected 2s10s DV01 within limits', description: '先检查投影后的净平行 DV01，账本仍未写入；获准后才可记录纸面成交。', detailLabel: '原子预检结果', payload: event };
      case 'portfolio_fill_blocked': return { ...common, kind: 'guard', label: 'LIMIT BLOCKED', title: 'Projected 2s10s DV01 exceeds limit', description: `副作用 0 次；${event.violations?.map(row => row.limit + ' ' + row.value + ' > ' + row.maximum).join(' · ') || '限额超出'}。`, detailLabel: '拒绝的投影与限额', payload: event };
      case 'ledger_reconciliation_started': return { ...common, kind: 'ledger', label: 'RECONCILE', title: 'Compare S1 with replayed ledger', description: '逐字段比较交易 ID、方向、利差、毛收益、成本与净 P&L。', detailLabel: 'Expected → Replayed', payload: event };
      case 'ledger_reconciliation_completed': return { ...common, kind: 'result', label: 'LEDGER PASS', title: 'Paper ledger reconciled', description: `${event.event_count} 个持久化事件重建出与 S1 相同的交易。`, detailLabel: '对账结果', payload: event };
      case 'ledger_mismatch_detected': return { ...common, kind: 'error', label: 'LEDGER MISMATCH', title: 'Replay differs from S1', description: `${event.differences?.length || 0} 个字段不一致；E1 被阻断，不继续伪造通过。`, detailLabel: 'Expected vs replayed diff', payload: event };
      case 'task_started': return { ...common, title: 'Node started', description: event.tool_name };
      case 'tool_lookup': return { ...common, label: 'REGISTRY', title: event.tool_name, description: event.found ? 'Tool 已在注册表找到' : 'Tool 未注册' };
      case 'tool_validation': return { ...common, kind: event.passed ? 'node' : 'error', label: 'VALIDATION', title: event.passed ? 'Arguments validated' : 'Arguments rejected', description: event.tool_name, detailLabel: '参数校验结果' };
      case 'tool_execution_started': return { ...common, kind: 'call', label: 'TOOL CALL', title: event.tool_name, description: `第 ${event.attempt} / ${event.max_attempts} 次调用`, detailLabel: '调用参数 · 完整 JSON', payload: event.arguments };
      case 'tool_observation': {
        const output = event.output || {};
        const description = output.artifact_type === 'prepared_rate_series' ? `${output.series_id} · ${output.summary?.count} 条观测 · 序列校验完成` : (event.task_id === 'D1' || event.task_id === 'J1') ? `${output.observations?.length ?? 0} 条对齐观测 · ${output.source_freshness || output.provider || '来源见结果'} · 截至 ${output.as_of || '未知'}` : `${output.completed_trade?.action || '模拟完成'} · 完整交易与计算结果已返回`;
        return { ...common, kind: 'result', label: 'TOOL RESULT', title: event.tool_name, description, detailLabel: '返回结果 · 完整 JSON', payload: output };
      }
      case 'task_completed': return { ...common, title: 'Node completed', description: event.tool_name };
      case 'plan_revision_registered': return { ...common, kind: 'replan', label: 'PLAN v0', title: 'Initial plan fingerprinted', description: `重规划预算尚余 ${event.remaining_revisions} 次；相同计划不会再次执行。`, detailLabel: '计划指纹与预算' };
      case 'observation_validation_started': return { ...common, kind: 'replan', label: 'GATE', title: 'Validate D1 Observation', description: 'Tool 调用成功不代表结果可供下游使用。' };
      case 'observation_validation_completed': return { ...common, kind: event.passed ? 'result' : 'replan', label: event.passed ? 'GATE PASS' : 'GATE REJECT', title: event.passed ? 'Observation accepted' : 'Observation rejected', description: event.passed ? `${event.output?.observation_count} 条观测满足下游要求。` : `${event.output?.observation_count}/${event.output?.minimum_required} 条；不把无效结果传给下游。`, detailLabel: 'Observation Gate 结果', payload: event.output };
      case 'task_invalidated': return { ...common, kind: 'replan', label: 'INVALIDATED', title: `${event.task_id} output removed from active state`, description: '结果仅保留在审计 Trace；不会进入 A2 / A10。', detailLabel: '被拒绝的完整 Observation', payload: event.rejected_observation };
      case 'replan_requested': return { ...common, kind: 'replan', label: 'FEEDBACK ↺', title: 'V1 requests a new plan', description: '这是重规划：Tool 已成功，但结果质量不够；不是原调用的瞬时失败重试。', detailLabel: '结构化反馈', payload: event.feedback };
      case 'plan_revised': return { ...common, kind: 'replan', label: `PLAN v${event.revision}`, title: 'Planner revised D1 arguments', description: `扩大数据窗口 · 剩余重规划预算 ${event.remaining_revisions} 次。`, detailLabel: '新旧计划与反馈', payload: event };
      case 'replan_loop_detected': return { ...common, kind: 'error', label: 'LOOP STOP', title: 'Repeated plan fingerprint blocked', description: 'Planner 再次提出已被拒绝的同一计划；Runtime 终止循环并 ABSTAIN。', detailLabel: '循环检测状态', payload: event.guard };
      case 'replan_budget_exhausted': return { ...common, kind: 'error', label: 'BUDGET STOP', title: 'Replanning budget exhausted', description: '新计划仍不满足 V1；Runtime 不允许无限循环，停止并 ABSTAIN。', detailLabel: '重规划预算状态', payload: event.guard };
      case 'parallel_group_started': return { ...common, label: 'FAN-OUT', title: 'Concurrent branches dispatched', description: `${event.task_ids.join(' + ')} · 最多 ${event.max_workers} 个 worker` };
      case 'join_waiting': return { ...common, label: 'JOIN', title: `Join · ${event.completed_dependencies.length}/${event.required} ready`, description: event.waiting_for.length ? `等待 ${event.waiting_for.join(' + ')}；尚未调用下游 Tool` : '两边均成功，准备放行' };
      case 'join_released': return { ...common, kind: 'result', label: 'FAN-IN', title: 'Join released · 2/2', description: '两个依赖均成功，现在才允许汇合与策略计算。' };
      case 'join_blocked': return { ...common, kind: 'error', label: 'JOIN BLOCKED', title: 'Join will not run', description: `失败分支：${event.failed_dependencies.join(', ')}；等待已运行的只读分支结束，不执行下游。` };
      case 'task_failed': return { ...common, kind: 'error', label: 'NODE FAILED', title: event.error_type, description: event.error_message };
      case 'task_blocked': return { ...common, label: 'BLOCKED', title: 'Node not executed', description: event.reason };
      case 'demo_scenario_selected': return { ...common, label: 'DEMO', title: `Teaching mode · ${event.scenario}`, description: event.message };
      case 'demo_delay_started': return { ...common, label: 'DEMO DELAY', title: `Teaching delay · ${event.delay_ms}ms`, description: event.reason };
      case 'run_budget_started': return { ...common, label: 'BUDGET', title: `Run budget · ${event.budget_ms / 1000}s`, description: '覆盖整次运行；到期请求协作停止，不强杀线程。' };
      case 'circuit_bypassed': return { ...common, kind: 'guard', label: 'CIRCUIT', title: 'Circuit guard · pass through', description: event.reason };
      case 'circuit_call_allowed': return { ...common, kind: 'guard', label: 'CIRCUIT', title: `Call allowed · ${String(event.state).toUpperCase()}`, description: `第 ${event.attempt} 次请求获准进入 Tool · 本次教学 Run` };
      case 'circuit_failure_recorded': return { ...common, kind: 'guard', label: 'FAILURE +1', title: `${event.error_type} recorded`, description: `连续失败 ${event.snapshot?.failure_count}/${event.snapshot?.failure_threshold}` };
      case 'circuit_state_changed': return { ...common, kind: 'guard', label: 'STATE', title: `${String(event.from_state).toUpperCase()} → ${String(event.to_state).toUpperCase()}`, description: event.to_state === 'open' ? '达到阈值；后续请求先被熔断器拦截。' : event.to_state === 'half_open' ? '冷却结束；只放行一次探测调用。' : '探测成功；恢复正常调用。' };
      case 'circuit_call_rejected': return { ...common, kind: 'guard', label: 'SHORT-CIRCUIT', title: 'Tool call rejected before execution', description: '熔断器为 OPEN；没有进入 Tool，也不产生外部请求。', detailLabel: '熔断状态', payload: event.snapshot };
      case 'circuit_success_recorded': return { ...common, kind: 'guard', label: 'SUCCESS', title: 'Successful call recorded', description: event.snapshot?.transition ? '探测成功，Circuit 回到 CLOSED。' : '调用成功，失败计数归零。' };
      case 'admission_bypassed': return { ...common, kind: 'guard', label: 'ADMISSION', title: 'Normal concurrent admission', description: event.reason };
      case 'admission_requested': return { ...common, kind: 'guard', label: 'ARRIVAL', title: `${event.target_task} requests admission`, description: '任务先经过本次教学 Run 的 Runtime Guard，尚未调用 Tool。' };
      case 'rate_limit_granted': return { ...common, kind: 'guard', label: 'PERMIT', title: `${event.target_task} admitted`, description: '获得执行许可，可以进入 Tool。' };
      case 'backpressure_queued': return { ...common, kind: 'guard', label: 'QUEUED', title: `${event.target_task} waits · depth ${event.queue_depth}`, description: '执行槽已满；通过有界队列把压力留在 Runtime。' };
      case 'rate_limit_waiting': return { ...common, kind: 'guard', label: 'THROTTLE', title: `Rate limit wait · ${Math.round(event.delay_ms)}ms`, description: '容量已释放，但仍需满足最小放行间隔。' };
      case 'backpressure_released': return { ...common, kind: 'guard', label: 'DEQUEUED', title: `${event.target_task} released from queue`, description: '拿到许可后才开始 Tool 调用。' };
      case 'admission_capacity_released': return { ...common, kind: 'guard', label: 'CAPACITY', title: `${event.target_task} released its slot`, description: 'Runtime 可以考虑放行下一个排队任务。' };
      case 'admission_rejected': return { ...common, kind: 'guard', label: 'REJECTED', title: `${event.target_task} rejected before Tool call`, description: '队列已满；快速失败，避免无限堆积。', detailLabel: '准入状态', payload: event.snapshot };
      case 'admission_cycle_completed': return { ...common, kind: 'guard', label: 'DRAINED', title: 'Admission queue drained', description: '活动数与队列深度都回到 0。' };
      case 'deadline_exceeded': return { ...common, kind: 'control', label: 'DEADLINE', title: 'Deadline exceeded', description: '预算已到 ≠ Tool 已停止。Runtime 将请求停止并等待确认。' };
      case 'cancellation_requested': return { ...common, kind: 'control', label: 'STOP REQUEST', title: 'Stop requested · waiting for acknowledgment', description: `原因：${event.reason} · 等待 ${event.active_tasks.join(', ') || '运行边界'} 确认` };
      case 'task_cancelled': return { ...common, kind: 'control', label: 'STOP ACK', title: 'Tool acknowledged stop', description: '该调用已退出；不是仅关闭浏览器连接。' };
      case 'tool_output_discarded': return { ...common, kind: 'control', label: 'DISCARDED', title: 'Late result discarded', description: '保留供检查，但不写入有效 Observation，不传给下游。', detailLabel: '查看被丢弃的完整结果', payload: event.output };
      case 'run_stopped': return { ...common, kind: 'control', label: 'STOPPED', title: event.reason === 'deadline' ? 'Run timed out · all workers stopped' : 'Run cancelled · all workers stopped', description: '停止已确认；此前完成的节点保留，下游不再执行。' };
      case 'non_cooperative_wait': return { ...common, kind: 'control', label: 'DEMO', title: 'Non-cooperative Tool demo', description: event.reason };
      case 'tool_execution_failed': return { ...common, kind: 'error', label: 'ERROR', title: event.error_type, description: `${event.error_message} · ${event.retryable ? '将按策略重试' : '不再重试'}`, detailLabel: '错误详情' };
      case 'tool_retry_scheduled': return { ...common, label: 'RETRY', title: `Retry scheduled · attempt ${event.next_attempt}`, description: `${event.delay_ms}ms 退避后再次调用` };
      case 'data_source_attempt': return { ...common, label: 'SOURCE', title: `${event.provider} · ${event.status}`, description: event.error_message || event.source_mode };
      case 'data_source_fallback_selected': return { ...common, label: 'SOURCE', title: `Fallback selected · ${event.provider}`, description: `${event.source_freshness} · ${event.source_mode} · ${event.as_of}` };
      case 'eval_started': return { ...common, kind: 'call', label: 'EVAL INPUT', title: event.evaluator, description: '校验 P&L 可复算性、数据时序与仅模拟边界', detailLabel: '评估输入 · 完整 JSON', payload: event.arguments };
      case 'eval_completed': return { ...common, kind: event.passed ? 'result' : 'error', label: 'EVAL RESULT', title: event.passed ? 'All checks passed' : 'Evaluation failed', description: Object.entries(event.output?.checks || {}).map(([name, passed]) => `${passed ? '✓' : '✕'} ${name}`).join(' · '), detailLabel: '逐项评估结果', payload: event.output };
      case 'run_completed': return { ...common, kind: 'result', label: 'RUNTIME', title: 'Workflow completed', description: '所有节点执行结束，等待最终运行产物。' };
      default: return common;
    }
  }
  return { NODES, PARALLEL_NODES, PARALLEL_ROWS, ORCHESTRATION_NODES, ORCHESTRATION_ROWS,
    DECOMPOSITION_NODES, DECOMPOSITION_ROWS, AGENT_TOOL_NODES, AGENT_TOOL_ROWS,
    OBSERVABILITY_NODES, OBSERVABILITY_ROWS, DURABLE_NODES, DURABLE_ROWS,
    SAGA_NODES, SAGA_ROWS, RELEASE_NODES, RELEASE_ROWS,
    STUDIO_ROLES, flowForEvent, roleForEvent,
    handoffForEvent, modeForScenario, createState, applyMessage, finishStream, failState, describe };
});
