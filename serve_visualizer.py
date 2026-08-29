"""Serve the active R6 investment/policy domain research workbench.

R6 preserves R4 source health, R3 dynamic query generation, and R5 Evidence
quality. It adds a second grounded synthesis layer:
Evidence -> S1 research synthesis -> D1 investment/policy decision brief.
"""

from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

from context import ExecutionContext
from observability import TraceRecorder
from r4_source_health import run_source_health
from r6_evals import make_r6_eval_suite
from r6_planner import R6ResearchPlanner
from r6_tooling import register_r6_tools
from scheduler import DAGScheduler


ROOT_DIR = Path(__file__).parent
WEB_DIR = ROOT_DIR / "web"
register_r6_tools()

CONTEXT_PRESETS = {
    "general": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="macro-research-agent",
        task_id="r6-research-root",
        trace_id="r6-research-trace",
    ),
    "read_only": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="read-only-agent",
        task_id="r6-read-only-root",
        trace_id="r6-read-only-trace",
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

        action = request_data.get("action", "r6_run")
        if action == "source_health":
            self._source_health(request_data)
            return

        context_preset = request_data.get("context_preset", "general")
        if context_preset not in CONTEXT_PRESETS:
            self.send_json(400, {"ok": False, "error": "Unknown context preset"})
            return

        domain = request_data.get("domain", "investment")
        if domain not in {"investment", "policy"}:
            self.send_json(400, {"ok": False, "error": "domain must be investment or policy"})
            return

        question = request_data.get(
            "goal",
            "Assess current inflation pressure using headline CPI, core CPI, market inflation expectations, and gasoline prices.",
        )
        execution_context = CONTEXT_PRESETS[context_preset]

        # Keep the older action names as compatibility aliases for cached R5 UI.
        if action in {"r6_run", "r3_run"}:
            self.send_json(200, self.execute_research(question, domain, execution_context))
            return

        if action in {"r6_evals", "r3_evals"}:
            result = self.execute_research(question, domain, execution_context)
            blueprint = result.get("blueprint") or {}
            suite = make_r6_eval_suite(blueprint, result, domain) if blueprint else {
                "passed": 0,
                "total": 1,
                "pass_rate": 0.0,
                "cases": [],
                "error": "No blueprint was produced, so R6 evals could not run.",
            }
            self.send_json(
                200,
                {
                    "ok": result.get("ok", False),
                    "action": "r6_evals",
                    "domain": domain,
                    "research_result": result,
                    "eval_suite": suite,
                },
            )
            return

        self.send_json(400, {"ok": False, "error": f"Unknown action: {action}"})

    def _source_health(self, request_data: dict) -> None:
        try:
            report = run_source_health(request_data.get("providers"))
            self.send_json(
                200,
                {"ok": report["ready"], "action": "source_health", "source_health": report},
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

    def execute_research(
        self,
        question: str,
        domain: str,
        execution_context: ExecutionContext,
    ) -> dict:
        reference_date = date.today().isoformat()
        events = [
            {"type": "research_question_received", "question": question, "domain": domain}
        ]

        try:
            blueprint_obj, plan = R6ResearchPlanner().build(
                question,
                domain=domain,
                reference_date=reference_date,
            )
            blueprint = blueprint_obj.to_dict()
        except Exception as exc:
            return {
                "ok": False,
                "action": "r6_run",
                "domain": domain,
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
        events.append({"type": "queries_compiled", "queries": blueprint["queries"]})
        events.append(
            {
                "type": "domain_lens_selected",
                "domain": domain,
                "detail": "Domain lens is explicit input; it does not change source Evidence collection.",
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
                "action": "r6_run",
                "domain": domain,
                "stage": "credentials",
                "reference_date": reference_date,
                "blueprint": blueprint,
                "error": {
                    "code": "missing_credentials",
                    "message": "Credentials are required only for sources selected by Query Compiler.",
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
            results = result.get("results", {})
            s1 = results.get("S1") or {}
            d1 = results.get("D1") or result.get("final_artifact") or {}
            if result.get("ok") and s1.get("quality"):
                events.append(
                    {
                        "type": "quality_assessed",
                        "quality": s1["quality"],
                        "confidence": s1.get("confidence"),
                        "confidence_type": s1.get("confidence_type"),
                    }
                )
            if result.get("ok") and d1.get("domain"):
                events.append(
                    {
                        "type": "domain_brief_created",
                        "domain": d1.get("domain"),
                        "decision_status": d1.get("decision_status"),
                        "confidence": d1.get("confidence"),
                        "evidence_ids": d1.get("evidence_ids", []),
                    }
                )

            payload = {
                "ok": result["ok"],
                "action": "r6_run",
                "domain": domain,
                "question": question,
                "reference_date": reference_date,
                "execution_context": execution_context.to_dict(),
                "blueprint": blueprint,
                "plan": result.get("plan"),
                "results": results,
                "research_synthesis": s1,
                "final_result": result.get("final_result"),
                "final_artifact": result.get("final_artifact"),
                "evidence": result.get("evidence", []),
                "citations": result.get("citations", []),
                "trace": result.get("trace"),
                "events": events,
            }
            if not result["ok"]:
                provider_map = {
                    query["query_id"]: query["provider"] for query in blueprint["queries"]
                }
                provider_map["S1"] = "RESEARCH_SYNTHESIS"
                provider_map["D1"] = "DOMAIN_SYNTHESIS"
                payload["stage"] = "source_or_runtime"
                payload["error"] = _source_failure(events, result.get("error"), provider_map)
            return payload
        except Exception as exc:
            return {
                "ok": False,
                "action": "r6_run",
                "domain": domain,
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
        return {"code": "runtime_failed", "message": str(fallback or "R6 research run failed")}
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
    print("Agent Research Workbench · R6")
    print("Open http://127.0.0.1:8000")
    print("Source Health: BLS + FRED + EIA operational diagnostics")
    print("Research: Question -> Evidence -> S1 Quality Synthesis -> D1 Investment/Policy Brief")
    print("D1 inherits citations/confidence; no new data fetches and no fake scenario probabilities.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
