/* R12 Step 6: Tool-DAG Strategy Agent with durable human approval pause/resume. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r12_step4.css?v=r12-step6-v1';
  document.head.appendChild(link);
})();

r12Step2State.agentRun = null;
r12Step2State.agentEval = null;

function r12Step6RunPanel() {
  const run = r12Step2State.agentRun;
  const waiting = run?.status === 'WAITING_HUMAN_IDENTITY_APPROVAL';
  const tasks = run?.plan?.tasks || [];
  return `<section class="strategy-section r12-agent-panel">
    <div class="kicker">R12 · STEP 6 · HUMAN-IN-THE-LOOP STRATEGY AGENT</div>
    <div class="strategy-section-head"><div><h3>Tool DAG · Durable Pause · Resume</h3><p>Agent 通过共享 Runtime/Tool Registry 获取两份合同并分析规则，在 H1 人工身份审批点持久化暂停。审批前绝不会运行 I1、V1 或 E1。</p></div><span class="pill ${run?.status === 'COMPLETED_PAPER_QUOTE' ? 'done' : waiting ? 'ready' : 'fail'}">${esc(run?.status || 'NOT_STARTED')}</span></div>
    <div class="r12-agent-actions">
      <button id="r12-agent-start" class="btn primary">Start Exact-pair Agent</button>
      <label>Durable run ID<input id="r12-agent-run-id" value="${esc(run?.run_id || '')}" placeholder="R12A-..."></label>
      <button id="r12-agent-resume" class="btn">Load / Resume Run</button>
      <button id="r12-agent-approve" class="btn primary" ${waiting ? '' : 'disabled'}>Approve H1 and Resume</button>
    </div>
    <p class="muted">Start 使用下方 exact contract IDs、target、fees 与 latency 输入。H1 等待时，请阅读 Rules Analysis，并手工勾选下方六个 identity checkbox，再点击 Approve H1。</p>
    ${run ? `<div class="strategy-summary"><div><span>Run</span><strong>${esc(run.run_id)}</strong></div><div><span>Next task</span><strong>${esc(run.next_task_id || 'DONE')}</strong></div><div><span>Checkpoints</span><strong>${esc(run.checkpoints?.length || 0)}</strong></div><div><span>Eval</span><strong>${esc(r12Step2State.agentEval?.passed)}</strong></div></div>
      <div class="r12-agent-task-list">${tasks.map((task) => `<div class="r12-agent-task"><strong>${esc(task.task_id)} · ${esc(task.tool_name)}</strong><span>${esc(task.status)}</span></div>`).join('')}</div>
      <details><summary>Strategy Agent run / trace / checkpoints</summary><pre class="codebox">${esc(pretty({run, eval:r12Step2State.agentEval}))}</pre></details>` : '<div class="strategy-scan-empty">Start an exact-pair run to see Runtime Tool tasks and the durable approval boundary.</div>'}
    <div class="paper-only">READ_COMPUTE_TOOLS_ONLY · HUMAN_APPROVAL_REQUIRED · NO_AUTO_EXECUTION</div>
  </section>`;
}

const r12Step6BaseInspector = r12Step2Inspector;
r12Step2Inspector = function r12Step6Inspector() {
  return `${r12Step6RunPanel()}${r12Step6BaseInspector()}`;
};

function r12Step6FeeModel() {
  const source = document.querySelector('#r12-fee-source')?.value?.trim();
  if (!source) throw new Error('Explicit fee model source is required');
  return {
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
}

function r12Step6Hydrate(payload) {
  const run = payload.run;
  r12Step2State.agentRun = run;
  r12Step2State.agentEval = payload.eval;
  const results = run.results || {};
  r12Step2State.kalshi = results.K1 || null;
  r12Step2State.polymarket = results.P1 || null;
  r12Step2State.rulesAnalysis = results.R1 || null;
  r12Step2State.identity = results.I1 || null;
  r12Step2State.rv = results.V1 || null;
  r12Step2State.execution = results.E1 || null;
}

async function r12Step6Post(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type':'application/json', 'Accept':'application/json'},
    cache: 'no-store',
    body: JSON.stringify(body),
  });
  const raw = await response.text();
  let payload;
  try { payload = JSON.parse(raw); }
  catch (_) { throw new Error(`Strategy Agent returned non-JSON (HTTP ${response.status})`); }
  if (!response.ok || !payload.ok) throw new Error(payload.error?.message || `HTTP ${response.status}`);
  return payload;
}

async function r12Step6Start() {
  try {
    const kalshiIdentifier = r12Step2State.kalshi?.provider_market_id || document.querySelector('#r12-kalshi-id')?.value?.trim();
    const polymarketIdentifier = r12Step2State.polymarket?.provider_market_id || document.querySelector('#r12-poly-id')?.value?.trim();
    if (!kalshiIdentifier || !polymarketIdentifier) throw new Error('Load or enter both exact market identifiers first');
    const target = r12Step2FiniteNonNegative('#r12-exec-target', 'Target contracts');
    if (target <= 0) throw new Error('Target contracts must be greater than zero');
    const cost = r12Step2FiniteNonNegative('#r12-rv-cost', 'Estimated basket cost');
    const payload = await r12Step6Post('/api/r12/agent/start', {
      kalshi_identifier: kalshiIdentifier,
      polymarket_identifier: polymarketIdentifier,
      target_contracts: target,
      fee_model: r12Step6FeeModel(),
      latency_buffer_bps: r12Step2FiniteNonNegative('#r12-latency-bps', 'Latency buffer'),
      estimated_total_cost_per_basket: cost,
    });
    r12Step6Hydrate(payload);
    toast(`Strategy Agent: ${payload.run.status}`);
  } catch (error) {
    r12Step2State.error = error.message;
    toast(`Strategy Agent: ${error.message}`);
  } finally {
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step6Resume() {
  try {
    const runId = document.querySelector('#r12-agent-run-id')?.value?.trim() || r12Step2State.agentRun?.run_id;
    if (!runId) throw new Error('Durable run ID is required');
    const payload = await r12Step6Post('/api/r12/agent/resume', {run_id:runId});
    r12Step6Hydrate(payload);
    toast(`Strategy Agent resume: ${payload.run.status}`);
  } catch (error) {
    r12Step2State.error = error.message;
    toast(`Strategy Agent resume: ${error.message}`);
  } finally {
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step6Approve() {
  try {
    const runId = r12Step2State.agentRun?.run_id;
    if (!runId) throw new Error('No active Strategy Agent run');
    const attestation = {attestation_source: document.querySelector('#r12-attestation-source')?.value?.trim()};
    document.querySelectorAll('[data-r12-identity]').forEach((input) => {
      attestation[input.dataset.r12Identity] = Boolean(input.checked);
    });
    const payload = await r12Step6Post('/api/r12/agent/approve', {run_id:runId, attestation});
    r12Step6Hydrate(payload);
    toast(`Strategy Agent: ${payload.run.status}`);
  } catch (error) {
    r12Step2State.error = error.message;
    toast(`Strategy Agent approval: ${error.message}`);
  } finally {
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

document.addEventListener('click', (event) => {
  if (event.target?.id === 'r12-agent-start') r12Step6Start();
  if (event.target?.id === 'r12-agent-resume') r12Step6Resume();
  if (event.target?.id === 'r12-agent-approve') r12Step6Approve();
});

renderAll();
