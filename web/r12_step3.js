/* R12 Step 3 UI: free-text discovery -> candidate selection -> existing identity gate. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r12_step3.css?v=r12-step3-v1';
  document.head.appendChild(link);
})();

const r12Step3State = {
  query: 'Fed September rate cut',
  discovery: null,
  loading: false,
  loadingCandidate: null,
  error: null,
  selected: {kalshi: null, polymarket: null},
};

function r12Step3ProviderPanel(provider) {
  const block = r12Step3State.discovery?.providers?.[provider];
  if (!block) return `<section class="discovery-provider"><div class="kicker">${esc(provider.toUpperCase())}</div><div class="empty">Search to discover candidates.</div></section>`;
  const candidates = block.candidates || [];
  return `<section class="discovery-provider">
    <div class="discovery-provider-head">
      <div><div class="kicker">${esc(provider.toUpperCase())}</div><strong>${esc(block.status || '—')}</strong></div>
      <span class="pill">${esc(candidates.length)} candidates</span>
    </div>
    <p class="muted">${esc(block.search_mode || '')}</p>
    <p class="muted">Coverage: ${esc(block.coverage_status || '—')}</p>
    ${block.error ? `<div class="eval-diagnostic"><strong>${esc(block.error.code || 'Error')}:</strong> ${esc(block.error.message || '')}</div>` : ''}
    <div class="candidate-list">${candidates.length ? candidates.map(r12Step3CandidateCard).join('') : '<div class="empty">No candidate returned in this bounded discovery window.</div>'}</div>
  </section>`;
}

function r12Step3CandidateCard(row) {
  const selected = r12Step3State.selected?.[row.provider] === row.identifier;
  return `<article class="candidate-card ${selected ? 'selected' : ''}">
    <div class="candidate-head"><span class="pill ${selected ? 'done' : ''}">${selected ? 'LOADED' : 'CANDIDATE ONLY'}</span><span>match ${esc(row.query_match_score ?? '—')}</span></div>
    <strong>${esc(row.market_title || row.event_title || row.identifier)}</strong>
    <p>${esc(row.event_title || '')}</p>
    <div class="candidate-meta"><span>ID ${esc(row.identifier)}</span><span>${esc(row.close_time || 'time —')}</span></div>
    <p class="muted">${esc(row.match_score_type || '')}</p>
    <button class="btn r12-use-candidate" data-provider="${esc(row.provider)}" data-identifier="${esc(row.identifier)}">Load exact contract for review</button>
  </article>`;
}

function r12Step3PairPanel() {
  const pairs = r12Step3State.discovery?.candidate_pairs || [];
  return `<section class="discovery-pairs">
    <div class="strategy-section-head"><div><h4>Cross-provider candidate pairs</h4><p>这里只做 lexical candidate ranking。<strong>Candidate Match ≠ Same Event</strong>。</p></div><span class="pill fail">IDENTITY UNVERIFIED</span></div>
    ${pairs.length ? pairs.map((row) => `<article class="pair-card">
      <div class="pair-score"><span>pair score</span><strong>${esc(row.pair_score)}</strong></div>
      <div class="pair-legs"><div><span>KALSHI</span><strong>${esc(row.kalshi_title || row.kalshi_identifier)}</strong><small>${esc(row.kalshi_identifier)}</small></div><div class="pair-arrow">↔</div><div><span>POLYMARKET</span><strong>${esc(row.polymarket_title || row.polymarket_identifier)}</strong><small>${esc(row.polymarket_identifier)}</small></div></div>
      <p class="muted">${esc(row.status)} · lexical similarity ${esc(row.lexical_similarity)}</p>
      <button class="btn primary r12-load-pair" data-kalshi="${esc(row.kalshi_identifier)}" data-polymarket="${esc(row.polymarket_identifier)}">Load pair for settlement review</button>
    </article>`).join('') : '<div class="empty">No cross-provider pair could be ranked from the current discovery results.</div>'}
  </section>`;
}

function r12Step3DiscoveryPanel() {
  const discovery = r12Step3State.discovery;
  return `<section class="strategy-section discovery-center">
    <div class="kicker">R12 · STEP 3 · MARKET DISCOVERY</div>
    <h3>Search Markets Instead of Typing Provider IDs</h3>
    <p>输入自然语言事件。Kalshi 使用<strong>有界 open-event 列表 + 本地 lexical ranking</strong>；Polymarket 使用官方 <code>public-search</code>。搜索只负责找候选，不负责证明 settlement identity。</p>
    <div class="discovery-search-row"><input id="r12-discovery-query" value="${esc(r12Step3State.query)}" placeholder="e.g. Fed September rate cut"><button id="r12-discovery-search" class="btn primary" ${r12Step3State.loading ? 'disabled' : ''}>${r12Step3State.loading ? 'Searching…' : 'Search Both Markets'}</button></div>
    <div class="discovery-guardrail"><strong>CANDIDATE_ONLY_IDENTITY_UNVERIFIED</strong><span>Search score is a lexical heuristic, not probability and not settlement proof.</span></div>
    ${r12Step3State.error ? `<div class="eval-diagnostic"><strong>Discovery:</strong> ${esc(r12Step3State.error)}</div>` : ''}
    ${discovery ? `<div class="discovery-summary"><span>Query <strong>${esc(discovery.query)}</strong></span><span>Pairs <strong>${esc(discovery.pair_count)}</strong></span><span>Next <strong>rules review</strong></span></div>` : ''}
    <div class="discovery-provider-grid">${r12Step3ProviderPanel('kalshi')}${r12Step3ProviderPanel('polymarket')}</div>
    ${discovery ? r12Step3PairPanel() : ''}
    <p class="muted">下面的 exact ticker / market-ID 输入框保留为 <strong>Advanced fallback</strong>。正常流程优先从上面的搜索候选点击加载。</p>
  </section>`;
}

const r12Step3BaseInspector = r12Step2Inspector;
r12Step2Inspector = function r12Step3Inspector() {
  return `${r12Step3DiscoveryPanel()}${r12Step3BaseInspector()}`;
};

async function r12Step3Search() {
  try {
    const query = document.querySelector('#r12-discovery-query')?.value?.trim() || r12Step3State.query.trim();
    if (!query) throw new Error('Search query is required');
    r12Step3State.query = query;
    r12Step3State.loading = true;
    r12Step3State.error = null;
    if (appState.selectedNav === 'strategy') renderDetail();
    const response = await fetch('/api/r12/discovery', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'Accept':'application/json'},
      cache: 'no-store',
      body: JSON.stringify({query}),
    });
    const raw = await response.text();
    let payload;
    try { payload = JSON.parse(raw); }
    catch (_) { throw new Error(`Discovery endpoint returned non-JSON (HTTP ${response.status})`); }
    if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
    r12Step3State.discovery = payload.discovery;
    toast(`Discovery: ${payload.discovery.pair_count} candidate pair(s)`);
  } catch (error) {
    r12Step3State.error = error.message;
    toast(`Discovery: ${error.message}`);
  } finally {
    r12Step3State.loading = false;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step3FetchContract(provider, identifier) {
  const response = await fetch('/api/r12/market-contract', {
    method: 'POST',
    headers: {'Content-Type':'application/json', 'Accept':'application/json'},
    cache: 'no-store',
    body: JSON.stringify({provider, identifier}),
  });
  const raw = await response.text();
  let payload;
  try { payload = JSON.parse(raw); }
  catch (_) { throw new Error(`${provider} market adapter returned non-JSON (HTTP ${response.status})`); }
  if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `${provider} HTTP ${response.status}`);
  return payload.contract;
}

async function r12Step3LoadCandidate(provider, identifier) {
  try {
    r12Step3State.loadingCandidate = `${provider}:${identifier}`;
    r12Step3State.error = null;
    const contract = await r12Step3FetchContract(provider, identifier);
    r12Step2State[provider] = contract;
    r12Step2State.identity = null;
    r12Step2State.rv = null;
    r12Step2State.execution = null;
    r12Step3State.selected[provider] = identifier;
    toast(`${provider} candidate loaded for rules review`);
  } catch (error) {
    r12Step3State.error = error.message;
    toast(`Candidate load: ${error.message}`);
  } finally {
    r12Step3State.loadingCandidate = null;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step3LoadPair(kalshiIdentifier, polymarketIdentifier) {
  try {
    r12Step3State.loadingCandidate = 'pair';
    r12Step3State.error = null;
    const [kalshi, polymarket] = await Promise.all([
      r12Step3FetchContract('kalshi', kalshiIdentifier),
      r12Step3FetchContract('polymarket', polymarketIdentifier),
    ]);
    r12Step2State.kalshi = kalshi;
    r12Step2State.polymarket = polymarket;
    r12Step2State.identity = null;
    r12Step2State.rv = null;
    r12Step3State.selected.kalshi = kalshiIdentifier;
    r12Step3State.selected.polymarket = polymarketIdentifier;
    toast('Candidate pair loaded. Settlement identity is still UNVERIFIED.');
  } catch (error) {
    r12Step3State.error = error.message;
    toast(`Pair load: ${error.message}`);
  } finally {
    r12Step3State.loadingCandidate = null;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

document.addEventListener('input', (event) => {
  if (event.target?.id === 'r12-discovery-query') r12Step3State.query = event.target.value;
});

document.addEventListener('keydown', (event) => {
  if (event.target?.id === 'r12-discovery-query' && event.key === 'Enter') {
    event.preventDefault();
    r12Step3Search();
  }
});

document.addEventListener('click', (event) => {
  if (event.target?.id === 'r12-discovery-search') r12Step3Search();
  const candidate = event.target?.closest?.('.r12-use-candidate');
  if (candidate) r12Step3LoadCandidate(candidate.dataset.provider, candidate.dataset.identifier);
  const pair = event.target?.closest?.('.r12-load-pair');
  if (pair) r12Step3LoadPair(pair.dataset.kalshi, pair.dataset.polymarket);
});

renderAll();
