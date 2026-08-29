"""R3 evals for decomposition, safe query compilation, and execution lineage."""

from __future__ import annotations

from r3_decomposition import build_blueprint
from r3_planner import R3ResearchPlanner


def make_r3_eval_suite(blueprint: dict, result: dict) -> dict:
    cases = [
        _decomposition_case(blueprint),
        _execution_case(blueprint, result),
    ]
    passed = sum(case["report"]["passed"] for case in cases)
    return {
        "passed": passed,
        "total": len(cases),
        "pass_rate": round(passed / len(cases), 3) if cases else 1.0,
        "cases": cases,
    }


def _decomposition_case(blueprint: dict) -> dict:
    subquestions = blueprint.get("subquestions") or []
    queries = blueprint.get("queries") or []
    capabilities = [item.get("capability") for item in subquestions]
    query_capabilities = [item.get("capability") for item in queries]

    unsafe_fields = []
    for query in queries:
        arguments = query.get("arguments") or {}
        for key in arguments:
            if key.lower() in {"api_key", "url", "endpoint", "token", "secret"}:
                unsafe_fields.append(f"{query.get('query_id')}:{key}")

    narrow_blueprint = build_blueprint("Compare headline and core CPI.").to_dict()
    narrow_queries = narrow_blueprint.get("queries") or []
    narrow_plan = R3ResearchPlanner().plan_from_blueprint(
        build_blueprint("Compare headline and core CPI."),
        reference_date="2026-08-29",
    )

    checks = [
        _check("subquestion_query_1to1", "Every subquestion compiles to exactly one query", len(subquestions), len(queries)),
        _check("capability_alignment", "Query capabilities match decomposed capabilities", query_capabilities, capabilities),
        _check("safe_query_fields", "Compiled arguments contain no URL/API-key/secret fields", unsafe_fields, []),
        _check("approved_providers", "Every query uses an approved provider", sorted({q.get("provider") for q in queries}), sorted({q.get("provider") for q in queries if q.get("provider") in {"BLS", "FRED", "EIA"}})),
        _check("narrow_query_pruning", "Headline/core-only question prunes FRED and EIA", [q.get("capability") for q in narrow_queries], ["headline_cpi", "core_cpi"]),
        _check("narrow_dag_size", "Two source queries become two source tasks plus one synthesis task", len(narrow_plan.tasks), 3),
        _check("narrow_credentials", "Narrow BLS-only question requires no credential env vars", sorted({env for q in narrow_queries for env in (q.get("requires_env") or [])}), []),
    ]
    return _case("r3-decomposition-query-contract", checks)


def _execution_case(blueprint: dict, result: dict) -> dict:
    queries = blueprint.get("queries") or []
    expected_query_ids = [item.get("query_id") for item in queries]
    plan = result.get("plan") or {}
    tasks = plan.get("tasks") or []
    task_ids = [item.get("task_id") for item in tasks]
    completed = [item.get("task_id") for item in tasks if item.get("status") == "completed"]
    evidence = result.get("evidence") or []
    citations = result.get("citations") or []
    artifact = result.get("final_artifact") or {}
    trace = result.get("trace") or {}
    metrics = trace.get("metrics") or {}

    evidence_ids = {item.get("evidence_id") for item in evidence if item.get("evidence_id")}
    cited_ids = {item.get("evidence_id") for item in citations if item.get("evidence_id")}
    freshness = artifact.get("freshness") or {} if isinstance(artifact, dict) else {}
    limitations = " ".join(str(x).lower() for x in (artifact.get("limitations") or [])) if isinstance(artifact, dict) else ""
    answer = str(artifact.get("answer", "")).lower() if isinstance(artifact, dict) else ""

    checks = [
        _check("success", "Dynamic research plan completed", bool(result.get("ok")) and plan.get("status") == "completed", True),
        _check("dynamic_task_contract", "Execution tasks equal compiled queries plus S1", task_ids, [*expected_query_ids, "S1"]),
        _check("task_completion", "All dynamic tasks completed", completed, [*expected_query_ids, "S1"]),
        _check("evidence_count", "One Evidence record per compiled query", len(evidence), len(queries)),
        _check("citation_grounding", "Citation IDs exactly match collected Evidence IDs", cited_ids == evidence_ids and len(cited_ids) == len(queries), True),
        _check("freshness_coverage", "Freshness computed for every collected Evidence", set(freshness) == evidence_ids, True),
        _check("tool_attempt_floor", "Runtime made at least one Tool attempt per task", int(metrics.get("tool_attempts", 0)) >= len(tasks), True),
        _check("causal_guardrail", "Synthesis remains descriptive rather than causal", "not causal" in answer or "not causal" in limitations, True),
    ]
    return _case("r3-execution-evidence-contract", checks)


def _case(case_id: str, checks: list[dict]) -> dict:
    passed = all(check["passed"] for check in checks)
    process = [
        {"type": "eval_case_started", "case_id": case_id, "check_ids": [check["check_id"] for check in checks]},
        *[{"type": "eval_check", "case_id": case_id, **check} for check in checks],
        {"type": "eval_case_verdict", "case_id": case_id, "passed": passed, "failures": [check["failure"] for check in checks if not check["passed"]]},
    ]
    return {
        "case": {"case_id": case_id},
        "report": {
            "case_id": case_id,
            "passed": passed,
            "checks": checks,
            "failures": [check["failure"] for check in checks if not check["passed"]],
        },
        "process": process,
    }


def _check(check_id: str, label: str, actual, expected) -> dict:
    passed = actual == expected
    return {
        "check_id": check_id,
        "label": label,
        "passed": passed,
        "actual": actual,
        "expected": expected,
        "failure": "" if passed else f"{label}: expected {expected!r}, got {actual!r}",
    }
