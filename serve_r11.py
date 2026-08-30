"""R11 preview server: constrained position sizing on top of the accepted R10 stack."""

from http.server import ThreadingHTTPServer

import serve_r8 as r8
from r11_portfolio import compute_position_size
from r11_tooling import register_r11_tools
from serve_r10 import R10VisualizerHandler


register_r11_tools()


class R11VisualizerHandler(R10VisualizerHandler):
    version_label = "R11"
    page_title = "Agent Research Workbench · R11 Position Sizing + Portfolio Risk"
    extra_scripts = (*R10VisualizerHandler.extra_scripts, "r11_ui.js")

    def do_POST(self):
        if self.path == "/api/r11/size":
            return self._handle_position_size()
        return super().do_POST()

    def _handle_position_size(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        run_id = request_data.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "r11_position_size",
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
                    "action": "r11_position_size",
                    "run_id": run_id,
                    "error": {"code": "run_not_found", "message": "Run Research and I2 again before sizing."},
                },
            )
            return

        i2 = run.get("r10_instrument_risk_ev")
        if not isinstance(i2, dict):
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "r11_position_size",
                    "run_id": run_id,
                    "error": {
                        "code": "instrument_risk_required",
                        "message": "R11 sizing requires a completed R10 I2 Instrument Bridge artifact.",
                    },
                },
            )
            return

        try:
            artifact = compute_position_size(
                i2,
                request_data.get("portfolio_value"),
                request_data.get("portfolio_value_unit"),
                request_data.get("portfolio_risk_budget"),
                request_data.get("portfolio_current_risk_used"),
                request_data.get("max_position_nav_fraction"),
                request_data.get("capital_required_per_reference_position"),
                request_data.get("capital_source"),
                max_reference_scale=request_data.get("max_reference_scale"),
            )
        except Exception as exc:
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "r11_position_size",
                    "run_id": run_id,
                    "error": {"code": exc.__class__.__name__, "message": str(exc)},
                },
            )
            return

        run["r11_position_size"] = artifact
        r8.remember_run(run)
        self._send_eval_json(
            200,
            {
                "ok": True,
                "action": "r11_position_size",
                "run_id": run_id,
                "position_size": artifact,
            },
        )


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), R11VisualizerHandler)
    print("Agent Research Workbench · R11 Position Sizing + Portfolio Risk")
    print("Open http://127.0.0.1:8000")
    print("R10 remains intact: Research -> T1 -> I1 -> I2 instrument risk EV")
    print("R11 P1: I2 -> explicit portfolio/capital constraints -> max admissible scale")
    print("Sizing method: constraint intersection, NOT Kelly / optimal portfolio / VaR")
    print("Portfolio risk: conservative additive worst-scenario budget; no diversification credit")
    print("P1 is review-only and never authorizes execution")
    print("Policy mode keeps P1 N/A")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping R11 visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
