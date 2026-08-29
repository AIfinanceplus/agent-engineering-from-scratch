const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const pretty = (value) => JSON.stringify(value, null, 2);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

const state = {
  result: null,
  suite: null,
  pack: null,
  packs: [],
  selectedStep: 'Q',
  logicTab: 'code',
  evidenceTab: 'evidence',
};

const el = {
  goal: $('#goal'), domain: $('#domain'), context: $('#context-preset'), packSelect: $('#forecast-pack'),
  run: $('#run-btn'), health: $('#health-btn'), eval: $('#eval-btn'), check: $('#check-forecast-btn'), export: $('#export-btn'),
  healthRefresh: $('#health-refresh'), healthList: $('#health-list'), healthChecked: $('#health-checked'), systemStatus: $('#system-status-text'),
  runStatus: $('#run-status-pill'), runId: $('#run-id'), runProgress: $('#run-progress'), flow: $('#agent-flow'),
  traceList: $('#trace-list'), eventCount: $('#event-count'), selectedStep: $('#selected-step'), logicCode: $('#logic-code'), logicNote: $('#logic-note'),
  evidenceContent: $('#evidence-content'), evidenceKpi: $('#evidence-kpi'),
  outputBody: $('#output-body'), outputStage: $('#output-stage'), outputProgressBar: $('#output-progress-bar'),
  visibleQuestion: $('#visible-question'), visibleConfig: $('#visible-config'),
  evalGrid: $('#eval-grid'), evalSummary: $('#eval-summary'), forecastBody: $('#forecast-table-body'),
  trackingRunId: $('#tracking-run-id'), trackingScenario: $('#tracking-scenario'), trackingEvidence: $('#tracking-evidence'), trackingForecasts: $('#tracking-forecasts'),
  refreshPacks: $('#refresh-packs'), copyOutput: $('#copy-output'), toast: $('#toast'),
  quickRerun: $('#quick-rerun'), quickEval: $('#quick-eval'), quickCheck: $('#quick-check'), quickExport: $('#quick-export'),
};

