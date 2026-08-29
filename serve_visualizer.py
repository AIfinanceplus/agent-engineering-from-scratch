"""Serve the V7 AgentState / StateStore visual debugger."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from agent import DEFAULT_MAX_STEPS, run_agent
from context import ExecutionContext
from model_adapters import FAKE_SCENARIOS, FakeModel
from state import InMemoryStateStore
from tools import TOOL_REGISTRY, reset_teaching_tools


WEB_DIR = Path(__file__).parent / "web"

# Browser chooses only a preset key. Identity itself is Runtime-owned.
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

        user_message = request_data.get(
            "message",
            "Calculate 10 + 20, then calculate 6 × 7.",
        )
        scenario = request_data.get("scenario", "multi_step")
        context_preset = request_data.get("context_preset", "general")
        max_steps = request_data.get("max_steps", DEFAULT_MAX_STEPS)

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

        events = []
        reset_teaching_tools()
        execution_context = CONTEXT_PRESETS[context_preset]
        state_store = InMemoryStateStore()

        try:
            final_answer = run_agent(
                user_message,
                model=FakeModel(scenario=scenario),
                on_event=events.append,
                max_steps=max_steps,
                execution_context=execution_context,
                state_store=state_store,
            )
            latest_state = state_store.load(execution_context.task_id)
            payload = {
                "ok": True,
                "scenario": scenario,
                "context_preset": context_preset,
                "execution_context": execution_context.to_dict(),
                "max_steps": max_steps,
                "tool_registry": [tool.trace_metadata() for tool in TOOL_REGISTRY.values()],
                "final_answer": final_answer,
                "latest_state": latest_state.to_dict() if latest_state is not None else None,
                "state_history": state_store.history(execution_context.task_id),
                "events": events,
            }
            status = 200
        except Exception as exc:
            latest_state = state_store.load(execution_context.task_id)
            payload = {
                "ok": False,
                "scenario": scenario,
                "context_preset": context_preset,
                "max_steps": max_steps,
                "error": f"{exc.__class__.__name__}: {exc}",
                "latest_state": latest_state.to_dict() if latest_state is not None else None,
                "state_history": state_store.history(execution_context.task_id),
                "events": events,
            }
            status = 500

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
    print("Agent Runtime Visual Debugger · V7")
    print("Open http://127.0.0.1:8000")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
