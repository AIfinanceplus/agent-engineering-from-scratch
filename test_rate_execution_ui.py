import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class PartialFillConsoleContractTests(unittest.TestCase):
    def test_partial_fill_race_is_exposed_end_to_end(self):
        html = (ROOT / "web" / "rate_console.html").read_text(encoding="utf-8")
        client = (ROOT / "web" / "rate_console.js").read_text(encoding="utf-8")
        server = (ROOT / "serve_rates.py").read_text(encoding="utf-8")
        self.assertIn('value="execution_race"', html)
        self.assertIn('value="paper_fill_accounting"', html)
        self.assertIn('value="paper_portfolio_risk"', html)
        self.assertIn('value="model_live"', html)
        self.assertIn('value="intent_live"', html)
        self.assertIn('name="model_api_key"', html)
        self.assertIn('id="role-grid"', html)
        self.assertIn('三位 Agent 协作室', html)
        self.assertIn('data-journey="risk-verify"', html)
        self.assertIn('沟通格式', html)
        self.assertIn('id="model-inspector-title"', html)
        self.assertIn('data-flow="information"', html)
        self.assertIn('data-flow="decision"', html)
        self.assertIn('data-flow="risk"', html)
        self.assertIn('id="engineering-details"', html)
        self.assertIn('id="lesson-archive"', html)
        self.assertIn('id="archive-scenario"', html)
        self.assertIn('id="key-session-status"', html)
        self.assertIn('Model Evals', html)
        self.assertIn('Agent Memory', html)
        self.assertIn('Multi-Agent Handoff', html)
        for scenario in ('eval_golden_pass', 'eval_regression_fail', 'memory_redaction_pass',
                         'memory_privacy_block', 'handoff_contract_pass', 'handoff_contract_reject'):
            self.assertIn(f'value="{scenario}"', html)
        self.assertIn("/api/rates/execution-race", client)
        self.assertIn("/api/rates/paper-fill", client)
        self.assertIn("/api/rates/paper-portfolio", client)
        self.assertIn("/api/rates/execution-race", server)
        self.assertIn("/api/rates/paper-fill", server)
        self.assertIn("/api/rates/paper-portfolio", server)
        self.assertIn("partial_fill_cancel_race", server)
        self.assertIn("paper_fill_accounting", server)
        self.assertIn("paper_portfolio_risk", server)
        self.assertIn('send("start", strategy="r12_paper_fill_accounting"', server)
        self.assertIn('send("start", strategy="r12_paper_portfolio_risk"', server)
        self.assertIn("max_abs_net_parallel_dv01_usd_per_bp", server)
        self.assertIn("2s10s_treasury_curve_paper_simulation_only", server)
        self.assertIn("portfolio_fill_blocked", client + server)
        self.assertIn("intent_live", client + (ROOT / "rate_parallel.py").read_text(encoding="utf-8"))
        self.assertIn("delete config.model_api_key", client)
        self.assertIn("sessionStorage.setItem(MODEL_KEY_SESSION", client)
        self.assertIn("sessionStorage.removeItem(MODEL_KEY_SESSION", client)
        self.assertIn("enteredModelApiKey || readSessionKey()", client)
        self.assertIn("selectArchivedScenario", client)
        self.assertIn("/api/rates/advanced-lesson", client)
        self.assertIn("updateLessonUI", client)
        self.assertIn("handoffForEvent", client)
        self.assertIn("updateModelInspector", client)
        self.assertIn("updateHandoffJourney", client)
        self.assertIn("role.constraints", client)
        self.assertIn("event.sender_role === role.id", client)
        self.assertIn("value.startsWith('handoff_')", client)
        self.assertIn('"model_api_key": model_api_key', server)
        self.assertIn('row["passed"] = True', server)
        self.assertIn("fill_deduplicated", client + server)
        self.assertIn("FILLED ", client)
        self.assertIn("CANCELED ", client)
        self.assertIn("REALIZED P&L", client)


if __name__ == "__main__":
    unittest.main()
