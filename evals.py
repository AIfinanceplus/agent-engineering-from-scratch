"""V11 repeatable evals for the teaching research Agent.

A trace explains one run. An eval applies explicit expectations to a run so
changes can be compared over time instead of judged by vibes.

The browser should be able to show *how* a verdict was produced, not only the
final PASS/FAIL. Each EvalReport therefore contains explicit deterministic
checks, and each eval case exposes a small process timeline:

case -> agent run -> checks -> verdict
"""

from dataclasses import asdict, dataclass, field, replace

from context import ExecutionContext
from observability import TraceRecorder
from planner import ResearchPlanner
from scheduler import DAGScheduler


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    goal: str
    expected_evidence_ids: tuple[str, ...] = ("E1", "E2")
    expected_citation_ids: tuple[str, ...] = ("[E1]", "[E2]")
    min_confidence: float = 0.8
    expected_task_count: int = 3


@dataclass
class EvalReport:
    case_id: str
    passed: bool
    scores: dict
    checks: list[dict] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    trace_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def score_result(case: EvalCase, result: dict) -> EvalReport:
    plan = result.get("plan") or {}
    tasks = plan.get("tasks") or []
    evidence = result.get("evidence") or []
    citations = result.get("citations") or []
    artifact = result.get("final_artifact") or {}

    collected_evidence_ids = {
        item.get("evidence_id") for item in evidence if item.get("evidence_id")
    }
    actual_citation_ids = {
        item.get("citation") for item in citations if item.get("citation")
    }
    cited_evidence_ids = {
        item.get("evidence_id") for item in citations if item.get("evidence_id")
    }

    expected_evidence = set(case.expected_evidence_ids)
    expected_citations = set(case.expected_citation_ids)
    completed = sum(task.get("status") == "completed" for task in tasks)
    task_count = len(tasks)
    confidence = artifact.get("confidence", 0) if isinstance(artifact, dict) else 0

    evidence_coverage = _ratio(
        len(expected_evidence & collected_evidence_ids),
        len(expected_evidence),
    )
    citation_completeness = _ratio(
        len(expected_citations & actual_citation_ids),
        len(expected_citations),
    )
    task_completion_rate = _ratio(completed, case.expected_task_count)
    citations_grounded = cited_evidence_ids.issubset(collected_evidence_ids)
    success = bool(result.get("ok")) and plan.get("status") == "completed"

    scores = {
        "success": success,
        "task_completion_rate": round(task_completion_rate, 3),
        "evidence_coverage": round(evidence_coverage, 3),
        "citation_completeness": round(citation_completeness, 3),
        "citations_grounded": citations_grounded,
        "confidence": confidence,
        "task_count": task_count,
    }

    checks = [
        _check(
            "success",
            "Plan completed successfully",
            success,
            actual=success,
            expected=True,
            failure="plan did not complete successfully",
        ),
        _check(
            "task_completion_rate",
            "All expected tasks completed",
            task_count == case.expected_task_count and task_completion_rate >= 1,
            actual=round(task_completion_rate, 3),
            expected=1.0,
            failure=(
                f"expected {case.expected_task_count} tasks, observed {task_count}"
                if task_count != case.expected_task_count
                else "not all expected tasks completed"
            ),
        ),
        _check(
            "evidence_coverage",
            "Expected evidence was collected",
            evidence_coverage >= 1,
            actual=round(evidence_coverage, 3),
            expected=1.0,
            failure="expected evidence coverage is incomplete",
        ),
        _check(
            "citation_completeness",
            "Expected citations were emitted",
            citation_completeness >= 1,
            actual=round(citation_completeness, 3),
            expected=1.0,
            failure="expected citations are incomplete",
        ),
        _check(
            "citations_grounded",
            "Every citation is backed by collected evidence",
            citations_grounded,
            actual=citations_grounded,
            expected=True,
            failure="one or more citations are not backed by collected evidence",
        ),
        _check(
            "confidence",
            "Confidence clears the case floor",
            confidence >= case.min_confidence,
            actual=confidence,
            expected=f">= {case.min_confidence:.3f}",
            failure=(
                f"confidence {confidence:.3f} is below floor {case.min_confidence:.3f}"
            ),
        ),
    ]
    failures = [check["failure"] for check in checks if not check["passed"]]

    trace = result.get("trace") or {}
    return EvalReport(
        case_id=case.case_id,
        passed=not failures,
        scores=scores,
        checks=checks,
        failures=failures,
        trace_metrics=dict(trace.get("metrics") or {}),
    )


