"""Serve the focused Agent Graph + Live Stream console; keep legacy APIs."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from rate_agent import RateSimulatedCrash, RateStrategyAgent
from rate_checkpoint import RateCheckpointStore
from rate_commands import RateIdempotencyStore
from rate_parallel import RateParallelAgent
from r7_streaming import encode_stream_message
from serve_r12 import R12VisualizerHandler


RATE_AGENT = RateStrategyAgent()
PARALLEL_RATE_AGENT = RateParallelAgent()


class RateStrategyHandler(R12VisualizerHandler):
    version_label = "RATE-CONSOLE-V2-PARALLEL"
    page_title = "Agent Workflow · Graph & Live Stream"

    def do_GET(self):
        if self.path.split("?", 1)[0] not in {"/", "/index.html"}:
            return super().do_GET()
        body = (Path(__file__).parent / "web" / "rate_console.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in {"/api/rates/run-once", "/api/rates/recovery-demo", "/api/rates/idempotency-demo", "/api/rates/stream"}:
            return super().do_POST()
        request_data = self._read_eval_request()
        if request_data is None:
            return
        if self.path == "/api/rates/stream":
            return self._stream_run(request_data)
        if self.path != "/api/rates/run-once":
            if self.path == "/api/rates/recovery-demo":
                return self._run_recovery_demo(request_data)
            if self.path == "/api/rates/idempotency-demo":
                return self._run_idempotency_demo(request_data)
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

    def _run_idempotency_demo(self, request_data):
        """Show that the same state-changing command is applied only once."""
        try:
            run = RATE_AGENT.run_once(
                lookback_days=request_data.get("lookback_days", 60),
                entry_z=request_data.get("entry_z", 1.0),
                holding_days=request_data.get("holding_days", 20),
                dv01_usd_per_bp=request_data.get("dv01_usd_per_bp", 100.0),
                round_trip_cost_bps=request_data.get("round_trip_cost_bps", 1.0),
                start_date=request_data.get("start_date"),
            )
            with tempfile.TemporaryDirectory(prefix="rate-idempotency-demo-") as directory:
                store = RateIdempotencyStore(directory)
                key = f"{run['run_id']}:PAPER-FILL"
                command = {"action": "record_paper_fill", "paper_trade_id": run["simulation"]["completed_trade"]["paper_trade_id"]}
                first = store.execute_once(key, command)
                second = store.execute_once(key, command)
            run["idempotency"] = {
                "demo": True,
                "idempotency_key": key,
                "command": command,
                "boundary": "Command Gateway",
                "attempts": [first["status"], second["status"]],
                "applied_attempts": int(first["applied"]) + int(second["applied"]),
                "ledger_before": 0,
                "ledger_after_first": first["record"]["effect_count"],
                "ledger_after_retry": second["record"]["effect_count"],
                "ledger_event_count": second["record"]["effect_count"],
                "same_command": True,
            }
            return self._send_eval_json(
                200,
                {"ok": True, "action": "rate_strategy_idempotency_demo", "run": run},
            )
        except Exception as exc:
            return self._send_eval_json(
                400,
                {"ok": False, "action": "rate_strategy_idempotency_demo",
                 "error": {"code": exc.__class__.__name__, "message": str(exc)}},
            )

    def _stream_run(self, request_data):
        """Stream each real Rate Agent event as newline-delimited JSON."""
        run_id = f"RATE-RUN-{uuid4().hex[:16]}"
        streamed_events = []
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def send(message_type, **payload):
            self.wfile.write(encode_stream_message(
                message_type, protocol="rate-ndjson-v1", run_id=run_id, **payload
            ))
            self.wfile.flush()

        def observe(event):
            streamed_events.append(event)
            send("event", event=event)

        try:
            parallel = request_data.get("execution_mode", "serial") == "parallel"
            send("start", strategy="2s10s", execution_mode="parallel" if parallel else "serial")
            agent = PARALLEL_RATE_AGENT if parallel else RATE_AGENT
            options = {"demo_scenario": request_data.get("demo_scenario", "live")} if parallel else {}
            run = agent.run_once(
                run_id=run_id,
                lookback_days=request_data.get("lookback_days", 60),
                entry_z=request_data.get("entry_z", 1.0),
                holding_days=request_data.get("holding_days", 20),
                dv01_usd_per_bp=request_data.get("dv01_usd_per_bp", 100.0),
                round_trip_cost_bps=request_data.get("round_trip_cost_bps", 1.0),
                start_date=request_data.get("start_date"),
                event_sink=observe,
                **options,
            )
            send("result", result=run)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:
            try:
                send("error", error={
                    "code": exc.__class__.__name__, "message": str(exc),
                    "task_id": getattr(exc, "task_id", None) or (
                        streamed_events[-1].get("task_id") if streamed_events else None
                    ),
                    "trace": streamed_events,
                    "failures": getattr(exc, "failures", {}),
                })
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), RateStrategyHandler)
    print("Agent Workflow · Graph & Live Stream · RATE-CONSOLE-V2-PARALLEL")
    print(f"Open http://{host}:{port}")
    print("Focused console: real node states, Tool arguments, results and retries")
    print("Lesson: D1 bulk data -> A2 / A10 concurrent branches -> J1 all-success Join -> S1 -> E1")
    print("Default UI mode is an explicitly disclosed snapshot + timing/failure teaching demo")
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
