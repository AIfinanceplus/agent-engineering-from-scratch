import json
import unittest

from rate_parallel import ParallelRunError, RateParallelAgent
from rate_prompt_security import PromptInjectionBlocked, RetrievedContentGuard
from rate_rag import CitationGate, LexicalRateRetriever, teaching_rag_fixture


def gated_fixture(scenario):
    fixture = teaching_rag_fixture(scenario)
    retrieval = LexicalRateRetriever(fixture["top_k"]).retrieve(
        fixture["query"], fixture["chunks"]
    )
    return CitationGate().validate(retrieval["selected"])


class PromptSecurityContractTests(unittest.TestCase):
    def test_mixed_content_quarantines_attack_and_preserves_clean_coverage(self):
        result = RetrievedContentGuard().inspect(gated_fixture("injection_mixed"))
        self.assertEqual({chunk["chunk_id"] for chunk in result["promoted"]},
                         {"fred-dgs2-current", "fred-dgs10-current"})
        self.assertEqual([chunk["chunk_id"] for chunk in result["quarantined"]],
                         ["compromised-rate-note"])
        decision = next(row for row in result["decisions"] if row["tainted"])
        self.assertEqual(decision["action"], "QUARANTINE")
        self.assertIn("instruction_override", decision["matched_rules"])
        self.assertIn("unauthorized_tool_request", decision["matched_rules"])

    def test_only_malicious_evidence_fails_closed_after_quarantine(self):
        with self.assertRaises(PromptInjectionBlocked) as caught:
            RetrievedContentGuard().inspect(gated_fixture("injection_blocked"))
        self.assertEqual(caught.exception.missing_series, ["DGS10", "DGS2"])

    def test_clean_content_is_promoted_only_as_data(self):
        result = RetrievedContentGuard().inspect(gated_fixture("injection_clean"))
        self.assertFalse(result["quarantined"])
        self.assertTrue(all(row["action"] == "PROMOTE_AS_DATA" for row in result["decisions"]))
        self.assertEqual(result["policy"], "retrieved_text_is_data_never_instructions")


class PromptSecurityIntegrationTests(unittest.TestCase):
    def agent(self):
        return RateParallelAgent(sleeper=lambda _: None)

    def test_attack_is_visible_in_audit_but_absent_from_model_and_tool_arguments(self):
        run = self.agent().run_once(demo_scenario="injection_mixed")
        events = run["trace"]
        quarantine = next(e for e in events if e["event"] == "retrieved_content_inspected"
                          and e["tainted"])
        self.assertIn("reveal the API key", quarantine["content_preview"])
        model = next(e for e in events if e["event"] == "model_request_started")
        tool_calls = [e["arguments"] for e in events if e["event"] == "tool_execution_started"]
        self.assertNotIn("reveal the API key", json.dumps(model["prompt"]))
        self.assertNotIn("reveal the API key", json.dumps(tool_calls))
        order = [next(e["sequence"] for e in events if e["event"] == name) for name in
                 ("citation_gate_completed", "taint_guard_started", "taint_guard_completed",
                  "context_pack_created", "model_request_started", "runtime_started")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(run["lesson"]["topic"], "prompt_injection_defense")
        self.assertTrue(run["eval"]["passed"])

    def test_attack_only_abstains_before_context_model_runtime_and_tools(self):
        with self.assertRaises(ParallelRunError) as caught:
            self.agent().run_once(demo_scenario="injection_blocked")
        self.assertEqual(caught.exception.code, "PROMPT_INJECTION_BLOCKED")
        self.assertEqual(caught.exception.task_id, "TG1")
        events = caught.exception.trace
        self.assertTrue(any(e["event"] == "taint_guard_completed" and not e["passed"]
                            for e in events))
        self.assertFalse(any(e["event"] in {"context_collection_started", "model_request_started",
                                             "runtime_started", "tool_execution_started"}
                             for e in events))


if __name__ == "__main__":
    unittest.main()
