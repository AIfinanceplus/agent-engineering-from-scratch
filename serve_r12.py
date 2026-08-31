"""R12 preview server: discovery, identity-gated RV, and depth-aware paper quotes."""

from http.server import ThreadingHTTPServer
from pathlib import Path

import r12_discovery as discovery_engine
import r12_event_sources as event_sources
import r12_execution as execution_engine
import r12_identity as identity_engine
import r12_paper as paper_engine
import r12_portfolio as portfolio_engine
import r12_rules as rules_engine
from r12_agent import JsonR12StrategyRunStore, R12StrategyAgent, evaluate_r12_strategy_agent_run
from r12_registry import current_strategy_registry_snapshot
from r12_strategy import scan_structural_opportunities
from r12_tooling import register_r12_tools
from serve_r11 import R11VisualizerHandler


register_r12_tools()
R12_AGENT_STORE = JsonR12StrategyRunStore(Path(__file__).parent / ".r12_agent_runs")
R12_STRATEGY_AGENT = R12StrategyAgent(R12_AGENT_STORE)
R12_PAPER_STORE = paper_engine.JsonlR12PaperLedgerStore(Path(__file__).parent / ".r12_paper_ledger")
R12_PAPER_LEDGER = paper_engine.R12PaperLedger(R12_PAPER_STORE)
R12_PAPER_PORTFOLIO = portfolio_engine.R12PaperPortfolio(R12_PAPER_LEDGER)


