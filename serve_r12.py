"""R12 preview server: strategy Opportunity Engine + verified cross-market RV."""

from http.server import ThreadingHTTPServer

import r12_event_sources as event_sources
import r12_identity as identity_engine
from r12_strategy import scan_structural_opportunities, strategy_registry_snapshot
from r12_tooling import register_r12_tools
from serve_r11 import R11VisualizerHandler


register_r12_tools()


class R12VisualizerHandler(R11VisualizerHandler):
    version_label = "R12"
    page_title = "Agent Research Workbench · R12 Strategy Opportunity Engine"
    extra_scripts = (*R11VisualizerHandler.extra_scripts, "r12_ui.js", "r12_step2.js")

    def do_POST(self):
        if self.path == "/api/r12/registry":
            return self._handle_registry()
        if self.path == "/api/r12/structural-scan":
            return self._handle_structural_scan()
        if self.path == "/api/r12/market-contract":
            return self._handle_market_contract()
        if self.path == "/api/r12/identity":
            return self._handle_identity()
        if self.path == "/api/r12/cross-market-rv":
            return self._handle_cross_market_rv()
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
            return self._r12_error("r12_structural_scan", exc)
        self._send_eval_json(
            200,
            {"ok": True, "action": "r12_structural_scan", "scan": scan},
        )

    def _handle_market_contract(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        provider = request_data.get("provider")
        identifier = request_data.get("identifier")
        try:
            if not isinstance(provider, str):
                raise ValueError("provider must be kalshi or polymarket")
            if provider.strip().lower() == "kalshi":
                contract = event_sources.fetch_kalshi_market_contract(identifier)
            elif provider.strip().lower() == "polymarket":
                contract = event_sources.fetch_polymarket_market_contract(identifier)
            else:
                raise ValueError("provider must be kalshi or polymarket")
        except Exception as exc:
            return self._r12_error("r12_market_contract", exc)
        self._send_eval_json(
            200,
            {
                "ok": True,
                "action": "r12_market_contract",
                "provider": provider.strip().lower(),
                "contract": contract,
            },
        )

    def _handle_identity(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            identity = identity_engine.validate_event_identity(
                request_data.get("kalshi_contract"),
                request_data.get("polymarket_contract"),
                attestation=request_data.get("attestation"),
            )
        except Exception as exc:
            return self._r12_error("r12_event_identity", exc)
        self._send_eval_json(
            200,
            {"ok": True, "action": "r12_event_identity", "identity": identity},
        )

    def _handle_cross_market_rv(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            scan = identity_engine.compare_cross_market_locked_rv(
                request_data.get("identity"),
                request_data.get("kalshi_contract"),
                request_data.get("polymarket_contract"),
                estimated_total_cost_per_basket=request_data.get("estimated_total_cost_per_basket", 0.0),
            )
        except Exception as exc:
            return self._r12_error("r12_cross_market_rv", exc)
        self._send_eval_json(
            200,
            {"ok": True, "action": "r12_cross_market_rv", "scan": scan},
        )

    def _r12_error(self, action: str, exc: Exception):
        self._send_eval_json(
            400,
            {
                "ok": False,
                "action": action,
                "error": {"code": exc.__class__.__name__, "message": str(exc)},
            },
        )


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8000), R12VisualizerHandler)
    print("Agent Research Workbench · R12 Strategy Opportunity Engine")
    print("Open http://127.0.0.1:8000")
    print("R11 remains intact: research -> mispricing -> instrument EV -> constrained sizing")
    print("R12 Step 1: structural constraints -> unified StrategyOpportunity")
    print("R12 Step 2: exact Kalshi ticker / Polymarket market ID -> normalized market contracts")
    print("Identity gate: title similarity NEVER auto-approves same-event settlement compatibility")
    print("Cross-market RV: only verified same-event YES+NO complement baskets at executable asks")
    print("No order credentials or order placement; top-of-book depth/fill risk is not modeled yet")
    print("All strategy output is PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION")
    print("Next: broader event discovery + settlement parser, then FOMC/CPI calibrated probability RV")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping R12 visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
