"""R12 Step 5 deterministic settlement-rules analysis.

The parser extracts review material from normalized Kalshi and Polymarket
contracts. It can block review when required material is absent, but it can never
approve event identity. Semantic equivalence remains an explicit human decision.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse


_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(?<![a-z0-9])[-+]?\d+(?:\.\d+)?%?", re.IGNORECASE)
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "if", "in",
    "is", "it", "of", "on", "or", "the", "to", "will", "with", "yes", "no",
}
_RISK_PATTERNS = {
    "void_or_cancellation": re.compile(r"\b(void|voided|cancel|cancelled|canceled|cancellation|invalid|invalidated)\b", re.I),
    "postponement_or_reschedule": re.compile(r"\b(postpone|postponed|postponement|reschedule|rescheduled|abandon|abandoned)\b", re.I),
    "revision_or_final_release": re.compile(r"\b(preliminary|final|revised|revision|corrected|restated)\b", re.I),
    "discretion_or_judgment": re.compile(r"\b(discretion|sole determination|judgment|determines?)\b", re.I),
    "early_close": re.compile(r"\b(early close|close early|early settlement|settle early)\b", re.I),
}


def analyze_settlement_rules(kalshi_contract: dict, polymarket_contract: dict) -> dict:
    """Extract and compare review facts without approving settlement identity."""
    _validate_contract(kalshi_contract, "kalshi")
    _validate_contract(polymarket_contract, "polymarket")

    extracted = {
        "kalshi": _extract_contract(kalshi_contract),
        "polymarket": _extract_contract(polymarket_contract),
    }
    checks = [
        _coverage_check(extracted),
        _resolution_source_check(extracted),
        _time_check(extracted),
        _measurement_check(extracted),
        _canonical_measurement_check(extracted),
        _edge_case_check(extracted),
        _lexical_check(extracted),
    ]

    blocking_findings = []
    for provider, row in extracted.items():
        if not row["completeness"]["has_rule_text"]:
            blocking_findings.append(f"{provider.upper()}_RULE_TEXT_REQUIRED")
        if not row["completeness"]["has_time_anchor"]:
            blocking_findings.append(f"{provider.upper()}_TIME_ANCHOR_REQUIRED")
    blocking_findings.extend(
        row["blocking_code"] for row in checks if isinstance(row.get("blocking_code"), str)
    )

    eligible = not blocking_findings
    if eligible:
        status = "RULES_ANALYSIS_READY_FOR_HUMAN_REVIEW"
    elif any(code.startswith("CANONICAL_") for code in blocking_findings):
        status = "RULES_ANALYSIS_BLOCKED_DETERMINISTIC_CONFLICT"
    else:
        status = "RULES_ANALYSIS_BLOCKED_INCOMPLETE"
    fingerprints = {
        "kalshi": settlement_contract_fingerprint(kalshi_contract),
        "polymarket": settlement_contract_fingerprint(polymarket_contract),
    }
    analysis_key = json.dumps(
        {
            "contracts": {
                "kalshi": kalshi_contract.get("provider_market_id"),
                "polymarket": polymarket_contract.get("provider_market_id"),
            },
            "fingerprints": fingerprints,
            "checks": checks,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    if eligible:
        recommended_next_step = "HUMAN_REVIEW_AND_EXPLICIT_IDENTITY_ATTESTATION"
    elif status == "RULES_ANALYSIS_BLOCKED_DETERMINISTIC_CONFLICT":
        recommended_next_step = "REJECT_PAIR_OR_CORRECT_CANONICAL_CONTRACT"
    else:
        recommended_next_step = "LOAD_COMPLETE_RULES_AND_RERUN_ANALYSIS"
    return {
        "artifact_type": "r12_settlement_rules_analysis",
        "analysis_id": "RULES-" + sha256(analysis_key.encode("utf-8")).hexdigest()[:16],
        "status": status,
        "contracts": {
            "kalshi": {
                "provider_market_id": kalshi_contract.get("provider_market_id"),
                "fingerprint": fingerprints["kalshi"],
            },
            "polymarket": {
                "provider_market_id": polymarket_contract.get("provider_market_id"),
                "fingerprint": fingerprints["polymarket"],
            },
        },
        "extracted": extracted,
        "comparison_checks": checks,
        "blocking_findings": blocking_findings,
        "difference_count": sum(
            1
            for row in checks
            if row["status"] in {"DIFFERENCE_REVIEW_REQUIRED", "POTENTIAL_CONFLICT", "DETERMINISTIC_CONFLICT"}
        ),
        "eligible_for_identity_review": eligible,
        "can_auto_approve_identity": False,
        "recommended_next_step": recommended_next_step,
        "guardrails": {
            "lexical_similarity_is_settlement_proof": False,
            "shared_source_domain_is_settlement_proof": False,
            "shared_date_is_settlement_proof": False,
            "parser_checks_attestation_boxes": False,
            "automatic_identity_approval": False,
            "automatic_execution": False,
        },
    }


def settlement_contract_fingerprint(contract: dict) -> str:
    """Fingerprint only identity-relevant contract fields, not volatile prices."""
    material = {
        "provider": contract.get("provider"),
        "provider_market_id": contract.get("provider_market_id"),
        "provider_event_id": contract.get("provider_event_id"),
        "question": contract.get("question"),
        "subtitle": contract.get("subtitle"),
        "description": contract.get("description"),
        "outcomes": contract.get("outcomes"),
        "resolution": contract.get("resolution"),
        "time_contract": contract.get("time_contract"),
        "measurement_contract": contract.get("measurement_contract"),
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def validate_rules_analysis_binding(analysis: dict | None, kalshi: dict, polymarket: dict) -> dict:
    """Return fail-closed binding checks for the identity gate."""
    artifact_valid = isinstance(analysis, dict) and analysis.get("artifact_type") == "r12_settlement_rules_analysis"
    expected = analyze_settlement_rules(kalshi, polymarket) if artifact_valid else None
    contracts = analysis.get("contracts") if artifact_valid else {}
    contracts = contracts if isinstance(contracts, dict) else {}
    ids_match = artifact_valid and all(
        ((contracts.get(provider) or {}).get("provider_market_id") == contract.get("provider_market_id"))
        for provider, contract in (("kalshi", kalshi), ("polymarket", polymarket))
    )
    fingerprints_current = artifact_valid and all(
        ((contracts.get(provider) or {}).get("fingerprint") == settlement_contract_fingerprint(contract))
        for provider, contract in (("kalshi", kalshi), ("polymarket", polymarket))
    )
    review_ready = artifact_valid and analysis.get("status") == "RULES_ANALYSIS_READY_FOR_HUMAN_REVIEW" and bool(
        analysis.get("eligible_for_identity_review")
    )
    no_auto_approval = artifact_valid and analysis.get("can_auto_approve_identity") is False
    matches_current_parser_output = artifact_valid and analysis == expected
    return {
        "analysis_present": analysis is not None,
        "artifact_valid": artifact_valid,
        "contract_ids_match": bool(ids_match),
        "fingerprints_current": bool(fingerprints_current),
        "ready_for_human_review": bool(review_ready),
        "parser_did_not_auto_approve": bool(no_auto_approval),
        "matches_current_parser_output": bool(matches_current_parser_output),
        "analysis_id": analysis.get("analysis_id") if artifact_valid else None,
        "all_pass": all(
            (
                artifact_valid,
                ids_match,
                fingerprints_current,
                review_ready,
                no_auto_approval,
                matches_current_parser_output,
            )
        ),
    }


def _extract_contract(contract: dict) -> dict:
    provider = contract["provider"]
    resolution = contract.get("resolution") or {}
    texts = _rule_texts(contract)
    combined = "\n".join(texts)
    sources = _source_refs(provider, resolution)
    times = _non_empty_items(contract.get("time_contract") or {})
    measurements = _non_empty_items(contract.get("measurement_contract") or {})
    risk_flags = {
        name: sorted({match.group(0).lower() for match in pattern.finditer(combined)})
        for name, pattern in _RISK_PATTERNS.items()
    }
    if provider == "kalshi" and resolution.get("early_close_condition"):
        risk_flags["early_close"] = sorted(set(risk_flags["early_close"] + ["structured_early_close_condition"]))
    return {
        "provider": provider,
        "provider_market_id": contract.get("provider_market_id"),
        "rule_texts": texts,
        "resolution_sources": sources,
        "time_anchors": times,
        "measurement_fields": measurements,
        "canonical_measurement": _canonical_measurement(measurements),
        "numeric_anchors": _numeric_anchors([*texts, *[str(value) for value in measurements.values()]]),
        "edge_case_flags": risk_flags,
        "semantic_tokens": sorted(_tokens(" ".join([str(contract.get("question") or ""), combined]))),
        "completeness": {
            "has_rule_text": bool(texts),
            "has_resolution_source": bool(sources),
            "has_time_anchor": bool(times),
            "has_measurement_fields": bool(measurements),
        },
    }


def _rule_texts(contract: dict) -> list[str]:
    resolution = contract.get("resolution") or {}
    if contract.get("provider") == "kalshi":
        candidates = [resolution.get("rules_primary"), resolution.get("rules_secondary"), resolution.get("early_close_condition")]
    else:
        candidates = [resolution.get("description"), contract.get("description")]
    texts = []
    seen = set()
    for value in candidates:
        if not isinstance(value, str):
            continue
        compact = " ".join(value.split())
        if compact and compact not in seen:
            seen.add(compact)
            texts.append(compact)
    return texts


def _source_refs(provider: str, resolution: dict) -> list[dict]:
    values = []
    if provider == "kalshi":
        for row in resolution.get("settlement_sources") or []:
            if isinstance(row, dict):
                values.extend((row.get("name"), row.get("url")))
        values.extend((resolution.get("contract_url"), resolution.get("contract_terms_url")))
    else:
        values.append(resolution.get("resolution_source"))
        values.extend(resolution.get("event_resolution_sources") or [])
    refs = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        raw = value.strip()
        parsed = urlparse(raw if "://" in raw else "")
        domain = parsed.hostname.lower().removeprefix("www.") if parsed.hostname else None
        canonical = domain or raw.casefold()
        if canonical in seen:
            continue
        seen.add(canonical)
        refs.append({"value": raw, "canonical_authority": canonical, "domain": domain})
    return refs


def _coverage_check(extracted: dict) -> dict:
    complete = all(row["completeness"]["has_rule_text"] for row in extracted.values())
    return _check("rule_text_coverage", "PRESENT_BOTH" if complete else "INCOMPLETE", {
        provider: row["completeness"]["has_rule_text"] for provider, row in extracted.items()
    }, probability=False)


def _resolution_source_check(extracted: dict) -> dict:
    values = {
        provider: {row["canonical_authority"] for row in data["resolution_sources"]}
        for provider, data in extracted.items()
    }
    if not all(values.values()):
        status = "INCOMPLETE"
    elif values["kalshi"] & values["polymarket"]:
        status = "SHARED_AUTHORITY_REVIEW_DETAILS"
    else:
        status = "DIFFERENCE_REVIEW_REQUIRED"
    return _check("resolution_authority", status, {key: sorted(value) for key, value in values.items()}, probability=False)


def _time_check(extracted: dict) -> dict:
    raw = {provider: list(data["time_anchors"].values()) for provider, data in extracted.items()}
    parsed = {provider: {_parse_time(value) for value in values} - {None} for provider, values in raw.items()}
    dates = {provider: {value.date().isoformat() for value in values} for provider, values in parsed.items()}
    if not all(raw.values()):
        status = "INCOMPLETE"
    elif parsed["kalshi"] & parsed["polymarket"]:
        status = "EXACT_TIME_ANCHOR_SHARED_REVIEW_SEMANTICS"
    elif dates["kalshi"] & dates["polymarket"]:
        status = "SHARED_CALENDAR_DATE_REVIEW_TIME_SEMANTICS"
    else:
        status = "DIFFERENCE_REVIEW_REQUIRED"
    return _check("resolution_horizon", status, {"raw": raw, "parsed_dates": {key: sorted(value) for key, value in dates.items()}}, probability=False)


def _measurement_check(extracted: dict) -> dict:
    values = {provider: set(data["numeric_anchors"]) for provider, data in extracted.items()}
    if not all(values.values()):
        status = "INCOMPLETE"
    elif values["kalshi"] & values["polymarket"]:
        status = "SHARED_NUMERIC_ANCHOR_REVIEW_MEASUREMENT_SEMANTICS"
    else:
        status = "POTENTIAL_CONFLICT"
    return _check("measurement_definition", status, {key: sorted(value) for key, value in values.items()}, probability=False)


def _canonical_measurement_check(extracted: dict) -> dict:
    values = {provider: data["canonical_measurement"] for provider, data in extracted.items()}
    if not all(values.values()):
        status = "NOT_AVAILABLE_REVIEW_RAW_MEASUREMENT"
        blocking_code = None
    elif values["kalshi"] == values["polymarket"]:
        status = "EXACT_CANONICAL_MATCH_STILL_REQUIRES_HUMAN_REVIEW"
        blocking_code = None
    else:
        status = "DETERMINISTIC_CONFLICT"
        blocking_code = "CANONICAL_MEASUREMENT_CONFLICT"
    row = _check("canonical_measurement_contract", status, values, probability=False)
    row["blocking_code"] = blocking_code
    return row


def _edge_case_check(extracted: dict) -> dict:
    present = {
        provider: sorted(name for name, matches in data["edge_case_flags"].items() if matches)
        for provider, data in extracted.items()
    }
    status = "SAME_FLAG_CATEGORIES_REVIEW_TEXT" if set(present["kalshi"]) == set(present["polymarket"]) else "DIFFERENCE_REVIEW_REQUIRED"
    return _check("edge_case_clauses", status, present, probability=False)


def _lexical_check(extracted: dict) -> dict:
    left = set(extracted["kalshi"]["semantic_tokens"])
    right = set(extracted["polymarket"]["semantic_tokens"])
    union = left | right
    score = round(len(left & right) / len(union), 4) if union else 0.0
    return _check("lexical_event_overlap", "HEURISTIC_ONLY_NOT_IDENTITY_PROOF", {"jaccard": score, "shared_tokens": sorted(left & right)}, probability=False)


def _check(name: str, status: str, observed: dict, *, probability: bool) -> dict:
    return {
        "check": name,
        "status": status,
        "observed": observed,
        "is_probability": probability,
        "can_approve_identity": False,
    }


def _numeric_anchors(values: list[str]) -> list[str]:
    found = set()
    for value in values:
        for match in _NUMBER_RE.findall(value):
            found.add(match.lstrip("+"))
    return sorted(found)


def _canonical_measurement(measurement: dict) -> dict | None:
    keys = ("canonical_metric", "canonical_operator", "canonical_threshold", "canonical_unit")
    if not all(key in measurement and measurement[key] not in (None, "") for key in keys):
        return None
    return {
        "metric": str(measurement["canonical_metric"]).strip().casefold(),
        "operator": str(measurement["canonical_operator"]).strip().casefold(),
        "threshold": str(measurement["canonical_threshold"]).strip().casefold(),
        "unit": str(measurement["canonical_unit"]).strip().casefold(),
    }


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(value) if token.casefold() not in _STOPWORDS}


def _non_empty_items(value: dict) -> dict:
    # Artifact output and analysis_id must not depend on provider dictionary
    # insertion order. Durable JSON stores commonly sort object keys.
    return {
        str(key): item
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        if item is not None and item != ""
    }


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _validate_contract(contract: dict, provider: str) -> None:
    if not isinstance(contract, dict) or contract.get("artifact_type") != "r12_market_contract":
        raise ValueError(f"{provider}_contract must be an r12_market_contract")
    if contract.get("provider") != provider:
        raise ValueError(f"expected provider={provider}")
