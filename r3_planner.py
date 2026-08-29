"""R3 planner: ResearchBlueprint -> dynamic ExecutionPlan DAG."""

from __future__ import annotations

from datetime import date

from planner import ExecutionPlan, PlanTask, validate_plan
from r3_decomposition import ResearchBlueprint, build_blueprint


class R3ResearchPlanner:
    def build(self, question: str, *, reference_date: str | None = None) -> tuple[ResearchBlueprint, ExecutionPlan]:
        reference_date = reference_date or date.today().isoformat()
        blueprint = build_blueprint(question)
        plan = self.plan_from_blueprint(blueprint, reference_date=reference_date)
        return blueprint, plan

    def plan_from_blueprint(self, blueprint: ResearchBlueprint, *, reference_date: str) -> ExecutionPlan:
        source_tasks = []
        for query in blueprint.queries:
            source_tasks.append(
                PlanTask(
                    task_id=query.query_id,
                    title=f"{query.provider} · {query.capability} · {query.subquestion_id}",
                    tool_name=query.tool_name,
                    arguments=dict(query.arguments),
                )
            )

        dependency_ids = [query.query_id for query in blueprint.queries]
        synthesis = PlanTask(
            task_id="S1",
            title="Synthesize evidence for the decomposed research question",
            tool_name="synthesize_research_bundle",
            arguments={
                "question": blueprint.question,
                "evidence_bundle": [
                    {"from_task": query.query_id}
                    for query in blueprint.queries
                ],
                "reference_date": reference_date,
            },
            depends_on=dependency_ids,
        )
        plan = ExecutionPlan(goal=blueprint.question, tasks=[*source_tasks, synthesis])
        validate_plan(plan)
        return plan
