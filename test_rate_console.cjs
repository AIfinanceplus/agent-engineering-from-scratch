const test = require('node:test');
const assert = require('node:assert/strict');
const { NODES, PARALLEL_NODES, PARALLEL_ROWS, createState, applyMessage, finishStream, failState, describe } = require('./web/rate_console_core.js');

function setup() {
  const state = createState();
  const message = (type, payload = {}) => ({ protocol: 'rate-ndjson-v1', run_id: 'test-run', type, ...payload });
  applyMessage(state, message('start'));
  const emit = (event, task_id, extras = {}) => applyMessage(state, message('event', { event: { event, task_id, run_id: 'test-run', sequence: state.events.length + 1, timestamp: '2026-09-01T01:02:03.000Z', ...extras } }));
  emit('goal_received', 'G1');
  emit('plan_created', 'P1');
  emit('runtime_started', 'R1');
  return { state, message, emit };
}

test('actual graph has no fake parallel tasks and runtime stays active during tools', () => {
  assert.deepEqual(NODES.map(n => n.id), ['G1', 'P1', 'R1', 'D1', 'S1', 'E1']);
  const { state, emit } = setup();
  emit('task_started', 'D1');
  assert.equal(state.nodes.D1, 'running');
  assert.equal(state.nodes.R1, 'running');
  assert.equal(state.nodes.G1, 'completed');
  assert.equal(state.nodes.S1, 'waiting');
});

test('retry keeps the node active and completion unblocks the next node', () => {
  const { state, emit } = setup();
  emit('task_started', 'D1');
  emit('tool_execution_failed', 'D1', { retryable: true });
  emit('tool_retry_scheduled', 'D1', { next_attempt: 2 });
  assert.equal(state.nodes.D1, 'running');
  emit('task_completed', 'D1');
  emit('task_started', 'S1');
  assert.equal(state.nodes.D1, 'completed');
  assert.equal(state.nodes.S1, 'running');
});

test('failure on S1 preserves D1 success and blocks E1', () => {
  const { state, emit, message } = setup();
  emit('task_completed', 'D1');
  emit('task_started', 'S1');
  applyMessage(state, message('error', { error: { task_id: 'S1', message: 'invalid input' } }));
  assert.equal(state.nodes.D1, 'completed');
  assert.equal(state.nodes.S1, 'failed');
  assert.equal(state.nodes.E1, 'blocked');
  assert.equal(state.nodes.R1, 'failed');
  assert.equal(state.phase, 'failed');
  assert.equal(finishStream(state), state);
});

test('result reconciles every event and eval failure is not shown as success', () => {
  for (const passed of [true, false]) {
    const { state, emit, message } = setup();
    emit('task_completed', 'D1');
    emit('task_completed', 'S1');
    emit('eval_started', 'E1');
    emit('eval_completed', 'E1', { passed });
    emit('run_completed', 'END');
    applyMessage(state, message('result', { result: { run_id: state.runId, trace: state.events, eval: { passed } } }));
    assert.equal(state.phase, passed ? 'completed' : 'failed');
    assert.equal(state.nodes.E1, passed ? 'completed' : 'failed');
    assert.equal(finishStream(state), state);
  }
});

test('rejects wrong protocol, run ID, missing sequence, duplicate and incomplete streams', () => {
  const { state, message } = setup();
  assert.throws(() => applyMessage(state, { ...message('event'), protocol: 'other' }));
  assert.throws(() => applyMessage(state, { ...message('event'), run_id: 'other' }));
  assert.throws(() => applyMessage(state, message('start')));
  assert.throws(() => applyMessage(state, message('event', { event: { sequence: 100, event: 'task_started', run_id: state.runId } })));
  assert.throws(() => applyMessage(state, message('result', { result: { run_id: state.runId, trace: [] } })));
  assert.throws(() => finishStream(state), /未收到最终结果/);
  assert.equal(state.events.length, 3);
});

test('disconnect preserves events and does not claim nodes completed', () => {
  const { state, emit } = setup();
  emit('task_started', 'D1');
  failState(state, { message: 'connection closed' });
  assert.equal(state.events.length, 4);
  assert.equal(state.nodes.D1, 'failed');
  assert.equal(state.nodes.S1, 'blocked');
  assert.deepEqual(state.activeTasks, []);
});

