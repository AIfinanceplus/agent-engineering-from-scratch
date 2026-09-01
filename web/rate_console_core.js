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
    ...NODES.slice(0, 2),
    { id: 'R1', title: 'Runtime', description: '调度并发 · 单线程归集事件' },
    NODES[3],
    { id: 'A2', title: '2Y series', description: 'Tool · 校验 2Y 序列' },
    { id: 'A10', title: '10Y series', description: 'Tool · 校验 10Y 序列' },
    { id: 'J1', title: 'Join', description: '两个分支均成功才放行' },
    ...NODES.slice(4)
  ];
  const PARALLEL_ROWS = [['G1'], ['P1'], ['R1'], ['D1'], ['A2', 'A10'], ['J1'], ['S1'], ['E1']];
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
      case 'plan_created': return { ...common, title: 'Plan created', description: event.graph ? 'D1 → A2 / A10 并发 → J1 汇合 → S1 → E1' : '固定计划 · D1 → S1，随后 E1 校验', detailLabel: '完整计划与依赖' };
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
      case 'parallel_group_started': return { ...common, label: 'FAN-OUT', title: 'Concurrent branches dispatched', description: `${event.task_ids.join(' + ')} · 最多 ${event.max_workers} 个 worker` };
      case 'join_waiting': return { ...common, label: 'JOIN', title: `Join · ${event.completed_dependencies.length}/${event.required} ready`, description: event.waiting_for.length ? `等待 ${event.waiting_for.join(' + ')}；尚未调用下游 Tool` : '两边均成功，准备放行' };
      case 'join_released': return { ...common, kind: 'result', label: 'FAN-IN', title: 'Join released · 2/2', description: '两个依赖均成功，现在才允许汇合与策略计算。' };
      case 'join_blocked': return { ...common, kind: 'error', label: 'JOIN BLOCKED', title: 'Join will not run', description: `失败分支：${event.failed_dependencies.join(', ')}；等待已运行的只读分支结束，不执行下游。` };
      case 'task_failed': return { ...common, kind: 'error', label: 'NODE FAILED', title: event.error_type, description: event.error_message };
      case 'task_blocked': return { ...common, label: 'BLOCKED', title: 'Node not executed', description: event.reason };
      case 'demo_scenario_selected': return { ...common, label: 'DEMO', title: `Teaching mode · ${event.scenario}`, description: event.message };
      case 'demo_delay_started': return { ...common, label: 'DEMO DELAY', title: `Teaching delay · ${event.delay_ms}ms`, description: event.reason };
      case 'run_budget_started': return { ...common, label: 'BUDGET', title: `Run budget · ${event.budget_ms / 1000}s`, description: '覆盖整次运行；到期请求协作停止，不强杀线程。' };
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
