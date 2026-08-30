"""R10 preview server: numerical pricing, instrument P&L bridge, EV, and embedded Eval Center."""

from http.server import ThreadingHTTPServer

import serve_visualizer as runtime
import serve_r8 as r8
import serve_r9 as r9
from r10_evals import make_r10_eval_suite
from r10_instrument import compute_instrument_risk_ev
from r10_investment import compute_scenario_expected_value
from r10_planner import R10ResearchPlanner
from r10_tooling import register_r10_tools


runtime.R7ResearchPlanner = R10ResearchPlanner
runtime.make_r7_eval_suite = make_r10_eval_suite
register_r10_tools()


class R10VisualizerHandler(r9.R9VisualizerHandler):
    version_label = "R10"
    page_title = "Agent Research Workbench · R10 Numerical Pricing + Instrument Risk EV"
    # Eval is embedded in the completed Research result. Step 2/3 are separate
    # extensions so the accepted workbench can be inspected incrementally.
    extra_scripts = ("r8_ui.js", "r9_ui.js", "r10_ui.js", "r10_step2.js", "r10_step3.js")
    eval_factory = staticmethod(make_r10_eval_suite)

    def execute_research(self, *args, **kwargs) -> dict:
        result = super().execute_research(*args, **kwargs)
        results = result.get("results") or {}
        result["numerical_research_target"] = results.get("T1")
        result["investment_decision"] = results.get("I1")

        blueprint = result.get("blueprint") or {}
        domain = result.get("domain")
        if blueprint and domain in {"investment", "policy"}:
            try:
                suite = make_r10_eval_suite(blueprint, result, domain)
                result["embedded_eval_suite"] = suite
                result["eval_transport"] = "embedded_in_run_v3"
                result["eval_error"] = None
            except Exception as exc:
                # Evaluation failure must not destroy an otherwise valid research run.
                result["embedded_eval_suite"] = None
                result["eval_transport"] = "embedded_in_run_v3"
                result["eval_error"] = {
                    "code": exc.__class__.__name__,
                    "message": str(exc),
                }
        r8.remember_run(result)
        return result

    def do_POST(self):
        if self.path == "/api/r10/ev":
            return self._handle_ev()
        if self.path == "/api/r10/instrument-risk":
            return self._handle_instrument_risk()
        return super().do_POST()

    def _read_run_and_decision(self, request_data: dict, *, action: str):
        run_id = request_data.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": action,
                    "error": {"code": "run_id_required", "message": "run_id is required"},
                },
            )
            return None, None, None
        run = r8.RUN_REGISTRY.get(run_id)
        if run is None:
            self._send_eval_json(
                404,
                {
                    "ok": False,
                    "action": action,
                    "run_id": run_id,
                    "error": {"code": "run_not_found", "message": "Run Research again before using this Investment tool."},
                },
            )
            return None, None, None
        decision = run.get("investment_decision") or (run.get("results") or {}).get("I1")
        if not isinstance(decision, dict):
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": action,
                    "run_id": run_id,
                    "error": {
                        "code": "investment_decision_required",
                        "message": "This tool requires an Investment run with I1.",
                    },
                },
            )
            return None, None, None
        return run_id, run, decision

    def _handle_ev(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        run_id, run, decision = self._read_run_and_decision(request_data, action="r10_ev")
        if run is None:
            return
        try:
            ev = compute_scenario_expected_value(
                decision,
                request_data.get("scenarios"),
                transaction_cost=request_data.get("transaction_cost", 0.0),
                payoff_unit=request_data.get("payoff_unit", "user_defined_payoff_unit"),
            )
        except Exception as exc:
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "r10_ev",
                    "run_id": run_id,
                    "error": {"code": exc.__class__.__name__, "message": str(exc)},
                },
            )
            return

        run["r10_ev"] = ev
        r8.remember_run(run)
        self._send_eval_json(
            200,
            {"ok": True, "action": "r10_ev", "run_id": run_id, "ev": ev},
        )

    def _handle_instrument_risk(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        run_id, run, decision = self._read_run_and_decision(
            request_data,
            action="r10_instrument_risk",
        )
        if run is None:
            return
        try:
            artifact = compute_instrument_risk_ev(
                decision,
                request_data.get("instrument_name"),
                request_data.get("position_direction"),
                request_data.get("sensitivity_per_bp"),
                request_data.get("sensitivity_source"),
                request_data.get("pnl_unit"),
                request_data.get("scenario_probabilities"),
                transaction_cost=request_data.get("transaction_cost", 0.0),
                carry=request_data.get("carry", 0.0),
                risk_budget=request_data.get("risk_budget"),
                loss_limit=request_data.get("loss_limit"),
            )
        except Exception as exc:
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "r10_instrument_risk",
                    "run_id": run_id,
                    "error": {"code": exc.__class__.__name__, "message": str(exc)},
                },
            )
            return

        run["r10_instrument_risk_ev"] = artifact
        r8.remember_run(run)
        self._send_eval_json(
            200,
            {
                "ok": True,
                "action": "r10_instrument_risk",
                "run_id": run_id,
                "instrument_risk_ev": artifact,
            },
        )


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), R10VisualizerHandler)
    print("Agent Research Workbench · R10 Numerical Pricing + Instrument Risk EV")
    print("Open http://127.0.0.1:8000")
    print("Investment Research: S1/D1/F1 -> T1; M6 -> I1 numerical research-market gap")
    print("T1: one-step persistence baseline; mechanical and uncalibrated")
    print("I1: standardized market-move bp scenarios; not security P&L")
    print("I2 Instrument Bridge: explicit sensitivity -> scenario P&L -> net EV -> worst loss -> risk review gate")
    print("Risk efficiency = net EV / worst scenario loss; explicitly NOT Sharpe ratio")
    print("No instrument sensitivity is guessed from a ticker/name and no position is auto-executed")
    print("Eval Center: embedded in the completed Research result; opening Eval performs NO HTTP eval fetch")
    print("Policy: preserves the policy chain and does not run Investment T1/I1/I2")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping R10 visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
