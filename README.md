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

## Current stage: V1

V0 introduced the smallest possible Agent Loop. V0.1 made the model provider replaceable. V0.2 made execution observable in the browser.

V1 adds the first explicit **trust boundary** around model-proposed tool calls:

```text
User
  ↓
Model proposes Tool Call
  ↓
Runtime
  ↓
Tool Registry         ← does this capability exist?
  ↓
Argument Validator    ← are the arguments valid?
  ↓
Python Tool           ← execute only if validation passed
  ↓
Observation           ← success OR structured error
  ↓
Model
  ↓
Final Answer
```

The important change is that the runtime no longer does this blindly:

```python
tool = tool_registry[tool_name]
result = tool(**arguments)
```

Instead it resolves and validates first. Unknown tool names, missing arguments, and invalid values are converted into structured Observations rather than uncaught Python exceptions.

> Model proposes an action. Runtime decides whether that proposal is executable.

### V1 deterministic failure scenarios

The visual debugger can reproduce four scenarios without an API key:

- `success` — valid calculator call reaches Python execution
- `unknown_tool` — Registry miss becomes `unknown_tool`
- `missing_argument` — call is rejected before execution
- `invalid_operation` — invalid enum-like value is rejected before execution

The rejected scenarios intentionally never emit `tool_execute`.

## Run deterministic Agent Runtime

```bash
python agent.py
```

This uses `FakeModel`, so it requires no API key.

## Run the visual debugger

```bash
python serve_visualizer.py
```

Then open:

```text
http://127.0.0.1:8000
```

In the browser you can choose a scenario and then:

- run the real deterministic Python runtime
- step forward and backward through execution events
- auto-play the complete Agent Loop
- watch Registry and Validator nodes light up
- verify rejected calls never reach the Calculator node
- see the matching Python code for each step
- read Chinese design commentary
- inspect the raw runtime event payload

## Run with a real OpenAI model

Install the SDK:

```bash
pip install -r requirements.txt
```

Set your API key in the environment:

```bash
export OPENAI_API_KEY="your_api_key_here"
```

Then run:

```bash
python run_real.py
```

The real adapter uses the OpenAI Responses API function-calling loop. Secrets are never stored in source code.

## Test

```bash
python -m unittest -v
```

Tests are deterministic and API-free. CI checks Python syntax, browser JavaScript syntax, successful tool execution, Registry misses, argument rejection, and visual trace behavior.
