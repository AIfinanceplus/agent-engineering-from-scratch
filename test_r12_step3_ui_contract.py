import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class R12Step3UIContractTests(unittest.TestCase):
    def test_server_loads_step3_and_discovery_endpoint(self):
        source = (ROOT / "serve_r12.py").read_text(encoding="utf-8")
        self.assertIn('"r12_step3.js"', source)
        self.assertIn('"/api/r12/discovery"', source)
        self.assertIn("discover_market_candidates", source)
        self.assertIn("candidate similarity NEVER auto-approves", source)

    def test_discovery_ui_replaces_raw_id_as_normal_path_but_keeps_fallback(self):
        source = (ROOT / "web" / "r12_step3.js").read_text(encoding="utf-8")
        self.assertIn("Search Markets Instead of Typing Provider IDs", source)
        self.assertIn("/api/r12/discovery", source)
        self.assertIn("CANDIDATE_ONLY_IDENTITY_UNVERIFIED", source)
        self.assertIn("Candidate Match ≠ Same Event", source)
        self.assertIn("Advanced fallback", source)
        self.assertIn("Load exact contract for review", source)
        self.assertIn("Load pair for settlement review", source)

    def test_loading_candidate_pair_does_not_auto_validate_identity(self):
        source = (ROOT / "web" / "r12_step3.js").read_text(encoding="utf-8")
        self.assertIn("r12Step2State.identity = null", source)
        self.assertIn("r12Step2State.rulesAnalysis = null", source)
        self.assertIn("Settlement identity is still UNVERIFIED", source)
        self.assertNotIn("r12Step2ValidateIdentity()", source)
        self.assertNotIn("r12Step2RunRV()", source)

    def test_step3_css_is_loaded_as_extension(self):
        source = (ROOT / "web" / "r12_step3.js").read_text(encoding="utf-8")
        self.assertIn("r12_step3.css?v=r12-step3-v1", source)


if __name__ == "__main__":
    unittest.main()
