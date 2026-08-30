/* R12 Step 8: task-oriented Strategy Center workspaces. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r12_step6.css?v=r12-step8-v1';
  document.head.appendChild(link);
})();

const r12Step8State = {
  workspace:'agent',
  setupDraft:{
    kalshi_id:'', polymarket_id:'', target:'10', estimated_cost:'0', fee_source:'manual_provider_schedule_review', latency_bps:'0',
    k_fee_rate:'0', k_fee_contract:'0', k_fee_fixed:'0', p_fee_rate:'0', p_fee_contract:'0', p_fee_fixed:'0',
  },
};

const R12_STEP8_SETUP_FIELDS = {
  'r12-kalshi-id':'kalshi_id', 'r12-poly-id':'polymarket_id', 'r12-exec-target':'target', 'r12-rv-cost':'estimated_cost',
  'r12-fee-source':'fee_source', 'r12-latency-bps':'latency_bps', 'r12-k-fee-rate':'k_fee_rate',
  'r12-k-fee-contract':'k_fee_contract', 'r12-k-fee-fixed':'k_fee_fixed', 'r12-p-fee-rate':'p_fee_rate',
  'r12-p-fee-contract':'p_fee_contract', 'r12-p-fee-fixed':'p_fee_fixed',
};

function r12Step8Header() {
  const workspace = r12Step8State.workspace;
  const tabs = [
    ['agent', 'Agent Run', '发现 → 配置 → H1 → 报价 → paper ledger'],
    ['manual', 'Manual Lab', '逐个调用底层工具'],
    ['roadmap', 'Strategy Roadmap', '五组策略与边界'],
  ];
  return `<div class="strategy-center-head r12-step8-head">
    <div><div class="kicker">R12 · OPERATOR WORKSPACES</div><h2>Strategy Opportunity Center</h2><p>默认只展示端到端 Agent 主线；底层工具和策略路线图分别进入独立工作区。</p></div>
    <span class="pill done">PAPER SIGNAL ONLY</span>
  </div>
  <div class="r12-workspace-tabs" role="tablist" aria-label="Strategy Center workspace">
    ${tabs.map(([id,label,description]) => `<button type="button" id="r12-workspace-tab-${id}" class="r12-workspace-tab ${workspace === id ? 'active' : ''}" data-r12-workspace="${id}" role="tab" aria-controls="r12-workspace-panel" aria-selected="${workspace === id}" tabindex="${workspace === id ? '0' : '-1'}"><strong>${label}</strong><span>${description}</span></button>`).join('')}
  </div>`;
}

function r12Step8AgentSetupPanel() {
  const kalshi = r12Step2State.kalshi;
  const poly = r12Step2State.polymarket;
  const draft = r12Step8State.setupDraft;
  return `<section class="strategy-section r12-agent-setup">
    <div class="kicker">AGENT RUN · 2 · LOCK PAIR &amp; CONFIGURE</div>
    <div class="strategy-section-head"><div><h3>Exact Pair &amp; Paper Quote Assumptions</h3><p>搜索候选后锁定精确合同；费用和 latency 都必须由操作者显式输入。</p></div><span class="pill ${kalshi && poly ? 'done' : ''}">${kalshi && poly ? 'PAIR_LOADED' : 'PAIR_REQUIRED'}</span></div>
    <details class="r12-exact-fallback"><summary>Advanced fallback · enter exact provider IDs</summary>
      <div class="live-contract-inputs">
        <label>Kalshi market ticker<input id="r12-kalshi-id" value="${esc(kalshi?.provider_market_id || draft.kalshi_id)}" placeholder="exact market ticker"></label><button id="r12-load-kalshi" class="btn">Load Kalshi Contract</button>
        <label>Polymarket market ID<input id="r12-poly-id" value="${esc(poly?.provider_market_id || draft.polymarket_id)}" placeholder="exact Gamma market ID"></label><button id="r12-load-poly" class="btn">Load Polymarket Contract</button>
      </div>
    </details>
    ${r12Step2State.error ? `<div class="eval-diagnostic"><strong>Agent setup:</strong> ${esc(r12Step2State.error)}</div>` : ''}
    <div class="live-contract-grid">${r12Step2ContractCard('kalshi', kalshi)}${r12Step2ContractCard('polymarket', poly)}</div>
    <div class="execution-input-grid r12-agent-quote-inputs">
      <label>Target contracts<input id="r12-exec-target" value="${esc(draft.target)}"></label>
      <label>Estimated cost / basket<input id="r12-rv-cost" value="${esc(draft.estimated_cost)}"></label>
      <label>Fee model source<input id="r12-fee-source" value="${esc(draft.fee_source)}"></label>
      <label>Latency buffer (bps / leg)<input id="r12-latency-bps" value="${esc(draft.latency_bps)}"></label>
      <label>Kalshi fee / notional<input id="r12-k-fee-rate" value="${esc(draft.k_fee_rate)}"></label>
      <label>Kalshi fee / contract<input id="r12-k-fee-contract" value="${esc(draft.k_fee_contract)}"></label>
      <label>Kalshi fixed / order<input id="r12-k-fee-fixed" value="${esc(draft.k_fee_fixed)}"></label>
      <label>Polymarket fee / notional<input id="r12-p-fee-rate" value="${esc(draft.p_fee_rate)}"></label>
      <label>Polymarket fee / contract<input id="r12-p-fee-contract" value="${esc(draft.p_fee_contract)}"></label>
      <label>Polymarket fixed / order<input id="r12-p-fee-fixed" value="${esc(draft.p_fee_fixed)}"></label>
    </div>
  </section>`;
}

function r12Step8ReviewPanel() {
  const waiting = r12Step2State.agentRun?.status === 'WAITING_HUMAN_IDENTITY_APPROVAL';
  return `<section class="r12-agent-review">
    <div class="kicker">AGENT RUN · 4 · HUMAN SETTLEMENT REVIEW</div>
    ${r12Step2RulesPanel()}
    ${r12Step2IdentityPanel()}
    <div class="r12-inline-approval">
      <div><strong>H1 approval boundary</strong><span id="r12-agent-inline-feedback">${esc(`Manual checks ${r12Step6CheckedCount()}/6`)}</span></div>
      <button type="button" id="r12-agent-approve-inline" data-r12-agent-action="approve" class="btn primary" ${waiting && !r12Step2State.agentUi.busy ? '' : 'disabled'}>Approve H1 and Resume</button>
    </div>
  </section>`;
}

function r12Step8ResultsPanel() {
  const identity = r12Step2State.identity;
  const rv = r12Step2State.rv;
  const execution = r12Step2State.execution;
  return `<section class="strategy-section r12-agent-results">
    <div class="kicker">AGENT RUN · 5 · VERIFIED RESULTS</div>
    <div class="strategy-section-head"><div><h3>I1 / V1 / E1 Artifacts</h3><p>这里只展示 Agent 已完成任务的结果，不重复提供手动执行按钮。</p></div><span class="pill ${execution ? 'done' : ''}">${execution ? 'E1_READY' : 'WAITING'}</span></div>
    ${identity ? `<details><summary>I1 · Settlement Identity</summary><pre class="codebox">${esc(pretty(identity))}</pre></details>` : '<div class="strategy-scan-empty">等待 H1 审批和 I1。</div>'}
    ${rv ? r12Step2RenderRV(rv) : ''}
    ${execution ? r12Step2RenderExecution(execution) : ''}
  </section>`;
}

function r12Step8AgentWorkspace() {
  return `<div class="r12-step8-workspace r12-step8-agent">
    <section class="strategy-section r12-agent-guide"><div class="kicker">AGENT RUN · 1 · DISCOVER</div><h3>Find an Exact Cross-market Pair</h3><p>Search 只生成候选；Load pair 才把精确 ID 送入后续规则与身份验证链。</p></section>
    ${r12Step3DiscoveryPanel()}
    ${r12Step8AgentSetupPanel()}
    <div class="r12-agent-stage"><div class="kicker">AGENT RUN · 3 · START / RESUME</div>${r12Step7BaseRunPanel()}</div>
    ${r12Step8ReviewPanel()}
    ${r12Step8ResultsPanel()}
    <div class="r12-paper-stage"><div class="kicker">AGENT RUN · 6 · PAPER LEDGER</div>${r12Step7PaperPanel()}</div>
  </div>`;
}

function r12Step8StructuralLab() {
  return `<section class="strategy-section">
    <div class="strategy-section-head"><div><h3>Structural / Logic Arbitrage Scanner</h3><p>独立的标准化 snapshot 教学工具，不属于跨市场 Agent 主线。</p></div><button id="r12-reset-demo" class="btn">Reset Demo</button></div>
    <textarea id="r12-snapshot" class="strategy-json-input" spellcheck="false">${esc(r12StrategyState.snapshotText)}</textarea>
    <div class="strategy-actions"><button id="r12-scan" class="btn primary" ${r12StrategyState.loading ? 'disabled' : ''}>${r12StrategyState.loading ? 'Scanning…' : 'Run Structural Scan'}</button><span>Binary complement · Threshold monotonicity · Exhaustive partition</span></div>
    ${r12StrategyState.error ? `<div class="eval-diagnostic"><strong>Scanner error:</strong> ${esc(r12StrategyState.error)}</div>` : ''}
    ${r12RenderScan()}
  </section>`;
}

function r12Step8ManualWorkspace() {
  return `<div class="r12-step8-workspace r12-step8-manual">
    <section class="strategy-section r12-manual-guide"><div class="kicker">MANUAL LAB</div><h3>Inspect One Boundary at a Time</h3><p>这里保留 Load、Rules、Identity、RV、Execution Quote 等逐工具入口，用于学习和故障定位；正常验收不需要逐个点击。</p></section>
    ${r12Step8StructuralLab()}
    ${r12Step3BaseInspector()}
  </div>`;
}

function r12Step8RoadmapWorkspace() {
  return `<div class="r12-step8-workspace r12-step8-roadmap">
    <section class="strategy-section"><div class="kicker">STRATEGY ROADMAP</div><h3>Five-strategy Registry</h3>${r12RenderRegistry()}</section>
    <section class="strategy-section strategy-boundary"><h3>Current boundary</h3><p><strong>Structural edge ≠ calibrated macro alpha.</strong> Cross-market 已具备 HITL Agent 与 paper ledger；FOMC、CPI 和 Options 仍需要各自的 reference adapter、概率校准、成本和 settlement contract。</p></section>
  </div>`;
}

renderR12StrategyCenter = function renderR12Step8StrategyCenter() {
  const content = r12Step8State.workspace === 'manual'
    ? r12Step8ManualWorkspace()
    : r12Step8State.workspace === 'roadmap'
      ? r12Step8RoadmapWorkspace()
      : r12Step8AgentWorkspace();
  return `<div class="strategy-center r12-step8-center">${r12Step8Header()}<div id="r12-workspace-panel" class="r12-workspace-content" role="tabpanel" aria-labelledby="r12-workspace-tab-${r12Step8State.workspace}">${content}</div></div>`;
};

const r12Step8BaseHydrateAgent = r12Step6Hydrate;
r12Step6Hydrate = function r12Step8HydrateAgent(payload) {
  r12Step8BaseHydrateAgent(payload);
  const tasks = payload.run?.plan?.tasks || [];
  const execution = tasks.find((task) => task.task_id === 'E1')?.arguments || {};
  const rv = tasks.find((task) => task.task_id === 'V1')?.arguments || {};
  const fee = execution.fee_model || {};
  if (execution.target_contracts !== undefined) r12Step8State.setupDraft.target = String(execution.target_contracts);
  if (rv.estimated_total_cost_per_basket !== undefined) r12Step8State.setupDraft.estimated_cost = String(rv.estimated_total_cost_per_basket);
  if (execution.latency_buffer_bps !== undefined) r12Step8State.setupDraft.latency_bps = String(execution.latency_buffer_bps);
  if (fee.source) r12Step8State.setupDraft.fee_source = fee.source;
  [['kalshi','k'], ['polymarket','p']].forEach(([provider,prefix]) => {
    const row = fee[provider] || {};
    if (row.fee_rate_on_notional !== undefined) r12Step8State.setupDraft[`${prefix}_fee_rate`] = String(row.fee_rate_on_notional);
    if (row.fee_per_contract !== undefined) r12Step8State.setupDraft[`${prefix}_fee_contract`] = String(row.fee_per_contract);
    if (row.fixed_fee_per_order !== undefined) r12Step8State.setupDraft[`${prefix}_fee_fixed`] = String(row.fixed_fee_per_order);
  });
};

document.addEventListener('input', (event) => {
  const field = R12_STEP8_SETUP_FIELDS[event.target?.id];
  if (field) r12Step8State.setupDraft[field] = event.target.value;
});

document.addEventListener('change', (event) => {
  if (!event.target?.matches?.('[data-r12-identity]')) return;
  const feedback = document.querySelector('#r12-agent-inline-feedback');
  if (feedback) feedback.textContent = `Manual checks ${r12Step6CheckedCount()}/6`;
});

document.addEventListener('click', (event) => {
  const tab = event.target?.closest?.('[data-r12-workspace]');
  if (tab) {
    event.preventDefault();
    r12Step8State.workspace = tab.dataset.r12Workspace;
    if (appState.selectedNav === 'strategy') renderDetail();
    return;
  }
  const approval = event.target?.closest?.('#r12-agent-approve-inline');
  if (approval) {
    event.preventDefault();
    r12Step6Approve();
  }
});

document.addEventListener('keydown', (event) => {
  const tab = event.target?.closest?.('[data-r12-workspace]');
  if (!tab || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  const tabs = [...document.querySelectorAll('[data-r12-workspace]')];
  const current = tabs.indexOf(tab);
  if (current < 0) return;
  event.preventDefault();
  const next = event.key === 'Home'
    ? 0
    : event.key === 'End'
      ? tabs.length - 1
      : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  tabs[next].click();
  document.querySelector(`[data-r12-workspace="${r12Step8State.workspace}"]`)?.focus();
});

renderAll();
