const $ = (s) => document.querySelector(s);

const runButton = $('#run-btn');
const evalButton = $('#eval-btn');
const prevButton = $('#prev-btn');
const nextButton = $('#next-btn');
const autoButton = $('#auto-btn');
const resetButton = $('#reset-btn');
const goalInput = $('#goal');
const contextPreset = $('#context-preset');
const dataMode = $('#data-mode');

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
const modeStrip = $('#mode-strip');
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
const traceDetail = $('#trace-detail');
const evalDetail = $('#eval-detail');
const runtimeDetail = $('#runtime-detail');
const rawEvent = $('#raw-event');

let uiMode = 'macro2';
let displayEvents = [];
let currentIndex = -1;
let autoTimer = null;
let lastResponse = null;
let lastEvalSuite = null;

const pretty = (v) => JSON.stringify(v, null, 2);
const clone = (v) => (v == null ? v : JSON.parse(JSON.stringify(v)));

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

function meaningful(event) {
  if (['plan_created','scheduler_tick','task_started','task_completed','task_failed','evidence_registered','synthesis_verified','plan_completed','plan_failed'].includes(event.type)) return true;
  if (event.type !== 'task_runtime_event') return false;
  const inner = event.event && event.event.type;
  return ['model_response','tool_validation','policy_decision','tool_attempt','tool_result','final'].includes(inner);
}

function buildMacroEvents(events) {
  let plan = null;
  let citations = [];
  return events.reduce((items, event) => {
    if (event.plan) plan = clone(event.plan);
    if (event.type === 'synthesis_verified') citations = clone(event.citations || []);
    if (meaningful(event)) items.push({event, plan: clone(plan), citations: clone(citations)});
    return items;
  }, []);
}

function buildEvalEvents(suite) {
  const items = [];
  (suite.cases || []).forEach((entry) => {
    (entry.process || []).forEach((event) => items.push({event, entry}));
  });
  return items;
}

function sourceName(task) {
  if (task.tool_name === 'fetch_bls_series') return 'BLS';
  if (task.tool_name === 'fetch_fred_series') return 'FRED';
  if (task.tool_name === 'fetch_eia_series') return 'EIA';
  return 'ANALYSIS';
}

function sourceAsOf(result) {
  if (!result || typeof result !== 'object') return '—';
  if (result.as_of) return result.as_of;
  const history = result.history || [];
  if (!history.length) return '—';
  const last = history[history.length - 1];
  return last.period_key || last.period || '—';
}

function renderMacroPlan(plan) {
  leftKicker.textContent = 'SOURCE PLAN';
  leftTitle.textContent = 'Multi-Source 任务';
  dagHint.innerHTML = '<span>H1</span><span>+</span><span>C1</span><span>+</span><span>F1</span><span>+</span><span>G1</span><span>→</span><span>A1</span>';
  legend.style.display = 'flex';

  if (!plan) {
    planList.innerHTML = '<div class="empty-state">运行后显示 BLS / FRED / EIA Source Tasks。</div>';
    return;
  }

  planList.innerHTML = '';
  (plan.tasks || []).forEach((task) => {
    const card = document.createElement('article');
    card.className = `task-card ${task.status || 'pending'}`;
    const head = document.createElement('div');
    head.className = 'task-head';
    head.innerHTML = `<span class="task-id">${task.task_id}</span><span class="status-chip ${task.status}">${String(task.status).toUpperCase()}</span>`;
    const title = document.createElement('strong');
    title.textContent = task.title;
    const meta = document.createElement('small');
    const provider = sourceName(task);
    const series = task.arguments && task.arguments.series_id;
    meta.textContent = series ? `${provider} · ${series} · ${(task.arguments.mode || '').toUpperCase()}` : `depends on: ${(task.depends_on || []).join(' + ')}`;
    card.append(head, title, meta);

    if (task.result && task.result.kind === 'evidence') {
      const source = document.createElement('div');
      source.className = 'source-row';
      source.innerHTML = `<span>${provider}</span><strong>${task.result.value} ${task.result.unit}</strong><small>as of ${sourceAsOf(task.result)}</small>`;
      card.appendChild(source);
    }
    if (task.result && task.result.kind === 'synthesis') {
      const signals = document.createElement('div');
      signals.className = 'task-result';
      signals.textContent = Object.entries(task.result.signals || {}).map(([k,v]) => `${k}: ${v}`).join('\n');
      card.appendChild(signals);
    }
    planList.appendChild(card);
  });

  const tasks = plan.tasks || [];
  const completed = tasks.filter((t) => t.status === 'completed').length;
  planStatus.textContent = plan.status;
  planProgress.textContent = `${completed} / ${tasks.length}`;
  evidenceCount.textContent = String(tasks.filter((t) => t.result && t.result.kind === 'evidence').length);
  planBadge.textContent = plan.status;
  planBadge.className = `badge ${plan.status === 'completed' ? 'completed' : 'neutral'}`;
}

