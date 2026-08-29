import tempfile
import unittest

from context import ExecutionContext
from r7_checkpoint import JsonResearchCheckpointStore, ResearchCheckpointRecorder


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-checkpoint",
    agent_id="macro-research-agent",
    task_id="r7-checkpoint-test",
    trace_id="r7-checkpoint-trace",
)


def plan(q="blocked", s1="blocked", d1="blocked", f1="blocked"):
    return {
        "status": "running",
        "tasks": [
            {"task_id": "Q1", "status": q, "depends_on": []},
            {"task_id": "S1", "status": s1, "depends_on": ["Q1"]},
            {"task_id": "D1", "status": d1, "depends_on": ["S1"]},
            {"task_id": "F1", "status": f1, "depends_on": ["D1"]},
        ],
    }


class ResearchCheckpointTests(unittest.TestCase):
    def test_meaningful_boundaries_are_durable_and_ordered(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonResearchCheckpointStore(tmp)
            recorder = ResearchCheckpointRecorder(
                run_id="RUN-TEST-001",
                execution_context=CONTEXT,
                store=store,
            )

            recorder.observe({"type": "plan_created", "plan": plan(q="ready")})
            recorder.observe(
                {
                    "type": "evidence_registered",
                    "evidence": {"evidence_id": "BLS:CUSR0000SA0"},
                }
            )
            recorder.observe(
                {"type": "task_completed", "task_id": "Q1", "plan": plan(q="completed")}
            )
            recorder.observe(
                {
                    "type": "task_completed",
                    "task_id": "S1",
                    "plan": plan(q="completed", s1="completed"),
                }
            )
            recorder.observe(
                {
                    "type": "task_completed",
                    "task_id": "D1",
                    "plan": plan(q="completed", s1="completed", d1="completed"),
                }
            )
            recorder.observe(
                {
                    "type": "task_completed",
                    "task_id": "F1",
                    "plan": plan(
                        q="completed",
                        s1="completed",
                        d1="completed",
                        f1="completed",
                    ),
                }
            )

            checkpoints = recorder.checkpoints()
            self.assertEqual(
                [item["boundary"] for item in checkpoints],
                ["after_plan_created", "after_evidence", "after_S1", "after_D1", "after_F1"],
            )
            self.assertEqual([item["checkpoint_id"] for item in checkpoints], ["CP-001", "CP-002", "CP-003", "CP-004", "CP-005"])
            self.assertEqual(checkpoints[1]["evidence_ids"], ["BLS:CUSR0000SA0"])
            self.assertEqual(checkpoints[1]["recovery"]["resume_candidate"], "S1")
            self.assertFalse(checkpoints[1]["restore_enabled"])
            self.assertTrue(checkpoints[1]["durable"])
            self.assertTrue(checkpoints[-1]["artifacts"]["S1"])
            self.assertTrue(checkpoints[-1]["artifacts"]["D1"])
            self.assertTrue(checkpoints[-1]["artifacts"]["F1"])

            persisted = store.list("RUN-TEST-001")
            self.assertEqual(persisted, checkpoints)
            self.assertEqual(store.latest("RUN-TEST-001")["checkpoint_id"], "CP-005")

    def test_duplicate_boundary_is_not_written_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = ResearchCheckpointRecorder(
                run_id="RUN-TEST-002",
                execution_context=CONTEXT,
                store=JsonResearchCheckpointStore(tmp),
            )
            event = {"type": "plan_created", "plan": plan(q="ready")}
            recorder.observe(event)
            recorder.observe(event)
            self.assertEqual(len(recorder.checkpoints()), 1)


if __name__ == "__main__":
    unittest.main()
