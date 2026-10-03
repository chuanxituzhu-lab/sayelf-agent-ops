from __future__ import annotations

from .models import ExecutionPlan, PlanStep, RoutingDecision, WorkItem


class MinimumPlanner:
    def build(self, workitem: WorkItem, decision: RoutingDecision) -> ExecutionPlan:
        steps = tuple(
            PlanStep(
                step=index,
                role=decision.selected_role,
                skill=skill_id,
                output=skill_id.split(".")[-1],
                done_when="required-output-present",
            )
            for index, skill_id in enumerate(decision.selected_skills, start=1)
        )
        return ExecutionPlan(
            id=f"PLAN-{workitem.id}",
            workitem_id=workitem.id,
            steps=steps,
        )


def apply_routing(
    workitem: WorkItem,
    decision: RoutingDecision,
    plan: ExecutionPlan,
) -> WorkItem:
    workitem.industry = decision.industry
    workitem.deliverable_type = decision.deliverable_type
    workitem.deliverable_level = decision.deliverable_level
    workitem.selected_role = decision.selected_role
    workitem.selected_skills = list(decision.selected_skills)
    workitem.excluded_roles = list(decision.excluded_roles)
    workitem.execution_plan = plan
    workitem.history.append({
        "event": "routed",
        "role": decision.selected_role,
        "skills": list(decision.selected_skills),
    })
    return workitem
