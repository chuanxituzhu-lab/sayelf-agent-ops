from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkItem:
    id: str
    input: str
    goal: str = ""
    deliverable: str = ""
    industry: str | None = None
    deliverable_type: str | None = None
    deliverable_level: str | None = None
    state: str = "INBOX"
    instance_id: str = "default"
    selected_role: str | None = None
    selected_skills: list[str] = field(default_factory=list)
    excluded_roles: list[str] = field(default_factory=list)
    outputs: list[Any] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    execution_plan: "ExecutionPlan | None" = None
    # Sprint 02: every party is an actor id, never "the user".
    owner: str | None = None
    assignee: str | None = None
    reviewer: str | None = None
    approver: str | None = None
    pending_gate: str | None = None
    rework_count: int = 0


@dataclass(frozen=True)
class RoleContract:
    id: str
    industry: str
    name: str
    responsibility: str
    owned_outputs: tuple[str, ...]
    allowed_skills: tuple[str, ...]
    forbidden_scope: tuple[str, ...] = ()
    status: str = "stable"


@dataclass(frozen=True)
class SkillContract:
    id: str
    owner_scope: str
    purpose: str
    accepted_inputs: tuple[str, ...]
    produced_outputs: tuple[str, ...]
    required_capabilities: tuple[str, ...] = ()
    validation: tuple[str, ...] = ()
    status: str = "stable"


@dataclass(frozen=True)
class RoutingDecision:
    industry: str
    deliverable_type: str
    deliverable_level: str
    selected_role: str
    selected_skills: tuple[str, ...]
    excluded_roles: tuple[str, ...]
    reason: str
    confidence: str = "high"
    followup_industry: str | None = None
    followup_role: str | None = None


@dataclass(frozen=True)
class PlanStep:
    step: int
    role: str
    skill: str
    output: str
    done_when: str


@dataclass(frozen=True)
class ExecutionPlan:
    id: str
    workitem_id: str
    steps: tuple[PlanStep, ...]
