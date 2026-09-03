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

## Current stage: Rate Strategy V1 — one complete 2s10s paper simulation

The default learning path is intentionally small. It needs no event search, no
cross-market identity matching, no human settlement checklist, and no broker
credentials:

```text
D1 public FRED DGS2 + DGS10 history
      ↓ common-date alignment
S1 60-observation 2s10s spread z-score
      ↓ explicit steepener / flattener rule
E1 latest historically completed 20-observation paper trade
      ↓ DV01 approximation, explicit cost, contract eval, full Tool trace
```

`RateStrategyAgent` uses a fixed two-Tool DAG. The shared Tool Registry validates
the public-data and simulation calls before execution. V1 deliberately uses no
LLM planner: the goal is to make Planner → Runtime → Tool → Observation → Eval
visible in one click. The full Workbench shell is retained, including the Agent
flow and Trace / Logic / Evidence / State / Checkpoint / Architecture views; only
the Strategy workspace is narrowed to the rate strategy. The output is a teaching
approximation, not an executable bond-price model or investment recommendation.

FRED CSV calls use `native_http.http_get_text`, which keeps certificate verification
enabled while routing Python TLS through the operating system trust store via
`truststore`. Do not disable certificate verification to work around local CA errors.
The D1 public-data Tool declares two retries. The Runtime applies short exponential
backoff only to connection/time-out failures and records the failed attempt and
retry in Trace. If FRED remains unavailable after three total attempts, the HTTP
API returns `503 DATA_SOURCE_UNAVAILABLE` together with the partial Agent trace.

## Advanced experiment retained: R12 Step 9 event-market portfolio

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
      ↓ replay every trade ledger
Paper portfolio aggregation
      ↓ atomic preflight before every new intent / fill
Unsettled trade / acquisition cost / leg risk / provider / identity limits
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

Step 9 keeps each ledger immutable and adds a separate portfolio read model. It
replays every `.r12_paper_ledger/*.jsonl` stream, aggregates unsettled cost,
unmatched leg quantity, provider notional, same-settlement-identity concentration,
MTM completeness, and realized P&L. New intents and fills are serialized through
an atomic preflight; a rejected command appends no event. The current teaching
limits are explicit code configuration, not calibrated investment advice.
Exposure is conservatively added across trades; Step 9 gives no correlation,
diversification, or cross-trade netting credit.

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

## Run the Agent Graph & Live Stream console

```bash
python3 -m pip install -r requirements.txt
python3 serve_rates.py
```

Open:

```text
http://127.0.0.1:8000
```

The default page has only two work areas: **Agent Graph** and **Agent Live Stream**.

1. Click **Run Agent**. The default parameters remain 60 observations, z=1,
   20-observation holding period, $100/bp DV01 and 1bp round-trip cost. The
   default scenario now demonstrates **Circuit Breaker recovery** and completes
   a trade from the disclosed teaching snapshot.
2. Follow Goal → Planner → Runtime → C1 → D1 → Q1 → **A2 / A10** → J1 → S1 → E1.
   D1 still fetches one bulk dataset. A2 and A10 independently prepare the 2Y
   and 10Y series; J1 checks that both came from the same run and source batch.
   S1 consumes the joined output. Runtime remains active throughout. No LLM is used.
3. The stream includes every emitted node event, registry lookup, validation,
   Tool call (full arguments), Tool result (full output), retry and Eval result.
   Expand a row to inspect JSON; no observations are truncated.
4. Click a Graph node to filter events; click it again or “显示全部” to reset.
   “跟随最新” controls scrolling without discarding earlier events.
5. D1 discloses the actual provider, source date and offline-snapshot status.
   Failures retain received events and mark downstream nodes as unexecuted.
6. Export JSON to retain the completed run or a partial failure trace.

The `POST /api/rates/stream` transport uses `rate-ndjson-v1` for every frame,
one unique run ID per request and consecutive event sequence numbers. A closed
connection without a terminal result/error is not considered success. Source
attempt details are reported when D1 returns, not during individual network reads.
The console observes execution; closing its browser does not provide a durable
cancel/resume contract. The UI now requests `execution_mode="parallel"`; omitted
mode retains the previous serial API for compatibility. Existing serial
checkpoint/recovery and idempotency demos are unchanged. Parallel checkpoint
recovery is not implemented in this lesson.

### Current lessons: Circuit Breaker and bounded admission

The two new Runtime guards are visible as real graph nodes. **C1** protects an
external Tool from repeated calls while its dependency is unhealthy. **Q1**
controls how quickly work may enter Tools and keeps waiting work bounded.

| Scenario | Policy | Observe |
| --- | --- | --- |
| 熔断 · 冷却后恢复 (default) | Open after 2 consecutive D1 failures; 300ms cooldown | CLOSED → OPEN → HALF-OPEN; one probe succeeds; CLOSED; workflow continues |
| 熔断 · 阻止第三次调用 | Open after 2 failures; long cooldown | Third request is rejected before `tool_execution_started`; D1 and downstream fail closed |
| 背压 · 排队后放行 | 1 active Tool, queue capacity 1, 500ms admission interval | A2 gets a permit; A10 is QUEUED; after capacity and interval allow it, A10 is DEQUEUED and called |
| 过载 · 队满立即拒绝 | 1 active Tool, queue capacity 0 | A10 is rejected before any Tool call; Join and downstream remain blocked |

Engineering contract:

- Tool argument validation occurs before the circuit counts an execution
  failure. Two retryable upstream failures open C1. An OPEN rejection does not
  call the Tool and is not counted as another upstream failure.
- Cooldown does not prove recovery. OPEN becomes HALF-OPEN and permits one
  probe. Only a successful probe closes the circuit and resets its failure
  count; a failed probe reopens it.
