import json
import unittest

from rate_parallel import ParallelRunError, RateParallelAgent
from rate_rag import (CitationGate, LexicalRateRetriever, RAGChunk,
                      RAGEvidenceInsufficient, teaching_rag_fixture)


class RateRAGContractTests(unittest.TestCase):
    def test_lexical_top_k_is_bounded_ranked_and_does_not_claim_embeddings(self):
        fixture = teaching_rag_fixture("rag_topk")
        result = LexicalRateRetriever(fixture["top_k"]).retrieve(
            fixture["query"], fixture["chunks"]
        )
        self.assertEqual(result["algorithm"], "deterministic_lexical_overlap")
        self.assertEqual([chunk["chunk_id"] for chunk in result["selected"]],
                         ["fred-dgs10-current", "fred-dgs2-current"])
        self.assertEqual(len(result["selected"]), 2)
        self.assertFalse(next(chunk for chunk in result["ranked"]
                              if chunk["chunk_id"] == "event-market-noise")["selected_top_k"])

    def test_every_chunk_has_stable_content_hash_and_citation_id(self):
        chunk = teaching_rag_fixture("rag_topk")["chunks"][0]
        duplicate = RAGChunk(chunk.chunk_id, chunk.source_id, chunk.title, chunk.text,
                             chunk.source_url, chunk.as_of, chunk.series, chunk.tokens)
        self.assertEqual(chunk.content_sha256, duplicate.content_sha256)
        self.assertEqual(chunk.citation_id, duplicate.citation_id)
        self.assertTrue(chunk.citation_id.startswith("CIT-"))

    def test_citation_gate_rejects_superseded_chunk_but_keeps_verified_coverage(self):
        fixture = teaching_rag_fixture("rag_stale")
        retrieval = LexicalRateRetriever(fixture["top_k"]).retrieve(
            fixture["query"], fixture["chunks"]
        )
        gate = CitationGate().validate(retrieval["selected"])
        stale = next(row for row in gate["decisions"] if row["chunk_id"] == "stale-direct-trading")
        self.assertFalse(stale["passed"])
        self.assertIn("source_version_superseded", stale["reasons"])
        self.assertEqual(set(gate["coverage"]), {"DGS2", "DGS10"})
        self.assertEqual(len(gate["accepted"]), 2)

    def test_missing_provenance_causes_evidence_abstention(self):
        fixture = teaching_rag_fixture("rag_insufficient")
        retrieval = LexicalRateRetriever(fixture["top_k"]).retrieve(
            fixture["query"], fixture["chunks"]
        )
        with self.assertRaises(RAGEvidenceInsufficient) as caught:
            CitationGate().validate(retrieval["selected"])
        self.assertEqual(caught.exception.missing_series, ["DGS10"])
        rejected = next(row for row in caught.exception.decisions if row["chunk_id"] == "unknown-dgs10")
        self.assertIn("source_domain_not_allowed", rejected["reasons"])

    def test_invalid_retrieval_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            LexicalRateRetriever(0)
        with self.assertRaises(ValueError):
            LexicalRateRetriever().retrieve("", [])
        with self.assertRaises(ValueError):
            RAGChunk("id", "source", "title", "text", None, "2026-09-01", (), 10)


class RateRAGIntegrationTests(unittest.TestCase):
    def agent(self):
        return RateParallelAgent(sleeper=lambda _: None)

    def test_topk_and_citation_gate_complete_before_context_and_model(self):
        run = self.agent().run_once(demo_scenario="rag_topk")
        events = run["trace"]
        positions = {name: next(event["sequence"] for event in events if event["event"] == name)
                     for name in ("retrieval_query_created", "retrieval_topk_selected",
                                  "citation_gate_completed", "context_pack_created",
                                  "model_request_started")}
        self.assertEqual(list(positions.values()), sorted(positions.values()))
        self.assertEqual(run["lesson"]["topic"], "rag_retrieval")
        self.assertTrue(run["eval"]["passed"])

    def test_stale_retrieval_is_audited_but_never_enters_model_prompt(self):
        run = self.agent().run_once(demo_scenario="rag_stale")
        events = run["trace"]
        self.assertTrue(any(event["event"] == "retrieval_candidate_scored"
                            and event["chunk_id"] == "stale-direct-trading"
                            and event["selected_top_k"] for event in events))
        self.assertTrue(any(event["event"] == "citation_checked"
                            and event["chunk_id"] == "stale-direct-trading"
                            and not event["passed"] for event in events))
        prompt = next(event["prompt"] for event in events if event["event"] == "model_request_started")
        serialized = json.dumps(prompt)
        self.assertNotIn("directly tradeable contracts", serialized)
        self.assertIn("CIT-", serialized)

    def test_incomplete_evidence_stops_before_context_model_and_tools(self):
        with self.assertRaises(ParallelRunError) as caught:
            self.agent().run_once(demo_scenario="rag_insufficient")
        self.assertEqual(caught.exception.code, "RAG_EVIDENCE_INSUFFICIENT")
        events = caught.exception.trace
        self.assertTrue(any(event["event"] == "citation_gate_completed"
                            and event["decision"] == "ABSTAIN" for event in events))
        self.assertFalse(any(event["event"] in {
            "context_collection_started", "model_request_started", "runtime_started",
            "tool_execution_started",
        } for event in events))


if __name__ == "__main__":
    unittest.main()