class R12VisualizerHandler(R11VisualizerHandler):
    version_label = "R12"
    page_title = "Agent Research Workbench · R12 Strategy Opportunity Engine"
    extra_scripts = (
        *R11VisualizerHandler.extra_scripts,
        "r12_ui.js",
        "r12_step2.js",
        "r12_step3.js",
        "r12_step4.js",
        "r12_step5.js",
        "r12_step6.js",
        "r12_step7.js",
    )

    def do_POST(self):
        if self.path == "/api/r12/registry":
            return self._handle_registry()
        if self.path == "/api/r12/structural-scan":
            return self._handle_structural_scan()
        if self.path == "/api/r12/discovery":
            return self._handle_discovery()
        if self.path == "/api/r12/market-contract":
            return self._handle_market_contract()
        if self.path == "/api/r12/identity":
            return self._handle_identity()
        if self.path == "/api/r12/rules-analysis":
            return self._handle_rules_analysis()
        if self.path == "/api/r12/cross-market-rv":
            return self._handle_cross_market_rv()
        if self.path == "/api/r12/execution-quote":
            return self._handle_execution_quote()
        if self.path == "/api/r12/agent/start":
            return self._handle_agent_start()
        if self.path == "/api/r12/agent/status":
            return self._handle_agent_status()
        if self.path == "/api/r12/agent/approve":
            return self._handle_agent_approve()
        if self.path == "/api/r12/agent/resume":
            return self._handle_agent_resume()
        if self.path == "/api/r12/paper/create":
            return self._handle_paper_create()
        if self.path == "/api/r12/paper/status":
            return self._handle_paper_status()
        if self.path == "/api/r12/paper/portfolio":
            return self._handle_paper_portfolio()
        if self.path == "/api/r12/paper/preflight-fill":
            return self._handle_paper_preflight_fill()
        if self.path == "/api/r12/paper/fill":
            return self._handle_paper_fill()
        if self.path == "/api/r12/paper/mark":
            return self._handle_paper_mark()
        if self.path == "/api/r12/paper/cancel":
            return self._handle_paper_cancel()
        if self.path == "/api/r12/paper/expire":
            return self._handle_paper_expire()
        if self.path == "/api/r12/paper/settle":
            return self._handle_paper_settle()
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
                "registry": current_strategy_registry_snapshot(),
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

    def _handle_discovery(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            discovery = discovery_engine.discover_market_candidates(request_data.get("query"))
        except Exception as exc:
            return self._r12_error("r12_market_discovery", exc)
        self._send_eval_json(
            200,
            {"ok": True, "action": "r12_market_discovery", "discovery": discovery},
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
                rules_analysis=request_data.get("rules_analysis"),
                attestation=request_data.get("attestation"),
            )
        except Exception as exc:
            return self._r12_error("r12_event_identity", exc)
        self._send_eval_json(
            200,
            {"ok": True, "action": "r12_event_identity", "identity": identity},
        )

    def _handle_rules_analysis(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            analysis = rules_engine.analyze_settlement_rules(
                request_data.get("kalshi_contract"),
                request_data.get("polymarket_contract"),
            )
        except Exception as exc:
            return self._r12_error("r12_settlement_rules_analysis", exc)
        self._send_eval_json(
            200,
            {"ok": True, "action": "r12_settlement_rules_analysis", "analysis": analysis},
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

    def _handle_execution_quote(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            quote = execution_engine.quote_cross_market_execution(
                request_data.get("identity"),
                request_data.get("kalshi_contract"),
                request_data.get("polymarket_contract"),
                target_contracts=request_data.get("target_contracts"),
                fee_model=request_data.get("fee_model"),
                latency_buffer_bps=request_data.get("latency_buffer_bps", 0.0),
            )
        except Exception as exc:
            return self._r12_error("r12_execution_quote", exc)
        self._send_eval_json(
            200,
            {"ok": True, "action": "r12_execution_quote", "quote": quote},
        )

    def _handle_agent_start(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            run = R12_STRATEGY_AGENT.start_exact_pair(
                kalshi_identifier=request_data.get("kalshi_identifier"),
                polymarket_identifier=request_data.get("polymarket_identifier"),
                target_contracts=request_data.get("target_contracts"),
                fee_model=request_data.get("fee_model"),
                latency_buffer_bps=request_data.get("latency_buffer_bps", 0.0),
                estimated_total_cost_per_basket=request_data.get("estimated_total_cost_per_basket", 0.0),
            )
        except Exception as exc:
            return self._r12_error("r12_strategy_agent_start", exc)
        self._send_agent_run("r12_strategy_agent_start", run)

    def _handle_agent_status(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            run = R12_STRATEGY_AGENT.get(request_data.get("run_id"))
        except Exception as exc:
            return self._r12_error("r12_strategy_agent_status", exc)
        self._send_agent_run("r12_strategy_agent_status", run)

    def _handle_agent_approve(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            run = R12_STRATEGY_AGENT.approve_and_resume(
                request_data.get("run_id"),
                request_data.get("attestation"),
            )
        except Exception as exc:
            return self._r12_error("r12_strategy_agent_approve", exc)
        self._send_agent_run("r12_strategy_agent_approve", run)

    def _handle_agent_resume(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            run = R12_STRATEGY_AGENT.resume(request_data.get("run_id"))
        except Exception as exc:
            return self._r12_error("r12_strategy_agent_resume", exc)
        self._send_agent_run("r12_strategy_agent_resume", run)

    def _handle_paper_create(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            run = R12_STRATEGY_AGENT.get(request_data.get("run_id"))
            trade = R12_PAPER_PORTFOLIO.create_from_agent_run(
                run,
                request_data.get("opportunity_id"),
                request_data.get("idempotency_key"),
            )
        except Exception as exc:
            return self._r12_error("r12_paper_create", exc)
        self._send_paper_trade("r12_paper_create", trade)

    def _handle_paper_status(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            trade = R12_PAPER_LEDGER.get(request_data.get("paper_trade_id"))
        except Exception as exc:
            return self._r12_error("r12_paper_status", exc)
        self._send_paper_trade("r12_paper_status", trade)

    def _handle_paper_portfolio(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            portfolio = R12_PAPER_PORTFOLIO.status()
        except Exception as exc:
            return self._r12_error("r12_paper_portfolio", exc)
        self._send_eval_json(
            200,
            {
                "ok": True,
                "action": "r12_paper_portfolio",
                "portfolio": portfolio,
                "eval": portfolio_engine.evaluate_r12_paper_portfolio(portfolio),
            },
        )

    def _handle_paper_preflight_fill(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            preflight = R12_PAPER_PORTFOLIO.preflight_fill(
                request_data.get("paper_trade_id"),
                leg_id=request_data.get("leg_id"),
                quantity=request_data.get("quantity"),
                price=request_data.get("price"),
                fee=request_data.get("fee", 0.0),
            )
        except Exception as exc:
            return self._r12_error("r12_paper_preflight_fill", exc)
        self._send_eval_json(200, {"ok": True, "action": "r12_paper_preflight_fill", "preflight": preflight})

    def _handle_paper_fill(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            trade = R12_PAPER_PORTFOLIO.record_fill(
                request_data.get("paper_trade_id"),
                leg_id=request_data.get("leg_id"),
                quantity=request_data.get("quantity"),
                price=request_data.get("price"),
                fee=request_data.get("fee", 0.0),
                idempotency_key=request_data.get("idempotency_key"),
            )
        except Exception as exc:
            return self._r12_error("r12_paper_fill", exc)
        self._send_paper_trade("r12_paper_fill", trade)

    def _handle_paper_mark(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            trade = R12_PAPER_LEDGER.mark_to_market(
                request_data.get("paper_trade_id"),
                marks=request_data.get("marks"),
                idempotency_key=request_data.get("idempotency_key"),
            )
        except Exception as exc:
            return self._r12_error("r12_paper_mark", exc)
        self._send_paper_trade("r12_paper_mark", trade)

    def _handle_paper_cancel(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            trade = R12_PAPER_LEDGER.cancel(
                request_data.get("paper_trade_id"),
                reason=request_data.get("reason"),
                idempotency_key=request_data.get("idempotency_key"),
            )
        except Exception as exc:
            return self._r12_error("r12_paper_cancel", exc)
        self._send_paper_trade("r12_paper_cancel", trade)

    def _handle_paper_expire(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            trade = R12_PAPER_LEDGER.expire(
                request_data.get("paper_trade_id"),
                reason=request_data.get("reason"),
                idempotency_key=request_data.get("idempotency_key"),
            )
        except Exception as exc:
            return self._r12_error("r12_paper_expire", exc)
        self._send_paper_trade("r12_paper_expire", trade)

    def _handle_paper_settle(self):
        request_data = self._read_eval_request()
        if request_data is None:
            return
        try:
            trade = R12_PAPER_LEDGER.settle(
                request_data.get("paper_trade_id"),
                winning_outcome=request_data.get("winning_outcome"),
                idempotency_key=request_data.get("idempotency_key"),
            )
        except Exception as exc:
            return self._r12_error("r12_paper_settle", exc)
        self._send_paper_trade("r12_paper_settle", trade)

    def _send_agent_run(self, action: str, run: dict):
        self._send_eval_json(
            200,
            {
                "ok": True,
                "action": action,
                "run": run,
                "eval": evaluate_r12_strategy_agent_run(run),
            },
        )

    def _send_paper_trade(self, action: str, trade: dict):
        portfolio = R12_PAPER_PORTFOLIO.status()
        self._send_eval_json(
            200,
            {
                "ok": True,
                "action": action,
                "trade": trade,
                "eval": paper_engine.evaluate_r12_paper_trade(trade),
                "portfolio": portfolio,
                "portfolio_eval": portfolio_engine.evaluate_r12_paper_portfolio(portfolio),
            },
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
    print("R12 Step 3: free-text discovery -> candidate pairs -> exact-contract review")
    print("Discovery candidate similarity NEVER auto-approves same-event settlement compatibility")
    print("Kalshi discovery: bounded OPEN event listing + local lexical ranking")
    print("Polymarket discovery: public-search + bounded event expansion")
    print("Identity gate: title similarity NEVER auto-approves same-event settlement compatibility")
    print("Identity gate: explicit rules review remains mandatory before cross-market RV")
    print("Step 4: public order-book depth + explicit fees + target fill + latency buffer")
    print("Step 5: fingerprint-bound deterministic rules analysis -> explicit human identity review")
    print("Step 6: Tool DAG -> durable pause -> human approval -> resumable paper quote")
    print("Step 7: explicit paper fills -> append-only replay -> leg risk -> MTM / settlement P&L")
    print("Step 8: Agent Run / Manual Lab / Strategy Roadmap operator workspaces")
    print("Step 8 fix: default event search entry + content-height Strategy workspace")
    print("Step 9: replayed paper portfolio -> atomic fill preflight -> multi-trade exposure limits")
    print("No order credentials, wallet, authenticated portfolio API, or order placement")
    print("All strategy output is PAPER_SIGNAL_ONLY_NO_AUTO_EXECUTION")
    print("Next: portfolio stress scenarios + durable per-strategy policy configuration")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping R12 visualizer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
