"""R12 preview server: strategy Opportunity Contract + structural arbitrage scanner."""

from http.server import ThreadingHTTPServer

from r12_strategy import scan_structural_opportunities, strategy_registry_snapshot
from r12_tooling import register_r12_tools
from serve_r11 import R11VisualizerHandler


register_r12_tools()


class R12VisualizerHandler(R11VisualizerHandler):
    version_label = "R12"
    page_title = "Agent Research Workbench · R12 Strategy Opportunity Engine"
    extra_scripts = (*R11VisualizerHandler.extra_scripts, "r12_ui.js")

    def do_POST(self):
        if self.path == "/api/r12/registry":
            return self._handle_registry()
        if self.path == "/api/r12/structural-scan":
            return self._handle_structural_scan()
        return super().do_POST()

    def _handle_registry(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        self._send_eval_json(
            200,
            {
                "ok": True,
                "action": "r12_strategy_registry",
                "registry": strategy_registry_snapshot(),
            },
        )

    def _handle_structural_scan(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            scan = scan_structural_opportunities(request_data.get("snapshot"))
        except Exception as exc:
            self._send_eval_json(
                400,
                {
                    "ok": False,
                    "action": "r12_structural_scan",
                    "error": {"code": exc.__class__.__name__, "message": str(exc)},
                },
            )
            return
        self._send_eval_json(
            200,
            {
                "ok": True,
                "action": "r12_structural_scan",
                "scan": scan,
            },
        )


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), R12VisualizerHandler)
    print("Agent Research Workbench · R12 Strategy Opportunity Engine")
    print("Open http://127.0.0.1:8000")
    print("R11 remains intact: research -> mispricing -> instrument EV -> constrained sizing")
    print("R12 Step 1: supplied market snapshot -> structural constraints -> StrategyOpportunity")
    print("Structural checks: binary complement, threshold monotonicity, exhaustive partition sum")
    print("No live prediction-market adapter yet; no shortability, settlement, liquidity, or execution is assumed")
    print("All strategy output is PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION")
    print("Next: event identity / settlement adapters, then FOMC + CPI calibrated probability RV")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping R12 visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
