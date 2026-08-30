import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class R12Step6UIContractTests(unittest.TestCase):
    def test_server_loads_step8_router_after_all_existing_r12_scripts(self):
        source = (ROOT / "serve_r12.py").read_text(encoding="utf-8")
        self.assertIn('"r12_step6.js"', source)
        self.assertLess(source.index('"r12_step5.js"'), source.index('"r12_step6.js"'))
        self.assertIn("Agent Run / Manual Lab / Strategy Roadmap operator workspaces", source)
        self.assertIn("default event search entry + content-height Strategy workspace", source)

    def test_strategy_center_has_three_task_oriented_workspaces(self):
        source = (ROOT / "web" / "r12_step6.js").read_text(encoding="utf-8")
        self.assertIn("workspace:'agent'", source)
        self.assertIn("Event Search & Agent", source)
        self.assertIn("Manual Lab", source)
        self.assertIn("Strategy Roadmap", source)
        self.assertIn('role="tablist"', source)
        self.assertIn('role="tabpanel"', source)
        self.assertIn('aria-controls="r12-workspace-panel"', source)
        self.assertIn('aria-labelledby="r12-workspace-tab-${r12Step8State.workspace}"', source)
        self.assertIn("['ArrowLeft', 'ArrowRight', 'Home', 'End']", source)
        self.assertIn("data-r12-workspace", source)

    def test_r12_opens_on_event_search_and_collapses_the_old_fixed_grid(self):
        step8 = (ROOT / "web" / "r12_step6.js").read_text(encoding="utf-8")
        base = (ROOT / "web" / "r12_ui.js").read_text(encoding="utf-8")
        css = (ROOT / "web" / "r12.css").read_text(encoding="utf-8")
        self.assertTrue(step8.rstrip().endswith("openR12StrategyCenter();"))
        workspace = step8[step8.index("function r12Step8AgentWorkspace"):step8.index("function r12Step8StructuralLab")]
        self.assertLess(workspace.index("r12Step3DiscoveryPanel()"), workspace.index("r12Step8AgentSetupPanel()"))
        self.assertIn("事件市场", base)
        self.assertIn("r12-strategy-workspace-mode", base)
        self.assertIn(".workspace.r12-strategy-workspace-mode{display:block;overflow:auto}", css)

    def test_agent_workspace_is_linear_and_keeps_h1_next_to_manual_checks(self):
        source = (ROOT / "web" / "r12_step6.js").read_text(encoding="utf-8")
        start = source.index("function r12Step8AgentWorkspace")
        end = source.index("function r12Step8StructuralLab")
        workspace = source[start:end]
        ordered = [
            "r12Step3DiscoveryPanel()",
            "r12Step8AgentSetupPanel()",
            "r12Step7BaseRunPanel()",
            "r12Step8ReviewPanel()",
            "r12Step8ResultsPanel()",
            "r12Step7PaperPanel()",
        ]
        positions = [workspace.index(token) for token in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('id="r12-agent-approve-inline"', source)
        self.assertIn('data-r12-agent-action="approve"', source)
        self.assertIn("Manual checks ${r12Step6CheckedCount()}/6", source)

    def test_manual_lab_owns_step_by_step_tools_and_roadmap_is_separate(self):
        source = (ROOT / "web" / "r12_step6.js").read_text(encoding="utf-8")
        self.assertIn("r12Step3BaseInspector()", source)
        self.assertIn("r12Step8StructuralLab()", source)
        self.assertIn("r12RenderRegistry()", source)
        css = (ROOT / "web" / "r12_step6.css").read_text(encoding="utf-8")
        self.assertIn("#r12-analyze-rules", css)
        self.assertIn("#r12-validate-identity", css)
        self.assertIn("display:none", css)

    def test_agent_setup_draft_survives_rerenders_and_tab_switches(self):
        source = (ROOT / "web" / "r12_step6.js").read_text(encoding="utf-8")
        self.assertIn("setupDraft", source)
        self.assertIn("R12_STEP8_SETUP_FIELDS", source)
        self.assertIn("r12Step8BaseHydrateAgent", source)
        self.assertIn("estimated_total_cost_per_basket", source)


if __name__ == "__main__":
    unittest.main()
