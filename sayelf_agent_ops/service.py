"""Entry-neutral service layer: what any agent-facing entry (MCP, future HTTP
API) may do with the kernel. It deliberately has no approve/deny operation —
human decisions happen only through ``approve_cli`` or the desktop app.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .actors import Actor, Project
from .approvals_sqlite import SQLiteApprovalStore
from .executor import BuiltinExecutor
from .gates import GateRejected
from .models import WorkItem
from .registry import available_industries, build_registry
from .role_updates import RoleUpdateStore
from .router import Router
from .runtime import Runtime
from .state import TransitionRejected
from .workflow_contract import (
    REQUIRED_EXECUTION_EVIDENCE,
    build_workflow_contract,
    validate_host_evidence,
    validate_workflow_contract,
)

DEFAULT_OWNER = "human.owner"
MAX_TEXT = 20_000


def default_home() -> Path:
    return Path(os.environ.get("SAYELF_AGENT_OPS_HOME") or Path.home() / ".sayelf" / "agent-ops")


def owner_id() -> str:
    return os.environ.get("SAYELF_OWNER") or DEFAULT_OWNER


def approval_store(home: Path | None = None) -> SQLiteApprovalStore:
    return SQLiteApprovalStore.at_path((home or default_home()) / "agent-ops.sqlite3")


def _error(code: str) -> dict[str, Any]:
    return {"ok": False, "error": code}


class AgentOpsService:
    def __init__(
        self,
        home: Path | None = None,
        owner: str | None = None,
        packs: tuple[str, ...] | None = None,
        provider: Any | None = None,
        remote: bool = False,
        allow_remote: bool = False,
        generic_skills: bool = True,
    ):
        self.home = home or default_home()
        self.owner = owner or owner_id()
        self.store = approval_store(self.home)
        self.role_updates = RoleUpdateStore(self.home / "role-updates.sqlite3")
        self.registry = build_registry(packs)
        self.role_updates.load_into(self.registry)
        # Consent for a remote model is given once, by the human, in the
        # server configuration (allow_remote) — never by the agent.
        from .providers.config import ModelSetup, model_handlers

        handlers, fallback = model_handlers(
            ModelSetup(provider, remote, allow_remote, generic_skills, "args"), self.registry)
        self.model = getattr(provider, "model", None)
        self.runtime = Runtime(
            Project.solo(self.owner, registry=self.registry),
            registry=self.registry,
            executor=BuiltinExecutor(handlers, registry=self.registry, fallback=fallback),
            approval_store=self.store,
            id_prefix=f"WI-{uuid.uuid4().hex[:6]}",
        )

    @classmethod
    def from_env(cls) -> "AgentOpsService":
        packs_env = os.environ.get("SAYELF_PACKS", "").strip()
        packs = tuple(p.strip() for p in packs_env.split(",") if p.strip()) or None
        from .providers.config import ModelConfigError, ModelSetup, load_model

        try:
            setup, error = load_model(default_home()), None
        except ModelConfigError as exc:
            # Start anyway (MCP hosts would only see a dead server) and say why.
            setup, error = ModelSetup(None, False, False, False, "none"), str(exc)
        svc = cls(packs=packs, provider=setup.provider, remote=setup.remote,
                  allow_remote=setup.consent, generic_skills=setup.generic_skills)
        svc.model_error = error
        return svc

    # ------------------------------------------------------------------ views
    def _summary(self, wi: WorkItem, with_events: bool = False) -> dict[str, Any]:
        pending = self.runtime._pending.get(wi.id, {})
        data = {
            "ok": True,
            "workitem_id": wi.id,
            "state": wi.state,
            "deliverable_type": wi.deliverable_type,
            "role": wi.selected_role,
            "skills": list(wi.selected_skills),
            "assignee": wi.assignee,
            "reviewer": wi.reviewer,
            "rework_count": wi.rework_count,
            "pending_gate": wi.pending_gate,
            "approval_request": pending.get("request"),
            "outputs": wi.outputs,
            "next_step": self._next_step(wi, pending),
        }
        if with_events:
            data["events"] = self.runtime.events(wi)
        return data

    def _next_step(self, wi: WorkItem, pending: dict[str, Any]) -> str:
        if wi.state == "DELIVERED":
            return "已交付。"
        if wi.state == "APPROVED" and wi.pending_gate:
            return (f"等待人工批准：请人类在终端运行 `python -m sayelf_agent_ops.approve_cli approve "
                    f"{pending.get('request')}`，批准后再调用 deliver_task。Agent 无权批准。")
        if wi.state == "REWORK":
            return "多轮审核未通过或被人工驳回：调整需求后可再次 run_task。"
        if wi.state == "WORKING":
            return "技能执行失败或被阻断，见 events 中的 executor-failed / skills-blocked。"
        return ""

    # ------------------------------------------------------------------ operations
    def capabilities(self) -> dict[str, Any]:
        return {
            "ok": True,
            "loaded_packs": list(self.registry.loaded_industries),
            "available_packs": list(available_industries()),
            "model": self.model,
            "model_error": getattr(self, "model_error", None),
            "owner": self.owner,
            "human_approval": "python -m sayelf_agent_ops.approve_cli (interactive terminal only)",
        }

    def route(self, text: str) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            return _error("INVALID_INPUT")
        try:
            decision = Router(self.registry).route(WorkItem(id="ROUTE", input=text, goal=text, deliverable=text))
        except ValueError as error:
            return _error(str(error).split(":")[0])
        from .planner import MinimumPlanner

        plan = MinimumPlanner(self.registry).build(WorkItem(id="ROUTE", input=text), decision)
        workflow_contract = build_workflow_contract(text, decision, plan, self.registry)
        workflow_validation = validate_workflow_contract(workflow_contract)
        evidence_template = {
            "schema": "host-execution-evidence-v1",
            "status": "not_run",
            "source_revision": "host-must-record",
            "route_digest": "host-must-record",
            "steps": [],
            "changed_files": [],
            "verification": [],
            "producer_self_check": {"status": "not_run"},
            "independent_review": {"status": "not_run"},
            "limitations": ["route_task only creates a plan; Codex has not executed it."],
        }
        return {
            "ok": True,
            "decision": asdict(decision),
            "workflow_contract": workflow_contract,
            "workflow_validation": workflow_validation,
            "host_execution_evidence": {
                "schema": evidence_template["schema"],
                "status": evidence_template["status"],
                "required_fields": list(REQUIRED_EXECUTION_EVIDENCE),
                "template": evidence_template,
                "validation": validate_host_evidence(evidence_template),
            },
            "host_execution": {
                "executor": "codex", "status": "planned", "execute_tool": None,
                "steps": [asdict(step) for step in plan.steps],
                "instructions": [
                    "Codex performs only the minimum listed skills, using the industry-specific role contracts; one AI role may own multiple ordered steps.",
                    "Do not call run_task or a model provider for this host workflow.",
                    "Record changed files or deliverables and actual verification evidence; mark unrun checks not_run.",
                    "Producer self-check and independent review are required; a role label alone does not establish reviewer independence.",
                    "If an independent reviewer is unavailable, report review_pending; do not claim the loop is complete.",
                    "Publishing, deployment and other gated external actions require specific human authorization.",
                ],
                "required_evidence": list(REQUIRED_EXECUTION_EVIDENCE),
            },
        }

    def validate_workflow_plan(self, contract: Any) -> dict[str, Any]:
        """Validate a workflow contract without executing it or persisting input."""
        return validate_workflow_contract(contract)

    def validate_host_execution_evidence(self, evidence: Any) -> dict[str, Any]:
        """Validate Codex host evidence; a pending review is never success."""
        return validate_host_evidence(evidence)

    def reconcile_role_suggestion(self, **suggestion: Any) -> dict[str, Any]:
        """Verify and locally apply a user role backed by a registered skill."""
        result = self.role_updates.reconcile(self.registry, **suggestion)
        if result.get("ok") and result.get("status") == "applied":
            role_id = result["role_id"]
            self.runtime.project.members.append(Actor(
                id=f"agent.{role_id}", kind="agent", roles=(role_id,),
                name=result["suggested_name"],
            ))
        return result

    def registered_roles(self) -> dict[str, Any]:
        return {"ok": True, "roles": [
            {"id": role.id, "industry": role.industry, "name": role.name,
             "responsibility": role.responsibility, "outputs": list(role.owned_outputs),
             "skills": list(role.allowed_skills), "forbidden_scope": list(role.forbidden_scope)}
            for role in self.registry.roles.values()
        ]}

    def role_updates_status(self) -> dict[str, Any]:
        return self.role_updates.list_updates()

    def revoke_role_update(self, update_id: str) -> dict[str, Any]:
        result = self.role_updates.revoke(self.registry, update_id)
        if result.get("ok") and result.get("role_id"):
            actor_id = f"agent.{result['role_id']}"
            self.runtime.project.members[:] = [m for m in self.runtime.project.members if m.id != actor_id]
        return result

    def run(self, text: str, goal: str | None = None) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            return _error("INVALID_INPUT")
        try:
            wi = self.runtime.submit(text, goal=goal or None)
        except ValueError as error:
            return _error(str(error).split(":")[0])
        return self._summary(self.runtime.run(wi))

    def get(self, workitem_id: str) -> dict[str, Any]:
        wi = self.runtime.items.get(workitem_id)
        return self._summary(wi, with_events=True) if wi else _error("UNKNOWN_WORKITEM")

    def pending_approvals(self) -> dict[str, Any]:
        mine = {wi_id: p["request"] for wi_id, p in self.runtime._pending.items() if "request" in p}
        rows = [r for r in self.store.list_requests(open_only=True) if r["request_id"] in mine.values()]
        return {"ok": True, "pending": rows}

    def deliver(self, workitem_id: str) -> dict[str, Any]:
        wi = self.runtime.items.get(workitem_id)
        if wi is None:
            return _error("UNKNOWN_WORKITEM")
        try:
            self.runtime.finalize(wi)
        except (TransitionRejected, GateRejected, PermissionError) as error:
            return {**self._summary(wi), "ok": False, "error": str(error).split(":")[0]}
        return self._summary(wi)
