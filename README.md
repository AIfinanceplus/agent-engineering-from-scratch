# Agent Engineering from Scratch

A step-by-step repository for building an Agent Runtime and turning it into a grounded research Agent.

## Phase 1 — Runtime from scratch

V0 → V11 cover the minimal loop, Tool Registry, validation, retry, Policy, ExecutionContext, StateStore, checkpointing, Planner/DAG Scheduler, Evidence/Citation, Tracing, and Evals.

## Phase 2 — Research Agent

- R1 — Real BLS source adapter
- R2 — API-only multi-source macro research
- R3 — Research decomposition + safe query generation
- R4 — Source API health + source contract testing
- R5 — Source quality / freshness / contradiction
- R6 — Investment & policy synthesis + domain evals

## Current stage: R4 — Source API health + research intelligence

R4 adds an explicit operational source boundary before research debugging:

```text
Real Public APIs
      ↓
SourceHealthChecker
TLS / credentials / HTTP / JSON / Evidence contract / as-of
      ↓
Research Question
      ↓
ResearchDecomposer
      ↓
Subquestions / Source Intents
      ↓
QueryCompiler
      ↓
Validated Query Specs
      ↓
Dynamic DAG
      ↓
Runtime → EvidenceStore → Synthesis → Citations → Trace → Evals
```

The key distinction is:

```text
API READY != DATA FRESH
```

API readiness checks transport and contract health. Freshness reports observation age separately because BLS monthly data, FRED market data, and EIA weekly data have different natural cadences.

## Active public sources

### BLS

BLS Public Data API v2 single-series endpoint:

```text
https://api.bls.gov/publicAPI/v2/timeseries/data/{series_id}
```

The production adapter uses native OS TLS trust and preserves GET → POST fallback through the official v2 endpoint.

Current CPI probes:

```text
CUSR0000SA0      headline CPI
CUSR0000SA0L1E  core CPI
```

No API key is required for the current BLS single-series path.

### FRED

```text
https://api.stlouisfed.org/fred/series/observations
```

Current research probe:

```text
T5YIE  5-Year Breakeven Inflation Rate
```

Required Runtime environment variable:

```text
FRED_API_KEY
```

### EIA

Current APIv2 petroleum REST route:

```text
https://api.eia.gov/v2/petroleum/pri/gnd/data/
```

Current research probe:

```text
EMM_EPMR_PTE_NUS_DPG  U.S. Regular All Formulations Retail Gasoline Prices
```

The query uses weekly frequency, the `value` data field, the series facet, descending period sort, and a short recent window.

Required Runtime environment variable:

```text
EIA_API_KEY
```

## Native TLS trust

`native_http.py` uses `truststore` so Python HTTPS uses the operating system trust store. On macOS this aligns Python certificate trust with the system Security.framework while keeping certificate and hostname verification enabled.

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Never disable TLS verification to make a public-data request pass.

## Test the real data-source APIs

Set credentials first when testing all three sources:

```bash
export FRED_API_KEY="..."
export EIA_API_KEY="..."
```

Then use either the workbench button:

```text
测试数据源 API
```

or the CLI:

```bash
python3 source_smoke.py
```

Test one provider independently:

```bash
python3 source_smoke.py BLS
python3 source_smoke.py FRED
python3 source_smoke.py EIA
```

A source result reports one of:

```text
READY
CREDENTIAL_MISSING
TLS_ERROR
AUTH_ERROR
HTTP_ERROR
TIMEOUT
CONNECTION_ERROR
CONTRACT_ERROR
API_ERROR
```

A successful result also reports a safe base endpoint, series ID, normalized Evidence ID, `as_of`, age, freshness heuristic, latency, and BLS transport when applicable.

Credential values are never included in Planner arguments, Tool arguments, Evidence, citations, Trace, health reports, or UI diagnostics.

## R3 research intelligence preserved inside R4

The research path remains question-driven rather than using a fixed H1/C1/F1/G1 plan.

Broad question:

```text
Assess current inflation pressure.
```

can compile to:

```text
Q1 headline CPI  → BLS
Q2 core CPI      → BLS
Q3 breakeven     → FRED
Q4 gasoline      → EIA
                  ↓
                 S1
```

Narrow question:

```text
Compare headline and core CPI.
```

compiles only to:

```text
Q1 headline CPI → BLS
Q2 core CPI     → BLS
                 ↓
                S1
```

FRED/EIA credentials are required only when QueryCompiler selects those providers.

## CI

CI is network-independent. It uses injected API-shaped responses to validate the production parsers and source-health contract without consuming public API quota or requiring repository secrets.

R4 CI checks include:

- Python and browser JavaScript syntax;
- native TLS verification remains enabled;
- credential-gated providers are not called when credentials are missing;
- TLS failures are classified correctly;
- malformed source output becomes `CONTRACT_ERROR`;
- secret values cannot leak into health diagnostics;
- R3 dynamic-query, Runtime, Evidence, Citation, Trace, and Eval regressions.

## Run the workbench

```bash
python3 serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

Active UI scripts:

```text
web/r3_app.js
web/r4_health.js
```