- Q1 separates arrival from admission. A queued task has no Tool call or Tool
  result yet. FIFO promotion happens only after capacity is released and the
  minimum admission interval passes.
- The waiting room is finite. Full queues reject work immediately instead of
  consuming unbounded memory. Rejected work is never fabricated as a branch
  result, so the all-success Join remains blocked.
- Circuit and admission state are Runtime policy, not strategy logic. Teaching
  failures, cooldowns and queue sizes are disclosed in stream events. No broker
  or external write is added.
- For deterministic teaching, C1 and Q1 are scoped to one Run. A production
  deployment must share admission/circuit state per upstream dependency across
  concurrent Runs (and coordinate it across processes); this demo makes no
  claim of service-wide protection.

Source file: `rate_resilience.py`. The Runtime in `rate_parallel.py` remains the
single owner that orders guard, Tool, Observation and terminal stream events.

### Previous lesson: time budget and cooperative cancellation

The one new concept is a **run-level stop boundary**. A deadline and a user's
Stop click signal the same `RunControl`. A stop request is not a confirmation
that a Tool has stopped; it is not a thread kill and does not undo earlier work.

| Scenario | Budget / behavior | Observe |
| --- | --- | --- |
| 演示 · 1 秒预算 (default) | 1s budget; cooperative A2 would wait 2s | Deadline → stop request → A2 exits → run timed out; completed A10 stays complete |
| 演示 · 手动停止 | 30s budget; both branches wait up to 8s | Click Stop; keep the stream connected until both Tools acknowledge exit |
| 演示 · 晚到结果 | 1s budget; A2 deliberately ignores the stop signal for 2.4s | Remain in “停止中”; late output is shown as DISCARDED, never sent to Join |

The graph topology is unchanged. Amber dashed nodes mean **stop requested**,
not **already stopped**. The stream retains the budget, reason, request,
per-Tool acknowledgment, discarded output and final stop confirmation.
Connection loss without confirmation yields **状态未知**, not “已取消”.

Engineering contract:

- The budget uses a monotonic clock and covers the whole run, including D1.
  It limits acceptance of results and scheduling of later work; it is **not a
  hard upper bound on how long a blocking Tool takes to return**.
- All Tool calls run in bounded worker pools; the owner polls controls and
  writes the ordered stream. Cooperative waits, retries, series preparation
  and source-switch boundaries check the same run scope.
- A blocking network read retains its transport timeout and may not stop
  immediately. There is no claim that Python threads are forcibly terminated.
- `POST /api/rates/cancel` with `{ "run_id": "..." }` returns 202 for a stop
  request, 409 for a known terminal run and 404 for an unknown/expired run.
  Repeated requests do not create additional effects. Old run IDs cannot stop
  a new run. Controls are process-local with bounded terminal history.
- Success and cancellation are ordered at a locked terminal boundary. Late
  output stays audit-only; completed work is not rolled back. Serial legacy
  APIs and their checkpoint/idempotency contracts are unchanged.
- Keep the stream open after pressing Stop. `run_stopped` and the final error
  frame confirm termination only after submitted callables have exited.

Source files: `rate_control.py` holds the scope and registry; `rate_parallel.py`
owns execution and result acceptance. No broker or external writes are added.

### Previous lesson: concurrency and the all-success Join

Only one new concept is introduced: independent tasks may run together, but a
dependent task must wait for **all required successful results**. Runtime uses at
most two worker threads per run. Workers send events through a queue; one owner
assigns event sequence numbers, updates run state and writes the HTTP stream.
This is concurrent scheduling, not a claim of CPU speedup under the Python GIL.

The previous lesson's four choices remain available:

| Scenario | Data / timing | Observe |
| --- | --- | --- |
| 演示 · 2Y 较慢 | Official bundled snapshot; A2 waits 2s, A10 waits 0.4s | Both run; A10 completes; Join waits 1/2 for A2 |
| 演示 · 10Y 较慢 | Same snapshot; reverse the delays | Completion order reverses; Join still waits for both |
| 演示 · 10Y 失败 | Same snapshot; explicit A10 fault after 0.4s | A2 finishes; J1/S1/E1 never execute |
| 公开数据 · 无注入 | Original FRED → Treasury → disclosed snapshot fallback | No injected delay or failure; fast branches may finish too quickly to see overlap |

The delays and injected failures are recorded as `demo_*` events. Tools really
execute; the UI never replays an animation as a live run. On branch failure we
drain the already-running read-only sibling, then return a failure with its
completed results still in the trace. We do not claim to cancel a running Tool.

Core check: **“One branch finished” is not the same as “Join may proceed.”**
Try both speed orders, then the failure scenario, without changing the strategy.

Visualization is a required design consideration for every new Agent lesson:
show real state transitions and inspectable inputs/outputs, keep the default
view focused, and never animate a simulated process as live execution.

Current UI:

```text
web/rate_console.html        focused default page
web/rate_console.css         responsive Graph / Stream layout
web/rate_console_core.js     pure event and protocol reducer
web/rate_console.js          incremental DOM updates and stream reader
web/index.html               retained historical Workbench shell
web/rate_workbench.js        retained historical rate overlay
```

To revisit the advanced event-market experiment, run `python3 serve_r12.py`.

Console checks: `node --test test_rate_console.cjs` and
`python3 -m unittest test_rate_http test_rate_agent test_rate_parallel test_rate_control test_rate_ui_contract`.
For the optional real-browser smoke test, install Playwright in your test
environment and run `CHROMIUM_EXECUTABLE=/path/to/chromium node test_rate_console_browser.cjs`.
That test starts a temporary local HTTP server with explicitly labelled fixture
data; it tests rendering and streaming, not public-source availability.
