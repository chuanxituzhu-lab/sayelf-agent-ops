"""Human-only approval for gated deliverables (the MCP server cannot approve).

  python -m sayelf_agent_ops.approve_cli list
  python -m sayelf_agent_ops.approve_cli approve <request_id>
  python -m sayelf_agent_ops.approve_cli deny <request_id> [--reason TEXT]

approve/deny require an interactive terminal and a typed confirmation, so an
agent calling tools cannot decide on your behalf by piping input.
"""
from __future__ import annotations

import argparse
import sys

from .gates import GateRejected, HumanGate
from .service import approval_store, default_home, owner_id


class _NotUsed:
    def passed_report(self, workitem):  # approve/deny never check acceptance
        return None


def _gate(store, owner):
    return HumanGate(_NotUsed(), approver_policy=lambda approver, req: approver == owner, store=store)


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sayelf-approve", description="Sayelf Agent Ops 人工批准")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出等待人工决定的请求")
    for name in ("approve", "deny"):
        p = sub.add_parser(name)
        p.add_argument("request_id")
        if name == "deny":
            p.add_argument("--reason", default="")
    args = parser.parse_args(argv)

    store = approval_store(default_home())
    owner = owner_id()
    if args.command == "list":
        rows = store.list_requests(open_only=True)
        if not rows:
            print("没有等待决定的请求。")
        for r in rows:
            state = "已批准，待交付" if r["approver"] else "待决定"
            print(f"{r['request_id']}  [{state}]  {r['action']} → {r['target']}\n"
                  f"    {r['summary']}  · 产出摘要 {r['payload_digest'][:12]}…  · {r['created_at']}")
        return 0

    if not _interactive():
        print("拒绝：批准/驳回只能在交互式终端由人完成。", file=sys.stderr)
        return 3
    req = store.get_request(args.request_id)
    if req is None:
        print("找不到该请求，或它已被驳回。", file=sys.stderr)
        return 2
    print(f"请求：{req.id}\n动作：{req.action.value}\n目标：{req.target}\n说明：{req.summary}\n"
          f"产出摘要：{req.payload_digest}\n批准人：{owner}")
    word = "yes" if args.command == "approve" else "deny"
    if input(f"确认{'批准' if word == 'yes' else '驳回'}？输入 {word} 继续：").strip() != word:
        print("已取消，未做任何改动。")
        return 1
    gate = _gate(store, owner)
    try:
        if args.command == "approve":
            approval = gate.approve(req.id, owner)
            print(f"已批准，{approval.expires_at.isoformat()} 前有效，只能使用一次。让 Agent 调用 deliver_task 完成交付。")
        else:
            gate.deny(req.id, owner, args.reason)
            print("已驳回。任务会退回返工。")
    except GateRejected as error:
        print(f"未执行：{error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
