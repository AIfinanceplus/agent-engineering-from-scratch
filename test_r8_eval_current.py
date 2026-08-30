import unittest
from unittest.mock import patch

from r8_eval_current import evaluate_current_run


RUN = {
    "ok": True,
    "run_id": "RUN-R8-EVAL-001",
    "domain": "investment",
    "blueprint": {
        "queries": [
            {
                "query_id": "Q1",
                "provider": "BLS",
                "capability": "headline_cpi",
                "arguments": {"series_id": "CUSR0000SA0"},
            }
        ]
    },
    "plan": {"status": "completed", "tasks": []},
    "results": {},
    "evidence": [],
    "citations": [],
}


class R8EvalCurrentRunTests(unittest.TestCase):
    def test_evaluates_existing_artifact_without_creating_a_research_run(self):
        expected_suite = {"passed": 5, "total": 5, "pass_rate": 1.0, "cases": []}
        with patch("r8_eval_current.make_r8_eval_suite", return_value=expected_suite) as make_suite:
            payload = evaluate_current_run(RUN)

        make_suite.assert_called_once_with(RUN["blueprint"], RUN, "investment")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["run_id"], RUN["run_id"])
        self.assertEqual(payload["research_result"], RUN)
        self.assertEqual(payload["eval_suite"], expected_suite)
        self.assertEqual(payload["evaluation_mode"], "existing_run_no_source_fetch")

    def test_requires_a_completed_run_artifact_shape(self):
        with self.assertRaisesRegex(ValueError, "run_id"):
            evaluate_current_run({"domain": "investment", "blueprint": {"queries": [{}]}})
        with self.assertRaisesRegex(ValueError, "compiled blueprint"):
            evaluate_current_run({"run_id": "RUN-X", "domain": "investment", "blueprint": {}})
        with self.assertRaisesRegex(ValueError, "domain"):
            evaluate_current_run({"run_id": "RUN-X", "domain": "other", "blueprint": {"queries": [{}]}})


if __name__ == "__main__":
    unittest.main()
