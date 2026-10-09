"""Sprint 02b：内核层（Actor/Project/Runtime）与规则层（两道门 + 按需加载）的接线测试。"""
from __future__ import annotations

import unittest

from sayelf_agent_ops.actors import Project
from sayelf_agent_ops.gates import GateRejected
from sayelf_agent_ops.loader import SkillLoader, SkillManifest
from sayelf_agent_ops.registry import build_default_registry
from sayelf_agent_ops.runtime import Runtime
from sayelf_agent_ops.state import TransitionRejected

OWNER = "human.nicola"
PUBLISH = "把已确认的文章整理成公众号草稿发布准备包"
TITLES = "写 5 个公众号标题"


def solo():
    return Runtime(Project.solo(OWNER))


class KernelIntegrationTests(unittest.TestCase):
    def test_k01_self_check_by_producer_review_by_other_agent(self):
        rt = solo()
        wi = rt.run(rt.submit(TITLES))
        events = rt.events(wi)
        checks = [e for e in events if e["event"] == "self-check"]
        reviews = [e for e in events if e["event"] == "review"]
        self.assertTrue(checks and reviews)
        self.assertEqual({e["actor"] for e in checks}, {wi.assignee})
        self.assertNotIn(wi.assignee, {e["actor"] for e in reviews})

    def test_k02_gate_request_binds_payload_digest(self):
        rt = solo()
        wi = rt.run(rt.submit(PUBLISH))
        gate_event = [e for e in rt.events(wi) if e["event"] == "gate-requested"][-1]
        self.assertTrue(gate_event["request"].startswith(f"AR-{wi.id}-"))
        self.assertEqual(64, len(gate_event["payload_digest"]))
        self.assertEqual("publish", gate_event["action"])

    def test_k03_output_changed_after_gate_request_is_blocked(self):
        rt = solo()
        wi = rt.run(rt.submit(PUBLISH))
        wi.outputs[0]["items"] = ["审批前被偷偷改过"]
        with self.assertRaises(GateRejected):
            rt.decide(wi, OWNER, approve=True, reason="确认")
        self.assertEqual("APPROVED", wi.state)

    def test_k04_delivery_carries_single_use_authorization(self):
        rt = solo()
        wi = rt.run(rt.submit(PUBLISH))
        rt.decide(wi, OWNER, approve=True, reason="确认")
        delivered = [e for e in rt.events(wi) if e["event"] == "delivered"][-1]
        self.assertTrue(delivered["authorization"].startswith(f"AR-{wi.id}-"))
        with self.assertRaises(TransitionRejected):
            rt.decide(wi, OWNER, approve=True, reason="再批一次")

    def test_k05_loader_releases_after_run(self):
        rt = solo()
        rt.run(rt.submit(TITLES))
        rt.run(rt.submit(PUBLISH))
        self.assertEqual(0, rt.loader.loaded_skills)

    def test_k06_noncommercial_skill_blocks_execution(self):
        registry = build_default_registry()
        loader = SkillLoader(
            registry,
            capabilities={"python"},
            manifests={"media.title-writing": SkillManifest(
                "media.title-writing", license="PolyForm-Noncommercial-1.0.0", commercial_use=False)},
        )
        rt = Runtime(Project.solo(OWNER), registry=registry, loader=loader)
        wi = rt.run(rt.submit(TITLES))
        self.assertEqual("WORKING", wi.state)
        self.assertFalse(wi.outputs)
        blocked = [e for e in rt.events(wi) if e["event"] == "skills-blocked"][-1]
        self.assertIn("LICENSE_NONCOMMERCIAL", blocked["blocked"]["media.title-writing"])

    def test_k07_placeholders_carry_contract_output_type(self):
        rt = solo()
        wi = rt.run(rt.submit(PUBLISH))
        produced = {
            o for s in wi.selected_skills for o in rt.registry.skills[s].produced_outputs
        }
        self.assertTrue(all(o["type"] in produced for o in wi.outputs))
        self.assertTrue(all(o["placeholder"] for o in wi.outputs))


if __name__ == "__main__":
    unittest.main()
