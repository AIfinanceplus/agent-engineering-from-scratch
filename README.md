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

## Current stage: V6 — ExecutionContext

V5 proved that Capability is not Permission. V6 answers the next question:

> Permission for whom?

Policy now receives both the Tool request and a Runtime-owned execution identity.

```text
User goal
   ↓
Runtime injects ExecutionContext
   ↓
Model proposes Tool Call
   ↓
Runtime Guards
   ↓
Tool Registry + Tool.validate
   ↓
PolicyEngine.evaluate(tool, arguments, execution_context)
   ↓
ALLOW / REQUIRE_APPROVAL / DENY
   ↓
Only ALLOW reaches tool.function(...)
```

### Model Context vs ExecutionContext

They are different concepts.

```text
Model Context
= what information the model sees

ExecutionContext
= who/what the system says is executing
```

V6 uses an immutable dataclass:

```python
ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="general-agent",
    task_id="task-001",
    trace_id="trace-001",
)
```

These fields are injected by Runtime infrastructure. They are not taken from a model-generated Tool Call.

### Context-aware policy

The teaching Policy keeps V5 risk rules and adds one identity rule:

```text
general-agent + send_message(medium)
    ↓
REQUIRE_APPROVAL

read-only-agent + send_message(medium)
    ↓
DENY
```

The Tool and arguments are identical. Only ExecutionContext changes.

Low-risk compute is still allowed for the read-only agent:

```text
read-only-agent + calculator(low)
    ↓
ALLOW
```

This demonstrates the key idea:

> Authorization is a function of capability + request + trusted execution identity.

### Why Runtime owns the identity

If Model output could supply its own `agent_id`, `tenant_id`, or `user_id`, it could simply claim a more privileged identity. V6 therefore keeps identity on a separate Runtime path:

```text
Model output
  └─ tool_name + arguments

Runtime infrastructure
  └─ ExecutionContext

Policy Engine
  └─ combines both
```

## Run the visual debugger

```bash
python serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

Recommended comparison:

1. Choose `MEDIUM risk · send_message`.
2. Run as `general-agent` → `REQUIRE_APPROVAL`.
3. Run the same Tool Call as `read-only-agent` → `DENY`.
4. Compare the `ExecutionContext Injected` and `Policy Decision` trace events.

The browser selects only a server-side context preset; it does not send arbitrary tenant/user/agent IDs into the Runtime.

## Run deterministic tests

```bash
python -m unittest -v
```

Tests verify typed immutable ExecutionContext, Runtime context injection, context-aware Policy differences, blocked execution for unauthorized identities, previous Policy behavior, Tool-owned retry, MAX_STEPS, duplicate protection, and Model/Tool validation.

## Run with a real OpenAI model

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_api_key_here"
python run_real.py
```

Secrets are never stored in source code.
