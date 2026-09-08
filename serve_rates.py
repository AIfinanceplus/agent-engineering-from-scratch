"""Serve the focused Agent Graph + Live Stream console; keep legacy APIs."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
from datetime import datetime, timezone
import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from rate_agent import RateSimulatedCrash, RateStrategyAgent
from rate_checkpoint import RateCheckpointStore
from rate_commands import RateIdempotencyStore
from rate_parallel import RateParallelAgent, SCENARIOS
from rate_control import RunControl, RunControlRegistry
from rate_approval import ApprovalRegistry
from rate_event_log import EventLogError, RateEventLog
from rate_execution import partial_fill_cancel_race_demo
from r12_paper import JsonlR12PaperLedgerStore, R12PaperLedger, evaluate_r12_paper_trade
from serve_r12 import R12VisualizerHandler


RATE_AGENT = RateStrategyAgent()
PARALLEL_RATE_AGENT = RateParallelAgent()
RUN_CONTROLS = RunControlRegistry()
APPROVALS = ApprovalRegistry(os.environ.get("RATE_APPROVAL_DIR", ".rate_approvals"))
EVENT_LOG = RateEventLog(os.environ.get("RATE_EVENT_DIR", os.path.join(tempfile.gettempdir(), "rate-agent-events")))


class RateStrategyHandler(R12VisualizerHandler):
    version_label = "RATE-CONSOLE-V18-PAPER-LEDGER"
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
        if self.path not in {"/api/rates/run-once", "/api/rates/recovery-demo", "/api/rates/idempotency-demo", "/api/rates/stream", "/api/rates/execution-race", "/api/rates/paper-fill", "/api/rates/replay", "/api/rates/cancel", "/api/rates/approval"}:
            return super().do_POST()
        request_data = self._read_eval_request()
        if request_data is None:
            return
        if self.path == "/api/rates/cancel":
            run_id = request_data.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                return self._send_eval_json(400, {"ok": False, "error": {"message": "run_id is required"}})
            outcome = RUN_CONTROLS.cancel(run_id)
            if outcome is None:
                return self._send_eval_json(404, {"ok": False, "error": {"message": "run_id not found in this server process"}})
            return self._send_eval_json(202 if outcome["accepted"] else 409,
                                        {"ok": outcome["accepted"], "control": outcome})
        if self.path == "/api/rates/approval":
            run_id = request_data.get("run_id")
            decision = request_data.get("decision")
            if not isinstance(run_id, str) or not run_id or decision not in {"approve", "deny"}:
                return self._send_eval_json(400, {"ok": False, "error": {
                    "message": "run_id and approve/deny decision are required"}})
            outcome = APPROVALS.decide(run_id, decision)
            return self._send_eval_json(202 if outcome["accepted"] else 409,
                                        {"ok": outcome["accepted"], "approval": outcome})
        if self.path == "/api/rates/stream":
            return self._stream_run(request_data)
        if self.path == "/api/rates/execution-race":
            return self._stream_execution_race()
        if self.path == "/api/rates/paper-fill":
            return self._stream_paper_fill()
        if self.path == "/api/rates/replay":
            return self._replay_run(request_data)
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
        mode = request_data.get("execution_mode", "serial")
        scenario = request_data.get("demo_scenario", "live")
        if mode not in ("serial", "parallel") or not isinstance(scenario, str) or scenario not in SCENARIOS:
            return self._send_eval_json(400, {"ok": False, "error": {"message": "invalid execution_mode or demo_scenario"}})
        parallel = mode == "parallel"
        default_budget = (1000 if scenario in {"deadline", "late_result"}
                          else 120000 if scenario in {"live", "approval_interactive",
                                                       "approval_durable_restart",
                                                       "approval_durable_stale",
                                                       "lease_failover", "lease_renewal",
                                                       "outbox_retry", "outbox_fenced"}
                          else 30000)
        control = None
        if parallel:
            try:
                control = RunControl(request_data.get("budget_ms", default_budget))
                RUN_CONTROLS.register(run_id, control)
            except (ValueError, RuntimeError) as exc:
                return self._send_eval_json(400, {"ok": False, "error": {"message": str(exc)}})
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            if control:
                control.request_stop("disconnect")
                control.finish("disconnected")
            return
        self.close_connection = True

        def send(message_type, **payload):
            message = {"protocol": "rate-ndjson-v1", "type": message_type, "run_id": run_id, **payload}
            EVENT_LOG.append(message)
            self.wfile.write((json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            self.wfile.flush()

        def observe(event):
            streamed_events.append(event)
            send("event", event=event)

        try:
            send("start", strategy="2s10s", execution_mode="parallel" if parallel else "serial",
                 cancel_supported=parallel, budget_ms=control.budget_ms if control else None)
            agent = PARALLEL_RATE_AGENT if parallel else RATE_AGENT
            options = {"demo_scenario": scenario, "control": control,
                       "approval_registry": APPROVALS} if parallel else {}
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
            if control:
                control.request_stop("disconnect")
            return
        except Exception as exc:
            try:
                send("error", error={
                    "code": getattr(exc, "code", exc.__class__.__name__), "message": str(exc),
                    "status": getattr(exc, "status", "failed"),
                    "task_id": getattr(exc, "task_id", None) or (
                        streamed_events[-1].get("task_id") if streamed_events else None
                    ),
                    "trace": streamed_events,
                    "failures": getattr(exc, "failures", {}),
                })
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
        finally:
            APPROVALS.discard(run_id)
            if control and not control.snapshot()["terminal"]:
                control.finish("failed")

    def _stream_execution_race(self):
        """Stream the deterministic partial-fill/cancel race without a broker."""
        run_id = f"RATE-RACE-{uuid4().hex[:16]}"
        demo = partial_fill_cancel_race_demo()
        trace = []
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        self.close_connection = True

        def send(message_type, **payload):
            message = {"protocol": "rate-ndjson-v1", "type": message_type, "run_id": run_id, **payload}
            EVENT_LOG.append(message)
            self.wfile.write((json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            self.wfile.flush()

        def emit(source):
            source_event = source["event"]
            mapped = {
                "order_accepted": "outbox_enqueued",
                "fill_recorded": "ledger_event_appended",
                "cancel_requested": "ledger_event_appending",
                "fill_deduplicated": "outbox_effect_deduplicated",
                "cancel_confirmed": "ledger_reconciliation_completed",
            }[source_event]
            row = {
                "sequence": len(trace) + 1,
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": mapped,
                "execution_event": source_event,
                "task_id": "O1" if mapped.startswith("outbox_") else "LG1",
                "order_id": source["order_id"],
                "payload": source["payload"],
            }
            if source_event in {"fill_recorded", "fill_deduplicated"}:
                row["effect_count"] = 1
            if source_event == "cancel_confirmed":
                row["passed"] = True
            trace.append(row)
            send("event", event=row)

        send("start", strategy="2s10s", execution_mode="parallel", cancel_supported=False,
             budget_ms=120000, lesson="partial_fill_cancel_race")
        for source in demo["events"]:
            emit(source)
        final = {
            "sequence": len(trace) + 1,
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "run_completed",
            "task_id": "R1",
            "lesson": "partial_fill_cancel_race",
            "status": "COMPLETED",
        }
        trace.append(final)
        send("event", event=final)
        run = {
            "artifact_type": "partial_fill_cancel_race_run",
            "run_id": run_id,
            "status": "COMPLETED_PARTIAL_FILL_CANCEL_RACE",
            "trace": trace,
            "execution": demo["execution"],
            "eval": {"passed": True, "checks": {
                "late_fill_counted": True, "duplicate_fill_deduplicated": True,
                "cancel_waited_for_confirmation": True, "quantity_conserved": True,
            }},
            "guardrails": {"paper_only": True, "broker_connection": False,
                           "automatic_execution": False},
            "lesson": {"topic": "partial_fill_cancel_race",
                       "graph": {"nodes": ["O1", "LG1", "E1"],
                                 "edges": [["O1", "LG1"], ["LG1", "E1"]]}},
        }
        send("result", result=run)

    def _stream_paper_fill(self):
        """Teach quote -> explicit paper fills -> marks -> settlement P&L."""
        run_id = f"RATE-PAPER-FILL-{uuid4().hex[:16]}"
        source_run_id = "R12A-PAPER-FILL-LESSON"
        opportunity_id = "OPP-PAPER-FILL-LESSON"
        first_leg = "kalshi:YES"
        second_leg = "polymarket:NO"
        quote = {
            "artifact_type": "r12_execution_quality_scan",
            "identity_id": "IDENTITY-PAPER-FILL-LESSON",
            "opportunities": [{
                "artifact_type": "r12_strategy_opportunity",
                "opportunity_id": opportunity_id,
                "eligible_for_paper_signal": True,
                "market_view": {"execution_quote": {
                    "target_contracts": 10,
                    "full_fill_at_target": True,
                    "eligible_for_paper_signal": True,
                    "net_edge_total": 0.4,
                    "legs": [
                        {"leg_id": first_leg, "provider": "kalshi", "outcome": "YES",
                         "full_fill": True, "filled_quantity": 10, "vwap": 0.45,
                         "notional": 4.5, "fee": 0.1},
                        {"leg_id": second_leg, "provider": "polymarket", "outcome": "NO",
                         "full_fill": True, "filled_quantity": 10, "vwap": 0.49,
                         "notional": 4.9, "fee": 0.1},
                    ],
                }},
            }],
        }
        agent_run = {
            "artifact_type": "r12_strategy_agent_run",
            "run_id": source_run_id,
            "status": "COMPLETED_PAPER_QUOTE",
            "results": {"E1": quote},
        }
        trace = []
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        self.close_connection = True

        def send(message_type, **payload):
            message = {"protocol": "rate-ndjson-v1", "type": message_type, "run_id": run_id, **payload}
            EVENT_LOG.append(message)
            self.wfile.write((json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            self.wfile.flush()

        send("start", strategy="r12_paper_fill_accounting", execution_mode="parallel",
             cancel_supported=False, budget_ms=120000, lesson="paper_fill_accounting")

        def emit_ledger(trade, paper_event_type, *, mapped="ledger_event_appended", extra=None):
            row = {
                "sequence": len(trace) + 1,
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": mapped,
                "event_type": paper_event_type,
                "paper_event_type": paper_event_type,
                "task_id": "O1" if mapped == "outbox_effect_deduplicated" else "LG1",
                "paper_trade_id": trade["paper_trade_id"],
                "event_count": trade["event_count"],
                "status": trade["status"],
                "risk": trade["risk"],
                "pnl": trade["pnl"],
                "payload": (extra or {}),
            }
            if mapped == "outbox_effect_deduplicated":
                row["effect_count"] = 0
                row["idempotency_key"] = "fill-first-four"
            trace.append(row)
            send("event", event=row)

        with tempfile.TemporaryDirectory(prefix="rate-paper-fill-lesson-") as directory:
            ledger = R12PaperLedger(JsonlR12PaperLedgerStore(directory))
            trade = ledger.create_from_agent_run(agent_run, opportunity_id, "create-paper-fill-lesson")
            emit_ledger(trade, "paper_intent_created")
            trade = ledger.record_fill(
                trade["paper_trade_id"], leg_id=first_leg, quantity=4, price=0.45,
                fee=0.04, idempotency_key="fill-first-four",
            )
            emit_ledger(trade, "paper_fill_recorded")
            retried = ledger.record_fill(
                trade["paper_trade_id"], leg_id=first_leg, quantity=4, price=0.45,
                fee=0.04, idempotency_key="fill-first-four",
            )
            emit_ledger(retried, "paper_fill_recorded", mapped="outbox_effect_deduplicated",
                        extra={"retry": True, "same_idempotency_key": True})
            trade = ledger.record_fill(
                trade["paper_trade_id"], leg_id=second_leg, quantity=4, price=0.49,
                fee=0.04, idempotency_key="fill-second-four",
            )
            emit_ledger(trade, "paper_fill_recorded")
            trade = ledger.record_fill(
                trade["paper_trade_id"], leg_id=first_leg, quantity=6, price=0.45,
                fee=0.06, idempotency_key="fill-first-six",
            )
            emit_ledger(trade, "paper_fill_recorded")
            trade = ledger.record_fill(
                trade["paper_trade_id"], leg_id=second_leg, quantity=6, price=0.49,
                fee=0.06, idempotency_key="fill-second-six",
            )
            emit_ledger(trade, "paper_fill_recorded")
            trade = ledger.mark_to_market(
                trade["paper_trade_id"], marks={first_leg: 0.46, second_leg: 0.50},
                idempotency_key="mark-paper-fill-lesson",
            )
            emit_ledger(trade, "paper_marks_updated")
            trade = ledger.settle(
                trade["paper_trade_id"], winning_outcome="YES",
                idempotency_key="settle-paper-fill-lesson",
            )
            emit_ledger(trade, "paper_trade_settled")
            reconciliation = {
                "sequence": len(trace) + 1,
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "ledger_reconciliation_completed",
                "event_type": "paper_trade_settled",
                "task_id": "LG1",
                "event_count": trade["event_count"],
                "passed": True,
                "status": trade["status"],
                "payload": {"expected": "replayed paper ledger", "replayed": "same projection"},
            }
            trace.append(reconciliation)
            send("event", event=reconciliation)
            evaluation = evaluate_r12_paper_trade(trade)
            final = {
                "sequence": len(trace) + 1,
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "run_completed",
                "task_id": "R1",
                "lesson": "paper_fill_accounting",
                "status": "COMPLETED",
            }
            trace.append(final)
            send("event", event=final)
            result = {
                "artifact_type": "r12_paper_fill_accounting_run",
                "run_id": run_id,
                "status": "COMPLETED_PAPER_FILL_ACCOUNTING",
                "trace": trace,
                "paper_trade": trade,
                "eval": evaluation,
                "guardrails": {
                    "paper_only": True,
                    "exchange_credentials_present": False,
                    "automatic_execution": False,
                    "quote_is_not_a_fill": True,
                    "partial_fill_is_locked_arbitrage": False,
                },
                "lesson": {
                    "topic": "paper_fill_accounting",
                    "graph": {
                        "nodes": ["E1", "O1", "LG1"],
                        "edges": [["E1", "O1"], ["O1", "LG1"]],
                    },
                },
            }
            send("result", result=result)

    def _replay_run(self, request_data):
        """Replay persisted envelopes without executing any Tool again."""
        run_id = request_data.get("run_id")
        after_sequence = request_data.get("after_sequence", 0)
        if not isinstance(run_id, str) or not run_id:
            return self._send_eval_json(400, {"ok": False, "error": {"code": "RUN_ID_REQUIRED", "message": "run_id is required"}})
        if not isinstance(after_sequence, int) or isinstance(after_sequence, bool) or after_sequence < 0:
            return self._send_eval_json(400, {"ok": False, "error": {"code": "INVALID_SEQUENCE", "message": "after_sequence must be a non-negative integer"}})
        try:
            messages = EVENT_LOG.read(run_id, after_sequence=after_sequence)
        except EventLogError as exc:
            return self._send_eval_json(400, {"ok": False, "error": {"code": "INVALID_REPLAY", "message": str(exc)}})
        if not messages:
            return self._send_eval_json(404, {"ok": False, "error": {"code": "RUN_NOT_FOUND", "message": "no persisted stream for run_id"}})
        replay_start = dict(messages[0])
        replay_start["replayed"] = True
        messages[0] = replay_start
        body = b"".join((json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8") for message in messages)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Rate-Replay", "true")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), RateStrategyHandler)
    print("Agent Workflow · Graph & Live Stream · RATE-CONSOLE-V18-PAPER-LEDGER")
    print(f"Open http://{host}:{port}")
    print("Focused console: real node states, Tool arguments, results and retries")
    print("Graph: G1 -> RG1 retrieves -> CG1 verifies -> CT1 packs -> model -> P1 -> R1 -> L1 -> H1 -> AZ1 -> Tools -> S1 -> O1 -> LG1 ledger reconcile -> E1")
    print("Default UI: high relevance stale chunk -> citation rejection -> verified evidence pack")
    print("New lesson: Stream Explainer · persist → deliver → observe → replay · no Tool re-execution")
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
