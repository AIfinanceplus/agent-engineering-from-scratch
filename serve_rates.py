"""Serve Rate Strategy V1 inside the full Agent Research Workbench UI."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import os

from rate_agent import RateStrategyAgent
from serve_r12 import R12VisualizerHandler


RATE_AGENT = RateStrategyAgent()


class RateStrategyHandler(R12VisualizerHandler):
    version_label = "RATE-V1"
    page_title = "Agent Research Workbench · Rate Strategy V1"
    extra_scripts = (*R12VisualizerHandler.extra_scripts, "rate_workbench.js")

    def do_POST(self):
        if self.path != "/api/rates/run-once":
            return super().do_POST()
        request_data = self._read_eval_request()
        if request_data is None:
            return
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


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), RateStrategyHandler)
    print("Agent Research Workbench · Rate Strategy V1")
    print(f"Open http://{host}:{port}")
    print("Full Workbench UI retained: Trace / Logic / Evidence / State / Checkpoint / Architecture")
    print("Strategy workspace: D1 public FRED data -> S1 explicit rule -> E1 paper simulation eval")
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