def run_eval_case(
    case: EvalCase,
    *,
    execution_context: ExecutionContext | None = None,
) -> dict:
    if execution_context is None:
        execution_context = ExecutionContext(
            tenant_id="eval-tenant",
            user_id="eval-user",
            agent_id="general-agent",
            task_id=f"eval:{case.case_id}",
            trace_id=f"eval-trace:{case.case_id}",
        )
    else:
        execution_context = replace(
            execution_context,
            task_id=f"{execution_context.task_id}:eval:{case.case_id}",
            trace_id=f"{execution_context.trace_id}:eval:{case.case_id}",
        )

    trace = TraceRecorder(execution_context.trace_id)
    result = DAGScheduler().run(
        ResearchPlanner().plan(case.goal),
        execution_context=execution_context,
        trace_recorder=trace,
    )
    report = score_result(case, result)
    return {
        "case": asdict(case),
        "report": report.to_dict(),
        "process": _build_process(case, result, report),
        "result": result,
    }


def run_eval_suite(
    cases: tuple[EvalCase, ...] | None = None,
    *,
    execution_context: ExecutionContext | None = None,
) -> dict:
    selected = DEFAULT_EVAL_CASES if cases is None else cases
    runs = [
        run_eval_case(case, execution_context=execution_context)
        for case in selected
    ]
    passed = sum(run["report"]["passed"] for run in runs)
    total = len(runs)
    return {
        "passed": passed,
        "total": total,
        "pass_rate": round(_ratio(passed, total), 3),
        "cases": [
            {
                "case": run["case"],
                "report": run["report"],
                "process": run["process"],
            }
            for run in runs
        ],
    }


def _build_process(case: EvalCase, result: dict, report: EvalReport) -> list[dict]:
    evidence_ids = [
        item.get("evidence_id")
        for item in result.get("evidence", [])
        if item.get("evidence_id")
    ]
    citation_ids = [
        item.get("citation")
        for item in result.get("citations", [])
        if item.get("citation")
    ]
    plan = result.get("plan") or {}
    artifact = result.get("final_artifact") or {}

    process = [
        {
            "type": "eval_case_started",
            "case_id": case.case_id,
            "goal": case.goal,
            "expectations": {
                "expected_task_count": case.expected_task_count,
                "expected_evidence_ids": list(case.expected_evidence_ids),
                "expected_citation_ids": list(case.expected_citation_ids),
                "min_confidence": case.min_confidence,
            },
        },
        {
            "type": "eval_agent_run_completed",
            "case_id": case.case_id,
            "run_summary": {
                "ok": bool(result.get("ok")),
                "plan_status": plan.get("status"),
                "task_count": len(plan.get("tasks") or []),
                "evidence_ids": evidence_ids,
                "citation_ids": citation_ids,
                "confidence": artifact.get("confidence", 0)
                if isinstance(artifact, dict)
                else 0,
                "trace_metrics": dict((result.get("trace") or {}).get("metrics") or {}),
            },
        },
    ]
    process.extend(
        {
            "type": "eval_check",
            "case_id": case.case_id,
            **check,
        }
        for check in report.checks
    )
    process.append(
        {
            "type": "eval_case_verdict",
            "case_id": case.case_id,
            "passed": report.passed,
            "failures": list(report.failures),
        }
    )
    return process


def _check(
    check_id: str,
    label: str,
    passed: bool,
    *,
    actual,
    expected,
    failure: str,
) -> dict:
    return {
        "check_id": check_id,
        "label": label,
        "passed": bool(passed),
        "actual": actual,
        "expected": expected,
        "failure": failure,
    }


def _ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


DEFAULT_EVAL_CASES = (
    EvalCase(
        case_id="research-lineage",
        goal="Explain the synthetic contribution using only collected evidence.",
        min_confidence=0.8,
    ),
    EvalCase(
        case_id="citation-integrity",
        goal="Produce a cited synthetic research conclusion with complete provenance.",
        min_confidence=0.85,
    ),
)
