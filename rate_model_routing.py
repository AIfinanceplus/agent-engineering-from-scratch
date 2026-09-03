"""Deterministic model routing, token reservation and bounded fallback."""

from dataclasses import asdict, dataclass
from uuid import uuid4

from rate_model_planner import ScriptedRatePlanModel


class ModelProviderUnavailable(ConnectionError):
    """A selected model endpoint failed after accepting the request."""


class ModelTokenBudgetExceeded(RuntimeError):
    def __init__(self, *, model_id, required_tokens, remaining_tokens):
        self.model_id = model_id
        self.required_tokens = required_tokens
        self.remaining_tokens = remaining_tokens
        super().__init__(
            f"model {model_id} requires reservation of {required_tokens} tokens; "
            f"only {remaining_tokens} remain"
        )


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    provider: str
    tier: str
    reservation_tokens: int
    structured_plan: bool = True


MODEL_CATALOG = (
    ModelSpec("scripted-economy-v1", "teaching-local", "economy", 600),
    ModelSpec("scripted-capable-v1", "teaching-local", "capable", 1200),
)


class ModelRouter:
    """Return an ordered, finite candidate list from a declared catalog."""

    def __init__(self, catalog=MODEL_CATALOG, max_fallbacks=1):
        if isinstance(max_fallbacks, bool) or not isinstance(max_fallbacks, int) or max_fallbacks < 0:
            raise ValueError("max_fallbacks must be a non-negative integer")
        if not catalog:
            raise ValueError("model catalog must not be empty")
        self.catalog = tuple(catalog)
        self.max_fallbacks = max_fallbacks

    def candidates(self, *, purpose):
        if purpose != "structured_rate_plan":
            raise ValueError("unsupported model routing purpose")
        return self.catalog[: self.max_fallbacks + 1]

    def snapshot(self):
        return {
            "purpose": "structured_rate_plan",
            "max_fallbacks": self.max_fallbacks,
            "catalog": [asdict(spec) for spec in self.catalog],
        }


class ModelTokenBudget:
    """Reserve worst-case tokens before a call, then charge disclosed usage."""

    def __init__(self, total_tokens):
        if isinstance(total_tokens, bool) or not isinstance(total_tokens, int) or total_tokens < 1:
            raise ValueError("total_tokens must be a positive integer")
        self.total_tokens = total_tokens
        self.spent_tokens = 0
        self.reserved_tokens = 0
        self._reservations = {}

    @property
    def remaining_tokens(self):
        return self.total_tokens - self.spent_tokens - self.reserved_tokens

    def reserve(self, spec):
        if spec.reservation_tokens > self.remaining_tokens:
            raise ModelTokenBudgetExceeded(
                model_id=spec.model_id,
                required_tokens=spec.reservation_tokens,
                remaining_tokens=self.remaining_tokens,
            )
        reservation_id = f"MODEL-RES-{uuid4().hex[:10]}"
        self._reservations[reservation_id] = spec.reservation_tokens
        self.reserved_tokens += spec.reservation_tokens
        return {"reservation_id": reservation_id, "model_id": spec.model_id,
                "reserved_tokens": spec.reservation_tokens, "budget": self.snapshot()}

    def settle(self, reservation_id, *, input_tokens, output_tokens):
        if reservation_id not in self._reservations:
            raise ValueError("unknown or already settled model reservation")
        for name, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        charged = input_tokens + output_tokens
        reserved = self._reservations[reservation_id]
        if charged > reserved:
            raise ValueError("reported model usage exceeds reserved tokens")
        self._reservations.pop(reservation_id)
        self.reserved_tokens -= reserved
        self.spent_tokens += charged
        return {"reservation_id": reservation_id, "reserved_tokens": reserved,
                "charged_tokens": charged, "released_tokens": reserved - charged,
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                          "source": "scripted_teaching_usage"},
                "budget": self.snapshot()}

    def snapshot(self):
        return {"total_tokens": self.total_tokens, "spent_tokens": self.spent_tokens,
                "reserved_tokens": self.reserved_tokens, "remaining_tokens": self.remaining_tokens}


class ScriptedRoutedModel:
    """Repeatable provider behavior; no network and no claim of real tokenization."""

    is_real_llm = False

    def __init__(self, spec, scenario):
        self.spec = spec
        self.scenario = scenario
        self.model_name = spec.model_id

    def complete(self, prompt):
        if self.spec.tier == "economy" and self.scenario in {"route_fallback", "route_budget"}:
            raise ModelProviderUnavailable(
                f"teaching failure: {self.spec.model_id} timed out after accepting the prompt"
            )
        raw_output = ScriptedRatePlanModel("model_valid").complete(prompt)
        output_tokens = 280 if self.spec.tier == "economy" else 320
        return {
            "raw_output": raw_output,
            "usage": {"input_tokens": 160, "output_tokens": output_tokens,
                      "source": "scripted_teaching_usage"},
        }
