const $ = (selector) => document.querySelector(selector);
const pretty = (value) => JSON.stringify(value, null, 2);
const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));

const runButton = $('#run-btn');
const evalButton = $('#eval-btn');
const checkForecastButton = $('#check-forecast-btn');
const prevButton = $('#prev-btn');
const nextButton = $('#next-btn');
const autoButton = $('#auto-btn');
const resetButton = $('#reset-btn');
const goalInput = $('#goal');
const domainInput = $('#domain');
const contextPreset = $('#context-preset');
const forecastPackInput = $('#forecast-pack');

const planStatus = $('#plan-status');
const planProgress = $('#plan-progress');
const evidenceCount = $('#evidence-count');
const traceKpi = $('#trace-kpi');
const evalKpi = $('#eval-kpi');
const finalResult = $('#final-result');
const planBadge = $('#plan-badge');
const planList = $('#plan-list');
const leftKicker = $('#left-kicker');
const leftTitle = $('#left-title');
const dagHint = $('#dag-hint');
const legend = $('#legend');
const runKicker = $('#run-kicker');
const runTitle = $('#run-title');
const modeLabel = $('#mode-label');
const modeHelp = $('#mode-help');
const eventCounter = $('#event-counter');
const currentAction = $('#current-action');
const timeline = $('#timeline');
const codeTitle = $('#code-title');
const codeFile = $('#code-file');
const codePanel = $('#code-panel');
const explainBody = $('#explain-body');
const supportKicker = $('#support-kicker');
const citationTitle = $('#citation-title');
const citationList = $('#citation-list');
const qualityDetail = $('#quality-detail');
const domainDetail = $('#domain-detail');
const forecastDetail = $('#forecast-detail');
const traceDetail = $('#trace-detail');
const evalDetail = $('#eval-detail');
const runtimeDetail = $('#runtime-detail');
const rawEvent = $('#raw-event');

let stepItems = [];
let stepIndex = -1;
let autoTimer = null;
let mode = 'run';