const STEP_META = {
  Q: {
    title: 'Question', file: 'serve_visualizer.py',
    why: '研究问题是整个 run 的不可变入口。这里记录问题、Domain Lens 与 ExecutionContext，但 Domain 不获得数据源选择权。',
    code: `question = request_data["goal"]\ndomain = request_data["domain"]\nexecution_context = CONTEXT_PRESETS[preset]\n# Question is input; Runtime still owns execution authority.`,
    payload: (r) => ({question: r?.question, domain: r?.domain, execution_context: r?.execution_context}),
  },
  DEC: {
    title: 'Decomposition', file: 'r3_decomposition.py',
    why: 'Decomposer 只决定“需要知道什么”，把研究问题拆成语义子问题；它不能发 URL、API key 或任意 series ID。',
    code: `subquestions = ResearchDecomposer().decompose(question)\n# WHAT to know, not HOW to fetch it.`,
    payload: (r) => ({subquestions: r?.blueprint?.subquestions, intents: r?.blueprint?.intents}),
  },
  QC: {
    title: 'Query Compiler', file: 'r3_decomposition.py',
    why: 'QueryCompiler 是可信边界：把 approved capability 映射到 provider / series / Tool，并把 credentials 留在 Runtime。',
    code: `queries = QueryCompiler().compile(subquestions)\n# capability -> approved provider / series / tool\n# no secret, raw URL, or arbitrary source authority`,
    payload: (r) => ({queries: r?.blueprint?.queries}),
  },
  QN: {
    title: 'Q1..Qn', file: 'scheduler.py + agent.py',
    why: 'Scheduler 只运行依赖已满足的任务；每个 source task 仍进入 Tool validation → Policy → Retry → execution。',
    code: `ready = scheduler.ready_tasks(plan)\nfor task in ready:\n    Runtime.validate(task)\n    Policy.check(context, tool)\n    result = Runtime.execute(tool, args)`,
    payload: (r) => ({source_tasks: (r?.plan?.tasks || []).filter((t) => String(t.task_id || '').startsWith('Q'))}),
  },
  E: {
    title: 'Evidence', file: 'evidence.py',
    why: 'Source output 不能直接变成答案。先标准化成 Evidence，并保留 source / as_of / history / provenance，后续 Citation 才可验证。',
    code: `evidence = normalize(source_result)\nEvidenceStore.register(evidence)\n# Tool Result != Evidence != Synthesis != Citation`,
    payload: (r) => ({evidence: r?.evidence, citations: r?.citations}),
  },
  S1: {
    title: 'S1 Research Synthesis', file: 'r3_synthesis.py + r5_quality.py',
    why: 'S1 先判断 Evidence 支持什么：authority、freshness、completeness、relevance，以及 AGREEMENT / MIXED_SIGNAL / CONTRADICTION。',
    code: `quality = assess_evidence_quality(evidence_bundle, signals, reference_date)\nS1 = synthesize_research_bundle(question, evidence_bundle, reference_date)\n# support score is heuristic, not probability`,
    payload: (r) => r?.research_synthesis || r?.results?.S1 || {},
  },
  D1: {
    title: 'D1 Domain Brief', file: 'r6_domain.py',
    why: 'D1 只改变决策框架，不允许重新抓数据、增加 Evidence ID 或抬高 confidence。Investment / Policy 的数据 lineage 完全一致。',
    code: `D1 = synthesize_domain_brief(\n  question, domain, research_synthesis=S1\n)\nassert D1.evidence_ids == S1.evidence_ids\nassert D1.confidence <= S1.confidence`,
    payload: (r) => r?.domain_brief || r?.results?.D1 || {},
  },
  F1: {
    title: 'F1 Forecast Pack', file: 'r7_forecast.py',
    why: 'Forecast 不是观点装饰，而是可结算 contract：baseline、方向、horizon、due date、Evidence lineage、invalidation rule。无法可靠预测时允许 ABSTAIN。',
    code: `F1 = build_forecast_pack(S1, D1, reference_date)\n# OPEN / ABSTAINED -> later PENDING / HIT / MISS / REVISE\nForecastStore.save(F1)`,
    payload: (r) => r?.forecast_pack || r?.results?.F1 || {},
  },
  EV: {
    title: 'Eval / Tracking', file: 'r7_evals.py',
    why: 'Eval 判断系统是否遵守合同；Tracking 则让旧 Forecast 等待真正的新 observation 后再结算，避免提前或用旧数据假结算。',
    code: `suite = make_r7_eval_suite(blueprint, result, domain)\nupdated = evaluate_forecast_pack(old_pack, fresh_S1, today)\n# due date + newer observation are both required for resolution`,
    payload: () => ({eval_suite: state.suite, forecast_pack: state.pack}),
  },
};

async function post(payload) {
  const response = await fetch('/api/run', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : `HTTP ${response.status}`);
  return data;
}

