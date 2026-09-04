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
    { id: 'CT1', title: 'Context builder', description: '筛选 · 冲突消解 · 压缩 · 打包' },
    { id: 'MR1', title: 'Model router', description: '选路 · token 预算 · 有界 fallback' },
    { id: 'M1', title: 'Model gateway', description: '生成提议 · 无执行权限' },
    NODES[1],
    { id: 'R1', title: 'Runtime', description: '调度 · 容错 · 单线程归集事件' },
    { id: 'C1', title: 'Circuit breaker', description: '连续失败时阻止新 Tool 调用' },
    NODES[3],
    { id: 'V1', title: 'Observation gate', description: '不通过 ↺ P1 · 通过 ↓ Q1' },
    { id: 'Q1', title: 'Admission queue', description: '限速 · 有界排队 · 过载拒绝' },
    { id: 'A2', title: '2Y series', description: 'Tool · 校验 2Y 序列' },
    { id: 'A10', title: '10Y series', description: 'Tool · 校验 10Y 序列' },
    { id: 'J1', title: 'Join', description: '两个分支均成功才放行' },
    ...NODES.slice(4)
  ];
  const PARALLEL_ROWS = [['G1'], ['RG1'], ['CG1'], ['CT1'], ['MR1'], ['M1'], ['P1'], ['R1'], ['C1'], ['D1'], ['V1'], ['Q1'], ['A2', 'A10'], ['J1'], ['S1'], ['E1']];
  function createState(mode = 'serial') {
    const definitions = mode === 'parallel' ? PARALLEL_NODES : NODES;
    return { mode, phase: 'idle', runId: null, events: [], nodes: Object.fromEntries(definitions.map(n => [n.id, 'waiting'])), activeTasks: [], activeTask: null, join: { completed: [], waitingFor: ['A2', 'A10'], required: 2 }, result: null, error: null, terminal: false, stopConfirmed: false, stopReason: null, cancelSupported: false, budgetMs: null };
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
      case 'retrieval_bypassed': state.nodes.RG1 = 'completed'; break;
      case 'retrieval_query_created': state.nodes.RG1 = 'retrieving'; break;
      case 'retrieval_candidate_scored': state.nodes.RG1 = 'ranking'; break;
      case 'retrieval_topk_selected': state.nodes.RG1 = 'topk'; break;
      case 'retrieval_completed': state.nodes.RG1 = 'completed'; break;
      case 'citation_gate_bypassed': state.nodes.CG1 = 'completed'; break;
      case 'citation_gate_started': state.nodes.CG1 = 'verifying'; break;
      case 'citation_checked': state.nodes.CG1 = event.passed ? 'verifying' : 'rejected'; break;
      case 'citation_gate_completed': state.nodes.CG1 = event.passed ? 'completed' : 'failed'; break;
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
      case 'plan_created': state.nodes.P1 = 'completed'; break;
      case 'runtime_started': state.nodes.R1 = 'running'; break;
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
      case 'run_completed': state.nodes.R1 = 'completed'; break;
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
      state.cancelSupported = message.cancel_supported === true;
      state.budgetMs = message.budget_ms ?? null;
    } else {
      if (!state.runId || message.run_id !== state.runId) throw new Error('流式消息来自不同的运行。');
      if (message.type === 'event') applyEvent(state, message.event);
      else if (message.type === 'result') {
        if (state.stopReason) throw new Error('停止请求后不能接受成功结果。');
        const result = message.result;
        if (!result || result.run_id !== state.runId || !Array.isArray(result.trace) || JSON.stringify(result.trace) !== JSON.stringify(state.events) || state.events.at(-1)?.event !== 'run_completed') throw new Error('最终结果与已接收的事件流不一致。');
        state.result = result;
        state.phase = result.eval?.passed === true ? 'completed' : 'failed';
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
      case 'retrieval_bypassed': return { ...common, kind: 'retrieval', label: 'RETRIEVER', title: 'Retrieval bypassed', description: event.reason };
      case 'retrieval_query_created': return { ...common, kind: 'retrieval', label: 'QUERY', title: event.query, description: `确定性 lexical retrieval · Top-K ${event.top_k} · 语料 ${event.corpus_size} chunks · 无伪造 embedding`, detailLabel: 'Query 与检索配置', payload: event };
      case 'retrieval_candidate_scored': return { ...common, kind: 'retrieval', label: 'RANK', title: `#${event.rank} ${event.chunk_id} · ${event.lexical_score}`, description: `${event.matched_terms.join(', ') || '无匹配词'}${event.selected_top_k ? ' · 进入 Top-K' : ' · 未进入 Top-K'}`, detailLabel: '完整 Chunk、来源与内容哈希', payload: event };
      case 'retrieval_topk_selected': return { ...common, kind: 'retrieval', label: 'TOP-K', title: `${event.selected_chunk_ids.length}/${event.top_k} chunks selected`, description: event.selected_chunk_ids.join(' · '), detailLabel: '候选引用', payload: event };
      case 'retrieval_completed': return { ...common, kind: 'retrieval', label: 'RETRIEVED', title: `${event.result_count} chunks forwarded`, description: '这只是检索候选；尚未通过来源门禁。' };
      case 'citation_gate_bypassed': return { ...common, kind: 'retrieval', label: 'SOURCE GATE', title: 'Citation gate bypassed', description: event.reason };
      case 'citation_gate_started': return { ...common, kind: 'retrieval', label: 'SOURCE GATE', title: `${event.candidate_count} citations under review`, description: `必须覆盖 ${event.required_series.join(' + ')}，且来源域名、版本、内容哈希完整。`, detailLabel: '门禁规则', payload: event };
      case 'citation_checked': return { ...common, kind: event.passed ? 'retrieval' : 'error', label: event.passed ? 'CITATION PASS' : 'CITATION REJECT', title: `${event.chunk_id} · ${event.domain || 'no source domain'}`, description: event.passed ? `${event.citation_id} · ${event.series.join(' + ')}` : event.reasons.join(' · '), detailLabel: '引用验证结果', payload: event };
      case 'citation_gate_completed': return { ...common, kind: event.passed ? 'result' : 'error', label: event.passed ? 'EVIDENCE READY' : 'ABSTAIN', title: event.passed ? `${event.accepted_citation_ids.length} verified citations` : `Missing ${event.missing_series.join(' + ')}`, description: event.passed ? `覆盖 ${event.coverage.join(' + ')}，允许进入 CT1。` : '证据不完整；CT1、模型、Runtime 与 Tools 都不会启动。', detailLabel: '来源门禁终态', payload: event };
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
      case 'plan_parse_started': return { ...common, kind: 'model', label: 'PARSE', title: 'Parse model output as JSON', description: '解析只证明 JSON 可读，不代表内容安全。' };
      case 'plan_parse_failed': return { ...common, kind: 'error', label: 'PARSE FAILED', title: event.error_type, description: event.error_message, detailLabel: '损坏的原始输出', payload: event.raw_output };
      case 'model_repair_requested': return { ...common, kind: 'model', label: 'REPAIR 1/1', title: 'Request one bounded format repair', description: '只修复输出格式；不扩大 Tool 权限。', detailLabel: '修复约束', payload: event };
      case 'plan_parsed': return { ...common, kind: 'model', label: 'JSON', title: 'Proposal parsed', description: '进入 Runtime 校验；仍不可执行。', detailLabel: '解析后的提议', payload: event.proposal };
      case 'plan_validation_started': return { ...common, kind: 'model', label: 'AUTHORITY', title: 'Runtime validates proposal', description: event.checks.join(' · '), detailLabel: '校验项目', payload: event.checks };
      case 'plan_validation_completed': return { ...common, kind: event.accepted ? 'result' : 'error', label: event.accepted ? 'PLAN ACCEPTED' : 'PLAN REJECTED', title: event.accepted ? 'Runtime permits execution' : 'Runtime refuses execution', description: event.accepted ? 'Schema、Tool allowlist、DAG、paper-only 与执行模板全部通过。' : event.reasons.join(' · '), detailLabel: '完整校验结果', payload: event.output || event.reasons };
      case 'model_plan_accepted': return { ...common, kind: 'model', label: 'BOUNDARY', title: 'Proposal promoted to executable Plan', description: '决定权属于 Runtime，不属于模型。', detailLabel: '获准执行的提议', payload: event.proposal };
      case 'model_plan_rejected': return { ...common, kind: 'error', label: 'ABSTAIN', title: 'Unsafe proposal stopped before Runtime', description: event.reasons.join(' · '), detailLabel: '拒绝原因', payload: event.reasons };
      case 'plan_created': return { ...common, title: 'Plan created', description: event.graph ? 'C1 保护 D1；V1 验证 Observation；Q1 控制分支准入' : '固定计划 · D1 → S1，随后 E1 校验', detailLabel: '完整计划与依赖' };
      case 'runtime_started': return { ...common, title: 'Runtime started', description: '从 Tool Registry 解析能力，并执行参数校验和重试策略。', detailLabel: 'Runtime 与 Tool Registry' };
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
  return { NODES, PARALLEL_NODES, PARALLEL_ROWS, createState, applyMessage, finishStream, failState, describe };
});
