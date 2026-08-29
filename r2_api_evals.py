"""Structural evals for the API-only R2 research run.

Interactive evals use the same live API result as the research workbench and
score explicit contracts. Unit tests can score a supplied result without network
access.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class APIEvalCase:
    case_id: str
    expected_tasks: tuple[str, ...] = ("H1", "C1", "F1", "G1", "A1")
    expected_providers: tuple[str, ...] = ("BLS", "FRED", "EIA")
    expected_evidence_count: int = 4
    expected_citation_count: int = 4
    expected_tool_attempts: int = 5


def score_api_result(case: APIEvalCase, result: dict) -> dict:
    plan = result.get("plan") or {}
    tasks = plan.get("tasks") or []
    task_ids = [task.get("task_id") for task in tasks]
    completed = [task.get("task_id") for task in tasks if task.get("status") == "completed"]
    evidence = result.get("evidence") or []
    citations = result.get("citations") or []
    artifact = result.get("final_artifact") or {}
    trace = result.get("trace") or {}
    metrics = trace.get("metrics") or {}

    providers = sorted({item.get("provider") for item in evidence if item.get("provider")})
    evidence_ids = {item.get("evidence_id") for item in evidence if item.get("evidence_id")}
    cited_ids = {item.get("evidence_id") for item in citations if item.get("evidence_id")}
    freshness = artifact.get("freshness") or {} if isinstance(artifact, dict) else {}
    limitations = artifact.get("limitations") or [] if isinstance(artifact, dict) else []
    limitation_text = " ".join(str(item).lower() for item in limitations)

    checks = [
        _check("success", "Plan completed", bool(result.get("ok")) and plan.get("status") == "completed", True),
        _check("task_contract", "H1/C1/F1/G1/A1 task contract", task_ids, list(case.expected_tasks)),
        _check("task_completion", "All API tasks completed", completed, list(case.expected_tasks)),
        _check("evidence_count", "Four source Evidence records", len(evidence), case.expected_evidence_count),
        _check("provider_coverage", "BLS/FRED/EIA coverage", providers, sorted(case.expected_providers)),
        _check("citation_count", "Four citations emitted", len(citations), case.expected_citation_count),
        _check("citations_grounded", "Every citation maps to collected Evidence", cited_ids.issubset(evidence_ids) and len(cited_ids) == case.expected_citation_count, True),
        _check("freshness", "Freshness computed for every Evidence record", set(freshness) == evidence_ids, True),
        _check("tool_attempts", "Expected Tool attempts", int(metrics.get("tool_attempts", 0)), case.expected_tool_attempts),
        _check("causal_guardrail", "Analysis labels signals as descriptive, not causal attribution", "not causal" in str(artifact.get("answer", "")).lower() or "not causal" in limitation_text, True),
    ]
    passed = all(check["passed"] for check in checks)
    return {
        "case_id": case.case_id,
        "passed": passed,
        "checks": checks,
        "failures": [check["failure"] for check in checks if not check["passed"]],
    }


def build_eval_process(case: APIEvalCase, result: dict, report: dict) -> list[dict]:
    plan = result.get("plan") or {}
    artifact = result.get("final_artifact") or {}
    process = [
        {
            "type": "eval_case_started",
            "case_id": case.case_id,
            "expectations": {
                "tasks": list(case.expected_tasks),
                "providers": list(case.expected_providers),
                "evidence_count": case.expected_evidence_count,
                "citation_count": case.expected_citation_count,
                "tool_attempts": case.expected_tool_attempts,
            },
        },
        {
            "type": "eval_agent_run_completed",
            "case_id": case.case_id,
            "run_summary": {
                "ok": result.get("ok"),
                "plan_status": plan.get("status"),
                "task_ids": [task.get("task_id") for task in plan.get("tasks") or []],
                "evidence_ids": [item.get("evidence_id") for item in result.get("evidence") or []],
                "citations": [item.get("citation") for item in result.get("citations") or []],
                "signals": artifact.get("signals") if isinstance(artifact, dict) else None,
            },
        },
    ]
    process.extend({"type": "eval_check", "case_id": case.case_id, **check} for check in report["checks"])
    process.append({"type": "eval_case_verdict", "case_id": case.case_id, "passed": report["passed"], "failures": report["failures"]})
    return process


def make_api_eval_suite(result: dict) -> dict:
    cases = (
        APIEvalCase(case_id="api-source-lineage"),
        APIEvalCase(case_id="api-freshness-citations"),
    )
    entries = []
    for case in cases:
        report = score_api_result(case, result)
        entries.append({
            "case": {"case_id": case.case_id, "expected_tasks": list(case.expected_tasks)},
            "report": report,
            "process": build_eval_process(case, result, report),
        })
    passed = sum(entry["report"]["passed"] for entry in entries)
    return {
        "passed": passed,
        "total": len(entries),
        "pass_rate": round(passed / len(entries), 3) if entries else 1.0,
        "shared_live_run": True,
        "cases": entries,
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
