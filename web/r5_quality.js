(() => {
  const qualityDetail = document.querySelector('#quality-detail');
  const evalKpi = document.querySelector('#eval-kpi');
  if (evalKpi) evalKpi.textContent = 'R5';
  if (!qualityDetail) return;

  const originalFetch = window.fetch.bind(window);
  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

  function renderQuality(artifact) {
    const quality = artifact && artifact.quality;
    if (!quality) return;
    const rows = quality.evidence_quality || [];
    const relations = quality.relations || [];
    qualityDetail.innerHTML = `
      <div class="citation-head"><span class="kicker">R5 EVIDENCE QUALITY</span><strong>${esc(quality.support_label)} · ${esc(quality.support_score)}</strong></div>
      <p><strong>Heuristic support score — not probability.</strong></p>
      ${rows.map((row) => `
        <article class="eval-check-card ${row.quality_label === 'LOW' ? 'fail' : 'pass'}">
          <strong>${esc(row.evidence_id)} · ${esc(row.quality_label)} ${esc(row.quality_score)}</strong>
          <span>authority ${esc(row.dimensions.authority)} · freshness ${esc(row.dimensions.freshness)} · completeness ${esc(row.dimensions.completeness)} · relevance ${esc(row.dimensions.relevance)}</span>
          <span>${esc(row.direction)} · ${esc(row.freshness.status)} · age ${esc(row.freshness.age_days)}</span>
        </article>`).join('')}
      <div class="stage-divider">RELATIONS</div>
      ${relations.length ? relations.map((item) => `
        <article class="eval-check-card ${item.relation === 'CONTRADICTION' ? 'fail' : 'pass'}">
          <strong>${esc(item.relation)}</strong>
          <span>${esc((item.evidence_ids || []).join(' ↔ '))}</span>
          <span>${esc(item.detail)}</span>
        </article>`).join('') : '<div class="empty-state">No comparable contradiction detected.</div>'}
      <pre><code>${esc(JSON.stringify({relation_summary: quality.relation_summary, penalties: quality.penalties, score_type: quality.score_type}, null, 2))}</code></pre>`;
  }

  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    try {
      const clone = response.clone();
      clone.json().then((payload) => {
        const result = payload.research_result || payload;
        if (result && result.final_artifact) renderQuality(result.final_artifact);
      }).catch(() => {});
    } catch (_) {}
    return response;
  };
})();
