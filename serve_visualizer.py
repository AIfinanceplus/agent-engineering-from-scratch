"""Serve the V8 durable checkpoint visual debugger."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from agent import DEFAULT_MAX_STEPS, SimulatedCrash, run_agent
from checkpoint import JsonCheckpointStore
from context import ExecutionContext
from model_adapters import FAKE_SCENARIOS, FakeModel
from tools import TOOL_REGISTRY, reset_teaching_tools


ROOT_DIR = Path(__file__).parent
WEB_DIR = ROOT_DIR / "web"
CHECKPOINT_DIR = ROOT_DIR / ".checkpoints"

# Browser chooses only a preset key. Identity itself remains Runtime-owned.
CONTEXT_PRESETS = {
    "general": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="general-agent",
        task_id="visual-task-general",
        trace_id="visual-trace-general",
    ),
    "read_only": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="read-only-agent",
        task_id="visual-task-read-only",
        trace_id="visual-trace-read-only",
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

        action = request_data.get("action", "run")
        user_message = request_data.get(
            "message",
            "Calculate 10 + 20, then calculate 6 × 7.",
        )
        scenario = request_data.get("scenario", "multi_step")
        context_preset = request_data.get("context_preset", "general")
        max_steps = request_data.get("max_steps", DEFAULT_MAX_STEPS)

        if action not in {"run", "crash", "resume", "clear"}:
            self.send_json(400, {"ok": False, "error": f"Unknown action: {action}", "events": []})
            return
        if scenario not in FAKE_SCENARIOS:
            self.send_json(400, {"ok": False, "error": f"Unknown scenario: {scenario}", "events": []})
            return
        if context_preset not in CONTEXT_PRESETS:
            self.send_json(400, {"ok": False, "error": f"Unknown context preset: {context_preset}", "events": []})
            return
        if (
            not isinstance(max_steps, int)
            or isinstance(max_steps, bool)
            or max_steps < 1
            or max_steps > 20
        ):
            self.send_json(400, {"ok": False, "error": "max_steps must be an integer from 1 to 20", "events": []})
            return

        execution_context = CONTEXT_PRESETS[context_preset]
        state_store = JsonCheckpointStore(CHECKPOINT_DIR)

        if action == "clear":
            state_store.clear(execution_context.task_id)
            self.send_json(
                200,
                {
                    "ok": True,
                    "action": action,
                    "checkpoint_exists": False,
                    "latest_state": None,
                    "state_history": [],
                    "events": [],
                },
            )
            return

        # A normal run or crash demo starts a fresh task history. Resume keeps
        # the durable file created by the previous request/process.
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
        payload = {
            "ok": status == 200,
            "action": action,
            "scenario": scenario,
            "context_preset": context_preset,
            "execution_context": execution_context.to_dict(),
            "max_steps": max_steps,
            "tool_registry": [tool.trace_metadata() for tool in TOOL_REGISTRY.values()],
            "final_answer": final_answer,
            "crashed": crashed,
            "error": error_text,
            "checkpoint_exists": state_store.exists(execution_context.task_id),
            "checkpoint_path": state_store.checkpoint_path(execution_context.task_id),
            "latest_state": latest_state.to_dict() if latest_state is not None else None,
            "state_history": state_store.history(execution_context.task_id),
            "events": events,
        }
        self.send_json(status, payload)

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[visualizer] {format % args}")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), VisualizerHandler)
    print("Agent Runtime Visual Debugger · V8")
    print("Open http://127.0.0.1:8000")
    print(f"Durable checkpoints: {CHECKPOINT_DIR}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
