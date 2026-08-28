# Agent Engineering from Scratch

A step-by-step learning repository for building an agent runtime from first principles.

The goal is to understand the system underneath agent frameworks before using LangGraph, Agents SDKs, or other abstractions.

## Learning roadmap

- V0 — Minimal Agent Loop
- V1 — Tool Registry
- V2 — Validation + MAX_STEPS
- V3 — Retry + Loop Detection
- V4 — Tool Object
- V5 — Policy Engine
- V6 — ExecutionContext
- V7 — StateStore
- V8 — Checkpoint / Durable Execution
- V9 — Planner + DAG Scheduler
- V10 — Evidence / Synthesis / Citation
- V11 — Tracing + Evals

## Current stage: V0

V0 intentionally uses a deterministic fake model adapter so the core control loop can be run and tested without an API key.

Core loop:

```text
User
  ↓
Model decides an action
  ↓
Tool Call
  ↓
Runtime executes Python function
  ↓
Observation
  ↓
Model produces final answer
```

The central design principle is:

> Model decides **what** to do. Runtime controls **how** it is executed.

## Run

```bash
python agent.py
```

## Test

```bash
python -m unittest -v
```
