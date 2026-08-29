# Agent Engineering from Scratch

A step-by-step repository for building an Agent Runtime and turning it into a grounded research Agent.

## Phase 1 — Runtime from scratch

V0 → V11 cover the minimal loop, Tool Registry, validation, retry, Policy, ExecutionContext, StateStore, checkpointing, Planner/DAG Scheduler, Evidence/Citation, Tracing, and Evals.

## Phase 2 — Research Agent

- R1 — Real BLS source adapter
- R2 — API-only multi-source macro research
- R3 — Research decomposition + safe query generation
- R4 — Source API health + source contract testing
- R5 — Evidence quality / freshness / contradiction
- R6 — Investment & policy synthesis + domain evals

## Current stage: R6 — grounded domain synthesis

```text
Research Question
      ↓
ResearchDecomposer
      ↓
QueryCompiler
      ↓
Q1..Qn source tasks
      ↓
EvidenceStore
      ↓
S1 Research Synthesis
quality / freshness / relations / limitations
      ↓
D1 Domain Synthesis
Investment OR Policy lens
      ↓
Grounded citations + Trace + R6 Evals
```

The key R6 distinction is:

```text
S1 = what the Evidence supports
D1 = how that grounded conclusion is framed for a decision domain
```

D1 cannot fetch new data, add Evidence IDs, or increase S1 confidence. Both S1 and D1 go through the existing Runtime/Tool/Policy/Scheduler path, and D1 citations are verified again against the same EvidenceStore.

## Domain lenses

### Investment

The investment brief contains:

- thesis;
- macro market channels;
- base/upside-inflation/downside-inflation scenarios;
- counterevidence;
- what would change the view;
- monitoring signals;
- limitations.

Scenario weighting is qualitative. The workbench does not fabricate probabilities and does not treat the brief as an individualized trade recommendation.

### Policy

The policy brief contains:

- policy problem;
- evidence posture;
- analytical options;
- tradeoffs;
- counterevidence;
- what would change the view;
- monitoring signals;
- limitations.

The brief frames evidence and tradeoffs rather than issuing a policy directive.

## Evidence quality inherited from R5

Every source Evidence record is assessed on four transparent dimensions:

```text
Authority
Freshness
Completeness
Relevance
```

Cross-source relations distinguish:

```text
AGREEMENT
MIXED_SIGNAL
CONTRADICTION
```

`MIXED_SIGNAL` means different indicators point in different directions. `CONTRADICTION` requires opposing conclusions on the same comparable claim. Support scores remain deterministic teaching heuristics, not calibrated probabilities of truth.

## Active public sources

```text
BLS  https://api.bls.gov/publicAPI/v2/timeseries/data
FRED https://api.stlouisfed.org/fred/series/observations
EIA  https://api.eia.gov/v2/petroleum/pri/gnd/data/
```

Runtime environment variables:

```text
BLS_API_KEY   optional registered BLS quota
FRED_API_KEY  required when FRED is selected
EIA_API_KEY   required when EIA is selected
```

Credentials never enter Planner arguments, Evidence, citations, Trace, health reports, or UI diagnostics.

## Source health

Run the real API smoke test:

```bash
python3 source_smoke.py
```

or one provider:

```bash
python3 source_smoke.py BLS
python3 source_smoke.py FRED
python3 source_smoke.py EIA
```

Source Health keeps operational readiness separate from observation freshness and classifies rate limits, TLS/auth/HTTP failures, malformed source contracts, and missing credentials.

## R6 Evals

The live R6 suite has three layers:

```text
1. r6-blueprint-query-contract
2. r6-research-quality-contract
3. r6-investment-decision-contract
   OR r6-policy-decision-contract
```

Checks include:

- decomposition/query 1:1 alignment and safe query fields;
- dynamic `Q1..Qn → S1 → D1` DAG completion;
- one grounded Evidence record per source query;
- final citation IDs exactly match collected Evidence IDs;
- S1 quality coverage and non-probabilistic confidence semantics;
- D1 cannot add/remove Evidence IDs or raise confidence;
- D1 has counterevidence, falsifiers, and monitoring signals;
- scenario weighting is qualitative rather than a fake probability;
- unresolved same-claim contradiction blocks a research-ready decision status.

CI remains network-independent by injecting API-shaped source responses while exercising the same production parsers/contracts.

## Run the workbench

```bash
python3 -m pip install -r requirements.txt
python3 serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

Use the Domain selector to switch between `Investment` and `Policy`. The source queries and Evidence should remain the same for the same research question; only D1 changes.

Active UI scripts:

```text
web/r6_app.js
web/r4_health.js
```
