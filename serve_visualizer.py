"""Serve the V9 Planner + DAG Scheduler visual debugger.

V9 makes the plan the primary UI. The V8 crash/resume endpoint remains
available for backward-compatible experiments, but the default teaching path is
Planner -> Scheduler -> existing task Runtime.
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from agent import DEFAULT_MAX_STEPS, SimulatedCrash, run_agent
from checkpoint import JsonCheckpointStore
from context import ExecutionContext
from model_adapters import FAKE_SCENARIOS, FakeModel
from planner import DeterministicPlanner
from scheduler import DAGScheduler
from tools import TOOL_REGISTRY, reset_teaching_tools


ROOT_DIR = Path(__file__).parent
WEB_DIR = ROOT_DIR / "web"
CHECKPOINT_DIR = ROOT_DIR / ".checkpoints"

CONTEXT_PRESETS = {
    "general": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="general-agent",
        task_id="visual-plan-root",
        trace_id="visual-plan-trace",
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

        action = request_data.get("action", "plan")
        goal = request_data.get(
            "goal",
            "Calculate two independent values, then combine their results.",
        )
        context_preset = request_data.get("context_preset", "general")

        if context_preset not in CONTEXT_PRESETS:
            self.send_json(
                400,
                {"ok": False, "error": f"Unknown context preset: {context_preset}", "events": []},
            )
            return

        execution_context = CONTEXT_PRESETS[context_preset]

        if action == "plan":
            self.run_plan(goal, execution_context)
            return

        self.run_legacy_v8(request_data, action, execution_context)

    def run_plan(self, goal: str, execution_context: ExecutionContext) -> None:
        events = []
        reset_teaching_tools()

        try:
            plan = DeterministicPlanner().plan(goal)
            result = DAGScheduler().run(
                plan,
                execution_context=execution_context,
                on_event=events.append,
            )
            payload = {
                "ok": result["ok"],
                "action": "plan",
                "goal": goal,
                "execution_context": execution_context.to_dict(),
                "plan": result["plan"],
                "results": result.get("results", {}),
                "final_result": result.get("final_result"),
                "events": events,
            }
            if not result["ok"]:
                payload["error"] = result.get("error")
                status = 500
            else:
                status = 200
        except Exception as exc:
            payload = {
                "ok": False,
                "action": "plan",
                "goal": goal,
                "error": f"{exc.__class__.__name__}: {exc}",
                "events": events,
            }
            status = 500

        self.send_json(status, payload)

    def run_legacy_v8(
        self,
        request_data: dict,
        action: str,
        execution_context: ExecutionContext,
    ) -> None:
        """Keep V8 crash/resume callable without making it primary UI."""
        if action not in {"run", "crash", "resume", "clear"}:
            self.send_json(400, {"ok": False, "error": f"Unknown action: {action}", "events": []})
            return

        scenario = request_data.get("scenario", "multi_step")
        max_steps = request_data.get("max_steps", DEFAULT_MAX_STEPS)
        user_message = request_data.get(
            "message",
            "Calculate 10 + 20, then calculate 6 × 7.",
        )

        if scenario not in FAKE_SCENARIOS:
            self.send_json(400, {"ok": False, "error": f"Unknown scenario: {scenario}", "events": []})
            return
        if (
            not isinstance(max_steps, int)
            or isinstance(max_steps, bool)
            or max_steps < 1
            or max_steps > 20
        ):
            self.send_json(400, {"ok": False, "error": "max_steps must be an integer from 1 to 20", "events": []})
            return

        state_store = JsonCheckpointStore(CHECKPOINT_DIR)
        if action == "clear":
            state_store.clear(execution_context.task_id)
            self.send_json(200, {"ok": True, "action": action, "events": []})
            return
        if action in {"run", "crash"}:
            state_store.clear(execution_context.task_id)

        events = []
        reset_teaching_tools()
        crashed = False
        final_answer = None
        error_text = None

        try:
            final_answer = run_agent(
                user_message,
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

        latest_state = state_store.load(execution_context.task_id)
        self.send_json(
            status,
            {
                "ok": status == 200,
                "action": action,
                "final_answer": final_answer,
                "crashed": crashed,
                "error": error_text,
                "latest_state": latest_state.to_dict() if latest_state else None,
                "events": events,
            },
        )

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
    print("Agent Runtime Visual Debugger · V9")
    print("Open http://127.0.0.1:8000")
    print("Primary view: Planner + DAG Scheduler")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
