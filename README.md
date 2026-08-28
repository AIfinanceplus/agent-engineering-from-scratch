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

## Current stage: V4 — Tool Object

V3 worked, but one capability was defined in several places: Python function in `tools.py`, validation rules elsewhere, model-facing JSON schema in `model_adapters.py`, and retry policy in Runtime configuration. That creates **configuration drift**.

V4 changes the Registry from:

```text
name → callable
```

to:

```text
name → Tool Object
```

A Tool now owns:

```python
Tool(
    name=...,
    description=...,
    parameters=...,
    function=...,
    max_retries=...,
    retryable_errors=...,
)
```

The same object is used to:

```text
Tool.parameters
   ├─→ Model schema
   └─→ Runtime argument validation

Tool.function
   └─→ real Python execution

Tool.max_retries + retryable_errors
   └─→ Runtime retry behavior
```

This makes the Tool definition the **single source of truth**.

### Why the retry example now makes more sense

`calculator` declares:

```text
max_retries = 0
```

`flaky_calculator` declares:

```text
max_retries = 2
retryable_errors = TimeoutError / ConnectionError
```

So Runtime does not globally decide that "all tools retry twice". It resolves the specific Tool Object and reads that capability's policy.

```text
Model proposes flaky_calculator
        ↓
Registry resolves Tool Object
        ↓
Tool.max_retries = 2
        ↓
Attempt 1 → TimeoutError
        ↓
Runtime Retry
        ↓
Attempt 2 → Success
```

The normal `calculator` would not retry a transient failure by default because its Tool Object says `max_retries = 0`.

### Model schema is no longer duplicated

`OpenAIModel` now receives:

```python
self.tools = model_tool_schemas()
```

and `model_tool_schemas()` calls each Tool's `to_model_schema()`. There is no separate hand-maintained calculator schema in the adapter.

## Run the visual debugger

```bash
python serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

Compare these two scenarios first:

```text
普通 Calculator · 不重试
Flaky Calculator · Tool 自带 Retry
```

When the Registry resolves the Tool, the trace shows its metadata, including `max_retries` and `retryable_errors`.

## Run deterministic tests

```bash
python -m unittest -v
```

Tests are API-free and verify that Registry returns Tool objects, model schemas come from those same objects, validation uses Tool parameters, retry policy is Tool-owned, and the previous MAX_STEPS / duplicate protections still work.

## Run with a real OpenAI model

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_api_key_here"
python run_real.py
```

Secrets are never stored in source code.
