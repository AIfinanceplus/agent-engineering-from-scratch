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

## Current stage: V5 — Policy Engine

V4 established one authoritative Tool definition. V5 adds a new boundary:

> Capability is not permission.

A Tool can exist, have valid arguments, and still be forbidden from executing.

```text
Model Tool Call
    ↓
Runtime Guards
    ↓
Tool Registry
    ↓
Tool.validate(arguments)
    ↓
PolicyEngine.evaluate(tool, arguments)
    ↓
ALLOW / REQUIRE_APPROVAL / DENY
    ↓
Only ALLOW reaches tool.function(...)
```

### Tool facts vs policy rules

Tool objects now include a risk classification:

```python
Tool(
    name=...,
    parameters=...,
    function=...,
    max_retries=...,
    risk="low" | "medium" | "high",
)
```

`risk` is a capability fact. It does not directly grant or remove permission.

The V5 `PolicyEngine` owns the rule:

```text
low    → ALLOW
medium → REQUIRE_APPROVAL
high   → DENY
```

This distinction matters because policy can later depend on identity, tenant, resource, environment, arguments, or organization rules without rewriting Tool functions.

### Deterministic policy scenarios

The visual debugger demonstrates three paths:

```text
calculator
risk=low
   ↓
ALLOW
   ↓
Python function executes
```

```text
send_message
risk=medium
   ↓
REQUIRE_APPROVAL
   ↓
approval_required Observation
   ↓
Python function does NOT execute
```

```text
delete_record
risk=high
   ↓
DENY
   ↓
policy_denied Observation
   ↓
Python function does NOT execute
```

`send_message` and `delete_record` are simulated teaching functions only; they do not perform external side effects.

V5 intentionally does **not** implement approval pause/resume yet. It only proves that Policy can stop execution before the function boundary.

## Run the visual debugger

```bash
python serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

Run these scenarios in order:

```text
LOW risk → ALLOW → 执行
MEDIUM risk → REQUIRE_APPROVAL
HIGH risk → DENY
```

Watch the `Policy Engine` node. In the latter two cases there should be no `Tool Attempt` event.

## Run deterministic tests

```bash
python -m unittest -v
```

Tests are API-free and verify Tool risk metadata, ALLOW/REQUIRE_APPROVAL/DENY decisions, blocked execution for medium/high risk, Tool-owned retry behavior, MAX_STEPS, duplicate protection, and Model/Tool validation.

## Run with a real OpenAI model

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_api_key_here"
python run_real.py
```

Secrets are never stored in source code.
