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

## Current stage: V2

V1 protected the Tool boundary. V2 protects the Runtime from the model itself.

```text
User
  ↓
Model Adapter
  ↓
Model Response Validator   ← is the normalized response contract valid?
  ↓
MAX_STEPS Budget           ← may another Tool Call execute?
  ↓
Tool Registry              ← does this capability exist?
  ↓
Tool Argument Validator    ← are its arguments valid?
  ↓
Python Tool
  ↓
Observation
  ↓
Model
  ↓
Final Answer or Runtime Stop
```

Two different ideas matter:

1. **Model response validation** checks whether Runtime can safely interpret the model output at all.
2. **MAX_STEPS** limits the total number of Tool Call attempts even when every individual call is valid.

> A valid action is not automatically allowed to run forever.

### V2 deterministic scenarios

The visual debugger can reproduce these cases without an API key:

- `success` — normal Tool Call completes
- `unknown_tool` — Registry rejects an unavailable capability
- `missing_argument` — Tool validator rejects missing data
- `invalid_operation` — Tool validator rejects an invalid value
- `malformed_response` — Model Response contract fails before Tool lookup
- `infinite_loop` — Model repeatedly proposes valid Tool Calls until Runtime hits `MAX_STEPS`

For the looping scenario, try `MAX_STEPS = 1`, `2`, and `3` and compare the trace. The next Tool Call is refused before execution.

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

- choose deterministic success and failure scenarios
- change `MAX_STEPS`
- step through real Runtime events
- watch Model Validator and Step Budget nodes light up
- see rejected actions stop before Tool execution
- inspect matching Python code and Chinese commentary
- inspect raw Runtime event payloads

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

Tests are deterministic and API-free. CI verifies Python syntax, browser JavaScript syntax, Tool validation, Model Response validation, and the MAX_STEPS loop guard.
