from __future__ import annotations

from .models import ExecutionPlan, PlanStep, RoutingDecision, WorkItem
from .registry import Registry


class MinimumPlanner:
    def __init__(self, registry: Registry | None = None):
        self.registry = registry

    def build(self, workitem: WorkItem, decision: RoutingDecision) -> ExecutionPlan:
        role_skills = decision.workflow_steps or tuple(
            (decision.selected_role, skill_id) for skill_id in decision.selected_skills
        )
        steps = tuple(
            PlanStep(
                step=index,
                role=role,
                skill=skill_id,
                output=self._output_for(decision, skill_id),
                done_when=self._acceptance_for(skill_id),
            )
            for index, (role, skill_id) in enumerate(role_skills, start=1)
        )
        return ExecutionPlan(
            id=f"PLAN-{workitem.id}",
            workitem_id=workitem.id,
            steps=steps,
        )

    def _output_for(self, decision: RoutingDecision, skill_id: str) -> str:
        if self.registry and skill_id in self.registry.skills:
            outputs = self.registry.skills[skill_id].produced_outputs
            if outputs:
                return outputs[0]
        return skill_id.split(".")[-1]

    def _acceptance_for(self, skill_id: str) -> str:
        if self.registry and skill_id in self.registry.skills:
            checks = self.registry.skills[skill_id].validation
            if checks:
                return " & ".join(checks)
        return "required-output-present"


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
