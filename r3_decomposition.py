"""R3 research decomposition and safe query compilation.

The intelligence boundary is explicit:
- ResearchDecomposer decides WHAT must be learned.
- QueryCompiler decides HOW an approved capability maps to a source/tool query.
- The decomposer never emits URLs, credentials, or arbitrary series IDs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from api_sources import API_SERIES


@dataclass(frozen=True)
class SubQuestion:
    subquestion_id: str
    question: str
    capability: str
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SourceIntent:
    subquestion_id: str
    capability: str
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class QuerySpec:
    query_id: str
    subquestion_id: str
    capability: str
    provider: str
    tool_name: str
    arguments: dict
    requires_env: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["requires_env"] = list(self.requires_env)
        return payload


@dataclass(frozen=True)
class ResearchBlueprint:
    question: str
    subquestions: tuple[SubQuestion, ...]
    intents: tuple[SourceIntent, ...]
    queries: tuple[QuerySpec, ...]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "subquestions": [item.to_dict() for item in self.subquestions],
            "intents": [item.to_dict() for item in self.intents],
            "queries": [item.to_dict() for item in self.queries],
        }


CAPABILITY_QUESTIONS = {
    "headline_cpi": (
        "What is the latest headline CPI trend?",
        "Headline CPI anchors the observed consumer-price trend.",
    ),
    "core_cpi": (
        "What is the latest core CPI trend excluding food and energy?",
        "Core CPI helps separate persistent inflation from volatile food and energy moves.",
    ),
    "breakeven_5y": (
        "What are market-based five-year inflation expectations doing?",
        "Breakevens add a market-expectations signal distinct from realized CPI.",
    ),
    "regular_gasoline": (
        "What are recent U.S. retail gasoline prices doing?",
        "Gasoline is a high-frequency energy-price signal, not a causal CPI attribution by itself.",
    ),
}


class ResearchDecomposer:
    """Deterministic teaching decomposer for the first R3 macro domain.

    A later stage may replace this proposal mechanism with an LLM, but the output
    contract stays the same and still flows through QueryCompiler validation.
    """

    def decompose(self, question: str) -> tuple[SubQuestion, ...]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        text = question.lower()

        broad = any(
            phrase in text
            for phrase in (
                "inflation pressure",
                "inflation outlook",
                "inflation drivers",
                "current inflation",
                "inflation trend",
                "assess inflation",
            )
        )
        capabilities: list[str] = []

        def add(capability: str) -> None:
            if capability not in capabilities:
                capabilities.append(capability)

        if broad or "headline" in text or "cpi" in text or "consumer price" in text:
            add("headline_cpi")
        if broad or "core" in text:
            add("core_cpi")
        if broad or "expectation" in text or "breakeven" in text or "market inflation" in text:
            add("breakeven_5y")
        if broad or "gasoline" in text or "gas price" in text or "energy price" in text:
            add("regular_gasoline")

        if not capabilities:
            raise ValueError(
                "R3 teaching decomposer could not map the question to an approved macro capability"
            )

        items = []
        for index, capability in enumerate(capabilities, start=1):
            subquestion, rationale = CAPABILITY_QUESTIONS[capability]
            items.append(
                SubQuestion(
                    subquestion_id=f"SQ{index}",
                    question=subquestion,
                    capability=capability,
                    rationale=rationale,
                )
            )
        return tuple(items)


class QueryCompiler:
    """Compile approved capability intents into validated Tool query specs."""

    TOOL_BY_PROVIDER = {
        "BLS": "fetch_bls_api_series",
        "FRED": "fetch_fred_api_series",
        "EIA": "fetch_eia_api_series",
    }
    REQUIRED_ENV = {
        "BLS": (),
        "FRED": ("FRED_API_KEY",),
        "EIA": ("EIA_API_KEY",),
    }

    def compile(self, subquestions: tuple[SubQuestion, ...]) -> tuple[QuerySpec, ...]:
        if not subquestions:
            raise ValueError("at least one subquestion is required")
        queries = []
        seen_capabilities = set()
        for index, subquestion in enumerate(subquestions, start=1):
            capability = subquestion.capability
            if capability in seen_capabilities:
                raise ValueError(f"duplicate capability intent: {capability}")
            seen_capabilities.add(capability)
            if capability not in API_SERIES:
                raise ValueError(f"capability is not in the approved source catalog: {capability}")
            series = API_SERIES[capability]
            provider = series["provider"]
            tool_name = self.TOOL_BY_PROVIDER.get(provider)
            if tool_name is None:
                raise ValueError(f"provider has no approved Tool mapping: {provider}")
            arguments = {
                "series_id": series["series_id"],
                "label": series["label"],
            }
            if provider in {"FRED", "EIA"}:
                arguments["unit"] = series["unit"]
            queries.append(
                QuerySpec(
                    query_id=f"Q{index}",
                    subquestion_id=subquestion.subquestion_id,
                    capability=capability,
                    provider=provider,
                    tool_name=tool_name,
                    arguments=arguments,
                    requires_env=self.REQUIRED_ENV[provider],
                )
            )
        return tuple(queries)


def build_blueprint(question: str) -> ResearchBlueprint:
    subquestions = ResearchDecomposer().decompose(question)
    intents = tuple(
        SourceIntent(
            subquestion_id=item.subquestion_id,
            capability=item.capability,
            rationale=item.rationale,
        )
        for item in subquestions
    )
    queries = QueryCompiler().compile(subquestions)
    return ResearchBlueprint(
        question=question,
        subquestions=subquestions,
        intents=intents,
        queries=queries,
    )
