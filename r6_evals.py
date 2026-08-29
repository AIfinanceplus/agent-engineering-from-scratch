"""R6 domain evals: blueprint safety, research quality, and decision-brief discipline."""

from __future__ import annotations

from r3_decomposition import build_blueprint


def make_r6_eval_suite(blueprint: dict, result: dict, domain: str) -> dict:
    cases = [
        _blueprint_case(blueprint),
        _research_case(blueprint, result),
        _domain_case(result, domain),
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
        _check("subquestion_query_1to1", "Every subquestion compiles to one source query", len(subquestions), len(queries)),
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
    return _case("r6-blueprint-query-contract", checks)


def _research_case(blueprint: dict, result: dict) -> dict:
    queries = blueprint.get("queries") or []
    plan = result.get("plan") or {}
    tasks = plan.get("tasks") or []
    task_ids = [item.get("task_id") for item in tasks]
    completed = [item.get("task_id") for item in tasks if item.get("status") == "completed"]
    evidence = result.get("evidence") or []
    citations = result.get("citations") or []
    results = result.get("results") or {}
    s1 = results.get("S1") or {}
    quality = s1.get("quality") or {}
    evidence_ids = {item.get("evidence_id") for item in evidence if item.get("evidence_id")}
    citation_ids = {item.get("evidence_id") for item in citations if item.get("evidence_id")}
    expected_tasks = [*[item.get("query_id") for item in queries], "S1", "D1"]

    checks = [
        _check("success", "R6 plan completes", bool(result.get("ok")) and plan.get("status") == "completed", True),
        _check("two_stage_dag", "Dynamic source tasks feed S1 then D1", task_ids, expected_tasks),
        _check("task_completion", "All R6 tasks complete", completed, expected_tasks),
        _check("evidence_count", "One Evidence record per compiled source query", len(evidence), len(queries)),
        _check("citation_grounding", "Final citations still resolve exactly to collected Evidence", citation_ids, evidence_ids),
        _check("s1_quality_coverage", "S1 assesses quality for every Evidence record", len(quality.get("evidence_quality") or []), len(evidence)),
        _check(
            "s1_not_probability",
            "S1 confidence remains a heuristic support score, not probability",
            s1.get("confidence_type"),
            "heuristic_support_score_not_probability",
        ),
        _check(
            "relation_contract",
            "S1 preserves agreement/mixed/contradiction relation categories",
            sorted((quality.get("relation_summary") or {}).keys()),
            ["agreement", "contradiction", "mixed_signal"],
        ),
    ]
    return _case("r6-research-quality-contract", checks)


def _domain_case(result: dict, domain: str) -> dict:
    results = result.get("results") or {}
    s1 = results.get("S1") or {}
    d1 = results.get("D1") or result.get("final_artifact") or {}
    sections = d1.get("sections") or {}
    guardrails = d1.get("guardrails") or {}
    relation_summary = ((s1.get("quality") or {}).get("relation_summary") or {})
    contradiction_count = int(relation_summary.get("contradiction", 0) or 0)

    common_sections = {
        "executive_summary",
        "counterevidence",
        "what_would_change_the_view",
        "monitoring_signals",
        "limitations",
    }
    domain_sections = (
        {"thesis", "market_channels", "base_case", "upside_inflation_scenario", "downside_inflation_scenario"}
        if domain == "investment"
        else {"policy_problem", "evidence_posture", "options", "tradeoffs"}
    )
    required_sections = common_sections | domain_sections
    scenario_weightings = _find_weightings(sections)

    checks = [
        _check("domain", "D1 uses the requested domain lens", d1.get("domain"), domain),
        _check("evidence_inheritance", "D1 cannot add or remove upstream Evidence IDs", d1.get("evidence_ids"), s1.get("evidence_ids")),
        _check(
            "confidence_noninflation",
            "D1 cannot increase upstream confidence",
            float(d1.get("confidence", 0.0)) <= float(s1.get("confidence", 0.0)),
            True,
        ),
        _check(
            "confidence_type",
            "D1 preserves non-probabilistic confidence semantics",
            d1.get("confidence_type"),
            "heuristic_support_score_not_probability",
        ),
        _check(
            "required_sections",
            "Domain brief exposes thesis/options, counterevidence, monitoring, and falsifiers",
            required_sections.issubset(set(sections.keys())),
            True,
        ),
        _check(
            "no_new_fetches",
            "D1 is a synthesis-only step and performs no new source fetch",
            guardrails.get("new_data_fetches"),
            0,
        ),
        _check(
            "qualitative_scenarios",
            "Scenario weighting is qualitative rather than fake probability",
            guardrails.get("scenario_weighting") == "qualitative_not_probability"
            and all(item == "qualitative" for item in scenario_weightings),
            True,
        ),
        _check(
            "counterevidence",
            "D1 explicitly carries counterevidence/disconfirming evidence",
            bool(d1.get("counterevidence")) and bool(sections.get("counterevidence")),
            True,
        ),
        _check(
            "monitoring",
            "D1 exposes monitoring signals tied to upstream Evidence IDs",
            {item.get("evidence_id") for item in d1.get("monitoring") or [] if item.get("evidence_id")}
            == set(d1.get("evidence_ids") or []),
            True,
        ),
        _check(
            "contradiction_blocks_action",
            "An unresolved same-claim contradiction cannot be marked research-ready",
            (d1.get("decision_status") == "RECONCILE_BEFORE_ACTION") if contradiction_count else True,
            True,
        ),
    ]
    return _case(f"r6-{domain}-decision-contract", checks)


def _find_weightings(value) -> list[str]:
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "weighting":
                rows.append(item)
            else:
                rows.extend(_find_weightings(item))
    elif isinstance(value, list):
        for item in value:
            rows.extend(_find_weightings(item))
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
