/* Rate Strategy V1 inside the full Agent Research Workbench shell. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'rate_workbench.css?v=rate-workbench-v1';
  document.head.appendChild(link);
})();

const rateWorkbenchState = {
  run:null,
  failureTrace:[],
  busy:false,
  error:null,
  selectedNode:'G1',
  config:{lookback_days:'60',entry_z:'1',holding_days:'20',dv01_usd_per_bp:'100',round_trip_cost_bps:'1'},
};

const RATE_NODE_META = {
  G1:{name:'Goal',icon:'◎',why:'操作者提出一个明确目标：用公开利率数据完成一次可审计的 paper simulation。',input:['One strategy','Explicit parameters'],output:['Agent goal'],code:'web/rate_workbench.js'},
  P1:{name:'Planner',icon:'✣',why:'固定 Planner 只生成 D1 → S1 两个任务，避免第一次学习被自由规划和事件匹配干扰。',input:['Goal','Strategy configuration'],output:['Two-Tool DAG'],code:'rate_agent.py'},
  R1:{name:'Runtime',icon:'⌘',why:'Runtime 从共享 Tool Registry 查找能力、验证参数，然后才允许函数执行。',input:['PlanTask','Tool arguments'],output:['Validated Tool call','Trace events'],code:'rate_agent.py / tools.py'},
  D1:{name:'D1 Rate Data Tool',icon:'◉',why:'数据 Tool 依次尝试 FRED 实时批量 CSV、美国财政部实时 CSV、带日期的本地官方数据快照；每次选择都会写入 Trace。',input:['start_date'],output:['rate_curve_history','Grounded rate Evidence','Source provenance'],code:'rate_sources.py / native_http.py'},
  S1:{name:'S1 Strategy Tool',icon:'⌁',why:'纯函数计算滚动 z-score，并寻找最近一笔已完成持有期的历史信号。',input:['rate_curve_history','lookback','threshold','holding','DV01','cost'],output:['One closed paper trade','P&L'],code:'rate_strategy.py'},
  E1:{name:'E1 Eval',icon:'✓',why:'Eval 独立重算 P&L，并检查无 lookahead、paper-only、无真实订单。',input:['rate_strategy_simulation'],output:['Contract checks','PASS / FAIL'],code:'rate_strategy.py'},
};

function rateConfigNumber(name) {
  return Number(rateWorkbenchState.config[name]);
}

function rateNodeStatus(nodeId) {
  const run = rateWorkbenchState.run;
  if (run) {
    if (nodeId === 'E1' && !run.eval?.passed) return 'failed';
    return 'completed';
  }
  if (rateWorkbenchState.error) return nodeId === 'D1' ? 'failed' : ['G1','P1','R1'].includes(nodeId) ? 'completed' : 'waiting';
  if (rateWorkbenchState.busy) return nodeId === 'D1' ? 'running' : ['G1','P1','R1'].includes(nodeId) ? 'completed' : 'waiting';
  return nodeId === 'G1' ? 'ready' : 'waiting';
}

function rateRenderInput() {
  const panel = document.querySelector('.input-panel');
  if (!panel) return;
  let overlay = panel.querySelector(':scope > .rate-input-content');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.className = 'rate-input-content';
    panel.appendChild(overlay);
  }
  [...panel.children].forEach((child) => { child.hidden = child !== overlay; });
  overlay.hidden = false;
  const c = rateWorkbenchState.config;
  overlay.innerHTML = `<div class="input-title"><div><div class="kicker">RATE STRATEGY INPUT</div><h2>一次跑通 2s10s Agent Simulation</h2></div><span class="pill">DETERMINISTIC · PAPER ONLY</span></div>
    <div class="rate-goal"><strong>Goal</strong><span>读取公开 DGS2 / DGS10 → 生成曲线均值回归信号 → 完成一笔历史 paper trade → Eval</span></div>
    <div class="rate-config-grid">
      <label>Lookback<input data-rate-field="lookback_days" value="${esc(c.lookback_days)}" inputmode="numeric"><small>observations</small></label>
      <label>Entry z<input data-rate-field="entry_z" value="${esc(c.entry_z)}" inputmode="decimal"><small>absolute threshold</small></label>
      <label>Holding<input data-rate-field="holding_days" value="${esc(c.holding_days)}" inputmode="numeric"><small>observations</small></label>
      <label>DV01<input data-rate-field="dv01_usd_per_bp" value="${esc(c.dv01_usd_per_bp)}" inputmode="decimal"><small>USD / bp</small></label>
      <label>Round-trip cost<input data-rate-field="round_trip_cost_bps" value="${esc(c.round_trip_cost_bps)}" inputmode="decimal"><small>basis points</small></label>
      <div class="rate-run-actions"><button id="rate-run-once" class="btn primary" ${rateWorkbenchState.busy ? 'disabled' : ''}>${rateWorkbenchState.busy ? 'D1 Resolving rate source…' : '▶ Run One Simulation'}</button><button id="rate-export" class="btn" ${rateWorkbenchState.run ? '' : 'disabled'}>⇩ JSON</button></div>
    </div>
    <p class="rate-rule">利差 = 10Y − 2Y；z ≤ −阈值做 steepener，z ≥ 阈值做 flattener；固定持有后按 DV01 近似平仓。</p>
    ${rateWorkbenchState.error ? `<div class="eval-diagnostic"><strong>Run failed:</strong> ${esc(rateWorkbenchState.error)}</div>` : ''}`;
  overlay.querySelectorAll('[data-rate-field]').forEach((input) => input.addEventListener('input', () => {
    rateWorkbenchState.config[input.dataset.rateField] = input.value;
  }));
  overlay.querySelector('#rate-run-once')?.addEventListener('click', rateRunOnce);
  overlay.querySelector('#rate-export')?.addEventListener('click', rateExportRun);
}

function rateRenderFlow() {
  const panel = document.querySelector('.execution');
  if (!panel) return;
  let overlay = panel.querySelector(':scope > .rate-execution-content');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.className = 'rate-execution-content';
    panel.appendChild(overlay);
  }
  [...panel.children].forEach((child) => { child.hidden = child !== overlay; });
  overlay.hidden = false;
  const run = rateWorkbenchState.run;
  const trace = run?.trace || rateWorkbenchState.failureTrace;
  const nodes = Object.entries(RATE_NODE_META);
  overlay.innerHTML = `<div class="execution-head"><div class="execution-title"><h2>Agent 运行过程</h2><span class="pill ${rateWorkbenchState.busy ? 'running' : run?.eval?.passed ? 'done' : rateWorkbenchState.error ? 'fail' : ''}">${rateWorkbenchState.busy ? 'RUNNING' : run ? 'COMPLETED' : rateWorkbenchState.error ? 'FAILED' : 'IDLE'}</span></div><div class="run-meta"><span>${esc(run?.run_id || 'No active run')}</span><span>${run ? '2/2 Tool tasks' : rateWorkbenchState.error ? 'D1 failed' : '0/2 Tool tasks'}</span><span>${trace.length} trace events</span></div></div>
    <div class="flow-scroll"><div class="flow rate-agent-flow">${nodes.map(([id,meta],index) => {
      const status = rateNodeStatus(id);
      return `<article class="node ${status} ${rateWorkbenchState.selectedNode === id ? 'selected' : ''}" data-rate-node="${id}" data-node="${id}"><span class="node-index">${index + 1}</span><strong class="node-name">${esc(meta.name)}</strong><span class="node-icon">${meta.icon}</span><span class="node-status">${status}</span><span class="checkpoint-marker">${id === 'E1' && run?.eval?.passed ? 'EVAL PASS' : ''}</span></article>`;
    }).join('')}</div></div>`;
  overlay.querySelectorAll('[data-rate-node]').forEach((node) => node.addEventListener('click', () => {
    rateWorkbenchState.selectedNode = node.dataset.rateNode;
    appState.selectedDetailTab = 'logic';
    rateRenderFlow();
    rateRenderDetail();
    rateRenderStatusBar();
  }));
}

function rateSelectedPayload() {
  const run = rateWorkbenchState.run;
  if (!run) return {configuration:rateWorkbenchState.config};
  if (rateWorkbenchState.selectedNode === 'P1') return run.plan;
  if (rateWorkbenchState.selectedNode === 'R1') return run.architecture;
  if (rateWorkbenchState.selectedNode === 'D1') return {data:run.data,evidence:run.evidence};
  if (rateWorkbenchState.selectedNode === 'S1') return run.simulation;
  if (rateWorkbenchState.selectedNode === 'E1') return run.eval;
  return {goal:run.goal,configuration:run.simulation?.configuration};
}

function rateRenderTrace() {
  const trace = rateWorkbenchState.run?.trace || rateWorkbenchState.failureTrace;
  if (!trace.length) return '<div class="empty">点击 Run One Simulation 后，这里逐步显示 Planner → Runtime → Tool → Observation → Eval。</div>';
  return `<div class="rate-trace-list">${trace.map((row) => {
    const failed = row.event === 'tool_execution_failed' || (row.event === 'data_source_attempt' && row.status === 'FAILED');
    const retry = row.event === 'tool_retry_scheduled';
    const fallback = row.event === 'data_source_fallback_selected';
    const status = failed ? (row.retryable ? 'RETRYABLE' : 'FAILED') : retry ? `RETRY ${row.next_attempt}` : fallback ? 'FALLBACK' : row.status || (row.passed === true ? 'PASS' : row.passed === false ? 'FAIL' : 'RECORDED');
    const detail = `${row.task_id}${row.tool_name ? ` · ${row.tool_name}` : ''}${row.provider ? ` · ${row.provider}` : ''}${row.source_mode ? ` · ${row.source_mode}` : ''}${row.source_freshness ? ` · ${row.source_freshness}` : ''}${row.as_of ? ` · as_of ${row.as_of}` : ''}${row.attempt ? ` · attempt ${row.attempt}/${row.max_attempts || '?'}` : ''}${row.delay_ms ? ` · backoff ${row.delay_ms}ms` : ''}${row.error_message ? ` · ${row.error_message}` : ''}`;
    return `<article class="rate-trace-row ${row.task_id === rateWorkbenchState.selectedNode ? 'selected' : ''}"><span class="rate-seq">${esc(row.sequence)}</span><div><strong>${esc(row.event)}</strong><small>${esc(detail)}</small></div><span class="pill ${failed ? 'fail' : retry ? 'running' : row.passed === false ? 'fail' : ['COMPLETED','SELECTED'].includes(row.status) || row.passed === true ? 'done' : ''}">${esc(status)}</span></article>`;
  }).join('')}</div>`;
}

function rateRenderLogic() {
  const meta = RATE_NODE_META[rateWorkbenchState.selectedNode];
  return `<div class="logic-grid"><div class="logic-card"><div class="kicker">${esc(rateWorkbenchState.selectedNode)} · ${esc(meta.name)}</div><h4>WHY</h4><p>${esc(meta.why)}</p><h4>INPUT</h4><ul>${meta.input.map((row) => `<li>${esc(row)}</li>`).join('')}</ul><h4>OUTPUT</h4><ul>${meta.output.map((row) => `<li>${esc(row)}</li>`).join('')}</ul><h4>RELATED CODE</h4><p><strong>${esc(meta.code)}</strong></p></div><pre class="codebox">${esc(pretty(rateSelectedPayload()))}</pre></div>`;
}

function rateRenderEvidence() {
  const run = rateWorkbenchState.run;
  if (!run) return '<div class="empty">D1 完成后显示数据来源、LIVE/SNAPSHOT 状态及 Evidence。</div>';
  const latest = run.data.observations[run.data.observations.length - 1];
  const sourceAttempts = run.data.source_attempts || [];
  return `<div class="rate-evidence-summary"><div><span>Selected source</span><strong>${esc(run.data.provider)}</strong></div><div><span>Mode</span><strong>${esc(run.data.source_freshness)} · ${esc(run.data.source_mode)}</strong></div><div><span>Common observations</span><strong>${esc(run.data.observation_count)}</strong></div><div><span>As of</span><strong>${esc(run.data.as_of)}</strong></div><div><span>Latest 2s10s</span><strong>${esc(latest.spread_bps)} bp</strong></div></div>${run.data.source_freshness === 'SNAPSHOT' ? `<div class="eval-diagnostic"><strong>Offline snapshot:</strong> captured ${esc(run.data.snapshot_captured_at)}; data as of ${esc(run.data.as_of)}. This is not a live quote.</div>` : ''}<div class="evidence-list">${sourceAttempts.map((row) => `<article class="evidence-card"><h4>${esc(row.provider)} · ${esc(row.status)}</h4><div class="card-meta"><span>${esc(row.source_mode)}</span>${row.error_message ? `<span>${esc(row.error_message)}</span>` : ''}</div></article>`).join('')}${run.evidence.map((row) => `<article class="evidence-card"><h4>${esc(row.evidence_id)} · ${esc(row.source.title)}</h4><div class="card-meta"><span>${esc(row.source.publisher)}</span><span>as_of ${esc(row.as_of)}</span><span>${esc(row.value)} ${esc(row.unit)}</span><span>common-date aligned</span></div></article>`).join('')}</div>`;
}

function rateRenderState() {
  const run = rateWorkbenchState.run;
  if (!run) return '<div class="empty">State appears after a run.</div>';
  return `<div class="state-grid"><section class="state-card"><div class="kicker">STATE · NOW</div><h4>Current Runtime View</h4><dl class="kv"><dt>run.status</dt><dd>${esc(run.status)}</dd><dt>phase</dt><dd>${esc(run.state.phase)}</dd><dt>current task</dt><dd>${esc(run.state.current_task || 'none')}</dd><dt>completed</dt><dd>${esc(run.state.completed_tasks.join(', '))}</dd><dt>trace events</dt><dd>${run.trace.length}</dd></dl></section><section class="state-card"><div class="kicker">GUARDRAILS</div><h4>Execution Boundary</h4><dl class="kv"><dt>paper only</dt><dd>${run.guardrails.paper_only}</dd><dt>broker connection</dt><dd>${run.guardrails.broker_connection}</dd><dt>automatic execution</dt><dd>${run.guardrails.automatic_execution}</dd><dt>LLM model</dt><dd>${esc(run.architecture.model)}</dd><dt>lookahead</dt><dd>${run.simulation.guardrails.lookahead_used_for_entry_signal}</dd></dl></section></div>`;
}

function rateRenderCheckpoint() {
  return `<div class="rate-checkpoint-empty"><div class="kicker">CHECKPOINT · EXPLICITLY NOT WIRED IN V1</div><h3>本次同步 Run 没有 durable checkpoint</h3><p>组件保留，用来学习 State 与 Checkpoint 的差别：当前 run artifact 只存在于浏览器和本次 HTTP 响应；刷新后不会恢复。等这条最小策略稳定后，再增加“D1 数据完成后落盘并可 resume”。</p><pre class="codebox">${esc(pretty({checkpoints:rateWorkbenchState.run?.checkpoints || [],restore_enabled:false,next_learning_boundary:'persist D1 observation then resume S1'}))}</pre></div>`;
}

function rateRenderArchitecture() {
  return `<div class="kicker">RATE AGENT ARCHITECTURE</div><h3>固定 Planner，完整 Runtime 边界</h3><div class="architecture-flow rate-architecture"><span class="arch-node">Goal</span><span class="arch-arrow">→</span><span class="arch-node">Planner</span><span class="arch-arrow">→</span><span class="arch-node">Runtime</span><span class="arch-arrow">→</span><span class="arch-node">Tool Registry</span><span class="arch-arrow">→</span><span class="arch-node">D1 Source Ladder</span><span class="arch-arrow">→</span><span class="arch-node">S1 Simulation</span><span class="arch-arrow">→</span><span class="arch-node">E1 Eval</span></div><div class="design-list"><div class="design-item"><strong>Planner</strong><p>固定 D1 → S1 DAG；第一次学习不引入自由规划噪声。</p></div><div class="design-item"><strong>Runtime</strong><p>查 Registry、验证 schema、记录每个边界的 trace。</p></div><div class="design-item"><strong>Source ladder</strong><p>FRED live → Treasury live → disclosed snapshot；失败不会伪装成实时成功。</p></div><div class="design-item"><strong>Tools</strong><p>函数实际做事；D1 读数据，S1 运行纯计算。</p></div><div class="design-item"><strong>Evidence</strong><p>DGS2/DGS10 保留 provider、series、as_of 和 source URI。</p></div><div class="design-item"><strong>Eval</strong><p>重算 P&L，检查 paper-only、无 lookahead、无真实订单。</p></div><div class="design-item"><strong>Model</strong><p>V1 为 none_deterministic_v1；Agent 不等于必须使用 LLM。</p></div></div>`;
}

function rateRenderDetail() {
  document.querySelectorAll('.detail-tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.detailTab === appState.selectedDetailTab));
  const body = document.querySelector('#detail-body');
  if (!body) return;
  if (appState.selectedDetailTab === 'trace') body.innerHTML = rateRenderTrace();
  else if (appState.selectedDetailTab === 'logic') body.innerHTML = rateRenderLogic();
  else if (appState.selectedDetailTab === 'evidence') body.innerHTML = rateRenderEvidence();
  else if (appState.selectedDetailTab === 'state') body.innerHTML = rateRenderState();
  else if (appState.selectedDetailTab === 'checkpoint') body.innerHTML = rateRenderCheckpoint();
  else body.innerHTML = rateRenderArchitecture();
}

function rateOutputInspector() {
  const run = rateWorkbenchState.run;
  if (!run) return '<div class="empty">运行后显示这一笔交易的输入、信号、成本与 P&L。</div>';
  const trade = run.simulation.completed_trade;
  return `<div class="output-stage"><div><div class="kicker">ONE CLOSED PAPER TRADE</div><strong>${esc(trade.action)}</strong></div><span class="pill ${trade.net_pnl_usd >= 0 ? 'done' : 'fail'}">${trade.net_pnl_usd >= 0 ? '+' : ''}$${esc(trade.net_pnl_usd)}</span></div><section class="output-section"><h3>${esc(trade.paper_trade_id)}</h3><dl class="kv"><dt>entry</dt><dd>${esc(trade.entry_date)} · ${esc(trade.entry_spread_bps)} bp</dd><dt>exit</dt><dd>${esc(trade.exit_date)} · ${esc(trade.exit_spread_bps)} bp</dd><dt>spread move</dt><dd>${esc(trade.spread_change_bps)} bp</dd><dt>gross</dt><dd>$${esc(trade.gross_pnl_usd)}</dd><dt>cost</dt><dd>$${esc(trade.cost_usd)}</dd><dt>net</dt><dd>$${esc(trade.net_pnl_usd)}</dd></dl></section><section class="output-section"><h3>Latest context</h3><p>${esc(run.simulation.latest_market_context.action)} · z ${esc(run.simulation.latest_market_context.z_score)} · ${esc(run.data.as_of)}</p></section>`;
}

function rateEvalInspector() {
  const evaluation = rateWorkbenchState.run?.eval;
  if (!evaluation) return '<div class="empty">E1 完成后显示 contract checks。</div>';
  return `<div class="output-stage"><div><div class="kicker">E1 EVALUATION</div><strong>${Object.values(evaluation.checks).filter(Boolean).length}/${Object.keys(evaluation.checks).length} PASS</strong></div><span class="pill ${evaluation.passed ? 'pass' : 'fail'}">${evaluation.passed ? 'PASS' : 'FAIL'}</span></div><div class="eval-list">${Object.entries(evaluation.checks).map(([name,passed]) => `<article class="eval-card"><h4>${passed ? '✓' : '✕'} ${esc(name)} <span class="pill ${passed ? 'pass' : 'fail'}">${passed ? 'PASS' : 'FAIL'}</span></h4></article>`).join('')}</div>`;
}

function rateRenderInspector() {
  document.querySelectorAll('.inspector-tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.inspectorTab === appState.selectedInspectorTab));
  const body = document.querySelector('#inspector-body');
  if (!body) return;
  if (appState.selectedInspectorTab === 'output') body.innerHTML = rateOutputInspector();
  else if (appState.selectedInspectorTab === 'checkpoint') body.innerHTML = rateRenderCheckpoint();
  else if (appState.selectedInspectorTab === 'eval') body.innerHTML = rateEvalInspector();
  else body.innerHTML = `<pre class="rawbox">${esc(pretty(rateWorkbenchState.run))}</pre>`;
}

function rateRenderStatusBar() {
  const run = rateWorkbenchState.run;
  const meta = RATE_NODE_META[rateWorkbenchState.selectedNode];
  document.querySelector('#status-current').textContent = meta.name;
  document.querySelector('#status-tasks').textContent = run ? '2/2' : '—';
  document.querySelector('#status-evidence').textContent = run?.evidence?.length || 0;
  document.querySelector('#status-trace').textContent = run?.trace?.length || 0;
  document.querySelector('#status-checkpoint').textContent = 'NOT WIRED V1';
  document.querySelector('#status-save').textContent = '—';
}

function rateRenderAll() {
  document.querySelector('.workspace')?.classList.remove('r12-strategy-workspace-mode');
  document.querySelector('.detail')?.classList.remove('strategy-center-mode');
  const input = document.querySelector('.input-panel');
  const execution = document.querySelector('.execution');
  const tabs = document.querySelector('.detail > .tabs');
  if (input) input.hidden = false;
  if (execution) execution.hidden = false;
  if (tabs) tabs.hidden = false;
  document.querySelectorAll('.nav-btn').forEach((button) => button.classList.toggle('active', button.dataset.nav === 'strategy'));
  rateRenderInput();
  rateRenderFlow();
  rateRenderDetail();
  rateRenderInspector();
  rateRenderStatusBar();
}

function rateRestoreOriginalPanels() {
  const input = document.querySelector('.input-panel');
  const execution = document.querySelector('.execution');
  [input, execution].forEach((panel) => {
    if (!panel) return;
    [...panel.children].forEach((child) => {
      child.hidden = child.classList.contains('rate-input-content') || child.classList.contains('rate-execution-content');
    });
    panel.hidden = false;
  });
  const tabs = document.querySelector('.detail > .tabs');
  if (tabs) tabs.hidden = false;
}

async function rateRunOnce() {
  rateWorkbenchState.busy = true;
  rateWorkbenchState.error = null;
  rateWorkbenchState.run = null;
  rateWorkbenchState.failureTrace = [];
  rateWorkbenchState.selectedNode = 'D1';
  appState.selectedDetailTab = 'trace';
  appState.selectedInspectorTab = 'output';
  rateRenderAll();
  try {
    const response = await fetch('/api/rates/run-once', {method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},cache:'no-store',body:JSON.stringify({
      lookback_days:rateConfigNumber('lookback_days'),entry_z:rateConfigNumber('entry_z'),holding_days:rateConfigNumber('holding_days'),dv01_usd_per_bp:rateConfigNumber('dv01_usd_per_bp'),round_trip_cost_bps:rateConfigNumber('round_trip_cost_bps'),
    })});
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      const runError = new Error(payload.error?.message || `HTTP ${response.status}`);
      runError.trace = payload.error?.trace || [];
      throw runError;
    }
    rateWorkbenchState.run = payload.run;
    rateWorkbenchState.selectedNode = 'E1';
    appState.selectedInspectorTab = 'eval';
    toast(`Rate Agent completed · ${payload.run.eval.passed ? 'EVAL PASS' : 'EVAL FAIL'}`);
  } catch (error) {
    rateWorkbenchState.error = error.message;
    rateWorkbenchState.failureTrace = error.trace || [];
    rateWorkbenchState.selectedNode = 'D1';
    toast(`Rate Agent: ${error.message}`);
  } finally {
    rateWorkbenchState.busy = false;
    rateRenderAll();
  }
}

function rateExportRun() {
  if (!rateWorkbenchState.run) return;
  const blob = new Blob([pretty(rateWorkbenchState.run)], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${rateWorkbenchState.run.run_id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

const rateBaseRenderAll = renderAll;
const rateBaseRenderDetail = renderDetail;
const rateBaseRenderInspector = renderInspector;
const rateBaseRenderStatusBar = renderStatusBar;

renderAll = function renderRateAwareAll() {
  if (appState.selectedNav === 'strategy') return rateRenderAll();
  rateRestoreOriginalPanels();
  return rateBaseRenderAll();
};
renderDetail = function renderRateAwareDetail() {
  if (appState.selectedNav === 'strategy') return rateRenderDetail();
  return rateBaseRenderDetail();
};
renderInspector = function renderRateAwareInspector() {
  if (appState.selectedNav === 'strategy') return rateRenderInspector();
  return rateBaseRenderInspector();
};
renderStatusBar = function renderRateAwareStatusBar() {
  if (appState.selectedNav === 'strategy') return rateRenderStatusBar();
  return rateBaseRenderStatusBar();
};
openR12StrategyCenter = function openRateStrategyCenter() {
  appState.selectedNav = 'strategy';
  appState.selectedDetailTab = appState.selectedDetailTab || 'trace';
  rateRenderAll();
};

const strategyNav = document.querySelector('[data-nav="strategy"]');
if (strategyNav) {
  strategyNav.querySelector('.nav-ico').textContent = '⌁';
  strategyNav.querySelector('.nav-label').textContent = '利率策略';
}
document.addEventListener('keydown', (event) => {
  if (appState.selectedNav !== 'strategy' || !(event.metaKey || event.ctrlKey) || event.key !== 'Enter') return;
  event.preventDefault();
  event.stopImmediatePropagation();
  rateRunOnce();
}, true);

openR12StrategyCenter();