test('calls and results expose full payloads, including all historical observations', () => {
  const output = { observations: Array.from({ length: 746 }, (_, i) => ({ date: i })), source_freshness: 'SNAPSHOT', as_of: '2026-08-31' };
  const call = describe({ event: 'tool_execution_started', arguments: { history: output }, attempt: 1, max_attempts: 3 });
  const result = describe({ event: 'tool_observation', task_id: 'D1', output });
  assert.equal(call.kind, 'call');
  assert.equal(call.payload.history, output);
  assert.equal(result.payload.observations.length, 746);
  assert.match(result.description, /SNAPSHOT/);
  assert.equal(describe({ event: 'eval_completed', passed: false, output: { checks: { no_real_orders: false } } }).kind, 'error');
});

test('parallel reducer tracks both active tasks and a 1/2 Join barrier', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  assert.deepEqual(PARALLEL_ROWS[14], ['A2', 'A10']);
  emit('task_started', 'A2');
  emit('task_started', 'A10');
  assert.deepEqual(state.activeTasks, ['A2', 'A10']);
  emit('task_completed', 'A10');
  emit('join_waiting', 'J1', { completed_dependencies: ['A10'], waiting_for: ['A2'], required: 2 });
  assert.deepEqual(state.activeTasks, ['A2']);
  assert.equal(state.nodes.A2, 'running');
  assert.equal(state.nodes.J1, 'waiting');
  assert.equal(state.join.completed.length, 1);
  emit('task_completed', 'A2');
  emit('join_released', 'J1');
  assert.equal(state.nodes.J1, 'ready');
});

test('branch failure does not falsely complete or fail its still-running sibling', () => {
  const { state, emit, message } = setup();
  state.nodes.A2 = 'waiting'; state.nodes.A10 = 'waiting'; state.nodes.J1 = 'waiting';
  emit('task_started', 'A2'); emit('task_started', 'A10');
  emit('task_failed', 'A10');
  emit('join_blocked', 'J1');
  assert.equal(state.nodes.A2, 'running');
  assert.deepEqual(state.activeTasks, ['A2']);
  emit('task_completed', 'A2');
  applyMessage(state, message('error', { error: { task_id: 'A10', message: 'branch failed' } }));
  assert.equal(state.nodes.A2, 'completed');
  assert.equal(state.nodes.A10, 'failed');
  assert.equal(state.nodes.J1, 'blocked');
  assert.equal(state.nodes.S1, 'blocked');
});

test('stop request is not a terminal state; only acknowledged stop can finalize', () => {
  const { state, emit, message } = setup();
  state.nodes.A2 = 'waiting';
  emit('task_started', 'A2');
  emit('cancellation_requested', 'R1', { reason: 'deadline', active_tasks: ['A2'] });
  assert.equal(state.phase, 'cancelling');
  assert.equal(state.nodes.A2, 'cancelling');
  assert.equal(state.terminal, false);
  assert.throws(() => applyMessage(state, message('error', { error: { code: 'RUN_DEADLINE_EXCEEDED' } })));
  emit('task_cancelled', 'A2', { reason: 'deadline', worker_stopped: true });
  emit('run_stopped', 'R1', { reason: 'deadline', status: 'timed_out', workers_stopped: true });
  applyMessage(state, message('error', { error: { code: 'RUN_DEADLINE_EXCEEDED' } }));
  assert.equal(state.phase, 'timed_out');
  assert.equal(state.nodes.A2, 'timed_out');
  assert.equal(state.terminal, true);
  finishStream(state);
});

test('a lost stream during cancellation is unknown, not acknowledged cancellation', () => {
  const { state, emit } = setup();
  emit('task_started', 'D1');
  emit('cancellation_requested', 'R1', { reason: 'user', active_tasks: ['D1'] });
  assert.throws(() => finishStream(state));
  failState(state, { message: 'connection lost' });
  assert.equal(state.nodes.D1, 'unknown');
  assert.equal(state.nodes.R1, 'unknown');
  assert.equal(state.stopConfirmed, false);
});

test('late success cannot overwrite a stop request', () => {
  const { state, emit, message } = setup();
  emit('cancellation_requested', 'R1', { reason: 'user', active_tasks: [] });
  assert.throws(() => applyMessage(state, message('result', { result: { run_id: state.runId, trace: state.events, eval: { passed: true } } })), /停止请求/);
  const view = describe({ event: 'tool_output_discarded', output: { value: 123 } });
  assert.equal(view.label, 'DISCARDED');
  assert.equal(view.payload.value, 123);
});