async function post(payload) {
  const response = await fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function loadForecastPacks(preferId = null) {
  try {
    const payload = await post({action: 'r7_packs'});
    const packs = payload.packs || [];
    const selected = preferId || forecastPackInput.value;
    forecastPackInput.innerHTML = '<option value="">none</option>';
    packs.forEach((pack) => {
      const option = document.createElement('option');
      option.value = pack.pack_id;
      const score = pack.scoreboard || {};
      option.textContent = `${pack.pack_id} · ${pack.created_at || '—'} · ${pack.domain || '—'} · ${pack.scenario || '—'} · ${score.resolved || 0} resolved`;
      forecastPackInput.appendChild(option);
    });
    if (selected && packs.some((pack) => pack.pack_id === selected)) {
      forecastPackInput.value = selected;
    } else if (packs.length) {
      forecastPackInput.value = packs[0].pack_id;
    }
  } catch (error) {
    console.warn('Could not load saved forecast packs', error);
  }
}

function meaningful(event) {
  return [
    'research_question_received', 'decomposition_created', 'queries_compiled',
    'domain_lens_selected', 'plan_created', 'scheduler_tick', 'task_started',
    'evidence_registered', 'synthesis_verified', 'task_completed', 'task_failed',
    'quality_assessed', 'domain_brief_created', 'forecast_pack_created',
    'forecast_pack_saved', 'plan_completed', 'plan_failed',
  ].includes(event.type) || (
    event.type === 'task_runtime_event' &&
    ['tool_validation', 'policy_decision', 'tool_attempt', 'tool_result'].includes((event.event || {}).type)
  );
}

function renderPlan(result) {
  const blueprint = result.blueprint || {};
  const plan = result.plan || {};
  const tasks = plan.tasks || [];
  const taskById = Object.fromEntries(tasks.map((item) => [item.task_id, item]));
  const subById = Object.fromEntries((blueprint.subquestions || []).map((item) => [item.subquestion_id, item]));

  leftKicker.textContent = 'R7 PLAN';
  leftTitle.textContent = 'Queries → S1 → D1 → F1';
  legend.style.display = 'flex';
  dagHint.innerHTML = `${(blueprint.queries || []).map((q) => `<span>${esc(q.query_id)}</span>`).join('<span>+</span>')}<span>→</span><span>S1</span><span>→</span><span>D1</span><span>→</span><span>F1</span>`;
  planList.innerHTML = '';

  (blueprint.queries || []).forEach((query) => {
    const task = taskById[query.query_id] || {};
    const sub = subById[query.subquestion_id] || {};
    const card = document.createElement('article');
    card.className = `blueprint-card ${task.status || 'pending'}`;
    card.innerHTML = `
      <div class="blueprint-head"><strong>${esc(query.query_id)} · ${esc(query.provider)}</strong><code>${esc(query.capability)}</code></div>
      <p>${esc(sub.question)}</p>
      <small>${esc(query.tool_name)} · ${esc((query.arguments || {}).series_id || '')}</small>`;
    planList.appendChild(card);
  });

  [
    ['S1', 'RESEARCH SYNTHESIS', 'Evidence → quality / relations → grounded conclusion'],
    ['D1', `${String(result.domain || '').toUpperCase()} DOMAIN`, 'S1 → decision frame without new Evidence'],
    ['F1', 'FORECAST PACK', 'S1 + D1 → falsifiable forecast contracts + scenario tracker'],
  ].forEach(([taskId, title, detail]) => {
    const task = taskById[taskId] || {};
    const card = document.createElement('article');
    card.className = `blueprint-card ${task.status || 'pending'}`;
    card.innerHTML = `<div class="blueprint-head"><strong>${taskId} · ${esc(title)}</strong><code>${esc(task.tool_name || '')}</code></div><p>${esc(detail)}</p><small>depends on: ${esc((task.depends_on || []).join(' + '))}</small>`;
    planList.appendChild(card);
  });

  const completed = tasks.filter((item) => item.status === 'completed').length;
  planStatus.textContent = plan.status || (result.ok ? 'completed' : 'failed');
  planProgress.textContent = `${completed} / ${tasks.length}`;
  planBadge.textContent = plan.status || 'planned';
  planBadge.className = `badge ${plan.status === 'completed' ? 'completed' : 'neutral'}`;
}

function renderCitations(result) {
  const citations = result.citations || [];
  supportKicker.textContent = 'GROUNDED CITATIONS';
  citationTitle.textContent = `${citations.length} verified`;
  citationList.innerHTML = '';
  if (!citations.length) {
    citationList.innerHTML = '<div class="empty-state">No citations yet.</div>';
    return;
  }
  citations.forEach((item) => {
    const row = document.createElement('article');
    row.className = 'citation-row';
    row.innerHTML = `<div><strong>${esc(item.citation)}</strong><span>${esc(item.publisher)}</span></div><span>${esc(item.title)}</span><code>${esc(item.evidence_id)}</code>`;
    citationList.appendChild(row);
  });
}

function renderQuality(result) {
  const s1 = result.research_synthesis || (result.results || {}).S1 || {};
  const quality = s1.quality || {};
  const rows = quality.evidence_quality || [];
  qualityDetail.innerHTML = `<div class="citation-head"><span class="kicker">S1 · EVIDENCE QUALITY</span><strong>${esc(quality.support_label || '—')} · ${esc(quality.support_score ?? '—')}</strong></div>`;
  if (!rows.length) {
    qualityDetail.innerHTML += '<div class="empty-state">No quality assessment.</div>';
    return;
  }
  rows.forEach((row) => {
    const dims = row.dimensions || {};
    qualityDetail.innerHTML += `<article class="eval-check-card pass"><strong>${esc(row.evidence_id)} · ${esc(row.quality_label)}</strong><span>score ${esc(row.quality_score)}</span><span>authority ${esc(dims.authority)} · freshness ${esc(dims.freshness)} · completeness ${esc(dims.completeness)} · relevance ${esc(dims.relevance)}</span><span>${esc(row.direction)} · ${esc((row.freshness || {}).status)}</span></article>`;
  });
  (quality.relations || []).forEach((rel) => {
    qualityDetail.innerHTML += `<article class="eval-check-card ${rel.relation === 'CONTRADICTION' ? 'fail' : 'pass'}"><strong>${esc(rel.relation)}</strong><span>${esc((rel.evidence_ids || []).join(' ↔ '))}</span><span>${esc(rel.detail)}</span></article>`;
  });
}

function renderDomain(result) {
  const d1 = result.domain_brief || (result.results || {}).D1 || {};
  const sections = d1.sections || {};
  domainDetail.innerHTML = `<div class="citation-head"><span class="kicker">D1 · ${esc(String(d1.domain || '').toUpperCase())} BRIEF</span><strong>${esc(d1.decision_status || '—')}</strong></div>`;
  domainDetail.innerHTML += `<article class="eval-check-card pass"><strong>Executive Summary</strong><span>${esc(sections.executive_summary || d1.answer || '')}</span><span>confidence ${esc(d1.confidence)} · ${esc(d1.confidence_type)}</span></article>`;
  const preferred = d1.domain === 'investment'
    ? ['thesis', 'market_channels', 'base_case', 'upside_inflation_scenario', 'downside_inflation_scenario', 'counterevidence', 'what_would_change_the_view', 'monitoring_signals', 'limitations']
    : ['policy_problem', 'evidence_posture', 'options', 'tradeoffs', 'counterevidence', 'what_would_change_the_view', 'monitoring_signals', 'limitations'];
  preferred.forEach((key) => {
    if (!(key in sections)) return;
    const card = document.createElement('article');
    card.className = 'eval-check-card pass';
    card.innerHTML = `<strong>${esc(key)}</strong><pre><code>${esc(pretty(sections[key]))}</code></pre>`;
    domainDetail.appendChild(card);
  });
}

function renderForecast(pack) {
  if (!pack || pack.artifact_type !== 'forecast_pack') {
    forecastDetail.innerHTML = '<div class="citation-head"><span class="kicker">F1 · FORECAST TRACKER</span><strong>—</strong></div><div class="empty-state">No forecast pack.</div>';
    return;
  }
  const tracker = pack.scenario_tracker || {};
  const score = pack.scoreboard || {};
  forecastDetail.innerHTML = `
    <div class="citation-head"><span class="kicker">F1 · ${esc(pack.pack_id)}</span><strong>${esc(tracker.current_state || '—')}</strong></div>
    <article class="eval-check-card pass">
      <strong>Scoreboard</strong>
      <span>OPEN ${esc(score.open || 0)} · ABSTAINED ${esc(score.abstained || 0)} · RESOLVED ${esc(score.resolved || 0)}</span>
      <span>HIT ${esc(score.hits || 0)} · MISS ${esc(score.misses || 0)} · historical directional accuracy ${esc(score.directional_accuracy ?? '—')}</span>
      <span>${esc(score.accuracy_type || '')}</span>
    </article>`;

  (pack.forecasts || []).forEach((item) => {
    const evaluation = item.evaluation || {};
    const failed = evaluation.outcome === 'MISS' || item.abstain_reason === 'same_claim_contradiction';
    const card = document.createElement('article');
    card.className = `eval-check-card ${failed ? 'fail' : 'pass'}`;
    card.innerHTML = `
      <strong>${esc(item.forecast_id)} · ${esc(item.status)} · ${esc(item.target_evidence_id)}</strong>
      <span>${esc(item.claim)}</span>
      <span>metric ${esc(item.target_metric)} · baseline ${esc(item.baseline_metric_value)} · expected ${esc(item.expected_direction || '—')}</span>
      <span>created ${esc(item.created_at)} · due ${esc(item.due_date)} · horizon ${esc(item.horizon_days)}d</span>
      <span>support ${esc(item.support_score)} · ${esc(item.support_score_type)}</span>
      ${item.abstain_reason ? `<span>abstain: ${esc(item.abstain_reason)}</span>` : ''}
      ${Object.keys(evaluation).length ? `<pre><code>${esc(pretty(evaluation))}</code></pre>` : ''}`;
    forecastDetail.appendChild(card);
  });

  const revision = pack.revision || {};
  forecastDetail.innerHTML += `<article class="eval-check-card ${revision.required ? 'fail' : 'pass'}"><strong>Revision ${revision.required ? 'REQUIRED' : 'not required'}</strong><pre><code>${esc(pretty(revision.reasons || []))}</code></pre></article>`;
  forecastDetail.innerHTML += `<article class="eval-check-card pass"><strong>Scenario History</strong><pre><code>${esc(pretty(tracker.history || []))}</code></pre></article>`;
}

function renderSummary(result, packOverride = null) {
  const trace = result.trace || {};
  const pack = packOverride || result.forecast_pack || result.final_artifact || {};
  evidenceCount.textContent = String((result.evidence || []).length);
  traceKpi.textContent = trace.trace_id ? 'TRACE ✓' : '—';
  evalKpi.textContent = String(result.domain || 'R7').toUpperCase();
  finalResult.textContent = ((pack.scenario_tracker || {}).current_state) || (result.ok ? 'DONE' : 'FAILED');
  modeLabel.textContent = `R7 · ${String(result.domain || '').toUpperCase()}`;
  modeHelp.textContent = 'F1 converts grounded S1/D1 outputs into explicit forecasts that can later be checked and revised.';
  runKicker.textContent = 'R7 PROCESS';
  runTitle.textContent = 'Evidence → S1 → D1 → F1 → Track';
}

function eventMeta(event) {
  if (event.type === 'research_question_received') return ['Research question', 'r7_planner.py', 'Question enters R7; domain is explicit but does not control source selection.'];
  if (event.type === 'decomposition_created') return ['Research decomposition', 'r3_decomposition.py', 'Question becomes semantic source requirements.'];
  if (event.type === 'queries_compiled') return ['Safe query compilation', 'r3_decomposition.py', 'Runtime-owned catalog resolves approved provider/series/tool.'];
  if (event.type === 'domain_lens_selected') return ['Domain lens selected', 'r7_planner.py', 'Investment/Policy changes D1 only.'];
  if (event.type === 'plan_created') return ['R7 DAG created', 'r7_planner.py', 'Queries feed S1, then D1, then F1.'];
  if (event.type === 'evidence_registered') return ['Evidence registered', 'evidence.py', 'Source output becomes grounded Evidence before synthesis.'];
  if (event.type === 'synthesis_verified') return ['Artifact citations verified', 'scheduler.py', 'S1, D1, and F1 must use Evidence IDs already present in EvidenceStore.'];
  if (event.type === 'quality_assessed') return ['S1 Evidence quality', 'r5_quality.py', 'Evidence quality and contradictions are evaluated before forecasting.'];
  if (event.type === 'domain_brief_created') return ['D1 Domain brief', 'r6_domain.py', 'D1 adds decision framing without new facts.'];
  if (event.type === 'forecast_pack_created') return ['F1 Forecast pack', 'r7_forecast.py', 'Forecasts receive baseline, expected direction, horizon, due date, lineage, and invalidation rule.'];
  if (event.type === 'forecast_pack_saved') return ['Forecast pack saved', 'r7_forecast.py', 'The pack survives process restart under .forecasts/.'];
  if (event.type === 'task_started') return [`${event.task_id} started`, event.task_id === 'F1' ? 'r7_forecast.py' : 'scheduler.py', 'Task enters existing Runtime validation/policy/execution.'];
  if (event.type === 'task_completed') return [`${event.task_id} completed`, event.task_id === 'F1' ? 'r7_forecast.py' : 'scheduler.py', 'Task output is recorded in plan state.'];
  if (event.type === 'task_failed') return [`${event.task_id} failed`, 'scheduler.py', 'Failure stays attributable to a concrete task.'];
  if (event.type === 'scheduler_tick') return ['Scheduler tick', 'scheduler.py', 'Dependency-satisfied tasks become READY.'];
  if (event.type === 'plan_completed') return ['R7 completed', 'scheduler.py', 'Final F1 artifact is returned with citations to original Evidence.'];
  if (event.type === 'task_runtime_event') return [`${event.task_id} · ${(event.event || {}).type}`, 'agent.py', 'Runtime still owns validation, policy, retry, and execution.'];
  return [event.type, 'serve_visualizer.py', 'R7 event.'];
}

function buildRunSteps(result) {
  return (result.events || []).filter(meaningful).map((event) => ({type: 'run', event}));
}

function buildEvalSteps(suite) {
  const rows = [];
  (suite.cases || []).forEach((entry) => {
    (entry.process || []).forEach((event) => rows.push({type: 'eval', event, entry}));
  });
  return rows;
}

function renderTimeline(items, activeIndex) {
  timeline.innerHTML = '';
  items.forEach((item, index) => {
    const event = item.event;
    const label = item.type === 'eval'
      ? (event.type === 'eval_check' ? `${event.passed ? '✓' : '✕'} ${event.label}` : `${event.case_id} · ${event.type}`)
      : eventMeta(event)[0];
    const li = document.createElement('li');
    li.className = index === activeIndex ? 'running' : index < activeIndex ? 'completed' : '';
    li.innerHTML = `<div class="timeline-index">${index + 1}</div><div><strong>${esc(label)}</strong><span>${esc(event.task_id || event.case_id || event.type)}</span></div>`;
    timeline.appendChild(li);
  });
}

function showStep(index) {
  if (!stepItems.length) return;
  stepIndex = Math.max(0, Math.min(index, stepItems.length - 1));
  const item = stepItems[stepIndex];
  const event = item.event;
  renderTimeline(stepItems, stepIndex);
  eventCounter.textContent = `${stepIndex + 1} / ${stepItems.length}`;

  if (item.type === 'eval') {
    const label = event.type === 'eval_check' ? event.label : `${event.case_id} · ${event.type}`;
    currentAction.innerHTML = `<strong>${esc(label)}</strong><span>${event.type === 'eval_check' ? esc(event.passed ? 'Actual satisfies expected contract.' : event.failure) : 'R7 eval process event.'}</span>`;
    codeTitle.textContent = label;
    codeFile.textContent = 'r7_evals.py';
    codePanel.textContent = pretty(event);
    explainBody.innerHTML = event.type === 'eval_check'
      ? `<p><strong>${event.passed ? 'PASS' : 'FAIL'}</strong> · Actual=${esc(pretty(event.actual))} · Expected=${esc(pretty(event.expected))}</p>`
      : '<p>Eval keeps expected contracts separate from the research run being judged.</p>';
    rawEvent.textContent = pretty(event);
    return;
  }

  const [label, file, explanation] = eventMeta(event);
  currentAction.innerHTML = `<strong>${esc(label)}</strong><span>${esc(explanation)}</span>`;
  codeTitle.textContent = label;
  codeFile.textContent = file;
  codePanel.textContent = pretty(event);
  explainBody.innerHTML = `<p>${esc(explanation)}</p>`;
  rawEvent.textContent = pretty(event);
}

function renderFailure(result) {
  const error = result.error || {};
  planStatus.textContent = 'failed';
  planBadge.textContent = 'FAILED';
  finalResult.textContent = 'FAILED';
  citationTitle.textContent = error.provider || result.stage || 'ERROR';
  citationList.innerHTML = `<article class="eval-check-card fail"><strong>${esc(error.task_id || error.code || 'error')}</strong><span>${esc(error.message || pretty(error))}</span>${error.missing_env ? `<span>Missing: ${esc(error.missing_env.join(', '))}</span>` : ''}</article>`;
}

function renderRun(result, packOverride = null) {
  mode = 'run';
  renderPlan(result);
  renderSummary(result, packOverride);
  renderCitations(result);
  renderQuality(result);
  renderDomain(result);
  renderForecast(packOverride || result.forecast_pack || result.final_artifact);
  runtimeDetail.textContent = pretty({blueprint: result.blueprint, results: result.results, forecast_pack: packOverride || result.forecast_pack});
  traceDetail.textContent = pretty(result.trace || {});
  evalDetail.textContent = '{}';
  if (!result.ok) renderFailure(result);
  stepItems = buildRunSteps(result);
  if (stepItems.length) showStep(0);
}

function renderEval(payload) {
  mode = 'eval';
  const suite = payload.eval_suite || {};
  const result = payload.research_result || {};
  renderSummary(result);
  renderCitations(result);
  renderQuality(result);
  renderDomain(result);
  renderForecast(result.forecast_pack || result.final_artifact);
  leftKicker.textContent = 'R7 EVALS';
  leftTitle.textContent = 'Blueprint · S1 · D1 · F1';
  legend.style.display = 'none';
  dagHint.innerHTML = '<span>Research</span><span>→</span><span>Domain</span><span>→</span><span>Forecast</span><span>→</span><span>Verdict</span>';
  planList.innerHTML = '';
  (suite.cases || []).forEach((entry) => {
    const report = entry.report || {};
    const checks = report.checks || [];
    const card = document.createElement('article');
    card.className = `task-card ${report.passed ? 'completed' : 'failed'}`;
    card.innerHTML = `<div class="task-head"><span class="task-id">R7</span><span class="status-chip ${report.passed ? 'completed' : 'failed'}">${report.passed ? 'PASS' : 'FAIL'}</span></div><strong>${esc(entry.case.case_id)}</strong><small>${checks.filter((c) => c.passed).length}/${checks.length} checks</small>`;
    planList.appendChild(card);
  });
  planStatus.textContent = 'r7 evals';
  planProgress.textContent = `${suite.passed || 0} / ${suite.total || 0}`;
  planBadge.textContent = suite.passed === suite.total ? 'PASS' : 'FAIL';
  planBadge.className = `badge ${suite.passed === suite.total ? 'completed' : 'neutral'}`;
  evalKpi.textContent = `${Math.round((suite.pass_rate || 0) * 100)}%`;
  evalDetail.textContent = pretty(suite);
  runtimeDetail.textContent = pretty(result);
  traceDetail.textContent = pretty(result.trace || {});
  stepItems = buildEvalSteps(suite);
  if (stepItems.length) showStep(0);
}

function stopAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  autoButton.textContent = '自动';
}

