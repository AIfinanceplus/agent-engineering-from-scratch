const $ = (s) => document.querySelector(s);
const pretty = (value) => JSON.stringify(value, null, 2);
const clone = (value) => value == null ? value : JSON.parse(JSON.stringify(value));

const el = {
  run: $('#run-btn'), eval: $('#eval-btn'), prev: $('#prev-btn'), next: $('#next-btn'),
  auto: $('#auto-btn'), reset: $('#reset-btn'), goal: $('#goal'), context: $('#context-preset'),
  dataMode: $('#data-mode'), planStatus: $('#plan-status'), progress: $('#plan-progress'),
  evidence: $('#evidence-count'), traceKpi: $('#trace-kpi'), evalKpi: $('#eval-kpi'),
  final: $('#final-result'), planBadge: $('#plan-badge'), planList: $('#plan-list'),
  leftKicker: $('#left-kicker'), leftTitle: $('#left-title'), dagHint: $('#dag-hint'),
  legend: $('#legend'), runKicker: $('#run-kicker'), runTitle: $('#run-title'),
  modeStrip: $('#mode-strip'), modeLabel: $('#mode-label'), modeHelp: $('#mode-help'),
  counter: $('#event-counter'), current: $('#current-action'), timeline: $('#timeline'),
  codeTitle: $('#code-title'), codeFile: $('#code-file'), code: $('#code-panel'),
  explain: $('#explain-body'), supportKicker: $('#support-kicker'),
  supportTitle: $('#citation-title'), supportList: $('#citation-list'),
  traceDetail: $('#trace-detail'), evalDetail: $('#eval-detail'),
  runtimeDetail: $('#runtime-detail'), rawEvent: $('#raw-event'),
};

let mode = 'macro';
let items = [];
let index = -1;
let timer = null;
let lastRun = null;
let lastSuite = null;

async function post(payload) {
  try {
    const response = await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    return {ok: response.ok, status: response.status, data};
  } catch (error) {
    return {ok: false, status: 0, data: {error: `NetworkError: ${error.message}`}};
  }
}

function setMacroMode() {
  mode = 'macro';
  el.runKicker.textContent = 'RUN / TRACE';
  el.runTitle.textContent = 'Multi-Source 研究过程';
  el.modeStrip.className = 'mode-strip run-mode';
  el.modeLabel.textContent = 'R2 MACRO RUN';
  el.modeHelp.textContent = 'Live 先 Preflight；通过后才进入 Planner / Scheduler / Runtime';
}

