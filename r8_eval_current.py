"""Evaluate an already-completed R8 run without re-running research or fetching sources.

This module exists to keep the conceptual boundary explicit:

    Trace/Run artifact = what happened in one execution
    Eval               = judge that existing artifact against contracts

Evaluation must not create a second research run merely to score the first one.
"""

from __future__ import annotations

from r8_evals import make_r8_eval_suite


def evaluate_current_run(research_result: dict) -> dict:
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

    suite = make_r8_eval_suite(blueprint, research_result, domain)
    return {
        "ok": True,
        "action": "r8_eval_current",
        "run_id": research_result["run_id"],
        "domain": domain,
        "evaluation_mode": "existing_run_no_source_fetch",
        "research_result": research_result,
        "eval_suite": suite,
    }
