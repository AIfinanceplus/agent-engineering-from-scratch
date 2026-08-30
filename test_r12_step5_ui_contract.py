import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class R12Step5UIContractTests(unittest.TestCase):
    def test_server_loads_step7_ui_and_all_paper_routes(self):
        source = (ROOT / "serve_r12.py").read_text(encoding="utf-8")
        self.assertIn('"r12_step5.js"', source)
        for route in ("create", "status", "fill", "mark", "cancel", "expire", "settle"):
            self.assertIn(f'"/api/r12/paper/{route}"', source)
        self.assertIn("explicit paper fills -> append-only replay", source)

    def test_ui_requires_explicit_fills_and_exposes_risk_and_pnl(self):
        source = (ROOT / "web" / "r12_step5.js").read_text(encoding="utf-8")
        self.assertIn("APPEND-ONLY PAPER EXECUTION LEDGER", source)
        self.assertIn("Create Paper Intent", source)
        self.assertIn("Record Fill", source)
        self.assertIn("Leg risk", source)
        self.assertIn("MTM P&amp;L", source)
        self.assertIn("Realized P&amp;L", source)
        self.assertIn("idempotency_key", source)
        self.assertIn("pendingCommands", source)
        self.assertIn("aria-busy", source)
        self.assertIn("panel.querySelectorAll('button')", source)
        self.assertIn("NO_EXCHANGE_CONNECTION", source)
        self.assertNotIn("place_order", source)

    def test_step7_panel_is_inserted_after_agent_panel_without_reordering_old_ui(self):
        source = (ROOT / "web" / "r12_step5.js").read_text(encoding="utf-8")
        self.assertIn("r12Step7BaseRunPanel", source)
        self.assertIn("`${r12Step7BaseRunPanel()}${r12Step7PaperPanel()}`", source)
        self.assertIn("r12_step5.css?v=r12-step7-v1", source)


if __name__ == "__main__":
    unittest.main()
