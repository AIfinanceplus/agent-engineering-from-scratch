/* R10 Step 2 UI: T1 numerical target -> numerical gap -> standardized payoff template. */

NODE_META.T1 = {
  name: 'T1 Numerical Research Target',
  code: 'r10_investment.py',
  why: 'T1 只有在 S1 数值信号与 F1 baseline / direction / horizon 可对齐时才生成点目标。当前规则是透明的一步变化延续基线，不是 calibrated forecast。',
  input: ['S1 comparable numeric signal', 'F1 open forecast contract'],
  output: ['Numerical target', 'Method', 'Horizon', 'Calibration status'],
};

function r10Step2InstallTargetNode() {
  const flow = document.querySelector('.flow');
  const i1 = document.querySelector('.node[data-node="I1"]');
  if (!flow || !i1 || document.querySelector('.node[data-node="T1"]')) return;
  const node = document.createElement('article');
  node.className = 'node';
  node.dataset.node = 'T1';
  node.innerHTML = '<span class="node-index">9</span><strong class="node-name">T1 Numeric Target</strong><span class="node-icon">#</span><span class="node-status">waiting</span><span class="checkpoint-marker"></span>';
  flow.insertBefore(node, i1);
  const i1Index = i1.querySelector('.node-index');
  if (i1Index) i1Index.textContent = '10';
  const ev = document.querySelector('.node[data-node="EV"] .node-index');
  if (ev) ev.textContent = '11';
  node.addEventListener('click', () => {
    appState.selectedNode = 'T1';
    appState.selectedDetailTab = 'logic';
    renderFlow(); renderDetail(); renderStatusBar();
  });
}
r10Step2InstallTargetNode();

const r10Step2BaseNodeState = nodeState;
nodeState = function r10Step2NodeState(node) {
  if (node === 'T1') {
    if (appState.run?.domain === 'policy') return 'not_applicable';
    return taskMap().T1?.status || 'waiting';
  }
  return r10Step2BaseNodeState(node);
};

const r10Step2BaseNodePayload = nodePayload;
nodePayload = function r10Step2NodePayload(node) {
  if (node === 'T1') return appState.run?.numerical_research_target || appState.run?.results?.T1 || null;
  return r10Step2BaseNodePayload(node);
};

const r10Step2BaseRenderFlow = renderFlow;
renderFlow = function r10Step2RenderFlow() {
  r10Step2BaseRenderFlow();
  const t1 = document.querySelector('.node[data-node="T1"]');
  if (t1 && appState.run?.domain === 'policy') {
    const status = t1.querySelector('.node-status');
    if (status) status.innerHTML = '<span class="pill">N/A POLICY</span>';
  }
};

function r10Step2TargetCard(target) {
  if (!target) return '<div class="r10-view-card"><span class="label">T1 Numerical Target</span><h4>waiting</h4></div>';
  return `<div class="r10-view-card"><span class="label">T1 Numerical Research Target</span>
    <h4>${esc(target.status || '—')}</h4>
    <p>Baseline: <strong>${esc(target.baseline_value ?? '—')}%</strong> · previous ${esc(target.previous_value ?? '—')}%</p>
    <p>Observed change: <strong>${esc(target.observed_change_pp ?? '—')} pp</strong></p>
    <p>Target: <strong>${esc(target.target_value ?? '—')}%</strong> · ${esc(target.target_gap_from_baseline_bp ?? '—')} bp</p>
    <p>Due: ${esc(target.due_date || '—')}</p>
    <p>Method: <code>${esc(target.method || '—')}</code></p>
    <p><strong>${esc(target.calibration_status || '—')}</strong></p>
  </div>`;
}

function r10Step2ScenarioTemplate(template) {
  const rows = template?.scenarios || [];
  return `<section class="output-section">
    <h3>Scenario Payoff Bridge</h3>
    <p class="r10-status">${esc(template?.status || '—')}</p>
    <p>Exposure: <strong>${esc(template?.exposure || '—')}</strong> · payoff unit=<strong>${esc(template?.payoff_unit || '—')}</strong></p>
    <p>Instrument P&amp;L: <strong>${esc(template?.instrument_pnl_status || '—')}</strong>. 这里的 payoff 是底层 market move 的标准化单位暴露，不是某只债券/ETF 的真实收益。</p>
    ${rows.length ? `<div class="evidence-list">${rows.map((row) => `<article class="evidence-card"><h4>${esc(row.name)}</h4><div class="card-meta"><span>market move ${esc(row.market_move_bp)} bp</span><span>normalized payoff ${esc(row.payoff)}</span><span>probability INPUT REQUIRED</span></div><p>${esc(row.meaning || '')}</p></article>`).join('')}</div>` : '<div class="empty">没有数值 gap，因此不生成 payoff template。</div>'}
  </section>`;
}

