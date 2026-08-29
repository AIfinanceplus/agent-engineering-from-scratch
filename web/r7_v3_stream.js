/* UI V3 Step 2: consume the real R7 NDJSON stream and progressively grow appState.run. */

appState.live = {
  active: false,
  currentNode: 'Q',
  followLive: true,
  receivedMessages: 0,
};

function hasEvent(type) {
  return (appState.run?.events || []).some((event) => event.type === type);
}

function hasCheckpoint(boundary) {
  return (appState.run?.checkpoints || []).some((cp) => cp.boundary === boundary);
}

function streamNodeState(node) {
  const run = appState.run;
  if (!run) return 'waiting';
  const tasks = taskMap();

  if (node === 'Q') return hasEvent('research_question_received') ? 'completed' : (appState.live.active ? 'running' : 'waiting');
  if (node === 'DEC') {
    if (hasEvent('decomposition_created')) return 'completed';
    return hasEvent('research_question_received') && appState.live.active ? 'running' : 'waiting';
  }
  if (node === 'QC') {
    if (hasEvent('queries_compiled')) return 'completed';
    return hasEvent('decomposition_created') && appState.live.active ? 'running' : 'waiting';
  }
  if (node === 'QN') {
    const qs = Object.values(tasks).filter((task) => String(task.task_id).startsWith('Q'));
    if (!qs.length) return hasEvent('plan_created') && appState.live.active ? 'running' : 'waiting';
    if (qs.some((task) => task.status === 'failed')) return 'failed';
    if (qs.every((task) => task.status === 'completed')) return 'completed';
    if (qs.some((task) => ['running','ready'].includes(task.status))) return 'running';
    return hasEvent('plan_created') ? 'running' : 'waiting';
  }
  if (node === 'E') {
    if (hasCheckpoint('after_evidence')) return 'completed';
    if ((run.evidence || []).length) return 'running';
    return nodeState('QN') === 'running' ? 'ready' : 'waiting';
  }
  if (node === 'S1' || node === 'D1' || node === 'F1') {
    const status = tasks[node]?.status;
    if (status === 'completed' || status === 'failed' || status === 'running') return status;
    if (status === 'ready') return 'ready';
    return 'waiting';
  }
  if (node === 'EV') {
    if (appState.evalSuite) return 'completed';
    if (run.ok === false) return 'waiting';
    if (run.ok === true || hasEvent('plan_completed')) return 'ready';
    return 'waiting';
  }
  return 'waiting';
}

// renderFlow resolves nodeState at render time, so replacing this binding upgrades
// the existing V3 renderer without duplicating the whole UI implementation.
nodeState = streamNodeState;

function liveNodeForEvent(event) {
  if (!event) return null;
  const type = event.type;
  if (type === 'research_question_received') return 'Q';
  if (type === 'decomposition_created') return 'DEC';
  if (type === 'queries_compiled' || type === 'domain_lens_selected') return 'QC';
  if (type === 'plan_created' || type === 'scheduler_tick') return 'QN';
  if (type === 'evidence_registered') return 'E';
  if (type === 'task_started' || type === 'task_completed' || type === 'task_failed') {
    const id = String(event.task_id || '');
    if (id.startsWith('Q')) return 'QN';
    if (['S1','D1','F1'].includes(id)) return id;
  }
  if (type === 'synthesis_verified') {
    const id = String(event.task_id || '');
    if (['S1','D1','F1'].includes(id)) return id;
  }
  if (type === 'quality_assessed') return 'S1';
  if (type === 'domain_brief_created') return 'D1';
  if (type === 'forecast_pack_created' || type === 'forecast_pack_saved') return 'F1';
  if (type === 'plan_completed') return 'EV';
  return null;
}

function ensureLiveRun(message) {
  const question = message.question || $('#goal').value.trim();
  const domain = message.domain || $('#domain').value;
  appState.run = {
    ok: null,
    action: 'r7_run',
    run_id: message.run_id || null,
    question,
    domain,
    reference_date: message.reference_date || null,
    execution_context: null,
    blueprint: {subquestions: [], intents: [], queries: []},
    plan: null,
    results: {},
    research_synthesis: null,
    domain_brief: null,
    forecast_pack: null,
    final_result: null,
    final_artifact: null,
    evidence: [],
    citations: [],
    trace: null,
    events: [],
    checkpoints: [],
    latest_checkpoint: null,
  };
}

function upsertEvidence(evidence) {
  if (!evidence?.evidence_id) return;
  const rows = appState.run.evidence || (appState.run.evidence = []);
  const index = rows.findIndex((row) => row.evidence_id === evidence.evidence_id);
  if (index >= 0) rows[index] = evidence;
  else rows.push(evidence);
}

function applyLiveEvent(event) {
  const run = appState.run;
  if (!run || !event) return;
  (run.events || (run.events = [])).push(event);

  if (event.plan) run.plan = event.plan;
  if (event.type === 'decomposition_created') {
    run.blueprint.subquestions = event.subquestions || [];
    run.blueprint.intents = event.intents || [];
  } else if (event.type === 'queries_compiled') {
    run.blueprint.queries = event.queries || [];
  } else if (event.type === 'evidence_registered') {
    upsertEvidence(event.evidence);
  } else if (event.type === 'task_completed') {
    run.results[event.task_id] = event.result;
    if (event.task_id === 'S1') run.research_synthesis = event.result;
    if (event.task_id === 'D1') run.domain_brief = event.result;
    if (event.task_id === 'F1') {
      run.forecast_pack = event.result;
      run.final_artifact = event.result;
    }
  } else if (event.type === 'task_failed') {
    run.ok = false;
    run.error = event.error || {message: 'Task failed'};
  } else if (event.type === 'synthesis_verified') {
    if (Array.isArray(event.citations)) run.citations = event.citations;
  } else if (event.type === 'forecast_pack_created') {
    if (run.forecast_pack) {
      run.forecast_pack.pack_id = event.pack_id || run.forecast_pack.pack_id;
    }
  } else if (event.type === 'plan_completed') {
    run.plan = event.plan || run.plan;
    run.final_result = event.final_result;
    run.final_artifact = event.final_artifact || run.final_artifact;
    run.evidence = event.evidence || run.evidence;
    run.citations = event.citations || run.citations;
    run.trace = event.trace || run.trace;
    run.results = event.results || run.results;
  }

  const node = liveNodeForEvent(event);
  if (node) {
    appState.live.currentNode = node;
    if (appState.live.followLive) appState.selectedNode = node;
  }
}

