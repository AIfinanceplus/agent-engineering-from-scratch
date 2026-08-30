/* R11 Step 1 UI: I2 candidate -> explicit portfolio constraints -> max admissible scale. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r11.css?v=r11-v1';
  document.head.appendChild(link);
})();

NODE_META.P1 = {
  name: 'P1 Position Sizing',
  code: 'r11_portfolio.py',
  why: 'P1 只在 I2 已经通过 position-review gate 后工作。它求显式约束的交集上限，不做 Kelly、均值方差优化、VaR，也不授权下单。',
  input: ['I2 instrument risk EV', 'Portfolio value / risk budget', 'Current risk usage', 'Capital per reference position', 'Max position fraction / scale cap'],
  output: ['Max admissible scale', 'Binding constraint', 'Scaled EV / worst loss', 'Capital allocation', 'Post-trade risk utilization'],
};

function r11InstallNode() {
  const flow = document.querySelector('.flow');
  const ev = document.querySelector('.node[data-node="EV"]');
  if (!flow || !ev || document.querySelector('.node[data-node="P1"]')) return;
  const node = document.createElement('article');
  node.className = 'node';
  node.dataset.node = 'P1';
  node.innerHTML = '<span class="node-index">12</span><strong class="node-name">P1 Position Sizing</strong><span class="node-icon">%</span><span class="node-status">waiting</span><span class="checkpoint-marker"></span>';
  flow.insertBefore(node, ev);
  const evIndex = ev.querySelector('.node-index');
  if (evIndex) evIndex.textContent = '13';
  node.addEventListener('click', () => {
    appState.selectedNode = 'P1';
    appState.selectedDetailTab = 'logic';
    renderFlow(); renderDetail(); renderStatusBar();
  });
}
r11InstallNode();

function r11I2Eligible() {
  const i2 = appState.run?.r10_instrument_risk_ev;
  return Boolean(i2?.position_review_gate?.eligible_for_review && i2?.position_review_gate?.status === 'ELIGIBLE_FOR_POSITION_REVIEW_NOT_EXECUTION');
}

const r11BaseNodeState = nodeState;
nodeState = function r11NodeState(node) {
  if (node === 'P1') {
    if (appState.run?.domain === 'policy') return 'not_applicable';
    if (appState.run?.r11_position_size) return 'completed';
    if (r11I2Eligible()) return 'ready';
    return 'waiting';
  }
  return r11BaseNodeState(node);
};

const r11BaseNodePayload = nodePayload;
nodePayload = function r11NodePayload(node) {
  if (node === 'P1') {
    return appState.run?.r11_position_size || {
      artifact_type: 'r11_position_sizing_waiting_for_portfolio_inputs',
      status: r11I2Eligible() ? 'READY_FOR_EXPLICIT_PORTFOLIO_INPUT' : 'WAITING_FOR_ELIGIBLE_I2',
      rule: 'Maximum admissible scale is a constraint-intersection ceiling, not an optimal position or executable order.',
    };
  }
  return r11BaseNodePayload(node);
};

const r11BaseRenderFlow = renderFlow;
renderFlow = function r11RenderFlow() {
  r11BaseRenderFlow();
  const p1 = document.querySelector('.node[data-node="P1"]');
  if (!p1) return;
  const status = p1.querySelector('.node-status');
  if (!status) return;
  if (appState.run?.domain === 'policy') {
    status.innerHTML = '<span class="pill">N/A POLICY</span>';
  } else if (appState.run?.r11_position_size) {
    status.innerHTML = '<span class="pill done">COMPLETED</span>';
  } else if (r11I2Eligible()) {
    status.innerHTML = '<span class="pill ready">INPUT READY</span>';
  } else if (appState.run?.r10_instrument_risk_ev) {
    status.innerHTML = '<span class="pill fail">BLOCKED I2</span>';
  }
};

function r11ResultCard() {
  const result = appState.run?.r11_position_size;
  if (!result) return '<div class="sizing-empty">运行 Position Sizing 后，这里显示约束上限、binding constraint、组合风险使用和 capital allocation。</div>';
  const sizing = result.sizing || {};
  const portfolio = result.portfolio || {};
  const economics = result.economics || {};
  const gate = result.position_review_gate || {};
  const instrument = result.instrument || {};
  const bindings = sizing.binding_constraints || [];
  return `
    <div class="sizing-result">
      <div class="metric-strip">
        <div class="metric"><span>Max Scale</span><strong>${esc(sizing.max_admissible_scale ?? '—')}×</strong></div>
        <div class="metric"><span>Scaled Net EV</span><strong>${esc(economics.scaled_net_ev ?? '—')} ${esc(instrument.pnl_unit || '')}</strong></div>
        <div class="metric"><span>Scaled Worst Loss</span><strong>${esc(economics.scaled_worst_scenario_loss ?? '—')} ${esc(instrument.pnl_unit || '')}</strong></div>
      </div>
      <p><strong>${esc(gate.status || result.status || '—')}</strong></p>
      <p>${esc(gate.reason || '')}</p>
      <div class="sizing-facts">
        <div><span>Binding</span><strong>${bindings.length ? bindings.map(esc).join(', ') : '—'}</strong></div>
        <div><span>Scaled sensitivity</span><strong>${esc(instrument.scaled_signed_pnl_per_bp ?? '—')} ${esc(instrument.pnl_unit || '')}/bp</strong></div>
        <div><span>Capital required</span><strong>${esc(portfolio.scaled_capital_required ?? '—')} ${esc(portfolio.portfolio_value_unit || '')}</strong></div>
        <div><span>Capital / NAV</span><strong>${portfolio.scaled_capital_fraction_of_nav == null ? '—' : esc((portfolio.scaled_capital_fraction_of_nav * 100).toFixed(2)) + '%'}</strong></div>
        <div><span>Post-trade risk use</span><strong>${portfolio.post_trade_risk_utilization == null ? '—' : esc((portfolio.post_trade_risk_utilization * 100).toFixed(2)) + '%'}</strong></div>
        <div><span>EV / Worst Loss</span><strong>${esc(economics.risk_efficiency_ratio ?? '—')}</strong></div>
      </div>
      <details><summary>Constraint scales</summary><pre class="codebox">${esc(pretty(sizing.constraint_scales || {}))}</pre></details>
    </div>`;
}

function renderR11SizingLab() {
  const run = appState.run;
  if (!run || run.domain !== 'investment') return '';
  const i2 = run.r10_instrument_risk_ev;
  const eligible = r11I2Eligible();
  const unit = i2?.instrument?.pnl_unit || 'USD';
  return `
    <section class="sizing-lab">
      <div class="kicker">R11 · STEP 1 · P1</div>
      <h3>Position Sizing &amp; Portfolio Risk Budget</h3>
      <p>这里计算的是<strong>最大可接受 reference-position scale</strong>。它不是 Kelly、最优组合或自动仓位建议。</p>
      ${i2 && !eligible ? `<div class="eval-diagnostic">P1 blocked: I2 status=${esc(i2.position_review_gate?.status || i2.status || 'unknown')}.</div>` : ''}
      ${!i2 ? '<div class="eval-diagnostic">先完成 I2 Instrument Bridge。</div>' : ''}
      <div class="sizing-grid">
        <label>Portfolio value<input id="r11-nav" placeholder="e.g. 1000000"></label>
        <label>Unit<input id="r11-unit" value="${esc(unit)}" placeholder="must match I2 P&L unit"></label>
        <label>Total portfolio risk budget<input id="r11-risk-budget" placeholder="same P&L unit"></label>
        <label>Current risk used<input id="r11-risk-used" value="0" placeholder="0"></label>
        <label>Max position % of NAV<input id="r11-max-nav-pct" value="5" placeholder="5"></label>
        <label>Capital / reference position<input id="r11-capital-ref" placeholder="e.g. 50000"></label>
        <label>Capital source<input id="r11-capital-source" value="user_input" placeholder="portfolio_system / user_input"></label>
        <label>Max reference scale<input id="r11-max-scale" placeholder="optional implementation cap"></label>
      </div>
      <button id="r11-size-calc" class="btn primary" ${eligible ? '' : 'disabled'}>Calculate Max Admissible Size</button>
      <p class="muted">Portfolio risk 使用保守 additive worst-scenario budget accounting；当前<strong>不计算 correlation、diversification credit、VaR、margin nonlinearity 或 liquidity impact</strong>。结果只进入 size review，不授权执行。</p>
      ${r11ResultCard()}
    </section>`;
}

const r11BaseDecisionLayer = renderR10DecisionLayer;
renderR10DecisionLayer = function renderR11DecisionLayer() {
  return `${r11BaseDecisionLayer()}${renderR11SizingLab()}`;
};

function r11Number(id, label, {optional=false}={}) {
  const raw = document.querySelector(id)?.value?.trim();
  if (!raw && optional) return null;
  if (!raw) throw new Error(`${label} is required`);
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`${label} must be numeric`);
  return value;
}

async function calculateR11Size() {
  const run = appState.run;
  if (!run?.run_id || run.domain !== 'investment') return toast('请先完成 Investment Research 和 I2');
  try {
    const navPct = r11Number('#r11-max-nav-pct', 'Max position % of NAV');
    const payload = {
      run_id: run.run_id,
      portfolio_value: r11Number('#r11-nav', 'Portfolio value'),
      portfolio_value_unit: document.querySelector('#r11-unit')?.value?.trim(),
      portfolio_risk_budget: r11Number('#r11-risk-budget', 'Portfolio risk budget'),
      portfolio_current_risk_used: r11Number('#r11-risk-used', 'Current risk used'),
      max_position_nav_fraction: navPct / 100,
      capital_required_per_reference_position: r11Number('#r11-capital-ref', 'Capital per reference position'),
      capital_source: document.querySelector('#r11-capital-source')?.value?.trim(),
      max_reference_scale: r11Number('#r11-max-scale', 'Max reference scale', {optional:true}),
    };
    const response = await fetch('/api/r11/size', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify(payload),
    });
    const raw = await response.text();
    let data;
    try { data = JSON.parse(raw); }
    catch (_) { throw new Error(`R11 sizing endpoint returned non-JSON (HTTP ${response.status})`); }
    if (!response.ok || !data.ok) throw new Error(data.error?.message || `HTTP ${response.status}`);
    appState.run.r11_position_size = data.position_size;
    renderInspector(); renderFlow();
    toast(`Position Sizing: ${data.position_size.status}`);
  } catch (error) {
    toast(`Position Sizing: ${error.message}`);
  }
}

document.addEventListener('click', (event) => {
  if (event.target?.id === 'r11-size-calc') calculateR11Size();
});

renderAll();
