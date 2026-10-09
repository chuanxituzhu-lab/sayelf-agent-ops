"""Sprint 02 运行时补充测试：返工、人工驳回、升级上报、拒绝无法路由的任务。"""
from __future__ import annotations

import unittest

from sayelf_agent_ops.actors import Actor, Project
from sayelf_agent_ops.executor import BuiltinExecutor, extract_topic, requested_count
from sayelf_agent_ops.runtime import Runtime
from sayelf_agent_ops.state import TransitionRejected

OWNER = "human.nicola"


def _bad_then_good(step, wi, feedback):
    items = ["重复标题"] * 5 if wi.rework_count == 0 else [f"标题{i}" for i in range(5)]
    return {"type": "title-list", "skill": step.skill, "items": items, "placeholder": False,
            "evidence": {"method": "test", "feedback_applied": list(feedback)}}


def _always_bad(step, wi, feedback):
    return {"type": "title-list", "skill": step.skill, "items": [], "placeholder": False, "evidence": {}}


class RuntimeTests(unittest.TestCase):
    def test_title_parsing(self):
        self.assertEqual(requested_count('给"一人公司"生成 3 个公众号标题'), 3)
        self.assertEqual(requested_count("写七个小红书标题"), 7)
        self.assertEqual(requested_count("公众号标题 × 4"), 4)
        self.assertEqual(extract_topic('给"一人公司 Agent Ops"生成 5 个公众号标题'), "一人公司 Agent Ops")

    def test_review_failure_triggers_rework_then_passes(self):
        rt = Runtime(Project.solo(OWNER), executor=BuiltinExecutor({"media.title-writing": _bad_then_good}))
        wi = rt.run(rt.submit("写 5 个公众号标题"))
        self.assertEqual(wi.state, "DELIVERED")
        self.assertEqual(wi.rework_count, 1)
        events = rt.events(wi)
        self.assertTrue(any(e["event"] == "rework-requested" for e in events))
        last_output = [e for e in events if e["event"] == "output"][-1]
        self.assertTrue(last_output["evidence"]["feedback_applied"])

    def test_endless_failure_escalates_to_human(self):
        rt = Runtime(Project.solo(OWNER), executor=BuiltinExecutor({"media.title-writing": _always_bad}))
        wi = rt.run(rt.submit("写 5 个公众号标题"))
        self.assertEqual(wi.state, "REWORK")
        self.assertEqual(rt.events(wi)[-1]["event"], "escalated")

    def test_human_rejection_sends_back_and_rerun_reaches_gate(self):
        rt = Runtime(Project.solo(OWNER))
        wi = rt.run(rt.submit("把已确认的文章整理成公众号草稿发布准备包"))
        rt.decide(wi, OWNER, approve=False, reason="先别发")
        self.assertEqual(wi.state, "REWORK")
        rt.run(wi)
        self.assertEqual(wi.state, "APPROVED")
        self.assertEqual(wi.pending_gate, "publish")

    def test_team_member_without_approval_role_cannot_pass_gate(self):
        project = Project.solo(OWNER)
        project.add_member(Actor(id="human.partner", kind="human", roles=("media.reviewer",)))
        rt = Runtime(project)
        wi = rt.run(rt.submit("把已确认的文章整理成公众号草稿发布准备包"))
        with self.assertRaises(PermissionError):
            rt.decide(wi, "human.partner", approve=True)

    def test_unroutable_input_is_rejected_at_submit(self):
        rt = Runtime(Project.solo(OWNER))
        with self.assertRaises(ValueError):
            rt.submit("今天天气怎么样")
        self.assertEqual(rt.items, {})

    def test_decide_without_gate_is_rejected(self):
        rt = Runtime(Project.solo(OWNER))
        wi = rt.run(rt.submit("写 5 个公众号标题"))
        with self.assertRaises(TransitionRejected):
            rt.decide(wi, OWNER, approve=True)

    def test_placeholder_outputs_are_declared(self):
        rt = Runtime(Project.solo(OWNER))
        wi = rt.run(rt.submit("写一篇完整公众号文章"))
        self.assertTrue(all(o["placeholder"] for o in wi.outputs))


if __name__ == "__main__":
    unittest.main()
