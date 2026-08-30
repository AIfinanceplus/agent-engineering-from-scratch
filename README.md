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
- R7 — Forecast contracts + scenario tracking + settlement
- R8 — Decision lenses + current-run evals
- R9 — Observed market-pricing context
- R10 — Numerical target + scenario EV + instrument risk
- R11 — Constraint-based position sizing
- R12 — Strategy opportunities + live public event markets + HITL Strategy Agent

## Current stage: R12 Step 8 — task-oriented Strategy Center

R12 keeps the earlier Runtime, Evidence, forecasting, EV, risk, and sizing layers,
then adds a five-strategy opportunity registry. The currently deepest live path is
same-event Kalshi/Polymarket relative value:

```text
Exact market identifiers
      ↓
R12 Planner DAG
      ↓
K1 / P1 public market-contract Tools through the shared Agent Runtime
      ↓
R1 fingerprint-bound deterministic settlement-rules analysis
      ↓
H1 durable WAITING_HUMAN_IDENTITY_APPROVAL checkpoint
      ↓ explicit six-check human attestation only
I1 settlement identity Tool
      ↓
V1 top-of-book reciprocal complement scan
      ↓
E1 depth-aware paper execution quote
      ↓ explicit user command; quote is never treated as a fill
Paper intent with zero fills
      ↓ idempotent simulated fill commands
Append-only hash-chained event ledger
      ↓ deterministic replay
Partial-leg risk / matched quantity / MTM P&L
      ↓ explicit YES or NO settlement
Realized paper P&L
```

The Strategy Agent persists an append-only checkpoint view after every boundary.
Resume skips durably completed tasks. No parser or model can check H1 boxes, and no
R12 component places orders. Step 7 deliberately separates the read/compute Agent
DAG from state-changing commands: E1 remains a quote, while every simulated fill,
mark, cancel/expire, and settlement requires an idempotency key and is recorded as
an fsync'd JSONL event under `.r12_paper_ledger/`.

Step 8 reorganizes the operator surface without changing those backend contracts:

```text
Agent Run          default linear acceptance path
Manual Lab         structural scan + one-tool-at-a-time diagnostics
Strategy Roadmap   five strategy families + current implementation boundary
```

The Agent Run workspace now follows user task order rather than implementation
history: discover pair → lock exact IDs → configure explicit costs → start/resume
Agent → review H1 beside the six checkboxes → inspect I1/V1/E1 → paper ledger.

Current five-strategy roadmap:

```text
1. Structural / logic arbitrage        deterministic scanner active
2. Same-event cross-market RV          live public data + HITL agent active
3. FOMC probability RV                 planned
4. CPI / macro-data RV                 research engine ready, calibration pending
5. Options vs event-market RV          planned
```

## R7 forecasting foundation retained

```text
Research Question
      ↓
ResearchDecomposer / QueryCompiler
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
F1 Forecast Pack
baseline / direction / horizon / due date / invalidation / lineage
      ↓
Durable .forecasts/ store
      ↓
Later fresh S1 check
      ↓
PENDING / INVALIDATED / RESOLVED HIT / RESOLVED MISS
      ↓
Scenario update + revision decision
```

The key R7 distinction is:

```text
Opinion != Forecast

A Forecast must be falsifiable and settleable.
```

Every OPEN forecast has:

```text
forecast_id
target Evidence ID
target metric
baseline value + baseline as-of
expected direction
horizon + due date
tolerance
Evidence lineage
invalidation rule
settlement rule
```

If the Evidence is contradictory or lacks a comparable directional baseline, R7 emits `ABSTAINED` rather than forcing a prediction.

## Forecast semantics

R7 currently uses a deterministic teaching baseline:

```text
directional_persistence_baseline
```

It asks whether the next meaningful observation, by the forecast horizon, continues the currently grounded direction. This is intentionally simple so the contract, settlement, and evaluation machinery can be learned before introducing statistical/ML forecasting models.

Provider-aware teaching horizons:

```text
BLS   45 days
FRED   7 days
EIA   14 days
```

These are workbench heuristics, not provider SLAs or calibrated optimal horizons.

Forecast support scores inherit upstream Evidence quality/confidence and remain:

```text
heuristic_support_score_not_probability
```

After forecasts resolve, R7 may compute historical directional hit rate. That statistic is explicitly labeled:

```text
historical_direction_hit_rate_not_probability
```

A historical hit rate is not the probability that the next forecast is correct.

## Scenario tracker

R7 tracks explicit scenario states:

```text
UPSIDE_INFLATION
DOWNSIDE_INFLATION
MIXED
RECONCILE
STABLE
UNRESOLVED
```

Examples:

