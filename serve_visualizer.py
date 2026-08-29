"""Serve the R2 multi-source macro research debugger.

Primary path: MultiSourceMacroPlanner -> Scheduler -> shared Runtime -> BLS/FRED/EIA
Source Adapters -> EvidenceStore -> freshness-aware synthesis -> citations -> Trace.
R1 and V11 teaching paths remain available as regressions.
"""

from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from agent import DEFAULT_MAX_STEPS, SimulatedCrash, run_agent
from checkpoint import JsonCheckpointStore
from context import ExecutionContext
from evals import EvalCase, run_eval_suite, score_result
from model_adapters import FAKE_SCENARIOS, FakeModel
from observability import TraceRecorder
from planner import CPIResearchPlanner, ResearchPlanner
from r2_planner import MultiSourceMacroPlanner
from r2_tooling import register_r2_tools
from scheduler import DAGScheduler
from tools import reset_teaching_tools


ROOT_DIR = Path(__file__).parent
WEB_DIR = ROOT_DIR / "web"
CHECKPOINT_DIR = ROOT_DIR / ".checkpoints"
register_r2_tools()

CONTEXT_PRESETS = {
    "general": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="macro-research-agent",
        task_id="visual-macro-root",
        trace_id="visual-macro-trace",
    ),
    "read_only": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="read-only-agent",
        task_id="visual-read-only-root",
        trace_id="visual-read-only-trace",
    ),
}


class VisualizerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_POST(self):
        if self.path != "/api/run":
            self.send_error(404, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            request_data = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Request body must be valid JSON")
            return

        action = request_data.get("action", "macro2")
        goal = request_data.get(
            "goal",
            "Assess current inflation pressure using CPI, market expectations, and gasoline evidence.",
        )
        context_preset = request_data.get("context_preset", "general")
        if context_preset not in CONTEXT_PRESETS:
            self.send_json(400, {"ok": False, "error": "Unknown context preset", "events": []})
            return

        execution_context = CONTEXT_PRESETS[context_preset]
        if action == "macro2":
            data_mode = request_data.get("data_mode", "fixture")
            reference_date = request_data.get("reference_date") or (
                "2026-03-20" if data_mode == "fixture" else date.today().isoformat()
            )
            self.run_multisource(
                goal,
                execution_context,
                data_mode=data_mode,
                reference_date=reference_date,
            )
            return
        if action == "macro":
            self.run_macro(
                goal,
                execution_context,
                data_mode=request_data.get("data_mode", "fixture"),
            )
            return
        if action == "research":
            self.run_research(goal, execution_context)
            return
        if action == "evals":
            self.run_evals(execution_context)
            return

        self.run_legacy_v8(request_data, action, execution_context)

    def run_multisource(
        self,
        goal: str,
        execution_context: ExecutionContext,
        *,
        data_mode: str,
        reference_date: str,
    ) -> None:
        events = []
        reset_teaching_tools()
        try:
            plan = MultiSourceMacroPlanner().plan(
                goal,
                mode=data_mode,
                reference_date=reference_date,
            )
            trace = TraceRecorder(execution_context.trace_id)
            result = DAGScheduler().run(
                plan,
                execution_context=execution_context,
                on_event=events.append,
                trace_recorder=trace,
            )
            payload = {
                "ok": result["ok"],
                "action": "macro2",
                "goal": goal,
                "data_mode": data_mode,
                "reference_date": reference_date,
                "execution_context": execution_context.to_dict(),
                "plan": result["plan"],
                "results": result.get("results", {}),
                "final_result": result.get("final_result"),
                "final_artifact": result.get("final_artifact"),
                "evidence": result.get("evidence", []),
                "citations": result.get("citations", []),
                "trace": result.get("trace"),
                "events": events,
            }
            status = 200 if result["ok"] else 500
            if not result["ok"]:
                payload["error"] = result.get("error")
        except Exception as exc:
            payload = {
                "ok": False,
                "action": "macro2",
                "goal": goal,
                "data_mode": data_mode,
                "reference_date": reference_date,
                "error": f"{exc.__class__.__name__}: {exc}",
                "events": events,
            }
            status = 500
        self.send_json(status, payload)

    def run_macro(
        self,
        goal: str,
        execution_context: ExecutionContext,
        *,
        data_mode: str,
    ) -> None:
        events = []
        reset_teaching_tools()
        try:
            plan = CPIResearchPlanner().plan(goal, data_mode=data_mode)
            trace = TraceRecorder(execution_context.trace_id)
            result = DAGScheduler().run(
                plan,
                execution_context=execution_context,
                on_event=events.append,
                trace_recorder=trace,
            )
            payload = {
                "ok": result["ok"],
                "action": "macro",
                "goal": goal,
                "data_mode": data_mode,
                "execution_context": execution_context.to_dict(),
                "plan": result["plan"],
                "results": result.get("results", {}),
                "final_result": result.get("final_result"),
                "final_artifact": result.get("final_artifact"),
                "evidence": result.get("evidence", []),
                "citations": result.get("citations", []),
                "trace": result.get("trace"),
                "events": events,
            }
            status = 200 if result["ok"] else 500
            if not result["ok"]:
                payload["error"] = result.get("error")
        except Exception as exc:
            payload = {
                "ok": False,
                "action": "macro",
                "goal": goal,
                "data_mode": data_mode,
                "error": f"{exc.__class__.__name__}: {exc}",
                "events": events,
            }
            status = 500
        self.send_json(status, payload)

    def run_research(self, goal: str, execution_context: ExecutionContext) -> None:
        events = []
        reset_teaching_tools()
        try:
            plan = ResearchPlanner().plan(goal)
            trace = TraceRecorder(execution_context.trace_id)
            result = DAGScheduler().run(
                plan,
                execution_context=execution_context,
                on_event=events.append,
                trace_recorder=trace,
            )
            interactive_case = EvalCase(
                case_id="interactive-research",
                goal=goal,
                min_confidence=0.8,
            )
            eval_report = score_result(interactive_case, result).to_dict()
            payload = {
                "ok": result["ok"],
                "action": "research",
                "goal": goal,
                "execution_context": execution_context.to_dict(),
                "plan": result["plan"],
                "results": result.get("results", {}),
                "final_result": result.get("final_result"),
                "final_artifact": result.get("final_artifact"),
                "evidence": result.get("evidence", []),
                "citations": result.get("citations", []),
                "trace": result.get("trace"),
                "eval_report": eval_report,
                "events": events,
            }
            status = 200 if result["ok"] else 500
            if not result["ok"]:
                payload["error"] = result.get("error")
        except Exception as exc:
            payload = {
                "ok": False,
                "action": "research",
                "goal": goal,
                "error": f"{exc.__class__.__name__}: {exc}",
                "events": events,
            }
            status = 500
        self.send_json(status, payload)

    def run_evals(self, execution_context: ExecutionContext) -> None:
        reset_teaching_tools()
        try:
            suite = run_eval_suite(execution_context=execution_context)
            self.send_json(200, {"ok": True, "action": "evals", "eval_suite": suite})
        except Exception as exc:
            self.send_json(
                500,
                {
                    "ok": False,
                    "action": "evals",
                    "error": f"{exc.__class__.__name__}: {exc}",
                },
            )

    def run_legacy_v8(self, request_data, action, execution_context):
        if action not in {"run", "crash", "resume", "clear"}:
            self.send_json(400, {"ok": False, "error": f"Unknown action: {action}", "events": []})
            return
        scenario = request_data.get("scenario", "multi_step")
        max_steps = request_data.get("max_steps", DEFAULT_MAX_STEPS)
        if scenario not in FAKE_SCENARIOS:
            self.send_json(400, {"ok": False, "error": "Unknown scenario", "events": []})
            return
        state_store = JsonCheckpointStore(CHECKPOINT_DIR)
        if action == "clear":
            state_store.clear(execution_context.task_id)
            self.send_json(200, {"ok": True, "action": action, "events": []})
            return
        if action in {"run", "crash"}:
            state_store.clear(execution_context.task_id)
        events = []
        crashed = False
        final_answer = None
        error_text = None
        try:
            final_answer = run_agent(
                request_data.get("message", "Calculate 10 + 20, then 6 × 7."),
                model=FakeModel(scenario=scenario),
                on_event=events.append,
                max_steps=max_steps,
                execution_context=execution_context,
                state_store=state_store,
                resume=(action == "resume"),
                crash_after_observations=(1 if action == "crash" else None),
            )
            status = 200
        except SimulatedCrash as exc:
            crashed = True
            error_text = str(exc)
            status = 200
        except Exception as exc:
            error_text = f"{exc.__class__.__name__}: {exc}"
            status = 500
        self.send_json(status, {
            "ok": status == 200,
            "action": action,
            "final_answer": final_answer,
            "crashed": crashed,
            "error": error_text,
            "events": events,
        })

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[visualizer] {format % args}")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), VisualizerHandler)
    print("Agent Research Workbench · R2")
    print("Open http://127.0.0.1:8000")
    print("Primary view: BLS + FRED + EIA -> Evidence -> Freshness -> Synthesis")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
