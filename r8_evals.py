"""R8 evals: preserve R7 lineage/forecast contracts and score professional D1 discipline."""

from __future__ import annotations

from r7_evals import make_r7_eval_suite


def make_r8_eval_suite(blueprint: dict, result: dict, domain: str) -> dict:
    base = make_r7_eval_suite(blueprint, result, domain)
    professional = _professional_case(result, domain)
    cases = [*base.get("cases", []), professional]
    passed = sum(1 for case in cases if case["report"]["passed"])
    return {
        "passed": passed,
        "total": len(cases),
        "pass_rate": round(passed / len(cases), 3) if cases else 1.0,
        "cases": cases,
    }


def _professional_case(result: dict, domain: str) -> dict:
    results = result.get("results") or {}
    s1 = results.get("S1") or {}
    d1 = results.get("D1") or {}
    sections = d1.get("sections") or {}
    guardrails = d1.get("guardrails") or {}

    common = [
        _check("r8_version", "D1 uses the R8 professional decision framework", d1.get("decision_framework_version"), "R8"),
        _check("domain", "Professional D1 matches requested domain", d1.get("domain"), domain),
        _check("evidence_exact", "Professional lens cannot change S1 Evidence IDs", d1.get("evidence_ids"), s1.get("evidence_ids")),
        _check(
            "confidence_noninflation",
            "Professional lens cannot increase S1 confidence",
            float(d1.get("confidence", 0.0)) <= float(s1.get("confidence", 0.0)),
            True,
        ),
        _check("no_query_mutation", "Professional lens cannot change upstream query selection", guardrails.get("professional_lens_changes_upstream_queries"), False),
    ]

    if domain == "investment":
        market = sections.get("market_pricing") or {}
        ev = sections.get("expected_value") or {}
        position = sections.get("position_framework") or {}
        checks = [
            *common,
            _check("brief_type", "Investment D1 uses professional investment schema", sections.get("brief_type"), "investment_professional_decision_brief"),
            _check("pricing_guardrail", "No asset-pricing gap is fabricated", market.get("status"), "PRICING_NOT_MODELED"),
            _check("ev_guardrail", "Expected value is withheld without probabilities/payoffs", ev.get("status"), "EV_NOT_COMPUTABLE"),
            _check("no_position", "No position is issued without a measurable pricing gap", position.get("position"), "NONE"),
            _check("no_pricing_fabrication", "Market-pricing fabrication is forbidden", guardrails.get("market_pricing_fabrication"), "forbidden"),
            _check("no_ev_fabrication", "EV fabrication is forbidden", guardrails.get("expected_value_without_probability_and_payoff"), "forbidden"),
        ]
    else:
        counterfactual = sections.get("counterfactual_analysis") or {}
        distribution = sections.get("distributional_analysis") or {}
        implementation = sections.get("implementation") or {}
        actionability = sections.get("policy_actionability") or {}
        checks = [
            *common,
            _check("brief_type", "Policy D1 uses professional policy schema", sections.get("brief_type"), "policy_professional_decision_brief"),
            _check("counterfactual_guardrail", "Causal counterfactual effects are not fabricated", counterfactual.get("status"), "COUNTERFACTUAL_EFFECTS_NOT_ESTIMATED"),
            _check("distribution_guardrail", "Distributional incidence is not fabricated", distribution.get("status"), "INCIDENCE_NOT_MODELED"),
            _check("implementation_guardrail", "Policy directive waits for implementation analysis", implementation.get("status"), "NOT_READY_FOR_DIRECTIVE"),
            _check("monitor_only", "Current descriptive bundle remains monitor-only", actionability.get("current_action"), "MONITOR_AND_UPDATE_EVIDENCE"),
            _check("no_causal_fabrication", "Causal policy-effect fabrication is forbidden", guardrails.get("causal_policy_effect_without_causal_evidence"), "forbidden"),
            _check("no_incidence_fabrication", "Distributional fabrication is forbidden", guardrails.get("distributional_claim_without_incidence_evidence"), "forbidden"),
        ]

    return _case(f"r8-{domain}-professional-decision-contract", checks)


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