prevButton.addEventListener('click', () => { stopAuto(); showStep(stepIndex - 1); });
nextButton.addEventListener('click', () => { stopAuto(); showStep(stepIndex + 1); });
autoButton.addEventListener('click', () => {
  if (autoTimer) { stopAuto(); return; }
  autoButton.textContent = '停止';
  autoTimer = setInterval(() => {
    if (stepIndex >= stepItems.length - 1) { stopAuto(); return; }
    showStep(stepIndex + 1);
  }, 900);
});
resetButton.addEventListener('click', () => {
  stopAuto();
  stepIndex = -1;
  stepItems = [];
  timeline.innerHTML = '<li class="empty-state">等待新的 R7 run / eval。</li>';
  eventCounter.textContent = '尚未运行';
  currentAction.innerHTML = '<strong>等待运行</strong><span>Forecast 必须可结算；允许 ABSTAIN。</span>';
  rawEvent.textContent = '{}';
});

runButton.addEventListener('click', async () => {
  stopAuto();
  runButton.disabled = true;
  const original = runButton.textContent;
  runButton.textContent = '运行中…';
  try {
    const result = await post({
      action: 'r7_run',
      goal: goalInput.value,
      domain: domainInput.value,
      context_preset: contextPreset.value,
    });
    renderRun(result);
    const packId = (result.forecast_pack || {}).pack_id;
    await loadForecastPacks(packId);
  } catch (error) {
    renderFailure({error: {code: 'frontend_error', message: error.message}});
  } finally {
    runButton.disabled = false;
    runButton.textContent = original;
  }
});