function setEvalMode() {
  mode = 'eval';
  el.runKicker.textContent = 'R2 EVAL PROCESS';
  el.runTitle.textContent = 'Case → R2 Run → Checks → Verdict';
  el.modeStrip.className = 'mode-strip eval-mode';
  el.modeLabel.textContent = 'R2 EVAL MODE';
  el.modeHelp.textContent = '直接评估 H1/C1/F1/G1/A1，不再使用 E1/E2 synthetic plan';
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

function renderPlan(plan) {
  el.leftKicker.textContent = 'SOURCE PLAN';
  el.leftTitle.textContent = 'R2 Multi-Source 任务';
  el.dagHint.innerHTML = '<span>H1</span><span>+</span><span>C1</span><span>+</span><span>F1</span><span>+</span><span>G1</span><span>→</span><span>A1</span>';
  el.legend.style.display = 'flex';
  el.planList.innerHTML = '';
  if (!plan) {
    el.planList.innerHTML = '<div class="empty-state">运行后显示 BLS / FRED / EIA Source Tasks。</div>';
    return;
  }
  for (const task of plan.tasks || []) {
    const card = document.createElement('article');
    card.className = `task-card ${task.status || 'pending'}`;
    const provider = sourceName(task);
    const series = task.arguments && task.arguments.series_id;
    card.innerHTML = `
      <div class="task-head"><span class="task-id">${task.task_id}</span><span class="status-chip ${task.status}">${String(task.status).toUpperCase()}</span></div>
      <strong>${task.title}</strong>
      <small>${series ? `${provider} · ${series} · ${(task.arguments.mode || '').toUpperCase()}` : `depends on: ${(task.depends_on || []).join(' + ')}`}</small>`;
    if (task.result && task.result.kind === 'evidence') {
      const row = document.createElement('div');
      row.className = 'source-row';
      row.innerHTML = `<span>${provider}</span><strong>${task.result.value} ${task.result.unit}</strong><small>as of ${sourceAsOf(task.result)}</small>`;
      card.appendChild(row);
    }
    if (task.result && task.result.kind === 'synthesis') {
      const result = document.createElement('div');
      result.className = 'task-result';
      result.textContent = Object.entries(task.result.signals || {}).map(([k, v]) => `${k}: ${v}`).join('\n');
      card.appendChild(result);
    }
    el.planList.appendChild(card);
  }
  const tasks = plan.tasks || [];
  const completed = tasks.filter((task) => task.status === 'completed').length;
  el.planStatus.textContent = plan.status;
  el.progress.textContent = `${completed} / ${tasks.length}`;
  el.evidence.textContent = String(tasks.filter((task) => task.result && task.result.kind === 'evidence').length);
  el.planBadge.textContent = plan.status;
  el.planBadge.className = `badge ${plan.status === 'completed' ? 'completed' : 'neutral'}`;
}

function renderPreflight(preflight) {
  el.leftKicker.textContent = 'LIVE PREFLIGHT';
  el.leftTitle.textContent = 'Source Readiness';
  el.dagHint.innerHTML = '<span>BLS</span><span>+</span><span>FRED</span><span>+</span><span>EIA</span><span>→</span><span>RUN</span>';
  el.legend.style.display = 'none';
  el.planList.innerHTML = '';
  for (const source of preflight.sources || []) {
    const card = document.createElement('article');
    card.className = `task-card ${source.ready ? 'completed' : 'failed'}`;
    card.innerHTML = `
      <div class="task-head"><span class="task-id">${source.provider[0]}</span><span class="status-chip ${source.ready ? 'completed' : 'failed'}">${source.ready ? 'READY' : 'MISSING'}</span></div>
      <strong>${source.provider}</strong>
      <small>${source.credential === 'none' ? 'No credential required' : source.credential}</small>
      <div class="task-result">${source.detail}</div>`;
    el.planList.appendChild(card);
  }
  el.planStatus.textContent = preflight.ready ? 'preflight passed' : 'preflight blocked';
  el.progress.textContent = `${(preflight.sources || []).filter((x) => x.ready).length} / ${(preflight.sources || []).length}`;
  el.evidence.textContent = '0';
  el.planBadge.textContent = preflight.ready ? 'READY' : 'BLOCKED';
  el.planBadge.className = `badge ${preflight.ready ? 'completed' : 'neutral'}`;
}

function renderEvalCases(suite, activeCase = null) {
  el.leftKicker.textContent = 'R2 EVAL DATASET';
  el.leftTitle.textContent = 'Multi-Source Eval Cases';
  el.dagHint.innerHTML = '<span>Case</span><span>→</span><span>H1/C1/F1/G1/A1</span><span>→</span><span>Checks</span>';
  el.legend.style.display = 'none';
  el.planList.innerHTML = '';
  for (const entry of suite.cases || []) {
    const report = entry.report || {};
    const checks = report.checks || [];
    const card = document.createElement('article');
    card.className = `task-card ${report.passed ? 'completed' : 'failed'}${entry.case.case_id === activeCase ? ' eval-active-case' : ''}`;
    card.innerHTML = `
      <div class="task-head"><span class="task-id">R2</span><span class="status-chip ${report.passed ? 'completed' : 'failed'}">${report.passed ? 'PASS' : 'FAIL'}</span></div>
      <strong>${entry.case.case_id}</strong>
      <small>${checks.filter((check) => check.passed).length}/${checks.length} checks · H1/C1/F1/G1/A1</small>`;
    el.planList.appendChild(card);
  }
  el.planStatus.textContent = suite.suite_id || 'r2 eval suite';
  el.progress.textContent = `${suite.passed} / ${suite.total}`;
  el.evidence.textContent = `${Math.round((suite.pass_rate || 0) * 100)}%`;
  el.planBadge.textContent = suite.passed === suite.total ? 'PASS' : 'FAIL';
  el.planBadge.className = `badge ${suite.passed === suite.total ? 'completed' : 'neutral'}`;
}

function renderCitations(citations) {
  el.supportKicker.textContent = 'CITATIONS';
  el.supportList.innerHTML = '';
  if (!citations || !citations.length) {
    el.supportTitle.textContent = '尚未形成';
    el.supportList.innerHTML = '<div class="empty-state">A1 完成后显示 4 个 verified citations。</div>';
    return;
  }
  el.supportTitle.textContent = `${citations.length} sources verified`;
  for (const item of citations) {
    const row = document.createElement('article');
    row.className = 'citation-row';
    row.innerHTML = `<div><strong>${item.citation}</strong><span>${item.publisher}</span></div><span>${item.title}</span><code>${item.uri}</code>`;
    el.supportList.appendChild(row);
  }
}

function renderFreshness(artifact) {
  const freshness = artifact && artifact.freshness || {};
  el.supportKicker.textContent = 'FRESHNESS';
  el.supportTitle.textContent = `${Object.keys(freshness).length} evidence clocks`;
  el.supportList.innerHTML = '';
  for (const [id, info] of Object.entries(freshness)) {
    const row = document.createElement('article');
    row.className = `freshness-row ${info.status}`;
    row.innerHTML = `<strong>${id}</strong><span>${info.as_of} · ${info.age_days} days · ${String(info.status).toUpperCase()}</span>`;
    el.supportList.appendChild(row);
  }
}

function renderCheck(check) {
  el.supportKicker.textContent = 'CURRENT CHECK';
  el.supportTitle.textContent = check.passed ? 'PASS' : 'FAIL';
  el.supportList.innerHTML = `<article class="eval-check-card ${check.passed ? 'pass' : 'fail'}"><strong>${check.label}</strong><span>Actual: ${pretty(check.actual)}</span><span>Expected: ${pretty(check.expected)}</span>${check.passed ? '' : `<span>${check.failure}</span>`}</article>`;
}

function buildMacroItems(events) {
  let plan = null;
  let citations = [];
  const meaningful = new Set(['plan_created', 'scheduler_tick', 'task_started', 'task_completed', 'task_failed', 'evidence_registered', 'synthesis_verified', 'plan_completed', 'plan_failed']);
  const innerMeaningful = new Set(['model_response', 'tool_validation', 'policy_decision', 'tool_attempt', 'tool_result', 'final']);
  const result = [];
  for (const event of events || []) {
    if (event.plan) plan = clone(event.plan);
    if (event.type === 'synthesis_verified') citations = clone(event.citations || []);
    const keep = meaningful.has(event.type) || (event.type === 'task_runtime_event' && innerMeaningful.has(event.event && event.event.type));
    if (keep) result.push({kind: 'macro', event, plan: clone(plan), citations: clone(citations)});
  }
  return result;
}

function buildPreflightItems(preflight) {
  const result = (preflight.sources || []).map((source) => ({kind: 'preflight', event: {type: 'preflight_source', source}, preflight}));
  result.push({kind: 'preflight', event: {type: 'preflight_verdict', passed: preflight.ready, missing_env: preflight.missing_env, setup: preflight.setup}, preflight});
  return result;
}

function buildEvalItems(suite) {
  const result = [];
  for (const entry of suite.cases || []) {
    for (const event of entry.process || []) result.push({kind: 'eval', event, entry});
  }
  return result;
}

function meta(item) {
  const event = item.event;
  if (item.kind === 'preflight') {
    if (event.type === 'preflight_source') return {
      label: `${event.source.provider} · ${event.source.ready ? 'READY' : 'MISSING'}`,
      title: `Live Preflight：${event.source.provider}`,
      file: 'live_preflight.py',
      code: pretty(event.source),
      explain: `<p>${event.source.detail}</p><p>这里只返回 credential 是否存在，绝不返回 secret value。</p>`,
    };
    return {
      label: event.passed ? 'Preflight PASS' : 'Preflight BLOCKED',
      title: event.passed ? 'Live sources ready' : 'Live mode 在进入 Planner 前被安全阻止',
      file: 'live_preflight.py / serve_visualizer.py',
      code: pretty({missing_env: event.missing_env, setup: event.setup}),
      explain: event.passed
        ? '<p>所有 live source requirements 已满足，下一步才允许创建 R2 DAG。</p>'
        : '<p>这不是 Agent 执行失败，而是 Runtime precondition 未满足。设置缺失环境变量并重启 workbench 后再运行。</p>',
    };
  }
  if (item.kind === 'eval') {
    if (event.type === 'eval_case_started') return {label: `${event.case_id} · Case`, title: 'R2 EvalCase：Expected 先固定', file: 'r2_evals.py', code: pretty(event.expectations), explain: '<p>Expected 明确要求 H1/C1/F1/G1/A1、4 Evidence、3 providers、4 citations 与 causal guardrail。</p>'};
    if (event.type === 'eval_agent_run_completed') return {label: `${event.case_id} · R2 run`, title: 'Actual R2 fixture run 冻结', file: 'r2_evals.py', code: pretty(event.run_summary), explain: '<p>Eval 跑的就是 R2 MultiSourceMacroPlanner，不再调用旧 ResearchPlanner(E1/E2)。</p>'};
    if (event.type === 'eval_check') return {label: `${event.case_id} · ${event.check_id} ${event.passed ? '✓' : '✕'}`, title: `Check：${event.label}`, file: 'r2_evals.py', code: `actual = ${pretty(event.actual)}\nexpected = ${pretty(event.expected)}\npassed = ${event.passed}`, explain: `<p>${event.passed ? 'PASS' : `FAIL: ${event.failure}`}</p>`};
    return {label: `${event.case_id} · ${event.passed ? 'PASS' : 'FAIL'}`, title: 'R2 Eval Verdict', file: 'r2_evals.py', code: pretty(event), explain: '<p>全部 R2 quality contracts 汇总成最终 Verdict。</p>'};
  }
  if (event.type === 'plan_created') return {label: 'R2 plan created', title: 'Planner：4 Source Tasks → A1', file: 'r2_planner.py', code: 'H1 = BLS headline\nC1 = BLS core\nF1 = FRED breakeven\nG1 = EIA gasoline\nA1.depends_on = ["H1", "C1", "F1", "G1"]', explain: '<p>A1 不允许隐藏取数。</p>'};
  if (event.type === 'scheduler_tick') return {label: `READY ${event.ready.join(', ') || '—'}`, title: 'Scheduler：dependency readiness', file: 'scheduler.py', code: `READY = ${pretty(event.ready)}\nBLOCKED = ${pretty(event.blocked)}`, explain: '<p>READY 由依赖状态计算，不由 Model 自己声明。</p>'};
  if (event.type === 'task_started') return {label: `${event.task_id} started`, title: `${event.task_id}：Task 进入 Runtime`, file: 'scheduler.py', code: pretty(event.arguments), explain: '<p>from_task 到这一刻才解析成完整 Evidence。</p>'};
  if (event.type === 'evidence_registered') return {label: `${event.evidence.evidence_id} registered`, title: 'EvidenceStore：统一 provenance contract', file: 'evidence.py', code: pretty(event.evidence), explain: '<p>BLS/FRED/EIA 进入同一个 EvidenceStore。</p>'};
  if (event.type === 'synthesis_verified') return {label: '4 citations verified', title: 'A1：Citation verification', file: 'scheduler.py / macro_multisource_analysis.py', code: pretty(event.citations), explain: '<p>不存在的 Evidence ID 会 fail closed。</p>'};
  if (event.type === 'plan_completed') return {label: 'R2 research completed', title: 'Final：signals + freshness + limitations', file: 'macro_multisource_analysis.py', code: pretty(event.final_artifact), explain: `<p><strong>${event.final_result}</strong></p>`};
  if (event.type === 'task_completed') return {label: `${event.task_id} completed`, title: `${event.task_id}：结果写回 Plan State`, file: 'scheduler.py', code: 'task.result = result\ntask.status = "completed"', explain: '<p>Scheduler 再判断下游 readiness。</p>'};
  if (event.type === 'task_runtime_event') {
    const inner = event.event || {};
    if (inner.type === 'tool_attempt') return {label: `${event.task_id} · Tool execute`, title: `${event.task_id}：Tool capability boundary`, file: event.task_id === 'F1' || event.task_id === 'G1' ? 'macro_multisource.py' : 'agent.py', code: pretty(inner.arguments), explain: '<p>API keys 不在 Tool args 中。</p>'};
    if (inner.type === 'tool_result') return {label: `${event.task_id} · Tool result`, title: `${event.task_id}：Observation`, file: event.task_id === 'A1' ? 'macro_multisource_analysis.py' : 'macro_sources.py / macro_multisource.py', code: pretty(inner.result), explain: '<p>Source response 已被 normalize。</p>'};
    if (inner.type === 'tool_validation') return {label: `${event.task_id} · validate`, title: 'Tool validation', file: 'tools.py / r2_tooling.py', code: pretty(inner.validation), explain: '<p>执行前先验证 schema。</p>'};
    if (inner.type === 'policy_decision') return {label: `${event.task_id} · Policy`, title: 'ExecutionContext + Policy', file: 'policy.py', code: pretty(inner.policy), explain: '<p>READY 不等于 ALLOW。</p>'};
    if (inner.type === 'model_response') return {label: `${event.task_id} · proposal`, title: 'Planned Tool proposal', file: 'agent.py', code: pretty(inner.response), explain: '<p>Planner 决定 WHAT，Runtime 决定 HOW。</p>'};
    if (inner.type === 'final') return {label: `${event.task_id} · Runtime final`, title: '单 Task Runtime 完成', file: 'agent.py', code: pretty(inner), explain: '<p>控制权回到 Scheduler。</p>'};
  }
  return {label: event.type, title: 'Event', file: 'scheduler.py', code: pretty(event), explain: '<p>Runtime event。</p>'};
}

function renderTimeline() {
  el.timeline.innerHTML = '';
  items.forEach((item, position) => {
    const m = meta(item);
    const li = document.createElement('li');
    li.className = 'timeline-item';
    if (position < index) li.classList.add('done');
    if (position === index) li.classList.add('active');
    li.innerHTML = `<span class="timeline-marker">${position + 1}</span><span>${m.label}</span>`;
    li.addEventListener('click', () => show(position));
    el.timeline.appendChild(li);
  });
}

function show(position) {
  if (!items.length) return;
  index = Math.max(0, Math.min(position, items.length - 1));
  const item = items[index];
  const m = meta(item);
  if (item.kind === 'preflight') {
    renderPreflight(item.preflight);
    el.supportKicker.textContent = 'LIVE SETUP';
    el.supportTitle.textContent = item.preflight.ready ? 'READY' : 'ACTION REQUIRED';
    el.supportList.innerHTML = item.preflight.ready
      ? '<div class="empty-state">Preflight passed. Planner may run.</div>'
      : `<div class="task-result">${(item.preflight.setup || []).join('\n')}</div>`;
  } else if (item.kind === 'eval') {
    renderEvalCases(lastSuite, item.event.case_id);
    if (item.event.type === 'eval_check') renderCheck(item.event);
    else {
      el.supportKicker.textContent = 'R2 EVAL';
      el.supportTitle.textContent = item.entry.report.passed ? 'PASS' : 'FAIL';
      el.supportList.innerHTML = `<div class="empty-state">${item.entry.case.case_id}</div>`;
    }
  } else {
    renderPlan(item.plan);
    if (item.event.type === 'plan_completed') renderFreshness(item.event.final_artifact);
    else renderCitations(item.citations);
  }
  el.counter.textContent = `${index + 1} / ${items.length}`;
  el.current.innerHTML = `<strong>${m.title}</strong><span>${m.label}</span>`;
  el.codeTitle.textContent = m.title;
  el.codeFile.textContent = m.file;
  el.code.textContent = m.code;
  el.explain.innerHTML = m.explain;
  el.traceDetail.textContent = pretty(lastRun && lastRun.trace || {});
  el.evalDetail.textContent = pretty(lastSuite || {});
  el.runtimeDetail.textContent = pretty(item.kind === 'eval' ? item.entry : item.kind === 'preflight' ? item.preflight : {plan_snapshot: item.plan, execution_context: lastRun && lastRun.execution_context, reference_date: lastRun && lastRun.reference_date});
  el.rawEvent.textContent = pretty(item.event);
  renderTimeline();
}

function stopAuto() {
  if (timer) clearInterval(timer);
  timer = null;
  el.auto.textContent = '自动';
}

async function runMacro() {
  stopAuto();
  setMacroMode();
  el.run.disabled = true;
  try {
    let preflightItems = [];
    if (el.dataMode.value === 'live') {
      const pre = await post({action: 'preflight', context_preset: el.context.value});
      if (!pre.ok) {
        el.current.innerHTML = `<strong>Preflight 请求失败</strong><span>${pre.data.error || `HTTP ${pre.status}`}</span>`;
        return;
      }
      preflightItems = buildPreflightItems(pre.data.preflight);
      if (!pre.data.preflight.ready) {
        items = preflightItems;
        lastRun = {preflight: pre.data.preflight};
        index = -1;
        el.traceKpi.textContent = '0 spans · 0 tools';
        el.evalKpi.textContent = 'LIVE · PREFLIGHT BLOCKED';
        el.final.textContent = `Missing: ${(pre.data.preflight.missing_env || []).join(', ')}`;
        show(0);
        return;
      }
    }

    const response = await post({
      action: 'macro2',
      goal: el.goal.value,
      data_mode: el.dataMode.value,
      context_preset: el.context.value,
    });
    if (!response.ok) {
      if (response.data.preflight) {
        items = buildPreflightItems(response.data.preflight);
        lastRun = response.data;
        index = -1;
        show(0);
      } else {
        el.current.innerHTML = `<strong>运行失败</strong><span>${response.data.error || `HTTP ${response.status}`}</span>`;
        el.runtimeDetail.textContent = pretty(response.data);
      }
      return;
    }

    lastRun = response.data;
    items = [...preflightItems, ...buildMacroItems(response.data.events || [])];
    index = -1;
    const trace = response.data.trace || {};
    el.traceKpi.textContent = `${trace.span_count || 0} spans · ${(trace.metrics && trace.metrics.tool_attempts) || 0} tools`;
    el.evalKpi.textContent = `${String(response.data.data_mode).toUpperCase()} · ${response.data.reference_date}`;
    el.final.textContent = response.data.final_result || '—';
    el.traceDetail.textContent = pretty(trace);
    if (items.length) show(0); else renderPlan(response.data.plan);
  } finally {
    el.run.disabled = false;
  }
}

async function runEvals() {
  stopAuto();
  setEvalMode();
  el.eval.disabled = true;
  try {
    const response = await post({action: 'evals', context_preset: el.context.value});
    if (!response.ok) {
      el.current.innerHTML = `<strong>R2 Eval 失败</strong><span>${response.data.error || `HTTP ${response.status}`}</span>`;
      return;
    }
    lastSuite = response.data.eval_suite;
    items = buildEvalItems(lastSuite);
    index = -1;
    el.traceKpi.textContent = 'R2 fixture suite';
    el.evalKpi.textContent = `${lastSuite.passed}/${lastSuite.total} PASS`;
    el.final.textContent = `${Math.round((lastSuite.pass_rate || 0) * 100)}% pass rate`;
    el.evalDetail.textContent = pretty(lastSuite);
    if (items.length) show(0); else renderEvalCases(lastSuite);
  } finally {
    el.eval.disabled = false;
  }
}

function reset() {
  stopAuto();
  setMacroMode();
  items = [];
  index = -1;
  lastRun = null;
  renderPlan(null);
  renderCitations([]);
  el.planStatus.textContent = '未运行';
  el.progress.textContent = '0 / 5';
  el.evidence.textContent = '0';
  el.traceKpi.textContent = '—';
  el.evalKpi.textContent = '—';
  el.final.textContent = '—';
  el.counter.textContent = '尚未运行';
  el.timeline.innerHTML = '<li class="empty-state">点击“运行 Multi-Source 研究”开始。</li>';
  el.current.innerHTML = '<strong>等待运行</strong><span>Live 模式会先执行 credential preflight。</span>';
  el.codeTitle.textContent = '对应代码';
  el.codeFile.textContent = 'r2_planner.py';
  el.code.textContent = '等待执行事件…';
  el.explain.innerHTML = '<p>这里解释 Live Preflight、Source Plan、Evidence、Freshness 与 R2 Eval。</p>';
  el.traceDetail.textContent = '{}';
  el.evalDetail.textContent = pretty(lastSuite || {});
  el.runtimeDetail.textContent = '{}';
  el.rawEvent.textContent = '{}';
}

el.prev.addEventListener('click', () => { stopAuto(); if (index > 0) show(index - 1); });
el.next.addEventListener('click', () => { stopAuto(); if (index < items.length - 1) show(index + 1); });
el.auto.addEventListener('click', () => {
  if (timer) { stopAuto(); return; }
  if (!items.length) return;
  el.auto.textContent = '停止';
  timer = setInterval(() => {
    if (index >= items.length - 1) { stopAuto(); return; }
    show(index + 1);
  }, 850);
});
el.run.addEventListener('click', runMacro);
el.eval.addEventListener('click', runEvals);
el.reset.addEventListener('click', reset);

reset();
