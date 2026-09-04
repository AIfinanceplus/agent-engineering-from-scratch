/* R12 Step 9: replayed multi-trade portfolio and exposure limits. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r12_step7.css?v=r12-step9-v1';
  document.head.appendChild(link);
})();

r12Step2State.paperPortfolio = null;
r12Step2State.paperPortfolioEval = null;
r12Step2State.paperPortfolioUi = {busy:false, error:null};

const R12_STEP9_LIMIT_LABELS = {
  max_unsettled_trades:'Unsettled trades',
  max_unsettled_acquisition_cost:'Unsettled acquisition cost',
  max_total_leg_risk_quantity:'Total unmatched leg quantity',
  max_provider_filled_notional:'Per-provider filled notional',
  max_identity_acquisition_cost:'Per-identity acquisition cost',
};

function r12Step9LimitUsage(portfolio, name) {
  const summary = portfolio.summary || {};
  if (name === 'max_unsettled_trades') return summary.unsettled_trade_count || 0;
  if (name === 'max_unsettled_acquisition_cost') return summary.unsettled_acquisition_cost || 0;
  if (name === 'max_total_leg_risk_quantity') return summary.total_leg_risk_quantity || 0;
  if (name === 'max_provider_filled_notional') return Math.max(0, ...Object.values(portfolio.by_provider || {}).map((row) => Number(row.filled_notional || 0)));
  if (name === 'max_identity_acquisition_cost') return Math.max(0, ...Object.values(portfolio.by_identity || {}).map((row) => Number(row.acquisition_cost || 0)));
  return 0;
}

function r12Step9PortfolioPanel() {
  const portfolio = r12Step2State.paperPortfolio;
  const ui = r12Step2State.paperPortfolioUi;
  if (!portfolio) return `<section class="strategy-section r12-portfolio-panel">
    <div class="strategy-section-head"><div><div class="kicker">R12 · STEP 9 · PAPER PORTFOLIO RISK</div><h3>Multi-trade Portfolio</h3><p>从所有 append-only trade ledgers 重建组合；每个新 intent / fill 都先通过原子化限额检查。</p></div><button type="button" id="r12-portfolio-refresh" class="btn" ${ui.busy ? 'disabled' : ''}>${ui.busy ? 'Loading…' : 'Load Portfolio'}</button></div>
    ${ui.error ? `<div class="eval-diagnostic">${esc(ui.error)}</div>` : '<div class="strategy-scan-empty">正在加载 paper portfolio。</div>'}
  </section>`;
  const summary = portfolio.summary || {};
  const limits = portfolio.limits || {};
  const violations = portfolio.violations || [];
  return `<section class="strategy-section r12-portfolio-panel">
    <div class="strategy-section-head"><div><div class="kicker">R12 · STEP 9 · PAPER PORTFOLIO RISK</div><h3>Multi-trade Portfolio &amp; Exposure Limits</h3><p>组合只读取并回放单笔 ledger。Preflight 不写事件；只有通过限额的显式模拟 fill 才能进入原 ledger。</p></div><div class="r12-portfolio-head-actions"><span class="pill ${portfolio.risk_status === 'WITHIN_LIMITS' ? 'done' : 'fail'}">${esc(portfolio.risk_status)}</span><button type="button" id="r12-portfolio-refresh" class="btn" ${ui.busy ? 'disabled' : ''}>${ui.busy ? 'Refreshing…' : 'Refresh'}</button></div></div>
    ${ui.error ? `<div class="eval-diagnostic">${esc(ui.error)}</div>` : ''}
    <div class="strategy-summary r12-portfolio-summary">
      <div><span>Trades</span><strong>${esc(summary.trade_count)}</strong></div>
      <div><span>Unsettled</span><strong>${esc(summary.unsettled_trade_count)}</strong></div>
      <div><span>Acquisition</span><strong>${esc(summary.unsettled_acquisition_cost)}</strong></div>
      <div><span>Leg risk</span><strong>${esc(summary.total_leg_risk_quantity)}</strong></div>
      <div><span>MTM P&amp;L</span><strong>${esc(summary.mark_to_market_pnl ?? 'INCOMPLETE MARKS')}</strong></div>
      <div><span>Realized P&amp;L</span><strong>${esc(summary.realized_pnl)}</strong></div>
    </div>
    ${violations.length ? `<div class="eval-diagnostic"><strong>Blocking limits:</strong> ${esc(violations.map((row) => `${row.limit}${row.scope ? `[${row.scope}]` : ''}`).join(', '))}</div>` : ''}
    <details class="r12-portfolio-details" ${violations.length ? 'open' : ''}><summary>Limits, trades, provider / identity concentration</summary>
      <div class="r12-limit-grid">${Object.entries(limits).map(([name,maximum]) => {
        const used = r12Step9LimitUsage(portfolio, name);
        const breached = violations.some((row) => row.limit === name);
        return `<article class="r12-limit-card ${breached ? 'breached' : ''}"><span>${esc(R12_STEP9_LIMIT_LABELS[name] || name)}</span><strong>${esc(used)} / ${esc(maximum)}</strong><small>${breached ? 'BLOCKING NEW RISK' : 'within limit'}</small></article>`;
      }).join('')}</div>
      <div class="r12-portfolio-trades">${(portfolio.trades || []).map((trade) => `<article><div><strong>${esc(trade.paper_trade_id)}</strong><span>${esc(trade.identity_id || 'identity —')}</span></div><span class="pill ${trade.status === 'SETTLED' ? 'done' : trade.leg_risk_quantity > 0 ? 'fail' : ''}">${esc(trade.status)}</span><span>cost ${esc(trade.acquisition_cost)}</span><span>matched ${esc(trade.matched_quantity)}</span><span>leg risk ${esc(trade.leg_risk_quantity)}</span><span>MTM ${esc(trade.mark_to_market_pnl ?? '—')}</span></article>`).join('') || '<div class="strategy-scan-empty">No paper trade ledgers yet.</div>'}</div>
      <details><summary>Raw portfolio projection / Eval</summary><pre class="codebox">${esc(pretty({portfolio, eval:r12Step2State.paperPortfolioEval}))}</pre></details>
    </details>
    <div class="paper-only">REPLAYED_LEDGER_SOURCE · ATOMIC_PREFLIGHT · EXPLICIT_LIMITS · NO_AUTO_EXECUTION</div>
  </section>`;
}

const r12Step9BasePaperPanel = r12Step7PaperPanel;
r12Step7PaperPanel = function r12Step9PortfolioAndTradePanels() {
  return `${r12Step9PortfolioPanel()}${r12Step9BasePaperPanel()}`;
};

const r12Step9BaseHydratePaper = r12Step7Hydrate;
r12Step7Hydrate = function r12Step9HydratePaper(payload, kind) {
  r12Step9BaseHydratePaper(payload, kind);
  if (payload.portfolio) r12Step2State.paperPortfolio = payload.portfolio;
  if (payload.portfolio_eval) r12Step2State.paperPortfolioEval = payload.portfolio_eval;
};

async function r12Step9LoadPortfolio() {
  try {
    r12Step2State.paperPortfolioUi.busy = true;
    r12Step2State.paperPortfolioUi.error = null;
    const payload = await r12Step6Post('/api/r12/paper/portfolio', {});
    r12Step2State.paperPortfolio = payload.portfolio;
    r12Step2State.paperPortfolioEval = payload.eval;
  } catch (error) {
    r12Step2State.paperPortfolioUi.error = error.message;
  } finally {
    r12Step2State.paperPortfolioUi.busy = false;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

document.addEventListener('click', (event) => {
  if (!event.target?.closest?.('#r12-portfolio-refresh')) return;
  event.preventDefault();
  r12Step9LoadPortfolio();
});

renderAll();
r12Step9LoadPortfolio();
