"""R5 evals extend R3 execution contracts with quality/relation checks."""

from __future__ import annotations

from r3_evals import make_r3_eval_suite


def make_r5_eval_suite(blueprint: dict, result: dict) -> dict:
    base = make_r3_eval_suite(blueprint, result)
    quality_case = _quality_case(result)
    cases = [*base["cases"], quality_case]
    passed = sum(1 for case in cases if case["report"]["passed"])
    return {
        "passed": passed,
        "total": len(cases),
        "pass_rate": round(passed / len(cases), 3) if cases else 1.0,
        "cases": cases,
    }


def _quality_case(result: dict) -> dict:
    artifact = result.get("final_artifact") or {}
    evidence = result.get("evidence") or []
    quality = artifact.get("quality") or {}
    rows = quality.get("evidence_quality") or []
    relation_summary = quality.get("relation_summary") or {}
    score_type = artifact.get("confidence_type")
    support_score = quality.get("support_score")

    checks = [
        _check(
            "quality_coverage",
            "Every collected Evidence record has a quality assessment",
            len(rows),
            len(evidence),
        ),
        _check(
            "support_score_contract",
            "Synthesis confidence is the explicit heuristic support score",
            artifact.get("confidence") == support_score,
            True,
        ),
        _check(
            "not_probability",
            "Support score is explicitly marked as non-probabilistic",
            score_type,
            "heuristic_support_score_not_probability",
        ),
        _check(
            "relation_contract",
            "Relation summary distinguishes agreement, mixed signal, and contradiction",
            sorted(relation_summary.keys()),
            ["agreement", "contradiction", "mixed_signal"],
        ),
        _check(
            "quality_dimensions",
            "Each Evidence quality row exposes all four scoring dimensions",
            all(
                set((row.get("dimensions") or {}).keys())
                == {"authority", "freshness", "completeness", "relevance"}
                for row in rows
            ),
            True,
        ),
        _check(
            "contradiction_guardrail",
            "A contradiction adds a stronger or equal penalty than mixed-signal uncertainty",
            float((quality.get("penalties") or {}).get("contradiction", 0.0))
            >= float((quality.get("penalties") or {}).get("mixed_signal", 0.0)),
            True,
        ),
    ]
    return _case("r5-evidence-quality-relation-contract", checks)


def _case(case_id: str, checks: list[dict]) -> dict:
    passed = all(check["passed"] for check in checks)
    failures = [check["failure"] for check in checks if not check["passed"]]
    return {
        "case": {"case_id": case_id},
        "report": {
            "case_id": case_id,
            "passed": passed,
            "checks": checks,
            "failures": failures,
        },
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