function renderEvalCases(suite, activeCaseId = null) {
  leftKicker.textContent = 'EVAL DATASET';
  leftTitle.textContent = 'Eval Cases';
  dagHint.innerHTML = '<span>Case</span><span>→</span><span>Run</span><span>→</span><span>Checks</span><span>→</span><span>Verdict</span>';
  legend.style.display = 'none';
  planList.innerHTML = '';
  (suite.cases || []).forEach((entry) => {
    const report = entry.report || {};
    const card = document.createElement('article');
    card.className = `task-card ${report.passed ? 'completed' : 'failed'}`;
    if (entry.case.case_id === activeCaseId) card.classList.add('eval-active-case');
    const checks = report.checks || [];
    card.innerHTML = `<div class="task-head"><span class="task-id">E</span><span class="status-chip ${report.passed ? 'completed' : 'failed'}">${report.passed ? 'PASS' : 'FAIL'}</span></div><strong>${entry.case.case_id}</strong><small>${checks.filter(c => c.passed).length}/${checks.length} deterministic checks</small>`;
    planList.appendChild(card);
  });
  planStatus.textContent = 'eval suite';
  planProgress.textContent = `${suite.passed} / ${suite.total}`;
  evidenceCount.textContent = `${Math.round((suite.pass_rate || 0) * 100)}%`;
  planBadge.textContent = suite.passed === suite.total ? 'PASS' : 'FAIL';
}

function renderCitations(citations) {
  supportKicker.textContent = 'CITATIONS';
  citationList.innerHTML = '';
  if (!citations || !citations.length) {
    citationTitle.textContent = '尚未形成';
    citationList.innerHTML = '<div class="empty-state">A1 完成后显示 BLS / FRED / EIA 来源。</div>';
    return;
  }
  citationTitle.textContent = `${citations.length} sources verified`;
  citations.forEach((item) => {
    const row = document.createElement('article');
    row.className = 'citation-row';
    row.innerHTML = `<div><strong>${item.citation}</strong><span>${item.publisher}</span></div><span>${item.title}</span><code>${item.uri}</code>`;
    citationList.appendChild(row);
  });
}

function renderFreshness(artifact) {
  supportKicker.textContent = 'FRESHNESS';
  citationList.innerHTML = '';
  const freshness = (artifact && artifact.freshness) || {};
  if (!Object.keys(freshness).length) {
    citationTitle.textContent = '等待 A1';
    citationList.innerHTML = '<div class="empty-state">A1 会比较每条 Evidence 的 as-of 日期。</div>';
    return;
  }
  citationTitle.textContent = `${Object.keys(freshness).length} evidence clocks`;
  Object.entries(freshness).forEach(([id, info]) => {
    const row = document.createElement('article');
    row.className = `freshness-row ${info.status}`;
    row.innerHTML = `<strong>${id}</strong><span>${info.as_of} · ${info.age_days} days · ${String(info.status).toUpperCase()}</span>`;
    citationList.appendChild(row);
  });
}

function renderCheck(check) {
  supportKicker.textContent = 'CURRENT CHECK';
  citationTitle.textContent = check.passed ? 'PASS' : 'FAIL';
  citationList.innerHTML = `<article class="eval-check-card ${check.passed ? 'pass' : 'fail'}"><strong>${check.label}</strong><span>Actual: ${pretty(check.actual)}</span><span>Expected: ${pretty(check.expected)}</span>${check.passed ? '' : `<span>${check.failure}</span>`}</article>`;
}

