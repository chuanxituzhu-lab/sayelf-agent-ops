"""Actor / Policy / Project —— Solo 与 Team 共用的唯一结构。

Solo = 成员里只有一个人类的 Project；Team = 多个人类。代码里没有 mode 字段。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .registry import Registry, build_default_registry

OWNER_ROLE = "owner"

# 审核是独立岗位，不参与交付物路由（因此不放进 Registry.roles，不影响 Sprint 01 路由）。
REVIEW_ROLES: dict[str, str] = {
    "media": "media.reviewer",
    "engineering": "engineering.reviewer",
}


@dataclass(frozen=True)
class Actor:
    id: str
    kind: str  # "human" | "agent"
    roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in ("human", "agent"):
            raise ValueError(f"UNKNOWN_ACTOR_KIND:{self.kind}")


@dataclass
class Policy:
    """哪些交付动作需要人类裁决，以及谁有权裁决。"""

    # deliverable_type -> gate 名称
    gated_deliverables: dict[str, str] = field(default_factory=dict)
    # gate 名称 -> 有权批准的角色
    gate_approver_roles: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "Policy":
        return cls(
            gated_deliverables={"platform-package": "publish"},
            gate_approver_roles={"publish": (OWNER_ROLE,)},
        )

    def gate_for(self, deliverable_type: str | None) -> str | None:
        if deliverable_type is None:
            return None
        return self.gated_deliverables.get(deliverable_type)


@dataclass
class Project:
    id: str
    members: list[Actor]
    policy: Policy = field(default_factory=Policy.default)

    @classmethod
    def solo(cls, owner_id: str, registry: Registry | None = None, project_id: str = "P-0001") -> "Project":
        """零配置单人项目：唯一人类 + 每个专业岗位一个 Agent + 每个行业一个审核 Agent。"""
        registry = registry or build_default_registry()
        members = [Actor(id=owner_id, kind="human", roles=(OWNER_ROLE,))]
        members += [Actor(id=f"agent.{rid}", kind="agent", roles=(rid,)) for rid in registry.roles]
        members += [Actor(id=f"agent.{rid}", kind="agent", roles=(rid,)) for rid in REVIEW_ROLES.values()]
        return cls(id=project_id, members=members)

    # ---- 成员 ----
    def add_member(self, actor: Actor) -> None:
        if any(m.id == actor.id for m in self.members):
            raise ValueError(f"DUPLICATE_MEMBER:{actor.id}")
        self.members.append(actor)

    def get(self, actor_id: str) -> Actor:
        for m in self.members:
            if m.id == actor_id:
                return m
        raise KeyError(f"UNKNOWN_MEMBER:{actor_id}")

    @property
    def humans(self) -> list[Actor]:
        return [m for m in self.members if m.kind == "human"]

    @property
    def owner(self) -> Actor:
        for m in self.humans:
            if OWNER_ROLE in m.roles:
                return m
        raise LookupError("PROJECT_HAS_NO_OWNER")

    # ---- 岗位指派 ----
    def agent_for_role(self, role_id: str) -> Actor:
        for m in self.members:
            if m.kind == "agent" and role_id in m.roles:
                return m
        raise LookupError(f"NO_AGENT_FOR_ROLE:{role_id}")

    def reviewer_for(self, industry: str, producer_id: str) -> Actor:
        role_id = REVIEW_ROLES.get(industry)
        if role_id is None:
            raise LookupError(f"NO_REVIEW_ROLE_FOR_INDUSTRY:{industry}")
        for m in self.members:
            if m.kind == "agent" and role_id in m.roles and m.id != producer_id:
                return m
        raise LookupError(f"NO_REVIEWER_AGENT:{role_id}")

    # ---- 人工裁决 ----
    def approver_for(self, gate: str) -> Actor:
        allowed = self.policy.gate_approver_roles.get(gate, (OWNER_ROLE,))
        for m in self.humans:
            if set(m.roles) & set(allowed):
                return m
        raise LookupError(f"NO_APPROVER_FOR_GATE:{gate}")

    def can_decide(self, actor_id: str, gate: str) -> bool:
        try:
            actor = self.get(actor_id)
        except KeyError:
            return False
        if actor.kind != "human":
            return False
        allowed = self.policy.gate_approver_roles.get(gate, (OWNER_ROLE,))
        return bool(set(actor.roles) & set(allowed))
