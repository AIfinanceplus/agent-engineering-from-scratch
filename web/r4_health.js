(() => {
  const r4HealthButton = document.querySelector('#health-btn');
  if (!r4HealthButton) return;

  const r4PlanStatus = document.querySelector('#plan-status');
  const r4PlanProgress = document.querySelector('#plan-progress');
  const r4EvidenceCount = document.querySelector('#evidence-count');
  const r4TraceKpi = document.querySelector('#trace-kpi');
  const r4EvalKpi = document.querySelector('#eval-kpi');
  const r4FinalResult = document.querySelector('#final-result');
  const r4PlanBadge = document.querySelector('#plan-badge');
  const r4PlanList = document.querySelector('#plan-list');
  const r4LeftKicker = document.querySelector('#left-kicker');
  const r4LeftTitle = document.querySelector('#left-title');
  const r4DagHint = document.querySelector('#dag-hint');
  const r4Legend = document.querySelector('#legend');
  const r4RunKicker = document.querySelector('#run-kicker');
  const r4RunTitle = document.querySelector('#run-title');
  const r4ModeLabel = document.querySelector('#mode-label');
  const r4ModeHelp = document.querySelector('#mode-help');
  const r4EventCounter = document.querySelector('#event-counter');
  const r4CurrentAction = document.querySelector('#current-action');
  const r4Timeline = document.querySelector('#timeline');
  const r4CodeTitle = document.querySelector('#code-title');
  const r4CodeFile = document.querySelector('#code-file');
  const r4CodePanel = document.querySelector('#code-panel');
  const r4ExplainBody = document.querySelector('#explain-body');
  const r4SupportKicker = document.querySelector('#support-kicker');
  const r4CitationTitle = document.querySelector('#citation-title');
  const r4CitationList = document.querySelector('#citation-list');
  const r4TraceDetail = document.querySelector('#trace-detail');
  const r4RuntimeDetail = document.querySelector('#runtime-detail');
  const r4RawEvent = document.querySelector('#raw-event');

  const r4Pretty = (value) => JSON.stringify(value, null, 2);
  const r4Escape = (value) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

  async function r4PostHealth() {
    const response = await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'source_health'}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  function r4StatusClass(item) {
    return item.ready ? 'completed' : 'failed';
  }

  function r4CredentialLabel(item) {
    if (item.credential_names && item.credential_names.length) {
      return `${item.credential_names.join(', ')}: ${item.credentials_present ? 'PRESENT' : 'MISSING'}`;
    }
    if (item.optional_credential_names && item.optional_credential_names.length) {
      return `${item.optional_credential_names.join(', ')}: ${item.optional_credentials_present ? 'PRESENT · registered quota' : 'OPTIONAL · anonymous quota'}`;
    }
    return 'No API key required';
  }

  function r4RenderPlan(report) {
    r4LeftKicker.textContent = 'SOURCE API HEALTH';
    r4LeftTitle.textContent = 'BLS / FRED / EIA';
    r4DagHint.innerHTML = '<span>TLS</span><span>→</span><span>AUTH</span><span>→</span><span>JSON</span><span>→</span><span>EVIDENCE</span>';
    r4Legend.style.display = 'none';
    r4PlanList.innerHTML = '';

    (report.results || []).forEach((item) => {
      const card = document.createElement('article');
      card.className = `task-card ${r4StatusClass(item)}`;
      const freshness = item.freshness || 'UNKNOWN';
      card.innerHTML = `
        <div class="task-head">
          <span class="task-id">${r4Escape(item.provider)}</span>
          <span class="status-chip ${r4StatusClass(item)}">${r4Escape(item.status)}</span>
        </div>
        <strong>${r4Escape(item.series_id)}</strong>
        <small>${r4Escape(r4CredentialLabel(item))}</small>
        <div class="source-row">
          <span>${r4Escape(freshness)}</span>
          <strong>${r4Escape(item.as_of || '—')}</strong>
          <small>${item.age_days == null ? 'age —' : `age ${r4Escape(item.age_days)}d`}</small>
        </div>`;
      r4PlanList.appendChild(card);
    });
  }

  function r4RenderTimeline(report) {
    r4Timeline.innerHTML = '';
    (report.results || []).forEach((item, index) => {
      const li = document.createElement('li');
      li.className = item.ready ? 'completed' : 'failed';
      const transport = item.transport ? ` · ${item.transport}` : '';
      const latency = item.latency_ms == null ? '—' : `${item.latency_ms} ms`;
      const error = item.error_message ? `<small>${r4Escape(item.error_message)}</small>` : '';
      const recovery = item.recovery_hint ? `<small><strong>Recovery:</strong> ${r4Escape(item.recovery_hint)}</small>` : '';
      li.innerHTML = `
        <div class="timeline-index">${index + 1}</div>
        <div>
          <strong>${r4Escape(item.provider)} · ${r4Escape(item.status)}</strong>
          <span>${r4Escape(item.endpoint)}${r4Escape(transport)} · ${r4Escape(latency)}</span>
          ${error}
          ${recovery}
        </div>`;
      r4Timeline.appendChild(li);
    });
  }

  function r4RenderDetails(report) {
    r4SupportKicker.textContent = 'SOURCE HEALTH';
    r4CitationTitle.textContent = `${report.overall} · ${report.ready_count}/${report.total}`;
    r4CitationList.innerHTML = '';

    (report.results || []).forEach((item) => {
      const row = document.createElement('article');
      row.className = `eval-check-card ${item.ready ? 'pass' : 'fail'}`;
      const checks = (item.checks || [])
        .map((check) => `${check.check}: ${check.passed ? 'PASS' : 'FAIL'} — ${check.detail}`)
        .join('\n');
      const recovery = item.recovery_hint ? `<span>Recovery: ${r4Escape(item.recovery_hint)}</span>` : '';
      row.innerHTML = `
        <strong>${r4Escape(item.provider)} · ${r4Escape(item.status)}</strong>
        <span>Series: ${r4Escape(item.series_id)}</span>
        <span>Credential: ${r4Escape(r4CredentialLabel(item))}</span>
        <span>As-of: ${r4Escape(item.as_of || '—')} · Freshness: ${r4Escape(item.freshness)}</span>
        <span>Endpoint: ${r4Escape(item.endpoint)}</span>
        ${recovery}
        <pre><code>${r4Escape(checks)}</code></pre>`;
      r4CitationList.appendChild(row);
    });
  }

  function r4Render(report) {
    r4RenderPlan(report);
    r4RenderTimeline(report);
    r4RenderDetails(report);

    r4PlanStatus.textContent = 'source health';
    r4PlanProgress.textContent = `${report.ready_count} / ${report.total}`;
    r4EvidenceCount.textContent = `${report.results.filter((item) => item.evidence_id).length}`;
    r4TraceKpi.textContent = 'SMOKE';
    r4EvalKpi.textContent = report.overall;
    r4FinalResult.textContent = `${report.ready_count}/${report.total} READY`;
    r4PlanBadge.textContent = report.overall;
    r4PlanBadge.className = `badge ${report.ready ? 'completed' : 'neutral'}`;

    r4RunKicker.textContent = 'REAL API SMOKE TEST';
    r4RunTitle.textContent = 'TLS → Auth → Response → Evidence';
    r4ModeLabel.textContent = 'R4 SOURCE HEALTH';
    r4ModeHelp.textContent = 'Same production adapters as research; no fixture mode';
    r4EventCounter.textContent = report.checked_at || 'checked';
    r4CurrentAction.innerHTML = report.ready
      ? '<strong>全部数据源 API 可用</strong><span>API readiness 与 freshness 已分别检查。</span>'
      : `<strong>数据源未全部 READY</strong><span>${r4Escape(report.overall)}；查看右侧具体 provider 和 recovery hint。</span>`;

    r4CodeTitle.textContent = 'SourceHealthChecker：真实 source contract';
    r4CodeFile.textContent = 'r4_source_health.py';
    r4CodePanel.textContent = [
      'for provider in BLS / FRED / EIA:',
      '    verify required / optional credentials',
      '    call production adapter',
      '    classify rate limit / TLS / HTTP / auth',
      '    validate normalized Evidence contract',
      '    report as_of + freshness separately',
      '',
      'BLS_API_KEY is optional: anonymous quota without it, registered quota with it.',
      'Never expose API key values.',
    ].join('\n');
    r4ExplainBody.innerHTML = '<p><strong>API READY ≠ data is fresh ≠ quota is available.</strong> R4 separates transport/auth/contract health, provider rate limits, and observation freshness. BLS can run anonymously, while optional BLS_API_KEY switches production requests to registered v2 quota.</p>';
    r4TraceDetail.textContent = r4Pretty({
      note: 'Source Health runs outside the Agent task trace because it diagnoses the infrastructure boundary itself.',
      checked_at: report.checked_at,
    });
    r4RuntimeDetail.textContent = r4Pretty(report);
    r4RawEvent.textContent = r4Pretty({action: 'source_health', source_health: report});
  }

  r4HealthButton.addEventListener('click', async () => {
    r4HealthButton.disabled = true;
    const original = r4HealthButton.textContent;
    r4HealthButton.textContent = '测试中…';
    r4CurrentAction.innerHTML = '<strong>正在测试真实 API</strong><span>BLS → FRED → EIA；使用生产 TLS 和 adapter。</span>';
    try {
      const payload = await r4PostHealth();
      if (!payload.source_health) {
        throw new Error(payload.error && payload.error.message ? payload.error.message : 'No source health report');
      }
      r4Render(payload.source_health);
    } catch (error) {
      r4PlanStatus.textContent = 'health error';
      r4FinalResult.textContent = 'ERROR';
      r4CurrentAction.innerHTML = `<strong>Source Health 执行失败</strong><span>${r4Escape(error.message)}</span>`;
      r4RuntimeDetail.textContent = r4Pretty({error: error.message});
    } finally {
      r4HealthButton.disabled = false;
      r4HealthButton.textContent = original;
    }
  });
})();