function macroMeta(item) {
  const event = item.event;
  if (event.type === 'plan_created') return {
    label: 'Multi-source plan created', title: 'Planner：先声明四个 Source，再声明 A1', file: 'r2_planner.py',
    code: 'H1 = BLS headline CPI\nC1 = BLS core CPI\nF1 = FRED 5Y breakeven\nG1 = EIA gasoline\nA1.depends_on = ["H1", "C1", "F1", "G1"]',
    explain: '<p>Source planning 与 analysis planning 分开。A1 只能消费完成后的 Evidence，不能隐藏取数。</p>',
  };
  if (event.type === 'scheduler_tick') return {
    label: `READY ${event.ready.join(', ') || '—'}`, title: 'Scheduler：根据依赖释放任务', file: 'scheduler.py',
    code: `READY   = ${pretty(event.ready)}\nBLOCKED = ${pretty(event.blocked)}`,
    explain: '<p>H1/C1/F1/G1 都没有依赖，理论上可并行；当前教学 Scheduler 仍顺序执行。A1 必须等待四条 Evidence。</p>',
  };
  if (event.type === 'task_started') return {
    label: `${event.task_id} started`, title: `${event.task_id}：解析上游结果`, file: 'scheduler.py',
    code: `resolved_arguments = _resolve_arguments(task.arguments, results)\n\n${pretty(event.arguments)}`,
    explain: '<p>只有到任务真正启动时，from_task 才被替换成完整 Evidence object。</p>',
  };
  if (event.type === 'evidence_registered') return {
    label: `${event.evidence.evidence_id} registered`, title: 'EvidenceStore：provenance 注册', file: 'evidence.py',
    code: `record = EvidenceRecord.from_dict(result)\nevidence_store.add(record)\n\n${pretty(event.evidence)}`,
    explain: '<p>不同来源最后进入同一个 EvidenceStore 合同，所以后面的 Citation 验证不需要知道数据来自 BLS、FRED 还是 EIA。</p>',
  };
  if (event.type === 'synthesis_verified') return {
    label: 'Cross-source citations verified', title: 'A1：四条 Evidence 都通过 Citation 验证', file: 'macro_multisource_analysis.py / scheduler.py',
    code: `citations = evidence_store.citations(result["evidence_ids"])\n\n${pretty(event.citations)}`,
    explain: '<p>A1 的描述性结论必须回指四条已经登记的证据；不存在的 Evidence ID 会 fail closed。</p>',
  };
  if (event.type === 'plan_completed') return {
    label: 'Multi-source research completed', title: 'Final：signals + freshness + limitations', file: 'macro_multisource_analysis.py',
    code: pretty(event.final_artifact),
    explain: `<p><strong>${event.final_result}</strong></p><p>注意 limitations：gasoline 与 breakeven 是描述性信号，不是 CPI 因果贡献。</p>`,
  };
  if (event.type === 'task_completed') return {
    label: `${event.task_id} completed`, title: `${event.task_id}：结果写回 Plan State`, file: 'scheduler.py',
    code: 'task.result = result\ntask.status = "completed"\nresults[task.task_id] = result',
    explain: '<p>Source 结果继续保留完整 history，供 A1 使用；EvidenceStore 同时保存精简 provenance record。</p>',
  };
  if (event.type === 'task_runtime_event') {
    const inner = event.event || {};
    if (inner.type === 'tool_attempt') return {
      label: `${event.task_id} · Tool execute`, title: `${event.task_id}：真实 capability 边界`, file: event.task_id === 'F1' || event.task_id === 'G1' ? 'macro_multisource.py' : 'agent.py',
      code: `result = tool.function(**arguments)\n\n${pretty(inner.arguments)}`,
      explain: '<p>Live FRED/EIA 的 API key 来自 Runtime 环境变量，不在 Tool arguments 中，因此 Model 和 Trace 都看不到凭证。</p>',
    };
    if (inner.type === 'tool_result') return {
      label: `${event.task_id} · Tool result`, title: `${event.task_id}：结构化 Observation`, file: event.task_id === 'A1' ? 'macro_multisource_analysis.py' : 'macro_sources.py / macro_multisource.py',
      code: pretty(inner.result),
      explain: '<p>Source Adapter 把不同 API response 归一化成统一 Evidence contract；A1 只读这些结果。</p>',
    };
    if (inner.type === 'tool_validation') return {label:`${event.task_id} · validate`,title:'Tool schema validation',file:'tools.py / r2_tooling.py',code:pretty(inner.validation),explain:'<p>业务 Tool 仍使用同一 Runtime validation。</p>'};
    if (inner.type === 'policy_decision') return {label:`${event.task_id} · Policy`,title:'ExecutionContext + Policy',file:'policy.py',code:pretty(inner.policy),explain:'<p>READY 不等于有权限；ExecutionContext 仍然参与 Policy。</p>'};
    if (inner.type === 'model_response') return {label:`${event.task_id} · proposal`,title:'Planned Tool Call proposal',file:'agent.py',code:pretty(inner.response),explain:'<p>Planner 定义 WHAT，Runtime 仍控制 HOW。</p>'};
    if (inner.type === 'final') return {label:`${event.task_id} · Runtime final`,title:'单 Task Runtime 完成',file:'agent.py',code:pretty(inner),explain:'<p>完成后控制权回到 Scheduler。</p>'};
  }
  return {label:event.type,title:'Runtime event',file:'scheduler.py',code:pretty(event),explain:'<p>底层事件。</p>'};
}

