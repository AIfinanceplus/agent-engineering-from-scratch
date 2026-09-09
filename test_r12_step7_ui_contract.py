import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class R12Step7UIContractTests(unittest.TestCase):
    def test_server_loads_step9_after_workspace_router_and_exposes_portfolio_routes(self):
        source = (ROOT / "serve_r12.py").read_text(encoding="utf-8")
        self.assertIn('"r12_step7.js"', source)
        self.assertLess(source.index('"r12_step6.js"'), source.index('"r12_step7.js"'))
        self.assertIn('"/api/r12/paper/portfolio"', source)
        self.assertIn('"/api/r12/paper/preflight-fill"', source)
        self.assertIn("atomic fill preflight", source)

    def test_portfolio_panel_is_composed_before_the_single_trade_ledger(self):
        source = (ROOT / "web" / "r12_step7.js").read_text(encoding="utf-8")
        self.assertIn("r12Step9BasePaperPanel", source)
        self.assertIn("`${r12Step9PortfolioPanel()}${r12Step9BasePaperPanel()}`", source)
        self.assertIn("Multi-trade Portfolio &amp; Exposure Limits", source)
        self.assertIn("ATOMIC_PREFLIGHT", source)
        self.assertIn("NO_AUTO_EXECUTION", source)
        self.assertIn('class="r12-portfolio-details"', source)
        self.assertIn("${violations.length ? 'open' : ''}", source)

    def test_ui_exposes_limits_aggregate_pnl_and_refresh(self):
        source = (ROOT / "web" / "r12_step7.js").read_text(encoding="utf-8")
        for label in (
            "Unsettled trades",
            "Unsettled acquisition cost",
            "Total unmatched leg quantity",
            "Per-provider filled notional",
            "Per-identity acquisition cost",
            "Realized P&amp;L",
        ):
            self.assertIn(label, source)
        self.assertIn("r12-portfolio-refresh", source)
        self.assertIn("/api/r12/paper/portfolio", source)
        self.assertNotIn("place_order", source)


if __name__ == "__main__":
    unittest.main()
