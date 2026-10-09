"""MCP entry for Sayelf Agent Ops (stdio, local only).

Run:  python -m sayelf_agent_ops.mcp_server
Needs the optional dependency:  pip install "mcp>=1.2"

Agents can route, run, inspect and deliver work. They cannot approve: a gated
deliverable waits until the human approves it with ``approve_cli`` in a terminal.
"""
from __future__ import annotations

from typing import Any

from .service import AgentOpsService

INSTRUCTIONS = (
    "Sayelf Agent Ops 执行内核：按交付物把任务分派给专业岗位，产出者自检、独立审核、自动返工；"
    "发布等高风险交付必须等人类在终端批准（approve_cli），你无权也不应尝试批准。"
    "交付物不明确时（UNROUTABLE_DELIVERABLE）请向用户澄清，不要硬套。"
)


def _server_class():
    try:
        from mcp.server.mcpserver import MCPServer  # mcp >= 2
        return MCPServer
    except ImportError:
        from mcp.server.fastmcp import FastMCP  # mcp 1.x
        return FastMCP


def build_server(service: AgentOpsService | None = None):
    svc = service or AgentOpsService.from_env()
    server = _server_class()("sayelf-agent-ops", instructions=INSTRUCTIONS)

    @server.tool()
    def capabilities() -> dict[str, Any]:
        """List loaded industry packs, the configured model and how humans approve."""
        return svc.capabilities()

    @server.tool()
    def route_task(text: str) -> dict[str, Any]:
        """Decide which role and skills own this task, by its deliverable. Does not execute anything."""
        return svc.route(text)

    @server.tool()
    def run_task(text: str, goal: str = "") -> dict[str, Any]:
        """Run a task through the kernel: route, produce, producer self-check, independent review,
        automatic rework. Returns DELIVERED, or APPROVED with an approval_request that a human must
        approve before deliver_task. Outputs marked placeholder=true are not finished work."""
        return svc.run(text, goal or None)

    @server.tool()
    def get_task(workitem_id: str) -> dict[str, Any]:
        """Show a task's state, outputs and the append-only event log (evidence chain)."""
        return svc.get(workitem_id)

    @server.tool()
    def list_pending_approvals() -> dict[str, Any]:
        """List this session's gated deliverables still waiting for a human decision."""
        return svc.pending_approvals()

    @server.tool()
    def deliver_task(workitem_id: str) -> dict[str, Any]:
        """Deliver a gated task after the human approved it. Returns AWAITING_HUMAN_APPROVAL if not
        yet decided; a denied request sends the task back to REWORK. Never approves anything."""
        return svc.deliver(workitem_id)

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
