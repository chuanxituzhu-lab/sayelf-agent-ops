"""Sprint 03：HumanGate 审批持久化，以及桌面“确认并生成发布包”走同一道授权门。"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from desktop.runtime import bootstrap
from desktop.runtime.approvals import LOCAL_HUMAN, SQLiteApprovalStore, desktop_human_gate
from sayelf_agent_ops.actors import Project
from sayelf_agent_ops.gates import ActionKind, GateRejected, HumanGate
from sayelf_agent_ops.models import WorkItem
from sayelf_agent_ops.runtime import Runtime

from test_media_workflow import FakeProvider, MediaWorkflowTests


class _Pass:
    def passed_report(self, workitem):
        return object()


class _Clock:
    def __init__(self):
        self.t = datetime(2026, 10, 9, tzinfo=timezone.utc)

    def __call__(self):
        return self.t


def _rows(root, sql, args=()):
    with closing(sqlite3.connect(root / "runtime.sqlite3")) as connection:
        return connection.execute(sql, args).fetchall()


class ApprovalPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "Sayelf"
        bootstrap.initialize(self.root, "media")
        self.wi = WorkItem(id="WI-P", input="x", outputs=[{"type": "publish-package"}])

    def gate(self, clock=None):
        return HumanGate(_Pass(), store=SQLiteApprovalStore(self.root), clock=clock or _Clock())

    def test_p01_approval_survives_restart_and_is_single_use(self):
        req = self.gate().request(self.wi, ActionKind.PUBLISH, "t", self.wi.outputs, "s")
        self.gate().approve(req.id, "human.nicola")
        token = self.gate().authorize(self.wi, req.id, ActionKind.PUBLISH, "t", self.wi.outputs)
        self.assertEqual("human.nicola", token.approver)
        with self.assertRaisesRegex(GateRejected, "ALREADY_CONSUMED"):
            self.gate().authorize(self.wi, req.id, ActionKind.PUBLISH, "t", self.wi.outputs)
        with self.assertRaisesRegex(GateRejected, "ALREADY_CONSUMED"):
            self.gate().approve(req.id, "human.nicola")
        consumed = _rows(self.root, "SELECT consumed_at FROM gate_approvals WHERE request_id=?", (req.id,))
        self.assertIsNotNone(consumed[0][0])

    def test_p02_expiry_is_enforced_after_restart(self):
        clock = _Clock()
        req = self.gate(clock).request(self.wi, ActionKind.PUBLISH, "t", self.wi.outputs, "s")
        self.gate(clock).approve(req.id, "human.nicola")
        clock.t += timedelta(minutes=31)
        with self.assertRaisesRegex(GateRejected, "EXPIRED"):
            self.gate(clock).authorize(self.wi, req.id, ActionKind.PUBLISH, "t", self.wi.outputs)

    def test_p03_denied_request_cannot_be_approved_later(self):
        req = self.gate().request(self.wi, ActionKind.PUBLISH, "t", self.wi.outputs, "s")
        self.gate().deny(req.id, "human.nicola", "不发")
        with self.assertRaisesRegex(GateRejected, "UNKNOWN_REQUEST"):
            self.gate().approve(req.id, "human.nicola")

    def test_p04_payload_binding_survives_restart(self):
        req = self.gate().request(self.wi, ActionKind.PUBLISH, "t", self.wi.outputs, "s")
        self.gate().approve(req.id, "human.nicola")
        changed = [{"type": "publish-package", "tampered": True}]
        with self.assertRaisesRegex(GateRejected, "PAYLOAD_CHANGED"):
            self.gate().authorize(self.wi, req.id, ActionKind.PUBLISH, "t", changed)

    def test_p05_desktop_gate_only_accepts_local_human(self):
        gate = desktop_human_gate(self.root)
        gate.acceptance = _Pass()
        req = gate.request(self.wi, ActionKind.PUBLISH, "t", self.wi.outputs, "s")
        with self.assertRaisesRegex(GateRejected, "APPROVER_NOT_ALLOWED"):
            gate.approve(req.id, "human.someone-else")
        gate.approve(req.id, LOCAL_HUMAN)

    def test_p06_kernel_runtime_can_persist_its_approvals(self):
        rt = Runtime(Project.solo("human.nicola"), approval_store=SQLiteApprovalStore(self.root))
        wi = rt.run(rt.submit("把已确认的文章整理成公众号草稿发布准备包"))
        rt.decide(wi, "human.nicola", approve=True, reason="确认")
        rows = _rows(self.root, "SELECT workitem_id, approver, consumed_at FROM gate_approvals")
        self.assertEqual(1, len(rows))
        self.assertEqual((wi.id, "human.nicola"), rows[0][:2])
        self.assertIsNotNone(rows[0][2])


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(ApprovalPersistenceTests))
    suite.addTest(DesktopExportCase("test_d01_export_goes_through_human_gate"))
    suite.addTest(DesktopExportCase("test_d02_reexport_reuses_authorization_without_new_approval"))
    return suite


class DesktopExportCase(MediaWorkflowTests):
    def test_d01_export_goes_through_human_gate(self):
        from desktop.runtime.media_workflow import approve_and_export, execute_media_workflow

        draft = execute_media_workflow(self.root, "WI-MEDIA-1", FakeProvider())["data"]["markdown"]
        approved = approve_and_export(self.root, "WI-MEDIA-1", draft)
        rows = _rows(self.root,
                     "SELECT request_id, action, target, approver, consumed_at FROM gate_approvals "
                     "WHERE workitem_id='WI-MEDIA-1'")
        self.assertEqual(1, len(rows))
        request_id, action, target, approver, consumed_at = rows[0]
        self.assertEqual("publish", action)
        self.assertEqual("local-package:WI-MEDIA-1:v1", target)
        self.assertEqual(LOCAL_HUMAN, approver)
        self.assertIsNotNone(consumed_at)
        with zipfile.ZipFile(approved["data"]["package_path"]) as archive:
            self.assertEqual(request_id, json.loads(archive.read("manifest.json"))["authorization"])
        evidence = _rows(self.root,
                         "SELECT evidence_json FROM workflow_events WHERE event_type='human-approved'")
        self.assertEqual(request_id, json.loads(evidence[0][0])["authorization"])

    def test_d02_reexport_reuses_authorization_without_new_approval(self):
        from desktop.runtime.media_workflow import approve_and_export, execute_media_workflow

        draft = execute_media_workflow(self.root, "WI-MEDIA-1", FakeProvider())["data"]["markdown"]
        approve_and_export(self.root, "WI-MEDIA-1", draft)
        approve_and_export(self.root, "WI-MEDIA-1", draft)
        edited = draft + "\n人工修订。\n"
        approve_and_export(self.root, "WI-MEDIA-1", edited)
        rows = _rows(self.root, "SELECT target FROM gate_approvals WHERE workitem_id='WI-MEDIA-1' ORDER BY created_at")
        self.assertEqual(["local-package:WI-MEDIA-1:v1", "local-package:WI-MEDIA-1:v2"], [r[0] for r in rows])


if __name__ == "__main__":
    unittest.main()
