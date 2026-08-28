# Agent Engineering from Scratch

A step-by-step learning repository for building an agent runtime from first principles.

The goal is to understand the system underneath agent frameworks before using LangGraph, Agents SDKs, or other abstractions.

## Learning roadmap

- V0 — Minimal Agent Loop
- V0.1 — Replaceable Model Adapter
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

## Current stage: V0.1

V0 introduced the smallest possible loop:

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

V0.1 adds one engineering idea: **the model is replaceable**.

```text
                 Agent Runtime
                      ↓
                Model Contract
                 ↙         ↘
           FakeModel     OpenAIModel
```

`agent.py` contains the runtime and tool implementation. `model_adapters.py` converts provider-specific model responses into a tiny runtime-facing contract: either `tool_call` or `final`.

The central design principle is:

> Model decides **what** to do. Runtime controls **how** it is executed.

## Run deterministic V0/V0.1

```bash
python agent.py
```

This uses `FakeModel`, so it requires no API key.

## Run with a real OpenAI model

Install the SDK:

```bash
pip install -r requirements.txt
```

Set your API key in the environment:

```bash
export OPENAI_API_KEY="your_api_key_here"
```

Then run:

```bash
python run_real.py
```

The real adapter uses the OpenAI Responses API function-calling loop. Secrets are never stored in source code.

## Test

```bash
python -m unittest -v
```

The unit tests remain deterministic and do not call a live model API.
