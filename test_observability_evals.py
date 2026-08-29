import unittest

from context import ExecutionContext
from evals import DEFAULT_EVAL_CASES, EvalCase, run_eval_case, run_eval_suite, score_result
from observability import TraceRecorder
from planner import ResearchPlanner
from scheduler import DAGScheduler
from tools import reset_teaching_tools


CONTEXT = ExecutionContext(
    tenant_id="demo-tenant",
    user_id="user-123",
    agent_id="research-agent",
    task_id="v11-test-root",
    trace_id="v11-test-trace",
)


class TraceRecorderTests(unittest.TestCase):
    def test_span_hierarchy_and_duration_are_explicit(self):
        times = iter([0.0, 0.1, 0.2, 0.5])
        trace = TraceRecorder("trace-test", clock=lambda: next(times))
        root = trace.start_span("plan.run")
        task = trace.start_span("task.E1", parent_span_id=root, task_id="E1")
        trace.end_span(task)
        trace.end_span(root)

        summary = trace.summary()
        self.assertEqual(summary["trace_id"], "trace-test")
        self.assertEqual(summary["span_count"], 2)
        self.assertEqual(summary["spans"][1]["parent_span_id"], root)
        self.assertEqual(summary["spans"][1]["duration_ms"], 100.0)
        self.assertEqual(summary["spans"][0]["duration_ms"], 500.0)

    def test_research_scheduler_records_expected_metrics(self):
        reset_teaching_tools()
        trace = TraceRecorder(CONTEXT.trace_id)
        result = DAGScheduler().run(
            ResearchPlanner().plan("trace the synthetic research flow"),
            execution_context=CONTEXT,
            trace_recorder=trace,
        )

        self.assertTrue(result["ok"])
        summary = result["trace"]
        self.assertEqual(summary["span_count"], 4)
        self.assertEqual(summary["metrics"]["scheduler_ticks"], 3)
        self.assertEqual(summary["metrics"]["tasks_started"], 3)
        self.assertEqual(summary["metrics"]["tasks_completed"], 3)
        self.assertEqual(summary["metrics"]["tool_attempts"], 3)
        self.assertEqual(summary["metrics"]["evidence_registered"], 2)
        self.assertEqual(summary["metrics"]["citations_verified"], 2)
        self.assertEqual(
            [span["name"] for span in summary["spans"]],
            ["plan.run", "task.E1", "task.E2", "task.S1"],
        )


class EvalTests(unittest.TestCase):
    def setUp(self):
        reset_teaching_tools()

    def test_default_eval_case_passes_with_complete_lineage(self):
        run = run_eval_case(DEFAULT_EVAL_CASES[0], execution_context=CONTEXT)
        report = run["report"]
        self.assertTrue(report["passed"])
        self.assertEqual(report["scores"]["evidence_coverage"], 1.0)
        self.assertEqual(report["scores"]["citation_completeness"], 1.0)
        self.assertTrue(report["scores"]["citations_grounded"])
        self.assertEqual(report["trace_metrics"]["tool_attempts"], 3)
        self.assertEqual(len(report["checks"]), 6)
        self.assertTrue(all(check["passed"] for check in report["checks"]))

    def test_eval_case_exposes_case_run_checks_and_verdict_process(self):
        run = run_eval_case(DEFAULT_EVAL_CASES[0], execution_context=CONTEXT)
        process = run["process"]
        self.assertEqual(process[0]["type"], "eval_case_started")
        self.assertEqual(process[1]["type"], "eval_agent_run_completed")
        self.assertEqual(
            [step["check_id"] for step in process if step["type"] == "eval_check"],
            [
                "success",
                "task_completion_rate",
                "evidence_coverage",
                "citation_completeness",
                "citations_grounded",
                "confidence",
            ],
        )
        self.assertEqual(process[-1]["type"], "eval_case_verdict")
        self.assertTrue(process[-1]["passed"])

    def test_default_eval_suite_is_repeatable_green_and_visualizable(self):
        suite = run_eval_suite(execution_context=CONTEXT)
        self.assertEqual(suite["passed"], 2)
        self.assertEqual(suite["total"], 2)
        self.assertEqual(suite["pass_rate"], 1.0)
        self.assertTrue(all(case["report"]["passed"] for case in suite["cases"]))
        self.assertTrue(all(case["process"] for case in suite["cases"]))
        self.assertTrue(
            all(case["process"][-1]["type"] == "eval_case_verdict" for case in suite["cases"])
        )

    def test_ungrounded_or_missing_citation_fails_eval(self):
        case = EvalCase(
            case_id="bad-citation",
            goal="test",
            expected_evidence_ids=("E1", "E2"),
            expected_citation_ids=("[E1]", "[E2]"),
            min_confidence=0.8,
        )
        fake_result = {
            "ok": True,
            "plan": {
                "status": "completed",
                "tasks": [
                    {"status": "completed"},
                    {"status": "completed"},
                    {"status": "completed"},
                ],
            },
            "evidence": [
                {"evidence_id": "E1"},
            ],
            "citations": [
                {"citation": "[E1]", "evidence_id": "E1"},
                {"citation": "[E99]", "evidence_id": "E99"},
            ],
            "final_artifact": {"confidence": 0.9},
            "trace": {"metrics": {}},
        }

        report = score_result(case, fake_result)
        self.assertFalse(report.passed)
        self.assertLess(report.scores["evidence_coverage"], 1.0)
        self.assertLess(report.scores["citation_completeness"], 1.0)
        self.assertFalse(report.scores["citations_grounded"])
        self.assertTrue(report.failures)
        grounded_check = next(
            check for check in report.checks if check["check_id"] == "citations_grounded"
        )
        self.assertFalse(grounded_check["passed"])


if __name__ == "__main__":
    unittest.main()
