# Agent Engineering from Scratch

A step-by-step repository for building an Agent Runtime and turning it into a grounded research Agent.

## Phase 1 — Runtime from scratch

V0 → V11 cover the minimal loop, Tool Registry, validation, retry, Policy, ExecutionContext, StateStore, checkpointing, Planner/DAG Scheduler, Evidence/Citation, Tracing, and Evals.

## Phase 2 — Research Agent

- R1 — Real BLS source adapter
- R2 — API-only multi-source macro research
- R3 — Research decomposition + query generation
- R4 — Source quality / freshness / contradiction
- R5 — Investment & policy synthesis + domain evals

## Current stage: R2 — API-only multi-source macro research

The active R2 application has one data path only:

```text
Research Question
      ↓
APIMacroPlanner
      ↓
H1 BLS Headline CPI API
C1 BLS Core CPI API
F1 FRED 5Y Breakeven API
G1 EIA Weekly Gasoline API
      ↓
A1 Cross-source synthesis
      ↓
EvidenceStore → Citations → Trace → API Evals
```

There is no user-visible Fixture/Live switch and no `mode` argument in the active R2 Planner or Tool schemas.

### Active source routes

```text
BLS
https://api.bls.gov/publicAPI/v1/timeseries/data/{series_id}

FRED
https://api.stlouisfed.org/fred/series/observations
FRED_API_KEY required

EIA
https://api.eia.gov/v2/petroleum/pri/gnd/data/
EIA_API_KEY required
```

The EIA adapter uses the current petroleum REST route with:

```text
frequency=weekly
data[0]=value
facets[series][]=EMM_EPMR_PTE_NUS_DPG
sort by period desc
length=8
```

FRED requests only a recent observation window instead of downloading the entire series history.

### Credentials

Set the keys in the shell before starting the workbench:

```bash
export FRED_API_KEY="..."
export EIA_API_KEY="..."
python3 serve_visualizer.py
```

Credentials are Runtime-owned. They do not enter Planner arguments, Tool arguments, Evidence, citations, or Trace.

### Failure behavior

External API failure is no longer returned as a generic HTTP 500. `/api/run` returns HTTP 200 with a structured application result:

```json
{
  "ok": false,
  "stage": "source_or_runtime",
  "error": {
    "task_id": "G1",
    "provider": "EIA",
    "message": "..."
  }
}
```

This makes the failing provider visible in the UI and keeps web-server health separate from upstream data-source health.

### API Evals

The visible eval path uses only the R2 task names:

```text
H1 / C1 / F1 / G1 / A1
```

Checks include:

- five-task contract;
- four API Evidence records;
- BLS/FRED/EIA provider coverage;
- four grounded citations;
- freshness coverage;
- five Tool attempts;
- causal guardrail: gasoline/breakeven are descriptive signals, not causal CPI attribution.

The two scoring profiles share one live research run to avoid unnecessarily repeating external API requests.

### CI

CI does not depend on internet availability. Adapter tests inject API-shaped JSON responses into the same production parsers. This is transport mocking, not a user-selectable fixture data mode.

Run locally:

```bash
python3 serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

The active UI script is `web/r2_api_app.js`.
