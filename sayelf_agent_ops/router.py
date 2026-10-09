from __future__ import annotations

from .models import RoutingDecision, WorkItem
from .packs import RouteRule
from .registry import Registry


class Router:
    """Deterministic deliverable-first router over registered industry packs."""

    def __init__(self, registry: Registry):
        self.registry = registry

    def route(self, workitem: WorkItem) -> RoutingDecision:
        text = " ".join([workitem.input, workitem.goal, workitem.deliverable]).lower()
        rule = self._classify_deliverable(text)

        excluded_roles = tuple(
            role.id
            for role in self.registry.roles.values()
            if role.industry == rule.industry and role.id != rule.role
        )

        for skill_id in rule.skills:
            if skill_id not in self.registry.skills:
                raise KeyError(f"UNKNOWN_SKILL:{skill_id}")
            if self.registry.skills[skill_id].owner_scope != rule.role:
                raise ValueError(f"SKILL_OWNER_MISMATCH:{skill_id}")

        return RoutingDecision(
            industry=rule.industry,
            deliverable_type=rule.deliverable_type,
            deliverable_level=rule.level,
            selected_role=rule.role,
            selected_skills=rule.skills,
            excluded_roles=excluded_roles,
            reason=rule.reason,
            confidence="high",
            followup_industry=rule.followup_industry,
            followup_role=rule.followup_role,
        )

    def _classify_deliverable(self, text: str) -> RouteRule:
        matches = [rule for rule in self.registry.route_rules if rule.predicate(text)]
        if not matches:
            raise ValueError("UNROUTABLE_DELIVERABLE")

        highest_priority = max(rule.priority for rule in matches)
        best_matches = [rule for rule in matches if rule.priority == highest_priority]
        if len(best_matches) != 1:
            rule_ids = ",".join(rule.id for rule in best_matches)
            raise ValueError(f"AMBIGUOUS_ROUTING_RULE:{rule_ids}")
        return best_matches[0]
