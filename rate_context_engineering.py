"""Deterministic context selection, compression and conflict handling for teaching.

This module models *model input context*.  It is intentionally separate from
``ExecutionContext`` (trusted identity) and from durable agent checkpoints.
The token counts are disclosed teaching units, not tokenizer or billing data.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextItem:
    item_id: str
    source: str
    text: str
    tokens: int
    relevance: float
    authority: float
    freshness: float
    mandatory: bool = False
    conflict_key: str | None = None
    compressed_text: str | None = None
    compressed_tokens: int | None = None

    def __post_init__(self):
        if not self.item_id or not self.source or not self.text:
            raise ValueError("context identity, source and text must be non-empty")
        if isinstance(self.tokens, bool) or not isinstance(self.tokens, int) or self.tokens < 1:
            raise ValueError("context tokens must be a positive integer")
        for name in ("relevance", "authority", "freshness"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if (self.compressed_text is None) != (self.compressed_tokens is None):
            raise ValueError("compressed text and tokens must be declared together")
        if self.compressed_tokens is not None and not 0 < self.compressed_tokens < self.tokens:
            raise ValueError("compressed tokens must be positive and smaller than full tokens")

    @property
    def score(self):
        return round(self.relevance * 0.5 + self.authority * 0.3 + self.freshness * 0.2, 3)


class ContextBudgetExceeded(RuntimeError):
    """Mandatory context alone cannot fit; do not silently remove policy."""


class ContextBuilder:
    """Build a finite model-input pack from explicitly attributed candidates."""

    def __init__(self, max_tokens):
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise ValueError("max_tokens must be a positive integer")
        self.max_tokens = max_tokens

    def build(self, candidates):
        candidates = tuple(candidates)
        if not candidates:
            raise ValueError("context candidates must not be empty")
        if len({item.item_id for item in candidates}) != len(candidates):
            raise ValueError("context item IDs must be unique")

        superseded = {}
        conflict_groups = {}
        for item in candidates:
            if item.conflict_key:
                conflict_groups.setdefault(item.conflict_key, []).append(item)
        for key, items in conflict_groups.items():
            winner = max(items, key=lambda item: (item.authority, item.freshness, item.relevance, item.item_id))
            for item in items:
                if item is not winner:
                    superseded[item.item_id] = {
                        "reason": "superseded_by_fresher_authoritative_context",
                        "conflict_key": key,
                        "winner": winner.item_id,
                    }

        decisions = []
        selected = []
        used = 0
        # Python's stable sort preserves declared order for equal-priority items,
        # so system policy remains ahead of the current user goal in the prompt.
        ordered = sorted(candidates, key=lambda item: (not item.mandatory, -item.score))
        for item in ordered:
            base = {
                "item_id": item.item_id,
                "source": item.source,
                "score": item.score,
                "relevance": item.relevance,
                "authority": item.authority,
                "freshness": item.freshness,
                "mandatory": item.mandatory,
                "full_tokens": item.tokens,
            }
            if item.item_id in superseded:
                decisions.append({**base, "decision": "dropped", **superseded[item.item_id]})
                continue
            if not item.mandatory and item.relevance < 0.5:
                decisions.append({**base, "decision": "dropped", "reason": "low_relevance"})
                continue
            remaining = self.max_tokens - used
            if item.tokens <= remaining:
                selected.append({"item_id": item.item_id, "source": item.source,
                                 "text": item.text, "tokens": item.tokens, "mode": "full"})
                used += item.tokens
                decisions.append({**base, "decision": "selected", "mode": "full",
                                  "used_tokens": item.tokens, "remaining_tokens": self.max_tokens - used})
                continue
            if item.compressed_text is not None and item.compressed_tokens <= remaining:
                selected.append({"item_id": item.item_id, "source": item.source,
                                 "text": item.compressed_text, "tokens": item.compressed_tokens,
                                 "mode": "compressed"})
                used += item.compressed_tokens
                decisions.append({**base, "decision": "compressed", "mode": "compressed",
                                  "used_tokens": item.compressed_tokens,
                                  "released_tokens": item.tokens - item.compressed_tokens,
                                  "remaining_tokens": self.max_tokens - used})
                continue
            if item.mandatory:
                raise ContextBudgetExceeded(
                    f"mandatory context {item.item_id} needs {item.tokens} tokens; {remaining} remain"
                )
            decisions.append({**base, "decision": "dropped", "reason": "context_budget_exceeded",
                              "remaining_tokens": remaining})

        return {
            "artifact_type": "model_context_pack",
            "usage_source": "scripted_teaching_tokens",
            "max_tokens": self.max_tokens,
            "used_tokens": used,
            "remaining_tokens": self.max_tokens - used,
            "selected_items": selected,
            "excluded_item_ids": [row["item_id"] for row in decisions if row["decision"] == "dropped"],
            "decisions": decisions,
            "model_input": {
                "usage_source": "scripted_teaching_tokens",
                "total_tokens": used,
                "items": selected,
            },
        }


def teaching_context_candidates(scenario):
    """Return disclosed candidates that make each context policy easy to inspect."""
    if scenario not in {"context_relevant", "context_compression", "context_conflict"}:
        raise ValueError("unknown context teaching scenario")
    shared = [
        ContextItem("policy", "system_policy",
                    "All actions are paper-only; no broker connection or real order is permitted.",
                    30, 1.0, 1.0, 1.0, mandatory=True),
        ContextItem("current_goal", "current_user_instruction",
                    "Run one auditable 2s10s paper simulation using only the approved rate workflow.",
                    25, 1.0, 1.0, 1.0, mandatory=True, conflict_key="strategy_scope"),
        ContextItem("tool_contracts", "runtime_registry",
                    "Allowed tools: fetch rate history, validate 2Y and 10Y branches, join, then simulate; model proposes only.",
                    55, 0.98, 1.0, 1.0, mandatory=True),
    ]
    noise = [
        ContextItem("old_event_notes", "historical_memory",
                    "Search Kalshi and Polymarket events and compare contract settlement rules.",
                    90, 0.12, 0.45, 0.2),
        ContextItem("ui_preference", "historical_conversation",
                    "Prefer a concise interface with an Agent Graph and Live Stream.",
                    40, 0.25, 0.7, 0.8),
    ]
    if scenario == "context_relevant":
        return shared + [
            ContextItem("latest_rate_result", "verified_observation",
                        "Latest verified lesson used DGS2 and DGS10 with a 60-day z-score and paper-only evaluation.",
                        70, 0.88, 0.9, 0.95,
                        compressed_text="Latest verified 2s10s run: 60-day z-score, paper-only.",
                        compressed_tokens=28),
        ] + noise
    if scenario == "context_compression":
        return shared + [
            ContextItem("long_run_history", "conversation_history",
                        "Long teaching history: rate source retries, checkpoints, idempotency, cancellation, parallel join, replanning, model authority and routing were each validated before this lesson.",
                        160, 0.86, 0.75, 0.9,
                        compressed_text="Prior verified invariants: resilient data, idempotent recovery, bounded runtime and model authority.",
                        compressed_tokens=40),
        ] + noise
    return shared + [
        ContextItem("stale_strategy_goal", "historical_user_instruction",
                    "Use event-market search and Kalshi/Polymarket matching as the primary strategy.",
                    60, 0.92, 1.0, 0.15, conflict_key="strategy_scope"),
        ContextItem("latest_rate_result", "verified_observation",
                    "The current approved strategy is the single 2s10s paper simulation.",
                    70, 0.88, 0.9, 0.95,
                    compressed_text="Current approved strategy: one 2s10s paper simulation.",
                    compressed_tokens=28),
    ] + noise


def context_policy_snapshot(builder, pack):
    return {
        "algorithm": "authority_freshness_conflict_then_relevance_budget",
        "score_weights": {"relevance": 0.5, "authority": 0.3, "freshness": 0.2},
        "compression": "declared_lossy_summary_only",
        "token_measurement": "scripted_teaching_tokens_not_billing",
        "max_tokens": builder.max_tokens,
        "pack": {key: value for key, value in pack.items() if key != "model_input"},
    }
