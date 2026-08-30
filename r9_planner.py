"""R9 planner: preserve R8 core research and add an Investment-only market context lane."""

from __future__ import annotations

from datetime import date

from planner import ExecutionPlan, PlanTask, validate_plan
from r3_decomposition import ResearchBlueprint, build_blueprint
from r9_market import MARKET_SERIES


class R9ResearchPlanner:
    def build(
        self,
        question: str,
        *,
        domain: str,
        reference_date: str | None = None,
    ) -> tuple[ResearchBlueprint, ExecutionPlan]:
        if domain not in {"investment", "policy"}:
            raise ValueError("domain must be investment or policy")
        reference_date = reference_date or date.today().isoformat()
        blueprint = build_blueprint(question)
        return blueprint, self.plan_from_blueprint(
            blueprint,
            domain=domain,
            reference_date=reference_date,
        )

    def plan_from_blueprint(
        self,
        blueprint: ResearchBlueprint,
        *,
        domain: str,
        reference_date: str,
    ) -> ExecutionPlan:
        research_source_tasks = [
            PlanTask(
                task_id=query.query_id,
                title=f"{query.provider} · {query.capability} · {query.subquestion_id}",
                tool_name=query.tool_name,
                arguments=dict(query.arguments),
            )
            for query in blueprint.queries
        ]
        research_source_ids = [query.query_id for query in blueprint.queries]

        s1 = PlanTask(
            task_id="S1",
            title="Synthesize grounded research evidence",
            tool_name="synthesize_research_bundle",
            arguments={
                "question": blueprint.question,
                "evidence_bundle": [{"from_task": task_id} for task_id in research_source_ids],
                "reference_date": reference_date,
            },
            depends_on=research_source_ids,
        )

        d1 = PlanTask(
            task_id="D1",
            title=f"Apply R8 professional {domain} decision lens",
            tool_name="synthesize_professional_decision_brief",
            arguments={
                "question": blueprint.question,
                "domain": domain,
                "research_synthesis": {"from_task": "S1"},
                "reference_date": reference_date,
            },
            depends_on=["S1"],
        )

        f1 = PlanTask(
            task_id="F1",
            title="Create falsifiable forecast contracts and scenario tracker",
            tool_name="create_forecast_pack",
            arguments={
                "question": blueprint.question,
                "domain": domain,
                "research_synthesis": {"from_task": "S1"},
                "domain_brief": {"from_task": "D1"},
                "reference_date": reference_date,
            },
            depends_on=["S1", "D1"],
        )

        tasks = [*research_source_tasks]
        if domain == "investment":
            market_tasks = []
            for task_id, spec in MARKET_SERIES.items():
                market_tasks.append(
                    PlanTask(
                        task_id=task_id,
                        title=f"FRED market context · {spec['label']}",
                        tool_name="fetch_fred_api_series",
                        arguments={
                            "series_id": spec["series_id"],
                            "label": spec["label"],
                            "unit": spec["unit"],
                        },
                    )
                )
            tasks.extend(market_tasks)
            tasks.append(s1)
            tasks.append(
                PlanTask(
                    task_id="M6",
                    title="Build observed market-pricing snapshot",
                    tool_name="build_market_pricing_snapshot",
                    arguments={
                        "policy_rate": {"from_task": "M1"},
                        "treasury_2y": {"from_task": "M2"},
                        "treasury_10y": {"from_task": "M3"},
                        "real_yield_10y": {"from_task": "M4"},
                        "breakeven_10y": {"from_task": "M5"},
                        "reference_date": reference_date,
                    },
                    depends_on=["M1", "M2", "M3", "M4", "M5"],
                )
            )
            tasks.extend([d1, f1])
        else:
            tasks.extend([s1, d1, f1])

        plan = ExecutionPlan(
            goal=f"[R9:{domain}] {blueprint.question}",
            tasks=tasks,
        )
        validate_plan(plan)
        return plan
