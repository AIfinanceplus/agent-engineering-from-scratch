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

## Current stage: V7 — AgentState + StateStore

V6 answered **who is executing?** V7 answers two new Runtime questions:

> Where has the Agent reached?
>
> What results has it already accumulated?

Previously these facts lived in temporary Python variables such as `tool_steps`, `observation`, and the current Tool Call. V7 makes them explicit:

```python
AgentState(
    task_id=...,
    status="running",
    phase="model_thinking",
    step=1,
    max_steps=4,
    current_tool="calculator",
    current_arguments={...},
    observations=[...],
    last_observation=...,
    final_answer=None,
    stop_reason=None,
)
```

The Runtime saves meaningful transitions to a `StateStore`:

```text
received_input
    ↓
model_thinking
    ↓
tool_selected
    ↓
validating_tool
    ↓
checking_policy
    ↓
executing_tool
    ↓
observation_ready
    ↓
model_thinking
    ↓
...
    ↓
completed / stopped
```

### State vs Trace

They serve different purposes:

```text
Trace
= what just happened, event by event

AgentState
= what is true right now
```

The visual debugger synchronizes them. Clicking any Trace event shows the most recent StateStore snapshot that existed at that exact point in execution, while keeping the matching code and Chinese explanation visible.

### Two-step teaching scenario

Run `两步任务 · 观察 State 累积`:

```text
Step 1
calculator(10, 20, add)
    ↓
Observation = 30
    ↓
State.observations = [30]
    ↓
Model decides next Tool

Step 2
calculator(6, 7, multiply)
    ↓
Observation = 42
    ↓
State.observations = [30, 42]
    ↓
Final Answer
```

This makes the difference between a temporary Tool result and accumulated Agent State visible.

### StateStore contract

V7 introduces:

```python
StateStore.save(state, reason=...)
StateStore.load(task_id)
StateStore.history(task_id)
```

The implementation is intentionally `InMemoryStateStore`. It snapshots state and supports `save/load/history`, but it **does not survive a process restart**.

That boundary is deliberate:

```text
V7 StateStore
= represent and store Runtime state during the process

V8 Checkpoint / Durable Execution
= persist recoverable state across failure/restart
```

## Run the visual debugger

```bash
python serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

Recommended first run:

1. Choose `两步任务 · 观察 State 累积`.
2. Click `运行真实 V7`.
3. Use `下一步` instead of autoplay at first.
4. Watch `Phase`, `Step`, `Current Tool`, and `已经拿到的结果` change.
5. Compare every `State Saved` event with the code panel beside it.

## Run deterministic tests

```bash
python -m unittest -v
```

Tests verify StateStore snapshot semantics, `save/load/history`, two-step result accumulation, state phase transitions, persistence of stop reasons and previous observations, ExecutionContext/Policy behavior, retry, MAX_STEPS, duplicate protection, and validation.

## Run with a real OpenAI model

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_api_key_here"
python run_real.py
```

Secrets are never stored in source code.
