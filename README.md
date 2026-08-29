# Agent Engineering from Scratch

A step-by-step learning repository for building an Agent Runtime from first principles.

## Roadmap

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

## Current stage: V11 — Tracing + Evals

V10 made research outputs grounded in explicit evidence. V11 asks a different question:

> How do we know the Agent is reliable, and how do we compare one version with another?

Two concepts stay separate:

```text
Trace
= explain one run
= spans + duration + runtime counters

Eval
= judge a run against explicit expectations
= repeat the same cases after code changes
```

## Trace model

`observability.py` adds:

```python
TraceRecorder
Span
```

The Scheduler creates one root span for the whole plan and one child span per Task:

```text
plan.run
├── task.E1
├── task.E2
└── task.S1
```

The trace also records counters without changing business behavior:

```text
scheduler_ticks
tasks_started
tasks_completed
tool_attempts
evidence_registered
citations_verified
runtime_events
```

For the default research DAG, the expected shape is:

```text
4 spans
3 Tool attempts
2 Evidence records
2 verified citations
3 completed Tasks
```

Tracing is deliberately side-channel observability. It does not decide which Task is READY, whether Policy allows execution, or what a Tool returns.

## Eval model

`evals.py` adds explicit `EvalCase` and `EvalReport` contracts.

The first scoring dimensions are:

```text
success
task_completion_rate
evidence_coverage
citation_completeness
citations_grounded
confidence
```

A result passes only if the expectations are satisfied. For example, a polished answer that cites `[E99]` while E99 was never collected fails `citations_grounded`.

```python
report = score_result(case, result)

if not report.passed:
    # fail the quality gate
```

The default suite contains two deterministic research cases and is designed to be rerun after implementation changes:

```python
suite = run_eval_suite()
# passed / total / pass_rate
```

## Full V11 architecture

```text
                           ExecutionContext
                                  │
                                  ↓
Goal → Planner → DAG → Scheduler → Task Runtime
                                  │
                                  ├→ Validation / Policy / Tool / State
                                  │
                                  ├→ EvidenceStore → Synthesis → Citations
                                  │
                                  └→ TraceRecorder
                                          │
                                          ↓
                                     Trace / Metrics
                                          │
                                          ↓
                                       Evals
                                          │
                                          ↓
                              PASS / FAIL + score breakdown
```

The old responsibilities still remain:

```text
Planner          = WHAT tasks exist
Scheduler        = WHEN tasks are READY
ExecutionContext = WHO is executing
Policy           = MAY this context execute the Tool
Runtime          = HOW a Task executes safely
EvidenceStore    = WHAT grounded evidence exists
Trace            = WHAT happened in this run
Eval             = DID the run satisfy our expectations
```

## Visual debugger

Run:

```bash
python serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

The main UI remains compact:

```text
PLAN            RUN              CODE
Task state      events/trace     matching implementation
E1/E2/S1        current step     WHY / NEXT
```

The top strip adds only two new observability KPIs:

```text
Trace → span count + Tool attempts
Eval  → PASS / FAIL
```

Detailed spans, metrics, eval failures, Runtime State, and raw events stay inside collapsible sections.

Two actions are available:

```text
运行研究
→ run one interactive research case
→ produce Trace + interactive EvalReport

运行 Evals
→ run the fixed default eval suite
→ report passed / total / pass_rate
```

## Tests

```bash
python -m unittest -v
```

V11 verifies:

- span hierarchy and duration accounting;
- one root span plus three Task spans for the research DAG;
- expected scheduler/task/tool/evidence/citation metrics;
- complete evidence and citations pass the eval;
- an ungrounded or missing citation fails the eval;
- the default eval suite passes 2/2;
- V0–V10 Runtime, Checkpoint, Planner, Evidence, Citation, Policy, Retry, and validation regressions still run.

All bundled research records remain synthetic teaching data. The goal is Agent Engineering, not the macroeconomic conclusion represented by the example numbers.
