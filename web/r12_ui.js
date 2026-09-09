/* R12 UI: standalone Strategy Opportunity Center + structural logic scanner. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r12.css?v=r12-v1';
  document.head.appendChild(link);
})();

const R12_DEMO_SNAPSHOT = {
  as_of: 'demo-snapshot',
  source: 'user_supplied_demo',
  binary_markets: [
    {
      event_id: 'fed-cut-demo',
      yes_price: 0.48,
      no_price: 0.47,
      estimated_total_cost: 0.01,
      settlement_compatibility_verified: true,
      shortability_verified: false,
    },
  ],
  threshold_groups: [
    {
      group_id: 'cpi-threshold-demo',
      relation: 'greater_than',
      settlement_compatibility_verified: true,
      pair_trade_capability_verified: true,
      estimated_pair_cost: 0.005,
      contracts: [
        {contract_id: 'cpi-gt-3.0', threshold: 3.0, yes_price: 0.70},
        {contract_id: 'cpi-gt-3.5', threshold: 3.5, yes_price: 0.55},
        {contract_id: 'cpi-gt-4.0', threshold: 4.0, yes_price: 0.58},
      ],
    },
  ],
  exclusive_groups: [
    {
      group_id: 'three-outcome-demo',
      mutually_exclusive_verified: true,
      exhaustive_verified: true,
      settlement_compatibility_verified: true,
      shortability_verified: false,
      estimated_total_cost: 0.01,
      contracts: [
        {contract_id: 'A', yes_price: 0.45},
        {contract_id: 'B', yes_price: 0.35},
        {contract_id: 'C', yes_price: 0.15},
      ],
    },
  ],
};

const r12StrategyState = {
  registry: null,
  scan: null,
  loading: false,
  error: null,
  snapshotText: JSON.stringify(R12_DEMO_SNAPSHOT, null, 2),
};

function r12InstallStrategyNav() {
  if (document.querySelector('[data-nav="strategy"]')) return;
  const evalNav = document.querySelector('[data-nav="eval"]');
  const nav = evalNav?.parentElement || document.querySelector('.nav');
  if (!nav) return;
  const button = document.createElement('button');
  button.className = 'nav-btn';
  button.dataset.nav = 'strategy';
  button.innerHTML = '<span class="nav-ico">⌁</span><span class="nav-label">事件市场</span>';
  if (evalNav) nav.insertBefore(button, evalNav);
  else nav.appendChild(button);
  button.addEventListener('click', () => selectNav('strategy'));
}
r12InstallStrategyNav();

function r12StrategyStatusClass(status) {
  if (status === 'ACTIVE_DETERMINISTIC') return 'done';
  if (status.includes('AVAILABLE') || status.includes('READY')) return 'ready';
  return '';
}

function r12RenderRegistry() {
  const registry = r12StrategyState.registry;
  if (!registry) {
    return '<div class="strategy-registry"><div class="empty">Loading strategy registry…</div></div>';
  }
  return `<div class="strategy-registry">${(registry.strategies || []).map((row) => `
    <article class="strategy-card">
      <div class="strategy-card-head"><strong>${esc(row.name)}</strong><span class="pill ${r12StrategyStatusClass(row.status)}">${esc(row.status)}</span></div>
      <div class="strategy-id">${esc(row.strategy_id)}</div>
      <p><strong>Reference:</strong> ${esc(row.reference_type)}</p>
      <p><strong>Next:</strong> ${esc(row.next_dependency)}</p>
    </article>`).join('')}</div>`;
}

function r12RenderOpportunity(row) {
  const paper = row.eligible_for_paper_signal;
  return `<article class="opportunity-card">
    <div class="opportunity-head">
      <div><div class="kicker">${esc(row.subtype)}</div><strong>${esc(row.opportunity_id)}</strong></div>
      <span class="pill ${paper ? 'done' : 'fail'}">${esc(row.status)}</span>
    </div>
    <div class="opportunity-metrics">
      <div><span>Gross edge</span><strong>${esc((row.gross_edge * 100).toFixed(2))}¢</strong></div>
      <div><span>Est. cost</span><strong>${esc((row.estimated_cost * 100).toFixed(2))}¢</strong></div>
      <div><span>Net edge</span><strong>${esc((row.net_edge * 100).toFixed(2))}¢</strong></div>
    </div>
    <p><strong>Candidate:</strong> ${esc(row.candidate_action)}</p>
    <p>${esc(row.rationale)}</p>
    <div class="opportunity-flags">
      <span>Settlement ${row.settlement_compatibility_verified ? '✓' : '×'}</span>
      <span>Implementation ${row.implementation_verified ? '✓' : '×'}</span>
      <span>Liquidity ${esc(row.liquidity_status)}</span>
    </div>
    <details><summary>Reference / Market Contract</summary><pre class="codebox">${esc(pretty({reference_view:row.reference_view, market_view:row.market_view, payoff_status:row.payoff_status, calibration_status:row.calibration_status, downstream_contract:row.downstream_contract}))}</pre></details>
    <div class="paper-only">${esc(row.execution_status)}</div>
  </article>`;
}

function r12RenderScan() {
  const scan = r12StrategyState.scan;
  if (!scan) return '<div class="strategy-scan-empty">运行 scanner 后显示结构性 pricing violations 和 paper-signal eligibility。</div>';
  return `<section class="strategy-results">
    <div class="strategy-summary">
      <div><span>Checks</span><strong>${esc(scan.observations_checked)}</strong></div>
      <div><span>Violations</span><strong>${esc(scan.opportunity_count)}</strong></div>
      <div><span>Paper signals</span><strong>${esc(scan.paper_signal_count)}</strong></div>
      <div><span>Execution</span><strong>PAPER ONLY</strong></div>
    </div>
    ${(scan.opportunities || []).length ? (scan.opportunities || []).map(r12RenderOpportunity).join('') : '<div class="empty">No structural violations in this snapshot.</div>'}
    <details><summary>Raw Structural Scan JSON</summary><pre class="codebox">${esc(pretty(scan))}</pre></details>
  </section>`;
}

function renderR12StrategyCenter() {
  return `<div class="strategy-center">
    <div class="strategy-center-head">
      <div><div class="kicker">R12 · PROBABILITY / PRICING DISCREPANCY ENGINE</div><h2>Strategy Opportunity Center</h2><p>先把所有策略统一成 Opportunity Contract。Step 1 只扫描数学/逻辑约束，不做价格预测，也不自动下单。</p></div>
      <span class="pill done">PAPER SIGNAL ONLY</span>
    </div>
    <section class="strategy-section"><h3>Five-strategy roadmap</h3>${r12RenderRegistry()}</section>
    <section class="strategy-section">
      <div class="strategy-section-head"><div><h3>Structural / Logic Arbitrage Scanner</h3><p>输入的是标准化 market snapshot。未来 live adapter 负责抓行情；scanner 只负责 exact logical constraints。</p></div><button id="r12-reset-demo" class="btn">Reset Demo</button></div>
      <textarea id="r12-snapshot" class="strategy-json-input" spellcheck="false">${esc(r12StrategyState.snapshotText)}</textarea>
      <div class="strategy-actions"><button id="r12-scan" class="btn primary" ${r12StrategyState.loading ? 'disabled' : ''}>${r12StrategyState.loading ? 'Scanning…' : 'Run Structural Scan'}</button><span>Binary complement · Threshold monotonicity · Exhaustive partition</span></div>
      ${r12StrategyState.error ? `<div class="eval-diagnostic"><strong>Scanner error:</strong> ${esc(r12StrategyState.error)}</div>` : ''}
      ${r12RenderScan()}
    </section>
    <section class="strategy-section strategy-boundary">
      <h3>R12 boundary</h3>
      <p><strong>Structural edge ≠ calibrated macro alpha.</strong> 下一步 Cross-market / FOMC / CPI / Options 仍需各自的 reference adapter、settlement contract、成本和概率校准。所有输出先进入 paper signal / human review。</p>
    </section>
  </div>`;
}

async function r12LoadRegistry() {
  if (r12StrategyState.registry || r12StrategyState.loading) return;
  try {
    const response = await fetch('/api/r12/registry', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: '{}',
    });
    const raw = await response.text();
    const payload = JSON.parse(raw);
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
    r12StrategyState.registry = payload.registry;
    if (appState.selectedNav === 'strategy') renderDetail();
  } catch (error) {
    r12StrategyState.error = `Registry: ${error.message}`;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12RunStructuralScan() {
  try {
    const input = document.querySelector('#r12-snapshot');
    if (input) r12StrategyState.snapshotText = input.value;
    const snapshot = JSON.parse(r12StrategyState.snapshotText);
    r12StrategyState.loading = true;
    r12StrategyState.error = null;
    renderDetail();
    const response = await fetch('/api/r12/structural-scan', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify({snapshot}),
    });
    const raw = await response.text();
    let payload;
    try { payload = JSON.parse(raw); }
    catch (_) { throw new Error(`Structural scanner returned non-JSON (HTTP ${response.status})`); }
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
    r12StrategyState.scan = payload.scan;
    toast(`Structural scan: ${payload.scan.paper_signal_count} paper signal(s)`);
  } catch (error) {
    r12StrategyState.error = error.message;
    toast(`Strategy Scanner: ${error.message}`);
  } finally {
    r12StrategyState.loading = false;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

const r12BaseRenderDetail = renderDetail;
renderDetail = function renderR12Detail() {
  if (appState.selectedNav === 'strategy') {
    const body = document.querySelector('#detail-body');
    if (body) body.innerHTML = renderR12StrategyCenter();
    return;
  }
  r12BaseRenderDetail();
};

const r12BaseRenderAll = renderAll;
renderAll = function renderR12All() {
  r12BaseRenderAll();
  const strategyMode = appState.selectedNav === 'strategy';
  const input = document.querySelector('.input-panel');
  const execution = document.querySelector('.execution');
  const detail = document.querySelector('.detail');
  const detailTabs = document.querySelector('.detail > .tabs');
  const workspace = document.querySelector('.workspace');
  if (workspace) workspace.classList.toggle('r12-strategy-workspace-mode', strategyMode);
  if (strategyMode) {
    if (input) input.hidden = true;
    if (execution) execution.hidden = true;
    if (detailTabs) detailTabs.hidden = true;
    if (detail) detail.classList.add('strategy-center-mode');
    renderDetail();
  } else if (detail) {
    detail.classList.remove('strategy-center-mode');
  }
  document.querySelectorAll('.nav-btn').forEach((button) => {
    button.classList.toggle('active', button.dataset.nav === appState.selectedNav);
  });
};

function openR12StrategyCenter() {
  appState.selectedNav = 'strategy';
  renderAll();
  r12LoadRegistry();
}

const r12BaseSelectNav = selectNav;
selectNav = function selectR12Nav(nav) {
  if (nav === 'strategy') return openR12StrategyCenter();
  return r12BaseSelectNav(nav);
};

document.addEventListener('input', (event) => {
  if (event.target?.id === 'r12-snapshot') r12StrategyState.snapshotText = event.target.value;
});

document.addEventListener('click', (event) => {
  if (event.target?.id === 'r12-scan') r12RunStructuralScan();
  if (event.target?.id === 'r12-reset-demo') {
    r12StrategyState.snapshotText = JSON.stringify(R12_DEMO_SNAPSHOT, null, 2);
    r12StrategyState.scan = null;
    r12StrategyState.error = null;
    renderDetail();
  }
});

renderAll();
