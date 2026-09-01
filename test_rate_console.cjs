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
  assert.deepEqual(PARALLEL_ROWS[4], ['A2', 'A10']);
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
