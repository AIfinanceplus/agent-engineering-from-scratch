/* R8 professional Decision Lens UI extension. Loaded only by serve_r8.py. */

NODE_META.D1 = {
  name: 'D1 Professional Decision Lens',
  code: 'r8_decision.py',
  why: 'S1 只回答“Evidence 支持什么”。R8 的 D1 才回答“这对 Investment 或 Policy 决策意味着什么”，并且明确暴露缺失的 pricing / causal / incidence / implementation inputs。',
  input: ['S1 Grounded Research', 'Domain Lens'],
  output: ['Professional Decision Brief', 'Decision Guardrails', 'Missing Decision Inputs'],
};

function r8List(items) {
  return `<ul>${(items || []).map((item) => `<li>${esc(item)}</li>`).join('') || '<li>—</li>'}</ul>`;
}

function renderInvestmentDecision(sections) {
  const pricing = sections.market_pricing || {};
  const ev = sections.expected_value || {};
  const position = sections.position_framework || {};
  const risks = sections.risk_map || {};
  const catalysts = sections.catalysts || [];
  return `
    <section class="output-section">
      <h3>Investment Decision Status</h3>
      <div class="metric-strip">
        <div class="metric"><span>Pricing</span><strong>${esc(pricing.status || '—')}</strong></div>
        <div class="metric"><span>Expected Value</span><strong>${esc(ev.status || '—')}</strong></div>
        <div class="metric"><span>Position</span><strong>${esc(position.position || '—')}</strong></div>
      </div>
      <p><strong>${esc(position.status || '—')}</strong> · research bias=${esc(position.research_bias || '—')}</p>
    </section>
    <section class="output-section">
      <h3>Market Pricing</h3>
      <p>${esc(pricing.interpretation || '—')}</p>
      <p><strong>Market-based expectation Evidence:</strong> ${esc((pricing.market_based_expectation_evidence_ids || []).join(', ') || '—')}</p>
      <strong>Missing before trade:</strong>${r8List(pricing.missing_inputs)}
    </section>
    <section class="output-section">
      <h3>Expected Value Discipline</h3>
      <p>${esc(ev.reason || '—')}</p>
      <strong>Required:</strong>${r8List(ev.required_inputs)}
    </section>
    <section class="output-section">
      <h3>Catalysts</h3>
      <ul>${catalysts.map((row) => `<li><strong>${esc(row.evidence_id)}</strong> — ${esc(row.trigger)}<br>${esc(row.why_it_matters)}</li>`).join('') || '<li>—</li>'}</ul>
    </section>
    <section class="output-section">
      <h3>Position Framework</h3>
      <p><strong>Current position:</strong> ${esc(position.position || 'NONE')}</p>
      ${r8List(position.conditions_before_position)}
    </section>
    <section class="output-section">
      <h3>Risk Map</h3>
      <ul>${Object.entries(risks).map(([key, value]) => `<li><strong>${esc(key)}</strong>: ${esc(value)}</li>`).join('')}</ul>
    </section>`;
}

