"""R2 eval suite for the real multi-source macro research path.

Unlike the legacy V11 synthetic evals, these cases execute the R2
H1/C1/F1/G1 -> A1 DAG in fixture mode. The process payload is intentionally
explicit so the browser can show Case -> Agent Run -> Checks -> Verdict.
"""

from dataclasses import asdict, dataclass, field, replace

from context import ExecutionContext
from observability import TraceRecorder
from r2_planner import MultiSourceMacroPlanner
from r2_tooling import register_r2_tools
from scheduler import DAGScheduler


EXPECTED_TASK_IDS = ("H1", "C1", "F1", "G1", "A1")
EXPECTED_EVIDENCE_IDS = (
    "BLS:CUSR0000SA0",
    "BLS:CUSR0000SA0L1E",
    "FRED:T5YIE",
    "EIA:PET.EMM_EPMR_PTE_NUS_DPG.W",
)
EXPECTED_CITATION_IDS = tuple(f"[{item}]" for item in EXPECTED_EVIDENCE_IDS)
EXPECTED_PROVIDERS = ("BLS", "FRED", "EIA")


@dataclass(frozen=True)
class R2EvalCase:
    case_id: str
    goal: str
    reference_date: str = "2026-03-20"
    require_all_nonstale: bool = True
    require_causal_guardrail: bool = True


@dataclass
class R2EvalReport:
    case_id: str
    passed: bool
    checks: list[dict] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    scores: dict = field(default_factory=dict)
    trace_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def score_r2_result(case: R2EvalCase, result: dict) -> R2EvalReport:
    plan = result.get("plan") or {}
    tasks = plan.get("tasks") or []
    evidence = result.get("evidence") or []
    citations = result.get("citations") or []
    artifact = result.get("final_artifact") or {}
    trace = result.get("trace") or {}

    task_ids = tuple(task.get("task_id") for task in tasks)
    completed = sum(task.get("status") == "completed" for task in tasks)
    evidence_ids = tuple(
        item.get("evidence_id") for item in evidence if item.get("evidence_id")
    )
    evidence_set = set(evidence_ids)
    providers = {
        str(evidence_id).split(":", 1)[0]
        for evidence_id in evidence_ids
        if ":" in str(evidence_id)
    }
    citation_ids = tuple(
        item.get("citation") for item in citations if item.get("citation")
    )
    cited_evidence_ids = {
        item.get("evidence_id") for item in citations if item.get("evidence_id")
    }
    freshness = artifact.get("freshness") or {} if isinstance(artifact, dict) else {}
    freshness_statuses = {
        evidence_id: info.get("status")
        for evidence_id, info in freshness.items()
        if isinstance(info, dict)
    }
    limitations = artifact.get("limitations") or [] if isinstance(artifact, dict) else []
    answer = artifact.get("answer", "") if isinstance(artifact, dict) else ""
    tool_attempts = int((trace.get("metrics") or {}).get("tool_attempts", 0))

    success = bool(result.get("ok")) and plan.get("status") == "completed"
    task_contract_ok = task_ids == EXPECTED_TASK_IDS and completed == len(EXPECTED_TASK_IDS)
    evidence_contract_ok = set(evidence_ids) == set(EXPECTED_EVIDENCE_IDS)
    provider_coverage_ok = providers == set(EXPECTED_PROVIDERS)
    citation_completeness_ok = set(citation_ids) == set(EXPECTED_CITATION_IDS)
    citations_grounded = cited_evidence_ids.issubset(evidence_set) and cited_evidence_ids == set(EXPECTED_EVIDENCE_IDS)
    freshness_complete = set(freshness) == set(EXPECTED_EVIDENCE_IDS)
    all_nonstale = freshness_complete and all(
        status in {"fresh", "aging"} for status in freshness_statuses.values()
    )
    causal_guardrail = (
        "not a causal cpi attribution" in answer.lower()
        and any("not causal cpi contributions" in str(item).lower() for item in limitations)
    )

    checks = [
        _check("success", "R2 plan completed", success, success, True, "R2 plan did not complete"),
        _check(
            "task_contract",
            "H1/C1/F1/G1/A1 all completed",
            task_contract_ok,
            {"task_ids": list(task_ids), "completed": completed},
            {"task_ids": list(EXPECTED_TASK_IDS), "completed": len(EXPECTED_TASK_IDS)},
            "R2 task DAG did not match the expected contract",
        ),
        _check(
            "evidence_contract",
            "Four expected source Evidence records exist",
            evidence_contract_ok,
            list(evidence_ids),
            list(EXPECTED_EVIDENCE_IDS),
            "R2 evidence IDs are incomplete or unexpected",
        ),
        _check(
            "provider_coverage",
            "BLS + FRED + EIA are represented",
            provider_coverage_ok,
            sorted(providers),
            list(EXPECTED_PROVIDERS),
            "not all required providers are represented",
        ),
        _check(
            "citation_completeness",
            "All four source citations were emitted",
            citation_completeness_ok,
            list(citation_ids),
            list(EXPECTED_CITATION_IDS),
            "R2 citations are incomplete",
        ),
        _check(
            "citations_grounded",
            "Every citation maps to collected Evidence",
            citations_grounded,
            sorted(cited_evidence_ids),
            list(EXPECTED_EVIDENCE_IDS),
            "one or more citations are ungrounded",
        ),
        _check(
            "freshness_complete",
            "Every Evidence record has a freshness clock",
            freshness_complete,
            freshness_statuses,
            "four evidence freshness entries",
            "freshness coverage is incomplete",
        ),
        _check(
            "all_nonstale",
            "Fixture evidence is fresh or aging, not stale",
            (all_nonstale if case.require_all_nonstale else True),
            freshness_statuses,
            "no stale evidence",
            "one or more fixture evidence records are stale",
        ),
        _check(
            "tool_attempts",
            "R2 executes exactly five Tool calls",
            tool_attempts == 5,
            tool_attempts,
            5,
            "unexpected Tool attempt count",
        ),
        _check(
            "causal_guardrail",
            "Synthesis labels cross-source signals as descriptive, not causal",
            (causal_guardrail if case.require_causal_guardrail else True),
            causal_guardrail,
            True,
            "causal limitation language is missing",
        ),
    ]
    failures = [check["failure"] for check in checks if not check["passed"]]
    scores = {
        "success": success,
        "task_completion_rate": round(completed / len(EXPECTED_TASK_IDS), 3),
        "evidence_coverage": round(len(set(evidence_ids) & set(EXPECTED_EVIDENCE_IDS)) / len(EXPECTED_EVIDENCE_IDS), 3),
        "citation_coverage": round(len(set(citation_ids) & set(EXPECTED_CITATION_IDS)) / len(EXPECTED_CITATION_IDS), 3),
        "provider_coverage": round(len(providers & set(EXPECTED_PROVIDERS)) / len(EXPECTED_PROVIDERS), 3),
        "freshness_coverage": round(len(set(freshness) & set(EXPECTED_EVIDENCE_IDS)) / len(EXPECTED_EVIDENCE_IDS), 3),
        "tool_attempts": tool_attempts,
    }
    return R2EvalReport(
        case_id=case.case_id,
        passed=not failures,
        checks=checks,
        failures=failures,
        scores=scores,
        trace_metrics=dict(trace.get("metrics") or {}),
    )