function evalMeta(item) {
  const event = item.event;
  if (event.type === 'eval_case_started') return {label:`${event.case_id} · Case loaded`,title:'EvalCase：先定义 Expected',file:'evals.py',code:pretty(event.expectations),explain:'<p>评分标准在 Agent 运行前已经固定。</p>'};
  if (event.type === 'eval_agent_run_completed') return {label:`${event.case_id} · Agent run`,title:'Actual Result 冻结',file:'evals.py',code:pretty(event.run_summary),explain:'<p>先完整执行 Agent，再做 deterministic checks。</p>'};
  if (event.type === 'eval_check') return {label:`${event.case_id} · ${event.check_id} ${event.passed ? '✓' : '✕'}`,title:`Check：${event.label}`,file:'evals.py',code:`actual = ${pretty(event.actual)}\nexpected = ${pretty(event.expected)}\npassed = ${event.passed}`,explain:`<p>${event.passed ? 'PASS' : `FAIL: ${event.failure}`}</p>`};
  return {label:`${event.case_id} · ${event.passed ? 'PASS' : 'FAIL'}`,title:'Eval Verdict',file:'evals.py',code:pretty(event),explain:'<p>所有质量合同汇总成 Verdict。</p>'};
}

function renderTimeline() {
  timeline.innerHTML = '';
  displayEvents.forEach((item, index) => {
    const meta = uiMode === 'eval' ? evalMeta(item) : macroMeta(item);
    const li = document.createElement('li');
    li.className = 'timeline-item';
    if (index < currentIndex) li.classList.add('done');
    if (index === currentIndex) li.classList.add('active');
    li.innerHTML = `<span class="timeline-marker">${index + 1}</span><span>${meta.label}</span>`;
    li.addEventListener('click', () => showStep(index));
    timeline.appendChild(li);
  });
}

function showStep(index) {
  if (!displayEvents.length) return;
  currentIndex = Math.max(0, Math.min(index, displayEvents.length - 1));
  const item = displayEvents[currentIndex];
  const meta = uiMode === 'eval' ? evalMeta(item) : macroMeta(item);
  if (uiMode === 'eval') {
    renderEvalCases(lastEvalSuite, item.event.case_id);
    if (item.event.type === 'eval_check') renderCheck(item.event);
    else {
      supportKicker.textContent = 'EVAL';
      citationTitle.textContent = item.entry.report.passed ? 'PASS' : 'FAIL';
      citationList.innerHTML = `<div class="empty-state">${item.entry.case.case_id}</div>`;
    }
  } else {
    renderMacroPlan(item.plan);
    if (item.event.type === 'plan_completed') renderFreshness(item.event.final_artifact);
    else renderCitations(item.citations);
  }
  eventCounter.textContent = `${currentIndex + 1} / ${displayEvents.length}`;
  currentAction.innerHTML = `<strong>${meta.title}</strong><span>${meta.label}</span>`;
  codeTitle.textContent = meta.title;
  codeFile.textContent = meta.file;
  codePanel.textContent = meta.code;
  explainBody.innerHTML = meta.explain;
  traceDetail.textContent = pretty(lastResponse && lastResponse.trace ? lastResponse.trace : {});
  evalDetail.textContent = pretty(lastEvalSuite || {});
  runtimeDetail.textContent = pretty(uiMode === 'eval' ? item.entry : {plan_snapshot:item.plan,execution_context:lastResponse && lastResponse.execution_context,reference_date:lastResponse && lastResponse.reference_date});
  rawEvent.textContent = pretty(item.event);
  renderTimeline();
}

function stopAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  autoButton.textContent = '自动';
}

