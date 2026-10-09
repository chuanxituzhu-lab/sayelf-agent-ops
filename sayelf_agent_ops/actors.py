"""Actor / Policy / Project —— Solo 与 Team 共用的唯一结构。

Solo = 成员里只有一个人类的 Project；Team = 多个人类。代码里没有 mode 字段。
Hybrid = 成员可增可退：退出的成员保留在名册里（历史与证据链仍指向他），但不再
被分派、不能裁决、不能管理成员。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

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
    name: str = ""
    active: bool = True

    def __post_init__(self) -> None:
        if self.kind not in ("human", "agent"):
            raise ValueError(f"UNKNOWN_ACTOR_KIND:{self.kind}")
        if not self.id:
            raise ValueError("EMPTY_ACTOR_ID")


@dataclass
class Policy:
    """哪些交付动作需要人类裁决，以及谁有权裁决。"""

    # deliverable_type -> gate 名称
    gated_deliverables: dict[str, str] = field(default_factory=dict)
    # gate 名称 -> 有权批准的角色（任一角色的持有人批准即可）
    gate_approver_roles: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # gate 名称 -> 必须全部到齐的角色（每个角色由不同的人各批一次，例如造价负责人 + 项目经理）
    gate_quorum: dict[str, tuple[str, ...]] = field(default_factory=dict)

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

    def quorum_for(self, gate: str) -> tuple[str, ...]:
        return tuple(self.gate_quorum.get(gate, ()))


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
        members += cls._default_agents(registry)
        return cls(id=project_id, members=members)

    @staticmethod
    def _default_agents(registry: Registry) -> list[Actor]:
        agents = [Actor(id=f"agent.{rid}", kind="agent", roles=(rid,)) for rid in registry.roles]
        agents += [Actor(id=f"agent.{rid}", kind="agent", roles=(rid,)) for rid in REVIEW_ROLES.values()]
        return agents

    @classmethod
    def from_spec(cls, spec: dict[str, Any], registry: Registry | None = None) -> "Project":
        """团队项目：人类成员与裁决规则来自一份规格（例如施工项目部模板），
        Agent 岗位默认按注册表补齐。规格里不需要、也不应该出现密码或密钥。"""
        registry = registry or build_default_registry()
        humans = [
            Actor(id=m["id"], kind=m.get("kind", "human"), roles=tuple(m.get("roles", ())),
                  name=m.get("name", ""), active=m.get("active", True))
            for m in spec.get("members", [])
        ]
        members = list(humans)
        if spec.get("include_default_agents", True):
            known = {m.id for m in members}
            members += [a for a in cls._default_agents(registry) if a.id not in known]
        policy_spec = spec.get("policy") or {}
        policy = Policy(
            gated_deliverables=dict(policy_spec.get("gated_deliverables", Policy.default().gated_deliverables)),
            gate_approver_roles={k: tuple(v) for k, v in policy_spec.get(
                "gate_approver_roles", Policy.default().gate_approver_roles).items()},
            gate_quorum={k: tuple(v) for k, v in policy_spec.get("gate_quorum", {}).items()},
        )
        project = cls(id=spec.get("id", "P-0001"), members=members, policy=policy)
        project.owner  # 规格里必须至少有一位在职负责人
        return project

    def to_spec(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "members": [{"id": m.id, "kind": m.kind, "roles": list(m.roles), "name": m.name,
                         "active": m.active} for m in self.members if m.kind == "human"],
            "policy": {
                "gated_deliverables": dict(self.policy.gated_deliverables),
                "gate_approver_roles": {k: list(v) for k, v in self.policy.gate_approver_roles.items()},
                "gate_quorum": {k: list(v) for k, v in self.policy.gate_quorum.items()},
            },
        }

    # ---- 成员 ----
    def add_member(self, actor: Actor) -> None:
        if any(m.id == actor.id for m in self.members):
            raise ValueError(f"DUPLICATE_MEMBER:{actor.id}")
        self.members.append(actor)

    def remove_member(self, actor_id: str) -> Actor:
        """退出项目：标记为不在职，名册里保留，历史不改写。"""
        actor = self.get(actor_id)
        if not actor.active:
            raise ValueError(f"ALREADY_INACTIVE:{actor_id}")
        if actor.kind == "human" and OWNER_ROLE in actor.roles:
            if not [m for m in self.humans if m.id != actor_id and OWNER_ROLE in m.roles]:
                raise ValueError("LAST_OWNER")
        updated = replace(actor, active=False)
        self.members[self.members.index(actor)] = updated
        return updated

    def get(self, actor_id: str) -> Actor:
        for m in self.members:
            if m.id == actor_id:
                return m
        raise KeyError(f"UNKNOWN_MEMBER:{actor_id}")

    @property
    def active_members(self) -> list[Actor]:
        return [m for m in self.members if m.active]

    @property
    def humans(self) -> list[Actor]:
        return [m for m in self.active_members if m.kind == "human"]

    @property
    def owner(self) -> Actor:
        for m in self.humans:
            if OWNER_ROLE in m.roles:
                return m
        raise LookupError("PROJECT_HAS_NO_OWNER")

    def is_owner(self, actor_id: str) -> bool:
        try:
            actor = self.get(actor_id)
        except KeyError:
            return False
        return actor.active and actor.kind == "human" and OWNER_ROLE in actor.roles

    # ---- 岗位指派 ----
    def agent_for_role(self, role_id: str) -> Actor:
        for m in self.active_members:
            if m.kind == "agent" and role_id in m.roles:
                return m
        raise LookupError(f"NO_AGENT_FOR_ROLE:{role_id}")

    def assignee_for_role(self, role_id: str) -> Actor:
        """专业岗位由人担任时交给人，否则交给该岗位的 Agent。单人项目里负责人只持有
        owner 角色，所以永远走 Agent —— Solo 行为不变。"""
        for m in self.humans:
            if role_id in m.roles:
                return m
        return self.agent_for_role(role_id)

    def reviewer_for(self, industry: str, producer_id: str) -> Actor:
        role_id = REVIEW_ROLES.get(industry)
        if role_id is None:
            raise LookupError(f"NO_REVIEW_ROLE_FOR_INDUSTRY:{industry}")
        for m in self.active_members:
            if m.kind == "agent" and role_id in m.roles and m.id != producer_id:
                return m
        raise LookupError(f"NO_REVIEWER_AGENT:{role_id}")

    # ---- 人工裁决 ----
    def _allowed_roles(self, gate: str) -> tuple[str, ...]:
        quorum = self.policy.quorum_for(gate)
        return quorum or self.policy.gate_approver_roles.get(gate, (OWNER_ROLE,))

    def approver_for(self, gate: str) -> Actor:
        allowed = self._allowed_roles(gate)
        for m in self.humans:
            if set(m.roles) & set(allowed):
                return m
        raise LookupError(f"NO_APPROVER_FOR_GATE:{gate}")

    def holders(self, role_id: str) -> list[Actor]:
        return [m for m in self.humans if role_id in m.roles]

    def can_decide(self, actor_id: str, gate: str, role: str | None = None) -> bool:
        try:
            actor = self.get(actor_id)
        except KeyError:
            return False
        if actor.kind != "human" or not actor.active:
            return False
        allowed = (role,) if role else self._allowed_roles(gate)
        return bool(set(actor.roles) & set(allowed))