```text
UPSIDE_INFLATION
= at least two tracked signals rising and none falling

DOWNSIDE_INFLATION
= at least two tracked signals falling and none rising

MIXED
= at least one rising and at least one falling

RECONCILE
= same-claim contradiction exists in S1
```

Scenario history is stored with the forecast pack. A scenario change, a forecast miss, an early invalidation trigger, or a new contradiction marks the pack as requiring research revision.

## Durable forecast tracking

Forecast packs are stored locally under:

```text
.forecasts/
```

The directory is gitignored. The workbench reloads saved forecast pack IDs after restart.

A new R7 research run creates/saves a pack. `检查 Forecast` reloads the selected historical pack, refreshes real source Evidence through the normal Query → Runtime → Evidence path, rebuilds a fresh S1, and evaluates the old forecast against that new grounded state.

A forecast is not resolved merely because its calendar due date has passed. R7 also requires a newer source observation than the baseline observation. Otherwise it reports:

```text
AWAITING_NEW_OBSERVATION
```

Before the due date, a reversal can trigger:

```text
PENDING_NOT_DUE
invalidation_triggered = true
```

but final settlement still waits for the contract's due date.

## R6 domain layer preserved

```text
S1 = what the Evidence supports
D1 = how that grounded conclusion is framed for a decision domain
F1 = what falsifiable future statements are now being tracked
```

D1 cannot fetch new data, add Evidence IDs, or increase S1 confidence. F1 cannot fetch data, invent Evidence IDs, increase confidence, or fabricate forecast probabilities.

Investment and Policy still use the same source Evidence for the same research question; only the D1 framing changes. F1 forecast targets are derived from S1 signals, so changing the domain lens does not silently change the underlying data targets.

## Evidence quality inherited from R5

Every source Evidence record is assessed on:

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

`MIXED_SIGNAL` is uncertainty across different indicators. `CONTRADICTION` requires opposing conclusions on the same comparable claim.

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

Credentials never enter Planner arguments, Evidence, citations, Trace, health reports, forecast packs, or UI diagnostics.

## Source health

```bash
python3 source_smoke.py
```

or:

```bash
python3 source_smoke.py BLS
python3 source_smoke.py FRED
python3 source_smoke.py EIA
```

Source Health keeps operational readiness, quota/rate-limit status, and observation freshness separate.

## R7 Evals

The R7 suite has four layers:

```text
1. r7-blueprint-query-contract
2. r7-research-lineage-contract
3. r7-investment-domain-contract
   OR r7-policy-domain-contract
4. r7-forecast-tracking-contract
```

Checks include:

- safe query compilation and provider allow-listing;
- dynamic `Q1..Qn → S1 → D1 → F1` DAG completion;
- one Evidence record per source query;
- final citations exactly grounded in collected Evidence;
- S1 quality coverage and non-probabilistic confidence semantics;
- D1 cannot add Evidence or raise confidence;
- F1 inherits Evidence IDs and confidence;
- every OPEN forecast has baseline, target metric, direction, due date, horizon, lineage, and invalidation rule;
- contradictions force forecast abstention for affected Evidence;
- scenario states have explicit triggers;
- F1 performs no new source fetch and invents no new Evidence;
- neither forecast support scores nor historical hit rates are represented as probabilities.

CI remains network-independent by injecting API-shaped source responses while exercising the same production parser, Runtime, Evidence, synthesis, forecast, and settlement contracts.

## Run the current workbench

```bash
python3 -m pip install -r requirements.txt
python3 serve_r12.py
```

Open:

```text
http://127.0.0.1:8000
```

Suggested R12 Step 8 Agent Run flow:

```text
1. 打开 策略机会；保持默认 Agent Run workspace
2. 搜索并加载 exact Kalshi / Polymarket pair
3. 输入 target、explicit fee model 与 latency buffer
4. Start Exact-pair Agent
5. 检查 R1 rules artifact；Agent 应停在 H1
6. 人工勾选六项 settlement identity attestation
7. Approve H1 and Resume
8. 检查 I1 / V1 / E1、task traces、checkpoints 与 eval
9. Create Paper Intent；确认初始状态为 PENDING_PAPER_FILL 且 0 fills
10. 先给一条腿 Record Fill；确认状态为 PARTIALLY_FILLED_LEG_RISK
11. 给另一条腿记录相同数量；确认 leg risk 回到 0
12. Update MTM，检查 acquisition cost、marked value 与 MTM P&L
13. Cancel / Expire 剩余数量，或补齐两腿至 FULLY_MATCHED
14. Settle YES / NO，检查 settlement payoff 与 realized P&L
15. 刷新页面并用 Paper trade ID Load Ledger，确认事件回放结果不变
```

Active UI scripts:

```text
web/r12_ui.js
web/r12_step2.js
web/r12_step3.js
web/r12_step4.js
web/r12_step5.js
web/r12_step6.js
```
