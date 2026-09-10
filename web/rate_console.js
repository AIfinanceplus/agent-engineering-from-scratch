(function () {
  'use strict';
  const { NODES, PARALLEL_NODES, PARALLEL_ROWS, ORCHESTRATION_NODES, ORCHESTRATION_ROWS,
    DECOMPOSITION_NODES, DECOMPOSITION_ROWS, AGENT_TOOL_NODES, AGENT_TOOL_ROWS,
    OBSERVABILITY_NODES, OBSERVABILITY_ROWS, DURABLE_NODES, DURABLE_ROWS,
    SAGA_NODES, SAGA_ROWS, RELEASE_NODES, RELEASE_ROWS,
    STUDIO_ROLES, flowForEvent, roleForEvent,
    handoffForEvent, modeForScenario, createState, applyMessage, finishStream, failState, describe } = window.RateConsole;
  const byId = id => document.getElementById(id);
  const labels = { waiting: '待执行', ready: '可执行', running: '运行中', paused: '等待重启', completed: '已完成', failed: '失败', blocked: '未执行', abstained: '主动停止', cancelling: '停止中', cancelled: '已取消', timed_out: '超时停止', unknown: '状态未知', open: 'OPEN', half_open: 'HALF-OPEN', queued: '排队中', throttling: '限速等待', rejected: '已拒绝', replan: '需重规划 ↺', invalidated: '已作废', proposed: '提议待审', repairing: '修复中', retrieving: '召回中', ranking: '排名中', topk: 'Top-K 完成', verifying: '验源中', scanning: '扫描中', quarantining: '隔离中', waiting_human: '等待人工', approved: '已批准', restarting: '进程重启', restoring: '恢复审批', acquiring: '申请租约', acquired: '持有租约', renewing: '续租中', expired: '已过期', taking_over: '接管中', fenced: '旧持有者已隔离', retrying: '等待重试', writing: '写入中', deduplicated: '已去重', issuing: '签发中', issued: '已签发', authorizing: '鉴权中', verified: '已授权', selecting: '筛选中', compressing: '压缩中', selected: '已选路', reserved: '预算已预留', fallback: '切换模型', budget_blocked: '预算阻止' };
  let state = createState(modeForScenario(document.getElementById('scenario')?.value || 'durable_resume_pass'));
  let inFlight = false;
  let filter = null;
  let selectedRole = null;
  let flowMode = 'information';
  let cancelPending = false;
  let cancelNote = '';
  let pendingCheckpoint = null;
  let resumingCheckpoint = false;
  const rows = [];
  const nodeElements = new Map();
  const edgeElements = [];
  const roleElements = new Map();
  const MODEL_KEY_SESSION = 'rate-console:model-api-key';
  const flowCopy = {
    information: ['信息流', '你 → 策略分析师 → 风险主管 → 执行主管 → Trace', '岗位卡固定显示输入和输出；沟通记录保留全部交接，不因流视图而消失。'],
    decision: ['决策流', '策略提议 → 独立验约 → 已批准合约 → 固定 Runtime', '每位 Agent 只决定自己职责内的事情，接收方必须重新验证。'],
    risk: ['风控流', 'Claims / Evidence → Contract Gate → ALLOW 或 BLOCK → Audit', '拒绝路径停在风险主管，执行主管保持未激活，副作用为零。'],
  };
  const advancedScenarios = new Set(['eval_golden_pass', 'eval_regression_fail', 'memory_redaction_pass', 'memory_privacy_block', 'handoff_contract_pass', 'handoff_contract_reject', 'orchestration_normal', 'orchestration_revision', 'orchestration_timeout_reassign', 'orchestration_loop_block', 'orchestration_authority_block', 'decomposition_dynamic_pass', 'decomposition_cycle_block', 'agent_tool_parallel_pass', 'agent_tool_scope_block', 'observability_slo_pass', 'observability_slo_breach', 'durable_resume_pass', 'durable_stale_checkpoint_block', 'saga_compensation_pass', 'saga_compensation_escalate', 'release_canary_promote', 'release_canary_rollback']);
  const lessonCopy = {
    eval: {
      title: 'Model Evals · Golden Trace', detail: '判断候选模型行为是否仍满足已批准合约。',
      whyTitle: '模型输出会随模型、Prompt 和上下文变化', why: '普通单元测试无法判断语义行为是否退化；Golden Trace 固定必须发生的安全行为。',
      howTitle: 'Golden → Candidate → Assertions → Score', how: '比较事件顺序、权限、Guardrails 与结果类型，不比较措辞是否逐字相同。',
      watchTitle: 'PASS 或 Regression Detected', watch: '查看每条 assertion；退化场景会明确指出越权 Tool 与缺失风险门禁。',
      overview: 'Golden Trace → Candidate Run → Behavioral Assertions → Regression Decision',
    },
    memory: {
      title: 'Agent Memory · 生命周期与隐私', detail: '区分本次运行状态和可以跨运行保存的脱敏知识。',
      whyTitle: '没有生命周期的“记忆”会变成隐私泄漏', why: '短期状态帮助完成当前任务；长期记忆必须先脱敏、带 Scope 和来源，并允许审计。',
      howTitle: 'Short-term → Privacy Gate → Long-term → Retrieval', how: '原始 API Key、邮箱和账户标识只能停留在短期内存；长期层只接收脱敏记录。',
      watchTitle: '写入、召回或零副作用阻断', watch: '正常场景展示持久化哈希与来源；违规场景在落盘前拒绝，effect_count=0。',
      overview: 'Run State → Redaction → Append-only Memory → Scoped Retrieval',
    },
    handoff: {
      title: 'Multi-Agent Handoff · 交接契约', detail: '每个 Agent 只在自己的职责和权限范围内工作。',
      whyTitle: '多 Agent 增加的是边界，不只是角色数量', why: '自由文本交接会丢失来源并暗中扩大权限；接收方必须重新验证，而不是盲目信任发送方。',
      howTitle: 'Analyst → Risk → Runtime', how: '每次交接绑定 Schema、角色、证据、Paper-only Guardrail 和内容哈希。',
      watchTitle: '接受后激活，拒绝则下游不启动', watch: '合法合约逐级传递；越权 automatic_execution 会被 Risk 拒绝且副作用为零。',
      overview: 'Role Contract → Handoff Envelope → Recipient Validation → Activation / Reject',
    },
    orchestration: {
      title: 'Supervisor · Multi-Agent Orchestration', detail: '让独立编排层管理任务所有权、Revision、超时与预算，而不获得业务执行权。',
      whyTitle: 'Handoff 解决交接格式，Supervisor 解决下一步由谁负责', why: '真实团队会遇到退回、超时和重复循环；没有编排政策，Agent 容易失去所有权边界或无限消耗预算。',
      howTitle: 'Assign → Observe → Return / Reassign → Complete / Stop', how: '每次决策都记录责任人、理由、所有权版本和剩余预算；任何时刻只能有一个 Owner。',
      watchTitle: '所有权先撤销，再重分配', watch: '重点观察 ASSIGN、RETURN、REASSIGN 和 STOP；Supervisor 不能改策略、批风险或执行 Tool。',
      overview: 'Goal → Supervisor Policy → Single Owner → Bounded Decision → Safe Terminal',
    },
    decomposition: {
      title: 'Dynamic Task Graph · 动态任务拆解', detail: '让 Agent 根据目标生成受约束的子任务图，再由 Runtime 验证后派发。',
      whyTitle: '复杂目标不能永远写死成一张 DAG', why: '任务数量会随问题变化，但动态不等于任意：任务 ID、输入输出和依赖必须先成为可验证的数据。',
      howTitle: 'Decompose → Graph Gate → Fan-out → Join → Synthesize', how: 'Graph Validator 在任何 Worker 启动前检查引用和环；通过后才并行派发三项有类型任务。',
      watchTitle: '先验证拓扑，再创建 Worker', watch: '正常场景观察 3/3 Join；有环场景停在 GV1，workers_dispatched=0。',
      overview: 'Goal → Typed Task Graph → Cycle Gate → Dynamic Workers → Join → Synthesis',
    },
    agent_tool: {
      title: 'Agent-as-Tool · 受控专家委派', detail: 'Manager 保留控制权，把专家 Agent 当作有边界的可调用能力。',
      whyTitle: '需要专家协作，不一定要转移对话控制权', why: 'Handoff 会把主动权交给接收者；Agent-as-Tool 让 Manager 组合多个专家输出并负责最终回答。',
      howTitle: 'Manager → Specialist Calls → Typed Results → Manager Synthesis', how: '每位专家只暴露声明过的输入、输出和 authority；结果必须返回 Manager，不能直接进入 Runtime。',
      watchTitle: '控制权始终属于 Manager', watch: '越权 place_order 会在专家 Scope Gate 被拦截，Runtime 不激活。',
      overview: 'Manager Control → Bounded Specialists → Typed Return → Synthesis → Paper Runtime',
    },
    observability: {
      title: 'Observability & SLO · 可操作的生产信号', detail: '把 Trace、Span、延迟和 Token 从展示信息变成运行门禁。',
      whyTitle: '有日志不等于可运营', why: '必须能定位哪一步慢、用了多少预算、是否泄露内容，并让超标指标触发明确动作。',
      howTitle: 'Root Trace → Child Spans → Metrics → SLO Gate', how: '每个 Span 绑定 parent，聚合 p95、tokens 和 effect_count；Prompt 与 Secret 不采集。',
      watchTitle: 'SLO 违反会阻止 Runtime', watch: '正常场景通过门禁；超标场景以 SAFE STOP 结束且副作用为零。',
      overview: 'Trace Context → Parented Spans → Aggregation → SLO Decision → Run / Stop',
    },
    durable: {
      title: 'Durable Workflow · 断点恢复', detail: '进程崩溃后验证 Checkpoint，只继续没有已提交输出的任务。',
      whyTitle: '恢复不能等同于从头再跑', why: '已完成 Tool 如果重复调用，会重复消耗、写入或污染状态；Checkpoint 必须证明哪些输出已经提交。',
      howTitle: 'Commit → Crash → Load → Revalidate → Resume', how: '恢复前重新验证 Run、图版本、输入指纹和 Guardrail；有效才恢复 W1/W2 并只继续 W3。',
      watchTitle: 'Resume、Replay 与 Rerun 必须区分', watch: '正常场景已完成 Tool 重复调用为 0；参数变化时旧 Checkpoint 在 RV1 被拒绝。',
      overview: 'Committed Output → Durable Checkpoint → Crash → Binding Gate → Selective Resume',
    },
    saga: {
      title: 'Saga & Compensation · 部分失败恢复', detail: '跨步骤失败后，以追加式补偿恢复纸面状态，而不是删除历史。',
      whyTitle: '跨 Tool 操作没有一个全局数据库事务', why: '后一步失败时，前面的纸面风险预留和意图可能已经发生；系统必须按逆序执行对应补偿。',
      howTitle: 'Forward Steps → Failure → Reverse Compensation → Reconcile', how: '每个正向步骤声明补偿动作；补偿失败时停止自动化并进入人工对账。',
      watchTitle: '补偿不是假装原操作没发生', watch: 'Trace 同时保留正向和补偿事件；只有 open_paper_effects=0 才能标记 COMPENSATED。',
      overview: 'Paper Effects → Failure → Reverse Compensation → Compensated / Manual Reconciliation',
    },
    release: {
      title: 'Agent Release Engineering · 安全发布', detail: '把 Model、Prompt、Graph 和 Policy 作为一个版本，经 Shadow 与 Canary 后晋级。',
      whyTitle: '升级模型只是升级 Agent 的一部分', why: 'Prompt、工具、任务图和风险政策都会改变行为；发布必须绑定完整 Bundle 并保留可回滚版本。',
      howTitle: 'Bundle → Golden Gate → Shadow → 5% Canary → Promote / Rollback', how: 'Shadow 无结果权限；Canary 只接收少量纸面流量，延迟或 Token 超标会自动切回 Current。',
      watchTitle: '新版本先证明自己，再获得流量', watch: '正常场景晋级到 100%；超标场景 Candidate 流量降为 0，失败 Trace 仍保留。',
      overview: 'Immutable Release → Offline Eval → Shadow → Canary Gate → Promote / Rollback',
    },
  };
  const scenarioBudget = () => ['deadline', 'late_result'].includes(byId('scenario').value) ? 1000 : ['live', 'execution_race', 'paper_fill_accounting', 'paper_portfolio_risk', 'model_live', 'intent_live', 'approval_interactive', 'approval_durable_restart', 'approval_durable_stale', 'lease_failover', 'lease_renewal', 'outbox_retry', 'outbox_fenced'].includes(byId('scenario').value) ? 120000 : 30000;

  const lessonForScenario = scenario => scenario.startsWith('durable_') ? 'durable' : scenario.startsWith('saga_') ? 'saga' : scenario.startsWith('release_') ? 'release' : scenario.startsWith('decomposition_') ? 'decomposition' : scenario.startsWith('agent_tool_') ? 'agent_tool' : scenario.startsWith('observability_') ? 'observability' : scenario.startsWith('memory_') ? 'memory' : scenario.startsWith('handoff_') ? 'handoff' : scenario.startsWith('orchestration_') ? 'orchestration' : 'eval';
  const lessonOutcomeCopy = {
    eval_golden_pass: ['Golden Trace 固定安全行为，不固定模型措辞', '候选运行保留了事件顺序、风险门禁与 paper-only 结果，模型可以升级。'],
    eval_regression_fail: ['回归评测的价值，是在上线前阻止行为退化', '越权 Tool 与缺失风险门禁已被 Golden Trace 检出；候选模型没有进入 Runtime。'],
    memory_redaction_pass: ['长期记忆只保存脱敏、可追溯的知识', '敏感值停留在短期状态；通过 Privacy Gate 的记录才带着 Scope 与来源进入长期层。'],
    memory_privacy_block: ['隐私门禁必须发生在长期写入之前', '违规记录在落盘前被阻断，长期记忆副作用为零。'],
    handoff_contract_pass: ['交接传递的是有边界的合约，不是隐式信任', 'Analyst、Risk 与 Runtime 逐级验约；只有通过的 Payload 与权限进入接收方。'],
    handoff_contract_reject: ['接收方必须重新验证，不能继承发送方的信任', 'automatic_execution 越权在 Risk 边界被拒绝，下游 Runtime 未激活。'],
    orchestration_normal: ['Supervisor 编排责任，不替 Agent 做业务决定', '任务按单一 Owner 推进；Supervisor 只记录 ASSIGN 与 COMPLETE，Runtime 仍受 paper-only 门禁约束。'],
    orchestration_revision: ['退回不是无限重做：Revision 必须有理由和预算', 'Risk 给出明确 DV01 修改要求；Supervisor 只安排一次有界修订，再交回 Risk 独立复核。'],
    orchestration_timeout_reassign: ['重分配前必须先撤销旧 Owner', '超时 Worker 的所有权先失效，再由新 Worker 接管同一个受限任务，避免双重所有者。'],
    orchestration_loop_block: ['循环不是继续重试：预算耗尽后必须安全停止', '重复退回被 Loop Guard 识别；Runtime 未激活，副作用为零。'],
    orchestration_authority_block: ['Supervisor 也受权限边界约束', 'automatic_execution 越权请求被阻断；Supervisor 无权改策略、批风险或调用执行 Tool。'],
    decomposition_dynamic_pass: ['动态任务图也必须先验约再派发', '三项有类型 Worker 任务通过无环检查后并行运行，并在 3/3 Join 后才进入综合。'],
    decomposition_cycle_block: ['检测到环时，一个 Worker 都不能创建', 'GV1 在派发前拒绝循环依赖；workers_dispatched=0，副作用为零。'],
    agent_tool_parallel_pass: ['Agent-as-Tool 协作不转移最终控制权', '曲线与风险专家返回结构化结果；Manager 组合结果后才提交给纸面 Runtime。'],
    agent_tool_scope_block: ['专家 Agent 的能力边界必须可执行地约束', 'risk_specialist 请求 place_order 被 Scope Gate 拒绝，Manager 安全停止。'],
    observability_slo_pass: ['可观测性必须能回答“哪里慢、花多少、下一步做什么”', '三个子 Span 的父子关系与预算指标完整，SLO 通过后才激活纸面 Runtime。'],
    observability_slo_breach: ['SLO 是运行政策，不只是仪表盘数字', '延迟与 Token 超标触发 SAFE STOP；Runtime 未激活，副作用为零。'],
    durable_resume_pass: ['恢复只继续没有已提交结果的工作', 'W1/W2 从输出收据恢复且不重复调用；W3 完成后 Recovery Join 才放行。'],
    durable_stale_checkpoint_block: ['Checkpoint 必须重新验约，不能盲目续跑', '输入指纹已变化，RV1 拒绝旧状态；恢复任务为 0，副作用为零。'],
    saga_compensation_pass: ['补偿以新事件纠正状态，不删除历史', '账本步骤失败后按逆序补偿意图与风险预留，未解决纸面效果回到 0。'],
    saga_compensation_escalate: ['补偿失败必须升级，不能虚报恢复成功', '风险释放失败后系统进入 NEEDS_MANUAL_RECONCILIATION，并冻结继续自动化。'],
    release_canary_promote: ['Agent 发布必须绑定完整版本并逐级获得权限', 'Candidate 通过 Golden、Shadow 与 5% Canary，才晋级为 100% Active。'],
    release_canary_rollback: ['Canary 的意义是限制坏版本影响范围', '延迟与 Token 超标后停止 Candidate 新流量，切回 Current 并保留失败 Trace。'],
  };
  function updateLessonOutcome() {
    const banner = byId('lesson-outcome-banner');
    const scenario = state.result?.scenario || byId('scenario').value;
    const lesson = advancedScenarios.has(scenario) ? lessonForScenario(scenario) : null;
    const visible = state.terminal;
    banner.hidden = !visible;
    const completed = visible && state.phase !== 'paused';
    document.querySelector('.course-focus').dataset.completed = String(completed);
    document.querySelectorAll('.course-roadmap li').forEach(item => item.classList.toggle('run-completed', completed && item.dataset.lesson === lesson));
    if (!visible) return;
    const copy = lessonOutcomeCopy[scenario] || (lesson ? [lessonCopy[lesson].watchTitle, lessonCopy[lesson].watch] : ['本次历史能力已运行', '完整结果与边界证据保留在 Trace & Evals 工程检查台。']);
    const terminalAction = state.result?.eval?.terminal_action;
    const passed = Boolean(state.result) && state.result.eval?.passed !== false;
    const effectEvent = [...state.events].reverse().find(event => Number.isFinite(event.effect_count));
    const guardedTerminal = ['STOP', 'ESCALATE', 'ROLLBACK'].includes(terminalAction);
    const terminalLabels = { STOP: 'SAFE STOP', ESCALATE: 'MANUAL REVIEW', ROLLBACK: 'AUTO ROLLBACK',
      COMPENSATED: 'COMPENSATED', PROMOTE: 'PROMOTED', COMPLETE: 'CONTRACT PASS' };
    const waitingRestart = state.phase === 'paused';
    banner.dataset.outcome = waitingRestart ? 'waiting' : guardedTerminal ? 'stopped' : passed ? 'pass' : 'blocked';
    byId('lesson-outcome-theme').textContent = waitingRestart ? 'Checkpoint 已提交，等待你触发恢复' : copy[0];
    byId('lesson-outcome-summary').textContent = waitingRestart ? '当前 HTTP 运行已经结束。点击“从断点重启”，观察新运行如何加载旧状态、重新验约并只继续 W3。' : copy[1];
    byId('lesson-outcome-scenario').textContent = `SCENARIO · ${scenario}`;
    byId('lesson-outcome-result').textContent = !state.result ? 'RUN ERROR' : waitingRestart ? 'WAITING RESTART' : terminalLabels[terminalAction] || (passed ? 'CONTRACT PASS' : 'REGRESSION BLOCKED');
    byId('lesson-outcome-effect').textContent = `SIDE EFFECTS · ${effectEvent?.effect_count ?? 0}`;
  }
  function sourceNote(scenario) {
    if (scenario.startsWith('eval_')) return '可重复模型候选 · Golden Trace 比较语义行为 · 回归失败阻止升级';
    if (scenario.startsWith('memory_')) return '短期状态仅本次 Run · 长期记忆先脱敏并绑定来源 · 无敏感值进入 Trace';
    if (scenario.startsWith('handoff_')) return '确定性教学 Agent · 接收方独立验约 · 仍为 2s10s paper_only';
    if (scenario.startsWith('orchestration_')) return '确定性 Supervisor · 单一任务所有者 · 有界 Revision / Token · 无执行权限';
    if (scenario.startsWith('decomposition_')) return '动态任务图 · 派发前无环检查 · 三个有类型 Worker · 仅 2s10s';
    if (scenario.startsWith('agent_tool_')) return 'Manager 保留控制 · 专家仅返回结构化结果 · Scope 越权零副作用阻断';
    if (scenario.startsWith('observability_')) return 'Trace/Span 父子关系 · 不采集 Prompt/Secret · SLO 可执行门禁';
    if (scenario.startsWith('durable_')) return '原子 Checkpoint · 绑定重验证 · 只恢复未完成任务 · 已完成 Tool 不重跑';
    if (scenario.startsWith('saga_')) return '追加式纸面事件 · 逆序补偿 · 补偿失败转人工对账 · 无真实订单';
    if (scenario.startsWith('release_')) return '不可变 Release Bundle · Shadow 无权限 · 5% Canary · 自动回滚';
    if (scenario === 'live') return '公开数据 · 无延时或故障注入';
    if (scenario === 'execution_race') return '纸面成交事件 · 持久化后发送 · 重复 fill 去重';
    if (scenario === 'paper_fill_accounting') return '纸面成交账本 · 报价与成交分离 · 幂等重试 · 结算 P&L';
    if (scenario === 'paper_portfolio_risk') return '2s10s 纸面组合投影 · 净平行 DV01 限额 · 拦截不写入账本';
    if (scenario === 'intent_live') return '本地 OpenAI API · Key 不进入 Trace · 模型只能提议受限 Intent';
    if (scenario === 'model_live') return '本地 OpenAI API · Key 不进入 Trace · 模型输出仅为待校验提议';
    return '教学演示 · 公开历史快照 · 包含明确的延时/故障注入';
  }
  function updateLessonUI() {
    const scenario = byId('scenario').value;
    const lesson = advancedScenarios.has(scenario) ? lessonForScenario(scenario) : null;
    const copy = lesson ? lessonCopy[lesson] : { title: '历史课程复习', detail: '旧能力仍可运行，但默认不占用当前课程界面。', whyTitle: '历史能力', why: '从历史课程抽屉载入的场景。', howTitle: '原有 Runtime', how: '沿用原来的事件协议与安全边界。', watchTitle: '完整 Trace', watch: '展开工程检查台复习原始事件。' };
    byId('course-now-title').textContent = copy.title;
    byId('course-now-detail').textContent = copy.detail;
    byId('lesson-why-title').textContent = copy.whyTitle;
    byId('lesson-why').textContent = copy.why;
    byId('lesson-how-title').textContent = copy.howTitle;
    byId('lesson-how').textContent = copy.how;
    byId('lesson-watch-title').textContent = copy.watchTitle;
    byId('lesson-watch').textContent = copy.watch;
    document.querySelector('.lesson-brief').dataset.lesson = lesson || 'history';
    document.querySelectorAll('.course-roadmap li').forEach(item => item.classList.toggle('active', item.dataset.lesson === lesson));
    const needsKey = ['model_live', 'intent_live'].includes(scenario);
    byId('model-key-field').hidden = !needsKey;
    byId('key-session').hidden = !needsKey;
    byId('orchestration-panel').hidden = lesson !== 'orchestration';
    byId('pattern-panel').hidden = !['decomposition', 'agent_tool', 'observability', 'durable', 'saga', 'release'].includes(lesson);
    byId('handoff').hidden = ['orchestration', 'decomposition', 'agent_tool', 'observability', 'durable', 'saga', 'release'].includes(lesson);
    byId('source-note').textContent = sourceNote(scenario);
    if (!state.runId && lesson) {
      byId('overview-title').textContent = copy.title.split(' · ')[0];
      byId('overview-change').textContent = copy.overview;
      byId('check-label').textContent = 'LESSON CHECK';
      byId('ledger-status').textContent = '等待 E1';
      byId('ledger-diff').textContent = '等待可重放的评测证据';
    }
  }

  function readSessionKey() {
    try { return sessionStorage.getItem(MODEL_KEY_SESSION) || ''; } catch (_) { return ''; }
  }
  function writeSessionKey(value) {
    try { sessionStorage.setItem(MODEL_KEY_SESSION, value); return true; } catch (_) { return false; }
  }
  function clearSessionKey() {
    try { sessionStorage.removeItem(MODEL_KEY_SESSION); } catch (_) { /* storage can be disabled */ }
    byId('model-api-key').value = '';
    updateKeyStatus();
  }
  function updateKeyStatus() {
    const remembered = Boolean(readSessionKey());
    byId('key-session-status').textContent = remembered ? 'Key 已在本标签页会话中记住' : '本标签页尚未记住 Key';
    byId('key-session-status').dataset.saved = String(remembered);
    byId('forget-model-key').disabled = !remembered;
  }
  function selectArchivedScenario() {
    const archive = byId('archive-scenario');
    const selected = archive.options[archive.selectedIndex];
    const scenario = byId('scenario');
    scenario.querySelector('option[data-archive="true"]')?.remove();
    const option = new Option(`历史 · ${selected.textContent}`, selected.value, true, true);
    option.dataset.archive = 'true';
    scenario.append(option);
    byId('lesson-archive').open = false;
    scenario.dispatchEvent(new Event('change'));
  }

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }
  const graphDefinitions = { parallel: PARALLEL_NODES, orchestration: ORCHESTRATION_NODES,
    decomposition: DECOMPOSITION_NODES, agent_tool: AGENT_TOOL_NODES,
    observability: OBSERVABILITY_NODES, durable: DURABLE_NODES,
    saga: SAGA_NODES, release: RELEASE_NODES };
  const graphRowsByMode = { parallel: PARALLEL_ROWS, orchestration: ORCHESTRATION_ROWS,
    decomposition: DECOMPOSITION_ROWS, agent_tool: AGENT_TOOL_ROWS,
    observability: OBSERVABILITY_ROWS, durable: DURABLE_ROWS,
    saga: SAGA_ROWS, release: RELEASE_ROWS };
  const definitions = () => graphDefinitions[state.mode] || NODES;
  function buildGraph() {
    nodeElements.clear();
    edgeElements.length = 0;
    byId('graph-nodes').replaceChildren();
    byId('graph-nodes').classList.toggle('parallel-graph', state.mode === 'parallel');
    byId('graph-nodes').classList.toggle('orchestration-graph', state.mode === 'orchestration');
    byId('node-count').textContent = `${definitions().length} nodes`;
    const graphRows = graphRowsByMode[state.mode] || NODES.map(n => [n.id]);
    graphRows.forEach((ids, index) => {
      const row = element('div', ids.length > 1 ? 'graph-row branch-row' : 'graph-row');
      byId('graph-nodes').append(row);
      for (const id of ids) {
        const node = definitions().find(n => n.id === id);
        const button = element('button', 'graph-node');
        button.type = 'button';
        button.dataset.node = node.id;
        button.setAttribute('aria-pressed', 'false');
        button.append(element('span', 'node-id', node.id));
        const text = element('span', 'node-text');
        text.append(element('span', 'node-title', node.title), element('span', 'node-description', node.description));
        button.append(text, element('span', 'node-status'));
        button.addEventListener('click', () => { filter = filter === node.id ? null : node.id; update(); });
        nodeElements.set(node.id, button);
        row.append(button);
      }
      if (index < graphRows.length - 1) {
        const edge = element('div', 'graph-edge');
        edge.setAttribute('aria-hidden', 'true');
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 100 24');
        svg.setAttribute('preserveAspectRatio', 'none');
        const nextIds = graphRows[index + 1];
        ids.forEach((from, fromIndex) => nextIds.forEach((to, toIndex) => {
          const x1 = ids.length === 1 ? 50 : (fromIndex + 1) * 100 / (ids.length + 1);
          const x2 = nextIds.length === 1 ? 50 : (toIndex + 1) * 100 / (nextIds.length + 1);
          const path = document.createElementNS(svg.namespaceURI, 'path');
          path.setAttribute('d', `M${x1} 0V12H${x2}V23M${x2 - 1.3} 19L${x2} 23L${x2 + 1.3} 19`);
          path.setAttribute('fill', 'none');
          path.setAttribute('stroke', 'currentColor');
          path.setAttribute('stroke-width', '1');
          path.setAttribute('vector-effect', 'non-scaling-stroke');
          svg.append(path);
          edgeElements.push({ element: path, from, to });
        }));
        edge.append(svg);
        byId('graph-nodes').append(edge);
      }
    });
  }
  buildGraph();

  function buildStudio() {
    roleElements.clear();
    byId('role-grid').replaceChildren();
    for (const role of STUDIO_ROLES) {
      const button = element('button', 'role-card');
      button.type = 'button';
      button.dataset.role = role.id;
      button.dataset.status = 'waiting';
      button.setAttribute('aria-pressed', 'false');
      const top = element('span', 'role-top');
      const avatar = element('span', 'role-avatar');
      avatar.setAttribute('aria-hidden', 'true');
      avatar.append(element('i', 'avatar-head'), element('i', 'avatar-body'), element('b', 'avatar-code', role.icon));
      top.append(avatar, element('span', 'role-type', role.type));
      const mission = element('span', 'role-mission');
      mission.append(element('small', '', '职责'), element('strong', '', role.mission));
      const io = element('span', 'role-io');
      const input = element('span', 'io-block');
      input.append(element('small', '', 'INPUT'), element('b', '', role.input));
      const output = element('span', 'io-block');
      output.append(element('small', '', 'OUTPUT'), element('b', '', role.output));
      io.append(input, element('i', 'io-arrow', '→'), output);
      const boundaries = element('span', 'role-boundaries');
      const capabilities = element('span', 'boundary-block');
      capabilities.append(element('small', '', '可以做'), ...role.functions.map(item => element('em', '', `✓ ${item}`)));
      const constraints = element('span', 'boundary-block boundary-deny');
      constraints.append(element('small', '', '绝对不能'), ...role.constraints.map(item => element('em', '', `⊘ ${item}`)));
      boundaries.append(capabilities, constraints);
      const footer = element('span', 'role-footer');
      footer.append(element('span', 'role-state', '等待运行'), element('span', 'role-evidence', '0 events'));
      button.append(top, element('strong', 'role-name', role.name), mission, io, boundaries, element('span', 'role-activity', role.idle), footer);
      button.addEventListener('click', () => {
        selectedRole = selectedRole === role.id ? null : role.id;
        filter = null;
        byId('engineering-details').open = true;
        update();
        byId('engineering-details').scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      roleElements.set(role.id, button);
      byId('role-grid').append(button);
    }
  }
  buildStudio();

  function roleStatus(role) {
    if (Object.values(state.agentStates || {}).some(status => status !== 'waiting')) return state.agentStates[role.id] || 'waiting';
    const statuses = role.tasks.map(task => state.nodes[task]).filter(Boolean);
    const failed = ['failed', 'rejected', 'open', 'expired', 'fenced', 'budget_blocked', 'abstained'];
    const active = ['ready', 'running', 'proposed', 'repairing', 'retrieving', 'ranking', 'topk', 'verifying', 'scanning', 'quarantining', 'waiting_human', 'restarting', 'restoring', 'acquired', 'renewing', 'taking_over', 'retrying', 'writing', 'issuing', 'issued', 'authorizing', 'selecting', 'compressing', 'selected', 'reserved', 'fallback'];
    if (statuses.some(status => failed.includes(status))) return 'failed';
    if (statuses.some(status => active.includes(status))) return 'active';
    if (statuses.some(status => status === 'completed')) return 'completed';
    if (statuses.some(status => status === 'blocked')) return 'blocked';
    return 'waiting';
  }

  function renderHandoffs() {
    const handoffs = state.events.map(event => ({ event, handoff: handoffForEvent(event) })).filter(item => item.handoff);
    const list = byId('handoff-list');
    list.replaceChildren();
    byId('handoff-count').textContent = `${handoffs.length} 条消息`;
    if (!handoffs.length) {
      list.append(element('li', 'handoff-empty', '运行后，这里逐条显示发送、验约、接受或拒绝。'));
      return;
    }
    for (const { event, handoff } of handoffs) {
      const item = element('li', 'handoff-item');
      item.dataset.flow = handoff.flow;
      item.dataset.filtered = String(handoff.flow !== flowMode);
      const meta = element('div', 'handoff-meta');
      meta.append(element('span', '', `#${event.sequence}`), element('span', '', handoff.flow.toUpperCase()));
      const from = STUDIO_ROLES.find(role => role.id === handoff.from)?.name || handoff.from;
      const to = STUDIO_ROLES.find(role => role.id === handoff.to)?.name || handoff.to;
      const evidence = element('button', 'handoff-evidence', '查看原始事件 ↗');
      evidence.type = 'button';
      evidence.addEventListener('click', () => {
        selectedRole = null;
        filter = event.task_id || null;
        byId('engineering-details').open = true;
        update();
        const row = byId('event-list').querySelector(`[data-sequence="${event.sequence}"]`);
        if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
      let message = 'Trace 中的结构化消息';
      if (event.event === 'handoff_contract_created') message = `Envelope · ${event.handoff?.schema_version || 'rate_handoff_v1'} · hash ${(event.handoff?.contract_sha256 || '').slice(0, 10)}…`;
      if (event.event === 'handoff_validation_started') message = '接收方不继承信任：重新检查 Schema、路由、Evidence、Guardrails 与 Hash';
      if (event.event === 'handoff_validation_completed') message = event.passed ? 'PASS · 合约允许进入下一步' : `BLOCK · ${(event.reasons || []).join(' · ')}`;
      if (event.event === 'handoff_accepted') message = 'ACCEPT · 只有合约声明的 Payload 和权限进入接收方';
      if (event.event === 'handoff_rejected') message = `REJECT · ${(event.reasons || []).join(' · ')} · effect_count=${event.effect_count}`;
      item.append(meta, element('div', 'handoff-actors', `${from}  →  ${to}`), element('strong', 'handoff-title', handoff.title), element('p', 'handoff-message', message), evidence);
      list.append(item);
    }
  }

  function updateHandoffJourney() {
    const events = state.events;
    const has = (name, predicate = () => true) => events.find(event => event.event === name && predicate(event));
    const set = (id, status, label) => {
      const step = document.querySelector(`[data-journey="${id}"]`);
      step.dataset.status = status;
      step.querySelector('em').textContent = label;
    };
    const firstSent = has('handoff_contract_created', event => event.recipient_role === 'risk_controller');
    const firstCheck = has('handoff_validation_completed', event => event.actor_role === 'risk_controller');
    const rejected = has('handoff_rejected', event => event.actor_role === 'risk_controller');
    const secondSent = has('handoff_contract_created', event => event.recipient_role === 'runtime_supervisor');
    const secondCheck = has('handoff_validation_completed', event => event.actor_role === 'runtime_supervisor');
    set('analyst-send', firstSent ? 'completed' : 'waiting', firstSent ? '已发送' : '等待');
    set('risk-verify', rejected ? 'rejected' : firstCheck?.passed ? 'completed' : firstSent ? 'active' : 'waiting', rejected ? '已拒绝' : firstCheck?.passed ? '通过' : firstSent ? '验约中' : '等待');
    set('risk-send', rejected ? 'blocked' : secondSent ? 'completed' : firstCheck?.passed ? 'active' : 'waiting', rejected ? '未执行' : secondSent ? '已发送' : firstCheck?.passed ? '准备交接' : '等待');
    set('runtime-verify', rejected ? 'blocked' : secondCheck?.passed ? 'completed' : secondSent ? 'active' : 'waiting', rejected ? '未激活' : secondCheck?.passed ? '通过并激活' : secondSent ? '验约中' : '等待');
  }

  function updateModelInspector() {
    const requests = state.events.filter(event => event.event === 'model_request_started');
    const responses = state.events.filter(event => event.event === 'model_response_received');
    const repairs = state.events.filter(event => event.event === 'model_repair_requested');
    const lastRequest = requests.at(-1);
    const lastResponse = responses.at(-1);
    const accepted = [...state.events].reverse().find(event => ['model_intent_accepted', 'model_plan_accepted'].includes(event.event));
    const rejected = [...state.events].reverse().find(event => ['model_intent_rejected', 'model_plan_rejected', 'model_intent_abstained'].includes(event.event));
    const bypassed = state.events.find(event => event.event === 'model_bypassed');
    byId('model-call-count').textContent = requests.length;
    byId('model-repair-count').textContent = repairs.length;
    byId('model-output-size').textContent = lastResponse?.output_characters ?? '—';
    byId('model-name').textContent = lastRequest?.model || (bypassed ? '本次未调用大模型' : '尚未调用模型');
    byId('model-presence-detail').textContent = lastRequest ? `${lastRequest.is_real_llm ? '真实 LLM' : '可重复教学模型'} · ${lastRequest.purpose || 'proposal'}` : (bypassed?.reason || '真实 LLM 与教学模型都会明确标记');
    byId('model-input-title').textContent = lastRequest ? `Attempt ${lastRequest.attempt} · ${lastRequest.purpose || 'proposal'}` : '等待 Model Input';
    byId('model-input').textContent = lastRequest ? JSON.stringify(lastRequest.prompt, null, 2) : '本次运行尚未向模型发送内容。';
    byId('model-output-title').textContent = lastResponse ? `未经信任 · ${lastResponse.output_characters} characters` : '等待 Raw Output';
    byId('model-output').textContent = lastResponse?.raw_output || '模型输出在 Runtime 校验前始终是不可信文本。';
    if (accepted) {
      byId('model-authority').textContent = accepted.event === 'model_intent_accepted' ? `Runtime 接受 Intent：${accepted.intent}` : 'Runtime 接受受限 Plan';
      byId('model-decision').textContent = accepted.event === 'model_intent_accepted' ? 'Runtime 根据允许列表校验 Intent，并映射为自己持有的固定 2s10s 纸面任务图。' : 'Schema、Tool allowlist、DAG 与 paper-only 合约由 Runtime 校验后才可执行。';
    } else if (rejected) {
      byId('model-authority').textContent = 'Runtime 已阻止模型提议';
      byId('model-decision').textContent = rejected.reason || rejected.reasons?.join(' · ') || '没有 Tool 获得执行机会。';
    } else {
      byId('model-authority').textContent = 'Runtime 保留最终权限';
      byId('model-decision').textContent = '模型不能直接选择 Tool、修改执行参数或创建订单。';
    }
  }

  function updateOrchestration() {
    const panel = byId('orchestration-panel');
    if (panel.hidden) return;
    const started = state.events.find(event => event.event === 'orchestration_started');
    const ownership = state.events.filter(event => event.event === 'task_ownership_changed').at(-1);
    const revoked = state.events.filter(event => event.event === 'task_ownership_revoked').at(-1);
    const decisions = state.events.filter(event => event.event === 'orchestration_decision_recorded');
    const lastDecision = decisions.at(-1);
    const budget = state.events.filter(event => event.event === 'orchestration_budget_updated').at(-1) || lastDecision?.budget;
    const policy = started?.policy || { max_assignments: 5, max_revisions: 2, token_budget: 1200 };
    const owner = lastDecision?.action === 'STOP' || lastDecision?.action === 'COMPLETE' ? '已释放' : revoked && (!ownership || revoked.sequence > ownership.sequence) ? '已撤销' : ownership?.to_owner || '—';
    byId('orchestration-policy').textContent = started ? `single_owner · ${policy.deadline_ms}ms deadline` : '等待编排策略';
    byId('orchestration-owner').textContent = owner;
    byId('orchestration-action').textContent = lastDecision?.action || '—';
    byId('orchestration-assignments').textContent = `${budget?.assignments || 0} / ${policy.max_assignments}`;
    byId('orchestration-revisions').textContent = `${budget?.revisions || 0} / ${policy.max_revisions}`;
    byId('orchestration-tokens').textContent = `${budget?.tokens_used || 0} / ${policy.token_budget}`;
    const list = byId('orchestration-decisions');
    list.replaceChildren();
    if (!decisions.length) {
      list.append(element('li', '', '运行后逐条显示 ASSIGN、RETURN、REASSIGN、STOP 或 COMPLETE。'));
      return;
    }
    decisions.forEach((decision, index) => {
      const item = element('li');
      item.dataset.action = decision.action;
      item.append(element('b', '', `${String(index + 1).padStart(2, '0')} · ${decision.action}`),
        element('small', '', `${decision.from_owner || 'Supervisor'} → ${decision.to_owner || '释放'} · ${decision.reason}`));
      list.append(item);
    });
  }

  function updatePatternPanel() {
    const panel = byId('pattern-panel');
    if (panel.hidden) return;
    const lesson = lessonForScenario(byId('scenario').value);
    const configs = {
      decomposition: ['GRAPH VALIDATION', 'Orchestrator', '动态 Fan-out / 3-way Join'],
      agent_tool: ['MANAGER CONTROL', 'Manager', '2 bounded specialist calls'],
      observability: ['SLO ENFORCEMENT', 'Risk Controller', 'Root trace / 3 child spans'],
      durable: ['RECOVERY CONTROL', 'Resume Validator', 'Checkpoint / selective resume'],
      saga: ['COMPENSATION CONTROL', 'Saga Coordinator', 'Forward / reverse / reconcile'],
      release: ['RELEASE CONTROL', 'Release Gate', 'Golden / Shadow / 5% Canary'],
    };
    const config = configs[lesson];
    const gate = [...state.events].reverse().find(event => ['task_graph_validated', 'task_graph_rejected', 'agent_tool_scope_rejected', 'manager_synthesis_completed', 'slo_evaluation_completed', 'checkpoint_binding_validated', 'stale_checkpoint_rejected', 'saga_compensated', 'reconciliation_required', 'canary_gate_evaluated', 'release_promoted', 'release_rolled_back'].includes(event.event));
    const active = lesson === 'decomposition' ? state.events.filter(event => event.event === 'dynamic_worker_dispatched').length
      : lesson === 'agent_tool' ? state.events.filter(event => event.event === 'agent_tool_call_started').length
      : lesson === 'observability' ? state.events.filter(event => event.event === 'span_completed').length
      : lesson === 'durable' ? state.events.filter(event => /task_restored|unfinished_task_resumed/.test(event.event)).length
      : lesson === 'saga' ? state.events.filter(event => event.event === 'compensation_applied').length
      : state.events.filter(event => /shadow_run_started|canary_started/.test(event.event)).length;
    const metric = state.events.find(event => event.event === 'telemetry_aggregated')?.metrics;
    byId('pattern-label').textContent = config[0];
    byId('pattern-owner').textContent = config[1];
    byId('pattern-topology').textContent = config[2];
    byId('pattern-active').textContent = `${active} observed`;
    byId('pattern-gate').textContent = !gate ? 'WAITING' : /rejected|reconciliation_required/.test(gate.event) || gate.passed === false ? 'BLOCK' : /rolled_back/.test(gate.event) ? 'ROLLBACK' : 'PASS';
    const sagaTerminal = state.events.find(event => /saga_compensated|reconciliation_required/.test(event.event));
    const releaseGate = state.events.find(event => event.event === 'canary_gate_evaluated');
    byId('pattern-budget').textContent = metric ? `${metric.p95_latency_ms}ms · ${metric.tokens_used} tok` : lesson === 'decomposition' ? '0 workers before gate' : lesson === 'agent_tool' ? 'declared scope only' : lesson === 'observability' ? 'p95 ≤ 1200ms' : lesson === 'durable' ? '0 repeated tool calls' : lesson === 'saga' ? `${sagaTerminal?.open_paper_effects ?? '—'} open paper effects` : `${releaseGate?.metrics?.p95_latency_ms ?? '—'}ms · ${releaseGate?.metrics?.tokens_per_run ?? '—'} tok`;
    const events = state.events.filter(event => /task_graph_|dynamic_|manager_|agent_tool_|span_|slo_|durable_|checkpoint_|task_restored|unfinished_task|resume_|recovery_|saga_|compensation_|reconciliation_|release_|shadow_|canary_/.test(event.event)).slice(-6);
    const list = byId('pattern-events');
    list.replaceChildren();
    (events.length ? events : [{ event: '等待运行', task_id: '—' }]).forEach(event => list.append(element('li', '', `${event.task_id} · ${event.event.replaceAll('_', ' ')}`)));
  }

  function updateStudio() {
    const relevantHandoffs = state.events.map(handoffForEvent).filter(Boolean).filter(handoff => handoff.flow === flowMode);
    for (const role of STUDIO_ROLES) {
      const button = roleElements.get(role.id);
      const roleEvents = state.events.filter(event => roleForEvent(event) === role.id || event.sender_role === role.id || event.recipient_role === role.id);
      const latest = roleEvents.at(-1);
      const status = roleStatus(role);
      button.dataset.status = status;
      button.dataset.flowMuted = String(state.events.length > 0 && !relevantHandoffs.some(handoff => [handoff.from, handoff.to].includes(role.id)));
      button.setAttribute('aria-pressed', String(selectedRole === role.id));
      const statusCopy = { active: '已激活', sending: '正在交接', validating: '独立验约中', ready: '验约通过', completed: '本次已完成', rejected: '已拒绝', failed: '已停止 / 阻断', blocked: '下游未执行', waiting: '等待运行' };
      button.querySelector('.role-state').textContent = statusCopy[status] || status;
      button.querySelector('.role-evidence').textContent = `${roleEvents.length} events`;
      button.querySelector('.role-activity').textContent = latest ? describe(latest).title : role.idle;
    }
    const copy = flowCopy[flowMode];
    byId('flow-route').dataset.flow = flowMode;
    byId('flow-route').querySelector('.route-label').textContent = copy[0];
    byId('flow-route-title').textContent = copy[1];
    byId('flow-route-detail').textContent = copy[2];
    renderHandoffs();
    updateHandoffJourney();
    updateModelInspector();
    updateOrchestration();
    updatePatternPanel();
  }

  function addDetails(row, label, payload) {
    const details = element('details', 'event-details');
    details.append(element('summary', '', label));
    details.addEventListener('toggle', () => {
      if (details.open && !details.querySelector('pre')) details.append(element('pre', '', JSON.stringify(payload, null, 2)));
    });
    row.append(details);
  }
  function addRow(event, view) {
    const row = element('li', 'event-row');
    row.dataset.kind = view.kind;
    row.dataset.node = event.task_id || 'END';
    row.dataset.event = event.event || view.label || '';
    row.dataset.sequence = event.sequence || '';
    const impact = eventImpact(event, view);
    row.dataset.phase = impact.phase.toLowerCase().replace(/\s+/g, '-');
    const metadata = element('div', 'event-meta');
    const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 }) : '';
    metadata.append(element('span', 'event-sequence', event.sequence ? String(event.sequence).padStart(2, '0') : '—'), element('span', 'event-node', event.task_id || 'END'), element('span', 'event-kind', view.label), element('time', 'event-time', time));
    metadata.lastChild.title = event.timestamp || '';
    row.append(metadata, element('div', 'event-title', view.title));
    if (view.description) row.append(element('p', 'event-description', view.description));
    const impactLine = element('div', 'event-impact');
    impactLine.append(element('span', 'impact-phase', impact.phase), element('span', 'impact-state', impact.state), element('span', 'impact-effect', impact.effect));
    row.append(impactLine);
    addDetails(row, view.detailLabel, view.payload);
    byId('event-list').append(row);
    rows.push(row);
  }
  function eventImpact(event, view) {
    const name = event.event || '';
    if (name === 'model_regression_completed') return { phase: 'MODEL EVAL', state: `结果：${event.passed ? 'PASS' : 'REGRESSION'}`, effect: event.passed ? '候选：可继续' : '候选：阻止升级' };
    if (name === 'model_eval_assertion_checked') return { phase: 'ASSERTION', state: `状态：${event.passed ? '通过' : '退化'}`, effect: '副作用：0 次' };
    if (name === 'memory_write_blocked') return { phase: 'PRIVACY GATE', state: '状态：已阻断', effect: `副作用：${event.effect_count} 次` };
    if (name === 'long_term_memory_written') return { phase: 'MEMORY WRITE', state: '状态：已脱敏持久化', effect: '范围：2s10s_preferences' };
    if (name === 'long_term_memory_retrieved') return { phase: 'MEMORY READ', state: '状态：有来源召回', effect: '权限：只读 Context' };
    if (name === 'handoff_rejected') return { phase: 'HANDOFF GATE', state: '状态：接收方拒绝', effect: `副作用：${event.effect_count} 次` };
    if (name === 'handoff_accepted') return { phase: 'HANDOFF', state: '状态：合约已接受', effect: '下游：允许激活' };
    if (name === 'handoff_validation_completed') return { phase: 'CONTRACT', state: `状态：${event.passed ? '通过' : '拒绝'}`, effect: event.passed ? '下游：待激活' : '下游：不启动' };
    if (name === 'orchestration_decision_recorded') return { phase: 'SUPERVISOR', state: `决策：${event.action}`, effect: `Owner：${event.to_owner || '已释放'}` };
    if (name === 'task_ownership_changed') return { phase: 'OWNERSHIP', state: `Owner：${event.to_owner}`, effect: `版本：v${event.ownership_version}` };
    if (name === 'task_returned_for_revision') return { phase: 'REVISION', state: `第 ${event.revision} 次退回`, effect: '下游：重新验约' };
    if (name === 'agent_timeout_detected') return { phase: 'TIMEOUT', state: '状态：未提交输出', effect: '所有权：待撤销' };
    if (name === 'orchestration_loop_detected') return { phase: 'LOOP GUARD', state: `重复：${event.occurrences} 次`, effect: '下游：STOP' };
    if (name === 'orchestration_authority_violation_detected') return { phase: 'AUTHORITY GATE', state: '状态：越权已拒绝', effect: `副作用：${event.effect_count} 次` };
    if (name === 'orchestration_stopped') return { phase: 'SAFE STOP', state: `原因：${event.reason}`, effect: `副作用：${event.effect_count} 次` };
    if (name === 'ledger_mismatch_detected') return { phase: 'RECONCILIATION FAILURE', state: '状态：账本不一致', effect: '下游：E1 被阻断' };
    if (name === 'ledger_reconciliation_completed') return { phase: 'RECONCILIATION', state: '状态：已对账', effect: `事件：${event.event_count ?? 0} 个` };
    if (name === 'ledger_event_appending' || name === 'ledger_event_appended') return { phase: 'PERSIST', state: `状态：${event.event_type}`, effect: '副作用：纸面账本 · fsync' };
    if (name === 'ledger_snapshot_rebuilt' || name === 'ledger_reconciliation_started') return { phase: 'RECONCILIATION', state: '状态：重建比较', effect: '结果：可复算' };
    if (name === 'ledger_replay_started') return { phase: 'PROCESS', state: '状态：重放中', effect: '边界：不调用外部 Tool' };
    if (name === 'outbox_ack_lost') return { phase: 'FAILURE WINDOW', state: '状态：待恢复', effect: '副作用：可能已发生' };
    if (name === 'outbox_effect_deduplicated') return { phase: 'RECOVERY', state: '状态：已去重', effect: `副作用：${event.effect_count ?? 1} 次` };
    if (name === 'outbox_effect_applied') return { phase: 'SIDE EFFECT', state: '状态：已写入', effect: `副作用：${event.effect_count ?? 1} 次` };
    if (name === 'outbox_side_effect_blocked' || name === 'capability_rejected' || name === 'lease_side_effect_blocked') return { phase: 'GUARD', state: '状态：已阻断', effect: '副作用：0 次' };
    if (name === 'tool_execution_failed' || name === 'task_failed' || name === 'admission_rejected' || name === 'circuit_call_rejected' || name === 'run_stopped') return { phase: 'FAILURE', state: `状态：${event.retryable ? '可重试' : '失败'}`, effect: '下游：停止或等待' };
    if (name === 'tool_retry_scheduled') return { phase: 'RETRY', state: `状态：attempt ${event.next_attempt}`, effect: `等待：${event.delay_ms ?? 0}ms` };
    if (name === 'eval_completed') return { phase: 'RESULT', state: `Eval：${event.passed ? 'PASS' : 'FAIL'}`, effect: '边界：仅模拟' };
    if (name === 'run_completed' || view.kind === 'result') return { phase: 'RESULT', state: '终态：已完成', effect: '下游：全部收束' };
    if (name === 'outbox_enqueued') return { phase: 'PROCESS', state: '状态：已入队', effect: '副作用：尚未发送' };
    if (name === 'outbox_dispatch_started') return { phase: 'PROCESS', state: `状态：attempt ${event.attempt}`, effect: '副作用：等待确认' };
    if (name === 'task_started' || name === 'tool_execution_started' || name === 'eval_started') return { phase: 'PROCESS', state: '状态：运行中', effect: '边界：调用进行中' };
    return { phase: view.kind === 'error' ? 'FAILURE' : 'OBSERVATION', state: '状态：已记录', effect: '结果：保留在 Trace' };
  }
  function updateOverview() {
    const eventCount = state.events.length;
    const selectedScenario = byId('scenario').value;
    const selectedLesson = advancedScenarios.has(selectedScenario) ? lessonForScenario(selectedScenario) : null;
    const frameCount = state.runId ? eventCount + 1 + (state.terminal ? 1 : 0) : 0;
    const attempts = state.events.filter(event => ['tool_execution_started', 'outbox_dispatch_started'].includes(event.event)).length;
    const effectEvent = [...state.events].reverse().find(event => Number.isFinite(event.effect_count));
    const effectCount = effectEvent ? String(effectEvent.effect_count) : '—';
    const outcome = state.phase === 'completed' ? 'PASS' : state.phase === 'failed' ? 'FAIL' : state.terminal ? state.phase.toUpperCase() : '—';
    byId('overview-mode').textContent = state.replayed ? 'REPLAY · READ ONLY' : inFlight ? 'LIVE · RECORDING' : state.runId ? 'LIVE · RECORDED' : '等待运行';
    const ledger = state.result?.paper_ledger;
    const executionResult = state.result?.execution;
    const raceDemo = executionResult?.artifact_type === 'paper_execution_projection';
    if (selectedLesson) byId('overview-title').textContent = lessonCopy[selectedLesson].title.split(' · ')[0];
    byId('overview-change').textContent = state.replayed
      ? '当前展示的是已持久化历史；页面只重建状态，不重新调用 Tool。'
      : selectedLesson
        ? lessonCopy[selectedLesson].overview
      : raceDemo
        ? '新增边界：取消请求不会抹掉取消确认前已经发生的成交；fill_id 重复回报只保留一次副作用。'
        : '新增边界：LG1 从纸面账本重放重建 P&L，再与 S1 对账；不一致时阻断 E1。';
    byId('frame-count').textContent = frameCount;
    byId('attempt-count').textContent = attempts;
    byId('side-effect-count').textContent = effectCount;
    byId('outcome-label').textContent = outcome;
    const steps = { persist: state.runId ? (eventCount ? 'completed' : 'active') : '', deliver: eventCount ? (inFlight ? 'active' : 'completed') : '', observe: eventCount ? (state.terminal ? 'completed' : 'active') : '', replay: state.replayed ? 'completed' : '' };
    Object.entries(steps).forEach(([id, status]) => { const node = byId(`capability-${id}`); node.classList.remove('active', 'completed'); if (status) node.classList.add(status); });
    const outcomePanel = byId('stream-outcome');
    outcomePanel.hidden = !state.runId;
    const regression = state.events.find(event => event.event === 'model_regression_completed' && !event.passed);
    byId('outcome-title').textContent = state.replayed ? 'Replay completed · same run, no Tool call' : regression ? 'Regression detected · candidate blocked' : state.phase === 'paused' ? 'Checkpoint committed · restart available' : state.phase === 'completed' ? 'Run completed · Eval passed' : state.phase === 'failed' ? 'Run failed · inspect the boundary below' : 'Run in progress';
    const last = state.events.at(-1);
    byId('outcome-detail').textContent = last ? `${last.task_id || 'Runtime'} · ${last.event} · sequence ${last.sequence}` : '等待第一条真实事件';
    if (byId('ledger-status')) {
      const mismatch = state.events.find(event => event.event === 'ledger_mismatch_detected');
      byId('ledger-status').textContent = mismatch ? 'MISMATCH · E1 BLOCKED' : ledger?.status || (state.nodes.LG1 === 'completed' ? 'RECONCILED' : '等待 LG1');
      byId('ledger-status').dataset.state = mismatch ? 'error' : ledger?.passed ? 'pass' : '';
      const diff = mismatch?.differences || ledger?.differences || [];
      byId('ledger-diff').textContent = diff.length ? diff.map(item => `${item.field}: ${item.expected} → ${item.replayed}`).join(' · ') : 'Expected = Replayed · 无差异';
    }
    if (raceDemo && byId('ledger-status')) {
      const stateLabel = executionResult.state === 'CANCELED' ? 'RACE RESOLVED' : executionResult.state;
      byId('ledger-status').textContent = stateLabel + ' · FILLED ' + executionResult.filled_quantity + ' / CANCELED ' + executionResult.canceled_quantity;
      byId('ledger-status').dataset.state = 'pass';
      byId('ledger-diff').textContent = 'requested ' + executionResult.requested_quantity + ' · remaining ' + executionResult.remaining_quantity + ' · events ' + executionResult.event_count;
    }
    const paperTrade = state.result?.paper_trade;
    if (paperTrade && byId('ledger-status')) {
      byId('ledger-status').textContent = paperTrade.status + ' · MATCHED ' + paperTrade.risk.matched_quantity + ' · REALIZED P&L ' + paperTrade.pnl.realized_pnl;
      byId('ledger-status').dataset.state = state.result?.eval?.passed ? 'pass' : 'error';
      byId('ledger-diff').textContent = 'target ' + paperTrade.target_quantity + ' · events ' + paperTrade.event_count + ' · leg risk ' + paperTrade.risk.leg_risk_quantity;
    }
    const paperPortfolio = state.result?.paper_portfolio;
    if (paperPortfolio && byId('ledger-status')) {
      const summary = paperPortfolio.summary;
      byId('ledger-status').textContent = paperPortfolio.risk_status + ' · 2S10S OPEN ' + summary.open_curve_trade_count + ' · NET DV01 ' + summary.net_parallel_dv01_usd_per_bp + ' USD/bp';
      byId('ledger-status').dataset.state = state.result?.eval?.passed ? 'pass' : 'error';
      byId('ledger-diff').textContent = 'gross DV01 ' + summary.gross_dv01_usd_per_bp + ' USD/bp · limits ' + paperPortfolio.violations.length + ' · realized P&L ' + summary.realized_pnl_usd;
    }
    const advancedResult = state.result && ['rate_model_eval_lesson', 'rate_memory_lesson', 'rate_multi_agent_handoff_lesson', 'rate_supervisor_orchestration_lesson', 'rate_dynamic_task_graph_lesson', 'rate_agent_as_tool_lesson', 'rate_observability_slo_lesson', 'rate_durable_workflow_lesson', 'rate_saga_compensation_lesson', 'rate_agent_release_lesson'].includes(state.result.artifact_type) ? state.result : null;
    if (advancedResult && byId('ledger-status')) {
      const regressions = advancedResult.eval.regressions || [];
      const checks = Object.entries(advancedResult.eval.checks || {});
      const evalLabels = { rate_model_eval_lesson: 'MODEL EVAL', rate_memory_lesson: 'MEMORY EVAL', rate_multi_agent_handoff_lesson: 'HANDOFF EVAL', rate_supervisor_orchestration_lesson: 'ORCHESTRATION EVAL', rate_dynamic_task_graph_lesson: 'GRAPH EVAL', rate_agent_as_tool_lesson: 'DELEGATION EVAL', rate_observability_slo_lesson: 'SLO EVAL', rate_durable_workflow_lesson: 'RECOVERY EVAL', rate_saga_compensation_lesson: 'SAGA EVAL', rate_agent_release_lesson: 'RELEASE EVAL' };
      byId('check-label').textContent = evalLabels[advancedResult.artifact_type];
      const waitingRestart = advancedResult.status === 'WAITING_FOR_RESTART';
      byId('ledger-status').textContent = waitingRestart ? 'CHECKPOINT COMMITTED · WAITING RESTART' : advancedResult.eval.passed ? 'PASS · CONTRACT PRESERVED' : 'REGRESSION · CANDIDATE BLOCKED';
      byId('ledger-status').dataset.state = waitingRestart ? '' : advancedResult.eval.passed ? 'pass' : 'error';
      byId('ledger-diff').textContent = regressions.length ? regressions.join(' · ') : checks.map(([name, passed]) => `${passed ? '✓' : '✂'} ${name}`).join(' · ');
    }
  }
  function update() {
    for (const [id, button] of nodeElements) {
      button.dataset.status = state.nodes[id];
      button.setAttribute('aria-pressed', String(filter === id));
      const statusLabel = id === 'J1' && state.nodes.J1 === 'waiting' ? `等待 ${state.join.completed.length}/2` : labels[state.nodes[id]];
      button.querySelector('.node-status').textContent = statusLabel;
      button.setAttribute('aria-label', `${id} ${definitions().find(n => n.id === id).title} · ${statusLabel} · 筛选事件`);
    }
    edgeElements.forEach(edge => { edge.element.dataset.active = String(state.nodes[edge.from] === 'completed' && !['waiting', 'blocked'].includes(state.nodes[edge.to])); });
    const phases = { idle: 'Ready to run', connecting: 'Connecting', running: 'Agent running', paused: 'Checkpoint saved · waiting restart', completed: 'Run completed', failed: 'Run failed', cancelling: 'Stopping · 等待确认', cancelled: 'Run cancelled', timed_out: 'Run timed out' };
    byId('run-status').dataset.phase = state.phase;
    byId('run-status').querySelector('span').textContent = phases[state.phase];
    byId('run-id').textContent = state.runId || (inFlight ? '正在连接 Runtime…' : '等待开始一次运行');
    byId('run-budget').textContent = `运行预算 ${(state.budgetMs ?? scenarioBudget()) / 1000}s`;
    byId('event-count').textContent = state.events.length;
    byId('empty-state').hidden = rows.length > 0 || !!filter;
    const roleFilter = selectedRole ? STUDIO_ROLES.find(role => role.id === selectedRole) : null;
    byId('stream-scope').textContent = roleFilter ? `${roleFilter.name} · ${roleFilter.tasks.join(' / ')}` : filter ? `${filter} · ${definitions().find(n => n.id === filter).title}` : `全部节点 · 调用 · 结果${state.activeTasks.length ? ` · 活跃 ${state.activeTasks.length}` : ''}`;
    byId('clear-filter').hidden = !filter && !roleFilter;
    rows.forEach(row => {
      row.hidden = roleFilter ? !roleFilter.tasks.includes(row.dataset.node) : !!filter && row.dataset.node !== filter && !(filter === 'R1' && row.dataset.node === 'END');
    });
    byId('filter-empty').hidden = (!filter && !roleFilter) || rows.some(row => !row.hidden);
    byId('download').disabled = !state.events.length;
    byId('replay-button').hidden = !state.terminal || state.phase === 'paused' || !state.runId || inFlight;
    byId('replay-button').disabled = inFlight;
    byId('run-button').disabled = inFlight;
    byId('restart-checkpoint-button').hidden = !pendingCheckpoint;
    byId('restart-checkpoint-button').disabled = inFlight;
    byId('restart-checkpoint-button').textContent = resumingCheckpoint ? '正在从断点重启…' : '↻ 从断点重启';
    byId('stop-button').hidden = !inFlight || state.terminal || !state.cancelSupported;
    byId('stop-button').disabled = cancelPending || state.phase === 'cancelling';
    byId('stop-button').textContent = state.phase === 'cancelling' ? '停止中…' : cancelPending ? '已请求…' : 'Stop';
    byId('scenario').disabled = inFlight;
    const approval = state.approval;
    byId('approval-panel').hidden = !approval?.pending;
    if (approval?.pending) {
      byId('approval-tool').textContent = `${approval.tool_name} · ${approval.scope}`;
      byId('approval-fingerprint').textContent = `参数指纹 ${approval.arguments_sha256.slice(0, 16)}… · 仅当前 Run · Paper only`;
    }
    byId('run-button').textContent = inFlight ? '运行中…' : state.terminal ? '↻  Run again' : '▶  Run Agent';
    for (const input of byId('parameters').elements) input.disabled = inFlight;
    byId('stream-footer').textContent = state.phase === 'failed' ? (state.error?.message || 'E1 评估未通过，详见结果') : ['cancelled', 'timed_out'].includes(state.phase) ? '所有 Tool 已退出 · 已完成节点保留 · 下游未继续' : state.phase === 'cancelling' ? '停止请求已发出；事件流保持连接，等待 Tool 确认' : state.phase === 'paused' ? 'Checkpoint 已持久化 · 点击“从断点重启”开启新的恢复请求' : state.phase === 'completed' ? (state.replayed ? '历史事件已重放 · 未重新调用 Tool' : '事件流已完成 · 完整输入与输出已保留') : cancelNote || (inFlight ? '连接保持中 · 等待下一条真实事件' : '准备接收真实运行事件');
    updateLessonOutcome();
    updateOverview();
    updateStudio();
  }
  function scrollToLatest() {
    if (byId('follow').checked) byId('stream-scroll').scrollTop = byId('stream-scroll').scrollHeight;
  }
  function releaseRunControls() {
    inFlight = false;
    byId('run-button').disabled = false;
    byId('scenario').disabled = false;
    for (const input of byId('parameters').elements) input.disabled = false;
    byId('run-button').textContent = state.terminal ? '↻  Run again' : '▶  Run Agent';
  }
  function showSource(data) {
    if (!data) return;
    byId('source-note').textContent = `${data.provider || '公开利率数据'} · ${data.source_freshness === 'SNAPSHOT' ? '离线快照（非实时）' : data.source_freshness || '来源见结果'} · 截至 ${data.as_of || '未知'}`;
  }
  function receive(message) {
    const oldMode = state.mode;
    applyMessage(state, message);
    if (oldMode !== state.mode) buildGraph();
    if (message.type === 'event') {
      addRow(message.event, describe(message.event));
      if (message.event.event === 'tool_observation' && message.event.task_id === 'D1') showSource(message.event.output);
    } else if (message.type === 'result') {
      state.result = message.result;
      if (state.phase === 'paused') pendingCheckpoint = { runId: message.result.run_id, scenario: message.result.scenario };
      else if (message.result.resume_of_run_id) pendingCheckpoint = null;
      const paused = state.phase === 'paused';
      addRow({ task_id: 'END' }, { kind: paused ? 'control' : state.phase === 'completed' ? 'result' : 'error', label: paused ? 'CHECKPOINT READY' : 'RUN RESULT', title: paused ? '等待手动从断点重启' : state.phase === 'completed' ? 'Run completed · Eval passed' : 'Run completed · Eval failed', description: paused ? '第一段请求已经结束；恢复必须由新的 HTTP 请求显式触发。' : '最终产物包含完整 Plan、Trace、数据、模拟与 Eval。', detailLabel: '完整运行结果 · JSON', payload: message.result });
    } else if (message.type === 'error') showError();
    update();
    scrollToLatest();
  }
  function showError() {
    const stopped = ['cancelled', 'timed_out'].includes(state.phase);
    addRow({ task_id: state.error?.task_id || state.activeTask || 'END' }, { kind: stopped ? 'control' : 'error', label: stopped ? 'RUN STOPPED' : 'RUN ERROR', title: state.error?.code || 'Stream interrupted', description: state.error?.message || '运行失败', detailLabel: '完整运行终态', payload: state.error });
  }
  async function requestStop() {
    const runId = state.runId;
    if (!runId || !inFlight || state.terminal || cancelPending) return;
    cancelPending = true;
    cancelNote = '正在提交停止请求；不会关闭事件流。';
    update();
    try {
      const response = await fetch('/api/rates/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: runId }) });
      const body = await response.json();
      if (state.runId !== runId || state.terminal) return;
      if (response.status === 409) cancelNote = '运行已结束，等待最后的流式消息。';
      else if (!response.ok || !body.control?.accepted) throw new Error(body.error?.message || '停止请求未被确认');
      else cancelNote = '停止请求已接受，等待 Tool 退出确认。';
    } catch (error) {
      if (state.runId !== runId || state.terminal) return;
      cancelPending = false;
      cancelNote = `取消尚未确认：${error.message}；可以重试。`;
    } finally {
      if (state.runId === runId) update();
    }
  }
  async function decideApproval(decision) {
    if (!state.approval?.pending || !state.runId) return;
    byId('approve-button').disabled = true;
    byId('deny-button').disabled = true;
    try {
      const response = await fetch('/api/rates/approval', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: state.runId, decision }) });
      const body = await response.json();
      if (!response.ok || !body.approval?.accepted) throw new Error(body.error?.message || body.approval?.reason || '审批未被接受');
    } catch (error) {
      byId('stream-footer').textContent = `审批失败：${error.message}`;
      byId('approve-button').disabled = false;
      byId('deny-button').disabled = false;
    }
  }
  async function consume(response) {
    if (!response.body || !response.headers.get('Content-Type')?.includes('application/x-ndjson')) throw new Error('服务未返回 NDJSON 事件流。');
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8', { fatal: true });
    let buffer = '';
    const parse = () => {
      let newline;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line) receive(JSON.parse(line));
      }
    };
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      parse();
    }
    buffer += decoder.decode();
    parse();
    if (buffer.trim()) receive(JSON.parse(buffer));
    finishStream(state);
    reader.releaseLock();
  }
  async function run() {
    if (inFlight) return;
    const form = byId('parameters');
    if (!form.checkValidity()) { byId('settings').open = true; form.reportValidity(); return; }
    const config = Object.fromEntries(new FormData(form).entries());
    const enteredModelApiKey = String(config.model_api_key || '').trim();
    const modelApiKey = enteredModelApiKey || readSessionKey();
    delete config.model_api_key;
    for (const key of ['lookback_days', 'entry_z', 'holding_days', 'dv01_usd_per_bp', 'round_trip_cost_bps']) config[key] = Number(config[key]);
    config.demo_scenario = byId('scenario').value;
    config.execution_mode = modeForScenario(config.demo_scenario);
    config.budget_ms = scenarioBudget();
    if (['model_live', 'intent_live'].includes(config.demo_scenario)) {
      if (!modelApiKey) {
        byId('settings').open = true;
        byId('model-api-key').focus();
        return;
      }
      if (enteredModelApiKey) writeSessionKey(enteredModelApiKey);
      config.model_api_key = modelApiKey;
      byId('model-api-key').value = '';
      updateKeyStatus();
    }
    cancelPending = false;
    cancelNote = '';
    pendingCheckpoint = null;
    resumingCheckpoint = false;
    inFlight = true;
    try {
      state = createState(config.execution_mode);
      state.phase = 'connecting';
      filter = null;
      selectedRole = null;
      rows.length = 0;
      byId('event-list').replaceChildren();
      byId('settings').open = false;
      byId('follow').checked = true;
      byId('source-note').textContent = sourceNote(config.demo_scenario);
      buildGraph();
      update();
      const endpoint = advancedScenarios.has(config.demo_scenario) ? '/api/rates/advanced-lesson' : config.demo_scenario === 'execution_race' ? '/api/rates/execution-race' : config.demo_scenario === 'paper_fill_accounting' ? '/api/rates/paper-fill' : config.demo_scenario === 'paper_portfolio_risk' ? '/api/rates/paper-portfolio' : '/api/rates/stream';
      const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' }, body: JSON.stringify(config) });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error?.message || `HTTP ${response.status}`);
      }
      await consume(response);
    } catch (error) {
      failState(state, { code: 'STREAM_ERROR', message: error.message, task_id: state.activeTask });
      showError();
    } finally {
      releaseRunControls();
      try {
        update();
        scrollToLatest();
        if (state.terminal) byId('lesson-outcome-banner').scrollIntoView({ behavior: 'smooth', block: 'center' });
      } finally {
        releaseRunControls();
      }
    }
  }
  async function resumeFromCheckpoint() {
    if (inFlight || !pendingCheckpoint) return;
    const checkpoint = { ...pendingCheckpoint };
    inFlight = true;
    resumingCheckpoint = true;
    filter = null;
    selectedRole = null;
    rows.length = 0;
    byId('event-list').replaceChildren();
    try {
      state = createState('durable');
      state.phase = 'connecting';
      buildGraph();
      update();
      const response = await fetch('/api/rates/durable-resume', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' }, body: JSON.stringify({ checkpoint_run_id: checkpoint.runId, demo_scenario: checkpoint.scenario }) });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error?.message || `HTTP ${response.status}`);
      }
      await consume(response);
    } catch (error) {
      failState(state, { code: 'RESUME_ERROR', message: error.message, task_id: 'RV1' });
      showError();
    } finally {
      inFlight = false;
      resumingCheckpoint = false;
      update();
      scrollToLatest();
      if (state.terminal) byId('lesson-outcome-banner').scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
  async function replayLast() {
    if (inFlight || !state.runId || !state.terminal) return;
    const runId = state.runId;
    const replayMode = state.mode;
    inFlight = true;
    cancelPending = false;
    cancelNote = '';
    filter = null;
    selectedRole = null;
    rows.length = 0;
    byId('event-list').replaceChildren();
    try {
      state = createState(replayMode);
      state.phase = 'connecting';
      buildGraph();
      update();
      const response = await fetch('/api/rates/replay', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' }, body: JSON.stringify({ run_id: runId, after_sequence: 0 }) });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error?.message || `HTTP ${response.status}`);
      }
      await consume(response);
    } catch (error) {
      failState(state, { code: 'REPLAY_ERROR', message: error.message, task_id: state.activeTask });
      showError();
    } finally {
      releaseRunControls();
      try {
        update();
        scrollToLatest();
        if (state.terminal) byId('lesson-outcome-banner').scrollIntoView({ behavior: 'smooth', block: 'center' });
      } finally {
        releaseRunControls();
      }
    }
  }
  byId('run-button').addEventListener('click', run);
  byId('restart-checkpoint-button').addEventListener('click', resumeFromCheckpoint);
  byId('replay-button').addEventListener('click', replayLast);
  byId('stop-button').addEventListener('click', requestStop);
  byId('approve-button').addEventListener('click', () => decideApproval('approve'));
  byId('deny-button').addEventListener('click', () => decideApproval('deny'));
  byId('forget-model-key').addEventListener('click', clearSessionKey);
  byId('load-archive-scenario').addEventListener('click', selectArchivedScenario);
  byId('scenario').addEventListener('change', () => {
    if (byId('scenario').value.startsWith('handoff_') || byId('scenario').value.startsWith('orchestration_')) {
      flowMode = 'decision';
      document.querySelectorAll('.flow-tab').forEach(tab => {
        const selected = tab.dataset.flow === flowMode;
        tab.classList.toggle('active', selected);
        tab.setAttribute('aria-selected', String(selected));
      });
    }
    if (!inFlight) {
      pendingCheckpoint = null;
      resumingCheckpoint = false;
      state = createState(modeForScenario(byId('scenario').value));
      filter = null;
      selectedRole = null;
      rows.length = 0;
      byId('event-list').replaceChildren();
      buildGraph();
    }
    updateLessonUI();
    update();
  });
  byId('parameters').addEventListener('submit', event => { event.preventDefault(); run(); });
  byId('clear-filter').addEventListener('click', () => { filter = null; selectedRole = null; update(); });
  document.querySelectorAll('.flow-tab').forEach(button => button.addEventListener('click', () => {
    flowMode = button.dataset.flow;
    document.querySelectorAll('.flow-tab').forEach(tab => {
      const selected = tab === button;
      tab.classList.toggle('active', selected);
      tab.setAttribute('aria-selected', String(selected));
    });
    updateStudio();
  }));
  byId('follow').addEventListener('change', scrollToLatest);
  // Reading older events should never be interrupted by automatic scrolling.
  byId('stream-scroll').addEventListener('wheel', event => { if (event.deltaY < 0) byId('follow').checked = false; }, { passive: true });
  byId('stream-scroll').addEventListener('touchmove', () => { byId('follow').checked = false; }, { passive: true });
  byId('stream-scroll').addEventListener('keydown', event => { if (['ArrowUp', 'PageUp', 'Home'].includes(event.key)) byId('follow').checked = false; });
  byId('download').addEventListener('click', () => {
    const artifact = state.result || { run_id: state.runId, status: state.phase, trace: state.events, error: state.error };
    const url = URL.createObjectURL(new Blob([JSON.stringify(artifact, null, 2)], { type: 'application/json' }));
    const link = element('a');
    link.href = url;
    link.download = `${state.runId || 'agent-run'}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  updateKeyStatus();
  updateLessonUI();
  update();
})();
