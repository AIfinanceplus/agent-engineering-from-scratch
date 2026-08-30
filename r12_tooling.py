"""R12 Tool pack: discovery, strategy registry, structural scanner, and verified cross-market RV."""

from r11_tooling import register_r11_tools
from r12_discovery import discover_market_candidates
from r12_event_sources import fetch_kalshi_market_contract, fetch_polymarket_market_contract
from r12_identity import compare_cross_market_locked_rv, validate_event_identity
from r12_registry import current_strategy_registry_snapshot
from r12_strategy import scan_structural_opportunities
from tools import TOOL_REGISTRY, Tool


def fetch_r12_market_contract(provider: str, identifier: str) -> dict:
    provider = provider.strip().lower() if isinstance(provider, str) else ""
    if provider == "kalshi":
        return fetch_kalshi_market_contract(identifier)
    if provider == "polymarket":
        return fetch_polymarket_market_contract(identifier)
    raise ValueError("provider must be kalshi or polymarket")


R12_STRUCTURAL_SCAN_TOOL = Tool(
    name="scan_r12_structural_opportunities",
    description=(
        "Scan a supplied prediction-market snapshot for exact logical pricing inconsistencies. "
        "The tool never fetches markets and never executes trades; it emits PAPER_SIGNAL_ONLY opportunities."
    ),
    parameters={
        "type": "object",
        "properties": {"snapshot": {"type": "object"}},
        "required": ["snapshot"],
        "additionalProperties": False,
    },
    function=scan_structural_opportunities,
    max_retries=0,
    risk="low",
)

R12_STRATEGY_REGISTRY_TOOL = Tool(
    name="get_r12_strategy_registry",
    description=(
        "Return the current five-strategy roadmap and implementation status without market fetching or execution."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    function=current_strategy_registry_snapshot,
    max_retries=0,
    risk="low",
)

R12_DISCOVERY_TOOL = Tool(
    name="discover_r12_market_candidates",
    description=(
        "Find plausible public Kalshi and Polymarket market candidates from a free-text event query. "
        "Discovery is bounded and lexical; candidate similarity NEVER approves settlement identity or trade execution."
    ),
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    },
    function=discover_market_candidates,
    max_retries=1,
    risk="low",
)

R12_MARKET_CONTRACT_TOOL = Tool(
    name="fetch_r12_market_contract",
    description=(
        "Fetch one exact public Kalshi market ticker or Polymarket market ID and normalize its rules, "
        "resolution metadata, time contract, and top-of-book market data. This tool never places orders."
    ),
    parameters={
        "type": "object",
        "properties": {
            "provider": {"type": "string", "enum": ["kalshi", "polymarket"]},
            "identifier": {"type": "string"},
        },
        "required": ["provider", "identifier"],
        "additionalProperties": False,
    },
    function=fetch_r12_market_contract,
    max_retries=1,
    risk="low",
)

R12_IDENTITY_TOOL = Tool(
    name="validate_r12_event_identity",
    description=(
        "Validate whether normalized Kalshi and Polymarket contracts may be treated as the same binary settlement event. "
        "Title similarity never auto-approves identity; explicit semantic/rules attestation is required."
    ),
    parameters={
        "type": "object",
        "properties": {
            "kalshi_contract": {"type": "object"},
            "polymarket_contract": {"type": "object"},
            "attestation": {"type": "object"},
        },
        "required": ["kalshi_contract", "polymarket_contract"],
        "additionalProperties": False,
    },
    function=validate_event_identity,
    max_retries=0,
    risk="low",
)

R12_CROSS_MARKET_RV_TOOL = Tool(
    name="compare_r12_cross_market_locked_rv",
    description=(
        "After settlement identity is explicitly verified, compare reciprocal cross-venue YES/NO asks for a locked "
        "$1 complement basket margin after explicit estimated costs. Emits paper signals only."
    ),
    parameters={
        "type": "object",
        "properties": {
            "identity": {"type": "object"},
            "kalshi_contract": {"type": "object"},
            "polymarket_contract": {"type": "object"},
            "estimated_total_cost_per_basket": {"type": "number"},
        },
        "required": ["identity", "kalshi_contract", "polymarket_contract"],
        "additionalProperties": False,
    },
    function=compare_cross_market_locked_rv,
    max_retries=0,
    risk="low",
)


def register_r12_tools() -> tuple[str, ...]:
    names = list(register_r11_tools())
    for tool in (
        R12_STRUCTURAL_SCAN_TOOL,
        R12_STRATEGY_REGISTRY_TOOL,
        R12_DISCOVERY_TOOL,
        R12_MARKET_CONTRACT_TOOL,
        R12_IDENTITY_TOOL,
        R12_CROSS_MARKET_RV_TOOL,
    ):
        existing = TOOL_REGISTRY.get(tool.name)
        if existing is not None and existing != tool:
            raise ValueError(f"Tool name collision while loading R12 tool: {tool.name}")
        TOOL_REGISTRY[tool.name] = tool
        names.append(tool.name)
    return tuple(names)
