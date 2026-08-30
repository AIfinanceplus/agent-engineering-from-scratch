"""R9 evals: preserve the R8 core contract and validate the separate market-context lane."""

from __future__ import annotations

from copy import deepcopy

from r8_evals import make_r8_eval_suite
from r9_market import EXPECTED_IDS


CORE_IDS = {"S1", "D1", "F1"}
MARKET_TASK_IDS = ["M1", "M2", "M3", "M4", "M5", "M6"]


def make_r9_eval_suite(blueprint: dict, result: dict, domain: str) -> dict:
    core = _project_core_result(blueprint, result)
    base = make_r8_eval_suite(blueprint, core, domain)
    market_case = _market_context_case(result, domain)
    cases = [*base.get("cases", []), market_case]
    passed = sum(1 for case in cases if case["report"]["passed"])
    return {
        "passed": passed,
        "total": len(cases),
        "pass_rate": round(passed / len(cases), 3) if cases else 1.0,
        "cases": cases,
    }


def _project_core_result(blueprint: dict, result: dict) -> dict:
    """Remove R9 Decision Context so R7/R8 contracts still judge the core research lane."""
    projected = deepcopy(result)
    query_ids = [row.get("query_id") for row in blueprint.get("queries") or []]
    allowed_tasks = set(query_ids) | CORE_IDS
    plan = deepcopy(projected.get("plan") or {})
    plan["tasks"] = [
        task for task in plan.get("tasks") or [] if task.get("task_id") in allowed_tasks
    ]
    projected["plan"] = plan
    projected["results"] = {
        key: value for key, value in (projected.get("results") or {}).items() if key in allowed_tasks
    }

    s1_ids = set(((projected.get("results") or {}).get("S1") or {}).get("evidence_ids") or [])
    projected["evidence"] = [
        row for row in projected.get("evidence") or [] if row.get("evidence_id") in s1_ids
    ]
    projected["citations"] = [
        row for row in projected.get("citations") or [] if row.get("evidence_id") in s1_ids
    ]
    return projected


def _market_context_case(result: dict, domain: str) -> dict:
    tasks = (result.get("plan") or {}).get("tasks") or []
    task_ids = [task.get("task_id") for task in tasks]
    results = result.get("results") or {}
    s1 = results.get("S1") or {}
    d1 = results.get("D1") or {}
    f1 = results.get("F1") or {}
    market = results.get("M6") or {}

    if domain == "policy":
        checks = [
            _check(
                "no_market_lane",
                "Policy mode does not fetch Investment market context",
                [task_id for task_id in task_ids if str(task_id).startswith("M")],
                [],
            ),
            _check("no_market_snapshot", "Policy mode has no M6 artifact", bool(market), False),
            _check("core_lineage_intact", "Policy D1 still inherits S1 Evidence", d1.get("evidence_ids"), s1.get("evidence_ids")),
        ]
        return _case("r9-policy-market-context-contract", checks)

    market_ids = set(market.get("evidence_ids") or [])
    s1_ids = set(s1.get("evidence_ids") or [])
    semantics = market.get("semantics") or {}
    guardrails = market.get("guardrails") or {}
    checks = [
        _check(
            "market_lane_tasks",
            "Investment adds the fixed M1..M6 Decision Context lane",
            [task_id for task_id in task_ids if str(task_id).startswith("M")],
            MARKET_TASK_IDS,
        ),
        _check("snapshot_type", "M6 is a market-pricing snapshot", market.get("artifact_type"), "market_pricing_snapshot"),
        _check("fixed_market_evidence", "M6 uses only approved fixed FRED market Evidence", market_ids, EXPECTED_IDS),
        _check("research_market_separation", "Market Evidence never enters S1", bool(s1_ids & market_ids), False),
        _check("d1_core_lineage", "R8 D1 still inherits only S1 research Evidence", set(d1.get("evidence_ids") or []), s1_ids),
        _check("f1_core_lineage", "Forecast targets still inherit only S1 research Evidence", set(f1.get("evidence_ids") or []), s1_ids),
        _check("no_fed_path", "R9 does not infer a market-implied Fed path", semantics.get("fed_path"), "NOT_INFERRED_R9"),
        _check("no_implied_macro_view", "R9 does not construct Market Implied View", semantics.get("market_implied_macro_view"), "NOT_CONSTRUCTED_R9"),
        _check("no_mispricing", "R9 does not compute mispricing", semantics.get("mispricing"), "NOT_COMPUTED_R9"),
        _check("no_ev", "R9 does not compute expected value", semantics.get("expected_value"), "NOT_COMPUTED_R9"),
        _check("no_position", "R9 issues no position", semantics.get("position"), "NONE_R9"),
        _check("guardrail_position", "Snapshot cannot recommend a position", guardrails.get("position_recommended"), False),
    ]
    return _case("r9-investment-market-context-contract", checks)


def _case(case_id: str, checks: list[dict]) -> dict:
    passed = all(item["passed"] for item in checks)
    failures = [item["failure"] for item in checks if not item["passed"]]
    return {
        "case": {"case_id": case_id},
        "report": {"case_id": case_id, "passed": passed, "checks": checks, "failures": failures},
        "process": [
            {"type": "eval_case_started", "case_id": case_id, "check_ids": [item["check_id"] for item in checks]},
            *[{"type": "eval_check", "case_id": case_id, **item} for item in checks],
            {"type": "eval_case_verdict", "case_id": case_id, "passed": passed, "failures": failures},
        ],
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
