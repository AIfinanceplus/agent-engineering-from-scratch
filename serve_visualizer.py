"""Serve the active R4 source-health + R3 research intelligence workbench.

R4 adds an operational source boundary before research debugging:
Source Health -> Question -> Subquestions -> Source Intents -> Query Specs ->
dynamic DAG -> Runtime -> Evidence -> Synthesis -> Citations -> Trace/Evals.
"""

from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

from context import ExecutionContext
from observability import TraceRecorder
from r3_evals import make_r3_eval_suite
from r3_planner import R3ResearchPlanner
from r3_tooling import register_r3_tools
from r4_source_health import run_source_health
from scheduler import DAGScheduler


ROOT_DIR = Path(__file__).parent
WEB_DIR = ROOT_DIR / "web"
register_r3_tools()

CONTEXT_PRESETS = {
    "general": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="macro-research-agent",
        task_id="r4-research-root",
        trace_id="r4-research-trace",
    ),
    "read_only": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="read-only-agent",
        task_id="r4-read-only-root",
        trace_id="r4-read-only-trace",
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
            self.send_json(400, {"ok": False, "error": "Request body must be valid JSON"})
            return

        action = request_data.get("action", "r3_run")

        if action == "source_health":
            try:
                providers = request_data.get("providers")
                report = run_source_health(providers)
                self.send_json(
                    200,
                    {
                        "ok": report["ready"],
                        "action": "source_health",
                        "source_health": report,
                    },
                )
            except Exception as exc:
                self.send_json(
                    200,
                    {
                        "ok": False,
                        "action": "source_health",
                        "source_health": None,
                        "error": {"code": exc.__class__.__name__, "message": str(exc)},
                    },
                )
            return

        context_preset = request_data.get("context_preset", "general")
        if context_preset not in CONTEXT_PRESETS:
            self.send_json(400, {"ok": False, "error": "Unknown context preset"})
            return

        question = request_data.get(
            "goal",
            "Assess current inflation pressure using headline CPI, core CPI, market inflation expectations, and gasoline prices.",
        )
        execution_context = CONTEXT_PRESETS[context_preset]

        if action == "r3_run":
            self.send_json(200, self.execute_r3(question, execution_context))
            return

        if action == "r3_evals":
            result = self.execute_r3(question, execution_context)
            blueprint = result.get("blueprint") or {}
            suite = make_r3_eval_suite(blueprint, result) if blueprint else {
                "passed": 0,
                "total": 1,
                "pass_rate": 0.0,
                "cases": [],
                "error": "No blueprint was produced, so R3 evals could not run.",
            }
            self.send_json(
                200,
                {
                    "ok": result.get("ok", False),
                    "action": "r3_evals",
                    "research_result": result,
                    "eval_suite": suite,
                },
            )
            return

        self.send_json(400, {"ok": False, "error": f"Unknown action: {action}"})

    def execute_r3(self, question: str, execution_context: ExecutionContext) -> dict:
        reference_date = date.today().isoformat()
        events = [{"type": "research_question_received", "question": question}]

        try:
            blueprint_obj, plan = R3ResearchPlanner().build(
                question,
                reference_date=reference_date,
            )
            blueprint = blueprint_obj.to_dict()
        except Exception as exc:
            return {
                "ok": False,
                "action": "r3_run",
                "stage": "decomposition_or_query_compile",
                "reference_date": reference_date,
                "error": {"code": exc.__class__.__name__, "message": str(exc)},
                "events": events,
            }

        events.append(
            {
                "type": "decomposition_created",
                "subquestions": blueprint["subquestions"],
                "intents": blueprint["intents"],
            }
        )
        events.append(
            {
                "type": "queries_compiled",
                "queries": blueprint["queries"],
            }
        )

        required_env = sorted(
            {
                name
                for query in blueprint["queries"]
                for name in query.get("requires_env", [])
            }
        )
        missing = [name for name in required_env if not os.environ.get(name)]
        if missing:
            return {
                "ok": False,
                "action": "r3_run",
                "stage": "credentials",
                "reference_date": reference_date,
                "blueprint": blueprint,
                "error": {
                    "code": "missing_credentials",
                    "message": "Credentials are required only for the sources selected by Query Compiler.",
                    "missing_env": missing,
                },
                "events": events,
            }

        try:
            trace = TraceRecorder(execution_context.trace_id)
            result = DAGScheduler().run(
                plan,
                execution_context=execution_context,
                on_event=events.append,
                trace_recorder=trace,
            )
            payload = {
                "ok": result["ok"],
                "action": "r3_run",
                "question": question,
                "reference_date": reference_date,
                "execution_context": execution_context.to_dict(),
                "blueprint": blueprint,
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
                provider_map = {
                    query["query_id"]: query["provider"]
                    for query in blueprint["queries"]
                }
                provider_map["S1"] = "ANALYSIS"
                payload["stage"] = "source_or_runtime"
                payload["error"] = _source_failure(
                    events,
                    result.get("error"),
                    provider_map,
                )
            return payload
        except Exception as exc:
            return {
                "ok": False,
                "action": "r3_run",
                "stage": "unhandled",
                "reference_date": reference_date,
                "blueprint": blueprint,
                "error": {"code": exc.__class__.__name__, "message": str(exc)},
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


def _source_failure(events: list[dict], fallback, provider_map: dict[str, str]) -> dict:
    failed = next((event for event in reversed(events) if event.get("type") == "task_failed"), None)
    if failed is None:
        return {"code": "runtime_failed", "message": str(fallback or "R3 research run failed")}
    task_id = failed.get("task_id")
    error = failed.get("error") or {}
    return {
        "code": error.get("code", "task_failed"),
        "message": error.get("message", str(error)),
        "task_id": task_id,
        "provider": provider_map.get(task_id, "UNKNOWN"),
    }


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), VisualizerHandler)
    print("Agent Research Workbench · R4")
    print("Open http://127.0.0.1:8000")
    print("Source Health: real BLS + FRED + EIA smoke tests through native OS TLS trust")
    print("Research: Question -> Subquestions -> Source Intents -> Query Specs -> Dynamic DAG -> Evidence")
    print("Source diagnostics never expose FRED_API_KEY or EIA_API_KEY values.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
