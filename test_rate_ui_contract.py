import unittest
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


class RateUIContractTests(unittest.TestCase):
    def test_console_event_reducer_runtime_contracts(self):
        result = subprocess.run(["node", "--test", "test_rate_console.cjs"], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_console_has_one_live_run_control_and_no_legacy_scripts(self):
        html = (ROOT / "web" / "rate_console.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('id="run-button"'), 1)
        self.assertIn('id="graph-nodes"', html)
        self.assertIn('id="event-list"', html)
        self.assertNotIn('data-detail-tab', html)
        self.assertNotIn('r12_', html)
        self.assertNotIn('rate_workbench', html)
        self.assertIn('Least Privilege &amp; Capability Tokens', html)
        self.assertIn('value="capability_wrong_tool"', html)
        self.assertIn('value="capability_valid"', html)
        self.assertIn('value="capability_expired"', html)
        self.assertIn('value="injection_mixed"', html)
        self.assertIn('value="injection_blocked"', html)
        self.assertIn('value="injection_clean"', html)
        self.assertIn('value="rag_stale"', html)
        self.assertIn('value="rag_topk"', html)
        self.assertIn('value="rag_insufficient"', html)
        self.assertIn('value="context_compression"', html)
        self.assertIn('value="context_relevant"', html)
        self.assertIn('value="context_conflict"', html)
        self.assertIn('知道 Tool ≠ 有权调用 Tool', html)

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
        self.assertIn("Agent Graph", source)
        self.assertIn("rate-agent-graph", source)
        self.assertIn("rate-stream-hud", source)
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

    def test_server_retains_legacy_apis_but_serves_focused_console(self):
        source = (ROOT / "serve_rates.py").read_text(encoding="utf-8")
        self.assertIn("class RateStrategyHandler(R12VisualizerHandler)", source)
        self.assertIn('"rate_console.html"', source)
        self.assertIn('"/api/rates/run-once"', source)
        self.assertIn("Graph & Live Stream", source)


if __name__ == "__main__":
    unittest.main()