test('circuit transitions remain visible and rejected calls never complete C1', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('circuit_call_allowed', 'C1', { state: 'closed', attempt: 1 });
  emit('circuit_failure_recorded', 'C1', { snapshot: { state: 'open' } });
  emit('circuit_state_changed', 'C1', { from_state: 'closed', to_state: 'open' });
  assert.equal(state.nodes.C1, 'open');
  emit('circuit_call_rejected', 'C1');
  assert.equal(state.nodes.C1, 'open');
  assert.equal(describe({ event: 'circuit_call_rejected', snapshot: { state: 'open' } }).kind, 'guard');
});

test('backpressure shows queued, throttled, released and drained states', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('admission_requested', 'Q1', { target_task: 'A10' });
  emit('backpressure_queued', 'Q1', { target_task: 'A10', queue_depth: 1 });
  assert.equal(state.nodes.Q1, 'queued');
  emit('rate_limit_waiting', 'Q1', { target_task: 'A10', delay_ms: 500 });
  assert.equal(state.nodes.Q1, 'throttling');
  emit('backpressure_released', 'Q1', { target_task: 'A10' });
  assert.equal(state.nodes.Q1, 'running');
  emit('admission_cycle_completed', 'Q1');
  assert.equal(state.nodes.Q1, 'completed');
});

test('replanning visibly invalidates D1, loops through P1, then accepts V1', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('task_completed', 'D1');
  emit('observation_validation_started', 'V1');
  emit('observation_validation_completed', 'V1', { passed: false, output: { observation_count: 40, minimum_required: 81 } });
  assert.equal(state.nodes.V1, 'replan');
  emit('task_invalidated', 'D1');
  emit('replan_requested', 'V1');
  assert.equal(state.nodes.D1, 'invalidated');
  assert.equal(state.nodes.P1, 'running');
  emit('plan_revised', 'P1', { revision: 1, remaining_revisions: 0 });
  emit('task_started', 'D1');
  emit('task_completed', 'D1');
  emit('observation_validation_started', 'V1');
  emit('observation_validation_completed', 'V1', { passed: true, output: { observation_count: 746, minimum_required: 81 } });
  assert.equal(state.nodes.P1, 'completed');
  assert.equal(state.nodes.D1, 'completed');
  assert.equal(state.nodes.V1, 'completed');
  assert.equal(describe({ event: 'replan_requested', feedback: {} }).label, 'FEEDBACK ↺');
});

test('loop and budget guards stop Planner instead of spinning', () => {
  for (const event of ['replan_loop_detected', 'replan_budget_exhausted']) {
    const { state, emit } = setup();
    Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
    emit(event, 'P1', { guard: { used_revisions: 1, max_revisions: 1 } });
    assert.equal(state.nodes.P1, 'failed');
    assert.equal(describe({ event, guard: {} }).kind, 'error');
  }
});

test('model proposal remains untrusted until P1 accepts it', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('model_request_started', 'M1', { model: 'scripted', attempt: 1, is_real_llm: false, prompt: {} });
  assert.equal(state.nodes.M1, 'running');
  emit('model_response_received', 'M1', { raw_output: '{}', output_characters: 2 });
  assert.equal(state.nodes.M1, 'proposed');
  emit('plan_parse_started', 'P1');
  emit('plan_parse_failed', 'P1', { error_type: 'ModelPlanParseError', error_message: 'bad json' });
  emit('model_repair_requested', 'M1');
  assert.equal(state.nodes.P1, 'repairing');
  assert.equal(state.nodes.M1, 'repairing');
  emit('model_request_started', 'M1', { model: 'scripted', attempt: 2, is_real_llm: false, prompt: {} });
  emit('model_response_received', 'M1', { raw_output: '{}', output_characters: 2 });
  emit('plan_validation_completed', 'P1', { accepted: true, output: { checks: {} } });
  assert.equal(state.nodes.P1, 'ready');
  emit('model_plan_accepted', 'P1', { proposal: {} });
  assert.equal(state.nodes.M1, 'completed');
  assert.equal(state.nodes.P1, 'completed');
  assert.equal(describe({ event: 'model_response_received', raw_output: '{}', output_characters: 2 }).label, 'RAW OUTPUT');
});

