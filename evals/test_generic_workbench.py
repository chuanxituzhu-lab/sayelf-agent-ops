"""Regression checks for the industry-neutral Agent Ops workbench entry."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sayelf_agent_ops.workspace import WorkspaceService


ROOT = Path(__file__).resolve().parents[1]
GENERIC = ROOT / "templates" / "agent-ops-workspace.json"


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

    def test_industry_input_is_a_route_hint_and_stays_read_only(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            service = WorkspaceService(spec=json.loads(GENERIC.read_text(encoding="utf-8")), home=home)
            before = (home / "workspace" / "state.json").exists()
            result = service.route_preview("human.owner", "写一篇公众号文章", "自媒体公司")
            self.assertEqual("自媒体公司", result["industry_input"])
            self.assertEqual("media", result["decision"]["industry"])
            self.assertEqual(before, (home / "workspace" / "state.json").exists())

    def test_console_explains_generic_base_and_optional_packs(self):
        app = (ROOT / "sayelf_agent_ops" / "console" / "web" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "sayelf_agent_ops" / "console" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("行业 / 专业（可填）", app)
        self.assertIn("行业包只是示范与已连接能力目录", app)
        self.assertIn("async function connections()", app)
        self.assertIn("data-view=\"connections\"", html)
        self.assertIn("通用智能工作台", html)
        self.assertNotIn("BuildCostIQ", app)


if __name__ == "__main__":
    unittest.main()
