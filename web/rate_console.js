(function () {
  'use strict';
  const { NODES, createState, applyMessage, finishStream, failState, describe } = window.RateConsole;
  const byId = id => document.getElementById(id);
  const labels = { waiting: '待执行', running: '运行中', completed: '已完成', failed: '失败', blocked: '未执行' };
  let state = createState();
  let inFlight = false;
  let filter = null;
  const rows = [];
  const nodeElements = new Map();
  const edgeElements = [];

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }
  NODES.forEach((node, index) => {
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
    byId('graph-nodes').append(button);
    if (index < NODES.length - 1) {
      const edge = element('div', 'graph-edge');
      edge.setAttribute('aria-hidden', 'true');
      // Static markup only; all event and Tool data use textContent.
      edge.innerHTML = '<svg viewBox="0 0 12 22" fill="none"><path d="M6 0v20m-3-4 3 4 3-4" stroke="currentColor" stroke-width="1.2"/></svg>';
      byId('graph-nodes').append(edge);
      edgeElements.push(edge);
    }
  });

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
    const metadata = element('div', 'event-meta');
    const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 }) : '';
    metadata.append(element('span', 'event-sequence', event.sequence ? String(event.sequence).padStart(2, '0') : '—'), element('span', 'event-node', event.task_id || 'END'), element('span', 'event-kind', view.label), element('time', 'event-time', time));
    metadata.lastChild.title = event.timestamp || '';
    row.append(metadata, element('div', 'event-title', view.title));
    if (view.description) row.append(element('p', 'event-description', view.description));
    addDetails(row, view.detailLabel, view.payload);
    byId('event-list').append(row);
    rows.push(row);
  }
  function update() {
    for (const [id, button] of nodeElements) {
      button.dataset.status = state.nodes[id];
      button.setAttribute('aria-pressed', String(filter === id));
      button.querySelector('.node-status').textContent = labels[state.nodes[id]];
      button.setAttribute('aria-label', `${id} ${NODES.find(n => n.id === id).title} · ${labels[state.nodes[id]]} · 筛选事件`);
    }
    edgeElements.forEach((edge, i) => { edge.dataset.active = String(state.nodes[NODES[i + 1].id] !== 'waiting' && state.nodes[NODES[i + 1].id] !== 'blocked'); });
    const phases = { idle: 'Ready to run', connecting: 'Connecting', running: 'Agent running', completed: 'Run completed', failed: 'Run failed' };
    byId('run-status').dataset.phase = state.phase;
    byId('run-status').querySelector('span').textContent = phases[state.phase];
    byId('run-id').textContent = state.runId || (inFlight ? '正在连接 Runtime…' : '等待开始一次运行');
    byId('event-count').textContent = state.events.length;
    byId('empty-state').hidden = rows.length > 0 || !!filter;
    byId('stream-scope').textContent = filter ? `${filter} · ${NODES.find(n => n.id === filter).title}` : '全部节点 · 调用 · 结果';
    byId('clear-filter').hidden = !filter;
    rows.forEach(row => { row.hidden = !!filter && row.dataset.node !== filter && !(filter === 'R1' && row.dataset.node === 'END'); });
    byId('filter-empty').hidden = !filter || rows.some(row => !row.hidden);
    byId('download').disabled = !state.events.length;
    byId('run-button').disabled = inFlight;
    byId('run-button').textContent = inFlight ? '运行中…' : state.terminal ? '↻  Run again' : '▶  Run Agent';
    for (const input of byId('parameters').elements) input.disabled = inFlight;
    byId('stream-footer').textContent = state.phase === 'failed' ? (state.error?.message || 'E1 评估未通过，详见结果') : state.phase === 'completed' ? '事件流已完成 · 完整输入与输出已保留' : inFlight ? '连接保持中 · 等待下一条真实事件' : '准备接收真实运行事件';
  }
  function scrollToLatest() {
    if (byId('follow').checked) byId('stream-scroll').scrollTop = byId('stream-scroll').scrollHeight;
  }
  function showSource(data) {
    if (!data) return;
    byId('source-note').textContent = `${data.provider || '公开利率数据'} · ${data.source_freshness === 'SNAPSHOT' ? '离线快照（非实时）' : data.source_freshness || '来源见结果'} · 截至 ${data.as_of || '未知'}`;
  }
  function receive(message) {
    applyMessage(state, message);
    if (message.type === 'event') {
      addRow(message.event, describe(message.event));
      if (message.event.event === 'tool_observation' && message.event.task_id === 'D1') showSource(message.event.output);
    } else if (message.type === 'result') {
      addRow({ task_id: 'END' }, { kind: state.phase === 'completed' ? 'result' : 'error', label: 'RUN RESULT', title: state.phase === 'completed' ? 'Run completed · Eval passed' : 'Run completed · Eval failed', description: '最终产物包含完整 Plan、Trace、数据、模拟与 Eval。', detailLabel: '完整运行结果 · JSON', payload: message.result });
    } else if (message.type === 'error') showError();
    update();
    scrollToLatest();
  }
  function showError() {
    addRow({ task_id: state.error?.task_id || state.activeTask || 'END' }, { kind: 'error', label: 'RUN ERROR', title: state.error?.code || 'Stream interrupted', description: state.error?.message || '运行失败', detailLabel: '完整错误信息', payload: state.error });
  }
  async function run() {
    if (inFlight) return;
    const form = byId('parameters');
    if (!form.checkValidity()) { byId('settings').open = true; form.reportValidity(); return; }
    const config = Object.fromEntries(new FormData(form).entries());
    for (const key of Object.keys(config)) config[key] = Number(config[key]);
    inFlight = true;
    state = createState();
    state.phase = 'connecting';
    filter = null;
    rows.length = 0;
    byId('event-list').replaceChildren();
    byId('settings').open = false;
    byId('follow').checked = true;
    byId('source-note').textContent = '数据来源及快照状态将在 D1 结果中披露';
    update();
    let reader;
    try {
      const response = await fetch('/api/rates/stream', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' }, body: JSON.stringify(config) });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error?.message || `HTTP ${response.status}`);
      }
      if (!response.body || !response.headers.get('Content-Type')?.includes('application/x-ndjson')) throw new Error('服务未返回 NDJSON 事件流。');
      reader = response.body.getReader();
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
    } catch (error) {
      failState(state, { code: 'STREAM_ERROR', message: error.message, task_id: state.activeTask });
      showError();
      if (reader) await reader.cancel().catch(() => {});
    } finally {
      if (reader) reader.releaseLock();
      inFlight = false;
      update();
      scrollToLatest();
    }
  }
  byId('run-button').addEventListener('click', run);
  byId('parameters').addEventListener('submit', event => { event.preventDefault(); run(); });
  byId('clear-filter').addEventListener('click', () => { filter = null; update(); });
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
  update();
})();
