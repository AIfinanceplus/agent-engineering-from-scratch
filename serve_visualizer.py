"""Serve the active R7 forecasting + scenario tracking workbench.

R7 preserves source health, dynamic research decomposition, Evidence quality, and
R6 domain synthesis. It adds a falsifiable forecast layer plus UI-visible durable
research checkpoints:
Evidence -> S1 -> D1 -> F1 Forecast Pack -> later check/settlement.

Research checkpoint snapshots survive process death, but orchestration-level
restore/resume is intentionally not wired yet. The UI labels that distinction.
"""

from datetime import date, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

from context import ExecutionContext
from observability import TraceRecorder
from r4_source_health import run_source_health
from r7_checkpoint import JsonResearchCheckpointStore, ResearchCheckpointRecorder
from r7_evals import make_r7_eval_suite
from r7_forecast import JsonForecastStore, evaluate_forecast_pack
from r7_planner import R7ResearchPlanner
from r7_tooling import register_r7_tools
from scheduler import DAGScheduler


ROOT_DIR = Path(__file__).parent
WEB_DIR = ROOT_DIR / "web"
FORECAST_STORE = JsonForecastStore(ROOT_DIR / ".forecasts")
CHECKPOINT_STORE = JsonResearchCheckpointStore(ROOT_DIR / ".research_checkpoints")
register_r7_tools()

