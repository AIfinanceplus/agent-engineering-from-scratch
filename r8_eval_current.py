"""Evaluate an existing R8/R9 run without re-running research or fetching sources."""

from __future__ import annotations

from r8_evals import make_r8_eval_suite


def evaluate_current_run(research_result: dict, eval_factory=None) -> dict:
    if not isinstance(research_result, dict):
        raise ValueError("research_result must be an object")
    if not research_result.get("run_id"):
        raise ValueError("research_result must contain run_id")
    blueprint = research_result.get("blueprint")
    if not isinstance(blueprint, dict) or not blueprint.get("queries"):
        raise ValueError("research_result must contain a compiled blueprint")
    domain = research_result.get("domain")
    if domain not in {"investment", "policy"}:
        raise ValueError("research_result domain must be investment or policy")

    factory = eval_factory or make_r8_eval_suite
    suite = factory(blueprint, research_result, domain)
    return {
        "ok": True,
        "action": "r8_eval_current",
        "run_id": research_result["run_id"],
        "domain": domain,
        "evaluation_mode": "existing_run_no_source_fetch",
        "research_result": research_result,
        "eval_suite": suite,
        "evaluated_artifact": {
            "plan_status": (research_result.get("plan") or {}).get("status"),
            "evidence_count": len(research_result.get("evidence") or []),
            "checkpoint_count": len(research_result.get("checkpoints") or []),
        },
    }
