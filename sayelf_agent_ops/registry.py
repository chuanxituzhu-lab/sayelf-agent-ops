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
    active_role_ids: set[str] = field(default_factory=set)

    @property
    def active_roles(self) -> int:
        return len(self.active_role_ids)

    @property
    def loaded_skills(self) -> int:
        return 0

    @property
    def loaded_industries(self) -> tuple[str, ...]:
        return tuple(pack.industry for pack in self.packs.values())

    def activate_role(self, role_id: str) -> None:
        if role_id not in self.roles:
            raise KeyError(f"UNKNOWN_ROLE:{role_id}")
        self.active_role_ids.add(role_id)

    def deactivate_role(self, role_id: str) -> None:
        if role_id not in self.roles:
            raise KeyError(f"UNKNOWN_ROLE:{role_id}")
        self.active_role_ids.discard(role_id)

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


# Industry packs are imported only when a registry asks for them, so an
# unused industry's roles, skills and rules never enter memory or context.
PACK_MODULES: dict[str, str] = {
    "media": "sayelf_agent_ops.packs.media",
    "engineering": "sayelf_agent_ops.packs.engineering",
}


def available_industries() -> tuple[str, ...]:
    return tuple(PACK_MODULES)


def build_registry(industries: tuple[str, ...] | list[str] | None = None) -> Registry:
    """Build a registry with only the requested industry packs.

    ``None`` loads every known pack (same as ``build_default_registry``).
    Cross-industry workflow rules are added only when every industry they
    connect is loaded.
    """
    import importlib

    wanted = tuple(PACK_MODULES) if industries is None else tuple(dict.fromkeys(industries))
    unknown = [name for name in wanted if name not in PACK_MODULES]
    if unknown:
        raise ValueError(f"UNKNOWN_PACK:{','.join(unknown)}")
    registry = Registry()
    for name in wanted:
        registry.register_pack(importlib.import_module(PACK_MODULES[name]).build_pack())

    from .packs.workflows import cross_industry_rules

    loaded = {pack.industry for pack in registry.packs.values()}
    rules = tuple(
        rule for rule in cross_industry_rules()
        if rule.industry in loaded and (rule.followup_industry is None or rule.followup_industry in loaded)
    )
    if rules:
        registry.register_rules(rules)
    return registry


def build_default_registry() -> Registry:
    return build_registry(None)
