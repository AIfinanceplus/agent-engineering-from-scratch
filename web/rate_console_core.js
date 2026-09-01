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
  function createState() {
    return { phase: 'idle', runId: null, events: [], nodes: Object.fromEntries(NODES.map(n => [n.id, 'waiting'])), activeTask: null, result: null, error: null, terminal: false };
  }
  function failState(state, error) {
    state.error = typeof error === 'string' ? { message: error } : error;
    state.phase = 'failed';
    state.terminal = true;
    const active = state.error.task_id || state.activeTask;
    if (active in state.nodes) state.nodes[active] = 'failed';
    if (state.nodes.R1 !== 'waiting') state.nodes.R1 = 'failed';
    for (const id of Object.keys(state.nodes)) {
      if (state.nodes[id] === 'waiting' || state.nodes[id] === 'running') state.nodes[id] = 'blocked';
    }
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
        if (id in state.nodes) state.nodes[id] = 'running';
        state.activeTask = id;
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
        state.activeTask = null;
        break;
      case 'eval_completed':
        state.nodes.E1 = event.passed ? 'completed' : 'failed';
        state.activeTask = null;
        break;
      case 'run_completed': state.nodes.R1 = 'completed'; break;
    }
  }
  function applyMessage(state, message) {
    if (!message || message.protocol !== 'rate-ndjson-v1' || typeof message.run_id !== 'string' || !message.run_id) throw new Error('无法识别的 Agent stream 协议。');
    if (state.terminal) throw new Error('终态之后仍收到消息。');
    if (message.type === 'start') {
      if (state.runId) throw new Error('重复的 stream start。');
      state.runId = message.run_id;
      state.phase = 'running';
    } else {
      if (!state.runId || message.run_id !== state.runId) throw new Error('流式消息来自不同的运行。');
      if (message.type === 'event') applyEvent(state, message.event);
      else if (message.type === 'result') {
        const result = message.result;
        if (!result || result.run_id !== state.runId || !Array.isArray(result.trace) || JSON.stringify(result.trace) !== JSON.stringify(state.events) || state.events.at(-1)?.event !== 'run_completed') throw new Error('最终结果与已接收的事件流不一致。');
        state.result = result;
        state.phase = result.eval?.passed === true ? 'completed' : 'failed';
        state.terminal = true;
      } else if (message.type === 'error') {
        failState(state, message.error || { message: 'Agent 执行失败' });
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
      case 'plan_created': return { ...common, title: 'Plan created', description: '固定计划 · D1 → S1，随后 E1 校验', detailLabel: '完整计划与依赖' };
      case 'runtime_started': return { ...common, title: 'Runtime started', description: '从 Tool Registry 解析能力，并执行参数校验和重试策略。', detailLabel: 'Runtime 与 Tool Registry' };
      case 'task_started': return { ...common, title: 'Node started', description: event.tool_name };
      case 'tool_lookup': return { ...common, label: 'REGISTRY', title: event.tool_name, description: event.found ? 'Tool 已在注册表找到' : 'Tool 未注册' };
      case 'tool_validation': return { ...common, kind: event.passed ? 'node' : 'error', label: 'VALIDATION', title: event.passed ? 'Arguments validated' : 'Arguments rejected', description: event.tool_name, detailLabel: '参数校验结果' };
      case 'tool_execution_started': return { ...common, kind: 'call', label: 'TOOL CALL', title: event.tool_name, description: `第 ${event.attempt} / ${event.max_attempts} 次调用`, detailLabel: '调用参数 · 完整 JSON', payload: event.arguments };
      case 'tool_observation': {
        const output = event.output || {};
        const description = event.task_id === 'D1' ? `${output.observations?.length ?? 0} 条对齐观测 · ${output.source_freshness || output.provider || '来源见结果'} · 截至 ${output.as_of || '未知'}` : `${output.completed_trade?.action || '模拟完成'} · 完整交易与计算结果已返回`;
        return { ...common, kind: 'result', label: 'TOOL RESULT', title: event.tool_name, description, detailLabel: '返回结果 · 完整 JSON', payload: output };
      }
      case 'task_completed': return { ...common, title: 'Node completed', description: event.tool_name };
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
  return { NODES, createState, applyMessage, finishStream, failState, describe };
});
