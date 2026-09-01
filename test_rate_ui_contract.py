import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class RateUIContractTests(unittest.TestCase):
    def test_rate_overlay_retains_workbench_components_and_replaces_only_strategy(self):
        base = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        source = (ROOT / "web" / "rate_workbench.js").read_text(encoding="utf-8")
        for label in ("Trace", "Logic", "Evidence", "State", "Checkpoint", "Architecture"):
            self.assertIn(label, base)
        self.assertIn("Agent 运行过程", base)
        self.assertIn("Run One Simulation", source)
        self.assertIn("Live Agent Stream", source)
        self.assertIn("/api/rates/stream", source)
        self.assertIn("getReader()", source)
        self.assertIn("application/x-ndjson", source)
        self.assertIn("/api/rates/recovery-demo", source)
        self.assertIn("/api/rates/idempotency-demo", source)
        self.assertIn("Idempotent Write", source)
        self.assertIn("idempotency", source)
        self.assertIn("Run Crash + Resume Demo", source)
        self.assertIn("rate-recovery-launch", source)
        self.assertIn("STATE TRANSITION TIMELINE", source)
        self.assertIn("rate-state-timeline", source)
        self.assertIn("rate-transition-list", source)
        self.assertIn("Planner", source)
        self.assertIn("Runtime", source)
        self.assertIn("Tool Registry", source)
        self.assertIn("D1 Rate Data Tool", source)
        self.assertIn("FRED live → Treasury live → disclosed snapshot", source)
        self.assertIn("S1 Strategy Tool", source)
        self.assertIn("E1 Eval", source)
        self.assertIn("利率策略", source)

    def test_client_calls_only_rate_api_and_exposes_every_learning_view(self):
        source = (ROOT / "web" / "rate_workbench.js").read_text(encoding="utf-8")
        self.assertIn("/api/rates/run-once", source)
        self.assertIn("failureTrace", source)
        self.assertIn("tool_retry_scheduled", source)
        self.assertIn("data_source_fallback_selected", source)
        self.assertIn("Offline snapshot", source)
        self.assertIn("RETRYABLE", source)
        self.assertNotIn("place_order", source)
        for renderer in (
            "rateRenderTrace", "rateRenderLogic", "rateRenderEvidence",
            "rateRenderState", "rateRenderCheckpoint", "rateRenderArchitecture",
        ):
            self.assertIn(renderer, source)
        self.assertIn("none_deterministic_v1", source)
        self.assertIn("CHECKPOINT · RECOVERY DEMO", source)
        self.assertIn("Crash + Resume Demo", source)
        self.assertIn("rateRestoreOriginalPanels", source)
        self.assertIn("DURABLE", source)
        self.assertIn("checkpoint_saved", source)
        self.assertIn("process_restarted", source)
        self.assertIn("task_skipped_from_checkpoint", source)
        self.assertIn("appState.selectedDetailTab = (recoveryDemo || idempotencyDemo) ? 'state' : 'trace'", source)
        self.assertIn("child.hidden = child !== overlay", source)
        self.assertNotIn("panel.innerHTML =", source)

    def test_server_extends_r12_workbench_and_loads_rate_overlay_last(self):
        source = (ROOT / "serve_rates.py").read_text(encoding="utf-8")
        self.assertIn("class RateStrategyHandler(R12VisualizerHandler)", source)
        self.assertIn('(*R12VisualizerHandler.extra_scripts, "rate_workbench.js")', source)
        self.assertIn('"/api/rates/run-once"', source)
        self.assertIn("Full Workbench UI retained", source)


if __name__ == "__main__":
    unittest.main()
