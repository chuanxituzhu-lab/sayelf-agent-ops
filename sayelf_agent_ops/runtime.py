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
        id_prefix: str = "WI",
    ):
        self.project = project
        self.registry = registry or build_default_registry()
        self.router = Router(self.registry)
        self.planner = MinimumPlanner(self.registry)
        self.state = StateEngine()
        self.executor = executor or BuiltinExecutor(registry=self.registry)
        self.reviewer = reviewer or RuleReviewer()
        self.acceptance = AcceptanceGate(self.registry)
        self.human_gate = HumanGate(
            self.acceptance, approver_policy=self._approver_policy, store=approval_store
        )
        self.loader = loader or SkillLoader(self.registry, capabilities=discover_capabilities())
        self._pending: dict[str, dict[str, Any]] = {}
        self.id_prefix = id_prefix
        self.items: dict[str, WorkItem] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._feedback: dict[str, list[str]] = {}
        # Team: plan steps owned by a human member wait for that person's output.
        self._human_tasks: dict[str, dict[str, Any]] = {}
        self._human_outputs: dict[tuple[str, int], dict[str, Any]] = {}
        self._project_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ events
    def _log(self, wi: WorkItem, actor: str, event: str, **data: Any) -> None:
        log = self._events.setdefault(wi.id, [])
        log.append({"seq": len(log) + 1, "at": _now(), "actor": actor, "event": event, **data})

    def events(self, wi: WorkItem) -> list[dict[str, Any]]:
        return copy.deepcopy(self._events.get(wi.id, []))

    def _approver_policy(self, approver: str, req: ApprovalRequest) -> bool:
        pending = self._pending.get(req.workitem_id)
        if not pending:
            return False
        role = pending.get("quorum_by_request", {}).get(req.id)
        return self.project.can_decide(approver, pending["gate"], role=role)

    # ------------------------------------------------------------------ members (Team / Hybrid)
    def _require_owner(self, by: str) -> None:
        if not self.project.is_owner(by):
            raise PermissionError(f"ONLY_OWNERS_MANAGE_MEMBERS:{by}")

    def _log_project(self, actor: str, event: str, **data: Any) -> None:
        self._project_log.append({"seq": len(self._project_log) + 1, "at": _now(),
                                  "actor": actor, "event": event, **data})

    def project_events(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._project_log)

    def add_member(self, actor, by: str):
        self._require_owner(by)
        self.project.add_member(actor)
        self._log_project(by, "member-added", member=actor.id, kind=actor.kind, roles=list(actor.roles))
        return actor

    def remove_member(self, actor_id: str, by: str):
        """成员退出：不再被分派、不能裁决；他手上等待中的人工步骤交回，下次运行重新分派。"""
        self._require_owner(by)
        removed = self.project.remove_member(actor_id)
        self._log_project(by, "member-removed", member=actor_id)
        for wi_id, task in list(self._human_tasks.items()):
            if task["assignee"] == actor_id:
                self._human_tasks.pop(wi_id)
                self._log(self.items[wi_id], by, "assignee-removed", step=task["step"],
                          role=task["role"], former_assignee=actor_id)
        return removed

    # ------------------------------------------------------------------ human-owned steps
    def human_tasks(self, actor_id: str | None = None) -> list[dict[str, Any]]:
        return [{"workitem_id": wi_id, **task} for wi_id, task in self._human_tasks.items()
                if actor_id is None or task["assignee"] == actor_id]

    def submit_human_output(self, wi: WorkItem, actor_id: str, content: Any) -> WorkItem:
        task = self._human_tasks.get(wi.id)
        if not task:
            raise TransitionRejected("NO_HUMAN_TASK")
        if task["assignee"] != actor_id:
            raise PermissionError(f"NOT_ASSIGNEE:{actor_id}")
        if not self.project.get(actor_id).active:
            raise PermissionError(f"INACTIVE_MEMBER:{actor_id}")
        if isinstance(content, str):
            output: dict[str, Any] = {"content": content}
        elif isinstance(content, dict):
            output = dict(content)
        else:
            raise ValueError("HUMAN_OUTPUT_INVALID")
        if not (str(output.get("content", "")).strip() or output.get("items")):
            raise ValueError("EMPTY_HUMAN_OUTPUT")
        output.update(type=task["output"], skill=task["skill"], role=task["role"], placeholder=False,
                      evidence={"method": "human", "actor": actor_id})
        self._human_outputs[(wi.id, task["step"])] = output
        self._human_tasks.pop(wi.id)
        self._log(wi, actor_id, "human-output-submitted", step=task["step"], role=task["role"],
                  skill=task["skill"], output_type=task["output"])
        return self.run(wi)

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
            id=f"{self.id_prefix}-{len(self.items) + 1:04d}",
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
        if wi.id in self._human_tasks:
            return wi  # 等人工步骤的成员交付，不重复派单

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
            # Steps run in plan order; each step sees the outputs of the steps
            # before it in this round (e.g. a script follows the outline).
            outputs = []
            wi.outputs = outputs
            active_actor = wi.assignee
            try:
                for step in wi.execution_plan.steps:
                    actor = self.project.assignee_for_role(step.role)
                    active_actor = actor.id
                    if actor.kind == "human":
                        key = (wi.id, step.step)
                        if key not in self._human_outputs:
                            self._human_tasks[wi.id] = {
                                "step": step.step, "role": step.role, "skill": step.skill,
                                "output": step.output, "assignee": actor.id, "feedback": list(feedback),
                            }
                            self._log(wi, SYSTEM_RUNTIME, "human-task-assigned", step=step.step,
                                      role=step.role, skill=step.skill, assignee=actor.id)
                            return wi
                        self._log(wi, actor.id, "step-started", step=step.step,
                                  role=step.role, skill=step.skill)
                        output = dict(self._human_outputs[key])
                        outputs.append(output)
                        self._log(wi, actor.id, "step-completed", step=step.step, role=step.role,
                                  skill=step.skill, output_type=output.get("type"), placeholder=False)
                        continue
                    self._log(wi, actor.id, "step-started", step=step.step,
                              role=step.role, skill=step.skill)
                    output = self.executor.run(step, wi, feedback)
                    output.setdefault("role", step.role)
                    outputs.append(output)
                    self._log(wi, actor.id, "step-completed", step=step.step,
                              role=step.role, skill=step.skill,
                              output_type=output.get("type"),
                              placeholder=output.get("placeholder", False))
            except SkillExecutionError as error:
                # 技能执行失败（如未授权调用远程模型、模型不可用）：停在 WORKING 交给人，
                # 不产出、不重试、不把输入写进日志。
                self._feedback[wi.id] = feedback
                self._log(wi, active_actor, "executor-failed", code=error.code)
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
            # 人工步骤的产出被打回：清掉，下一轮重新交给同一岗位的人，并带上审核意见。
            for key in [k for k in self._human_outputs if k[0] == wi.id]:
                del self._human_outputs[key]
            if attempt == MAX_ATTEMPTS_PER_RUN:
                # 多轮返工仍未通过：停在 REWORK 交给人类，不无限循环。
                self._feedback[wi.id] = feedback
                self._log(wi, SYSTEM_RUNTIME, "escalated", reason="MAX_ATTEMPTS_REACHED")
                return wi
            self._move(wi, wi.assignee, WorkState.WORKING)

        gate = self.project.policy.gate_for(wi.deliverable_type)
        if gate and self.project.policy.quorum_for(gate):
            return self._request_quorum(wi, gate)
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

    def _request_quorum(self, wi: WorkItem, gate: str) -> WorkItem:
        """多人裁决：规则里的每个角色各由一位不同的人批准一次，全部到齐才交付。"""
        roles = self.project.policy.quorum_for(gate)
        action = ActionKind(gate) if gate in {a.value for a in ActionKind} else ActionKind.EXTERNAL_WRITE
        target = f"{wi.deliverable_type}@{self.project.id}"
        wi.pending_gate = gate
        wi.approver = "+".join(roles)
        pending: dict[str, Any] = {"gate": gate, "action": action, "target": target,
                                   "quorum": {}, "approved": {}, "tokens": {}}
        self._pending[wi.id] = pending
        for role in roles:
            req = self.human_gate.request(wi, action, f"{target}#{role}", wi.outputs,
                                          summary=f"{gate} ({role}): {wi.deliverable_type}")
            pending["quorum"][role] = req.id
        pending["quorum_by_request"] = {req_id: role for role, req_id in pending["quorum"].items()}
        unstaffed = [r for r in roles if not self.project.holders(r)]
        self._log(wi, SYSTEM_RUNTIME, "gate-requested", gate=gate, quorum=list(roles),
                  requests=dict(pending["quorum"]), action=action.value, target=target,
                  unstaffed_roles=unstaffed)
        return wi

    def _complete_quorum_role(self, wi: WorkItem, pending: dict[str, Any], role: str, actor_id: str) -> None:
        if actor_id in pending["approved"].values():
            raise PermissionError(f"ALREADY_APPROVED_BY_ACTOR:{actor_id}")
        req_id = pending["quorum"][role]
        token = self.human_gate.authorize(wi, req_id, pending["action"], f"{pending['target']}#{role}", wi.outputs)
        pending["approved"][role] = actor_id
        pending["tokens"][role] = token.request_id
        self._log(wi, actor_id, "decision", gate=pending["gate"], approve=True, role=role, request=req_id)

    def _deliver_if_quorum_complete(self, wi: WorkItem, pending: dict[str, Any], actor_id: str) -> WorkItem:
        if len(pending["approved"]) < len(pending["quorum"]):
            return wi
        self._pending.pop(wi.id, None)
        wi.pending_gate = None
        self._move(wi, actor_id, WorkState.DELIVERED)
        self._log(wi, actor_id, "delivered", authorizations=dict(pending["tokens"]),
                  approvers=dict(pending["approved"]))
        return wi

    def _deny_quorum(self, wi: WorkItem, pending: dict[str, Any], actor_id: str, reason: str) -> WorkItem:
        for role, req_id in pending["quorum"].items():
            if role not in pending["approved"]:
                self.human_gate.deny(req_id, actor_id, reason)
        self._pending.pop(wi.id, None)
        self._log(wi, actor_id, "decision", gate=pending["gate"], approve=False, reason=reason)
        wi.pending_gate = None
        wi.rework_count += 1
        self._move(wi, actor_id, WorkState.REWORK)
        self._feedback[wi.id] = [reason] if reason else []
        return wi

    def _route(self, wi: WorkItem) -> None:
        decision = self.router.route(wi)
        plan = self.planner.build(wi, decision)
        apply_routing(wi, decision, plan)
        producer = self.project.assignee_for_role(decision.selected_role)
        reviewer = self.project.reviewer_for(decision.industry, producer.id)
        wi.assignee = producer.id
        wi.reviewer = reviewer.id
        self._log(wi, SYSTEM_ROUTER, "route", role=decision.selected_role,
                  skills=list(decision.selected_skills), excluded=list(decision.excluded_roles),
                  assignee=producer.id, reviewer=reviewer.id, reason=decision.reason,
                  followup_role=decision.followup_role,
                  workflow_steps=[{"role": role, "skill": skill}
                                  for role, skill in decision.workflow_steps])
        self._move(wi, SYSTEM_ROUTER, WorkState.WORKING)

    # ------------------------------------------------------------------ decide
    def finalize(self, wi: WorkItem) -> WorkItem:
        """Complete a gate the human decided out of band (e.g. the approval CLI).

        The agent that called ``run`` never approves anything: it can only ask
        whether a human has. Approved → redeem the single-use authorization and
        deliver. Denied → back to REWORK. Undecided → ``AWAITING_HUMAN_APPROVAL``.
        """
        if wi.state != WorkState.APPROVED or not wi.pending_gate:
            raise TransitionRejected("NO_PENDING_GATE")
        pending = self._pending.get(wi.id)
        if pending and "quorum" in pending:
            return self._finalize_quorum(wi, pending)
        if not pending or "request" not in pending:
            raise TransitionRejected("NO_PENDING_REQUEST")
        store = self.human_gate.store
        gate = wi.pending_gate
        if store.get_request(pending["request"]) is None:
            self._pending.pop(wi.id, None)
            self._log(wi, wi.approver or SYSTEM_RUNTIME, "decision", gate=gate, approve=False,
                      reason="denied-out-of-band", request=pending["request"])
            wi.pending_gate = None
            wi.rework_count += 1
            self._move(wi, wi.approver or SYSTEM_RUNTIME, WorkState.REWORK)
            return wi
        approval = store.get_approval(pending["request"])
        if approval is None:
            raise TransitionRejected("AWAITING_HUMAN_APPROVAL")
        if not self.project.can_decide(approval.approver, gate):
            raise PermissionError(f"NOT_ALLOWED_TO_DECIDE:{approval.approver}:{gate}")
        token = self.human_gate.authorize(
            wi, pending["request"], pending["action"], pending["target"], wi.outputs
        )
        self._pending.pop(wi.id, None)
        self._log(wi, approval.approver, "decision", gate=gate, approve=True,
                  reason="approved-out-of-band", request=pending["request"])
        wi.pending_gate = None
        self._move(wi, approval.approver, WorkState.DELIVERED)
        self._log(wi, approval.approver, "delivered", authorization=token.request_id,
                  payload_digest=token.payload_digest)
        return wi

    def _finalize_quorum(self, wi: WorkItem, pending: dict[str, Any]) -> WorkItem:
        store = self.human_gate.store
        last = wi.approver or SYSTEM_RUNTIME
        for role, req_id in pending["quorum"].items():
            if role in pending["approved"]:
                continue
            if store.get_request(req_id) is None:
                return self._deny_quorum(wi, pending, wi.approver or SYSTEM_RUNTIME, "denied-out-of-band")
            approval = store.get_approval(req_id)
            if approval is None:
                continue
            if not self.project.can_decide(approval.approver, pending["gate"], role=role):
                raise PermissionError(f"NOT_ALLOWED_TO_DECIDE:{approval.approver}:{role}")
            self._complete_quorum_role(wi, pending, role, approval.approver)
            last = approval.approver
        if len(pending["approved"]) < len(pending["quorum"]):
            raise TransitionRejected("AWAITING_HUMAN_APPROVAL")
        return self._deliver_if_quorum_complete(wi, pending, last)

    def decide(self, wi: WorkItem, actor_id: str, approve: bool, reason: str = "") -> WorkItem:
        if wi.state != WorkState.APPROVED or not wi.pending_gate:
            raise TransitionRejected("NO_PENDING_GATE")
        gate = wi.pending_gate
        if not self.project.can_decide(actor_id, gate):
            raise PermissionError(f"NOT_ALLOWED_TO_DECIDE:{actor_id}:{gate}")

        pending = self._pending.get(wi.id)
        if pending and "quorum" in pending:
            if not approve:
                return self._deny_quorum(wi, pending, actor_id, reason)
            if actor_id in pending["approved"].values():
                raise PermissionError(f"ALREADY_APPROVED_BY_ACTOR:{actor_id}")
            role = next((r for r in pending["quorum"] if r not in pending["approved"]
                         and self.project.can_decide(actor_id, gate, role=r)), None)
            if role is None:
                raise PermissionError(f"NOT_ALLOWED_TO_DECIDE:{actor_id}:{gate}")
            self.human_gate.approve(pending["quorum"][role], actor_id)
            self._complete_quorum_role(wi, pending, role, actor_id)
            return self._deliver_if_quorum_complete(wi, pending, actor_id)
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
