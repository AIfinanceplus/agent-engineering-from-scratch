"""R7 evals: research lineage, domain discipline, and falsifiable forecast contracts."""

from __future__ import annotations

import re
from datetime import date

from r3_decomposition import build_blueprint


PACK_ID_RE = re.compile(r"^FP-[A-F0-9]{12}$")
REQUIRED_SCENARIOS = {
    "UPSIDE_INFLATION",
    "DOWNSIDE_INFLATION",
    "MIXED",
    "RECONCILE",
    "STABLE",
    "UNRESOLVED",
}


def make_r7_eval_suite(blueprint: dict, result: dict, domain: str) -> dict:
    cases = [
        _blueprint_case(blueprint),
        _research_case(blueprint, result),
        _domain_case(result, domain),
        _forecast_case(result),
    ]
    passed = sum(1 for case in cases if case["report"]["passed"])
    return {
        "passed": passed,
        "total": len(cases),
        "pass_rate": round(passed / len(cases), 3) if cases else 1.0,
        "cases": cases,
    }


def _blueprint_case(blueprint: dict) -> dict:
    subquestions = blueprint.get("subquestions") or []
    queries = blueprint.get("queries") or []
    unsafe = []
    for query in queries:
        for key in (query.get("arguments") or {}):
            if key.lower() in {"api_key", "url", "endpoint", "token", "secret"}:
                unsafe.append(f"{query.get('query_id')}:{key}")
    narrow = build_blueprint("Compare headline and core CPI.").to_dict()
    checks = [
        _check("subquestion_query_1to1", "Every subquestion compiles to one query", len(subquestions), len(queries)),
        _check(
            "capability_alignment",
            "Compiled capabilities match decomposed capabilities",
            [item.get("capability") for item in queries],
            [item.get("capability") for item in subquestions],
        ),
        _check("safe_query_fields", "Source queries contain no secret/URL fields", unsafe, []),
        _check(
            "approved_providers",
            "All source queries use approved providers",
            all(item.get("provider") in {"BLS", "FRED", "EIA"} for item in queries),
            True,
        ),
        _check(
            "narrow_pruning",
            "Headline/core-only question still prunes unrelated sources",
            [item.get("capability") for item in narrow.get("queries") or []],
            ["headline_cpi", "core_cpi"],
        ),
    ]
    return _case("r7-blueprint-query-contract", checks)


def _research_case(blueprint: dict, result: dict) -> dict:
    queries = blueprint.get("queries") or []
    tasks = (result.get("plan") or {}).get("tasks") or []
    task_ids = [item.get("task_id") for item in tasks]
    completed = [item.get("task_id") for item in tasks if item.get("status") == "completed"]
    expected = [*[item.get("query_id") for item in queries], "S1", "D1", "F1"]
    evidence = result.get("evidence") or []
    citations = result.get("citations") or []
    results = result.get("results") or {}
    s1 = results.get("S1") or {}
    quality = s1.get("quality") or {}
    evidence_ids = {item.get("evidence_id") for item in evidence if item.get("evidence_id")}
    citation_ids = {item.get("evidence_id") for item in citations if item.get("evidence_id")}

    checks = [
        _check("success", "R7 plan completes", bool(result.get("ok")) and (result.get("plan") or {}).get("status") == "completed", True),
        _check("four_stage_dag", "Queries feed S1 then D1 then F1", task_ids, expected),
        _check("task_completion", "All R7 tasks complete", completed, expected),
        _check("evidence_count", "One Evidence record per source query", len(evidence), len(queries)),
        _check("citation_grounding", "Final citations resolve exactly to collected Evidence", citation_ids, evidence_ids),
        _check("s1_quality_coverage", "S1 assesses every Evidence record", len(quality.get("evidence_quality") or []), len(evidence)),
        _check(
            "s1_not_probability",
            "S1 confidence remains heuristic support, not probability",
            s1.get("confidence_type"),
            "heuristic_support_score_not_probability",
        ),
    ]
    return _case("r7-research-lineage-contract", checks)


def _domain_case(result: dict, domain: str) -> dict:
    results = result.get("results") or {}
    s1 = results.get("S1") or {}
    d1 = results.get("D1") or {}
    guardrails = d1.get("guardrails") or {}
    checks = [
        _check("domain", "D1 uses the requested domain", d1.get("domain"), domain),
        _check("evidence_inheritance", "D1 inherits S1 Evidence IDs", d1.get("evidence_ids"), s1.get("evidence_ids")),
        _check(
            "confidence_noninflation",
            "D1 cannot increase S1 confidence",
            float(d1.get("confidence", 0.0)) <= float(s1.get("confidence", 0.0)),
            True,
        ),
        _check("no_domain_fetch", "D1 performs no new source fetch", guardrails.get("new_data_fetches"), 0),
        _check(
            "qualitative_scenarios",
            "D1 scenario framing is explicitly non-probabilistic",
            guardrails.get("scenario_weighting"),
            "qualitative_not_probability",
        ),
    ]
    return _case(f"r7-{domain}-domain-contract", checks)