function toast(message, kind = 'ok') {
  el.toast.textContent = message;
  el.toast.className = `toast show${kind === 'error' ? ' error' : ''}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.toast.className = 'toast'; }, 2400);
}

function pill(status) {
  const s = String(status || '—').toLowerCase();
  let cls = 'neutral';
  if (['ready','pass','hit','completed','success'].some((x) => s.includes(x))) cls = 'pass';
  else if (['running','open','pending_not_due','awaiting'].some((x) => s.includes(x))) cls = 'running';
  else if (['abstain','pending'].some((x) => s.includes(x))) cls = 'pending';
  else if (['fail','miss','error','rate_limited','invalid'].some((x) => s.includes(x))) cls = 'fail';
  return `<span class="pill ${cls}">${esc(status || '—')}</span>`;
}

function setBusy(button, busy, text = null) {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.textContent;
    button.disabled = true;
    button.textContent = text || '运行中…';
  } else {
    button.disabled = false;
    button.textContent = button.dataset.label || button.textContent;
  }
}

function currentConfig() {
  return {goal: el.goal.value.trim(), domain: el.domain.value, context_preset: el.context.value};
}

async function loadForecastPacks(preferId = null) {
  try {
    const payload = await post({action: 'r7_packs'});
    state.packs = payload.packs || [];
    const before = preferId || el.packSelect.value;
    el.packSelect.innerHTML = '<option value="">none</option>';
    state.packs.forEach((pack) => {
      const option = document.createElement('option');
      option.value = pack.pack_id;
      option.textContent = `${pack.pack_id} · ${pack.created_at || '—'} · ${pack.scenario || '—'}`;
      el.packSelect.appendChild(option);
    });
    if (before && state.packs.some((p) => p.pack_id === before)) el.packSelect.value = before;
    else if (state.packs.length) el.packSelect.value = state.packs[0].pack_id;
  } catch (error) {
    console.warn('forecast pack list failed', error);
  }
}

function meaningfulEvents(result) {
  return (result?.events || []).filter((event) => event && event.type);
}

function eventLabel(event) {
  const type = event.type || 'event';
  const nested = event.event || {};
  if (type === 'task_runtime_event') return `${event.task_id || 'task'} · ${nested.type || 'runtime'}`;
  const map = {
    research_question_received: 'Research question received', decomposition_created: 'Decomposition completed',
    queries_compiled: 'Queries compiled', domain_lens_selected: 'Domain lens selected', plan_created: 'Plan created',
    scheduler_tick: 'Scheduler tick', task_started: `${event.task_id || 'Task'} started`, task_completed: `${event.task_id || 'Task'} completed`,
    task_failed: `${event.task_id || 'Task'} failed`, evidence_registered: 'Evidence registered', synthesis_verified: 'Citation lineage verified',
    quality_assessed: 'Evidence quality assessed', domain_brief_created: 'D1 Domain Brief created', forecast_pack_created: 'F1 Forecast Pack created',
    forecast_pack_saved: 'Forecast Pack saved', plan_completed: 'Plan completed', plan_failed: 'Plan failed',
  };
  return map[type] || type.replaceAll('_', ' ');
}

function eventLevel(event) {
  if (String(event.type).includes('failed')) return ['FAIL', 'fail'];
  if (['task_completed','plan_completed','evidence_registered','synthesis_verified','forecast_pack_saved'].includes(event.type)) return ['SUCCESS', 'success'];
  if (event.type === 'task_runtime_event') return ['RUNTIME', ''];
  return ['INFO', ''];
}

function renderTrace(result) {
  const events = meaningfulEvents(result);
  el.eventCount.textContent = `${events.length} events`;
  if (!events.length) {
    el.traceList.innerHTML = '<div class="empty">没有运行事件。</div>';
    return;
  }
  el.traceList.innerHTML = events.map((event, index) => {
    const [level, cls] = eventLevel(event);
    const time = event.timestamp || event.time || `#${String(index + 1).padStart(2, '0')}`;
    return `<div class="trace-row"><span class="trace-time">${esc(time)}</span><span class="trace-badge ${cls}">${level}</span><span class="trace-text">${esc(eventLabel(event))}</span></div>`;
  }).join('');
}

function taskStatus(result, taskId) {
  const tasks = result?.plan?.tasks || [];
  const task = tasks.find((item) => item.task_id === taskId);
  return task?.status || null;
}

function setNode(node, status, detail) {
  node.classList.remove('done', 'active', 'failed');
  const statusEl = node.querySelector('.flow-status');
  if (status === 'completed') { node.classList.add('done'); statusEl.innerHTML = `<strong>✓ ${esc(detail || '完成')}</strong>`; }
  else if (status === 'running') { node.classList.add('active'); statusEl.textContent = detail || '运行中'; }
  else if (status === 'failed') { node.classList.add('failed'); statusEl.textContent = detail || '失败'; }
  else statusEl.textContent = detail || '待处理';
}

