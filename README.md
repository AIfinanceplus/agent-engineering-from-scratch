# Agent Engineering from Scratch

A step-by-step learning repository for building an agent runtime from first principles.

The goal is to understand the system underneath agent frameworks before using LangGraph, Agents SDKs, or other abstractions.

## Learning roadmap

- V0 — Minimal Agent Loop
- V0.1 — Replaceable Model Adapter
- V0.2 — Visual Runtime Debugger
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

## Current stage: V0.2

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

V0.1 made the model provider replaceable:

```text
                 Agent Runtime
                      ↓
                Model Contract
                 ↙         ↘
           FakeModel     OpenAIModel
```

V0.2 adds **observability without changing control**. `run_agent()` accepts an optional `on_event` callback. The visual debugger uses those real runtime events to animate the architecture, show the matching code, and explain each step in Chinese.

```text
Actual Python Runtime
        ↓ emits events
   on_event observer
        ↓
Local Web Server
        ↓
Browser Visual Debugger
```

The observer is intentionally read-only. It can see what happened, but it does not decide what happens next.

The central design principle remains:

> Model decides **what** to do. Runtime controls **how** it is executed.

## Run deterministic Agent Runtime

```bash
python agent.py
```

This uses `FakeModel`, so it requires no API key.

## Run the visual debugger

```bash
python serve_visualizer.py
```

Then open:

```text
http://127.0.0.1:8000
```

In the browser you can:

- run the real deterministic V0.2 runtime
- step forward and backward through execution events
- auto-play the complete Agent Loop
- see which architecture component is active
- see the matching Python code for each step
- read Chinese design commentary explaining why the boundary exists
- inspect the raw runtime event payload

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

The unit tests remain deterministic and do not call a live model API. CI also checks Python syntax and browser JavaScript syntax.
