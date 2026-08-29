# Agent Engineering from Scratch

A step-by-step learning repository for building an Agent Runtime and then turning it into a grounded research Agent.

## Phase 1 — Runtime from scratch

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

## Phase 2 — Research Agent

- R1 — Real Source Adapter: BLS CPI
- R2 — Multi-source macro evidence
- R3 — Research decomposition + query generation
- R4 — Source quality / freshness / contradiction
- R5 — Investment & policy synthesis + domain evals

## Current stage: R1 — Real BLS Source Adapter

Phase 1 proved that the Agent Runtime can plan, execute Tools, preserve state, validate citations, trace runs, and evaluate quality. R1 changes the data boundary:

> Stop using only bundled teaching evidence. Connect the same Runtime to a real public source without giving up reproducibility.

The first research question is deliberately narrow:

```text
Compare the latest headline and core CPI year-over-year rates
using BLS evidence only.
```

## R1 architecture

```text
Research Question
       ↓
CPIResearchPlanner
       ↓
┌─────────────────────┐       ┌─────────────────────┐
│ H1                  │       │ C1                  │
│ Headline CPI        │       │ Core CPI            │
│ CUSR0000SA0         │       │ CUSR0000SA0L1E      │
│ fetch_bls_series    │       │ fetch_bls_series    │
└──────────┬──────────┘       └──────────┬──────────┘
           │ Evidence                     │ Evidence
           └──────────────┬───────────────┘
                          ↓
                    ┌───────────┐
                    │ A1        │
                    │ compare   │
                    │ CPI YoY   │
                    └─────┬─────┘
                          ↓
              Synthesis + Citations
                          ↓
                        Trace
```

The important boundary is:

```text
Source Task
= fetch / normalize / attach provenance

Analysis Task
= consume already-collected Evidence
= no hidden re-fetch
```

## Source Adapter

`macro_sources.py` introduces `BLSAdapter`.

It supports two modes with the same normalized output contract:

```text
fixture
→ deterministic replay
→ CI / learning / debugging
→ never presented as current BLS data

live
→ HTTP GET to the BLS Public Data API
→ real observations from the local Runtime
```

A normalized source result includes:

```text
kind = evidence
evidence_id
series_id
source_mode
latest value
history[]
claim
publisher
source URI
confidence
```

The Tool layer registers:

```python
fetch_bls_series(...)
compare_cpi_series(...)
```

Both still pass through the existing Runtime:

```text
Tool proposal
→ validation
→ Policy
→ Retry
→ execution
→ AgentState
→ EvidenceStore
→ Trace
```

For live BLS requests, `TimeoutError` and `ConnectionError` remain retryable Runtime execution failures. Analysis errors are not treated as transient network retries.

## CPI analysis

`macro_analysis.py` computes the latest year-over-year rate from the collected monthly history:

```python
yoy = (latest / same_month_previous_year - 1) * 100
```

A1 receives the complete H1/C1 evidence objects through DAG dependency resolution:

```python
{
    "headline": {"from_task": "H1"},
    "core": {"from_task": "C1"},
}
```

Only when H1 and C1 are complete does Scheduler resolve those references into actual Evidence objects.

The synthesis carries both evidence IDs, and `EvidenceStore` verifies them before citations are returned.

## Why fixture and live are separate

CI should test our Agent, not the availability of an external website.

```text
CI
→ fixture replay
→ deterministic parser / planner / analysis / citation tests

Local research
→ Live BLS
→ same Source Adapter contract
→ real network response
```

`BLSAdapter` also accepts an injected transport, so tests verify the live BLS JSON response shape and URL construction without sending a network request.

## Research Workbench

Run:

```bash
python serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

The R1 UI keeps the compact three-pane structure:

```text
SOURCE PLAN        RUN / TRACE             CODE
H1 headline        fetch                    matching Python
C1 core            evidence registration   WHY / NEXT
A1 analysis        analysis                 citations
```

Use the Data selector:

```text
Fixture Replay
→ recommended first
→ deterministic teaching flow

Live BLS
→ real BLS request from your local Python Runtime
```

V11 Eval Mode remains available from the same workbench as a regression-learning tool.

## Tests

```bash
python -m unittest -v
```

R1 adds tests for:

- normalized fixture Evidence contract;
- BLS live API JSON parsing with an injected transport;
- official BLS series URL construction;
- CPI YoY calculation from monthly history;
- H1/C1 → A1 Planner dependencies;
- full fixture research run through the existing Runtime;
- two BLS Evidence records and two verified citations;
- Trace Tool-attempt accounting;
- all V0–V11 regression tests.

The fixture values are intentionally teaching-only. Select `Live BLS` when you want the workbench to retrieve current observations from the external source.