test('unsafe model plan fails P1 and leaves Runtime waiting', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('plan_validation_completed', 'P1', { accepted: false, reasons: ['unknown tool'] });
  emit('model_plan_rejected', 'P1', { reasons: ['unknown tool'] });
  assert.equal(state.nodes.M1, 'completed');
  assert.equal(state.nodes.P1, 'failed');
  assert.equal(state.nodes.R1, 'waiting');
  assert.equal(describe({ event: 'model_plan_rejected', reasons: ['unknown tool'] }).label, 'ABSTAIN');
});

test('model router exposes reservation, provider failure and bounded fallback', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('model_routing_started', 'MR1', { candidates: ['small', 'large'], max_fallbacks: 1, budget: { total_tokens: 2000 } });
  emit('model_route_selected', 'MR1', { model: 'small', tier: 'economy', provider: 'local', reason: 'lowest tier' });
  emit('model_budget_reserved', 'MR1', { reservation: { reserved_tokens: 600, budget: { remaining_tokens: 1400 } } });
  assert.equal(state.nodes.MR1, 'reserved');
  emit('model_request_started', 'M1', { model: 'small', attempt: 1, is_real_llm: false, prompt: {} });
  emit('model_provider_failed', 'M1', { model: 'small', error_message: 'timeout' });
  emit('model_fallback_requested', 'MR1', { from_model: 'small', to_model: 'large', fallback_number: 1, max_fallbacks: 1 });
  assert.equal(state.nodes.M1, 'failed');
  assert.equal(state.nodes.MR1, 'fallback');
  emit('model_route_selected', 'MR1', { model: 'large', tier: 'capable', provider: 'local', reason: 'fallback' });
  emit('model_route_completed', 'MR1', { selected_model: 'large', fallback_count: 1, budget: { spent_tokens: 640, total_tokens: 2000 } });
  assert.equal(state.nodes.MR1, 'completed');
  assert.equal(describe({ event: 'model_fallback_requested', from_model: 'small', to_model: 'large', fallback_number: 1, max_fallbacks: 1 }).label, 'FALLBACK 1/1');
});

test('token budget stops fallback before a second model request', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('model_budget_rejected', 'MR1', { model: 'large', required_tokens: 1200, remaining_tokens: 540 });
  assert.equal(state.nodes.MR1, 'budget_blocked');
  assert.equal(describe({ event: 'model_budget_rejected', model: 'large', required_tokens: 1200, remaining_tokens: 540 }).label, 'BUDGET STOP');
  emit('model_route_abstained', 'MR1', { reason: 'budget exhausted' });
  assert.equal(state.nodes.MR1, 'failed');
  assert.equal(state.nodes.M1, 'waiting');
});

test('context builder shows score, compression, drop and final pack before model input', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('context_collection_started', 'CT1', { candidate_count: 5, max_tokens: 150, sources: ['system'] });
  emit('context_item_scored', 'CT1', { item_id: 'history', score: 0.84, relevance: 0.86, authority: 0.75, freshness: 0.9 });
  assert.equal(state.nodes.CT1, 'selecting');
  emit('context_item_compressed', 'CT1', { item_id: 'history', full_tokens: 160, used_tokens: 40, released_tokens: 120 });
  assert.equal(state.nodes.CT1, 'compressing');
  emit('context_item_dropped', 'CT1', { item_id: 'noise', reason: 'low_relevance' });
  emit('context_pack_created', 'CT1', { used_tokens: 150, max_tokens: 150, excluded_item_ids: ['noise'], context_pack: { items: [{ item_id: 'history' }] } });
  assert.equal(state.nodes.CT1, 'completed');
  assert.equal(describe({ event: 'context_item_compressed', item_id: 'history', full_tokens: 160, used_tokens: 40, released_tokens: 120 }).label, 'COMPRESS');
  assert.equal(describe({ event: 'context_item_dropped', item_id: 'noise', reason: 'low_relevance' }).label, 'DROP');
  assert.equal(describe({ event: 'context_pack_created', used_tokens: 150, max_tokens: 150, excluded_item_ids: ['noise'], context_pack: { items: [{ item_id: 'history' }] } }).label, 'PACK');
});

test('historical lessons explicitly bypass the context builder', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('context_bypassed', 'CT1', { reason: 'historical lesson' });
  assert.equal(state.nodes.CT1, 'completed');
});