function setMacroMode() {
  uiMode = 'macro2';
  runKicker.textContent = 'RUN / TRACE';
  runTitle.textContent = 'Multi-Source 研究过程';
  modeStrip.className = 'mode-strip run-mode';
  modeLabel.textContent = 'R2 MACRO RUN';
  modeHelp.textContent = 'BLS + FRED + EIA → Evidence → Freshness → Synthesis';
}

function setEvalMode() {
  uiMode = 'eval';
  runKicker.textContent = 'EVAL PROCESS';
  runTitle.textContent = 'Case → Run → Checks → Verdict';
  modeStrip.className = 'mode-strip eval-mode';
  modeLabel.textContent = 'EVAL MODE';
  modeHelp.textContent = '逐项显示 Expected / Actual / PASS-FAIL';
}

async function runMacro() {
  stopAuto(); setMacroMode(); runButton.disabled = true;
  try {
    const data = await post({action:'macro2',goal:goalInput.value,data_mode:dataMode.value,context_preset:contextPreset.value});
    lastResponse = data;
    displayEvents = buildMacroEvents(data.events || []);
    currentIndex = -1;
    const trace = data.trace || {};
    traceKpi.textContent = `${trace.span_count || 0} spans · ${(trace.metrics && trace.metrics.tool_attempts) || 0} tools`;
    evalKpi.textContent = `${String(data.data_mode).toUpperCase()} · ${data.reference_date}`;
    finalResult.textContent = data.final_result || '—';
    traceDetail.textContent = pretty(trace);
    if (displayEvents.length) showStep(0); else renderMacroPlan(data.plan);
  } catch (error) {
    currentAction.innerHTML = `<strong>运行失败</strong><span>${error.message}</span>`;
  } finally { runButton.disabled = false; }
}

async function runEvals() {
  stopAuto(); setEvalMode(); evalButton.disabled = true;
  try {
    const data = await post({action:'evals',context_preset:contextPreset.value});
    lastEvalSuite = data.eval_suite;
    displayEvents = buildEvalEvents(lastEvalSuite);
    currentIndex = -1;
    traceKpi.textContent = 'V11 regression';
    evalKpi.textContent = `${lastEvalSuite.passed}/${lastEvalSuite.total} PASS`;
    finalResult.textContent = `${Math.round(lastEvalSuite.pass_rate * 100)}% pass rate`;
    if (displayEvents.length) showStep(0);
  } catch (error) {
    currentAction.innerHTML = `<strong>Eval 失败</strong><span>${error.message}</span>`;
  } finally { evalButton.disabled = false; }
}

function resetView() {
  stopAuto(); setMacroMode(); displayEvents = []; currentIndex = -1; lastResponse = null;
  renderMacroPlan(null); renderCitations([]);
  planStatus.textContent = '未运行'; planProgress.textContent = '0 / 5'; evidenceCount.textContent = '0';
  traceKpi.textContent = '—'; evalKpi.textContent = '—'; finalResult.textContent = '—';
  eventCounter.textContent = '尚未运行'; timeline.innerHTML = '<li class="empty-state">点击“运行 Multi-Source 研究”开始。</li>';
  currentAction.innerHTML = '<strong>等待运行</strong><span>建议先用 Fixture Replay 看清四来源结构。</span>';
  codeTitle.textContent = '对应代码'; codeFile.textContent = 'r2_planner.py'; codePanel.textContent = '等待执行事件…';
  explainBody.innerHTML = '<p>这里解释 Source Plan、Evidence、Freshness 与 Synthesis。</p>';
  traceDetail.textContent = '{}'; evalDetail.textContent = pretty(lastEvalSuite || {}); runtimeDetail.textContent = '{}'; rawEvent.textContent = '{}';
}

prevButton.addEventListener('click', () => {stopAuto(); if (currentIndex > 0) showStep(currentIndex - 1);});
nextButton.addEventListener('click', () => {stopAuto(); if (currentIndex < displayEvents.length - 1) showStep(currentIndex + 1);});
autoButton.addEventListener('click', () => {
  if (autoTimer) { stopAuto(); return; }
  if (!displayEvents.length) return;
  autoButton.textContent = '停止';
  autoTimer = setInterval(() => {
    if (currentIndex >= displayEvents.length - 1) { stopAuto(); return; }
    showStep(currentIndex + 1);
  }, 800);
});
runButton.addEventListener('click', runMacro);
evalButton.addEventListener('click', runEvals);
resetButton.addEventListener('click', resetView);
resetView();
