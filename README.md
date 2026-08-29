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

## Current stage: V10 — Evidence / Synthesis / Citation

V9 could execute a multi-task DAG. V10 upgrades Task outputs from bare values into research artifacts with provenance.

```text
Research Goal
    ↓
ResearchPlanner
    ↓
E1: collect Evidence ──┐
                       ├──> S1: synthesize
E2: collect Evidence ──┘
    ↓                         ↓
EvidenceStore          verified evidence IDs
    ↓                         ↓
source + claim + confidence + citations
                              ↓
                         Final Answer
```

### The key rule

Citation is not decoration added after writing the answer.

```text
BAD
Model writes conclusion
    ↓
append [1] [2]

V10
Evidence enters Runtime
    ↓
assign evidence_id
    ↓
store source / claim / confidence
    ↓
Synthesis references evidence_ids
    ↓
EvidenceStore verifies those IDs
    ↓
render citations
```

## Synthetic teaching data

All bundled V10 evidence is intentionally synthetic. It is used only to teach lineage and must not be interpreted as real macroeconomic data.

```text
E1
Teaching Energy Bulletin
Synthetic Data Lab
value = 0.4 percentage points
confidence = 0.92

E2
Teaching Shelter Bulletin
Synthetic Data Lab
value = 0.3 percentage points
confidence = 0.88
```

S1 depends on E1 and E2. The synthesis Tool receives the full evidence objects, not only their numeric values, and produces:

```text
combined value = 0.7 percentage points
confidence = 0.88
citations = [E1] [E2]
```

The confidence is deliberately conservative: the teaching synthesizer uses the lower supporting confidence.

## Evidence model

`evidence.py` introduces:

```python
SourceRef
EvidenceRecord
EvidenceStore
```

An EvidenceRecord carries:

```text
evidence_id
claim
value
unit
confidence
source_id
title
publisher
uri
```

The Scheduler registers evidence as soon as a Task returns it:

```python
record = EvidenceRecord.from_dict(result)
evidence_store.add(record)
task.evidence_ids = [record.evidence_id]
```

When S1 returns a synthesis, the Scheduler verifies its claimed evidence IDs against the store:

```python
citations = evidence_store.citations(evidence_ids)
```

An unknown ID fails instead of producing an unsupported citation.

## Responsibilities remain separate

```text
Planner          = WHAT research tasks exist
Scheduler        = WHEN each task is READY
ExecutionContext = WHO is executing
Policy           = whether that identity may execute the capability
Runtime          = HOW one task executes safely
EvidenceStore    = WHAT evidence/provenance has actually been collected
Synthesis        = WHAT can be concluded from that evidence
```

V10 does not replace the V1–V9 layers. Every evidence and synthesis Task still goes through Tool validation, Policy, AgentState, and the existing Runtime.

## Compact visual debugger

Run:

```bash
python serve_visualizer.py
```

Open:

```text
http://127.0.0.1:8000
```

The UI keeps the compact three-pane layout:

```text
PLAN            RUN                 CODE
research tasks  evidence lineage    matching Python
E1 / E2 / S1    selected events     WHY / NEXT
status          current progress     citations
```

Raw evidence, plan state, and Runtime details are still available in collapsible sections instead of permanently consuming the screen.

Recommended sequence:

1. `ResearchPlanner created DAG` — E1/E2 READY, S1 blocked.
2. E1 executes through Runtime and returns a structured EvidenceRecord.
3. `E1 provenance registered` — inspect source, claim, confidence.
4. E2 repeats the same process.
5. Scheduler now releases S1.
6. S1 receives the complete E1/E2 evidence objects.
7. `Synthesis verified` — EvidenceStore validates `[E1]` and `[E2]`.
8. Final result is returned together with evidence, citations, and confidence.

## Tests

```bash
python -m unittest -v
```

V10 verifies:

- ResearchPlanner creates E1/E2 → S1 dependencies;
- S1 cannot start until both evidence Tasks complete;
- evidence round-trips without losing source or confidence;
- EvidenceStore rejects unknown citation IDs;
- final synthesis value is 0.7 with confidence 0.88;
- citations are exactly `[E1]` and `[E2]` and correspond to stored evidence;
- Plan State carries evidence/citation IDs;
- all prior Planner, Scheduler, Runtime, Policy, Retry, Checkpoint, State, and validation tests continue to run.