test('RAG makes ranking, Top-K and citation rejection visible before context', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('retrieval_query_created', 'RG1', { query: 'DGS2 DGS10', top_k: 3, corpus_size: 4, embedding_model: null });
  emit('retrieval_candidate_scored', 'RG1', { rank: 1, chunk_id: 'stale', lexical_score: 0.9, matched_terms: ['dgs2'], selected_top_k: true });
  assert.equal(state.nodes.RG1, 'ranking');
  emit('retrieval_topk_selected', 'RG1', { top_k: 3, selected_chunk_ids: ['stale'], selected_citation_ids: ['CIT-1'] });
  assert.equal(state.nodes.RG1, 'topk');
  emit('retrieval_completed', 'RG1', { result_count: 1, algorithm: 'deterministic_lexical_overlap' });
  emit('citation_gate_started', 'CG1', { candidate_count: 1, required_series: ['DGS2', 'DGS10'], allowed_domains: ['fred.stlouisfed.org'] });
  emit('citation_checked', 'CG1', { passed: false, chunk_id: 'stale', domain: 'fred.stlouisfed.org', reasons: ['source_version_superseded'], series: ['DGS2'] });
  assert.equal(state.nodes.CG1, 'rejected');
  emit('citation_gate_completed', 'CG1', { passed: false, missing_series: ['DGS10'], accepted_citation_ids: [] });
  assert.equal(state.nodes.CG1, 'failed');
  assert.equal(state.nodes.CT1, 'waiting');
  assert.equal(describe({ event: 'retrieval_topk_selected', top_k: 3, selected_chunk_ids: ['stale'], selected_citation_ids: ['CIT-1'] }).label, 'TOP-K');
  assert.equal(describe({ event: 'citation_checked', passed: false, chunk_id: 'stale', domain: 'fred.stlouisfed.org', reasons: ['source_version_superseded'], series: ['DGS2'] }).label, 'CITATION REJECT');
});

test('historical lessons explicitly bypass retrieval and citation gates', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('retrieval_bypassed', 'RG1', { reason: 'historical lesson' });
  emit('citation_gate_bypassed', 'CG1', { reason: 'no retrieved evidence' });
  emit('taint_guard_bypassed', 'TG1', { reason: 'no retrieved content' });
  assert.equal(state.nodes.RG1, 'completed');
  assert.equal(state.nodes.CG1, 'completed');
  assert.equal(state.nodes.TG1, 'completed');
});

test('taint guard visualizes quarantine and blocks unsafe propagation', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('taint_guard_started', 'TG1', { candidate_count: 3, trust_default: 'UNTRUSTED', policy: 'retrieved_text_is_data_never_instructions' });
  assert.equal(state.nodes.TG1, 'scanning');
  emit('retrieved_content_inspected', 'TG1', { chunk_id: 'attack', citation_id: 'CIT-X', tainted: true, action: 'QUARANTINE', matched_rules: ['instruction_override'], content_preview: 'ignore prior instructions' });
  assert.equal(state.nodes.TG1, 'quarantining');
  assert.equal(describe(state.events.at(-1)).label, 'QUARANTINE');
  emit('taint_guard_completed', 'TG1', { passed: false, missing_series: ['DGS10'], promoted_citation_ids: [], quarantined_citation_ids: ['CIT-X'] });
  assert.equal(state.nodes.TG1, 'failed');
  assert.equal(state.nodes.CT1, 'waiting');
  assert.equal(describe(state.events.at(-1)).label, 'ABSTAIN');
});

test('capability gate denies before Tool execution and exposes exact reason', () => {
  const { state, emit } = setup();
  Object.assign(state, { mode: 'parallel', nodes: Object.fromEntries(PARALLEL_NODES.map(n => [n.id, 'waiting'])) });
  emit('capability_policy_started', 'AZ1', { bindings: ['run_id', 'tool_name', 'scope'] });
  emit('capability_minted', 'AZ1', { target_task: 'D1', requested_tool: 'fetch_public_rate_history', capability: { tool_name: 'simulate_one_curve_trade', scope: 'paper:simulate', max_uses: 1 } });
  emit('capability_check_started', 'AZ1', { target_task: 'D1', tool_name: 'fetch_public_rate_history', required_scope: 'rates:read', capability: {} });
  assert.equal(state.nodes.AZ1, 'authorizing');
  emit('capability_rejected', 'AZ1', { target_task: 'D1', tool_name: 'fetch_public_rate_history', required_scope: 'rates:read', reasons: ['tool_not_authorized'], decision: 'DENY_BEFORE_TOOL' });
  assert.equal(state.nodes.AZ1, 'failed');
  assert.equal(state.nodes.D1, 'waiting');
  assert.equal(describe(state.events.at(-1)).label, 'DENIED');
});
