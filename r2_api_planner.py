"""API-only R2 planner.

The active workbench always creates public-API source tasks. There is no
fixture/live switch in Planner arguments.
"""

from datetime import date

from api_sources import API_SERIES
from planner import ExecutionPlan, PlanTask, validate_plan


class APIMacroPlanner:
    def plan(self, goal: str, *, reference_date: str | None = None) -> ExecutionPlan:
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal must be a non-empty string")
        reference_date = reference_date or date.today().isoformat()
        headline = API_SERIES["headline_cpi"]
        core = API_SERIES["core_cpi"]
        breakeven = API_SERIES["breakeven_5y"]
        gasoline = API_SERIES["regular_gasoline"]

        plan = ExecutionPlan(
            goal=goal,
            tasks=[
                PlanTask(
                    task_id="H1",
                    title="Fetch headline CPI from BLS API",
                    tool_name="fetch_bls_api_series",
                    arguments={"series_id": headline["series_id"], "label": headline["label"]},
                ),
                PlanTask(
                    task_id="C1",
                    title="Fetch core CPI from BLS API",
                    tool_name="fetch_bls_api_series",
                    arguments={"series_id": core["series_id"], "label": core["label"]},
                ),
                PlanTask(
                    task_id="F1",
                    title="Fetch 5Y breakeven from FRED API",
                    tool_name="fetch_fred_api_series",
                    arguments={
                        "series_id": breakeven["series_id"],
                        "label": breakeven["label"],
                        "unit": breakeven["unit"],
                    },
                ),
                PlanTask(
                    task_id="G1",
                    title="Fetch weekly gasoline from EIA API",
                    tool_name="fetch_eia_api_series",
                    arguments={
                        "series_id": gasoline["series_id"],
                        "label": gasoline["label"],
                        "unit": gasoline["unit"],
                    },
                ),
                PlanTask(
                    task_id="A1",
                    title="Synthesize API macro signals",
                    tool_name="synthesize_macro_signals",
                    arguments={
                        "headline": {"from_task": "H1"},
                        "core": {"from_task": "C1"},
                        "breakeven": {"from_task": "F1"},
                        "gasoline": {"from_task": "G1"},
                        "reference_date": reference_date,
                    },
                    depends_on=["H1", "C1", "F1", "G1"],
                ),
            ],
        )
        validate_plan(plan)
        return plan
