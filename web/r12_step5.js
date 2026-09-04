/* R12 Step 7: append-only paper fills, leg risk, replay, and paper P&L. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r12_step5.css?v=r12-step7-v1';
  document.head.appendChild(link);
})();

r12Step2State.paperTrade = null;
r12Step2State.paperEval = null;
r12Step2State.paperUi = {busy:null, message:'E1 完成后可创建模拟成交意图。', error:null, pendingCommands:{}};

function r12Step7Opportunities() {
  return r12Step2State.agentRun?.results?.E1?.opportunities || [];
}

function r12Step7Terminal(trade) {
  const status = trade?.status || '';
  return status === 'SETTLED' || status.startsWith('CANCELLED_') || status.startsWith('EXPIRED_');
}

function r12Step7PaperPanel() {
  const trade = r12Step2State.paperTrade;
  const ui = r12Step2State.paperUi;
  const opportunities = r12Step7Opportunities();
  const canCreate = r12Step2State.agentRun?.status === 'COMPLETED_PAPER_QUOTE' && opportunities.length > 0;
  const terminal = r12Step7Terminal(trade);
  const risk = trade?.risk || {};
  const pnl = trade?.pnl || {};
  return `<section class="strategy-section r12-paper-panel">
    <div class="kicker">R12 · STEP 7 · APPEND-ONLY PAPER EXECUTION LEDGER</div>
    <div class="strategy-section-head"><div><h3>Paper Intent · Explicit Fills · Replay · P&amp;L</h3><p>E1 只是报价，不是成交。这里的每个 fill 都是显式模拟命令，并通过 idempotency key 写入可回放事件日志。</p></div><span class="pill ${trade?.status === 'FULLY_MATCHED' || trade?.status === 'SETTLED' ? 'done' : trade?.status?.includes('LEG_RISK') ? 'fail' : ''}">${esc(trade?.status || 'NO_PAPER_TRADE')}</span></div>
    <div class="r12-paper-actions">
      <label>E1 opportunity<select id="r12-paper-opportunity">${opportunities.map((row) => `<option value="${esc(row.opportunity_id)}">${esc(row.opportunity_id)} · ${esc(row.market_view?.execution_quote?.name)}</option>`).join('') || '<option value="">No eligible E1 opportunity</option>'}</select></label>
      <button type="button" id="r12-paper-create" class="btn primary" ${canCreate && !ui.busy ? '' : 'disabled'}>${ui.busy === 'create' ? 'Creating…' : 'Create Paper Intent'}</button>
      <label>Paper trade ID<input id="r12-paper-trade-id" value="${esc(trade?.paper_trade_id || '')}" placeholder="R12P-..."></label>
      <button type="button" id="r12-paper-load" class="btn" ${ui.busy ? 'disabled' : ''}>${ui.busy === 'load' ? 'Loading…' : 'Load Ledger'}</button>
    </div>
    <div class="r12-paper-feedback ${ui.error ? 'eval-diagnostic' : ''}" role="status" aria-live="polite">${esc(ui.error || ui.message)}</div>
    ${trade ? `<div class="strategy-summary r12-paper-summary">
      <div><span>Events</span><strong>${esc(trade.event_count)}</strong></div>
      <div><span>Matched</span><strong>${esc(risk.matched_quantity)} / ${esc(trade.target_quantity)}</strong></div>
      <div><span>Leg risk</span><strong>${esc(risk.leg_risk_quantity)}</strong></div>
      <div><span>MTM P&amp;L</span><strong>${esc(pnl.mark_to_market_pnl ?? '—')}</strong></div>
      <div><span>Realized P&amp;L</span><strong>${esc(pnl.realized_pnl ?? '—')}</strong></div>
    </div>
    <div class="r12-paper-leg-grid">${(trade.legs || []).map((leg) => r12Step7LegCard(leg, terminal)).join('')}</div>
    <div class="r12-paper-command-row">
      <button type="button" id="r12-paper-mark" class="btn" ${trade.status === 'SETTLED' || ui.busy ? 'disabled' : ''}>Update MTM</button>
      <button type="button" id="r12-paper-cancel" class="btn" ${terminal || risk.fully_matched_target || ui.busy ? 'disabled' : ''}>Cancel Remaining</button>
      <button type="button" id="r12-paper-expire" class="btn" ${terminal || risk.fully_matched_target || ui.busy ? 'disabled' : ''}>Expire Remaining</button>
      <button type="button" class="btn r12-paper-settle" data-winner="YES" ${trade.status === 'SETTLED' || ui.busy ? 'disabled' : ''}>Settle YES</button>
      <button type="button" class="btn r12-paper-settle" data-winner="NO" ${trade.status === 'SETTLED' || ui.busy ? 'disabled' : ''}>Settle NO</button>
    </div>
    <details><summary>Append-only ledger / replay / Eval</summary><pre class="codebox">${esc(pretty({trade, eval:r12Step2State.paperEval}))}</pre></details>` : '<div class="strategy-scan-empty">等待 COMPLETED_PAPER_QUOTE；创建 intent 后仍然是 0 fills。</div>'}
    <div class="paper-only">SIMULATED_FILLS_ONLY · IDEMPOTENT_COMMANDS · APPEND_ONLY · NO_EXCHANGE_CONNECTION</div>
  </section>`;
}

function r12Step7LegCard(leg, terminal) {
  const safeId = leg.leg_id.replace(/[^a-zA-Z0-9_-]/g, '-');
  return `<article class="r12-paper-leg" data-leg-id="${esc(leg.leg_id)}">
    <div class="live-contract-head"><strong>${esc(leg.provider.toUpperCase())} ${esc(leg.outcome)}</strong><span>${esc(leg.filled_quantity)} / ${esc(leg.target_quantity)}</span></div>
    <div class="execution-metrics"><span>quoted ${esc(leg.quoted_vwap)}</span><span>avg ${esc(leg.average_fill_price ?? '—')}</span><span>fees ${esc(leg.fees)}</span><span>mark ${esc(leg.mark ?? '—')}</span></div>
    <div class="r12-paper-fill-row">
      <label>Fill qty<input id="r12-fill-qty-${safeId}" data-paper-field="quantity" value="${esc(leg.remaining_quantity)}"></label>
      <label>Fill price<input id="r12-fill-price-${safeId}" data-paper-field="price" value="${esc(leg.quoted_vwap)}"></label>
      <label>Fee<input id="r12-fill-fee-${safeId}" data-paper-field="fee" value="0"></label>
      <button type="button" class="btn primary r12-paper-fill" ${terminal || leg.remaining_quantity <= 0 || r12Step2State.paperUi.busy ? 'disabled' : ''}>Record Fill</button>
    </div>
    <label class="r12-paper-mark-field">Current mark<input id="r12-mark-${safeId}" data-paper-field="mark" value="${esc(leg.mark ?? leg.quoted_vwap)}"></label>
  </article>`;
}

const r12Step7BaseRunPanel = r12Step6RunPanel;
r12Step6RunPanel = function r12Step7RunAndLedgerPanels() {
  return `${r12Step7BaseRunPanel()}${r12Step7PaperPanel()}`;
};

const r12Step7BaseHydrateAgent = r12Step6Hydrate;
r12Step6Hydrate = function r12Step7HydrateAgent(payload) {
  const previousRunId = r12Step2State.agentRun?.run_id;
  r12Step7BaseHydrateAgent(payload);
  if (previousRunId && previousRunId !== payload.run?.run_id) {
    r12Step2State.paperTrade = null;
    r12Step2State.paperEval = null;
  }
};

function r12Step7CommandKey(kind, payload) {
  const signature = JSON.stringify(payload);
  const existing = r12Step2State.paperUi.pendingCommands[kind];
  if (existing?.signature === signature) return existing.key;
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const command = {signature, key:`r12-${kind}-${random}`};
  r12Step2State.paperUi.pendingCommands[kind] = command;
  return command.key;
}

function r12Step7Hydrate(payload, kind) {
  r12Step2State.paperTrade = payload.trade;
  r12Step2State.paperEval = payload.eval;
  r12Step2State.paperUi.pendingCommands[kind] = null;
  r12Step2State.paperUi.message = `${payload.action}: ${payload.trade.status}`;
  r12Step2State.paperUi.error = null;
}

function r12Step7SetBusy(kind, message) {
  r12Step2State.paperUi.busy = kind;
  r12Step2State.paperUi.message = message;
  r12Step2State.paperUi.error = null;
  const panel = document.querySelector('.r12-paper-panel');
  if (panel) {
    panel.setAttribute('aria-busy', 'true');
    panel.querySelectorAll('button').forEach((button) => { button.disabled = true; });
  }
  const feedback = document.querySelector('.r12-paper-feedback');
  if (feedback) {
    feedback.classList.remove('eval-diagnostic');
    feedback.textContent = message;
  }
}

function r12Step7Number(input, label, {positive=false, max=null}={}) {
  const value = Number(input?.value?.trim());
  if (!Number.isFinite(value) || value < 0 || (positive && value <= 0)) throw new Error(`${label} must be ${positive ? 'positive' : 'non-negative'}`);
  if (max !== null && value > max) throw new Error(`${label} must be <= ${max}`);
  return value;
}

async function r12Step7Command(kind, path, body, message) {
  try {
    const payloadWithoutKey = {...body};
    body.idempotency_key = r12Step7CommandKey(kind, payloadWithoutKey);
    r12Step7SetBusy(kind, message);
    const payload = await r12Step6Post(path, body);
    r12Step7Hydrate(payload, kind);
    toast(`Paper ledger: ${payload.trade.status}`);
  } catch (error) {
    r12Step2State.paperUi.error = error.message;
    toast(`Paper ledger: ${error.message}`);
  } finally {
    r12Step2State.paperUi.busy = null;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step7Create() {
  const runId = r12Step2State.agentRun?.run_id;
  const opportunityId = document.querySelector('#r12-paper-opportunity')?.value;
  if (!runId || !opportunityId) {
    r12Step2State.paperUi.error = 'A completed Agent run with an eligible E1 opportunity is required';
    renderDetail();
    return;
  }
  return r12Step7Command('create', '/api/r12/paper/create', {run_id:runId, opportunity_id:opportunityId}, '正在创建 0-fill paper intent');
}

async function r12Step7Load() {
  const paperTradeId = document.querySelector('#r12-paper-trade-id')?.value?.trim();
  if (!paperTradeId) {
    r12Step2State.paperUi.error = 'Paper trade ID is required';
    renderDetail();
    return;
  }
  try {
    r12Step7SetBusy('load', `正在回放 ${paperTradeId}`);
    const payload = await r12Step6Post('/api/r12/paper/status', {paper_trade_id:paperTradeId});
    r12Step7Hydrate(payload, 'load');
  } catch (error) {
    r12Step2State.paperUi.error = error.message;
  } finally {
    r12Step2State.paperUi.busy = null;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step7Fill(card) {
  const legId = card.dataset.legId;
  const remaining = r12Step2State.paperTrade.legs.find((leg) => leg.leg_id === legId)?.remaining_quantity;
  const body = {
    paper_trade_id:r12Step2State.paperTrade.paper_trade_id,
    leg_id:legId,
    quantity:r12Step7Number(card.querySelector('[data-paper-field="quantity"]'), 'Fill quantity', {positive:true}),
    price:r12Step7Number(card.querySelector('[data-paper-field="price"]'), 'Fill price', {max:1}),
    fee:r12Step7Number(card.querySelector('[data-paper-field="fee"]'), 'Fill fee'),
  };
  if (body.quantity > remaining) throw new Error(`Fill quantity must be <= remaining ${remaining}`);
  return r12Step7Command(`fill-${legId}`, '/api/r12/paper/fill', body, `正在记录 ${legId} 模拟成交`);
}

async function r12Step7Mark() {
  const marks = {};
  document.querySelectorAll('.r12-paper-leg').forEach((card) => {
    marks[card.dataset.legId] = r12Step7Number(card.querySelector('[data-paper-field="mark"]'), `Mark ${card.dataset.legId}`, {max:1});
  });
  return r12Step7Command('mark', '/api/r12/paper/mark', {paper_trade_id:r12Step2State.paperTrade.paper_trade_id, marks}, '正在追加 MTM marks');
}

function r12Step7Dispatch(action) {
  Promise.resolve().then(action).catch((error) => {
    r12Step2State.paperUi.error = error.message;
    if (appState.selectedNav === 'strategy') renderDetail();
  });
}

document.addEventListener('click', (event) => {
  const create = event.target?.closest?.('#r12-paper-create');
  const load = event.target?.closest?.('#r12-paper-load');
  const fill = event.target?.closest?.('.r12-paper-fill');
  const mark = event.target?.closest?.('#r12-paper-mark');
  const cancel = event.target?.closest?.('#r12-paper-cancel');
  const expire = event.target?.closest?.('#r12-paper-expire');
  const settle = event.target?.closest?.('.r12-paper-settle');
  if (!(create || load || fill || mark || cancel || expire || settle)) return;
  event.preventDefault();
  if (create) r12Step7Dispatch(() => r12Step7Create());
  if (load) r12Step7Dispatch(() => r12Step7Load());
  if (fill) r12Step7Dispatch(() => r12Step7Fill(fill.closest('.r12-paper-leg')));
  if (mark) r12Step7Dispatch(() => r12Step7Mark());
  if (cancel) r12Step7Dispatch(() => r12Step7Command('cancel', '/api/r12/paper/cancel', {paper_trade_id:r12Step2State.paperTrade.paper_trade_id, reason:'manual_paper_cancel'}, '正在取消剩余模拟数量'));
  if (expire) r12Step7Dispatch(() => r12Step7Command('expire', '/api/r12/paper/expire', {paper_trade_id:r12Step2State.paperTrade.paper_trade_id, reason:'manual_paper_expiry'}, '正在标记剩余模拟数量过期'));
  if (settle) r12Step7Dispatch(() => r12Step7Command(`settle-${settle.dataset.winner}`, '/api/r12/paper/settle', {paper_trade_id:r12Step2State.paperTrade.paper_trade_id, winning_outcome:settle.dataset.winner}, `正在按 ${settle.dataset.winner} 结算`));
});

renderAll();
