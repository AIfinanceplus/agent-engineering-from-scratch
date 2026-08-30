/* R10 UI: I1 market comparison, EV Lab, and standalone embedded Evaluation Center. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r10.css?v=r10-v1';
  document.head.appendChild(link);
})();

NODE_META.I1 = {
  name: 'I1 Market vs Research',
  code: 'r10_investment.py',
  why: 'R10 在 S1/D1/F1 与 M6 都完成之后才允许比较 Research View 与 Market View。方向差异不是数值 mispricing；EV 必须有显式概率与 payoff。',
  input: ['S1 Research View', 'D1 Investment Lens', 'F1 Forecast Contract', 'M6 Observed Market Context'],
  output: ['Market Implied View', 'Pricing Hypothesis', 'EV Gate', 'Position Gate'],
};

function r10InstallFlowNode() {
  const flow = document.querySelector('.flow');
  const evNode = document.querySelector('.node[data-node="EV"]');
  if (!flow || !evNode || document.querySelector('.node[data-node="I1"]')) return;
  const node = document.createElement('article');
  node.className = 'node';
  node.dataset.node = 'I1';
  node.innerHTML = '<span class="node-index">9</span><strong class="node-name">I1 Market vs Research</strong><span class="node-icon">≠</span><span class="node-status">waiting</span><span class="checkpoint-marker"></span>';
  flow.insertBefore(node, evNode);
  const evIndex = evNode.querySelector('.node-index');
  if (evIndex) evIndex.textContent = '10';
  node.addEventListener('click', () => {
    appState.selectedNode = 'I1';
    appState.selectedDetailTab = 'logic';
    renderFlow(); renderDetail(); renderStatusBar();
  });
}
r10InstallFlowNode();

const r10BaseNodeState = nodeState;
nodeState = function r10NodeState(node) {
  if (node === 'I1') {
    if (appState.run?.domain === 'policy') return 'not_applicable';
    return taskMap().I1?.status || 'waiting';
  }
  return r10BaseNodeState(node);
};

const r10BaseNodePayload = nodePayload;
nodePayload = function r10NodePayload(node) {
  if (node === 'I1') return appState.run?.investment_decision || appState.run?.results?.I1 || null;
  return r10BaseNodePayload(node);
};

const r10BaseRenderFlow = renderFlow;
renderFlow = function r10RenderFlow() {
  r10BaseRenderFlow();
  const i1 = document.querySelector('.node[data-node="I1"]');
  if (i1 && appState.run?.domain === 'policy') {
    const status = i1.querySelector('.node-status');
    if (status) status.innerHTML = '<span class="pill">N/A POLICY</span>';
  }
};

function r10Value(row) {
  if (!row) return '—';
  const value = row.value ?? row.baseline_metric_value;
  return value == null ? '—' : `${value}%`;
}

function renderR10DecisionLayer() {
  const decision = appState.run?.investment_decision || appState.run?.results?.I1;
  if (!decision) {
    return '<section class="output-section"><h3>R10 · Research vs Market</h3><p>等待 I1：只有 S1 / D1 / F1 / M6 全部完成后才进行比较。</p></section>';
  }
  const research = decision.research_view || {};
  const forecast = research.comparable_market_forecast || {};
  const market = decision.market_implied_view || {};
  const mispricing = decision.mispricing || {};
  const ev = appState.run?.r10_ev || decision.expected_value || {};
  const position = decision.position_gate || {};
  const five = market.five_year_inflation_compensation;
  const ten = market.ten_year_inflation_compensation;

  return `
    <section class="output-section">
      <h3>R10 · Research View ↔ Market View</h3>
      <div class="r10-comparison">
        <div class="r10-view-card"><span class="label">Research View</span><h4>${esc(forecast.target_evidence_id || 'No comparable forecast')}</h4><p>Direction: <strong>${esc(forecast.expected_direction || forecast.status || '—')}</strong></p><p>Baseline: ${esc(forecast.baseline_metric_value ?? '—')} · due ${esc(forecast.due_date || '—')}</p><p>Support: ${esc(forecast.support_score ?? '—')} <small>${esc(forecast.support_score_type || '')}</small></p></div>
        <div class="r10-view-card"><span class="label">Observed Market View</span><h4>Inflation compensation</h4><p>5Y: <strong>${esc(r10Value(five))}</strong> · ${esc(five?.as_of || '—')}</p><p>10Y: <strong>${esc(r10Value(ten))}</strong> · ${esc(ten?.as_of || '—')}</p><p>2Y Treasury is explicitly <strong>NOT</strong> treated as a Fed-futures path.</p></div>
      </div>
    </section>
    <section class="output-section">
      <h3>Pricing Hypothesis / Mispricing Gate</h3>
      <p class="r10-status">${esc(mispricing.status || '—')}</p>
      <p>${esc(mispricing.pricing_hypothesis || '')}</p>
      <ul><li>Market baseline: ${esc(mispricing.market_baseline ?? '—')}%</li><li>Research direction: ${esc(mispricing.research_expected_direction || '—')}</li><li>Numeric gap: ${esc(mispricing.gap_magnitude_pp ?? 'NOT QUANTIFIED')}</li></ul>
      <p>${esc(mispricing.why_not_numeric || '')}</p>
    </section>
    <section class="output-section">
      <h3>Expected Value Gate</h3>
      <p><strong>${esc(ev.status || '—')}</strong></p>
      ${ev.net_expected_value == null ? `<p>${esc((decision.expected_value || {}).formula || '')}</p>` : `<div class="metric-strip"><div class="metric"><span>Gross EV</span><strong>${esc(ev.gross_expected_value)}</strong></div><div class="metric"><span>Cost</span><strong>${esc(ev.transaction_cost)}</strong></div><div class="metric"><span>Net EV</span><strong>${esc(ev.net_expected_value)}</strong></div></div><p>${esc(ev.interpretation || '')}</p>`}
      <p>Position gate: <strong>${esc(position.status || '—')}</strong> · ${esc(position.position || 'NONE')}</p>
    </section>
    ${renderR10EVLab()}`;
}

function renderR10EVLab() {
  return `
    <section class="ev-lab">
      <div class="kicker">R10 · EV LAB</div><h3>Scenario Expected Value</h3>
      <p>这里的概率与 payoff 必须由你明确输入；系统不会把 support score 偷换成概率。</p>
      <div class="ev-grid"><label>Scenario<input value="Downside" data-ev-name="0"></label><label>Probability<input placeholder="0.20" data-ev-prob="0"></label><label>Payoff<input placeholder="-2.0" data-ev-payoff="0"></label></div>
      <div class="ev-grid"><label>Scenario<input value="Base" data-ev-name="1"></label><label>Probability<input placeholder="0.50" data-ev-prob="1"></label><label>Payoff<input placeholder="0.5" data-ev-payoff="1"></label></div>
      <div class="ev-grid"><label>Scenario<input value="Upside" data-ev-name="2"></label><label>Probability<input placeholder="0.30" data-ev-prob="2"></label><label>Payoff<input placeholder="2.5" data-ev-payoff="2"></label></div>
      <div class="ev-footer"><label>Transaction cost<input id="r10-ev-cost" placeholder="0"></label><label>Payoff unit<input id="r10-ev-unit" placeholder="return_pct / bps / $"></label><button id="r10-ev-calc" class="btn primary">Calculate EV</button></div>
    </section>`;
}

const r10PreviousInvestmentDecision = renderInvestmentDecision;
renderInvestmentDecision = function renderR10InvestmentDecision(sections) {
  return `${renderR10DecisionLayer()}${r10PreviousInvestmentDecision(sections)}`;
};

function r10EvalSuite() {
  return appState.run?.embedded_eval_suite || appState.evalSuite || null;
}

function renderR10EvalCenter() {
  const suite = r10EvalSuite();
  const run = appState.run;
  if (!run) return '<div class="eval-center"><div class="empty">先运行 Research，再打开 Evaluation Center。</div></div>';
  if (!suite) {
    const error = run.eval_error;
    return `<div class="eval-center"><div class="eval-center-head"><div><div class="kicker">EVALUATION CENTER</div><h2>Current Run Evaluation</h2></div></div><div class="eval-diagnostic"><strong>Embedded Eval unavailable.</strong><br>${esc(error?.message || 'No embedded suite on this run.')}</div><pre class="codebox">${esc(pretty(error))}</pre></div>`;
  }
  const cases = suite.cases || [];
  const failed = cases.filter((row) => !row.report?.passed).length;
  return `<div class="eval-center">
    <div class="eval-center-head"><div><div class="kicker">EVALUATION CENTER · CURRENT IMMUTABLE RUN</div><h2>${esc(suite.passed)}/${esc(suite.total)} contracts passed</h2><p>Eval 与 Research final result 同包返回；打开这里不会再次 fetch Eval，也不会重新抓 BLS/FRED/EIA。</p></div><span class="pill ${failed ? 'fail' : 'done'}">${failed ? `${failed} FAILED` : 'ALL PASS'}</span></div>
    <div class="eval-summary-grid"><div class="eval-summary-card"><span>Run</span><strong>${esc(run.run_id)}</strong></div><div class="eval-summary-card"><span>Domain</span><strong>${esc(run.domain)}</strong></div><div class="eval-summary-card"><span>Transport</span><strong>EMBEDDED</strong></div><div class="eval-summary-card"><span>Serialization</span><strong>${esc(suite.serialization_contract || '—')}</strong></div></div>
    <div class="eval-diagnostic"><strong>Transport diagnostic:</strong> HTTP Eval fetch = NONE · source re-fetch = NONE · suite source = <code>${esc(run.eval_transport || 'embedded_in_run_v3')}</code>.</div>
    ${cases.map((row, index) => renderR10EvalCase(row, index)).join('')}
    <details><summary>Raw Eval JSON</summary><pre class="codebox">${esc(pretty(suite))}</pre></details>
  </div>`;
}

function renderR10EvalCase(row, index) {
  const report = row.report || {};
  const checks = report.checks || [];
  const caseId = report.case_id || row.case?.case_id || `case-${index + 1}`;
  return `<article class="eval-case"><div class="eval-case-head"><div><div class="kicker">CASE ${index + 1}</div><strong>${esc(caseId)}</strong></div><span class="pill ${report.passed ? 'done' : 'fail'}">${report.passed ? 'PASS' : 'FAIL'}</span></div><div class="eval-checks">${checks.map((check) => `<div class="eval-check"><strong class="${check.passed ? 'eval-pass' : 'eval-fail'}">${check.passed ? '✓' : '×'}</strong><div><strong>${esc(check.label || check.check_id)}</strong>${check.passed ? '' : `<br><span class="eval-fail">${esc(check.failure || '')}</span>`}</div></div>`).join('') || '<div class="empty">No check detail.</div>'}</div></article>`;
}

const r10BaseRenderDetail = renderDetail;
renderDetail = function renderR10Detail() {
  if (appState.selectedNav === 'eval') {
    const body = $('#detail-body');
    if (body) body.innerHTML = renderR10EvalCenter();
    return;
  }
  r10BaseRenderDetail();
};

const r10BaseRenderAll = renderAll;
renderAll = function renderR10All() {
  r10BaseRenderAll();
  const evalMode = appState.selectedNav === 'eval';
  const input = document.querySelector('.input-panel');
  const execution = document.querySelector('.execution');
  const detail = document.querySelector('.detail');
  const detailTabs = document.querySelector('.detail > .tabs');
  if (input) input.hidden = evalMode;
  if (execution) execution.hidden = evalMode;
  if (detailTabs) detailTabs.hidden = evalMode;
  if (detail) detail.classList.toggle('eval-center-mode', evalMode);
  if (evalMode) renderDetail();
};

function openR10EvalCenter() {
  if (!appState.run) return toast('请先运行一次 Research');
  appState.evalSuite = appState.run.embedded_eval_suite || null;
  appState.selectedNav = 'eval';
  appState.selectedNode = 'EV';
  appState.selectedInspectorTab = 'output';
  renderAll();
}

const r10BaseSelectNav = selectNav;
selectNav = function selectR10Nav(nav) {
  if (nav === 'eval') return openR10EvalCenter();
  return r10BaseSelectNav(nav);
};

const r10InspectorEvalTab = document.querySelector('[data-inspector-tab="eval"]');
if (r10InspectorEvalTab) r10InspectorEvalTab.style.display = 'none';

const r10OldEvalButton = $('#eval-btn');
if (r10OldEvalButton) {
  const button = r10OldEvalButton.cloneNode(true);
  button.textContent = '✓ Evaluation Center';
  button.title = 'Open the embedded Evaluation Center; no Eval HTTP request';
  r10OldEvalButton.replaceWith(button);
  button.addEventListener('click', openR10EvalCenter);
}

function r10RequiredNumber(selector, label) {
  const el = document.querySelector(selector);
  const raw = el?.value?.trim();
  if (!raw) throw new Error(`${label} is required`);
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`${label} must be numeric`);
  return value;
}

async function calculateR10EV() {
  const run = appState.run;
  if (!run?.run_id) return toast('请先完成一个 Investment Research Run');
  if (run.domain !== 'investment') return toast('EV Lab 只用于 Investment mode');
  try {
    const scenarios = [0,1,2].map((index) => ({
      name: document.querySelector(`[data-ev-name="${index}"]`)?.value?.trim() || `scenario_${index + 1}`,
      probability: r10RequiredNumber(`[data-ev-prob="${index}"]`, `Scenario ${index + 1} probability`),
      payoff: r10RequiredNumber(`[data-ev-payoff="${index}"]`, `Scenario ${index + 1} payoff`),
      probability_source: 'user_assumption',
    }));
    const costRaw = $('#r10-ev-cost')?.value?.trim();
    const transactionCost = costRaw ? Number(costRaw) : 0;
    if (!Number.isFinite(transactionCost) || transactionCost < 0) throw new Error('Transaction cost must be non-negative');
    const payoffUnit = $('#r10-ev-unit')?.value?.trim() || 'user_defined_payoff_unit';
    const response = await fetch('/api/r10/ev', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify({run_id:run.run_id, scenarios, transaction_cost:transactionCost, payoff_unit:payoffUnit}),
    });
    const raw = await response.text();
    let payload;
    try { payload = JSON.parse(raw); }
    catch (_) { throw new Error(`EV endpoint returned non-JSON (HTTP ${response.status})`); }
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
    appState.run.r10_ev = payload.ev;
    renderInspector();
    toast(`EV calculated: ${payload.ev.status}`);
  } catch (error) {
    toast(`EV Lab: ${error.message}`);
  }
}

document.addEventListener('click', (event) => {
  if (event.target?.id === 'r10-ev-calc') calculateR10EV();
});

renderAll();