function applyLiveCheckpoint(checkpoint) {
  const run = appState.run;
  if (!run || !checkpoint?.checkpoint_id) return;
  const rows = run.checkpoints || (run.checkpoints = []);
  const index = rows.findIndex((cp) => cp.checkpoint_id === checkpoint.checkpoint_id);
  if (index >= 0) rows[index] = checkpoint;
  else rows.push(checkpoint);
  run.latest_checkpoint = checkpoint;
  appState.selectedCheckpointId = checkpoint.checkpoint_id;

  const node = ({
    after_plan_created: 'DEC',
    after_evidence: 'E',
    after_S1: 'S1',
    after_D1: 'D1',
    after_F1: 'F1',
  })[checkpoint.boundary];
  if (node) {
    appState.live.currentNode = node;
    if (appState.live.followLive) appState.selectedNode = node;
  }
}

let liveRenderQueued = false;
function scheduleLiveRender() {
  if (liveRenderQueued) return;
  liveRenderQueued = true;
  requestAnimationFrame(() => {
    liveRenderQueued = false;
    renderHeaderAndInput();
    renderFlow();
    renderDetail();
    renderInspector();
    renderStatusBar();
  });
}

function handleStreamMessage(message) {
  if (!message || message.protocol !== 'r7-ndjson-v1') return;
  appState.live.receivedMessages += 1;

  if (message.type === 'start') {
    ensureLiveRun(message);
    appState.live.active = true;
    appState.live.currentNode = 'Q';
    appState.live.followLive = true;
    appState.selectedNode = 'Q';
    appState.selectedDetailTab = 'trace';
    appState.selectedInspectorTab = 'output';
    appState.selectedCheckpointId = null;
    appState.evalSuite = null;
  } else if (message.type === 'event') {
    applyLiveEvent(message.event);
  } else if (message.type === 'checkpoint') {
    applyLiveCheckpoint(message.checkpoint);
  } else if (message.type === 'result') {
    appState.run = message.result;
    appState.live.active = false;
    appState.live.currentNode = message.result?.ok ? 'EV' : appState.live.currentNode;
    appState.selectedCheckpointId = message.result?.latest_checkpoint?.checkpoint_id || appState.selectedCheckpointId;
    if (appState.live.followLive) appState.selectedNode = message.result?.ok ? 'F1' : appState.selectedNode;
  } else if (message.type === 'error') {
    appState.live.active = false;
    if (appState.run) {
      appState.run.ok = false;
      appState.run.error = message.error;
    }
    toast(`Stream error: ${message.error?.message || 'unknown error'}`);
  }
  scheduleLiveRender();
}

async function streamRunResearch() {
  const question = $('#goal').value.trim();
  if (!question) return toast('请输入研究问题');

  appState.live.active = true;
  appState.live.followLive = true;
  appState.live.receivedMessages = 0;
  setBusy(true, 'STREAMING');
  ensureLiveRun({question, domain: $('#domain').value});
  renderAll();

  try {
    const response = await fetch('/api/stream', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        action: 'r7_run',
        goal: question,
        domain: $('#domain').value,
        context_preset: $('#context-preset').value,
      }),
    });
    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`;
      try {
        const payload = await response.json();
        errorMessage = payload.error?.message || payload.error || errorMessage;
      } catch (_) {}
      throw new Error(errorMessage);
    }
    if (!response.body) throw new Error('Streaming response body is unavailable in this browser');

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        handleStreamMessage(JSON.parse(line));
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) handleStreamMessage(JSON.parse(buffer));

    const result = appState.run;
    if (!result) throw new Error('Stream ended without a result');
    if (result.forecast_pack?.pack_id) await loadForecastPacks(result.forecast_pack.pack_id);
    toast(result.ok ? `Live run completed · ${appState.live.receivedMessages} messages` : `Run failed: ${result.error?.message || 'unknown error'}`);
  } catch (error) {
    appState.live.active = false;
    if (appState.run) {
      appState.run.ok = false;
      appState.run.error = {code: error.name || 'stream_error', message: error.message};
    }
    toast(`Live run error: ${error.message}`);
  } finally {
    appState.live.active = false;
    setBusy(false);
    renderAll();
  }
}

// The base V3 button already has a one-shot run listener. Replacing the node removes
// that listener while keeping the same id/classes so all existing render helpers work.
const oldRunButton = $('#run-btn');
if (oldRunButton) {
  const liveRunButton = oldRunButton.cloneNode(true);
  oldRunButton.replaceWith(liveRunButton);
  liveRunButton.addEventListener('click', streamRunResearch);
}

// The keyboard shortcut in the base script resolves runResearch at keydown time.
runResearch = streamRunResearch;

// Clicking a node during a live run pauses auto-follow so the user can inspect it.
$$('.node').forEach((node) => node.addEventListener('click', () => {
  if (appState.live.active) appState.live.followLive = false;
}));
