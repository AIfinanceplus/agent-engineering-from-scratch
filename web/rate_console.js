(function () {
  'use strict';
  const { NODES, PARALLEL_NODES, PARALLEL_ROWS, STUDIO_ROLES, flowForEvent, handoffForEvent, createState, applyMessage, finishStream, failState, describe } = window.RateConsole;
  const byId = id => document.getElementById(id);
  const labels = { waiting: '待执行', ready: '可执行', running: '运行中', completed: '已完成', failed: '失败', blocked: '未执行', abstained: '主动停止', cancelling: '停止中', cancelled: '已取消', timed_out: '超时停止', unknown: '状态未知', open: 'OPEN', half_open: 'HALF-OPEN', queued: '排队中', throttling: '限速等待', rejected: '已拒绝', replan: '需重规划 ↺', invalidated: '已作废', proposed: '提议待审', repairing: '修复中', retrieving: '召回中', ranking: '排名中', topk: 'Top-K 完成', verifying: '验源中', scanning: '扫描中', quarantining: '隔离中', waiting_human: '等待人工', approved: '已批准', restarting: '进程重启', restoring: '恢复审批', acquiring: '申请租约', acquired: '持有租约', renewing: '续租中', expired: '已过期', taking_over: '接管中', fenced: '旧持有者已隔离', retrying: '等待重试', writing: '写入中', deduplicated: '已去重', issuing: '签发中', issued: '已签发', authorizing: '鉴权中', verified: '已授权', selecting: '筛选中', compressing: '压缩中', selected: '已选路', reserved: '预算已预留', fallback: '切换模型', budget_blocked: '预算阻止' };
  let state = createState('parallel');
  let inFlight = false;
  let filter = null;
  let selectedRole = null;
  let flowMode = 'information';
  let cancelPending = false;
  let cancelNote = '';
  const rows = [];
  const nodeElements = new Map();
  const edgeElements = [];
  const roleElements = new Map();
  const MODEL_KEY_SESSION = 'rate-console:model-api-key';
  const flowCopy = {
    information: ['信息流', 'Goal → Context → Intent → Observation → Result', '展示真正传递的数据；没有进入 Trace 的信息不会被画成已传递。'],
    decision: ['决策流', 'Model Proposal → Runtime Validation → Fixed Plan → Outcome', '区分模型提议与 Runtime 决定；模型不能直接启动 Tool。'],
    risk: ['风控流', 'Evidence → Guardrail → Allow / Block → Audit', '展示检查对象、规则与影响；被绕过的历史能力不会显示成已通过。'],
  };
  const scenarioBudget = () => ['deadline', 'late_result'].includes(byId('scenario').value) ? 1000 : ['live', 'execution_race', 'paper_fill_accounting', 'paper_portfolio_risk', 'model_live', 'intent_live', 'approval_interactive', 'approval_durable_restart', 'approval_durable_stale', 'lease_failover', 'lease_renewal', 'outbox_retry', 'outbox_fenced'].includes(byId('scenario').value) ? 120000 : 30000;

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
  const definitions = () => state.mode === 'parallel' ? PARALLEL_NODES : NODES;
  function buildGraph() {
    nodeElements.clear();
    edgeElements.length = 0;
    byId('graph-nodes').replaceChildren();
    byId('graph-nodes').classList.toggle('parallel-graph', state.mode === 'parallel');
    byId('node-count').textContent = `${definitions().length} nodes`;
    const graphRows = state.mode === 'parallel' ? PARALLEL_ROWS : NODES.map(n => [n.id]);
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
          const x1 = ids.length === 1 ? 50 : 25 + 50 * fromIndex;
          const x2 = nextIds.length === 1 ? 50 : 25 + 50 * toIndex;
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
      top.append(element('span', 'role-avatar', role.icon), element('span', 'role-type', role.type));
      const footer = element('span', 'role-footer');
      footer.append(element('span', 'role-state', '等待运行'), element('span', 'role-evidence', '0 events'));
      button.append(top, element('strong', 'role-name', role.name), element('span', 'role-activity', role.idle), footer);
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
    byId('handoff-count').textContent = `${handoffs.length} 个关键交接`;
    if (!handoffs.length) {
      list.append(element('li', 'handoff-empty', '运行后，这里只显示影响信息、决策或风险边界的关键交接。'));
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
      item.append(meta, element('div', 'handoff-actors', `${from}  →  ${to}`), element('strong', 'handoff-title', handoff.title), evidence);
      list.append(item);
    }
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

  function updateStudio() {
    const relevantHandoffs = state.events.map(handoffForEvent).filter(Boolean).filter(handoff => handoff.flow === flowMode);
    for (const role of STUDIO_ROLES) {
      const button = roleElements.get(role.id);
      const roleEvents = state.events.filter(event => role.tasks.includes(event.task_id) || (role.id === 'model' && event.event === 'model_response_received'));
      const latest = roleEvents.at(-1);
      const status = roleStatus(role);
      button.dataset.status = status;
      button.dataset.flowMuted = String(state.events.length > 0 && !relevantHandoffs.some(handoff => [handoff.from, handoff.to].includes(role.id)));
      button.setAttribute('aria-pressed', String(selectedRole === role.id));
      button.querySelector('.role-state').textContent = status === 'active' ? '正在工作' : status === 'completed' ? '本次已完成' : status === 'failed' ? '已停止 / 阻断' : status === 'blocked' ? '下游未执行' : '等待运行';
      button.querySelector('.role-evidence').textContent = `${roleEvents.length} events`;
      button.querySelector('.role-activity').textContent = latest ? describe(latest).title : role.idle;
    }
    const copy = flowCopy[flowMode];
    byId('flow-route').dataset.flow = flowMode;
    byId('flow-route').querySelector('.route-label').textContent = copy[0];
    byId('flow-route-title').textContent = copy[1];
    byId('flow-route-detail').textContent = copy[2];
    renderHandoffs();
    updateModelInspector();
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
    const frameCount = state.runId ? eventCount + 1 + (state.terminal ? 1 : 0) : 0;
    const attempts = state.events.filter(event => ['tool_execution_started', 'outbox_dispatch_started'].includes(event.event)).length;
    const effectEvent = [...state.events].reverse().find(event => Number.isFinite(event.effect_count));
    const effectCount = effectEvent ? String(effectEvent.effect_count) : '—';
    const outcome = state.phase === 'completed' ? 'PASS' : state.phase === 'failed' ? 'FAIL' : state.terminal ? state.phase.toUpperCase() : '—';
    byId('overview-mode').textContent = state.replayed ? 'REPLAY · READ ONLY' : inFlight ? 'LIVE · RECORDING' : state.runId ? 'LIVE · RECORDED' : '等待运行';
    const ledger = state.result?.paper_ledger;
    const executionResult = state.result?.execution;
    const raceDemo = executionResult?.artifact_type === 'paper_execution_projection';
    byId('overview-change').textContent = state.replayed
      ? '当前展示的是已持久化历史；页面只重建状态，不重新调用 Tool。'
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
    byId('outcome-title').textContent = state.replayed ? 'Replay completed · same run, no Tool call' : state.phase === 'completed' ? 'Run completed · Eval passed' : state.phase === 'failed' ? 'Run failed · inspect the boundary below' : 'Run in progress';
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
    const phases = { idle: 'Ready to run', connecting: 'Connecting', running: 'Agent running', completed: 'Run completed', failed: 'Run failed', cancelling: 'Stopping · 等待确认', cancelled: 'Run cancelled', timed_out: 'Run timed out' };
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
    byId('replay-button').hidden = !state.terminal || !state.runId || inFlight;
    byId('replay-button').disabled = inFlight;
    byId('run-button').disabled = inFlight;
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
    byId('stream-footer').textContent = state.phase === 'failed' ? (state.error?.message || 'E1 评估未通过，详见结果') : ['cancelled', 'timed_out'].includes(state.phase) ? '所有 Tool 已退出 · 已完成节点保留 · 下游未继续' : state.phase === 'cancelling' ? '停止请求已发出；事件流保持连接，等待 Tool 确认' : state.phase === 'completed' ? (state.replayed ? '历史事件已重放 · 未重新调用 Tool' : '事件流已完成 · 完整输入与输出已保留') : cancelNote || (inFlight ? '连接保持中 · 等待下一条真实事件' : '准备接收真实运行事件');
    updateOverview();
    updateStudio();
  }
  function scrollToLatest() {
    if (byId('follow').checked) byId('stream-scroll').scrollTop = byId('stream-scroll').scrollHeight;
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
      addRow({ task_id: 'END' }, { kind: state.phase === 'completed' ? 'result' : 'error', label: 'RUN RESULT', title: state.phase === 'completed' ? 'Run completed · Eval passed' : 'Run completed · Eval failed', description: '最终产物包含完整 Plan、Trace、数据、模拟与 Eval。', detailLabel: '完整运行结果 · JSON', payload: message.result });
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
    config.execution_mode = 'parallel';
    config.demo_scenario = byId('scenario').value;
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
    inFlight = true;
    state = createState('parallel');
    state.phase = 'connecting';
    filter = null;
    selectedRole = null;
    rows.length = 0;
    byId('event-list').replaceChildren();
    byId('settings').open = false;
    byId('follow').checked = true;
    byId('source-note').textContent = config.demo_scenario === 'live' ? '公开数据 · 无延时或故障注入' : config.demo_scenario === 'execution_race' ? '纸面成交事件 · 持久化后发送 · 重复 fill 去重' : config.demo_scenario === 'paper_fill_accounting' ? '纸面成交账本 · 报价与成交分离 · 幂等重试 · 结算 P&L' : config.demo_scenario === 'paper_portfolio_risk' ? '2s10s 纸面组合投影 · 净平行 DV01 限额 · 拦截不写入账本' : config.demo_scenario === 'intent_live' ? '本地 OpenAI API · Key 不进入页面或 Trace · 模型只能提议受限 Intent，Runtime 映射固定任务图' : config.demo_scenario === 'model_live' ? '本地 OpenAI API · Key 不进入页面或 Trace · 模型输出仅为待校验提议' : '教学演示 · 公开历史快照 · 包含明确的延时/故障注入';
    update();
    try {
      const endpoint = config.demo_scenario === 'execution_race' ? '/api/rates/execution-race' : config.demo_scenario === 'paper_fill_accounting' ? '/api/rates/paper-fill' : config.demo_scenario === 'paper_portfolio_risk' ? '/api/rates/paper-portfolio' : '/api/rates/stream';
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
      inFlight = false;
      update();
      scrollToLatest();
    }
  }
  async function replayLast() {
    if (inFlight || !state.runId || !state.terminal) return;
    const runId = state.runId;
    inFlight = true;
    cancelPending = false;
    cancelNote = '';
    filter = null;
    selectedRole = null;
    rows.length = 0;
    byId('event-list').replaceChildren();
    state = createState('parallel');
    state.phase = 'connecting';
    update();
    try {
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
      inFlight = false;
      update();
      scrollToLatest();
    }
  }
  byId('run-button').addEventListener('click', run);
  byId('replay-button').addEventListener('click', replayLast);
  byId('stop-button').addEventListener('click', requestStop);
  byId('approve-button').addEventListener('click', () => decideApproval('approve'));
  byId('deny-button').addEventListener('click', () => decideApproval('deny'));
  byId('forget-model-key').addEventListener('click', clearSessionKey);
  byId('load-archive-scenario').addEventListener('click', selectArchivedScenario);
  byId('scenario').addEventListener('change', () => {
    if (!state.runId) byId('source-note').textContent = byId('scenario').value === 'live' ? '公开数据 · 无延时或故障注入' : '教学演示 · 公开历史快照 · 包含明确的延时/故障注入';
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
  update();
})();