evalButton.addEventListener('click', async () => {
  stopAuto();
  evalButton.disabled = true;
  const original = evalButton.textContent;
  evalButton.textContent = '评测中…';
  try {
    const payload = await post({
      action: 'r7_evals',
      goal: goalInput.value,
      domain: domainInput.value,
      context_preset: contextPreset.value,
    });
    renderEval(payload);
  } catch (error) {
    renderFailure({error: {code: 'frontend_error', message: error.message}});
  } finally {
    evalButton.disabled = false;
    evalButton.textContent = original;
  }
});

checkForecastButton.addEventListener('click', async () => {
  stopAuto();
  const packId = forecastPackInput.value;
  if (!packId) {
    currentAction.innerHTML = '<strong>没有 Forecast Pack</strong><span>先运行 R7 研究，或从 Saved Forecast 选择一个历史 pack。</span>';
    return;
  }
  checkForecastButton.disabled = true;
  const original = checkForecastButton.textContent;
  checkForecastButton.textContent = '检查中…';
  try {
    const payload = await post({
      action: 'r7_check',
      pack_id: packId,
      context_preset: contextPreset.value,
    });
    if (!payload.ok) {
      const result = payload.research_result || {error: payload.error || {code: 'check_failed', message: 'Forecast check failed'}};
      renderFailure(result);
      return;
    }
    const result = payload.research_result || {};
    renderRun(result, payload.forecast_pack);
    modeLabel.textContent = 'R7 · FORECAST CHECK';
    modeHelp.textContent = 'Saved forecast is checked against a fresh grounded S1; forecasts remain pending until due and a newer observation exists.';
    currentAction.innerHTML = `<strong>${esc(packId)} checked</strong><span>${esc((payload.forecast_pack || {}).answer || '')}</span>`;
    await loadForecastPacks(packId);
  } catch (error) {
    renderFailure({error: {code: 'frontend_error', message: error.message}});
  } finally {
    checkForecastButton.disabled = false;
    checkForecastButton.textContent = original;
  }
});

loadForecastPacks();
