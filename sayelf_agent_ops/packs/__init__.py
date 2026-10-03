from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..models import RoleContract, SkillContract


@dataclass(frozen=True)
class RouteRule:
    id: str
    predicate: Callable[[str], bool]
    priority: int
    deliverable_type: str
    industry: str
    level: str
    role: str
    skills: tuple[str, ...]
    reason: str
    followup_industry: str | None = None
    followup_role: str | None = None


@dataclass(frozen=True)
class IndustryPack:
    id: str
    industry: str
    roles: tuple[RoleContract, ...]
    skills: tuple[SkillContract, ...]
    route_rules: tuple[RouteRule, ...]
