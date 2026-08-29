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

## Current stage: V9 — Planner + DAG Scheduler

V8 made one Agent run durable. V9 moves one layer up and asks:

> What if the goal contains multiple tasks with dependencies?

V9 deliberately separates three responsibilities:

```text
Planner
= WHAT tasks should exist?
= What depends on what?

Scheduler
= WHICH task is READY now?
= Which tasks are BLOCKED?

Agent Runtime
= HOW does one selected task execute safely?
```

The existing Runtime is still used inside every scheduled task, so Tool validation, Policy, Retry, MAX_STEPS, StateStore, and other deterministic boundaries are not bypassed.

## Teaching DAG

The deterministic Planner creates:

```text
Task A: 10 + 20 = 30 ──┐
                        ├──> Task C: A + B = 72
Task B:  6 × 7 = 42 ──┘
```

Initial Scheduler state:

```text
A = READY
B = READY
C = BLOCKED
```

V9 uses a sequential Scheduler on purpose. A and B may both be READY, but the teaching implementation executes one READY Task at a time:

```text
Tick 1
READY   = [A, B]
BLOCKED = [C]
    ↓
run A
    ↓
A = COMPLETED (30)

Tick 2
READY   = [B]
BLOCKED = [C]
    ↓
run B
    ↓
B = COMPLETED (42)

Tick 3
READY   = [C]
BLOCKED = []
    ↓
resolve C arguments from A/B results
    ↓
calculator(30, 42, add)
    ↓
72
```

This keeps DAG semantics separate from concurrency. Parallel execution can be added later without changing what READY/BLOCKED means.

## Planner validation

`validate_plan(...)` fails closed on:

```text
duplicate task IDs
missing dependency IDs
self-dependency
cycles
```

A Scheduler should not try to "figure out" a malformed DAG while executing it.

## Compact visual debugger UI

V9 redesigns the browser around the information needed at this stage.

Desktop layout:

```text
┌──────────── PLAN ────────────┐
│ Task cards / dependency state │
│ READY / RUNNING / BLOCKED     │
└───────────────────────────────┘

┌──────────── RUN ─────────────┐
│ selected teaching events      │
│ current Scheduler/Runtime step │
└───────────────────────────────┘

┌──────────── CODE ────────────┐
│ matching code                 │
│ WHY / NEXT explanation        │
│ collapsible Runtime details   │
└───────────────────────────────┘
```

The three panes share one viewport on larger screens and scroll independently. Raw Runtime events remain available under collapsible `Details`, but they no longer dominate the main screen.

Run:

```bash
python serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

Recommended learning sequence:

1. `Planner created DAG` — inspect `planner.py`.
2. First `Scheduler tick` — confirm A/B READY and C BLOCKED.
3. `Task A started` — observe Scheduler handoff to Runtime.
4. Walk through A's Tool validation, Policy, Tool execution, and result.
5. Observe the next Scheduler tick: B READY, C still BLOCKED.
6. After B completes, observe C become READY.
7. At `Task C started`, inspect resolved arguments `{a: 30, b: 42}`.
8. Finish at final result `72`.

## Tests

```bash
python -m unittest -v
```

V9 adds tests that verify:

- the Planner creates A/B → C dependencies;
- cyclic DAGs are rejected;
- Scheduler transitions are exactly `READY [A,B] / BLOCKED [C]`, then `READY [B]`, then `READY [C]`;
- dependency results are resolved into C as `30` and `42`;
- final result is `72`;
- every Task still passes through the existing Runtime validation, Policy, Tool execution, and StateStore events;
- all V0–V8 regression tests continue to run.

V8 crash/resume endpoints remain in the local server for backward-compatible experiments, but the V9 UI intentionally makes Planner/Scheduler the primary view.