CONTEXT_PRESETS = {
    "general": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="macro-research-agent",
        task_id="r7-research-root",
        trace_id="r7-research-trace",
    ),
    "read_only": ExecutionContext(
        tenant_id="demo-tenant",
        user_id="user-123",
        agent_id="read-only-agent",
        task_id="r7-read-only-root",
        trace_id="r7-read-only-trace",
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

        action = request_data.get("action", "r7_run")
        if action == "source_health":
            self._source_health(request_data)
            return
        if action == "r7_packs":
            self._forecast_packs()
            return
        if action == "r7_checkpoints":
            self._research_checkpoints(request_data)
            return

        context_preset = request_data.get("context_preset", "general")
        if context_preset not in CONTEXT_PRESETS:
            self.send_json(400, {"ok": False, "error": "Unknown context preset"})
            return
        execution_context = CONTEXT_PRESETS[context_preset]

        if action == "r7_check":
            self._check_forecast(request_data, execution_context)
            return

        domain = request_data.get("domain", "investment")
        if domain not in {"investment", "policy"}:
            self.send_json(400, {"ok": False, "error": "domain must be investment or policy"})
            return
        question = request_data.get(
            "goal",
            "Assess current inflation pressure using headline CPI, core CPI, market inflation expectations, and gasoline prices.",
        )

        # Compatibility aliases keep cached R6/R5 pages functional while R7 is active.
        if action in {"r7_run", "r6_run", "r3_run"}:
            self.send_json(
                200,
                self.execute_research(question, domain, execution_context, save_forecast=True),
            )
            return

        if action in {"r7_evals", "r6_evals", "r3_evals"}:
            result = self.execute_research(
                question,
                domain,
                execution_context,
                save_forecast=False,
            )
            blueprint = result.get("blueprint") or {}
            suite = make_r7_eval_suite(blueprint, result, domain) if blueprint else {
                "passed": 0,
                "total": 1,
                "pass_rate": 0.0,
                "cases": [],
                "error": "No blueprint was produced, so R7 evals could not run.",
            }
            self.send_json(
                200,
                {
                    "ok": result.get("ok", False),
                    "action": "r7_evals",
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

    def _forecast_packs(self) -> None:
        rows = []
        for pack_id in FORECAST_STORE.list_ids():
            pack = FORECAST_STORE.load(pack_id)
            if not pack:
                continue
            rows.append(
                {
                    "pack_id": pack_id,
                    "created_at": pack.get("created_at"),
                    "last_checked_at": pack.get("last_checked_at"),
                    "domain": pack.get("domain"),
                    "question": pack.get("question"),
                    "scenario": (pack.get("scenario_tracker") or {}).get("current_state"),
                    "scoreboard": pack.get("scoreboard") or {},
                }
            )
        rows.sort(key=lambda item: (item.get("created_at") or "", item.get("pack_id") or ""), reverse=True)
        self.send_json(200, {"ok": True, "action": "r7_packs", "packs": rows})

    def _research_checkpoints(self, request_data: dict) -> None:
        run_id = request_data.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            self.send_json(
                200,
                {
                    "ok": False,
                    "action": "r7_checkpoints",
                    "error": {"code": "run_id_required", "message": "run_id is required"},
                },
            )
            return
        try:
            checkpoints = CHECKPOINT_STORE.list(run_id)
        except Exception as exc:
            self.send_json(
                200,
                {
                    "ok": False,
                    "action": "r7_checkpoints",
                    "error": {"code": exc.__class__.__name__, "message": str(exc)},
                },
            )
            return
        self.send_json(
            200,
            {
                "ok": True,
                "action": "r7_checkpoints",
                "run_id": run_id,
                "checkpoints": checkpoints,
                "latest_checkpoint": checkpoints[-1] if checkpoints else None,
            },
        )

    def _check_forecast(
        self,
        request_data: dict,
        execution_context: ExecutionContext,
    ) -> None:
        pack_id = request_data.get("pack_id")
        try:
            old_pack = FORECAST_STORE.load(pack_id)
        except Exception as exc:
            self.send_json(
                200,
                {
                    "ok": False,
                    "action": "r7_check",
                    "error": {"code": exc.__class__.__name__, "message": str(exc)},
                },
            )
            return
        if old_pack is None:
            self.send_json(
                200,
                {
                    "ok": False,
                    "action": "r7_check",
                    "error": {"code": "forecast_pack_not_found", "message": f"No saved forecast pack: {pack_id}"},
                },
            )
            return

        result = self.execute_research(
            old_pack.get("question", ""),
            old_pack.get("domain", "investment"),
            execution_context,
            save_forecast=False,
        )
        if not result.get("ok"):
            self.send_json(
                200,
                {
                    "ok": False,
                    "action": "r7_check",
                    "pack_id": pack_id,
                    "research_result": result,
                    "error": result.get("error") or {"code": "research_refresh_failed", "message": "Could not refresh Evidence."},
                },
            )
            return

        try:
            updated = evaluate_forecast_pack(
                old_pack,
                result.get("research_synthesis") or {},
                date.today().isoformat(),
            )
            FORECAST_STORE.save(updated)
        except Exception as exc:
            self.send_json(
                200,
                {
                    "ok": False,
                    "action": "r7_check",
                    "pack_id": pack_id,
                    "error": {"code": exc.__class__.__name__, "message": str(exc)},
                },
            )
            return

        self.send_json(
            200,
            {
                "ok": True,
                "action": "r7_check",
                "pack_id": pack_id,
                "forecast_pack": updated,
                "research_result": result,
            },
        )

    def execute_research(
        self,
        question: str,
        domain: str,
        execution_context: ExecutionContext,
        *,
        save_forecast: bool,
    ) -> dict:
        reference_date = date.today().isoformat()
        run_id = f"RUN-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S-%f')}"
        events = [
            {"type": "research_question_received", "question": question, "domain": domain}
        ]

        try:
            blueprint_obj, plan = R7ResearchPlanner().build(
                question,
                domain=domain,
                reference_date=reference_date,
            )
            blueprint = blueprint_obj.to_dict()
        except Exception as exc:
            return {
                "ok": False,
                "action": "r7_run",
                "run_id": run_id,
                "domain": domain,
                "stage": "decomposition_or_query_compile",
                "reference_date": reference_date,
                "error": {"code": exc.__class__.__name__, "message": str(exc)},
                "events": events,
                "checkpoints": [],
                "latest_checkpoint": None,
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
                "detail": "Domain lens changes D1 only; source Evidence selection remains question-driven.",
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
                "action": "r7_run",
                "run_id": run_id,
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
                "checkpoints": [],
                "latest_checkpoint": None,
            }

        checkpoint_recorder = ResearchCheckpointRecorder(
            run_id=run_id,
            execution_context=execution_context,
            store=CHECKPOINT_STORE,
        )

        def record_event(event: dict) -> None:
            events.append(event)
            checkpoint_recorder.observe(event)

        try:
            trace = TraceRecorder(execution_context.trace_id)
            result = DAGScheduler().run(
                plan,
                execution_context=execution_context,
                on_event=record_event,
                trace_recorder=trace,
            )
            results = result.get("results", {})
            s1 = results.get("S1") or {}
            d1 = results.get("D1") or {}
            f1 = results.get("F1") or result.get("final_artifact") or {}

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
            if result.get("ok") and f1.get("artifact_type") == "forecast_pack":
                events.append(
                    {
                        "type": "forecast_pack_created",
                        "pack_id": f1.get("pack_id"),
                        "scenario": (f1.get("scenario_tracker") or {}).get("current_state"),
                        "scoreboard": f1.get("scoreboard") or {},
                        "forecasts": f1.get("forecasts") or [],
                    }
                )
                if save_forecast:
                    path = FORECAST_STORE.save(f1)
                    events.append(
                        {
                            "type": "forecast_pack_saved",
                            "pack_id": f1.get("pack_id"),
                            "path": str(path.relative_to(ROOT_DIR)),
                        }
                    )

            checkpoints = checkpoint_recorder.checkpoints()
            payload = {
                "ok": result["ok"],
                "action": "r7_run",
                "run_id": run_id,
                "domain": domain,
                "question": question,
                "reference_date": reference_date,
                "execution_context": execution_context.to_dict(),
                "blueprint": blueprint,
                "plan": result.get("plan"),
                "results": results,
                "research_synthesis": s1,
                "domain_brief": d1,
                "forecast_pack": f1,
                "final_result": result.get("final_result"),
                "final_artifact": result.get("final_artifact"),
                "evidence": result.get("evidence", []),
                "citations": result.get("citations", []),
                "trace": result.get("trace"),
                "events": events,
                "checkpoints": checkpoints,
                "latest_checkpoint": checkpoints[-1] if checkpoints else None,
            }
            if not result["ok"]:
                provider_map = {
                    query["query_id"]: query["provider"] for query in blueprint["queries"]
                }
                provider_map.update(
                    {
                        "S1": "RESEARCH_SYNTHESIS",
                        "D1": "DOMAIN_SYNTHESIS",
                        "F1": "FORECAST_SYNTHESIS",
                    }
                )
                payload["stage"] = "source_or_runtime"
                payload["error"] = _source_failure(events, result.get("error"), provider_map)
            return payload
        except Exception as exc:
            checkpoints = checkpoint_recorder.checkpoints()
            return {
                "ok": False,
                "action": "r7_run",
                "run_id": run_id,
                "domain": domain,
                "stage": "unhandled",
                "reference_date": reference_date,
                "blueprint": blueprint,
                "error": {"code": exc.__class__.__name__, "message": str(exc)},
                "events": events,
                "checkpoints": checkpoints,
                "latest_checkpoint": checkpoints[-1] if checkpoints else None,
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
        return {"code": "runtime_failed", "message": str(fallback or "R7 research run failed")}
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
    print("Agent Research Workbench · R7 / UI V3")
    print("Open http://127.0.0.1:8000")
    print("Research: Question -> Evidence -> S1 -> D1 -> F1 Forecast Pack")
    print("Checkpoint: durable research snapshots -> inspectable; orchestration restore not wired yet")
    print("Tracking: saved forecast pack -> fresh S1 -> pending/invalidation/resolution -> scenario revision")
    print("Forecast scores are historical directional hit rates, not forecast probabilities.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
