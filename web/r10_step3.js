/* R10 Step 3 UI: explicit instrument sensitivity -> P&L -> risk EV -> review gate. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r10_step3.css?v=r10-step3-v1';
  document.head.appendChild(link);
})();

NODE_META.I2 = {
  name: 'I2 Instrument Bridge',
  code: 'r10_instrument.py',
  why: 'I2 不属于宏观 Research DAG。它只在 I1 已经得到 numerical gap 后，使用显式 instrument sensitivity、概率、成本和 risk limits，把 market move 转成真实 P&L 单位。',
  input: ['I1 numerical market gap', 'Explicit P&L-per-bp sensitivity', 'Scenario probabilities', 'Carry / cost / risk limits'],
  output: ['Scenario instrument P&L', 'Net EV', 'Worst Scenario Loss', 'Risk Efficiency', 'Position Review Gate'],
};

function r10Step3InstallNode() {
  const flow = document.querySelector('.flow');
  const i1 = document.querySelector('.node[data-node="I1"]');
  const ev = document.querySelector('.node[data-node="EV"]');
  if (!flow || !i1 || !ev || document.querySelector('.node[data-node="I2"]')) return;
  const node = document.createElement('article');
  node.className = 'node';
  node.dataset.node = 'I2';
  node.innerHTML = '<span class="node-index">11</span><strong class="node-name">I2 Instrument Bridge</strong><span class="node-icon">$</span><span class="node-status">waiting</span><span class="checkpoint-marker"></span>';
  flow.insertBefore(node, ev);
  const evIndex = ev.querySelector('.node-index');
  if (evIndex) evIndex.textContent = '12';
  node.addEventListener('click', () => {
    appState.selectedNode = 'I2';
    appState.selectedDetailTab = 'logic';
    renderFlow(); renderDetail(); renderStatusBar();
  });
}
r10Step3InstallNode();

const r10Step3BaseNodeState = nodeState;
nodeState = function r10Step3NodeState(node) {
  if (node === 'I2') {
    if (appState.run?.domain === 'policy') return 'not_applicable';
    if (appState.run?.r10_instrument_risk_ev) return 'completed';
    if (appState.run?.investment_decision || appState.run?.results?.I1) return 'ready';
    return 'waiting';
  }
  return r10Step3BaseNodeState(node);
};

const r10Step3BaseNodePayload = nodePayload;
nodePayload = function r10Step3NodePayload(node) {
  if (node === 'I2') {
    return appState.run?.r10_instrument_risk_ev || {
      artifact_type: 'r10_instrument_bridge_waiting_for_user_input',
      status: appState.run?.results?.I1 ? 'READY_FOR_EXPLICIT_INSTRUMENT_INPUT' : 'WAITING_FOR_I1',
      rule: 'No ticker/name is used to guess DV01 or P&L sensitivity.',
    };
  }
  return r10Step3BaseNodePayload(node);
};

const r10Step3BaseRenderFlow = renderFlow;
renderFlow = function r10Step3RenderFlow() {
  r10Step3BaseRenderFlow();
  const i2 = document.querySelector('.node[data-node="I2"]');
  if (!i2) return;
  const status = i2.querySelector('.node-status');
  if (appState.run?.domain === 'policy') {
    if (status) status.innerHTML = '<span class="pill">N/A POLICY</span>';
    return;
  }
  if (!status) return;
  if (appState.run?.r10_instrument_risk_ev) status.innerHTML = '<span class="pill done">COMPLETED</span>';
  else if (appState.run?.results?.I1) status.innerHTML = '<span class="pill ready">INPUT READY</span>';
};

function r10Step3TemplateRows() {
  const decision = appState.run?.investment_decision || appState.run?.results?.I1 || {};
  return decision.scenario_payoff_template?.scenarios || [];
}

function r10Step3DefaultDirection() {
  const decision = appState.run?.investment_decision || appState.run?.results?.I1 || {};
  const exposure = decision.scenario_payoff_template?.exposure || '';
  return exposure.startsWith('SHORT_') ? 'SHORT' : 'LONG';
}

function r10Step3ResultCard() {
  const result = appState.run?.r10_instrument_risk_ev;
  if (!result) return '<div class="instrument-empty">运行 Instrument Lab 后，这里显示真实 P&L 单位的 scenario EV 与 risk gate。</div>';
  const instrument = result.instrument || {};
  const gate = result.position_review_gate || {};
  const scenarios = result.scenarios || [];
  return `
    <div class="instrument-result">
      <div class="metric-strip">
        <div class="metric"><span>Net EV</span><strong>${esc(result.net_expected_value ?? '—')} ${esc(instrument.pnl_unit || '')}</strong></div>
        <div class="metric"><span>Worst Loss</span><strong>${esc(result.worst_scenario_loss ?? '—')} ${esc(instrument.pnl_unit || '')}</strong></div>
        <div class="metric"><span>EV / Worst Loss</span><strong>${esc(result.risk_efficiency_ratio ?? '—')}</strong></div>
      </div>
      <p><strong>${esc(gate.status || result.status || '—')}</strong></p>
      <p>${esc(gate.reason || '')}</p>
      <p class="muted">Risk efficiency type: <code>${esc(result.risk_efficiency_type || '')}</code></p>
      <div class="instrument-scenarios">${scenarios.map((row) => `<div><strong>${esc(row.name)}</strong><span>${esc(row.market_move_bp)} bp</span><span>p=${esc(row.probability)}</span><span>net P&amp;L=${esc(row.net_instrument_pnl)} ${esc(instrument.pnl_unit || '')}</span></div>`).join('')}</div>
    </div>`;
}

function renderR10InstrumentLab() {
  const run = appState.run;
  if (!run || run.domain !== 'investment') return '';
  const decision = run.investment_decision || run.results?.I1 || {};
  const template = decision.scenario_payoff_template || {};
  const rows = r10Step3TemplateRows();
  const disabled = template.status !== 'STANDARDIZED_MARKET_MOVE_PAYOFF_TEMPLATE_AVAILABLE';
  const direction = r10Step3DefaultDirection();
  return `
    <section class="instrument-lab">
      <div class="kicker">R10 · STEP 3 · I2</div>
      <h3>Instrument Sensitivity &amp; Risk EV</h3>
      <p>把 I1 的 market move 映射成真实 P&amp;L 单位。系统<strong>不会</strong>根据 ticker/name 猜 DV01；sensitivity 必须显式输入或未来由 instrument adapter 提供。</p>
      ${disabled ? `<div class="eval-diagnostic">Instrument bridge unavailable: ${esc(template.status || 'no numerical gap')}.</div>` : ''}
      <div class="instrument-grid">
        <label>Instrument / strategy<input id="r10-inst-name" placeholder="e.g. 5Y breakeven package"></label>
        <label>Direction<select id="r10-inst-direction"><option value="LONG" ${direction==='LONG'?'selected':''}>LONG</option><option value="SHORT" ${direction==='SHORT'?'selected':''}>SHORT</option></select></label>
        <label>P&amp;L per 1bp<input id="r10-inst-sensitivity" placeholder="e.g. 2500"></label>
        <label>Sensitivity source<input id="r10-inst-source" value="user_input" placeholder="instrument_adapter / broker / user_input"></label>
        <label>P&amp;L unit<input id="r10-inst-unit" value="USD" placeholder="USD / return_pct"></label>
        <label>Carry over horizon<input id="r10-inst-carry" value="0" placeholder="0"></label>
        <label>Transaction cost<input id="r10-inst-cost" value="0" placeholder="0"></label>
        <label>Risk budget<input id="r10-inst-budget" placeholder="required for review gate"></label>
        <label>Loss limit<input id="r10-inst-loss-limit" placeholder="required for review gate"></label>
      </div>
      <div class="instrument-probs">
        ${rows.map((row, index) => `<label><span>${esc(row.name)} · ${esc(row.market_move_bp)}bp</span><input data-i2-prob="${index}" data-i2-name="${esc(row.name)}" placeholder="probability"></label>`).join('') || '<span>No scenario template.</span>'}
      </div>
      <button id="r10-instrument-calc" class="btn primary" ${disabled ? 'disabled' : ''}>Calculate Instrument Risk EV</button>
      <p class="muted">Net EV / worst scenario loss 是教学用 risk-efficiency ratio，<strong>不是 Sharpe、VaR 或 calibrated risk model</strong>。通过 gate 也只表示 eligible for review，不授权执行。</p>
      ${r10Step3ResultCard()}
    </section>`;
}

const r10Step3BaseDecisionLayer = renderR10DecisionLayer;
renderR10DecisionLayer = function renderR10Step3DecisionLayer() {
  return `${r10Step3BaseDecisionLayer()}${renderR10InstrumentLab()}`;
};

function r10Step3Number(id, label, {optional=false}={}) {
  const raw = document.querySelector(id)?.value?.trim();
  if (!raw && optional) return null;
  if (!raw) throw new Error(`${label} is required`);
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`${label} must be numeric`);
  return value;
}

async function calculateR10InstrumentRisk() {
  const run = appState.run;
  if (!run?.run_id || run.domain !== 'investment') return toast('请先完成 Investment Research Run');
  try {
    const probabilities = [...document.querySelectorAll('[data-i2-prob]')].map((input) => ({
      name: input.dataset.i2Name,
      probability: r10Step3Number(`[data-i2-prob="${input.dataset.i2Prob}"]`, `${input.dataset.i2Name} probability`),
      probability_source: 'user_assumption',
    }));
    const payload = {
      run_id: run.run_id,
      instrument_name: document.querySelector('#r10-inst-name')?.value?.trim(),
      position_direction: document.querySelector('#r10-inst-direction')?.value,
      sensitivity_per_bp: r10Step3Number('#r10-inst-sensitivity', 'P&L per 1bp'),
      sensitivity_source: document.querySelector('#r10-inst-source')?.value?.trim(),
      pnl_unit: document.querySelector('#r10-inst-unit')?.value?.trim(),
      scenario_probabilities: probabilities,
      carry: r10Step3Number('#r10-inst-carry', 'Carry'),
      transaction_cost: r10Step3Number('#r10-inst-cost', 'Transaction cost'),
      risk_budget: r10Step3Number('#r10-inst-budget', 'Risk budget', {optional:true}),
      loss_limit: r10Step3Number('#r10-inst-loss-limit', 'Loss limit', {optional:true}),
    };
    const response = await fetch('/api/r10/instrument-risk', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify(payload),
    });
    const raw = await response.text();
    let data;
    try { data = JSON.parse(raw); }
    catch (_) { throw new Error(`Instrument endpoint returned non-JSON (HTTP ${response.status})`); }
    if (!response.ok || !data.ok) throw new Error(data.error?.message || `HTTP ${response.status}`);
    appState.run.r10_instrument_risk_ev = data.instrument_risk_ev;
    renderInspector(); renderFlow();
    toast(`Instrument Risk EV: ${data.instrument_risk_ev.status}`);
  } catch (error) {
    toast(`Instrument Lab: ${error.message}`);
  }
}

document.addEventListener('click', (event) => {
  if (event.target?.id === 'r10-instrument-calc') calculateR10InstrumentRisk();
});

renderAll();
