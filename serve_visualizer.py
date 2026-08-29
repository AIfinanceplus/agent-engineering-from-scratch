"""Serve the active R2 API-only macro research workbench.

The browser has two actions only:
- api_run: one live BLS + FRED + EIA research run.
- api_evals: score the same live run against explicit R2 contracts.

External source failures are application-level results returned as HTTP 200 with
structured provider/task diagnostics. A bad upstream API should not look like a
mysterious web-server crash.
"""

from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

from context import ExecutionContext
from observability import TraceRecorder
from r2_api_evals import make_api_eval_suite
from r2_api_planner import APIMacroPlanner
from r2_api_tooling import register_api_tools
from scheduler import DAGScheduler


ROOT_DIR = Path(__file__).parent
WEB_DIR = ROOT_DIR / "web"
register_api_tools()

CONTEXT_PRESETS = {
    "general": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="macro-research-agent",
        task_id="api-macro-root",
        trace_id="api-macro-trace",
    ),
    "read_only": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="read-only-agent",
        task_id="api-read-only-root",
        trace_id="api-read-only-trace",
    ),
}

TASK_PROVIDER = {
    "H1": "BLS",
    "C1": "BLS",
    "F1": "FRED",
    "G1": "EIA",
    "A1": "ANALYSIS",
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
            self.send_json(400, {"ok": False, "error": "Request body must be valid JSON"})
            return

        action = request_data.get("action", "api_run")
        context_preset = request_data.get("context_preset", "general")
        if context_preset not in CONTEXT_PRESETS:
            self.send_json(400, {"ok": False, "error": "Unknown context preset"})
            return

        goal = request_data.get(
            "goal",
            "Assess current inflation pressure using headline CPI, core CPI, market inflation expectations, and gasoline prices.",
        )
        execution_context = CONTEXT_PRESETS[context_preset]

        if action == "api_run":
            result = self.execute_api(goal, execution_context)
            self.send_json(200, result)
            return

        if action == "api_evals":
            result = self.execute_api(goal, execution_context)
            suite = make_api_eval_suite(result)
            self.send_json(
                200,
                {
                    "ok": result.get("ok", False),
                    "action": "api_evals",
                    "research_result": result,
                    "eval_suite": suite,
                },
            )
            return

        self.send_json(400, {"ok": False, "error": f"Unknown action: {action}"})

    def execute_api(self, goal: str, execution_context: ExecutionContext) -> dict:
        events = []
        reference_date = date.today().isoformat()
        missing = [name for name in ("FRED_API_KEY", "EIA_API_KEY") if not os.environ.get(name)]
        if missing:
            return {
                "ok": False,
                "action": "api_run",
                "stage": "credentials",
                "reference_date": reference_date,
                "error": {
                    "code": "missing_credentials",
                    "message": "Required API credentials are missing.",
                    "missing_env": missing,
                },
                "events": [],
            }

        try:
            plan = APIMacroPlanner().plan(goal, reference_date=reference_date)
            trace = TraceRecorder(execution_context.trace_id)
            result = DAGScheduler().run(
                plan,
                execution_context=execution_context,
                on_event=events.append,
                trace_recorder=trace,
            )
            payload = {
                "ok": result["ok"],
                "action": "api_run",
                "goal": goal,
                "reference_date": reference_date,
                "execution_context": execution_context.to_dict(),
                "plan": result.get("plan"),
                "results": result.get("results", {}),
                "final_result": result.get("final_result"),
                "final_artifact": result.get("final_artifact"),
                "evidence": result.get("evidence", []),
                "citations": result.get("citations", []),
                "trace": result.get("trace"),
                "events": events,
            }
            if not result["ok"]:
                payload["stage"] = "source_or_runtime"
                payload["error"] = _source_failure(events, result.get("error"))
            return payload
        except Exception as exc:
            return {
                "ok": False,
                "action": "api_run",
                "stage": "unhandled",
                "reference_date": reference_date,
                "error": {
                    "code": exc.__class__.__name__,
                    "message": str(exc),
                },
                "events": events,
            }

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[visualizer] {format % args}")


def _source_failure(events: list[dict], fallback) -> dict:
    failed = next((event for event in reversed(events) if event.get("type") == "task_failed"), None)
    if failed is None:
        return {
            "code": "runtime_failed",
            "message": str(fallback or "API research run failed"),
        }
    task_id = failed.get("task_id")
    error = failed.get("error") or {}
    return {
        "code": error.get("code", "task_failed"),
        "message": error.get("message", str(error)),
        "task_id": task_id,
        "provider": TASK_PROVIDER.get(task_id, "UNKNOWN"),
    }


def main():
    fred_ready = bool(os.environ.get("FRED_API_KEY"))
    eia_ready = bool(os.environ.get("EIA_API_KEY"))
    server = ThreadingHTTPServer(("127.0.0.1", 8000), VisualizerHandler)
    print("Agent Research Workbench · R2 API-only")
    print("Open http://127.0.0.1:8000")
    print("Sources: BLS API + FRED API + EIA API")
    print(f"Credentials: FRED={'READY' if fred_ready else 'MISSING'}, EIA={'READY' if eia_ready else 'MISSING'}")
    print("Upstream API failures are returned as structured source diagnostics, not HTTP 500.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
