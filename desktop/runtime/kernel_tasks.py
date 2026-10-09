"""Desktop entry for work items that run on the Agent Ops kernel (Runtime).

The router decides the engine: a work item whose deliverable is in
``KERNEL_DELIVERABLES`` can run here; everything else keeps using the
three-stage media workflow. Both share the workspace provider settings, the
per-run consent rule for remote endpoints, and the durable HumanGate store.
"""
from __future__ import annotations

import json
import re
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
from sayelf_agent_ops.skills.video_llm import make_model_handlers

KERNEL_DELIVERABLES = {
    "title-list": "标题候选",
    "video-script": "短视频脚本",
    "software-feature-package": "软件功能成果包",
}


def _routing_input(request):
    extracted = "\n".join(
        f"\n材料《{entry['name']}》识别文字：\n{entry.get('extracted_text', '')}"
        for entry in request.get("attachments", [])
        if entry.get("extracted_text")
    )
    return "\n".join((request.get("channel", ""), request["request"], extracted))


def _markdown(deliverable, outputs):
    if deliverable == "software-feature-package":
        sections = ["# 软件功能成果包", "", "> AI 生成的本地审阅材料；实现文件尚未写入仓库，测试尚未执行。", ""]
        for output in outputs:
            kind = output.get("type")
            if kind == "software-design":
                sections.extend([f"## 软件方案设计 · `{output['role']}`", "", output["summary"], "", "### 假设", ""])
                sections.extend([f"- {item}" for item in output["assumptions"]] or ["- 无"])
                sections.extend(["", "### 验收标准", ""])
                sections.extend([f"- {item}" for item in output["acceptance_criteria"]])
                sections.extend(["", "### 文件范围", ""])
                sections.extend([f"- `{item['path']}`：{item['purpose']}" for item in output["files"]])
            elif kind == "software-change":
                sections.extend(["", f"## 软件开发成果 · `{output['role']}`", "", output["summary"], ""])
                for item in output["files"]:
                    candidate = item["path"].rsplit(".", 1)[-1] if "." in item["path"] else "text"
                    suffix = candidate if candidate.isalnum() and len(candidate) <= 16 else "text"
                    ticks = max((len(run) for run in re.findall(r"`+", item["content"])), default=2) + 1
                    fence = "`" * max(3, ticks)
                    sections.extend([f"### `{item['path']}`", "", f"{fence}{suffix}", item["content"], fence, ""])
                if output["limitations"]:
                    sections.extend(["### 已知限制", "", *[f"- {item}" for item in output["limitations"]], ""])
                if output["apply_instructions"]:
                    sections.extend(["### 应用说明", "", *[f"- {item}" for item in output["apply_instructions"]], ""])
            elif kind == "software-test-report":
                sections.extend(["", f"## QA 测试与审查 · `{output['role']}`", "", output["review_summary"], "",
                                 f"验证状态：**{output['verification_state']}（未执行）**", ""])
                for index, case in enumerate(output["test_cases"], 1):
                    sections.extend([f"### {index}. {case['name']}", "",
                                     *[f"{step_no}. {step}" for step_no, step in enumerate(case["steps"], 1)],
                                     f"预期结果：{case['expected']}", ""])
                sections.extend(["### 风险", "", *([f"- {item}" for item in output["risks"]] or ["- 未列出"]), ""])
        return "\n".join(sections).rstrip() + "\n"
    if deliverable == "title-list":
        titles = next(o["items"] for o in outputs if o.get("type") == "title-list")
        body = "# 标题候选\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(titles, 1))
    else:
        script = next(o for o in outputs if o.get("type") == "video-script")
        outline = next((o["items"] for o in outputs if o.get("type") == "outline"), [])
        body = script["content"] + "\n## 内容大纲\n\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(outline, 1))
    return body + "\n\n由模型生成，经产出者自检与独立审核；发布前请人工确认事实与平台规范。\n"


def run_kernel_task(path, workitem_id, provider, allow_external=False):
    workitem_id = bootstrap._validate_workitem_id(workitem_id)
    status = bootstrap.health(path)
    if status["pack"] not in ("media", "software"):
        raise bootstrap.BootstrapError("WORKFLOW_INVALID")
    root = bootstrap.data_root(status["data_dir"])
    request = bootstrap._load_workitem_request(root, root / "workitems" / workitem_id / "request.json")
    text = _routing_input(request)

    pack = status["pack"]
    registry = build_registry((pack,))
    with bootstrap._opened(root) as connection:
        bootstrap._activate_registered_roles(connection, registry, pack)
    probe = WorkItem(id=workitem_id, input=text, goal=request["request"], deliverable=text)
    try:
        decision = Router(registry).route(probe)
    except ValueError:
        raise bootstrap.BootstrapError("UNROUTABLE_DELIVERABLE") from None
    if decision.deliverable_type not in KERNEL_DELIVERABLES:
        raise bootstrap.BootstrapError("UNROUTABLE_DELIVERABLE")
    required_roles = tuple(dict.fromkeys(role for role, _ in decision.workflow_steps)) or (decision.selected_role,)
    missing_roles = [role_id for role_id in required_roles if role_id not in registry.active_role_ids]
    if missing_roles:
        raise bootstrap.BootstrapError("ROLE_NOT_ACTIVE")

    config = bootstrap.provider_status(root)
    remote = not is_local_endpoint(config["endpoint"])
    if remote and allow_external is not True:
        # Checked before any model call: nothing leaves the device without consent.
        raise bootstrap.BootstrapError("MODEL_CONSENT_REQUIRED")
    handlers = make_model_handlers(provider, remote=remote, consent=allow_external is True)
    runtime = Runtime(
        Project.solo(LOCAL_HUMAN, registry=registry),
        registry=registry,
        executor=BuiltinExecutor(handlers, registry=registry),
        approval_store=SQLiteApprovalStore(root),
    )
    wi = runtime.run(runtime.submit(text, goal=request["request"], industry="media"))
    events = runtime.events(wi)
    failed = [e for e in events if e["event"] == "executor-failed"]

    task_id = f"KT-{uuid.uuid4().hex[:12]}"
    deliverable = decision.deliverable_type
    record = {
        "task_id": task_id,
        "workitem_id": workitem_id,
        "deliverable_type": deliverable,
        "state": wi.state,
        "assignee": wi.assignee,
        "reviewer": wi.reviewer,
        "rework_count": wi.rework_count,
        # Events carry codes, digests and actor ids only; request text stays out of the log.
        "events": [{k: v for k, v in e.items() if k != "input"} for e in events],
    }
    (root / "logs" / f"{task_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    roles = bootstrap._role_details(registry, pack)
    if wi.state == "DELIVERED":
        content = _markdown(deliverable, wi.outputs)
        output_path = root / "outputs" / f"{workitem_id}-{deliverable}-{task_id}.md"
        output_path.write_text(content, encoding="utf-8")
        return {
            "code": 0,
            "msg": f"{KERNEL_DELIVERABLES[deliverable]}已生成，并通过产出者自检与独立审核。",
            "data": {**record, "kernel_result": True, "label": KERNEL_DELIVERABLES[deliverable],
                     "result_content": content, "output_name": output_path.name, "roles": roles},
        }
    reason = failed[-1]["code"] if failed else "REVIEW_NOT_PASSED"
    return {
        "code": 20,
        "msg": bootstrap.MESSAGES.get(reason, "多轮审核仍未通过，已停下交给你处理；可调整需求后重试。"),
        "data": {**record, "reason": reason, "roles": roles},
    }
