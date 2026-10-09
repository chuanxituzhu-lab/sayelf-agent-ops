"""Desktop entry for tasks that run on the Agent Ops kernel (Runtime).

First task: title generation with the configured chat model. It reuses the
workspace provider settings, the per-run consent rule for remote endpoints,
and the durable HumanGate store.
"""
from __future__ import annotations

import json
import uuid

from desktop.runtime import bootstrap
from desktop.runtime.approvals import LOCAL_HUMAN, SQLiteApprovalStore
from desktop.runtime.model_provider import is_local_endpoint
from sayelf_agent_ops.actors import Project
from sayelf_agent_ops.executor import BuiltinExecutor
from sayelf_agent_ops.models import WorkItem
from sayelf_agent_ops.registry import build_registry
from sayelf_agent_ops.router import Router
from sayelf_agent_ops.runtime import Runtime
from sayelf_agent_ops.skills.title_llm import make_llm_title_handler

TITLE_ROLE = "media.content-planner"
MAX_TEXT = 2_000


def run_titles(path, text, provider, allow_external=False):
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise bootstrap.BootstrapError("INVALID_WORKITEM")
    status = bootstrap.health(path)
    if status["pack"] != "media":
        raise bootstrap.BootstrapError("WORKFLOW_INVALID")
    root = bootstrap.data_root(status["data_dir"])
    registry = build_registry(("media",))
    with bootstrap._opened(root) as connection:
        bootstrap._activate_registered_roles(connection, registry, "media")
    if TITLE_ROLE not in registry.active_role_ids:
        raise bootstrap.BootstrapError("ROLE_NOT_ACTIVE")

    probe = WorkItem(id="PROBE", input=text, goal=text, deliverable=text)
    try:
        decision = Router(registry).route(probe)
    except ValueError:
        raise bootstrap.BootstrapError("UNROUTABLE_DELIVERABLE") from None
    if decision.deliverable_type != "title-list":
        raise bootstrap.BootstrapError("UNROUTABLE_DELIVERABLE")

    config = bootstrap.provider_status(root)
    remote = not is_local_endpoint(config["endpoint"])
    if remote and allow_external is not True:
        # Checked before any model call: nothing leaves the device without consent.
        raise bootstrap.BootstrapError("MODEL_CONSENT_REQUIRED")
    handler = make_llm_title_handler(provider, remote=remote, consent=allow_external is True)
    runtime = Runtime(
        Project.solo(LOCAL_HUMAN),
        registry=registry,
        executor=BuiltinExecutor({"media.title-writing": handler}, registry=registry),
        approval_store=SQLiteApprovalStore(root),
    )
    wi = runtime.run(runtime.submit(text, industry="media"))
    events = runtime.events(wi)
    failed = [e for e in events if e["event"] == "executor-failed"]
    titles = next((o.get("items", []) for o in wi.outputs if o.get("type") == "title-list"), [])

    task_id = f"TITLES-{uuid.uuid4().hex[:12]}"
    record = {
        "task_id": task_id,
        "state": wi.state,
        "titles": titles if wi.state == "DELIVERED" else [],
        "assignee": wi.assignee,
        "reviewer": wi.reviewer,
        "rework_count": wi.rework_count,
        # Events carry codes, digests and actor ids only; the request text is not stored here.
        "events": [{k: v for k, v in e.items() if k != "input"} for e in events],
    }
    log_path = root / "logs" / f"{task_id}.json"
    log_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    if wi.state == "DELIVERED":
        output_path = root / "outputs" / f"{task_id}.md"
        output_path.write_text(
            "# 标题候选\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(titles, 1))
            + "\n\n由模型生成，经产出者自检与独立审核；发布前请人工确认。\n",
            encoding="utf-8",
        )
        return {"code": 0, "msg": "标题已生成并通过自检与独立审核。",
                "data": {**record, "output_path": str(output_path)}}
    reason = failed[-1]["code"] if failed else "REVIEW_NOT_PASSED"
    return {
        "code": 20,
        "msg": bootstrap.MESSAGES.get(reason, "标题多轮审核未通过，已停下交给你处理。"),
        "data": {**record, "reason": reason},
    }
