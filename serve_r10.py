"""R10 preview server: numerical Research Target, market gap, EV lab, embedded Eval Center."""

from http.server import ThreadingHTTPServer
import json

import serve_visualizer as runtime
import serve_r8 as r8
import serve_r9 as r9
from r10_evals import make_r10_eval_suite
from r10_investment import compute_scenario_expected_value
from r10_planner import R10ResearchPlanner
from r10_tooling import register_r10_tools


runtime.R7ResearchPlanner = R10ResearchPlanner
runtime.make_r7_eval_suite = make_r10_eval_suite
register_r10_tools()


class R10VisualizerHandler(r9.R9VisualizerHandler):
    version_label = "R10"
    page_title = "Agent Research Workbench · R10 Numerical Pricing + EV"
    # R10 intentionally does NOT load r8_eval_current.js. Eval is embedded in the
    # completed Research result and the Evaluation Center is a local UI projection.
    extra_scripts = ("r8_ui.js", "r9_ui.js", "r10_ui.js", "r10_step2.js")
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
        if self.path != "/api/r10/ev":
            return super().do_POST()

        request_data = self._read_eval_request()
        if request_data is None:
            return
        run_id = request_data.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "r10_ev",
                    "error": {"code": "run_id_required", "message": "run_id is required"},
                },
            )
            return
        run = r8.RUN_REGISTRY.get(run_id)
        if run is None:
            self._send_eval_json(
                404,
                {
                    "ok": False,
                    "action": "r10_ev",
                    "error": {"code": "run_not_found", "message": "Run Research again before using EV Lab."},
                },
            )
            return
        decision = run.get("investment_decision") or (run.get("results") or {}).get("I1")
        if not isinstance(decision, dict):
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "r10_ev",
                    "run_id": run_id,
                    "error": {"code": "investment_decision_required", "message": "EV Lab is available only for an Investment run with I1."},
                },
            )
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
            {
                "ok": True,
                "action": "r10_ev",
                "run_id": run_id,
                "ev": ev,
            },
        )


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), R10VisualizerHandler)
    print("Agent Research Workbench · R10 Numerical Pricing + EV")
    print("Open http://127.0.0.1:8000")
    print("Investment: S1/D1/F1 -> T1 numerical target; M6 market context; T1/M6 -> I1 numerical gap")
    print("T1: one-step persistence baseline; mechanical and uncalibrated, never a probability or security fair value")
    print("I1 payoff bridge: standardized bp-on-unit-exposure template; actual security P&L still needs sensitivity")
    print("EV Lab: explicit scenario probabilities only; support score is never a probability")
    print("Eval Center: suite is embedded in the completed Research result; clicking Eval performs NO HTTP eval fetch")
    print("Policy: preserves the R8/R9 policy chain and does not run Investment T1/I1")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping R10 visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
