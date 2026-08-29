import unittest

from context import ExecutionContext
from evidence import EvidenceRecord, EvidenceStore, SYNTHETIC_EVIDENCE_CATALOG
from planner import ResearchPlanner
from scheduler import DAGScheduler
from tools import reset_teaching_tools


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="research-agent",
    task_id="research-test-root",
    trace_id="research-test-trace",
)


class EvidencePipelineTests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_research_planner_requires_evidence_before_synthesis(self):
        plan = ResearchPlanner().plan("synthetic research")
        tasks = plan.task_map()
        self.assertEqual([task.task_id for task in plan.tasks], ["E1", "E2", "S1"])
        self.assertEqual(tasks["E1"].depends_on, [])
        self.assertEqual(tasks["E2"].depends_on, [])
        self.assertEqual(tasks["S1"].depends_on, ["E1", "E2"])

    def test_evidence_store_rejects_unknown_citation(self):
        store = EvidenceStore()
        store.add(SYNTHETIC_EVIDENCE_CATALOG["energy"])
        with self.assertRaises(KeyError):
            store.citations(["E1", "E404"])

    def test_evidence_round_trip_preserves_source_and_confidence(self):
        original = SYNTHETIC_EVIDENCE_CATALOG["energy"]
        restored = EvidenceRecord.from_dict(original.to_dict())
        self.assertEqual(restored, original)
        self.assertEqual(restored.source.uri, "teaching://energy-bulletin")
        self.assertEqual(restored.confidence, 0.92)

    def test_research_scheduler_registers_provenance_and_verified_citations(self):
        events = []
        result = DAGScheduler().run(
            ResearchPlanner().plan("synthetic research"),
            execution_context=CONTEXT,
            on_event=events.append,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual([item["evidence_id"] for item in result["evidence"]], ["E1", "E2"])
        self.assertEqual([item["citation"] for item in result["citations"]], ["[E1]", "[E2]"])
        self.assertEqual(result["final_artifact"]["kind"], "synthesis")
        self.assertEqual(result["final_artifact"]["value"], 0.7)
        self.assertEqual(result["final_artifact"]["confidence"], 0.88)
        self.assertIn("[E1] [E2]", result["final_result"])

        event_types = [event["type"] for event in events]
        first_synthesis_start = next(
            index
            for index, event in enumerate(events)
            if event["type"] == "task_started" and event["task_id"] == "S1"
        )
        registered_before = [
            event for event in events[:first_synthesis_start]
            if event["type"] == "evidence_registered"
        ]
        self.assertEqual([event["evidence"]["evidence_id"] for event in registered_before], ["E1", "E2"])
        self.assertIn("synthesis_verified", event_types)

    def test_synthesis_task_carries_evidence_and_citation_ids_in_plan_state(self):
        result = DAGScheduler().run(
            ResearchPlanner().plan("synthetic research"),
            execution_context=CONTEXT,
        )
        synthesis = next(task for task in result["plan"]["tasks"] if task["task_id"] == "S1")
        self.assertEqual(synthesis["evidence_ids"], ["E1", "E2"])
        self.assertEqual(synthesis["citation_ids"], ["[E1]", "[E2]"])


if __name__ == "__main__":
    unittest.main()