def _forecast_case(result: dict) -> dict:
    results = result.get("results") or {}
    s1 = results.get("S1") or {}
    d1 = results.get("D1") or {}
    f1 = results.get("F1") or result.get("final_artifact") or {}
    forecasts = f1.get("forecasts") or []
    guardrails = f1.get("guardrails") or {}
    scenario = f1.get("scenario_tracker") or {}
    definitions = {item.get("state") for item in scenario.get("definitions") or [] if item.get("state")}
    upstream_ids = set(s1.get("evidence_ids") or [])
    contradicted_ids = _contradicted_ids((s1.get("quality") or {}).get("relations") or [])

    open_rows = [item for item in forecasts if item.get("status") == "OPEN"]
    abstained_rows = [item for item in forecasts if item.get("status") == "ABSTAINED"]
    required_fields = {
        "forecast_id",
        "status",
        "target_evidence_id",
        "provider",
        "target_metric",
        "baseline_metric_value",
        "baseline_as_of",
        "created_at",
        "horizon_days",
        "due_date",
        "method",
        "support_score",
        "support_score_type",
        "evidence_ids",
        "claim",
        "invalidation_rule",
    }

    contract_rows_ok = all(required_fields.issubset(set(item.keys())) for item in forecasts)
    open_rows_ok = all(
        item.get("expected_direction") in {"rising", "falling", "flat"}
        and item.get("baseline_metric_value") is not None
        and date.fromisoformat(item["due_date"]) > date.fromisoformat(item["created_at"])
        and set(item.get("evidence_ids") or []).issubset(upstream_ids)
        for item in open_rows
    )
    abstention_ok = all(bool(item.get("abstain_reason")) for item in abstained_rows)
    contradiction_abstention = all(
        item.get("status") == "ABSTAINED"
        for item in forecasts
        if item.get("target_evidence_id") in contradicted_ids
    )

    checks = [
        _check("artifact_type", "F1 returns a forecast pack", f1.get("artifact_type"), "forecast_pack"),
        _check("pack_id", "Forecast pack has a stable safe identifier", bool(PACK_ID_RE.match(str(f1.get("pack_id") or ""))), True),
        _check("evidence_inheritance", "F1 cannot add or remove upstream Evidence IDs", f1.get("evidence_ids"), s1.get("evidence_ids")),
        _check(
            "confidence_noninflation",
            "F1 cannot increase D1/S1 confidence",
            float(f1.get("confidence", 0.0)) <= min(float(s1.get("confidence", 0.0)), float(d1.get("confidence", 0.0))),
            True,
        ),
        _check("forecast_contract_fields", "Every forecast is explicitly settleable or abstained", contract_rows_ok, True),
        _check("open_forecast_contract", "OPEN forecasts have baseline, horizon, direction, and grounded Evidence", open_rows_ok, True),
        _check("abstention_contract", "ABSTAINED forecasts explain why no forecast was issued", abstention_ok, True),
        _check("contradiction_abstains", "Same-claim contradiction cannot silently become a forecast", contradiction_abstention, True),
        _check("scenario_states", "Scenario tracker exposes explicit state triggers", REQUIRED_SCENARIOS.issubset(definitions), True),
        _check("no_new_fetches", "F1 performs no source fetch", guardrails.get("new_data_fetches"), 0),
        _check("no_new_evidence", "F1 invents no new Evidence IDs", guardrails.get("new_evidence_ids"), 0),
        _check("no_probability", "F1 does not fabricate forecast probability", guardrails.get("forecast_probability"), "not_provided"),
        _check(
            "score_semantics",
            "Historical forecast accuracy is not represented as a probability",
            (f1.get("scoreboard") or {}).get("accuracy_type"),
            "historical_direction_hit_rate_not_probability",
        ),
    ]
    return _case("r7-forecast-tracking-contract", checks)


def _contradicted_ids(relations: list[dict]) -> set[str]:
    rows: set[str] = set()
    for relation in relations:
        if isinstance(relation, dict) and relation.get("relation") == "CONTRADICTION":
            rows.update(item for item in relation.get("evidence_ids") or [] if isinstance(item, str))
    return rows


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
