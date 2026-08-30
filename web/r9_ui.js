/* R9 observed Market Context UI extension. Loaded only by serve_r9.py. */

const r9BaseInvestmentDecision = renderInvestmentDecision;

function r9MarketLevel(label, row) {
  if (!row) return `<div class="metric"><span>${esc(label)}</span><strong>—</strong></div>`;
  return `<div class="metric"><span>${esc(label)}</span><strong>${esc(row.value)}%</strong><small>${esc(row.as_of || '—')}</small></div>`;
}

function renderR9MarketContext() {
  const market = appState.run?.results?.M6 || {};
  if (!market.artifact_type) {
    return `<section class="output-section"><h3>R9 · Market Context</h3><p>等待 M1–M6；Policy 模式不会运行这条 Investment-only lane。</p></section>`;
  }
  const levels = market.market_levels || {};
  const derived = market.derived_observations || {};
  const semantics = market.semantics || {};
  return `
    <section class="output-section">
      <h3>R9 · Observed Market Context</h3>
      <p>${esc(market.answer || '')}</p>
      <div class="metric-strip">
        ${r9MarketLevel('EFFR', levels.effective_fed_funds_rate)}
        ${r9MarketLevel('2Y', levels.treasury_2y)}
        ${r9MarketLevel('10Y', levels.treasury_10y)}
        ${r9MarketLevel('10Y Real', levels.real_yield_10y)}
        ${r9MarketLevel('10Y BE', levels.breakeven_10y)}
      </div>
    </section>
    <section class="output-section">
      <h3>Synchronized Derived Observations</h3>
      <ul>
        <li><strong>10Y − 2Y:</strong> ${esc(derived.term_spread_10y_minus_2y)} pp · ${esc(derived.curve_shape || '—')} · as of ${esc(derived.term_spread_as_of || '—')}</li>
        <li><strong>10Y nominal − real:</strong> ${esc(derived.nominal_minus_real_10y_spread)} pp · as of ${esc(derived.nominal_real_breakeven_as_of || '—')}</li>
        <li><strong>Breakeven cross-check gap:</strong> ${esc(derived.breakeven_crosscheck_gap)} pp</li>
      </ul>
    </section>
    <section class="output-section">
      <h3>R9 Boundary</h3>
      <ul>
        <li>Fed path: ${esc(semantics.fed_path || '—')}</li>
        <li>Market-implied macro view: ${esc(semantics.market_implied_macro_view || '—')}</li>
        <li>Mispricing: ${esc(semantics.mispricing || '—')}</li>
        <li>Expected value: ${esc(semantics.expected_value || '—')}</li>
        <li>Position: ${esc(semantics.position || '—')}</li>
      </ul>
      <p><strong>Research Evidence ≠ Market Evidence.</strong> R10 才允许把 S1 Research View 与 Market Implied View 做显式比较。</p>
    </section>`;
}

renderInvestmentDecision = function renderR9InvestmentDecision(sections) {
  return `${renderR9MarketContext()}${r9BaseInvestmentDecision(sections)}`;
};

NODE_META.D1 = {
  ...NODE_META.D1,
  code: 'r8_decision.py + r9_market.py',
  why: 'R9 保留 R8 的专业 Investment D1，同时增加独立 Market Context lane。M1–M6 不进入 S1，也不在 R9 计算 mispricing / EV / position。',
};

if (typeof renderInspector === 'function') renderInspector();
