/* R8 Eval Current Run: evaluate the existing run artifact without source re-fetch. */

async function evaluateCurrentR8Run() {
  if (!appState.run) {
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
  try {
    const response = await fetch('/api/r8/eval', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({research_result: appState.run}),
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
    toast(`Current Run Evals: ${appState.evalSuite?.passed || 0}/${appState.evalSuite?.total || 0} passed · no source fetch`);
  } catch (error) {
    toast(`Eval error: ${error.message}`);
  } finally {
    setBusy(false);
    renderStatusBar();
  }
}

// r7_v3.js already attached the legacy "rerun research then eval" listener.
// Cloning removes that listener while preserving the same DOM contract/styling.
const r8OldEvalButton = $('#eval-btn');
if (r8OldEvalButton) {
  const r8CurrentEvalButton = r8OldEvalButton.cloneNode(true);
  r8CurrentEvalButton.title = 'Evaluate the current Run without fetching sources again';
  r8OldEvalButton.replaceWith(r8CurrentEvalButton);
  r8CurrentEvalButton.addEventListener('click', evaluateCurrentR8Run);
}

// Keep the global action semantically aligned for future callers.
runEvals = evaluateCurrentR8Run;
