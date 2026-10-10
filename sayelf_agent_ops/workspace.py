"""Sprint 07 — Workspace service: the kernel as seen by a product workbench.

A product workbench (BuildCostIQ first) shows its own industry UI and calls
this layer for everything team-shaped: who is on the project, what is waiting
for whom, and human decisions. Every call carries an ``actor_id`` that the
entry layer resolved from a credential — never from the request body — so a
person can only act as themselves.

Two entries, two audiences:

* MCP (``mcp_server``)       — AI hosts. Can route/run/read; cannot decide.
* Workspace API (this layer) — people, through a product UI. Can submit human
  steps and decide gates, each check done by the kernel's own rules.

Everything survives a restart: membership and approval rules in
``<home>/workspace/project.json``, work items / human tasks / quorum progress /
evidence in ``<home>/workspace/state.json`` (Sprint 08), approvals in SQLite
(shared with the MCP entry).
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from .actors import OWNER_ROLE, Actor, Project
from .executor import BuiltinExecutor
from .gates import GateRejected
from .models import WorkItem
from .registry import build_registry
from .runtime import Runtime
from . import runtime_store
from .service import MAX_TEXT, approval_store, default_home
from .state import TransitionRejected, WorkState

MAX_MEMBER_ID = 64
MAX_NAME = 64
MAX_ROLES = 12


class WorkspaceError(Exception):
    """A refused operation. ``status`` maps to an HTTP status code."""

    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code = code
        self.status = status


def _code(error: Exception) -> str:
    return str(error.args[0] if error.args else error).split(":")[0].strip("'\"")


def _valid_id(value: Any) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= MAX_MEMBER_ID
            and all(c.isalnum() or c in ".-_" for c in value))


def workspace_dir(home: Path | None = None) -> Path:
    return (home or default_home()) / "workspace"


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class WorkspaceService:
    def __init__(
        self,
        spec: dict[str, Any] | None = None,
        home: Path | None = None,
        packs: tuple[str, ...] | None = None,
        handlers: dict[str, Any] | None = None,
        model: Any | None = None,
    ):
        self.home = home or default_home()
        self.project_file = workspace_dir(self.home) / "project.json"
        self.state_file = workspace_dir(self.home) / "state.json"
        self.registry = build_registry(packs)
        if self.project_file.exists():
            spec = json.loads(self.project_file.read_text(encoding="utf-8"))
        elif spec is None:
            raise WorkspaceError("NO_PROJECT_SPEC", 500)
        project = Project.from_spec(spec, registry=self.registry)
        # Model port: with a model configured, skills run on it directly —
        # no AI host platform needed. Without one, placeholders stay honest.
        from .providers.config import ModelSetup, model_handlers

        self.model = model or ModelSetup(None, False, False, False, "none")
        model_skill_handlers, fallback = model_handlers(self.model, self.registry)
        all_handlers = {**model_skill_handlers, **(handlers or {})}
        self.runtime = Runtime(
            project,
            registry=self.registry,
            executor=BuiltinExecutor(all_handlers, registry=self.registry, fallback=fallback),
            approval_store=approval_store(self.home),
            id_prefix=f"WI-{uuid.uuid4().hex[:6]}",
        )
        self._lock = threading.RLock()
        saved = runtime_store.load(self.state_file)
        if saved is not None:
            try:
                runtime_store.restore(self.runtime, saved)
            except (KeyError, TypeError, ValueError) as error:
                # Never start over silently: people's pending work would vanish.
                raise WorkspaceError(f"STATE_UNREADABLE:{_code(error)}", 500) from None
        self._save_project()

    @property
    def project(self) -> Project:
        return self.runtime.project

    def _save_state(self) -> None:
        _write_json_atomic(self.state_file, runtime_store.snapshot(self.runtime))

    def _save_project(self) -> None:
        spec = self.project.to_spec()
        spec["include_default_agents"] = True
        _write_json_atomic(self.project_file, spec)

    # ------------------------------------------------------------------ identity
    def member(self, actor_id: str) -> Actor:
        try:
            actor = self.project.get(actor_id)
        except KeyError:
            raise WorkspaceError("UNKNOWN_MEMBER", 401) from None
        if actor.kind != "human":
            raise WorkspaceError("AGENTS_HAVE_NO_WORKSPACE_ACCESS", 403)
        if not actor.active:
            raise WorkspaceError("INACTIVE_MEMBER", 403)
        return actor

    def _item(self, workitem_id: str) -> WorkItem:
        wi = self.runtime.items.get(workitem_id) if isinstance(workitem_id, str) else None
        if wi is None:
            raise WorkspaceError("UNKNOWN_WORKITEM", 404)
        return wi

    # ------------------------------------------------------------------ views
    @staticmethod
    def _actor_view(actor: Actor) -> dict[str, Any]:
        return {"id": actor.id, "kind": actor.kind, "name": actor.name, "roles": list(actor.roles),
                "active": actor.active, "owner": actor.kind == "human" and OWNER_ROLE in actor.roles}

    def _gate_view(self, wi: WorkItem, viewer: str) -> dict[str, Any] | None:
        pending = self.runtime._pending.get(wi.id)
        if not pending or wi.state != WorkState.APPROVED:
            return None
        gate = pending["gate"]
        if "quorum" in pending:
            roles = [{
                "role": role,
                "approved_by": pending["approved"].get(role),
                "holders": [m.id for m in self.project.holders(role)],
            } for role in pending["quorum"]]
            can = (viewer not in pending["approved"].values() and any(
                r["approved_by"] is None and self.project.can_decide(viewer, gate, role=r["role"])
                for r in roles))
            return {"gate": gate, "kind": "quorum", "roles": roles, "can_decide": can,
                    "action": pending["action"].value, "target": pending["target"]}
        return {"gate": gate, "kind": "single", "approver": wi.approver,
                "can_decide": self.project.can_decide(viewer, gate),
                "action": pending["action"].value, "target": pending["target"]}

    def _workitem_view(self, wi: WorkItem, viewer: str, detail: bool = False) -> dict[str, Any]:
        task = self.runtime._human_tasks.get(wi.id)
        steps = []
        if wi.execution_plan is not None:
            steps = [{"step": s.step, "role": s.role, "skill": s.skill, "output": s.output}
                     for s in wi.execution_plan.steps]
        data: dict[str, Any] = {
            "id": wi.id,
            "input": wi.input,
            "state": wi.state,
            "industry": wi.industry,
            "deliverable_type": wi.deliverable_type,
            "role": wi.selected_role,
            "owner": wi.owner,
            "assignee": wi.assignee,
            "reviewer": wi.reviewer,
            "rework_count": wi.rework_count,
            "steps": steps,
            "waiting_for": ({"kind": "human-task", "assignee": task["assignee"], "step": task["step"],
                             "role": task["role"]} if task else None),
            "gate": self._gate_view(wi, viewer),
        }
        if detail:
            data["outputs"] = wi.outputs
            data["events"] = self.runtime.events(wi)
        return data

    # ------------------------------------------------------------------ reads
    def me(self, actor_id: str) -> dict[str, Any]:
        with self._lock:
            return {"member": self._actor_view(self.member(actor_id)), "project": self.project.id}

    def project_view(self, actor_id: str) -> dict[str, Any]:
        with self._lock:
            self.member(actor_id)
            spec = self.project.to_spec()
            return {
                "id": self.project.id,
                "members": [self._actor_view(m) for m in self.project.members],
                "policy": spec["policy"],
                "packs": list(self.registry.loaded_industries),
            }

    def capabilities(self, actor_id: str) -> dict[str, Any]:
        with self._lock:
            self.member(actor_id)
            return {"packs": list(self.registry.loaded_industries), "model": self.model.describe()}

    def project_events(self, actor_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self.member(actor_id)
            return self.runtime.project_events()

    def list_workitems(self, actor_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self.member(actor_id)
            return [self._workitem_view(wi, actor_id) for wi in reversed(list(self.runtime.items.values()))]

    def get_workitem(self, actor_id: str, workitem_id: str) -> dict[str, Any]:
        with self._lock:
            self.member(actor_id)
            return self._workitem_view(self._item(workitem_id), actor_id, detail=True)

    def my_tasks(self, actor_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self.member(actor_id)
            return self.runtime.human_tasks(actor_id)

    def my_approvals(self, actor_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self.member(actor_id)
            rows = []
            for wi in self.runtime.items.values():
                gate = self._gate_view(wi, actor_id)
                if gate and gate["can_decide"]:
                    rows.append(self._workitem_view(wi, actor_id))
            return rows

    # ------------------------------------------------------------------ work
    def submit(self, actor_id: str, text: Any) -> dict[str, Any]:
        with self._lock:
            self.member(actor_id)
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                raise WorkspaceError("INVALID_INPUT")
            try:
                wi = self.runtime.submit(text, submitted_by=actor_id)
            except ValueError as error:
                raise WorkspaceError(_code(error), 422) from None
            wi = self.runtime.run(wi)
            self._save_state()
            return self._workitem_view(wi, actor_id, detail=True)

    def submit_task(self, actor_id: str, workitem_id: str, content: Any) -> dict[str, Any]:
        with self._lock:
            self.member(actor_id)
            wi = self._item(workitem_id)
            if isinstance(content, str) and len(content) > MAX_TEXT:
                raise WorkspaceError("INVALID_INPUT")
            if isinstance(content, dict) and len(json.dumps(content, ensure_ascii=False)) > MAX_TEXT:
                raise WorkspaceError("INVALID_INPUT")
            try:
                wi = self.runtime.submit_human_output(wi, actor_id, content)
            except PermissionError as error:
                raise WorkspaceError(_code(error), 403) from None
            except TransitionRejected as error:
                raise WorkspaceError(_code(error), 409) from None
            except ValueError as error:
                raise WorkspaceError(_code(error), 422) from None
            self._save_state()
            return self._workitem_view(wi, actor_id, detail=True)

    def decide(self, actor_id: str, workitem_id: str, approve: Any, reason: Any = "") -> dict[str, Any]:
        with self._lock:
            self.member(actor_id)
            if not isinstance(approve, bool):
                raise WorkspaceError("INVALID_INPUT")
            if not isinstance(reason, str) or len(reason) > 2000:
                raise WorkspaceError("INVALID_INPUT")
            if not approve and not reason.strip():
                raise WorkspaceError("REASON_REQUIRED_TO_RETURN")
            wi = self._item(workitem_id)
            try:
                wi = self.runtime.decide(wi, actor_id, approve, reason.strip())
            except PermissionError as error:
                raise WorkspaceError(_code(error), 403) from None
            except (TransitionRejected, GateRejected) as error:
                raise WorkspaceError(_code(error), 409) from None
            self._save_state()
            return self._workitem_view(wi, actor_id, detail=True)

    # ------------------------------------------------------------------ members
    def add_member(self, actor_id: str, data: Any) -> dict[str, Any]:
        with self._lock:
            self.member(actor_id)
            if not isinstance(data, dict):
                raise WorkspaceError("INVALID_INPUT")
            member_id, name, roles = data.get("id"), data.get("name", ""), data.get("roles", [])
            if not _valid_id(member_id) or not member_id.startswith("human."):
                raise WorkspaceError("INVALID_MEMBER_ID")
            if not isinstance(name, str) or len(name) > MAX_NAME:
                raise WorkspaceError("INVALID_INPUT")
            if (not isinstance(roles, list) or not roles or len(roles) > MAX_ROLES
                    or not all(_valid_id(r) for r in roles)):
                raise WorkspaceError("INVALID_ROLES")
            try:
                actor = self.runtime.add_member(
                    Actor(id=member_id, kind="human", roles=tuple(dict.fromkeys(roles)), name=name.strip()),
                    by=actor_id)
            except PermissionError as error:
                raise WorkspaceError(_code(error), 403) from None
            except ValueError as error:
                raise WorkspaceError(_code(error), 409) from None
            self._save_project()
            self._save_state()
            return self._actor_view(actor)

    def remove_member(self, actor_id: str, member_id: str) -> dict[str, Any]:
        with self._lock:
            self.member(actor_id)
            try:
                actor = self.runtime.remove_member(member_id, by=actor_id)
            except PermissionError as error:
                raise WorkspaceError(_code(error), 403) from None
            except KeyError:
                raise WorkspaceError("UNKNOWN_MEMBER", 404) from None
            except ValueError as error:
                raise WorkspaceError(_code(error), 409) from None
            self._save_project()
            self._save_state()
            return self._actor_view(actor)
