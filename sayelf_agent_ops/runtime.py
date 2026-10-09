"""Runtime —— Solo 与 Team 共用的唯一执行路径。

submit → run（Agent 自动接力：路由 → 按需加载 Skill → 产出 → 产出者自检（AcceptanceGate）
→ 独立审核（Reviewer）→ 返工）→ 交付或停在 Human Gate → decide（一次性授权令牌）
所有动作写入只追加的事件日志（证据链），每条记录都有 actor。

两道门的分工：
- AcceptanceGate：产出者自检，规则来自 SkillContract.validation；通过记录绑定产出摘要。
- Reviewer：独立审核者（不能是产出者），自检和审核都通过才算通过。
- HumanGate：Policy 决定谁能批（Project.can_decide），HumanGate 决定批的是什么——
  动作、目标、产出摘要三者绑定，一次有效，批准后改稿即失效。
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from .actors import Project
from .executor import BuiltinExecutor, Executor, SkillExecutionError
from .gates import AcceptanceGate, ActionKind, ApprovalRequest, ApprovalStore, HumanGate
from .loader import SkillLoader, discover_capabilities
from .models import WorkItem
from .planner import MinimumPlanner, apply_routing
from .registry import Registry, build_default_registry
from .review import RuleReviewer
from .router import Router
from .state import StateEngine, TransitionRejected, WorkState

SYSTEM_ROUTER = "system.router"
SYSTEM_RUNTIME = "system.runtime"
MAX_ATTEMPTS_PER_RUN = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Runtime:
    def __init__(
        self,
        project: Project,
        registry: Registry | None = None,
        executor: Executor | None = None,
        reviewer: Any | None = None,
        loader: SkillLoader | None = None,
        approval_store: ApprovalStore | None = None,
    ):
        self.project = project
        self.registry = registry or build_default_registry()
        self.router = Router(self.registry)
        self.planner = MinimumPlanner()
        self.state = StateEngine()
        self.executor = executor or BuiltinExecutor(registry=self.registry)
        self.reviewer = reviewer or RuleReviewer()
        self.acceptance = AcceptanceGate(self.registry)
        self.human_gate = HumanGate(
            self.acceptance, approver_policy=self._approver_policy, store=approval_store
        )
        self.loader = loader or SkillLoader(self.registry, capabilities=discover_capabilities())
        self._pending: dict[str, dict[str, Any]] = {}
        self.items: dict[str, WorkItem] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._feedback: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ events
    def _log(self, wi: WorkItem, actor: str, event: str, **data: Any) -> None:
        log = self._events.setdefault(wi.id, [])
        log.append({"seq": len(log) + 1, "at": _now(), "actor": actor, "event": event, **data})

    def events(self, wi: WorkItem) -> list[dict[str, Any]]:
        return copy.deepcopy(self._events.get(wi.id, []))

    def _approver_policy(self, approver: str, req: ApprovalRequest) -> bool:
        pending = self._pending.get(req.workitem_id)
        return bool(pending) and self.project.can_decide(approver, pending["gate"])

    def _move(self, wi: WorkItem, actor: str, target: WorkState) -> None:
        before = wi.state
        self.state.transition(wi, target)
        self._log(wi, actor, "state", **{"from": before, "to": wi.state})

    # ------------------------------------------------------------------ submit
    def submit(
        self,
        text: str,
        goal: str | None = None,
        deliverable: str | None = None,
        industry: str | None = None,
        submitted_by: str | None = None,
    ) -> WorkItem:
        text = (text or "").strip()
        if not text:
            raise ValueError("EMPTY_INPUT")
        owner = submitted_by or self.project.owner.id
        if self.project.get(owner).kind != "human":
            raise PermissionError("ONLY_HUMANS_SUBMIT")

        wi = WorkItem(
            id=f"WI-{len(self.items) + 1:04d}",
            input=text,
            goal=goal or text,
            deliverable=deliverable or text,
            owner=owner,
        )
        # 未指定行业时由交付物路由决定；无法路由则直接拒绝，不硬套岗位。
        wi.industry = industry or self.router.route(wi).industry
        self.items[wi.id] = wi
        self._log(wi, owner, "submit", input=text)
        self._move(wi, SYSTEM_ROUTER, WorkState.SCOPED)
        return wi

    # ------------------------------------------------------------------ run
    def run(self, wi: WorkItem) -> WorkItem:
        if wi.state == WorkState.SCOPED:
            self._route(wi)
        elif wi.state == WorkState.REWORK:
            self._move(wi, wi.assignee or SYSTEM_RUNTIME, WorkState.WORKING)
        elif wi.state != WorkState.WORKING:
            return wi

        loaded = self.loader.load_for_plan(wi.execution_plan)
        if not loaded.ok:
            # 缺能力 / 许可证不允许 / 超出上下文预算：明确停下，不带病执行。
            self._log(wi, SYSTEM_RUNTIME, "skills-blocked", blocked=dict(loaded.blocked))
            self._log(wi, SYSTEM_RUNTIME, "escalated", reason="SKILLS_BLOCKED")
            return wi
        try:
            return self._execute(wi)
        finally:
            self.loader.release(wi.execution_plan)

    def _execute(self, wi: WorkItem) -> WorkItem:
        feedback = self._feedback.pop(wi.id, [])
        for attempt in range(1, MAX_ATTEMPTS_PER_RUN + 1):
            try:
                outputs = [self.executor.run(step, wi, feedback) for step in wi.execution_plan.steps]
            except SkillExecutionError as error:
                # 技能执行失败（如未授权调用远程模型、模型不可用）：停在 WORKING 交给人，
                # 不产出、不重试、不把输入写进日志。
                self._feedback[wi.id] = feedback
                self._log(wi, wi.assignee, "executor-failed", code=error.code)
                self._log(wi, SYSTEM_RUNTIME, "escalated", reason=error.code)
                return wi
            wi.outputs = outputs
            for out in outputs:
                self._log(wi, wi.assignee, "output", skill=out.get("skill"), type=out.get("type"),
                          placeholder=out.get("placeholder", False), evidence=out.get("evidence", {}))
            self._move(wi, wi.assignee, WorkState.READY)
            self_check = self.acceptance.check(wi)
            self._log(wi, wi.assignee, "self-check", passed=self_check.passed,
                      failures=list(self_check.failures), output_digest=self_check.output_digest)
            self._move(wi, wi.assignee, WorkState.REVIEW)

            result = self.reviewer.review(wi, outputs)
            self._log(wi, wi.reviewer, "review", passed=result.passed, checks=result.checks)
            if result.passed and self_check.passed:
                self._move(wi, wi.reviewer, WorkState.APPROVED)
                break
            wi.rework_count += 1
            feedback = list(self_check.failures) + result.failures
            self._move(wi, wi.reviewer, WorkState.REWORK)
            self._log(wi, wi.reviewer, "rework-requested", feedback=feedback)
            if attempt == MAX_ATTEMPTS_PER_RUN:
                # 多轮返工仍未通过：停在 REWORK 交给人类，不无限循环。
                self._feedback[wi.id] = feedback
                self._log(wi, SYSTEM_RUNTIME, "escalated", reason="MAX_ATTEMPTS_REACHED")
                return wi
            self._move(wi, wi.assignee, WorkState.WORKING)

        gate = self.project.policy.gate_for(wi.deliverable_type)
        if gate:
            action = ActionKind(gate) if gate in {a.value for a in ActionKind} else ActionKind.EXTERNAL_WRITE
            target = f"{wi.deliverable_type}@{self.project.id}"
            wi.pending_gate = gate
            wi.approver = self.project.approver_for(gate).id
            self._pending[wi.id] = {"gate": gate, "action": action, "target": target}
            req = self.human_gate.request(
                wi, action, target, wi.outputs, summary=f"{gate}: {wi.deliverable_type}"
            )
            self._pending[wi.id]["request"] = req.id
            self._log(wi, SYSTEM_RUNTIME, "gate-requested", gate=gate, approver=wi.approver,
                      request=req.id, action=action.value, target=target,
                      payload_digest=req.payload_digest)
            return wi

        self._move(wi, SYSTEM_RUNTIME, WorkState.DELIVERED)
        self._log(wi, SYSTEM_RUNTIME, "delivered")
        return wi

    def _route(self, wi: WorkItem) -> None:
        decision = self.router.route(wi)
        plan = self.planner.build(wi, decision)
        apply_routing(wi, decision, plan)
        producer = self.project.agent_for_role(decision.selected_role)
        reviewer = self.project.reviewer_for(decision.industry, producer.id)
        wi.assignee = producer.id
        wi.reviewer = reviewer.id
        self._log(wi, SYSTEM_ROUTER, "route", role=decision.selected_role,
                  skills=list(decision.selected_skills), excluded=list(decision.excluded_roles),
                  assignee=producer.id, reviewer=reviewer.id, reason=decision.reason,
                  followup_role=decision.followup_role)
        self._move(wi, SYSTEM_ROUTER, WorkState.WORKING)

    # ------------------------------------------------------------------ decide
    def decide(self, wi: WorkItem, actor_id: str, approve: bool, reason: str = "") -> WorkItem:
        if wi.state != WorkState.APPROVED or not wi.pending_gate:
            raise TransitionRejected("NO_PENDING_GATE")
        gate = wi.pending_gate
        if not self.project.can_decide(actor_id, gate):
            raise PermissionError(f"NOT_ALLOWED_TO_DECIDE:{actor_id}:{gate}")

        pending = self._pending.get(wi.id)
        if not pending or "request" not in pending:
            raise TransitionRejected("NO_PENDING_REQUEST")

        token = None
        if approve:
            # 批准与兑现绑定同一份产出：批准后产出被改动，这里会被 HumanGate 拦下。
            self.human_gate.approve(pending["request"], actor_id)
            token = self.human_gate.authorize(
                wi, pending["request"], pending["action"], pending["target"], wi.outputs
            )
        else:
            self.human_gate.deny(pending["request"], actor_id, reason)

        self._pending.pop(wi.id, None)
        self._log(wi, actor_id, "decision", gate=gate, approve=bool(approve), reason=reason,
                  request=pending["request"])
        wi.pending_gate = None
        if approve:
            self._move(wi, actor_id, WorkState.DELIVERED)
            self._log(wi, actor_id, "delivered", authorization=token.request_id,
                      payload_digest=token.payload_digest)
        else:
            wi.rework_count += 1
            self._move(wi, actor_id, WorkState.REWORK)
            self._feedback[wi.id] = [reason] if reason else []
        return wi
