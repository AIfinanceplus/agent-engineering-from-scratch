/* R12 Step 6: Tool-DAG Strategy Agent with durable human approval pause/resume. */

(() => {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'r12_step4.css?v=r12-step6-v2';
  document.head.appendChild(link);
})();

r12Step2State.agentRun = null;
r12Step2State.agentEval = null;
r12Step2State.agentUi = {
  busy: null,
  message: 'Agent 尚未启动。',
  error: null,
};

function r12Step6Ui() {
  return r12Step2State.agentUi;
}

function r12Step6Draft() {
  if (!r12Step2State.agentAttestationDraft) {
    r12Step2State.agentAttestationDraft = {attestation_source:'human_rules_review', checks:{}};
  }
  return r12Step2State.agentAttestationDraft;
}

function r12Step6CheckedCount() {
  const checks = r12Step6Draft().checks || {};
  return R12_IDENTITY_CHECKS.filter(([key]) => checks[key] === true).length;
}

function r12Step6SetBusy(action, message) {
  const ui = r12Step6Ui();
  ui.busy = action;
  ui.message = message;
  ui.error = null;
  const buttons = document.querySelectorAll(`#r12-agent-${action}, [data-r12-agent-action="${action}"]`);
  buttons.forEach((button) => {
    button.disabled = true;
    button.textContent = action === 'approve' ? 'Approving H1…' : action === 'start' ? 'Starting Agent…' : 'Loading Run…';
  });
  r12Step6RefreshFeedback();
}

function r12Step6RefreshFeedback() {
  const feedback = document.querySelector('#r12-agent-feedback');
  if (!feedback) return;
  const ui = r12Step6Ui();
  const count = r12Step6CheckedCount();
  feedback.className = `r12-agent-feedback ${ui.error ? 'eval-diagnostic' : ''}`;
  feedback.textContent = ui.error || `${ui.message} · H1 checks ${count}/6`;
}

function r12Step6CollectAttestation() {
  const draft = r12Step6Draft();
  draft.attestation_source = document.querySelector('#r12-attestation-source')?.value?.trim() || '';
  document.querySelectorAll('[data-r12-identity]').forEach((input) => {
    draft.checks[input.dataset.r12Identity] = Boolean(input.checked);
  });
  return {attestation_source:draft.attestation_source, ...draft.checks};
}

