"""Prompt-injection boundary for retrieved rate evidence.

Retrieved text is data, never authority.  This deterministic teaching guard
quarantines whole chunks that contain instruction-like control language, then
re-checks required evidence coverage before anything can enter CT1.
"""

from dataclasses import dataclass
import re


INJECTION_RULES = (
    ("instruction_override", re.compile(r"\b(ignore|disregard|override)\b.{0,40}\b(instruction|policy|rule)s?\b", re.I)),
    ("secret_exfiltration", re.compile(r"\b(reveal|print|return|send)\b.{0,40}\b(secret|token|api[ -]?key|system prompt)s?\b", re.I)),
    ("unauthorized_tool_request", re.compile(r"\b(call|invoke|execute|run)\b.{0,35}\b(tool|shell|command|order)s?\b", re.I)),
    ("authority_impersonation", re.compile(r"\b(system|developer)\s+(message|instruction)\b", re.I)),
)


class PromptInjectionBlocked(RuntimeError):
    def __init__(self, message, *, decisions, missing_series):
        self.decisions = list(decisions)
        self.missing_series = list(missing_series)
        super().__init__(message)


@dataclass(frozen=True)
class TaintDecision:
    chunk_id: str
    citation_id: str
    tainted: bool
    matched_rules: tuple[str, ...]
    action: str
    content_preview: str

    def public_record(self):
        return {
            "chunk_id": self.chunk_id,
            "citation_id": self.citation_id,
            "tainted": self.tainted,
            "matched_rules": list(self.matched_rules),
            "action": self.action,
            "content_preview": self.content_preview,
        }


class RetrievedContentGuard:
    """Treat all retrieved chunks as tainted until inspected and promoted."""

    def __init__(self, required_series=("DGS2", "DGS10")):
        self.required_series = tuple(required_series)

    def inspect(self, verified_evidence):
        decisions, promoted, quarantined = [], [], []
        for chunk in verified_evidence.get("accepted", []):
            matched = tuple(name for name, pattern in INJECTION_RULES
                            if pattern.search(chunk.get("text", "")))
            tainted = bool(matched)
            decision = TaintDecision(
                chunk_id=chunk["chunk_id"],
                citation_id=chunk["citation_id"],
                tainted=tainted,
                matched_rules=matched,
                action="QUARANTINE" if tainted else "PROMOTE_AS_DATA",
                content_preview=chunk["text"],
            ).public_record()
            decisions.append(decision)
            (quarantined if tainted else promoted).append(chunk)

        coverage = sorted({series for chunk in promoted for series in chunk.get("series", [])
                           if series in self.required_series})
        missing = sorted(set(self.required_series) - set(coverage))
        if missing:
            raise PromptInjectionBlocked(
                f"safe evidence missing coverage for {', '.join(missing)} after quarantine",
                decisions=decisions,
                missing_series=missing,
            )
        return {
            "artifact_type": "trusted_retrieved_data",
            "passed": True,
            "required_series": list(self.required_series),
            "coverage": coverage,
            "promoted": promoted,
            "quarantined": quarantined,
            "decisions": decisions,
            "policy": "retrieved_text_is_data_never_instructions",
        }


def prompt_security_snapshot(result):
    return {
        "policy": result["policy"],
        "coverage": result["coverage"],
        "promoted_citation_ids": [chunk["citation_id"] for chunk in result["promoted"]],
        "quarantined_citation_ids": [chunk["citation_id"] for chunk in result["quarantined"]],
        "detector": "deterministic_instruction_pattern_guard",
        "llm_judge": False,
    }
