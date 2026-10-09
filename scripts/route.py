"""按交付物路由一条任务，输出 JSON。供 Claude Code / Codex 在共享底座里调用。

用法：
  python scripts/route.py "写 5 个公众号标题"
  python scripts/route.py --run "写 5 个公众号标题"     # 在单人项目里跑完整闭环，输出状态与事件
只做本地确定性计算，不联网、不调用模型、不写文件。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sayelf_agent_ops.actors import Project  # noqa: E402
from sayelf_agent_ops.models import WorkItem  # noqa: E402
from sayelf_agent_ops.registry import build_default_registry  # noqa: E402
from sayelf_agent_ops.router import Router  # noqa: E402
from sayelf_agent_ops.runtime import Runtime  # noqa: E402


def route(text: str) -> dict:
    wi = WorkItem(id="ROUTE", input=text, goal=text, deliverable=text)
    try:
        return {"ok": True, "decision": asdict(Router(build_default_registry()).route(wi))}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


def run(text: str, owner: str) -> dict:
    rt = Runtime(Project.solo(owner))
    try:
        wi = rt.run(rt.submit(text))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "workitem": wi.id,
        "state": wi.state,
        "role": wi.selected_role,
        "skills": wi.selected_skills,
        "assignee": wi.assignee,
        "reviewer": wi.reviewer,
        "pending_gate": wi.pending_gate,
        "approver": wi.approver,
        "outputs": wi.outputs,
        "events": rt.events(wi),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sayelf Agent Ops deliverable-first router")
    parser.add_argument("text", help="任务文本")
    parser.add_argument("--run", action="store_true", help="在单人项目中运行完整闭环")
    parser.add_argument("--owner", default="human.owner", help="单人项目的人类成员 id")
    args = parser.parse_args(argv)
    result = run(args.text, args.owner) if args.run else route(args.text)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
