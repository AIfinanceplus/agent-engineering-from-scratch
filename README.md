# Agent Engineering from Scratch

A step-by-step learning repository that first builds an Agent Runtime from first principles, then turns it into a grounded investment / policy research Agent.

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
- **R2 — Multi-source macro evidence: BLS + FRED + EIA**
- R3 — Research decomposition + query generation
- R4 — Source quality / contradiction handling
- R5 — Investment & policy synthesis + domain evals

## Current stage: R2 — Multi-Source Macro Research

R1 proved one real-source path. R2 introduces a source plan with independent public-data adapters and a downstream synthesis that can only consume already-collected evidence.

```text
Research Question
       ↓
MultiSourceMacroPlanner
       ↓
┌────────────┬────────────┬────────────┬────────────┐
│ H1         │ C1         │ F1         │ G1         │
│ BLS        │ BLS        │ FRED       │ EIA        │
│ headline   │ core CPI   │ 5Y BEI     │ gasoline   │
└─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┘
      │ Evidence    │ Evidence    │ Evidence    │ Evidence
      └─────────────┴──────┬──────┴─────────────┘
                           ↓
                          A1
                 cross-source synthesis
                           ↓
             freshness + signals + limitations
                           ↓
                 verified 4-source citations
```

### Responsibilities

```text
Source Adapter = fetch + normalize + provenance
EvidenceStore  = register grounded source identity
Analysis       = consume completed Evidence only
Freshness      = compare each source's as-of clock
Synthesis      = descriptive cross-source read
Citation       = verify every claimed evidence ID
```

R2 deliberately does **not** infer causal CPI contributions from gasoline or breakeven co-movement. Those are descriptive signals only.

## Source adapters

### BLS

R1's `BLSAdapter` remains the source for headline and core CPI.

### FRED

`FREDAdapter` uses `fred/series/observations` in live mode and the `T5YIE` 5-year breakeven series in the first R2 plan.

Live FRED requires:

```bash
export FRED_API_KEY="..."
```

### EIA

`EIAAdapter` uses EIA API v2's `seriesid` compatibility route for the first gasoline series.

Live EIA requires:

```bash
export EIA_API_KEY="..."
```

### Credential rule

API keys are Runtime-owned configuration. They are never included in:

```text
Tool arguments
Plan fields
ExecutionContext
Evidence
Trace events
Citation metadata
```

The adapters persist only public source pages / series identifiers, never the credential-bearing request URL.

## Fixture vs live

```text
Fixture Replay
→ deterministic BLS / FRED / EIA payloads
→ same normalized Evidence contract
→ CI and teaching
→ no network dependency

Live Public APIs
→ local Runtime performs external requests
→ BLS + FRED + EIA
→ same downstream Planner / Scheduler / Evidence / Citation path
```

The fixture values are teaching-only and are not current macro observations.

## R2 Tool Pack

Domain-specific capabilities are loaded as an explicit extension pack instead of permanently bloating the core Runtime registry:

```python
register_r2_tools()
```

The pack adds:

```text
fetch_fred_series
fetch_eia_series
synthesize_macro_signals
```

The existing R1 `fetch_bls_series` capability remains available.

Every Tool still passes through the original Runtime:

```text
Validation → Policy → Retry → Execution → AgentState → EvidenceStore → Trace
```

## Freshness-aware synthesis

A1 receives complete H1/C1/F1/G1 results through DAG dependency resolution and calculates:

```text
headline CPI YoY
core CPI YoY
core-minus-headline gap
gasoline window % change
5Y breakeven window change
per-evidence age / freshness status
```

The first deterministic freshness buckets are:

```text
0–45 days   = fresh
46–90 days  = aging
>90 days    = stale
```

If any required evidence is stale, synthesis confidence is capped instead of silently pretending all sources are equally current.

## Research Workbench

Run:

```bash
python serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

The compact UI remains:

```text
SOURCE PLAN              RUN / TRACE              CODE
BLS / FRED / EIA         Scheduler / Runtime      matching Python
status / as-of / value   evidence / synthesis     WHY / NEXT
                         Eval Mode preserved       citations / freshness
```

Start with `Fixture Replay`. For live FRED/EIA, set the two API keys before launching the server.

V11 Eval Mode remains available and still shows `Case → Agent Run → Checks → Verdict` step by step.

## Tests

```bash
python -m unittest -v
```

R2 adds coverage for:

- FRED and EIA normalization;
- missing live credentials failing explicitly;
- credentials reaching the HTTP transport but never being persisted in Evidence;
- freshness calculation;
- descriptive gasoline / breakeven signal calculation;
- H1/C1/F1/G1 → A1 dependency structure;
- five Tool attempts, four Evidence records, and four grounded citations in a full fixture run;
- all R1 and V0–V11 regressions.
