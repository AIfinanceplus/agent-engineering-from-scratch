"""V11 repeatable evals for the teaching research Agent.

A trace explains one run. An eval applies explicit expectations to a run so
changes can be compared over time instead of judged by vibes.
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

    evidence_coverage = _ratio(len(expected_evidence & collected_evidence_ids), len(expected_evidence))
    citation_completeness = _ratio(len(expected_citations & actual_citation_ids), len(expected_citations))
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

    failures = []
    if not success:
        failures.append("plan did not complete successfully")
    if task_count != case.expected_task_count:
        failures.append(
            f"expected {case.expected_task_count} tasks, observed {task_count}"
        )
    if task_completion_rate < 1:
        failures.append("not all expected tasks completed")
    if evidence_coverage < 1:
        failures.append("expected evidence coverage is incomplete")
    if citation_completeness < 1:
        failures.append("expected citations are incomplete")
    if not citations_grounded:
        failures.append("one or more citations are not backed by collected evidence")
    if confidence < case.min_confidence:
        failures.append(
            f"confidence {confidence:.3f} is below floor {case.min_confidence:.3f}"
        )

    trace = result.get("trace") or {}
    return EvalReport(
        case_id=case.case_id,
        passed=not failures,
        scores=scores,
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
            }
            for run in runs
        ],
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
