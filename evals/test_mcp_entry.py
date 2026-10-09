"""MCP / service entry: agents can run and deliver, only a human in a terminal can approve."""
from __future__ import annotations

import asyncio
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sayelf_agent_ops import approve_cli
from sayelf_agent_ops.service import AgentOpsService

HAS_MCP = importlib.util.find_spec("mcp") is not None
ROOT = Path(__file__).resolve().parents[1]
PUBLISH = "把已确认的文章整理成公众号草稿发布准备包"


def cli(args, home, owner="human.owner", tty=False, answer="yes"):
    out, err = io.StringIO(), io.StringIO()
    env = {"SAYELF_AGENT_OPS_HOME": str(home), "SAYELF_OWNER": owner}
    with patch.dict(os.environ, env), patch.object(approve_cli, "_interactive", return_value=tty), \
            patch("builtins.input", return_value=answer), redirect_stdout(out), redirect_stderr(err):
        code = approve_cli.main(args)
    return code, out.getvalue() + err.getvalue()


class ServiceEntryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "agent-ops"
        self.svc = AgentOpsService(home=self.home, owner="human.owner")

    def test_s01_low_risk_task_delivers_without_human(self):
        result = self.svc.run("写 5 个公众号标题")
        self.assertEqual("DELIVERED", result["state"])
        self.assertNotEqual(result["assignee"], result["reviewer"])

    def test_s02_gated_task_waits_for_terminal_approval_then_delivers(self):
        run = self.svc.run(PUBLISH)
        self.assertEqual("APPROVED", run["state"])
        request_id = run["approval_request"]
        self.assertIn("approve_cli approve", run["next_step"])
        self.assertEqual("AWAITING_HUMAN_APPROVAL", self.svc.deliver(run["workitem_id"])["error"])
        self.assertEqual([request_id], [r["request_id"] for r in self.svc.pending_approvals()["pending"]])
        code, _ = cli(["approve", request_id], self.home, tty=True)
        self.assertEqual(0, code)
        delivered = self.svc.deliver(run["workitem_id"])
        self.assertEqual("DELIVERED", delivered["state"])
        events = self.svc.get(run["workitem_id"])["events"]
        self.assertEqual(request_id, [e for e in events if e["event"] == "delivered"][-1]["authorization"])
        self.assertEqual("NO_PENDING_GATE", self.svc.deliver(run["workitem_id"])["error"])

    def test_s03_non_interactive_approval_is_refused(self):
        run = self.svc.run(PUBLISH)
        code, text = cli(["approve", run["approval_request"]], self.home, tty=False)
        self.assertEqual(3, code)
        self.assertIn("交互式终端", text)
        self.assertEqual("AWAITING_HUMAN_APPROVAL", self.svc.deliver(run["workitem_id"])["error"])

    def test_s04_wrong_confirmation_changes_nothing(self):
        run = self.svc.run(PUBLISH)
        code, _ = cli(["approve", run["approval_request"]], self.home, tty=True, answer="y")
        self.assertEqual(1, code)
        self.assertEqual("AWAITING_HUMAN_APPROVAL", self.svc.deliver(run["workitem_id"])["error"])

    def test_s05_denied_in_terminal_sends_task_to_rework(self):
        run = self.svc.run(PUBLISH)
        code, _ = cli(["deny", run["approval_request"], "--reason", "不发"], self.home, tty=True, answer="deny")
        self.assertEqual(0, code)
        self.assertEqual("REWORK", self.svc.deliver(run["workitem_id"])["state"])

    def test_s06_approver_must_be_the_project_owner(self):
        run = self.svc.run(PUBLISH)
        cli(["approve", run["approval_request"]], self.home, owner="human.stranger", tty=True)
        result = self.svc.deliver(run["workitem_id"])
        self.assertFalse(result["ok"])
        self.assertEqual("NOT_ALLOWED_TO_DECIDE", result["error"])
        self.assertEqual("APPROVED", result["state"])

    def test_s07_service_exposes_no_approval_operation(self):
        for name in ("approve", "deny", "decide"):
            self.assertFalse(hasattr(self.svc, name))

    def test_s08_unroutable_and_invalid_input_are_codes(self):
        self.assertEqual("UNROUTABLE_DELIVERABLE", self.svc.route("今天天气怎么样")["error"])
        self.assertEqual("INVALID_INPUT", self.svc.run("   ")["error"])
        self.assertEqual("UNKNOWN_WORKITEM", self.svc.get("WI-nope")["error"])

    def test_s09_remote_model_needs_configured_consent(self):
        class Model:
            model = "remote"
            calls = 0

            def complete_json(self, *a):
                Model.calls += 1
                return {"titles": ["a"]}

        svc = AgentOpsService(home=self.home, provider=Model(), remote=True, allow_remote=False)
        result = svc.run("写 3 个公众号标题")
        self.assertEqual(0, Model.calls)
        self.assertEqual("WORKING", result["state"])
        codes = [e.get("code") for e in svc.get(result["workitem_id"])["events"] if e["event"] == "executor-failed"]
        self.assertEqual(["MODEL_CONSENT_REQUIRED"], codes)

    def test_s10_cli_list_shows_open_requests(self):
        run = self.svc.run(PUBLISH)
        code, text = cli(["list"], self.home)
        self.assertEqual(0, code)
        self.assertIn(run["approval_request"], text)


@unittest.skipUnless(HAS_MCP, "optional dependency mcp not installed")
class McpProtocolTests(unittest.TestCase):
    """Real MCP handshake over stdio, as an agent client would connect (mcp 1.x and 2.x)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "agent-ops"

    def session_call(self, calls):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=sys.executable, args=["-m", "sayelf_agent_ops.mcp_server"], cwd=str(ROOT),
            env={**os.environ, "SAYELF_AGENT_OPS_HOME": str(self.home), "PYTHONPATH": str(ROOT)},
        )

        async def go():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = {t.name for t in (await session.list_tools()).tools}
                    results = [await session.call_tool(name, args) for name, args in calls]
                    return tools, results

        return asyncio.run(go())

    @staticmethod
    def text(result):
        return "".join(getattr(c, "text", "") for c in result.content)

    def test_m01_tools_listed_and_none_can_approve(self):
        tools, _ = self.session_call([])
        self.assertEqual({"capabilities", "route_task", "run_task", "get_task",
                          "list_pending_approvals", "deliver_task"}, tools)

    def test_m02_run_then_deliver_requires_human(self):
        _, results = self.session_call([
            ("route_task", {"text": "写 5 个公众号标题"}),
            ("run_task", {"text": PUBLISH}),
        ])
        self.assertIn("media.content-planner", self.text(results[0]))
        self.assertIn("approve_cli approve", self.text(results[1]))
        self.assertIn('"APPROVED"', self.text(results[1]).replace("'", '"'))

    def test_m03_software_route_available_over_mcp(self):
        _, results = self.session_call([
            ("route_task", {"text": "修复 Draftloom 软件代码：微信 40164 错误展示公网 IP"}),
        ])
        self.assertIn("software.architect", self.text(results[0]))
        self.assertIn("software.engineer", self.text(results[0]))
        self.assertIn("software.bug-fix", self.text(results[0]))


if __name__ == "__main__":
    unittest.main()
