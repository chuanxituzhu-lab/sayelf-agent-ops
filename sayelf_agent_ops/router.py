from __future__ import annotations

import re

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

        selected_rules = self._compose_rules(text, rule)
        workflow_steps = self._ordered_steps(text, selected_rules)
        selected_role = workflow_steps[0][0] if workflow_steps else rule.role
        selected_skills = tuple(skill_id for _, skill_id in workflow_steps) or rule.skills
        requested_deliverables = tuple(dict.fromkeys(item.deliverable_type for item in selected_rules))
        reasons = [item.reason for item in selected_rules]
        if len(selected_rules) > 1:
            reasons.append("检测到明确的多项交付要求，按技能依赖合并工作流并去除重复岗位/技能。")
        elif rule.workflow_selector is not None:
            reasons.append("按任务范围选择最少工作岗位；QA 独立验收保留。")

        workflow_roles = {role_id for role_id, _ in workflow_steps}
        excluded_roles = tuple(
            role.id
            for role in self.registry.roles.values()
            if role.industry == rule.industry and role.id not in (workflow_roles or {selected_role})
        )

        for skill_id in selected_skills:
            if skill_id not in self.registry.skills:
                raise KeyError(f"UNKNOWN_SKILL:{skill_id}")
            expected_owner = next((role for role, skill in workflow_steps if skill == skill_id), rule.role)
            if self.registry.skills[skill_id].owner_scope != expected_owner:
                raise ValueError(f"SKILL_OWNER_MISMATCH:{skill_id}")

        return RoutingDecision(
            industry=rule.industry,
            deliverable_type=rule.deliverable_type,
            deliverable_level=rule.level,
            selected_role=selected_role,
            selected_skills=selected_skills,
            excluded_roles=excluded_roles,
            reason=" ".join(dict.fromkeys(reasons)),
            confidence="high",
            followup_industry=rule.followup_industry,
            followup_role=rule.followup_role,
            workflow_steps=workflow_steps,
            requested_deliverables=requested_deliverables,
        )

    def _compose_rules(self, text: str, primary: RouteRule) -> tuple[RouteRule, ...]:
        """Include distinct, explicitly joined deliverables from the same pack.

        Broad fallback rules are intentionally excluded. A task with no explicit
        conjunction keeps the existing single-route behavior.
        """
        if not re.search(r"(?:并且|同时|然后|以及|并|和|及|\band\b|\bthen\b)", text):
            return (primary,)
        matched = [
            rule for rule in self.registry.route_rules
            if rule.industry == primary.industry
            and rule.priority > 20
            and rule.predicate(text)
            and (rule is primary or rule.composition_predicate is None or rule.composition_predicate(text))
        ]
        primary_steps = (
            primary.workflow_selector(text) if primary.workflow_selector is not None
            else primary.workflow_steps or tuple((primary.role, skill_id) for skill_id in primary.skills)
        )
        primary_output_types = {
            output
            for _, skill_id in primary_steps
            for output in self.registry.skills[skill_id].produced_outputs
        }
        # Several rules can describe the same requested result. Keep the most
        # specific route for each deliverable and always retain the primary.
        by_deliverable: dict[str, RouteRule] = {primary.deliverable_type: primary}
        for candidate in sorted(matched, key=lambda item: item.priority, reverse=True):
            if candidate is not primary and candidate.deliverable_type in primary_output_types:
                continue
            by_deliverable.setdefault(candidate.deliverable_type, candidate)
        if len(by_deliverable) < 2:
            return (primary,)
        return (primary, *(item for key, item in by_deliverable.items() if key != primary.deliverable_type))

    def _ordered_steps(
        self, text: str, rules: tuple[RouteRule, ...]
    ) -> tuple[tuple[str, str], ...]:
        candidates: list[tuple[str, str]] = []
        for rule in rules:
            if rule.workflow_selector is not None:
                candidates.extend(rule.workflow_selector(text))
            elif rule.workflow_steps:
                candidates.extend(rule.workflow_steps)
            else:
                candidates.extend((rule.role, skill_id) for skill_id in rule.skills)

        # A skill appearing via both a compound rule and its prerequisite is
        # one work step, so it cannot create duplicate staffing.
        unique: dict[str, str] = {}
        for role_id, skill_id in candidates:
            existing = unique.get(skill_id)
            if existing is not None and existing != role_id:
                raise ValueError(f"SKILL_OWNER_MISMATCH:{skill_id}")
            unique.setdefault(skill_id, role_id)

        order = list(unique)
        produced_by: dict[str, list[str]] = {}
        for skill_id in order:
            for output in self.registry.skills[skill_id].produced_outputs:
                produced_by.setdefault(output, []).append(skill_id)
        prerequisites: dict[str, set[str]] = {skill_id: set() for skill_id in order}
        for skill_id in order:
            for accepted in self.registry.skills[skill_id].accepted_inputs:
                prerequisites[skill_id].update(
                    producer for producer in produced_by.get(accepted, ()) if producer != skill_id
                )

        ordered: list[str] = []
        remaining = set(order)
        while remaining:
            ready = [skill_id for skill_id in order
                     if skill_id in remaining and prerequisites[skill_id].issubset(ordered)]
            if not ready:
                raise ValueError("WORKFLOW_DEPENDENCY_CYCLE")
            for skill_id in ready:
                ordered.append(skill_id)
                remaining.remove(skill_id)
        return tuple((unique[skill_id], skill_id) for skill_id in ordered)

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
