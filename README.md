# Agent Engineering from Scratch

A step-by-step learning repository for building an Agent Runtime from first principles.

The goal is to understand the system underneath agent frameworks before using LangGraph, Agents SDKs, or other abstractions.

## Learning roadmap

- V0 — Minimal Agent Loop
- V0.1 — Replaceable Model Adapter
- V0.2 — Visual Runtime Debugger
- V1 — Tool Registry + Basic Validation
- V2 — MAX_STEPS + Model Response Validation
- V3 — Retry + Loop Detection
- V4 — Tool Object
- V5 — Policy Engine
- V6 — ExecutionContext
- V7 — StateStore
- V8 — Checkpoint / Durable Execution
- V9 — Planner + DAG Scheduler
- V10 — Evidence / Synthesis / Citation
- V11 — Tracing + Evals

## Current stage: V8 — Checkpoint / Durable Execution

V7 made AgentState explicit and visible, but its `InMemoryStateStore` disappeared when the Python process died. V8 makes selected Runtime state durable on disk.

The teaching experiment is deliberately concrete:

```text
Step 1
calculator(10, 20, add)
    ↓
30
    ↓
AgentState.phase = observation_ready
    ↓
JsonCheckpointStore.save(...)
    ↓
💥 simulated process crash

NEW Runtime + NEW Model object
    ↓
JsonCheckpointStore.load(task_id)
    ↓
recover Observation = 30
    ↓
DO NOT execute 10 + 20 again
    ↓
send saved Observation back to Model
    ↓
Step 2: calculator(6, 7, multiply)
    ↓
42
    ↓
Final Answer
```

### Why `observation_ready` is the V8 recovery boundary

V8 resumes only from a checkpoint where the Tool result has already been recorded:

```text
Tool execution
    ↓
Observation produced
    ↓
state.record_observation(...)
    ↓
checkpoint saved to disk
    ↓
SAFE DEMO CRASH POINT
```

The checkpoint also persists the continuation identifiers needed to continue model reasoning:

```python
AgentState(
    ...,
    last_observation=30,
    pending_response_id="...",
    pending_call_id="...",
    seen_calls=[...],
)
```

A fresh Runtime can therefore continue from the saved Observation instead of re-running the completed Tool.

### Durable StateStore

V8 adds `JsonCheckpointStore`:

```python
store = JsonCheckpointStore(".checkpoints")
store.save(state, reason="observation_recorded")
state = store.load(task_id)
history = store.history(task_id)
```

Writes use a temporary file plus `os.replace` so the local checkpoint document is atomically replaced.

The `.checkpoints/` directory is ignored by Git and exists only as local Runtime data.

### Checkpoint is NOT exactly-once execution

This distinction is essential.

A checkpoint can tell the Runtime what state was durably recorded. It cannot magically prove whether an external side effect happened if the process died in this window:

```text
send_email() actually succeeds
    ↓
💥 crash BEFORE post-effect checkpoint
```

After restart, the checkpoint may still say the action was not completed, even though the external email was sent.

Production systems therefore combine durable execution with mechanisms such as:

```text
idempotency keys
transactional outbox
provider request IDs
side-effect receipts
workflow-engine activity semantics
```

V8 intentionally does not claim exactly-once behavior.

## Visual debugger

Run:

```bash
python serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

Recommended sequence:

1. Select `两步任务 · Crash / Resume`.
2. Click `① 运行到 Crash`.
3. Walk the Trace until `Checkpoint Saved · observation_ready` and `💥 Simulated Crash`.
4. Confirm the checkpoint dashboard shows one saved Observation: `30`.
5. Click `② 从 Checkpoint 恢复`.
6. The Trace inserts `NEW PROCESS / RUNTIME`.
7. Confirm `Checkpoint Loaded` and `Resume Boundary` appear.
8. Confirm the Resume segment contains only the second Tool attempt: `6 × 7`.
9. Final State contains observations `[30, 42]`.

The page keeps four views synchronized:

```text
Trace        → what just happened
AgentState   → where the Agent is and what it already knows
Checkpoint   → what survives process death
Code         → which Runtime line caused the transition
Commentary   → why this transition is safe / what happens next
```

## Tests

```bash
python -m unittest -v
```

V8 tests verify:

- JSON checkpoint state survives a brand-new Store instance;
- crash occurs only after Observation 30 is durable;
- a fresh Runtime + fresh FakeModel can resume;
- resumed execution does not re-run the completed `10 + 20` Tool;
- final durable State contains both `30` and `42`;
- resume without a checkpoint fails closed;
- all prior Runtime, Policy, Context, Retry, MAX_STEPS, duplicate, and validation behavior remains covered.

## Run with a real OpenAI model

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_api_key_here"
python run_real.py
```

Secrets are never stored in source code.
