from __future__ import annotations

from dataclasses import dataclass, field

from .models import RoleContract, SkillContract
from .packs import IndustryPack, RouteRule


@dataclass
class Registry:
    roles: dict[str, RoleContract] = field(default_factory=dict)
    skills: dict[str, SkillContract] = field(default_factory=dict)
    route_rules: list[RouteRule] = field(default_factory=list)
    packs: dict[str, IndustryPack] = field(default_factory=dict)

    # Sprint 01: registration is not activation.
    @property
    def active_roles(self) -> int:
        return 0

    @property
    def loaded_skills(self) -> int:
        return 0

    def register_pack(self, pack: IndustryPack) -> None:
        if not pack.id or not pack.industry:
            raise ValueError("PACK_ID_AND_INDUSTRY_REQUIRED")
        if pack.id in self.packs:
            raise ValueError(f"DUPLICATE_PACK:{pack.id}")
        if any(existing.industry == pack.industry for existing in self.packs.values()):
            raise ValueError(f"DUPLICATE_INDUSTRY_PACK:{pack.industry}")
        if any(rule.industry != pack.industry for rule in pack.route_rules):
            raise ValueError(f"ROUTE_INDUSTRY_MISMATCH:{pack.id}")

        roles = {role.id: role for role in pack.roles}
        skills = {skill.id: skill for skill in pack.skills}
        if len(roles) != len(pack.roles) or set(roles) & set(self.roles):
            raise ValueError(f"DUPLICATE_ROLE:{pack.id}")
        if len(skills) != len(pack.skills) or set(skills) & set(self.skills):
            raise ValueError(f"DUPLICATE_SKILL:{pack.id}")
        if any(role.industry != pack.industry for role in roles.values()):
            raise ValueError(f"ROLE_INDUSTRY_MISMATCH:{pack.id}")
        if any(skill.owner_scope not in roles for skill in skills.values()):
            raise ValueError(f"SKILL_OWNER_OUTSIDE_PACK:{pack.id}")
        for role in roles.values():
            for skill_id in role.allowed_skills:
                if skill_id not in skills or skills[skill_id].owner_scope != role.id:
                    raise ValueError(f"ROLE_SKILL_MISMATCH:{role.id}:{skill_id}")

        merged_roles = self.roles | roles
        merged_skills = self.skills | skills
        self._validate_rules(pack.route_rules, merged_roles, merged_skills)
        self.roles.update(roles)
        self.skills.update(skills)
        self.route_rules.extend(pack.route_rules)
        self.packs[pack.id] = pack

    def register_rules(self, rules: tuple[RouteRule, ...]) -> None:
        self._validate_rules(rules, self.roles, self.skills)
        self.route_rules.extend(rules)

    def _validate_rules(
        self,
        rules: tuple[RouteRule, ...],
        roles: dict[str, RoleContract],
        skills: dict[str, SkillContract],
    ) -> None:
        existing_ids = {rule.id for rule in self.route_rules}
        for rule in rules:
            if rule.id in existing_ids:
                raise ValueError(f"DUPLICATE_ROUTE_RULE:{rule.id}")
            existing_ids.add(rule.id)
            if rule.role not in roles or roles[rule.role].industry != rule.industry:
                raise ValueError(f"UNKNOWN_ROUTE_ROLE:{rule.id}:{rule.role}")
            for skill_id in rule.skills:
                if skill_id not in skills:
                    raise KeyError(f"UNKNOWN_SKILL:{skill_id}")
                if skills[skill_id].owner_scope != rule.role:
                    raise ValueError(f"SKILL_OWNER_MISMATCH:{skill_id}")
                if skill_id not in roles[rule.role].allowed_skills:
                    raise ValueError(f"ROUTE_SKILL_NOT_ALLOWED:{rule.role}:{skill_id}")
            if rule.followup_role and rule.followup_role not in roles:
                raise ValueError(f"UNKNOWN_FOLLOWUP_ROLE:{rule.id}:{rule.followup_role}")
            if rule.followup_role and roles[rule.followup_role].industry != rule.followup_industry:
                raise ValueError(f"FOLLOWUP_INDUSTRY_MISMATCH:{rule.id}")


def build_default_registry() -> Registry:
    from .packs.engineering import build_pack as build_engineering_pack
    from .packs.media import build_pack as build_media_pack
    from .packs.workflows import cross_industry_rules

    registry = Registry()
    registry.register_pack(build_media_pack())
    registry.register_pack(build_engineering_pack())
    registry.register_rules(cross_industry_rules())
    return registry