function renderFlow(result, evalMode = false) {
  const nodes = Object.fromEntries($$('.flow-node').map((n) => [n.dataset.step, n]));
  const blueprint = result?.blueprint || {};
  const queryTasks = (result?.plan?.tasks || []).filter((t) => String(t.task_id || '').startsWith('Q'));
  const hasQuestion = Boolean(result?.question || result?.events?.length);
  setNode(nodes.Q, hasQuestion ? 'completed' : null, hasQuestion ? '已接收' : null);
  setNode(nodes.DEC, blueprint.subquestions?.length ? 'completed' : null, blueprint.subquestions?.length ? `${blueprint.subquestions.length} 子问题` : null);
  setNode(nodes.QC, blueprint.queries?.length ? 'completed' : null, blueprint.queries?.length ? `${blueprint.queries.length} Queries` : null);
  const qCompleted = queryTasks.filter((t) => t.status === 'completed').length;
  const qFailed = queryTasks.some((t) => t.status === 'failed');
  setNode(nodes.QN, qFailed ? 'failed' : qCompleted === queryTasks.length && queryTasks.length ? 'completed' : queryTasks.some((t) => t.status === 'running') ? 'running' : null, queryTasks.length ? `${qCompleted}/${queryTasks.length}` : null);
  setNode(nodes.E, result?.evidence?.length ? 'completed' : null, result?.evidence?.length ? `${result.evidence.length} Evidence` : null);
  ['S1','D1','F1'].forEach((id) => setNode(nodes[id], taskStatus(result, id), taskStatus(result, id) || null));
  setNode(nodes.EV, evalMode && state.suite ? (state.suite.pass_rate === 1 ? 'completed' : 'failed') : state.pack ? 'completed' : null, evalMode && state.suite ? `${state.suite.passed}/${state.suite.total} PASS` : state.pack ? 'Tracking ready' : null);

  const tasks = result?.plan?.tasks || [];
  const complete = tasks.filter((t) => t.status === 'completed').length;
  el.runProgress.textContent = `${complete} / ${tasks.length || 0}`;
  el.runId.textContent = result?.execution_context?.trace_id ? `Trace ${result.execution_context.trace_id}` : `Run ${result?.reference_date || '—'}`;
  const status = result?.ok === false ? 'FAILED' : result?.ok ? 'COMPLETED' : 'IDLE';
  el.runStatus.textContent = status;
  el.runStatus.className = `pill ${status === 'COMPLETED' ? 'pass' : status === 'FAILED' ? 'fail' : 'neutral'}`;
}

function renderVisibleInput(result = null) {
  el.visibleQuestion.textContent = result?.question || el.goal.value.trim() || '—';
  el.visibleConfig.textContent = `Domain: ${result?.domain || el.domain.value}\nIdentity: ${el.context.value}\nSaved Forecast: ${el.packSelect.value || 'none'}`;
}