renderR10DecisionLayer = function renderR10Step2DecisionLayer() {
  const decision = appState.run?.investment_decision || appState.run?.results?.I1;
  const target = appState.run?.numerical_research_target || appState.run?.results?.T1;
  if (!decision) {
    return `<section class="output-section"><h3>R10 Step 2 · Numerical Pricing</h3><p>等待 T1 / I1：数值目标只有在 S1 与 F1 可比较时才生成。</p></section>`;
  }
  const research = decision.research_view || {};
  const forecast = research.comparable_market_forecast || {};
  const market = decision.market_implied_view || {};
  const mispricing = decision.mispricing || {};
  const payoffTemplate = decision.scenario_payoff_template || {};
  const ev = appState.run?.r10_ev || decision.expected_value || {};
  const position = decision.position_gate || {};
  const five = market.five_year_inflation_compensation;
  const ten = market.ten_year_inflation_compensation;

  return `
    <section class="output-section">
      <h3>R10 Step 2 · Research Target ↔ Market Value</h3>
      <div class="r10-comparison">
        ${r10Step2TargetCard(target)}
        <div class="r10-view-card"><span class="label">Observed Market Value</span><h4>Inflation compensation</h4><p>5Y: <strong>${esc(r10Value(five))}</strong> · ${esc(five?.as_of || '—')}</p><p>10Y context: <strong>${esc(r10Value(ten))}</strong> · ${esc(ten?.as_of || '—')}</p><p>F1 direction: <strong>${esc(forecast.expected_direction || forecast.status || '—')}</strong></p><p>2Y Treasury remains explicitly <strong>NOT</strong> a Fed-futures path.</p></div>
      </div>
    </section>
    <section class="output-section">
      <h3>Numerical Mispricing / Research-Market Gap</h3>
      <p class="r10-status">${esc(mispricing.status || '—')}</p>
      <p>${esc(mispricing.pricing_hypothesis || '')}</p>
      <div class="metric-strip"><div class="metric"><span>Market</span><strong>${esc(mispricing.market_baseline ?? '—')}%</strong></div><div class="metric"><span>Research Target</span><strong>${esc(mispricing.research_target ?? '—')}%</strong></div><div class="metric"><span>Gap</span><strong>${esc(mispricing.gap_magnitude_bp ?? '—')} bp</strong></div></div>
      <p>${esc(mispricing.interpretation || mispricing.why_not_numeric || '')}</p>
      <p><code>${esc(mispricing.gap_formula || 'target unavailable')}</code></p>
    </section>
    ${r10Step2ScenarioTemplate(payoffTemplate)}
    <section class="output-section">
      <h3>Expected Value Gate</h3>
      <p><strong>${esc(ev.status || '—')}</strong></p>
      ${ev.net_expected_value == null ? `<p>${esc((decision.expected_value || {}).formula || '')}</p><p>Payoff template 可以来自数值 gap；概率仍必须显式输入。</p>` : `<div class="metric-strip"><div class="metric"><span>Gross EV</span><strong>${esc(ev.gross_expected_value)}</strong></div><div class="metric"><span>Cost</span><strong>${esc(ev.transaction_cost)}</strong></div><div class="metric"><span>Net EV</span><strong>${esc(ev.net_expected_value)}</strong></div></div><p>${esc(ev.interpretation || '')}</p>`}
      <p>Position gate: <strong>${esc(position.status || '—')}</strong> · ${esc(position.position || 'NONE')}</p>
    </section>
    ${renderR10EVLab()}`;
};

renderR10EVLab = function renderR10Step2EVLab() {
  const decision = appState.run?.investment_decision || appState.run?.results?.I1 || {};
  const template = decision.scenario_payoff_template || {};
  const rows = template.scenarios || [];
  const defaults = [0,1,2].map((index) => rows[index] || {});
  return `
    <section class="ev-lab">
      <div class="kicker">R10 · EV LAB · STEP 2</div><h3>Scenario Expected Value</h3>
      <p>Payoff 若已有数值 gap，会自动填入标准化 bp 模板；<strong>Probability 仍故意留空</strong>，必须由你明确输入。</p>
      ${defaults.map((row, index) => `<div class="ev-grid"><label>Scenario<input value="${esc(row.name || ['Downside','Base','Upside'][index])}" data-ev-name="${index}"></label><label>Probability<input placeholder="required" data-ev-prob="${index}"></label><label>Payoff<input value="${row.payoff == null ? '' : esc(row.payoff)}" placeholder="${index===0?'-2.0':index===1?'0.5':'2.5'}" data-ev-payoff="${index}"></label></div>`).join('')}
      <div class="ev-footer"><label>Transaction cost<input id="r10-ev-cost" placeholder="0"></label><label>Payoff unit<input id="r10-ev-unit" value="${esc(template.payoff_unit || '')}" placeholder="return_pct / bps / $"></label><button id="r10-ev-calc" class="btn primary">Calculate EV</button></div>
      <p class="muted">标准化 bp payoff ≠ security P&amp;L。转换为真实交易收益需要 instrument sensitivity / DV01 / convexity / basis 等。</p>
    </section>`;
};

renderAll();
