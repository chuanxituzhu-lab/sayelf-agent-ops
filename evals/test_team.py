"""Sprint 06 — Team (N 人 + N Agent) 与 Hybrid（成员进出），以 BuildCostIQ 施工项目部为验证场。"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from sayelf_agent_ops.actors import Actor, Project
from sayelf_agent_ops.gates import GateRejected
from sayelf_agent_ops.runtime import Runtime
from sayelf_agent_ops.state import TransitionRejected

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "buildcostiq-project-department.json"
BOQ = "对比两版 BOQ 的清单特征变化和漏项"
DRAWING = "比较两版施工图的版本变化"


def team() -> Runtime:
    return Runtime(Project.from_spec(json.loads(TEMPLATE.read_text(encoding="utf-8"))))


class TeamStructureTests(unittest.TestCase):
    def test_t01_template_loads_humans_and_agents(self):
        project = team().project
        self.assertEqual({"human.pm", "human.cost-lead", "human.tech-lead"}, {h.id for h in project.humans})
        self.assertEqual("human.pm", project.owner.id)
        self.assertTrue(any(m.kind == "agent" for m in project.members))

    def test_t02_spec_round_trips(self):
        project = team().project
        again = Project.from_spec(project.to_spec())
        self.assertEqual(project.to_spec(), again.to_spec())

    def test_t03_spec_without_owner_is_rejected(self):
        with self.assertRaises(LookupError):
            Project.from_spec({"members": [{"id": "human.a", "roles": ["cost-lead"]}]})


class HumanOwnedStepTests(unittest.TestCase):
    def test_h01_step_held_by_a_human_waits_for_that_person(self):
        rt = team()
        wi = rt.run(rt.submit(DRAWING, submitted_by="human.pm"))
        self.assertEqual("WORKING", wi.state)
        tasks = rt.human_tasks("human.tech-lead")
        self.assertEqual(1, len(tasks))
        self.assertEqual("engineering.technical", tasks[0]["role"])
        self.assertEqual([], rt.human_tasks("human.cost-lead"))

    def test_h02_only_the_assignee_can_submit(self):
        rt = team()
        wi = rt.run(rt.submit(DRAWING, submitted_by="human.pm"))
        with self.assertRaises(PermissionError):
            rt.submit_human_output(wi, "human.cost-lead", "我不是技术负责人")
        with self.assertRaises(ValueError):
            rt.submit_human_output(wi, "human.tech-lead", "   ")

    def test_h03_human_output_is_reviewed_by_an_independent_agent_then_delivered(self):
        rt = team()
        wi = rt.run(rt.submit(DRAWING, submitted_by="human.pm"))
        wi = rt.submit_human_output(wi, "human.tech-lead", "B 版较 A 版：3 号井位移 1.2 m；管径 DN600→DN800。")
        self.assertEqual("DELIVERED", wi.state)
        events = rt.events(wi)
        producers = {e["actor"] for e in events if e["event"] == "step-completed"}
        reviewers = {e["actor"] for e in events if e["event"] == "review"}
        self.assertEqual({"human.tech-lead"}, producers)
        self.assertTrue(reviewers and not (producers & reviewers))
        self.assertEqual("human", wi.outputs[0]["evidence"]["method"])

    def test_h04_rerun_while_waiting_does_not_duplicate_the_task(self):
        rt = team()
        wi = rt.run(rt.submit(DRAWING, submitted_by="human.pm"))
        rt.run(wi)
        self.assertEqual(1, sum(1 for e in rt.events(wi) if e["event"] == "human-task-assigned"))


class QuorumApprovalTests(unittest.TestCase):
    def setUp(self):
        self.rt = team()
        self.wi = self.rt.run(self.rt.submit(BOQ, submitted_by="human.pm"))

    def test_q01_cost_release_waits_for_both_roles(self):
        self.assertEqual("APPROVED", self.wi.state)
        self.assertEqual("cost-release", self.wi.pending_gate)
        self.rt.decide(self.wi, "human.cost-lead", approve=True)
        self.assertEqual("APPROVED", self.wi.state)
        self.rt.decide(self.wi, "human.pm", approve=True)
        self.assertEqual("DELIVERED", self.wi.state)
        delivered = [e for e in self.rt.events(self.wi) if e["event"] == "delivered"][-1]
        self.assertEqual({"cost-lead": "human.cost-lead", "project-manager": "human.pm"}, delivered["approvers"])

    def test_q02_same_person_cannot_fill_two_roles(self):
        self.rt.project.add_member(Actor("human.both", "human", ("cost-lead", "project-manager")))
        self.rt.decide(self.wi, "human.both", approve=True)
        with self.assertRaisesRegex(PermissionError, "ALREADY_APPROVED_BY_ACTOR"):
            self.rt.decide(self.wi, "human.both", approve=True)
        self.assertEqual("APPROVED", self.wi.state)

    def test_q03_member_without_a_quorum_role_cannot_decide(self):
        with self.assertRaises(PermissionError):
            self.rt.decide(self.wi, "human.tech-lead", approve=True)

    def test_q04_any_required_role_can_reject(self):
        self.rt.decide(self.wi, "human.cost-lead", approve=True)
        self.rt.decide(self.wi, "human.pm", approve=False, reason="漏项未核对完")
        self.assertEqual("REWORK", self.wi.state)

    def test_q05_agents_never_count_toward_quorum(self):
        with self.assertRaises(PermissionError):
            self.rt.decide(self.wi, "agent.engineering.commercial", approve=True)

    def test_q06_output_change_between_approvals_is_blocked(self):
        self.rt.decide(self.wi, "human.cost-lead", approve=True)
        self.wi.outputs[0]["items"] = ["审批中被改动"]
        with self.assertRaises(GateRejected):
            self.rt.decide(self.wi, "human.pm", approve=True)


class MembershipTests(unittest.TestCase):
    def test_m01_only_owners_manage_members_and_it_is_logged(self):
        rt = team()
        with self.assertRaisesRegex(PermissionError, "ONLY_OWNERS"):
            rt.add_member(Actor("human.x", "human", ("cost-lead",)), by="human.cost-lead")
        rt.add_member(Actor("human.x", "human", ("cost-lead",)), by="human.pm")
        self.assertEqual("member-added", rt.project_events()[-1]["event"])
        self.assertEqual("human.pm", rt.project_events()[-1]["actor"])

    def test_m02_removed_member_cannot_decide(self):
        rt = team()
        wi = rt.run(rt.submit(BOQ, submitted_by="human.pm"))
        rt.remove_member("human.cost-lead", by="human.pm")
        with self.assertRaises(PermissionError):
            rt.decide(wi, "human.cost-lead", approve=True)

    def test_m03_removing_the_assignee_hands_the_step_back(self):
        rt = team()
        wi = rt.run(rt.submit(DRAWING, submitted_by="human.pm"))
        rt.remove_member("human.tech-lead", by="human.pm")
        self.assertEqual([], rt.human_tasks())
        self.assertIn("assignee-removed", [e["event"] for e in rt.events(wi)])
        wi = rt.run(wi)  # 没有人担任该岗位时回到 Agent
        self.assertEqual("DELIVERED", wi.state)

    def test_m04_last_owner_cannot_leave(self):
        rt = team()
        with self.assertRaisesRegex(ValueError, "LAST_OWNER"):
            rt.remove_member("human.pm", by="human.pm")

    def test_m05_history_survives_member_removal(self):
        rt = team()
        wi = rt.run(rt.submit(DRAWING, submitted_by="human.pm"))
        wi = rt.submit_human_output(wi, "human.tech-lead", "差异：3 号井位移。")
        before = rt.events(wi)
        rt.remove_member("human.tech-lead", by="human.pm")
        self.assertEqual(before, rt.events(wi))
        self.assertFalse(rt.project.get("human.tech-lead").active)

    def test_m06_new_member_takes_over_a_role(self):
        rt = team()
        rt.remove_member("human.tech-lead", by="human.pm")
        rt.add_member(Actor("human.tech-lead-2", "human", ("engineering.technical",), name="新技术负责人"), by="human.pm")
        wi = rt.run(rt.submit(DRAWING, submitted_by="human.pm"))
        self.assertEqual("human.tech-lead-2", rt.human_tasks()[0]["assignee"])


if __name__ == "__main__":
    unittest.main()
