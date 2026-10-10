"""Sprint 08 — durable runtime state for long-running entries (the Workspace API).

``snapshot`` turns everything a running ``Runtime`` remembers about its work
items into plain JSON; ``restore`` puts it back into a fresh Runtime built
from the same project. Approval requests and decisions already live in the
SQLite approval store, so a restart resumes exactly where people left off:
pending human tasks, quorum progress, the self-check record a gate relies on,
and the evidence log.

Plain JSON on purpose (no pickle): the file is readable, diffable and cannot
execute code when loaded.
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from .gates import AcceptanceReport, ActionKind
from .models import ExecutionPlan, PlanStep, WorkItem

FORMAT_VERSION = 1
_WORKITEM_FIELDS = {f.name for f in fields(WorkItem)}


class SnapshotError(ValueError):
    pass


def _plan_from(data: dict[str, Any] | None) -> ExecutionPlan | None:
    if data is None:
        return None
    return ExecutionPlan(
        id=data["id"],
        workitem_id=data["workitem_id"],
        steps=tuple(PlanStep(**step) for step in data["steps"]),
    )


def _workitem_from(data: dict[str, Any]) -> WorkItem:
    unknown = set(data) - _WORKITEM_FIELDS
    if unknown:
        raise SnapshotError(f"UNKNOWN_WORKITEM_FIELDS:{sorted(unknown)}")
    values = dict(data)
    values["execution_plan"] = _plan_from(values.get("execution_plan"))
    return WorkItem(**values)


def _pending_out(pending: dict[str, Any]) -> dict[str, Any]:
    out = dict(pending)
    if "action" in out:
        out["action"] = ActionKind(out["action"]).value
    return out


def _pending_in(pending: dict[str, Any]) -> dict[str, Any]:
    out = dict(pending)
    if "action" in out:
        out["action"] = ActionKind(out["action"])
    return out


def snapshot(runtime: Any) -> dict[str, Any]:
    acceptance = runtime.acceptance
    return {
        "v": FORMAT_VERSION,
        "project": runtime.project.id,
        "id_prefix": runtime.id_prefix,
        "items": [asdict(wi) for wi in runtime.items.values()],
        "events": runtime._events,
        "feedback": runtime._feedback,
        "pending": {wi_id: _pending_out(p) for wi_id, p in runtime._pending.items()},
        "human_tasks": runtime._human_tasks,
        "human_outputs": [[wi_id, step, output] for (wi_id, step), output in runtime._human_outputs.items()],
        "project_log": runtime._project_log,
        "acceptance": {
            "attempts": acceptance._attempts,
            "passed": {wi_id: asdict(report) for wi_id, report in acceptance._passed.items()},
        },
    }


def restore(runtime: Any, data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or data.get("v") != FORMAT_VERSION:
        raise SnapshotError("UNSUPPORTED_SNAPSHOT_VERSION")
    if data.get("project") != runtime.project.id:
        raise SnapshotError("SNAPSHOT_PROJECT_MISMATCH")
    items = [_workitem_from(item) for item in data["items"]]
    runtime.id_prefix = data["id_prefix"]
    runtime.items = {wi.id: wi for wi in items}
    runtime._events = {k: list(v) for k, v in data["events"].items()}
    runtime._feedback = {k: list(v) for k, v in data["feedback"].items()}
    runtime._pending = {k: _pending_in(v) for k, v in data["pending"].items()}
    runtime._human_tasks = dict(data["human_tasks"])
    runtime._human_outputs = {(wi_id, int(step)): output for wi_id, step, output in data["human_outputs"]}
    runtime._project_log = list(data["project_log"])
    acceptance = runtime.acceptance
    acceptance._attempts = {k: int(v) for k, v in data["acceptance"]["attempts"].items()}
    acceptance._passed = {
        wi_id: AcceptanceReport(**{**report, "failures": tuple(report["failures"])})
        for wi_id, report in data["acceptance"]["passed"].items()
    }


def load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
