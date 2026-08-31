const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '—').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const money = (value) => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:2}).format(Number(value));

function metric(label, value, className='') {
  return `<article class="metric ${className}"><span>${esc(label)}</span><strong>${esc(value)}</strong></article>`;
}

function fact(label, value) {
  return `<div class="fact"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}

function renderRun(run) {
  const simulation = run.simulation;
  const trade = simulation.completed_trade;
  const latest = simulation.latest_market_context;
  const evalResult = run.eval;
  $('#empty').hidden = true;
  $('#results').hidden = false;
  $('#metrics').innerHTML = [
    metric('Simulated action', trade.action),
    metric('Entry z-score', trade.entry_z_score),
    metric('Spread move', `${trade.spread_change_bps} bp`),
    metric('Net paper P&L', money(trade.net_pnl_usd), trade.net_pnl_usd >= 0 ? 'positive' : 'negative'),
  ].join('');
  $('#trade').innerHTML = `<div class="eyebrow">S1 · ONE CLOSED PAPER TRADE</div><h2>${esc(trade.paper_trade_id)}</h2><div class="facts">
    ${fact('Entry', trade.entry_date)}${fact('Exit', trade.exit_date)}
    ${fact('Entry spread', `${trade.entry_spread_bps} bp`)}${fact('Exit spread', `${trade.exit_spread_bps} bp`)}
    ${fact('Gross P&L', money(trade.gross_pnl_usd))}${fact('Explicit cost', money(trade.cost_usd))}
  </div>`;
  $('#context').innerHTML = `<div class="eyebrow">LATEST DATA CONTEXT</div><h2>${esc(latest.action)}</h2><div class="facts">
    ${fact('Data as of', latest.as_of)}${fact('Latest z-score', latest.z_score)}
    ${fact('2s10s spread', `${latest.entry_spread_bps} bp`)}${fact('Rolling mean', `${latest.rolling_mean_bps} bp`)}
    ${fact('FRED observations', run.data.observation_count)}${fact('Source', 'DGS2 + DGS10')}
  </div>`;
  $('#eval-badge').textContent = evalResult.passed ? 'EVAL PASSED' : 'EVAL FAILED';
  $('#eval-badge').className = `badge ${evalResult.passed ? 'pass' : 'fail'}`;
  $('#trace').innerHTML = run.trace.map((row) => `<article><b>${esc(row.task_id)}</b><span>${esc(row.event)}</span><small>${esc(row.tool_name || row.artifact_type)} · ${esc(row.status || (row.passed ? 'PASSED' : 'FAILED'))}</small></article>`).join('');
  $('#raw').textContent = JSON.stringify(run, null, 2);
}

async function runOnce() {
  const button = $('#run-once');
  const error = $('#error');
  button.disabled = true;
  button.textContent = 'Running D1 → S1 → E1…';
  error.hidden = true;
  try {
    const response = await fetch('/api/rates/run-once', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify({
        lookback_days: Number($('#lookback').value),
        entry_z: Number($('#entry-z').value),
        holding_days: Number($('#holding').value),
        dv01_usd_per_bp: Number($('#dv01').value),
        round_trip_cost_bps: Number($('#cost').value),
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
    renderRun(payload.run);
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = 'Run One Paper Simulation';
  }
}

$('#run-once').addEventListener('click', runOnce);
