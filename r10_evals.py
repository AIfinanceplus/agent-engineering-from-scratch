"""R10 evals: preserve R9 contracts and validate pricing/EV discipline."""

from __future__ import annotations

from r9_evals import make_r9_eval_suite


def make_r10_eval_suite(blueprint: dict, result: dict, domain: str) -> dict:
    base = make_r9_eval_suite(blueprint, result, domain)
    decision_case = _r10_decision_case(result, domain)
    cases = [*base.get("cases", []), decision_case]
    passed = sum(1 for case in cases if case["report"]["passed"])
    return _json_safe(
        {
            "passed": passed,
            "total": len(cases),
            "pass_rate": round(passed / len(cases), 3) if cases else 1.0,
            "cases": cases,
            "evaluation_version": "R10",
            "serialization_contract": "json_safe",
        }
    )


def _r10_decision_case(result: dict, domain: str) -> dict:
    tasks = (result.get("plan") or {}).get("tasks") or []
    task_ids = [row.get("task_id") for row in tasks]
    results = result.get("results") or {}
    i1 = results.get("I1") or {}

    if domain == "policy":
        checks = [
            _check("policy_no_i1_task", "Policy does not run Investment I1", "I1" in task_ids, False),
            _check("policy_no_i1_artifact", "Policy has no Investment decision artifact", bool(i1), False),
        ]
        return _case("r10-policy-separation-contract", checks)

    research_ids = set(i1.get("research_evidence_ids") or [])
    market_ids = set(i1.get("market_evidence_ids") or [])
    combined = set(i1.get("evidence_ids") or [])
    mispricing = i1.get("mispricing") or {}
    ev = i1.get("expected_value") or {}
    position = i1.get("position_gate") or {}
    guardrails = i1.get("guardrails") or {}

    checks = [
        _check("i1_task", "Investment plan contains I1 after research/market artifacts", "I1" in task_ids, True),
        _check("i1_type", "I1 is an R10 investment decision", i1.get("artifact_type"), "r10_investment_decision"),
        _check("lineage_union", "I1 lineage is exactly Research Evidence union Market Evidence", combined, research_ids | market_ids),
        _check("lineage_separate", "Research and Market lineage remain separately inspectable", bool(research_ids and market_ids), True),
        _check(
            "mispricing_not_fabricated",
            "Directional forecast is not relabeled as numerical mispricing",
            mispricing.get("gap_magnitude_pp"),
            None,
        ),
        _check(
            "ev_requires_scenario_book",
            "EV abstains until explicit probabilities and payoffs exist",
            ev.get("status"),
            "EV_NOT_COMPUTABLE_MISSING_SCENARIO_BOOK",
        ),
        _check("no_support_probability", "Support score is never used as probability", guardrails.get("support_score_used_as_probability"), False),
        _check("no_fake_fed_path", "2Y Treasury is not treated as a Fed futures path", guardrails.get("fed_futures_path_inferred_from_treasury_yield"), False),
        _check("no_position", "No position is issued before EV/risk budget", position.get("position"), "NONE"),
    ]
    return _case("r10-investment-pricing-ev-contract", checks)


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


def _json_safe(value):
    """Normalize Eval artifacts before they cross the browser/stream boundary."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted((_json_safe(item) for item in value), key=lambda item: repr(item))
    return value