function renderOutput(result, packOverride = null, checkMode = false) {
  const s1 = result?.research_synthesis || result?.results?.S1 || {};
  const d1 = result?.domain_brief || result?.results?.D1 || {};
  const pack = packOverride || result?.forecast_pack || result?.results?.F1 || {};
  const scenario = pack?.scenario_tracker?.current_state;
  const score = pack?.scoreboard || {};
  const sections = d1?.sections || {};
  const progress = result?.ok ? 100 : result ? 40 : 0;
  el.outputProgressBar.style.width = `${progress}%`;
  el.outputStage.textContent = checkMode ? `Forecast Check · ${scenario || '—'}` : pack?.artifact_type === 'forecast_pack' ? `F1 Forecast Pack · ${scenario || '—'}` : d1?.domain ? 'D1 Domain Brief' : s1?.answer ? 'S1 Research Synthesis' : '等待研究';
  if (!result) return;
  const limitations = d1?.upstream?.limitations || s1?.limitations || [];
  el.outputBody.innerHTML = `
    <div class="output-stage"><strong>${esc(el.outputStage.textContent)}</strong><div class="output-progress"><i style="width:${progress}%"></i></div></div>
    <div class="output-section"><h4>综合答案 / Executive Summary</h4><p>${esc(d1?.answer || s1?.answer || '尚无综合答案。')}</p></div>
    ${sections.thesis ? `<div class="output-section"><h4>投资 Thesis</h4><p>${esc(sections.thesis)}</p></div>` : ''}
    ${sections.policy_problem ? `<div class="output-section"><h4>Policy Problem</h4><p>${esc(sections.policy_problem)}</p></div>` : ''}
    <div class="output-section"><h4>结构化状态</h4><ul>
      <li>S1 support: ${esc(s1?.confidence ?? '—')} · ${esc(s1?.confidence_type || '—')}</li>
      <li>D1 decision: ${esc(d1?.decision_status || '—')} · domain=${esc(d1?.domain || result.domain || '—')}</li>
      <li>F1 scenario: ${esc(scenario || '—')} · OPEN=${esc(score.open || 0)} · ABSTAINED=${esc(score.abstained || 0)} · RESOLVED=${esc(score.resolved || 0)}</li>
      <li>Citations: ${esc((result?.citations || []).length)} verified · Evidence: ${esc((result?.evidence || []).length)}</li>
    </ul></div>
    ${limitations.length ? `<div class="output-section"><h4>Limitations</h4><ul>${limitations.slice(0,4).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
    <div class="final-card"><strong>Final Result</strong><pre>${esc(pretty({scenario, decision_status: d1?.decision_status, confidence: d1?.confidence, scoreboard: score, revision: pack?.revision}))}</pre></div>`;
}

function renderEvidence(result) {
  const evidence = result?.evidence || [];
  const citations = result?.citations || [];
  const quality = result?.research_synthesis?.quality || result?.results?.S1?.quality || {};
  el.evidenceKpi.textContent = `${evidence.length} Evidence`;
  if (state.evidenceTab === 'citations') {
    el.evidenceContent.innerHTML = citations.length ? `<div class="evidence-list">${citations.map((c) => `<div class="evidence-card"><div class="evidence-card-head"><strong>${esc(c.citation || c.evidence_id)}</strong>${pill('VERIFIED')}</div><small>${esc(c.publisher || '')} · ${esc(c.title || '')}</small><small>${esc(c.evidence_id)}</small></div>`).join('')}</div>` : '<div class="empty">暂无 Citation。</div>';
    return;
  }
  if (state.evidenceTab === 'quality') {
    const rows = quality.evidence_quality || [];
    const relations = quality.relations || [];
    el.evidenceContent.innerHTML = rows.length ? `<div class="quality-bars">${rows.map((row) => {
      const score = Number(row.quality_score || 0);
      return `<div class="quality-row"><span>${esc(row.evidence_id)}</span><span class="bar ${score < .65 ? 'amber' : ''}"><i style="width:${Math.round(score*100)}%"></i></span><strong>${esc(row.quality_score)}</strong></div>`;
    }).join('')}</div><div class="evidence-list" style="margin-top:10px">${relations.map((rel) => `<div class="evidence-card"><div class="evidence-card-head"><strong>${esc(rel.relation)}</strong>${pill(rel.relation === 'CONTRADICTION' ? 'WARNING' : 'OK')}</div><small>${esc(rel.detail || '')}</small></div>`).join('')}</div>` : '<div class="empty">暂无 Quality assessment。</div>';
    return;
  }
  const qRows = quality.evidence_quality || [];
  const qById = Object.fromEntries(qRows.map((q) => [q.evidence_id, q]));
  const high = qRows.filter((q) => q.quality_label === 'HIGH').length;
  const medium = qRows.filter((q) => q.quality_label === 'MEDIUM').length;
  const low = qRows.filter((q) => q.quality_label === 'LOW').length;
  el.evidenceContent.innerHTML = `
    <div class="evidence-summary">
      <div class="evidence-stat"><strong>${evidence.length}</strong><span>总证据</span></div>
      <div class="evidence-stat"><strong>${citations.length}</strong><span>Verified</span></div>
      <div class="evidence-stat"><strong>${high}</strong><span>高质量</span></div>
      <div class="evidence-stat"><strong>${medium}</strong><span>中等</span></div>
      <div class="evidence-stat"><strong>${low}</strong><span>低质量</span></div>
    </div>
    ${evidence.length ? `<div class="evidence-list">${evidence.map((item) => {
      const q = qById[item.evidence_id] || {};
      return `<div class="evidence-card"><div class="evidence-card-head"><strong>${esc(item.claim || item.evidence_id)}</strong>${pill(q.quality_label || 'EVIDENCE')}</div><small>${esc(item.provider || item.source?.publisher || '')} · as_of ${esc(item.as_of || '—')} · ${esc(item.unit || '')}</small><small>${esc(item.evidence_id)} · value ${esc(item.value)}</small></div>`;
    }).join('')}</div>` : '<div class="empty">暂无 Evidence。</div>'}`;
}

function renderForecastTable(pack) {
  const rows = pack?.forecasts || [];
  el.trackingScenario.textContent = pack?.scenario_tracker?.current_state || '—';
  el.trackingForecasts.textContent = String(rows.length);
  if (!rows.length) {
    el.forecastBody.innerHTML = '<tr><td colspan="6" class="empty">暂无 Forecast。</td></tr>';
    return;
  }
  el.forecastBody.innerHTML = rows.map((item) => {
    const ev = item.evaluation || {};
    return `<tr><td>${esc(item.forecast_id)}</td><td>${esc(item.target_evidence_id)}</td><td>${esc(item.expected_direction || 'ABSTAIN')}</td><td>${esc(item.due_date || '—')}</td><td>${pill(item.status)}</td><td>${pill(ev.outcome || ev.status || '—')}</td></tr>`;
  }).join('');
}

function renderEval(suite) {
  state.suite = suite || null;
  if (!suite) {
    el.evalSummary.textContent = '未运行'; el.evalSummary.className = 'pill neutral';
    el.evalGrid.innerHTML = ['Query / Blueprint Contract','Evidence Lineage','Domain Discipline','Forecast Verifiability'].map((x) => `<div class="eval-item"><span>${x}</span><span class="pill neutral">—</span></div>`).join('');
    return;
  }
  el.evalSummary.textContent = `${suite.passed}/${suite.total} PASS`;
  el.evalSummary.className = `pill ${suite.pass_rate === 1 ? 'pass' : 'fail'}`;
  el.evalGrid.innerHTML = (suite.cases || []).map((entry) => {
    const report = entry.report || {};
    const failed = (report.checks || []).filter((x) => !x.passed).length;
    return `<div class="eval-item"><span>${esc(report.case_id || entry.case?.case_id || 'Eval')}</span>${pill(report.passed ? 'PASS' : `FAIL ${failed}`)}</div>`;
  }).join('');
}

function renderTracking(result, pack) {
  el.trackingRunId.textContent = result?.execution_context?.trace_id || result?.reference_date || '—';
  el.trackingScenario.textContent = pack?.scenario_tracker?.current_state || '—';
  el.trackingEvidence.textContent = String((result?.evidence || []).length);
  el.trackingForecasts.textContent = String((pack?.forecasts || []).length);
}

function renderLogic() {
  const meta = STEP_META[state.selectedStep] || STEP_META.Q;
  el.selectedStep.textContent = meta.title;
  const payload = meta.payload(state.result || {});
  if (state.logicTab === 'payload') el.logicCode.textContent = pretty(payload);
  else el.logicCode.textContent = `# ${meta.file}\n\n${meta.code}`;
  el.logicNote.innerHTML = `<strong>为什么：</strong>${esc(meta.why)}<br><strong>组件：</strong>${esc(meta.file)}`;
  $$('.flow-node').forEach((node) => node.classList.toggle('active', node.dataset.step === state.selectedStep));
}

function renderAll(result, packOverride = null, options = {}) {
  state.result = result;
  state.pack = packOverride || result?.forecast_pack || result?.results?.F1 || null;
  renderVisibleInput(result);
  renderFlow(result, Boolean(options.evalMode));
  renderTrace(result);
  renderEvidence(result);
  renderOutput(result, state.pack, Boolean(options.checkMode));
  renderForecastTable(state.pack);
  renderTracking(result, state.pack);
  renderLogic();
  if (!options.evalMode) renderEval(null);
}

function renderFailure(result) {
  const err = result?.error || {};
  const message = err.message || (typeof err === 'string' ? err : pretty(err));
  el.runStatus.textContent = 'FAILED'; el.runStatus.className = 'pill fail';
  el.outputBody.innerHTML = `<div class="output-section"><h4>运行失败</h4><p>${esc(message)}</p></div><div class="final-card"><strong>${esc(err.code || result?.stage || 'ERROR')}</strong><pre>${esc(pretty(err))}</pre></div>`;
}

async function runResearch() {
  const cfg = currentConfig();
  if (!cfg.goal) return toast('请输入研究问题', 'error');
  setBusy(el.run, true, '运行中…');
  el.runStatus.textContent = 'RUNNING'; el.runStatus.className = 'pill running';
  $$('.flow-node').forEach((n) => n.classList.add('loading-shimmer'));
  renderVisibleInput();
  try {
    const result = await post({action: 'r7_run', ...cfg});
    $$('.flow-node').forEach((n) => n.classList.remove('loading-shimmer'));
    renderAll(result);
    if (!result.ok) renderFailure(result);
    else {
      await loadForecastPacks(result.forecast_pack?.pack_id);
      toast('R7 研究完成，Forecast Pack 已保存');
    }
  } catch (error) {
    $$('.flow-node').forEach((n) => n.classList.remove('loading-shimmer'));
    toast(error.message, 'error');
  } finally { setBusy(el.run, false); }
}

async function runEvals() {
  const cfg = currentConfig();
  if (!cfg.goal) return toast('请输入研究问题', 'error');
  setBusy(el.eval, true, '评估中…');
  try {
    const payload = await post({action: 'r7_evals', ...cfg});
    const result = payload.research_result || {};
    renderAll(result, result.forecast_pack || result.results?.F1, {evalMode: true});
    renderEval(payload.eval_suite || {});
    state.selectedStep = 'EV'; renderLogic();
    if (!result.ok) renderFailure(result);
    else toast(`Evals: ${(payload.eval_suite || {}).passed || 0}/${(payload.eval_suite || {}).total || 0} PASS`);
  } catch (error) { toast(error.message, 'error'); }
  finally { setBusy(el.eval, false); }
}

async function checkForecast() {
  const packId = el.packSelect.value;
  if (!packId) return toast('请选择 Saved Forecast', 'error');
  setBusy(el.check, true, '检查中…');
  try {
    const payload = await post({action: 'r7_check', pack_id: packId, context_preset: el.context.value});
    const result = payload.research_result || {};
    if (!payload.ok) {
      renderAll(result || {}, payload.forecast_pack || null, {checkMode: true});
      renderFailure(payload);
      return toast(payload.error?.message || 'Forecast check failed', 'error');
    }
    renderAll(result, payload.forecast_pack, {checkMode: true});
    state.selectedStep = 'EV'; renderLogic();
    await loadForecastPacks(packId);
    toast('Forecast 已用最新 grounded Evidence 检查');
  } catch (error) { toast(error.message, 'error'); }
  finally { setBusy(el.check, false); }
}

async function runHealth() {
  setBusy(el.health, true, '检查中…');
  if (el.healthRefresh) setBusy(el.healthRefresh, true, '…');
  try {
    const payload = await post({action: 'source_health'});
    const report = payload.source_health || {};
    const rows = report.results || [];
    el.healthList.innerHTML = rows.map((row) => `<div class="health-row"><span class="health-name">${esc(row.provider)}</span><span class="health-meta">${esc(row.latency_ms ?? '—')} ms</span>${pill(row.status)}</div>`).join('') || '<div class="empty">无 health result。</div>';
    el.healthChecked.textContent = `checked ${report.checked_at || 'now'} · ${report.ready_count || 0}/${report.total || 0} READY`;
    el.systemStatus.textContent = report.ready ? 'ALL SYSTEMS OPERATIONAL' : 'SOURCE DEGRADED';
    toast(report.ready ? '数据源全部 READY' : '部分数据源需要处理', report.ready ? 'ok' : 'error');
  } catch (error) { el.systemStatus.textContent = 'HEALTH CHECK FAILED'; toast(error.message, 'error'); }
  finally { setBusy(el.health, false); if (el.healthRefresh) setBusy(el.healthRefresh, false); }
}

function exportJson() {
  if (!state.result && !state.pack && !state.suite) return toast('当前没有可导出的结果', 'error');
  const blob = new Blob([pretty({research_result: state.result, forecast_pack: state.pack, eval_suite: state.suite})], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `agent-research-${Date.now()}.json`; a.click();
  URL.revokeObjectURL(url); toast('JSON 已导出');
}

async function copyOutput() {
  const text = el.outputBody.innerText.trim();
  if (!text) return toast('当前没有输出', 'error');
  try { await navigator.clipboard.writeText(text); toast('输出已复制'); }
  catch { toast('浏览器未允许复制', 'error'); }
}

$$('.flow-node').forEach((node) => node.addEventListener('click', () => { state.selectedStep = node.dataset.step; renderLogic(); }));
$$('[data-logic-tab]').forEach((tab) => tab.addEventListener('click', () => {
  state.logicTab = tab.dataset.logicTab;
  $$('[data-logic-tab]').forEach((x) => x.classList.toggle('active', x === tab));
  renderLogic();
}));
$$('[data-evidence-tab]').forEach((tab) => tab.addEventListener('click', () => {
  state.evidenceTab = tab.dataset.evidenceTab;
  $$('[data-evidence-tab]').forEach((x) => x.classList.toggle('active', x === tab));
  renderEvidence(state.result || {});
}));

el.run.addEventListener('click', runResearch);
el.eval.addEventListener('click', runEvals);
el.check.addEventListener('click', checkForecast);
el.health.addEventListener('click', runHealth);
el.healthRefresh.addEventListener('click', runHealth);
el.export.addEventListener('click', exportJson);
el.copyOutput.addEventListener('click', copyOutput);
el.refreshPacks.addEventListener('click', () => loadForecastPacks());
el.quickRerun.addEventListener('click', runResearch);
el.quickEval.addEventListener('click', runEvals);
el.quickCheck.addEventListener('click', checkForecast);
el.quickExport.addEventListener('click', exportJson);
el.goal.addEventListener('input', () => renderVisibleInput());
el.domain.addEventListener('change', () => renderVisibleInput());
el.context.addEventListener('change', () => renderVisibleInput());
el.packSelect.addEventListener('change', () => renderVisibleInput());

document.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') runResearch();
});

renderVisibleInput();
renderLogic();
renderEval(null);
loadForecastPacks();