def run_r2_eval_case(
    case: R2EvalCase,
    *,
    execution_context: ExecutionContext | None = None,
) -> dict:
    register_r2_tools()
    if execution_context is None:
        execution_context = ExecutionContext(
            tenant_id="eval-tenant",
            user_id="eval-user",
            agent_id="macro-research-agent",
            task_id=f"r2-eval:{case.case_id}",
            trace_id=f"r2-eval-trace:{case.case_id}",
        )
    else:
        execution_context = replace(
            execution_context,
            task_id=f"{execution_context.task_id}:r2-eval:{case.case_id}",
            trace_id=f"{execution_context.trace_id}:r2-eval:{case.case_id}",
        )

    trace = TraceRecorder(execution_context.trace_id)
    result = DAGScheduler().run(
        MultiSourceMacroPlanner().plan(
            case.goal,
            mode="fixture",
            reference_date=case.reference_date,
        ),
        execution_context=execution_context,
        trace_recorder=trace,
    )
    report = score_r2_result(case, result)
    return {
        "case": asdict(case),
        "report": report.to_dict(),
        "process": _build_process(case, result, report),
        "result": result,
    }


def run_r2_eval_suite(
    cases: tuple[R2EvalCase, ...] | None = None,
    *,
    execution_context: ExecutionContext | None = None,
) -> dict:
    selected = DEFAULT_R2_EVAL_CASES if cases is None else cases
    runs = [run_r2_eval_case(case, execution_context=execution_context) for case in selected]
    passed = sum(run["report"]["passed"] for run in runs)
    total = len(runs)
    return {
        "suite_id": "r2-multi-source-macro",
        "passed": passed,
        "total": total,
        "pass_rate": round(1.0 if total == 0 else passed / total, 3),
        "cases": [
            {"case": run["case"], "report": run["report"], "process": run["process"]}
            for run in runs
        ],
    }


def _build_process(case: R2EvalCase, result: dict, report: R2EvalReport) -> list[dict]:
    artifact = result.get("final_artifact") or {}
    process = [
        {
            "type": "eval_case_started",
            "case_id": case.case_id,
            "goal": case.goal,
            "expectations": {
                "task_ids": list(EXPECTED_TASK_IDS),
                "evidence_ids": list(EXPECTED_EVIDENCE_IDS),
                "providers": list(EXPECTED_PROVIDERS),
                "citation_ids": list(EXPECTED_CITATION_IDS),
                "tool_attempts": 5,
                "causal_guardrail": case.require_causal_guardrail,
            },
        },
        {
            "type": "eval_agent_run_completed",
            "case_id": case.case_id,
            "run_summary": {
                "ok": bool(result.get("ok")),
                "plan_status": (result.get("plan") or {}).get("status"),
                "task_ids": [task.get("task_id") for task in (result.get("plan") or {}).get("tasks", [])],
                "evidence_ids": [item.get("evidence_id") for item in result.get("evidence", [])],
                "citation_ids": [item.get("citation") for item in result.get("citations", [])],
                "freshness": artifact.get("freshness") if isinstance(artifact, dict) else {},
                "trace_metrics": dict((result.get("trace") or {}).get("metrics") or {}),
            },
        },
    ]
    process.extend(
        {"type": "eval_check", "case_id": case.case_id, **check}
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


def _check(check_id: str, label: str, passed: bool, actual, expected, failure: str) -> dict:
    return {
        "check_id": check_id,
        "label": label,
        "passed": bool(passed),
        "actual": actual,
        "expected": expected,
        "failure": failure,
    }


DEFAULT_R2_EVAL_CASES = (
    R2EvalCase(
        case_id="r2-multi-source-lineage",
        goal="Evaluate the full R2 BLS, FRED, and EIA evidence lineage.",
    ),
    R2EvalCase(
        case_id="r2-freshness-causal-guardrails",
        goal="Evaluate R2 freshness coverage and descriptive-vs-causal guardrails.",
    ),
)
