"""R7 planner: source evidence -> S1 -> D1 -> F1 forecast pack."""

from __future__ import annotations

from datetime import date

from planner import ExecutionPlan, PlanTask, validate_plan
from r3_decomposition import ResearchBlueprint, build_blueprint


class R7ResearchPlanner:
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
        source_tasks = [
            PlanTask(
                task_id=query.query_id,
                title=f"{query.provider} · {query.capability} · {query.subquestion_id}",
                tool_name=query.tool_name,
                arguments=dict(query.arguments),
            )
            for query in blueprint.queries
        ]
        source_ids = [query.query_id for query in blueprint.queries]

        research_synthesis = PlanTask(
            task_id="S1",
            title="Synthesize grounded research evidence",
            tool_name="synthesize_research_bundle",
            arguments={
                "question": blueprint.question,
                "evidence_bundle": [{"from_task": task_id} for task_id in source_ids],
                "reference_date": reference_date,
            },
            depends_on=source_ids,
        )

        domain_synthesis = PlanTask(
            task_id="D1",
            title=f"Translate grounded research into a {domain} decision brief",
            tool_name="synthesize_domain_brief",
            arguments={
                "question": blueprint.question,
                "domain": domain,
                "research_synthesis": {"from_task": "S1"},
                "reference_date": reference_date,
            },
            depends_on=["S1"],
        )

        forecast_pack = PlanTask(
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

        plan = ExecutionPlan(
            goal=f"[{domain}] {blueprint.question}",
            tasks=[*source_tasks, research_synthesis, domain_synthesis, forecast_pack],
        )
        validate_plan(plan)
        return plan
