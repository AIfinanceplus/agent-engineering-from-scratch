"""R12 Tool pack: deterministic strategy registry and structural opportunity scanner."""

from r11_tooling import register_r11_tools
from r12_strategy import scan_structural_opportunities, strategy_registry_snapshot
from tools import TOOL_REGISTRY, Tool


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
    function=strategy_registry_snapshot,
    max_retries=0,
    risk="low",
)


def register_r12_tools() -> tuple[str, ...]:
    names = list(register_r11_tools())
    for tool in (R12_STRUCTURAL_SCAN_TOOL, R12_STRATEGY_REGISTRY_TOOL):
        existing = TOOL_REGISTRY.get(tool.name)
        if existing is not None and existing != tool:
            raise ValueError(f"Tool name collision while loading R12 tool: {tool.name}")
        TOOL_REGISTRY[tool.name] = tool
        names.append(tool.name)
    return tuple(names)
