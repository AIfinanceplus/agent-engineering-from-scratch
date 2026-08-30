/* R8/R9 Eval Current Run: evaluate the registered run without source re-fetch. */

async function evaluateCurrentR8Run() {
  if (!appState.run?.run_id) {
    toast('请先运行一次 Research，再评估当前 Run');
    return;
  }
  if (appState.live?.active) {
    toast('Research 仍在运行，请等待当前 Run 完成');
    return;
  }
  if (!appState.run.blueprint?.queries?.length) {
    toast('当前 Run 没有完整 blueprint，无法执行 Eval');
    return;
  }

  setBusy(true, 'EVALUATING CURRENT RUN');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch('/api/eval/current', {
      method: 'POST',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({run_id: appState.run.run_id}),
      signal: controller.signal,
    });
    const raw = await response.text();
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch (_) {
      throw new Error(`Eval endpoint returned non-JSON response (HTTP ${response.status})`);
    }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error?.message || payload.error || `HTTP ${response.status}`);
    }
    appState.evalSuite = payload.eval_suite || null;
    appState.selectedNode = 'EV';
    appState.selectedInspectorTab = 'eval';
    appState.selectedDetailTab = 'trace';
    renderAll();
    toast(`Current Run Evals: ${appState.evalSuite?.passed || 0}/${appState.evalSuite?.total || 0} passed · ${payload.eval_transport || 'no source fetch'}`);
  } catch (error) {
    const transportFailure = error?.name === 'AbortError' || (error instanceof TypeError && /fetch/i.test(error.message || ''));
    const message = transportFailure
      ? 'Eval transport unavailable：确认当前 server 是 serve_r8.py / serve_r9.py，并强制刷新页面后重新 Run Research'
      : error.message;
    toast(`Eval error: ${message}`);
  } finally {
    clearTimeout(timer);
    setBusy(false);
    renderStatusBar();
  }
}

const r8OldEvalButton = $('#eval-btn');
if (r8OldEvalButton) {
  const r8CurrentEvalButton = r8OldEvalButton.cloneNode(true);
  r8CurrentEvalButton.title = 'Evaluate the registered current Run without fetching sources again';
  r8OldEvalButton.replaceWith(r8CurrentEvalButton);
  r8CurrentEvalButton.addEventListener('click', evaluateCurrentR8Run);
}
runEvals = evaluateCurrentR8Run;