function renderPolicyDecision(sections) {
  const baseline = sections.no_action_baseline || {};
  const cf = sections.counterfactual_analysis || {};
  const distribution = sections.distributional_analysis || {};
  const implementation = sections.implementation || {};
  const actionability = sections.policy_actionability || {};
  const options = sections.option_analysis || [];
  return `
    <section class="output-section">
      <h3>Policy Actionability</h3>
      <div class="metric-strip">
        <div class="metric"><span>Actionability</span><strong>${esc(actionability.status || '—')}</strong></div>
        <div class="metric"><span>Counterfactual</span><strong>${esc(cf.status || '—')}</strong></div>
        <div class="metric"><span>Implementation</span><strong>${esc(implementation.status || '—')}</strong></div>
      </div>
      <p><strong>Current action:</strong> ${esc(actionability.current_action || '—')}</p>
    </section>
    <section class="output-section">
      <h3>No-Action Baseline</h3>
      <p><strong>${esc(baseline.posture || '—')}</strong></p><p>${esc(baseline.rationale || '—')}</p>
      <p>Causal outcome estimate: <strong>${esc(baseline.causal_outcome_estimate || '—')}</strong></p>
    </section>
    <section class="output-section">
      <h3>Option Analysis</h3>
      ${options.map((row) => `<article class="evidence-card" style="margin-bottom:7px"><h4>${esc(row.option)}</h4><p><strong>Objective:</strong> ${esc(row.objective)}</p><p><strong>Benefit:</strong> ${esc(row.potential_benefit)}</p><p><strong>Cost:</strong> ${esc(row.potential_cost)}</p><div class="card-meta"><span>causal=${esc(row.causal_effect_estimate)}</span><span>reversibility=${esc(row.reversibility)}</span></div></article>`).join('')}
    </section>
    <section class="output-section">
      <h3>Counterfactual Analysis</h3>
      ${(cf.scenarios || []).map((row) => `<p><strong>${esc(row.counterfactual)}</strong><br>${esc(row.question)}<br>Outcome: ${esc(row.outcome_estimate)}</p>`).join('')}
      <strong>Required for causal comparison:</strong>${r8List(cf.required_for_causal_comparison)}
    </section>
    <section class="output-section">
      <h3>Distributional Incidence</h3>
      <p>Status: <strong>${esc(distribution.status || '—')}</strong></p>
      ${r8List(distribution.dimensions_to_analyze)}
      <p>${esc(distribution.claim_rule || '')}</p>
    </section>
    <section class="output-section">
      <h3>Implementation</h3>
      <p>Status: <strong>${esc(implementation.status || '—')}</strong></p>
      ${r8List(implementation.missing_inputs)}
    </section>`;
}

renderOutputInspector = function renderR8OutputInspector() {
  const run = appState.run;
  if (!run) return '<div class="empty">运行研究后，这里显示 S1 → R8 D1 → F1。</div>';
  const s1 = run.research_synthesis || {};
  const d1 = run.domain_brief || {};
  const f1 = run.forecast_pack || run.final_artifact || {};
  const sections = d1.sections || {};
  const score = f1.scoreboard || {};
  const scenario = f1.scenario_tracker?.current_state || '—';
  const isStreaming = run.ok == null;
  const outputState = isStreaming ? 'STREAMING' : (run.ok ? 'GROUNDED' : 'FAILED');
  const outputClass = isStreaming ? 'running' : (run.ok ? 'done' : 'fail');

  return `<div class="output-stage"><div><div class="kicker">R8 · ${esc((d1.domain || run.domain || 'decision').toUpperCase())}</div><strong>${esc(d1.professional_decision_status || scenario)}</strong></div><span class="pill ${outputClass}">${outputState}</span></div>
    <section class="output-section"><h3>Executive Summary</h3><p>${esc(sections.executive_summary || d1.answer || s1.answer || '等待 D1...')}</p></section>
    ${d1.domain === 'policy' ? renderPolicyDecision(sections) : renderInvestmentDecision(sections)}
    <section class="output-section"><h3>Grounding</h3><ul><li>S1 support: ${esc(s1.confidence)} · ${esc(s1.confidence_type)}</li><li>Evidence IDs unchanged: ${esc((d1.evidence_ids || []).join(', ') || '—')}</li><li>Decision framework: ${esc(d1.decision_framework_version || '—')}</li><li>F1 scenario: ${esc(scenario)}</li></ul></section>
    <section class="output-section"><h3>Forecast Scoreboard</h3><div class="metric-strip"><div class="metric"><span>OPEN</span><strong>${score.open || 0}</strong></div><div class="metric"><span>HIT</span><strong>${score.hits || 0}</strong></div><div class="metric"><span>MISS</span><strong>${score.misses || 0}</strong></div></div><p>${esc(score.accuracy_type || 'historical_direction_hit_rate_not_probability')}</p></section>`;
};

if (typeof renderInspector === 'function') renderInspector();
