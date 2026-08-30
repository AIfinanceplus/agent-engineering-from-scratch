"""R10 evals: preserve R9 contracts and validate numerical pricing/EV discipline."""

from __future__ import annotations

from math import isclose

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
            "evaluation_version": "R10-step2",
            "serialization_contract": "json_safe",
        }
    )


def _r10_decision_case(result: dict, domain: str) -> dict:
    tasks = (result.get("plan") or {}).get("tasks") or []
    task_ids = [row.get("task_id") for row in tasks]
    results = result.get("results") or {}
    t1 = results.get("T1") or {}
    i1 = results.get("I1") or {}

    if domain == "policy":
        checks = [
            _check("policy_no_t1_task", "Policy does not run Investment numerical target T1", "T1" in task_ids, False),
            _check("policy_no_i1_task", "Policy does not run Investment I1", "I1" in task_ids, False),
            _check("policy_no_t1_artifact", "Policy has no numerical Investment target artifact", bool(t1), False),
            _check("policy_no_i1_artifact", "Policy has no Investment decision artifact", bool(i1), False),
        ]
        return _case("r10-policy-separation-contract", checks)

    research_ids = set(i1.get("research_evidence_ids") or [])
    market_ids = set(i1.get("market_evidence_ids") or [])
    combined = set(i1.get("evidence_ids") or [])
    target_ids = set(t1.get("evidence_ids") or [])
    mispricing = i1.get("mispricing") or {}
    payoff = i1.get("scenario_payoff_template") or {}
    ev = i1.get("expected_value") or {}
    position = i1.get("position_gate") or {}
    guardrails = i1.get("guardrails") or {}

    target_available = t1.get("status") == "NUMERICAL_TARGET_AVAILABLE"
    numeric_status_valid = (
        mispricing.get("status") in {"NUMERIC_GAP_AVAILABLE", "NO_NUMERIC_GAP"}
        if target_available
        else mispricing.get("status") in {
            "DIRECTIONAL_GAP_ONLY",
            "NO_DIRECTIONAL_GAP",
            "ABSTAINED_NO_COMPARABLE_OPEN_FORECAST",
        }
    )
    gap_math_valid = _gap_math_valid(t1, mispricing)
    payoff_contract_valid = _payoff_contract_valid(mispricing, payoff)

    checks = [
        _check("t1_task", "Investment plan contains T1 after F1", "T1" in task_ids, True),
        _check("i1_task", "Investment plan contains I1 after T1 and market context", "I1" in task_ids, True),
        _check("t1_type", "T1 is an R10 numerical research target", t1.get("artifact_type"), "r10_numerical_research_target"),
        _check("i1_type", "I1 is an R10 investment decision", i1.get("artifact_type"), "r10_investment_decision"),
        _check("lineage_union", "I1 lineage is exactly Research Evidence union Market Evidence", combined, research_ids | market_ids),
        _check("target_lineage_subset", "T1 cites only Evidence already present in S1", target_ids <= research_ids, True),
        _check("lineage_inspectable", "Research and Market context lineages remain inspectable", bool(research_ids and market_ids), True),
        _check("target_not_calibrated", "Mechanical T1 is explicitly not presented as calibrated", t1.get("calibration_status"), "NOT_CALIBRATED_MECHANICAL_BASELINE"),
        _check("numeric_status_valid", "Numerical gap appears only when T1 is comparable", numeric_status_valid, True),
        _check("gap_arithmetic", "Gap equals numerical research target minus current market baseline", gap_math_valid, True),
        _check("payoff_bridge", "Scenario payoff template respects the numerical-gap state", payoff_contract_valid, True),
        _check(
            "ev_requires_probabilities",
            "EV abstains until explicit scenario probabilities are supplied",
            ev.get("status"),
            "EV_NOT_COMPUTABLE_MISSING_SCENARIO_PROBABILITIES",
        ),
        _check("no_support_probability", "Support score is never used as probability", guardrails.get("support_score_used_as_probability"), False),
        _check("no_fake_fed_path", "2Y Treasury is not treated as a Fed futures path", guardrails.get("fed_futures_path_inferred_from_treasury_yield"), False),
        _check("no_fake_security_pnl", "Underlying bp move is not called security P&L", guardrails.get("market_move_bp_called_security_pnl"), False),
        _check("no_position", "No position is issued before EV/risk budget", position.get("position"), "NONE"),
    ]
    return _case("r10-investment-numerical-pricing-ev-contract", checks)


def _gap_math_valid(target: dict, mispricing: dict) -> bool:
    if target.get("status") != "NUMERICAL_TARGET_AVAILABLE":
        return mispricing.get("gap_magnitude_pp") is None
    try:
        expected_pp = float(target["target_value"]) - float(mispricing["market_baseline"])
        actual_pp = float(mispricing["gap_magnitude_pp"])
        actual_bp = float(mispricing["gap_magnitude_bp"])
    except (KeyError, TypeError, ValueError):
        return False
    return isclose(actual_pp, expected_pp, rel_tol=0.0, abs_tol=1e-8) and isclose(
        actual_bp, expected_pp * 100.0, rel_tol=0.0, abs_tol=1e-6
    )


def _payoff_contract_valid(mispricing: dict, payoff: dict) -> bool:
    if mispricing.get("status") == "NUMERIC_GAP_AVAILABLE":
        rows = payoff.get("scenarios") or []
        return bool(
            payoff.get("status") == "STANDARDIZED_MARKET_MOVE_PAYOFF_TEMPLATE_AVAILABLE"
            and payoff.get("probabilities") == "NOT_ASSIGNED"
            and payoff.get("instrument_pnl_status") == "NOT_MODELED_REQUIRES_SENSITIVITY"
            and len(rows) == 3
            and all(row.get("probability") is None for row in rows)
        )
    return payoff.get("status") == "PAYOFF_TEMPLATE_UNAVAILABLE_NO_NUMERIC_GAP"


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
