import unittest
from datetime import datetime, timedelta, timezone

from sayelf_agent_ops.demo import run_first_vertical_slice
from sayelf_agent_ops.gates import (
    AcceptanceGate,
    ActionKind,
    GateRejected,
    HumanGate,
)
from sayelf_agent_ops.models import WorkItem
from sayelf_agent_ops.registry import build_default_registry


class FakeClock:
    def __init__(self):
        self.t = datetime(2026, 10, 9, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


def ready_item():
    return run_first_vertical_slice()  # Sprint 01 slice, state READY


class AcceptanceGateTests(unittest.TestCase):
    def setUp(self):
        self.registry = build_default_registry()
        self.gate = AcceptanceGate(self.registry)

    def test_a01_ready_slice_passes(self):
        wi = ready_item()
        report = self.gate.check(wi)
        self.assertTrue(report.passed)
        self.assertEqual((), report.failures)

    def test_a02_not_ready_is_rejected(self):
        wi = WorkItem(id="WI-N", input="x", goal="x", deliverable="x")
        with self.assertRaises(GateRejected):
            self.gate.check(wi)

    def test_a03_wrong_output_type_fails(self):
        wi = ready_item()
        wi.outputs = [{"type": "article", "content": "..."}]
        report = self.gate.check(wi)
        self.assertFalse(report.passed)
        self.assertIn("MISSING_OUTPUT", report.failures[0])

    def test_a04_empty_output_fails(self):
        wi = ready_item()
        wi.outputs = [{"type": "title-list", "items": []}]
        self.assertFalse(self.gate.check(wi).passed)

    def test_a05_escalates_after_max_attempts(self):
        wi = ready_item()
        wi.outputs = [{"type": "title-list", "items": []}]
        first = self.gate.check(wi)
        second = self.gate.check(wi)
        self.assertFalse(first.escalate_to_human)
        self.assertTrue(second.escalate_to_human)

    def test_a06_pass_invalidated_when_output_changes(self):
        wi = ready_item()
        self.gate.check(wi)
        self.assertIsNotNone(self.gate.passed_report(wi))
        wi.outputs[0]["items"].append("偷偷加的第六个标题")
        self.assertIsNone(self.gate.passed_report(wi))


class HumanGateTests(unittest.TestCase):
    def setUp(self):
        self.registry = build_default_registry()
        self.acceptance = AcceptanceGate(self.registry)
        self.clock = FakeClock()
        self.gate = HumanGate(self.acceptance, clock=self.clock)
        self.wi = ready_item()
        self.payload = {"titles": list(self.wi.outputs[0]["items"])}

    def _approved_request(self):
        self.acceptance.check(self.wi)
        req = self.gate.request(
            self.wi, ActionKind.PUBLISH, "wechat:sayelf", self.payload, "发布 5 个标题"
        )
        self.gate.approve(req.id, "nicola")
        return req

    def test_h01_request_requires_acceptance(self):
        with self.assertRaisesRegex(GateRejected, "ACCEPTANCE_NOT_PASSED"):
            self.gate.request(self.wi, ActionKind.PUBLISH, "wechat:sayelf", self.payload, "x")

    def test_h02_happy_path_single_use(self):
        req = self._approved_request()
        token = self.gate.authorize(self.wi, req.id, ActionKind.PUBLISH, "wechat:sayelf", self.payload)
        self.assertEqual("nicola", token.approver)
        with self.assertRaisesRegex(GateRejected, "ALREADY_CONSUMED"):
            self.gate.authorize(self.wi, req.id, ActionKind.PUBLISH, "wechat:sayelf", self.payload)

    def test_h03_agent_cannot_approve(self):
        self.acceptance.check(self.wi)
        req = self.gate.request(self.wi, ActionKind.PUBLISH, "wechat:sayelf", self.payload, "x")
        with self.assertRaisesRegex(GateRejected, "AGENT_SELF_APPROVAL"):
            self.gate.approve(req.id, "agent:media.growth-operator")

    def test_h04_non_authorizing_events_never_approve(self):
        self.acceptance.check(self.wi)
        req = self.gate.request(self.wi, ActionKind.PUBLISH, "wechat:sayelf", self.payload, "x")
        for event in ("draft-prepared", "uploaded", "account-configured", "previous-approval"):
            with self.assertRaises(GateRejected):
                self.gate.approve(req.id, event)
        with self.assertRaisesRegex(GateRejected, "NO_APPROVAL"):
            self.gate.authorize(self.wi, req.id, ActionKind.PUBLISH, "wechat:sayelf", self.payload)

    def test_h05_payload_change_voids_approval(self):
        req = self._approved_request()
        changed = {"titles": self.payload["titles"] + ["改过的"]}
        with self.assertRaisesRegex(GateRejected, "PAYLOAD_CHANGED"):
            self.gate.authorize(self.wi, req.id, ActionKind.PUBLISH, "wechat:sayelf", changed)

    def test_h06_approval_not_inherited_by_other_target(self):
        req = self._approved_request()
        with self.assertRaisesRegex(GateRejected, "TARGET_MISMATCH"):
            self.gate.authorize(self.wi, req.id, ActionKind.PUBLISH, "xiaohongshu:sayelf", self.payload)

    def test_h07_approval_not_inherited_by_other_action(self):
        req = self._approved_request()
        with self.assertRaisesRegex(GateRejected, "ACTION_MISMATCH"):
            self.gate.authorize(self.wi, req.id, ActionKind.DELETE, "wechat:sayelf", self.payload)

    def test_h08_approval_expires(self):
        req = self._approved_request()
        self.clock.advance(minutes=31)
        with self.assertRaisesRegex(GateRejected, "EXPIRED"):
            self.gate.authorize(self.wi, req.id, ActionKind.PUBLISH, "wechat:sayelf", self.payload)

    def test_h09_output_edit_after_approval_blocks(self):
        req = self._approved_request()
        self.wi.outputs[0]["items"][0] = "审批后被改的标题"
        with self.assertRaisesRegex(GateRejected, "ACCEPTANCE_NOT_PASSED"):
            self.gate.authorize(self.wi, req.id, ActionKind.PUBLISH, "wechat:sayelf", self.payload)

    def test_h10_second_publish_needs_second_approval(self):
        req1 = self._approved_request()
        self.gate.authorize(self.wi, req1.id, ActionKind.PUBLISH, "wechat:sayelf", self.payload)
        req2 = self.gate.request(self.wi, ActionKind.PUBLISH, "wechat:sayelf", self.payload, "再发一次")
        with self.assertRaisesRegex(GateRejected, "NO_APPROVAL"):
            self.gate.authorize(self.wi, req2.id, ActionKind.PUBLISH, "wechat:sayelf", self.payload)

    def test_h11_solo_mode_needs_no_org_config(self):
        gate = HumanGate(self.acceptance, clock=self.clock)  # no approver_policy
        self.acceptance.check(self.wi)
        req = gate.request(self.wi, ActionKind.PUBLISH, "wechat:sayelf", self.payload, "x")
        self.assertEqual("nicola", gate.approve(req.id, "nicola").approver)

    def test_h12_audit_trail_records_non_authorizing_event(self):
        self.gate.record_non_authorizing(self.wi, "uploaded")
        self.assertEqual({"event": "uploaded", "authorizes": False}, self.wi.history[-1])


if __name__ == "__main__":
    unittest.main()
