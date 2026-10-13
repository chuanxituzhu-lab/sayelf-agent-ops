"""Regression checks for the industry-neutral Agent Ops workbench entry."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sayelf_agent_ops.workspace import WorkspaceError, WorkspaceService


ROOT = Path(__file__).resolve().parents[1]
GENERIC = ROOT / "templates" / "agent-ops-workspace.json"
TEAM = ROOT / "templates" / "agent-ops-team-workspace.json"


class GenericWorkbenchTests(unittest.TestCase):
    def test_generic_template_has_only_a_shared_owner(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            service = WorkspaceService(spec=json.loads(GENERIC.read_text(encoding="utf-8")), home=home)
            view = service.project_view("human.owner")
            humans = [member for member in view["members"] if member["kind"] == "human"]
            self.assertEqual("P-SAYELF-AGENT-OPS", view["id"])
            self.assertEqual(["human.owner"], [member["id"] for member in humans])
            self.assertNotIn("human.pm", {member["id"] for member in humans})
            self.assertEqual("solo", view["mode"])
            self.assertEqual("一人多 Agent", view["mode_label"])

    def test_team_template_exposes_many_people_many_agents(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            service = WorkspaceService(spec=json.loads(TEAM.read_text(encoding="utf-8")), home=home)
            view = service.project_view("human.owner")
            self.assertEqual("team", view["mode"])
            self.assertEqual("多人多 Agent", view["mode_label"])
            self.assertEqual(2, view["human_count"])
            self.assertGreater(view["agent_count"], 0)

    def test_industry_input_is_a_route_hint_and_stays_read_only(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            service = WorkspaceService(spec=json.loads(GENERIC.read_text(encoding="utf-8")), home=home)
            before = (home / "workspace" / "state.json").exists()
            result = service.route_preview("human.owner", "写一篇公众号文章", "自媒体公司")
            self.assertEqual("自媒体公司", result["industry_input"])
            self.assertEqual("media", result["decision"]["industry"])
            self.assertEqual(before, (home / "workspace" / "state.json").exists())

    def test_unroutable_work_returns_actionable_error(self):
        with tempfile.TemporaryDirectory() as raw:
            service = WorkspaceService(spec=json.loads(GENERIC.read_text(encoding="utf-8")), home=Path(raw))
            with self.assertRaises(WorkspaceError) as ctx:
                service.submit("human.owner", "制作过程", industry="生态微景观")
            self.assertEqual("UNROUTABLE_DELIVERABLE", ctx.exception.code)

    def test_software_execution_has_an_independent_reviewer(self):
        with tempfile.TemporaryDirectory() as raw:
            service = WorkspaceService(spec=json.loads(GENERIC.read_text(encoding="utf-8")), home=Path(raw))
            item = service.submit("human.owner", "开发一个登录页面", industry="软件开发")
            self.assertEqual("DELIVERED", item["state"])
            self.assertEqual("agent.software.reviewer", item["reviewer"])
            self.assertNotEqual(item["assignee"], item["reviewer"])

    def test_console_explains_generic_base_and_optional_packs(self):
        app = (ROOT / "sayelf_agent_ops" / "console" / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "sayelf_agent_ops" / "console" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("行业 / 专业（可填）", app)
        self.assertIn("行业包只是示范与已连接能力目录", app)
        self.assertIn("async function connections()", app)
        self.assertIn("data-view=\"connections\"", html)
        self.assertIn("通用智能工作台", html)
        self.assertIn("UNROUTABLE_DELIVERABLE", app)
        self.assertIn("按此方案开始执行", app)
        self.assertIn("输入已修改，请重新生成分派方案", app)
        self.assertNotIn("BuildCostIQ", app)


if __name__ == "__main__":
    unittest.main()
