"""Sprint 08 — the Workspace survives a restart: nothing people started is lost."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sayelf_agent_ops.workspace import WorkspaceError, WorkspaceService

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "buildcostiq-project-department.json"
BOQ = "对比两版 BOQ 的清单特征变化和漏项"
DRAWING = "比较两版施工图的版本变化"
PROGRESS = "核对二标段本月形象进度是否滞后"


class RestartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.ws = WorkspaceService(spec=json.loads(TEMPLATE.read_text(encoding="utf-8")), home=self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def restart(self) -> WorkspaceService:
        return WorkspaceService(home=self.home)

    def test_p01_half_finished_quorum_resumes_after_restart(self):
        wi = self.ws.submit("human.pm", PROGRESS)
        self.ws.decide("human.prod-lead", wi["id"], True)
        ws = self.restart()
        view = ws.get_workitem("human.pm", wi["id"])
        roles = {r["role"]: r["approved_by"] for r in view["gate"]["roles"]}
        self.assertEqual("human.prod-lead", roles["production-lead"])
        self.assertIsNone(roles["project-manager"])
        with self.assertRaises(WorkspaceError):  # still one person, one role
            ws.decide("human.prod-lead", wi["id"], True)
        self.assertEqual("DELIVERED", ws.decide("human.pm", wi["id"], True)["state"])

    def test_p02_pending_human_task_resumes_after_restart(self):
        wi = self.ws.submit("human.pm", DRAWING)
        ws = self.restart()
        self.assertEqual(1, len(ws.my_tasks("human.tech-lead")))
        self.assertEqual("DELIVERED", ws.submit_task("human.tech-lead", wi["id"], "管径 DN600→DN800")["state"])

    def test_p03_evidence_log_and_ids_continue(self):
        first = self.ws.submit("human.pm", BOQ)
        events_before = self.ws.get_workitem("human.pm", first["id"])["events"]
        ws = self.restart()
        self.assertEqual(events_before, ws.get_workitem("human.pm", first["id"])["events"])
        second = ws.submit("human.pm", BOQ)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(2, len(ws.list_workitems("human.pm")))

    def test_p04_returned_work_keeps_its_reason_after_restart(self):
        wi = self.ws.submit("human.pm", BOQ)
        self.ws.decide("human.cost-lead", wi["id"], False, "漏项口径不对")
        ws = self.restart()
        view = ws.get_workitem("human.pm", wi["id"])
        self.assertEqual("REWORK", view["state"])
        self.assertEqual(["漏项口径不对"], ws.runtime._feedback[wi["id"]])

    def test_p05_member_changes_and_project_log_persist(self):
        self.ws.add_member("human.pm", {"id": "human.qa", "name": "质量负责人", "roles": ["qa-lead"]})
        ws = self.restart()
        self.assertEqual("member-added", ws.project_events("human.pm")[-1]["event"])

    def test_p06_corrupt_state_refuses_to_start_instead_of_forgetting(self):
        self.ws.submit("human.pm", BOQ)
        (self.home / "workspace" / "state.json").write_text('{"v": 99}', encoding="utf-8")
        with self.assertRaises(WorkspaceError) as ctx:
            self.restart()
        self.assertTrue(ctx.exception.code.startswith("STATE_UNREADABLE"))

    def test_p07_state_file_is_plain_json(self):
        self.ws.submit("human.pm", PROGRESS)
        data = json.loads((self.home / "workspace" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(1, data["v"])
        self.assertEqual("P-BUILDCOSTIQ-DEMO", data["project"])


if __name__ == "__main__":
    unittest.main()
