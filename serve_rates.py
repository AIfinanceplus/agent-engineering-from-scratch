"""Serve Rate Strategy V1 inside the full Agent Research Workbench UI."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import os
import tempfile

from rate_agent import RateSimulatedCrash, RateStrategyAgent
from rate_checkpoint import RateCheckpointStore
from serve_r12 import R12VisualizerHandler


RATE_AGENT = RateStrategyAgent()


class RateStrategyHandler(R12VisualizerHandler):
    version_label = "RATE-V1-STATE"
    page_title = "Agent Research Workbench · Rate Strategy V1 · State / Resume"
    extra_scripts = (*R12VisualizerHandler.extra_scripts, "rate_workbench.js")

    def do_POST(self):
        if self.path not in {"/api/rates/run-once", "/api/rates/recovery-demo"}:
            return super().do_POST()
        request_data = self._read_eval_request()
        if request_data is None:
            return
        if self.path != "/api/rates/run-once":
            if self.path == "/api/rates/recovery-demo":
                return self._run_recovery_demo(request_data)
        try:
            run = RATE_AGENT.run_once(
                lookback_days=request_data.get("lookback_days", 60),
                entry_z=request_data.get("entry_z", 1.0),
                holding_days=request_data.get("holding_days", 20),
                dv01_usd_per_bp=request_data.get("dv01_usd_per_bp", 100.0),
                round_trip_cost_bps=request_data.get("round_trip_cost_bps", 1.0),
                start_date=request_data.get("start_date"),
            )
        except Exception as exc:
            unavailable = isinstance(exc, (ConnectionError, TimeoutError)) or bool(
                getattr(exc, "transient", False)
            )
            return self._send_eval_json(
                503 if unavailable else 400,
                {
                    "ok": False,
                    "action": "rate_strategy_run_once",
                    "error": {
                        "code": "DATA_SOURCE_UNAVAILABLE" if unavailable else exc.__class__.__name__,
                        "message": str(exc),
                        "retryable": unavailable,
                        "task_id": getattr(exc, "task_id", None),
                        "attempts": getattr(exc, "attempts", None),
                        "trace": getattr(exc, "trace", []),
                    },
                },
            )
        return self._send_eval_json(
            200,
            {"ok": True, "action": "rate_strategy_run_once", "run": run},
        )

    def _run_recovery_demo(self, request_data):
        """Run D1, persist its checkpoint, crash, then resume from S1."""
        if request_data is None:
            return
        options = {
            "lookback_days": request_data.get("lookback_days", 60),
            "entry_z": request_data.get("entry_z", 1.0),
            "holding_days": request_data.get("holding_days", 20),
            "dv01_usd_per_bp": request_data.get("dv01_usd_per_bp", 100.0),
            "round_trip_cost_bps": request_data.get("round_trip_cost_bps", 1.0),
            "start_date": request_data.get("start_date"),
        }
        with tempfile.TemporaryDirectory(prefix="rate-checkpoint-demo-") as directory:
            store = RateCheckpointStore(directory)
            try:
                RATE_AGENT.run_once(
                    **options, checkpoint_store=store, crash_after_task="D1"
                )
            except RateSimulatedCrash as crash:
                run = RATE_AGENT.run_once(
                    **options,
                    run_id=crash.run_id,
                    checkpoint_store=store,
                    resume=True,
                )
                run["recovery"].update(
                    {
                        "demo": True,
                        "crashed_after": crash.task_id,
                        "crash_trace_length": len(crash.trace),
                        "checkpoint_path": store.checkpoint_path(crash.run_id),
                    }
                )
                return self._send_eval_json(
                    200,
                    {"ok": True, "action": "rate_strategy_recovery_demo", "run": run},
                )
            except Exception as exc:
                return self._send_eval_json(
                    400,
                    {"ok": False, "action": "rate_strategy_recovery_demo",
                     "error": {"code": exc.__class__.__name__, "message": str(exc)}},
                )
        return self._send_eval_json(
            500,
            {"ok": False, "action": "rate_strategy_recovery_demo",
             "error": {"code": "RECOVERY_DEMO_DID_NOT_CRASH", "message": "demo did not reach crash boundary"}},
        )


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), RateStrategyHandler)
    print("Agent Research Workbench · Rate Strategy V1 · State / Resume")
    print(f"Open http://{host}:{port}")
    print("Full Workbench UI retained: Trace / Logic / Evidence / State / Checkpoint / Architecture")
    print("Strategy workspace: D1 resilient public rates -> S1 explicit rule -> E1 paper simulation eval")
    print("D1 ladder: FRED live -> U.S. Treasury live -> disclosed bundled snapshot")
    print("No broker connection or automatic execution")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
