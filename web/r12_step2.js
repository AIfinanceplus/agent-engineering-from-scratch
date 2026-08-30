/* R12 live path: exact contracts -> rules analysis -> identity -> depth-aware paper quote. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r12_step2.css?v=r12-step5-v1';
  document.head.appendChild(link);
})();

const R12_IDENTITY_CHECKS = [
  ['same_event_meaning', 'Same event meaning'],
  ['same_yes_outcome', 'Same YES outcome semantics'],
  ['same_measurement_definition', 'Same measurement / threshold definition'],
  ['compatible_resolution_source', 'Compatible resolution source'],
  ['compatible_resolution_horizon', 'Compatible resolution / time horizon'],
  ['edge_cases_reviewed', 'Edge cases / cancellation rules reviewed'],
];

const r12Step2State = {
  kalshi: null,
  polymarket: null,
  rulesAnalysis: null,
  identity: null,
  rv: null,
  execution: null,
  loading: null,
  error: null,
};

function r12Step2ContractCard(provider, contract) {
  if (!contract) return `<article class="live-contract-card"><div class="kicker">${esc(provider.toUpperCase())}</div><div class="empty">Not loaded.</div></article>`;
  const q = contract.quotes || {};
  const r = contract.resolution || {};
  const t = contract.time_contract || {};
  return `<article class="live-contract-card">
    <div class="live-contract-head"><div><div class="kicker">${esc(provider.toUpperCase())}</div><strong>${esc(contract.provider_market_id)}</strong></div><span class="pill ${q.quote_status?.startsWith('EXECUTABLE') ? 'done' : ''}">${esc(q.quote_status || '—')}</span></div>
    <h4>${esc(contract.question || '—')}</h4>
    <div class="live-quote-grid"><div><span>YES bid/ask</span><strong>${esc(q.yes_bid ?? '—')} / ${esc(q.yes_ask ?? '—')}</strong></div><div><span>NO bid/ask</span><strong>${esc(q.no_bid ?? '—')} / ${esc(q.no_ask ?? '—')}</strong></div></div>
    <p><strong>Time:</strong> ${esc(t.close_time || t.end_time || t.expiration_time || '—')}</p>
    <details><summary>Resolution / rules</summary><pre class="codebox">${esc(pretty(r))}</pre></details>
    <details><summary>Normalized contract</summary><pre class="codebox">${esc(pretty(contract))}</pre></details>
    <div class="paper-only">${esc(contract.execution_status)}</div>
  </article>`;
}

function r12Step2RulesPanel() {
  const both = r12Step2State.kalshi && r12Step2State.polymarket;
  const analysis = r12Step2State.rulesAnalysis;
  return `<section class="live-identity-panel rules-analysis-panel">
    <div class="strategy-section-head"><div><h3>2 · Deterministic Settlement Rules Analysis</h3><p>机器只提取 rules、resolution authority、time、measurement 和 edge cases。报告与当前合同 fingerprint 绑定，不会替你勾选 identity。</p></div><span class="pill ${analysis?.eligible_for_identity_review ? 'done' : 'fail'}">${esc(analysis?.status || 'NOT_RUN')}</span></div>
    <button id="r12-analyze-rules" class="btn primary" ${both ? '' : 'disabled'}>Analyze Current Settlement Rules</button>
    ${analysis ? r12Step2RenderRulesAnalysis(analysis) : '<div class="strategy-scan-empty">Load both exact contracts, then analyze their current rules.</div>'}
  </section>`;
}

function r12Step2RenderRulesAnalysis(analysis) {
  return `<div class="rules-analysis-result">
    <div class="strategy-summary"><div><span>Analysis</span><strong>${esc(analysis.analysis_id)}</strong></div><div><span>Differences</span><strong>${esc(analysis.difference_count)}</strong></div><div><span>Blocking</span><strong>${esc(analysis.blocking_findings?.length || 0)}</strong></div><div><span>Auto approve</span><strong>FALSE</strong></div></div>
    <div class="rules-check-list">${(analysis.comparison_checks || []).map((row) => `<div class="rules-check-row"><strong>${esc(row.check)}</strong><span>${esc(row.status)}</span><span>can approve identity: ${esc(row.can_approve_identity)}</span></div>`).join('')}</div>
    ${(analysis.blocking_findings || []).length ? `<div class="eval-diagnostic"><strong>Blocking:</strong> ${esc(analysis.blocking_findings.join(', '))}</div>` : ''}
    <details><summary>Extracted rules and comparison evidence</summary><pre class="codebox">${esc(pretty(analysis))}</pre></details>
    <div class="paper-only">HUMAN_REVIEW_REQUIRED · PARSER_NEVER_AUTO_ATTESTS</div>
  </div>`;
}

function r12Step2IdentityPanel() {
  const both = r12Step2State.kalshi && r12Step2State.polymarket;
  const rulesReady = Boolean(r12Step2State.rulesAnalysis?.eligible_for_identity_review);
  const identity = r12Step2State.identity;
  return `<section class="live-identity-panel">
    <div class="strategy-section-head"><div><h3>3 · Human Event Identity / Settlement Review</h3><p>Parser 没发现 blocker 也不等于相同事件。请阅读报告后逐项人工确认；所有 checkbox 默认保持未勾选。</p></div><span class="pill ${identity?.settlement_compatible_for_rv ? 'done' : 'fail'}">${esc(identity?.status || 'UNVERIFIED')}</span></div>
    <div class="identity-check-grid">${R12_IDENTITY_CHECKS.map(([key,label]) => `<label><input type="checkbox" data-r12-identity="${esc(key)}"> <span>${esc(label)}</span></label>`).join('')}</div>
    <label class="identity-source">Review / attestation source<input id="r12-attestation-source" value="human_rules_review" placeholder="human_rules_review / independent_rules_parser"></label>
    <button id="r12-validate-identity" class="btn primary" ${both && rulesReady ? '' : 'disabled'}>Validate Settlement Identity</button>
    ${identity ? `<details open><summary>Identity Contract</summary><pre class="codebox">${esc(pretty(identity))}</pre></details>` : ''}
  </section>`;
}

function r12Step2RVPanel() {
  const identity = r12Step2State.identity;
  const allowed = Boolean(identity?.settlement_compatible_for_rv);
  const scan = r12Step2State.rv;
  return `<section class="live-rv-panel">
    <div class="strategy-section-head"><div><h3>4 · Same-event Cross-market RV</h3><p>先用 top-of-book 检查是否存在值得继续报价的方向。两条腿结算一致时，每个完整 basket 到期总 payoff=1。</p></div><span class="pill">PRELIMINARY TOP-OF-BOOK</span></div>
    <div class="rv-cost-row"><label>Estimated total cost / basket<input id="r12-rv-cost" value="0" placeholder="probability-price points, e.g. 0.01"></label><button id="r12-run-cross-rv" class="btn primary" ${allowed ? '' : 'disabled'}>Compare Verified Cross-market RV</button></div>
    <p class="muted">这里的正 edge 只是 preliminary screen。必须通过下一步完整 depth、explicit fee 和 target-fill gate，才能成为 depth-aware paper signal。</p>
    ${scan ? r12Step2RenderRV(scan) : '<div class="strategy-scan-empty">Identity 通过后才能运行。</div>'}
  </section>`;
}

function r12Step2RenderRV(scan) {
  const opportunities = scan.opportunities || [];
  return `<div class="live-rv-result">
    <div class="strategy-summary"><div><span>Baskets</span><strong>${esc(scan.baskets_checked?.length || 0)}</strong></div><div><span>Positive</span><strong>${esc(scan.opportunity_count)}</strong></div><div><span>Paper signals</span><strong>${esc(scan.paper_signal_count)}</strong></div><div><span>Quotes</span><strong>${esc(scan.quote_mode)}</strong></div></div>
    <div class="basket-list">${(scan.baskets_checked || []).map((row) => `<div class="basket-row"><strong>${esc(row.name)}</strong><span>gross cost ${esc(row.gross_cost ?? '—')}</span><span>gross edge ${esc(row.gross_edge ?? '—')}</span><span>net ${esc(row.net_edge ?? '—')}</span><span>${esc(row.status)}</span></div>`).join('')}</div>
    ${opportunities.map(r12RenderOpportunity).join('') || '<div class="empty">No positive locked complement margin after costs.</div>'}
    <details><summary>Raw Cross-market RV JSON</summary><pre class="codebox">${esc(pretty(scan))}</pre></details>
  </div>`;
}

function r12Step2ExecutionPanel() {
  const allowed = Boolean(r12Step2State.identity?.settlement_compatible_for_rv);
  const quote = r12Step2State.execution;
  return `<section class="live-rv-panel execution-quote-panel">
    <div class="strategy-section-head"><div><h3>5 · Depth-aware Paper Execution Quote</h3><p>对两条腿逐级 walk asks；只有目标数量在两边都能完整成交，并扣除明确费用与 latency buffer 后仍有正 edge，才产生 paper signal。</p></div><span class="pill">PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION</span></div>
    <div class="execution-input-grid">
      <label>Target contracts<input id="r12-exec-target" value="10"></label>
      <label>Fee model source<input id="r12-fee-source" value="manual_provider_schedule_review"></label>
      <label>Latency buffer (bps / leg)<input id="r12-latency-bps" value="0"></label>
      <label>Kalshi fee / notional<input id="r12-k-fee-rate" value="0"></label>
      <label>Kalshi fee / contract<input id="r12-k-fee-contract" value="0"></label>
      <label>Kalshi fixed / order<input id="r12-k-fee-fixed" value="0"></label>
      <label>Polymarket fee / notional<input id="r12-p-fee-rate" value="0"></label>
      <label>Polymarket fee / contract<input id="r12-p-fee-contract" value="0"></label>
      <label>Polymarket fixed / order<input id="r12-p-fee-fixed" value="0"></label>
    </div>
    <button id="r12-run-execution-quote" class="btn primary" ${allowed ? '' : 'disabled'}>Quote Target Against Full Visible Depth</button>
    <p class="muted">费用必须显式输入；零费率也代表你明确核对后的输入，不是系统猜测。Latency buffer 是用户给定的保守缓冲，并非校准后的成交延迟模型。</p>
    ${quote ? r12Step2RenderExecution(quote) : '<div class="strategy-scan-empty">等待 settlement identity 通过并生成目标报价。</div>'}
  </section>`;
}

function r12Step2RenderExecution(quote) {
  return `<div class="live-rv-result">
    <div class="strategy-summary"><div><span>Target</span><strong>${esc(quote.target_contracts)}</strong></div><div><span>Fee model</span><strong>${esc(quote.fee_model_status)}</strong></div><div><span>Paper signals</span><strong>${esc(quote.paper_signal_count)}</strong></div><div><span>Policy</span><strong>${esc(quote.execution_policy)}</strong></div></div>
    <div class="execution-basket-list">${(quote.baskets_checked || []).map((basket) => `<article class="execution-basket"><div class="live-contract-head"><strong>${esc(basket.name)}</strong><span class="pill ${basket.eligible_for_paper_signal ? 'done' : 'fail'}">${esc(basket.status)}</span></div><div class="execution-metrics"><span>max complete ${esc(basket.max_complete_quantity_from_current_depth)}</span><span>gross ${esc(basket.gross_edge_total ?? '—')}</span><span>fees ${esc(basket.fee_total ?? '—')}</span><span>latency ${esc(basket.latency_buffer_cost_total ?? '—')}</span><span>net ${esc(basket.net_edge_total ?? '—')}</span></div>${(basket.legs || []).map((leg) => `<div class="execution-leg"><strong>${esc(leg.provider)} ${esc(leg.outcome)}</strong><span>filled ${esc(leg.filled_quantity)} / ${esc(leg.requested_quantity)}</span><span>VWAP ${esc(leg.vwap ?? '—')}</span><span>worst ${esc(leg.worst_ask ?? '—')}</span><span>slippage ${esc(leg.slippage_vs_best_ask ?? '—')}</span></div>`).join('')}</article>`).join('')}</div>
    ${(quote.opportunities || []).map(r12RenderOpportunity).join('') || '<div class="empty">No target-sized paper signal after depth, explicit fees, and latency buffer.</div>'}
    <details><summary>Raw execution quote JSON</summary><pre class="codebox">${esc(pretty(quote))}</pre></details>
  </div>`;
}

function r12Step2Inspector() {
  return `<section class="strategy-section live-contract-inspector">
    <div class="kicker">R12 · STEP 2 · LIVE PUBLIC MARKET DATA</div>
    <h3>Live Contract Inspector</h3>
    <p>输入<strong>精确市场 ID</strong>。Adapter 只取 public market metadata / orderbook，不使用交易凭证；Event Identity 由下一层单独审核。</p>
    <div class="live-contract-inputs">
      <label>Kalshi market ticker<input id="r12-kalshi-id" placeholder="exact market ticker"></label><button id="r12-load-kalshi" class="btn">Load Kalshi Contract</button>
      <label>Polymarket market ID<input id="r12-poly-id" placeholder="exact Gamma market ID"></label><button id="r12-load-poly" class="btn">Load Polymarket Contract</button>
    </div>
    ${r12Step2State.error ? `<div class="eval-diagnostic"><strong>Live adapter:</strong> ${esc(r12Step2State.error)}</div>` : ''}
    <div class="live-contract-grid">${r12Step2ContractCard('kalshi', r12Step2State.kalshi)}${r12Step2ContractCard('polymarket', r12Step2State.polymarket)}</div>
    ${r12Step2RulesPanel()}
    ${r12Step2IdentityPanel()}
    ${r12Step2RVPanel()}
    ${r12Step2ExecutionPanel()}
  </section>`;
}

const r12Step2BaseCenter = renderR12StrategyCenter;
renderR12StrategyCenter = function renderR12Step2StrategyCenter() {
  return `${r12Step2BaseCenter()}${r12Step2Inspector()}`;
};

async function r12Step2LoadContract(provider) {
  try {
    const selector = provider === 'kalshi' ? '#r12-kalshi-id' : '#r12-poly-id';
    const identifier = document.querySelector(selector)?.value?.trim();
    if (!identifier) throw new Error(`${provider} exact identifier is required`);
    r12Step2State.loading = provider;
    r12Step2State.error = null;
    const response = await fetch('/api/r12/market-contract', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify({provider, identifier}),
    });
    const raw = await response.text();
    let payload;
    try { payload = JSON.parse(raw); }
    catch (_) { throw new Error(`Market adapter returned non-JSON (HTTP ${response.status})`); }
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
    r12Step2State[provider] = payload.contract;
    r12Step2State.rulesAnalysis = null;
    r12Step2State.identity = null;
    r12Step2State.rv = null;
    r12Step2State.execution = null;
    toast(`${provider} contract loaded`);
  } catch (error) {
    r12Step2State.error = error.message;
    toast(`Live Contract: ${error.message}`);
  } finally {
    r12Step2State.loading = null;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step2AnalyzeRules() {
  try {
    if (!r12Step2State.kalshi || !r12Step2State.polymarket) throw new Error('Load both market contracts first');
    const response = await fetch('/api/r12/rules-analysis', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify({kalshi_contract:r12Step2State.kalshi, polymarket_contract:r12Step2State.polymarket}),
    });
    const raw = await response.text();
    const payload = JSON.parse(raw);
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
    r12Step2State.rulesAnalysis = payload.analysis;
    r12Step2State.identity = null;
    r12Step2State.rv = null;
    r12Step2State.execution = null;
    toast(`Rules analysis: ${payload.analysis.status}`);
  } catch (error) {
    r12Step2State.error = error.message;
    toast(`Rules analysis: ${error.message}`);
  } finally {
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step2ValidateIdentity() {
  try {
    if (!r12Step2State.kalshi || !r12Step2State.polymarket) throw new Error('Load both market contracts first');
    if (!r12Step2State.rulesAnalysis?.eligible_for_identity_review) throw new Error('Current rules analysis must be ready first');
    const attestation = {attestation_source: document.querySelector('#r12-attestation-source')?.value?.trim()};
    document.querySelectorAll('[data-r12-identity]').forEach((input) => {
      attestation[input.dataset.r12Identity] = Boolean(input.checked);
    });
    const response = await fetch('/api/r12/identity', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify({kalshi_contract:r12Step2State.kalshi, polymarket_contract:r12Step2State.polymarket, rules_analysis:r12Step2State.rulesAnalysis, attestation}),
    });
    const raw = await response.text();
    const payload = JSON.parse(raw);
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
    r12Step2State.identity = payload.identity;
    r12Step2State.rv = null;
    r12Step2State.execution = null;
    toast(`Identity: ${payload.identity.status}`);
  } catch (error) {
    r12Step2State.error = error.message;
    toast(`Identity: ${error.message}`);
  } finally {
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

function r12Step2FiniteNonNegative(selector, label) {
  const value = Number(document.querySelector(selector)?.value?.trim());
  if (!Number.isFinite(value) || value < 0) throw new Error(`${label} must be finite and non-negative`);
  return value;
}

async function r12Step2RunExecutionQuote() {
  try {
    if (!r12Step2State.identity?.settlement_compatible_for_rv) throw new Error('Settlement identity must be verified first');
    const target = r12Step2FiniteNonNegative('#r12-exec-target', 'Target contracts');
    if (target <= 0) throw new Error('Target contracts must be greater than zero');
    const source = document.querySelector('#r12-fee-source')?.value?.trim();
    if (!source) throw new Error('Explicit fee model source is required');
    const feeModel = {
      source,
      kalshi: {
        fee_rate_on_notional: r12Step2FiniteNonNegative('#r12-k-fee-rate', 'Kalshi notional fee'),
        fee_per_contract: r12Step2FiniteNonNegative('#r12-k-fee-contract', 'Kalshi contract fee'),
        fixed_fee_per_order: r12Step2FiniteNonNegative('#r12-k-fee-fixed', 'Kalshi fixed fee'),
      },
      polymarket: {
        fee_rate_on_notional: r12Step2FiniteNonNegative('#r12-p-fee-rate', 'Polymarket notional fee'),
        fee_per_contract: r12Step2FiniteNonNegative('#r12-p-fee-contract', 'Polymarket contract fee'),
        fixed_fee_per_order: r12Step2FiniteNonNegative('#r12-p-fee-fixed', 'Polymarket fixed fee'),
      },
    };
    const response = await fetch('/api/r12/execution-quote', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify({identity:r12Step2State.identity, kalshi_contract:r12Step2State.kalshi, polymarket_contract:r12Step2State.polymarket, target_contracts:target, fee_model:feeModel, latency_buffer_bps:r12Step2FiniteNonNegative('#r12-latency-bps', 'Latency buffer')}),
    });
    const raw = await response.text();
    const payload = JSON.parse(raw);
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
    r12Step2State.execution = payload.quote;
    toast(`Execution quote: ${payload.quote.paper_signal_count} depth-aware paper signal(s)`);
  } catch (error) {
    r12Step2State.error = error.message;
    toast(`Execution quote: ${error.message}`);
  } finally {
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step2RunRV() {
  try {
    if (!r12Step2State.identity?.settlement_compatible_for_rv) throw new Error('Settlement identity must be verified first');
    const rawCost = document.querySelector('#r12-rv-cost')?.value?.trim() || '0';
    const cost = Number(rawCost);
    if (!Number.isFinite(cost) || cost < 0) throw new Error('Estimated basket cost must be non-negative');
    const response = await fetch('/api/r12/cross-market-rv', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify({identity:r12Step2State.identity, kalshi_contract:r12Step2State.kalshi, polymarket_contract:r12Step2State.polymarket, estimated_total_cost_per_basket:cost}),
    });
    const raw = await response.text();
    const payload = JSON.parse(raw);
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
    r12Step2State.rv = payload.scan;
    toast(`Cross-market RV: ${payload.scan.paper_signal_count} paper signal(s)`);
  } catch (error) {
    r12Step2State.error = error.message;
    toast(`Cross-market RV: ${error.message}`);
  } finally {
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

document.addEventListener('click', (event) => {
  if (event.target?.id === 'r12-load-kalshi') r12Step2LoadContract('kalshi');
  if (event.target?.id === 'r12-load-poly') r12Step2LoadContract('polymarket');
  if (event.target?.id === 'r12-analyze-rules') r12Step2AnalyzeRules();
  if (event.target?.id === 'r12-validate-identity') r12Step2ValidateIdentity();
  if (event.target?.id === 'r12-run-cross-rv') r12Step2RunRV();
  if (event.target?.id === 'r12-run-execution-quote') r12Step2RunExecutionQuote();
});

renderAll();
