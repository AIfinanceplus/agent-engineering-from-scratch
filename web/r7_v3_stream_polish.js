/* Live-run semantics layered on top of the stable V3 renderer. */

const completedOutputRenderer = renderOutputInspector;
renderOutputInspector = function renderStreamingOutputInspector() {
  const run = appState.run;
  if (!run) return completedOutputRenderer();
  if (!appState.live.active && run.ok !== null) return completedOutputRenderer();

  const s1 = run.research_synthesis || {};
  const d1 = run.domain_brief || {};
  const f1 = run.forecast_pack || run.final_artifact || {};
  const score = f1.scoreboard || {};
  const scenario = f1.scenario_tracker?.current_state || '—';
  const liveNode = NODE_META[appState.live.currentNode]?.name || 'Research';
  const summary = d1.sections?.executive_summary || d1.answer || s1.answer || `Agent 正在执行 ${liveNode}；输出会随着 grounded artifacts 到达而逐步更新。`;
  const thesis = d1.sections?.thesis || d1.sections?.evidence_posture || '等待 D1 Domain Brief';

  return `<div class="output-stage"><div><div class="kicker">LIVE RESEARCH OUTPUT</div><strong>${esc(liveNode)}</strong></div><span class="pill running">STREAMING</span></div>
    <section class="output-section"><h3>当前综合输出 / Live Summary</h3><p>${esc(summary)}</p></section>
    <section class="output-section"><h3>${d1.domain === 'policy' ? 'Policy Posture' : 'Investment Thesis'}</h3><p>${esc(thesis)}</p></section>
    <section class="output-section"><h3>实时状态</h3><ul><li>S1: ${s1.answer ? 'available' : 'pending'} · support ${esc(s1.confidence ?? '—')}</li><li>D1: ${d1.answer || d1.sections ? 'available' : 'pending'} · ${esc(d1.decision_status || '—')}</li><li>F1: ${f1.artifact_type === 'forecast_pack' ? `available · scenario ${scenario}` : 'pending'}</li><li>Evidence: ${(run.evidence || []).length} · Citations: ${(run.citations || []).length}</li><li>Checkpoint: ${esc(run.latest_checkpoint?.checkpoint_id || '—')}</li></ul></section>
    <section class="output-section"><h3>Forecast Scoreboard</h3><div class="metric-strip"><div class="metric"><span>OPEN</span><strong>${score.open || 0}</strong></div><div class="metric"><span>HIT</span><strong>${score.hits || 0}</strong></div><div class="metric"><span>MISS</span><strong>${score.misses || 0}</strong></div></div></section>`;
};

const completedStatusRenderer = renderStatusBar;
renderStatusBar = function renderLiveStatusBar() {
  completedStatusRenderer();
  if (appState.live?.active) {
    const node = NODE_META[appState.live.currentNode]?.name || appState.live.currentNode || '—';
    $('#status-current').textContent = node;
  }
};
