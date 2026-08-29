"""R2 multi-source macro planner.

Source tasks collect independent evidence first. The downstream analysis task
receives only completed evidence objects; it never fetches hidden data itself.
"""

from datetime import date

from macro_multisource import EIA_SERIES, FRED_SERIES
from macro_sources import BLS_SERIES
from planner import ExecutionPlan, PlanTask, validate_plan


class MultiSourceMacroPlanner:
    def plan(
        self,
        goal: str,
        *,
        mode: str = "fixture",
        reference_date: str | None = None,
    ) -> ExecutionPlan:
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal must be a non-empty string")
        if mode not in {"fixture", "live"}:
            raise ValueError("mode must be 'fixture' or 'live'")
        reference_date = reference_date or date.today().isoformat()

        headline = BLS_SERIES["headline_cpi"]
        core = BLS_SERIES["core_cpi"]
        breakeven = FRED_SERIES["breakeven_5y"]
        gasoline = EIA_SERIES["regular_gasoline"]

        plan = ExecutionPlan(
            goal=goal,
            tasks=[
                PlanTask(
                    task_id="H1",
                    title="Fetch headline CPI from BLS",
                    tool_name="fetch_bls_series",
                    arguments={
                        "series_id": headline["series_id"],
                        "label": headline["label"],
                        "mode": mode,
                    },
                ),
                PlanTask(
                    task_id="C1",
                    title="Fetch core CPI from BLS",
                    tool_name="fetch_bls_series",
                    arguments={
                        "series_id": core["series_id"],
                        "label": core["label"],
                        "mode": mode,
                    },
                ),
                PlanTask(
                    task_id="F1",
                    title="Fetch market inflation expectations from FRED",
                    tool_name="fetch_fred_series",
                    arguments={
                        "series_id": breakeven["series_id"],
                        "label": breakeven["label"],
                        "unit": breakeven["unit"],
                        "mode": mode,
                    },
                ),
                PlanTask(
                    task_id="G1",
                    title="Fetch retail gasoline prices from EIA",
                    tool_name="fetch_eia_series",
                    arguments={
                        "series_id": gasoline["series_id"],
                        "label": gasoline["label"],
                        "unit": gasoline["unit"],
                        "mode": mode,
                    },
                ),
                PlanTask(
                    task_id="A1",
                    title="Synthesize cross-source inflation signals",
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
