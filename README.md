# Agent Engineering from Scratch

A step-by-step learning repository for building an agent runtime from first principles.

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

## Current stage: V3

V1 protected the Tool boundary. V2 constrained the model with Model Response Validation and `MAX_STEPS`. V3 separates two kinds of repetition that look similar in a trace but belong to different layers.

```text
User
  ↓
Model Adapter
  ↓
Model Response Validator
  ↓
MAX_STEPS Budget
  ↓
Duplicate Tool Call Detector    ← did the Model propose this exact action before?
  ↓
Tool Registry
  ↓
Tool Argument Validator
  ↓
Retry Executor                  ← retry transient execution failures internally
  ↓
Python Tool
  ↓
Observation
  ↓
Model
  ↓
Final Answer or Runtime Stop
```

The core distinction is:

```text
Runtime Retry
same Model Tool Call
    ↓
Tool Attempt #1 → Timeout
    ↓
Tool Attempt #2 → Success

Model Duplicate Loop
Tool Call A → Observation
    ↓
Model proposes Tool Call A again
    ↓
Duplicate Detector blocks second execution
```

A retry does **not** consume another Model step. It is the Runtime repeating the same action because execution failed transiently. A duplicate Tool Call is a new Model decision and therefore does consume another `MAX_STEPS` slot.

`max_retries=2` means:

```text
initial attempt + retry #1 + retry #2 = at most 3 Tool executions
```

Only selected transient exceptions are retryable in V3:

```python
RETRYABLE_ERRORS = (TimeoutError, ConnectionError)
```

Deterministic validation errors and ordinary Python exceptions are not blindly retried.

### V3 deterministic scenarios

The visual debugger can reproduce these cases without an API key:

- `success` — normal Tool Call completes on the first attempt
- `retry_success` — `flaky_calculator` raises `TimeoutError` once, Runtime retries, second attempt succeeds
- `duplicate_loop` — Model proposes exactly the same `calculator` call twice; second real execution is blocked
- `infinite_loop` — Model keeps proposing different valid calls; duplicate detection does not fire and `MAX_STEPS` remains the guard
- `malformed_response` — Model Response contract fails before Tool lookup
- `unknown_tool` — Registry rejects an unavailable capability
- `missing_argument` — Tool validator rejects missing data
- `invalid_operation` — Tool validator rejects an invalid value

The important principle is:

> Retry handles execution uncertainty. Replanning handles decision uncertainty.

V3 still does not implement model replanning logic explicitly; it only creates structured Observations that a real model could use to choose a different next action.

## Run deterministic Agent Runtime

```bash
python agent.py
```

## Run the visual debugger

```bash
python serve_visualizer.py
```

Then open:

```text
http://127.0.0.1:8000
```

The browser lets you:

- choose deterministic success/failure/loop/retry scenarios
- change `MAX_STEPS`
- change `MAX_RETRIES`
- step through real Runtime events
- see each Tool attempt separately
- see transient failure trigger a Runtime retry without another Model call
- see exact duplicate Model actions blocked before second Tool execution
- compare duplicate loops with changing-argument loops that require `MAX_STEPS`
- inspect matching Python code, Chinese commentary, and raw event payloads

## Run with a real OpenAI model

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_api_key_here"
python run_real.py
```

Secrets are never stored in source code.

## Test

```bash
python -m unittest -v
```

Tests are deterministic and API-free. CI verifies Python syntax, browser JavaScript syntax, Tool/Model validation, MAX_STEPS, transient retry behavior, retry exhaustion, and exact duplicate Tool Call blocking.