function r12Step6RunPanel() {
  const run = r12Step2State.agentRun;
  const waiting = run?.status === 'WAITING_HUMAN_IDENTITY_APPROVAL';
  const tasks = run?.plan?.tasks || [];
  const ui = r12Step6Ui();
  return `<section class="strategy-section r12-agent-panel">
    <div class="kicker">R12 · STEP 6 · HUMAN-IN-THE-LOOP STRATEGY AGENT</div>
    <div class="strategy-section-head"><div><h3>Tool DAG · Durable Pause · Resume</h3><p>Agent 通过共享 Runtime/Tool Registry 获取两份合同并分析规则，在 H1 人工身份审批点持久化暂停。审批前绝不会运行 I1、V1 或 E1。</p></div><span class="pill ${run?.status === 'COMPLETED_PAPER_QUOTE' ? 'done' : waiting ? 'ready' : 'fail'}">${esc(run?.status || 'NOT_STARTED')}</span></div>
    <div class="r12-agent-actions">
      <button type="button" id="r12-agent-start" class="btn primary" ${ui.busy ? 'disabled' : ''}>${ui.busy === 'start' ? 'Starting Agent…' : 'Start Exact-pair Agent'}</button>
      <label>Durable run ID<input id="r12-agent-run-id" value="${esc(run?.run_id || '')}" placeholder="R12A-..."></label>
      <button type="button" id="r12-agent-resume" class="btn" ${ui.busy ? 'disabled' : ''}>${ui.busy === 'resume' ? 'Loading Run…' : 'Load / Resume Run'}</button>
      <button type="button" id="r12-agent-approve" class="btn primary" ${waiting && !ui.busy ? '' : 'disabled'}>${ui.busy === 'approve' ? 'Approving H1…' : 'Approve H1 and Resume'}</button>
    </div>
    <p class="muted">Start 使用 Agent Setup 中的 exact contract IDs、target、fees 与 latency 输入。H1 等待时，请阅读 Rules Analysis，并手工勾选六个 identity checkbox，再点击 Approve H1。</p>
    <div id="r12-agent-feedback" class="r12-agent-feedback ${ui.error ? 'eval-diagnostic' : ''}" role="status" aria-live="polite">${esc(ui.error || `${ui.message} · H1 checks ${r12Step6CheckedCount()}/6`)}</div>
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
    const feeModel = r12Step6FeeModel();
    const latencyBufferBps = r12Step2FiniteNonNegative('#r12-latency-bps', 'Latency buffer');
    r12Step2State.agentAttestationDraft = {attestation_source:'human_rules_review', checks:{}};
    r12Step6SetBusy('start', '正在获取两边合同并运行 K1 / P1 / R1');
    const payload = await r12Step6Post('/api/r12/agent/start', {
      kalshi_identifier: kalshiIdentifier,
      polymarket_identifier: polymarketIdentifier,
      target_contracts: target,
      fee_model: feeModel,
      latency_buffer_bps: latencyBufferBps,
      estimated_total_cost_per_basket: cost,
    });
    r12Step6Hydrate(payload);
    r12Step6Ui().message = payload.run.status === 'WAITING_HUMAN_IDENTITY_APPROVAL'
      ? '已暂停在 H1；请完成下方六项人工核对'
      : `Agent status: ${payload.run.status}`;
    r12Step6Ui().error = null;
    toast(`Strategy Agent: ${payload.run.status}`);
  } catch (error) {
    r12Step2State.error = error.message;
    r12Step6Ui().error = error.message;
    toast(`Strategy Agent: ${error.message}`);
  } finally {
    r12Step6Ui().busy = null;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step6Resume() {
  try {
    const runId = document.querySelector('#r12-agent-run-id')?.value?.trim() || r12Step2State.agentRun?.run_id;
    if (!runId) throw new Error('Durable run ID is required');
    r12Step6SetBusy('resume', `正在加载 ${runId}`);
    const payload = await r12Step6Post('/api/r12/agent/resume', {run_id:runId});
    r12Step6Hydrate(payload);
    r12Step6Ui().message = `Run loaded: ${payload.run.status}`;
    r12Step6Ui().error = null;
    toast(`Strategy Agent resume: ${payload.run.status}`);
  } catch (error) {
    r12Step2State.error = error.message;
    r12Step6Ui().error = error.message;
    toast(`Strategy Agent resume: ${error.message}`);
  } finally {
    r12Step6Ui().busy = null;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

async function r12Step6Approve() {
  try {
    const runId = r12Step2State.agentRun?.run_id;
    if (!runId) throw new Error('No active Strategy Agent run');
    if (r12Step2State.agentRun?.status !== 'WAITING_HUMAN_IDENTITY_APPROVAL') {
      throw new Error(`Run is ${r12Step2State.agentRun?.status || 'NOT_STARTED'}, not waiting for H1 approval`);
    }
    const attestation = r12Step6CollectAttestation();
    const missing = R12_IDENTITY_CHECKS.filter(([key]) => attestation[key] !== true).map(([,label]) => label);
    if (missing.length) throw new Error(`Complete all six identity checks first (${6 - missing.length}/6 checked)`);
    if (!attestation.attestation_source) throw new Error('Review / attestation source is required');
    r12Step6SetBusy('approve', 'H1 已提交；正在继续 I1 / V1 / E1');
    const payload = await r12Step6Post('/api/r12/agent/approve', {run_id:runId, attestation});
    r12Step6Hydrate(payload);
    r12Step6Ui().message = `H1 approved; Agent completed with ${payload.run.status}`;
    r12Step6Ui().error = null;
    toast(`Strategy Agent: ${payload.run.status}`);
  } catch (error) {
    r12Step2State.error = error.message;
    r12Step6Ui().error = error.message;
    toast(`Strategy Agent approval: ${error.message}`);
  } finally {
    r12Step6Ui().busy = null;
    if (appState.selectedNav === 'strategy') renderDetail();
  }
}

document.addEventListener('input', (event) => {
  if (event.target?.id === 'r12-attestation-source') {
    r12Step6Draft().attestation_source = event.target.value;
    r12Step6RefreshFeedback();
  }
});

document.addEventListener('change', (event) => {
  const input = event.target?.closest?.('[data-r12-identity]');
  if (!input) return;
  r12Step6Draft().checks[input.dataset.r12Identity] = Boolean(input.checked);
  r12Step6RefreshFeedback();
});

document.addEventListener('click', (event) => {
  const button = event.target?.closest?.('#r12-agent-start, #r12-agent-resume, #r12-agent-approve');
  if (!button) return;
  event.preventDefault();
  if (button.id === 'r12-agent-start') r12Step6Start();
  if (button.id === 'r12-agent-resume') r12Step6Resume();
  if (button.id === 'r12-agent-approve') r12Step6Approve();
});

renderAll();
