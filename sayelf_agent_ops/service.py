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

from .actors import Project
from .approvals_sqlite import SQLiteApprovalStore
from .executor import BuiltinExecutor
from .gates import GateRejected
from .models import WorkItem
from .registry import available_industries, build_registry
from .router import Router
from .runtime import Runtime
from .state import TransitionRejected

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
        self.registry = build_registry(packs)
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
        return {"ok": True, "decision": asdict(decision)}

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
