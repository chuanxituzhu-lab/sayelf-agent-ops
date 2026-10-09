"""Sayelf Agent Ops v0.2 —— 四条 Solo 不变式（冻结）。

见 ARCHITECTURE.md 第 5 节。Sprint 02 已实现，四条不变式强制生效。
任何改动使其中一条失败，不得合入。

接口：
  sayelf_agent_ops.actors   : Actor(id, kind, roles), Project.solo(owner_id), Project.add_member(actor)
  sayelf_agent_ops.runtime  : Runtime(project).submit(text, goal, deliverable, industry) -> WorkItem
                              Runtime.run(workitem) -> WorkItem       # Agent 自动接力，直到 DELIVERED 或停在 Human Gate
                              Runtime.decide(workitem, actor_id, approve: bool, reason: str) -> WorkItem
                              Runtime.events(workitem) -> list[dict]  # 只追加事件日志
  sayelf_agent_ops.state    : WorkState 增加 REVIEW / REWORK / APPROVED / DELIVERED；WorkItem 增加 pending_gate
"""
from __future__ import annotations

import unittest

OWNER = "human.nicola"


def _solo_runtime():
    from sayelf_agent_ops.actors import Project
    from sayelf_agent_ops.runtime import Runtime

    return Runtime(Project.solo(OWNER))


def _submit_titles(rt):
    return rt.submit(
        text='给"一人公司 Agent Ops"生成 5 个公众号标题',
        goal="获得 5 个可用于微信公众号的文章标题",
        deliverable="公众号标题 × 5",
        industry="media",
    )


def _submit_publish(rt):
    return rt.submit(
        text="把已确认的文章整理成公众号草稿发布准备包",
        goal="得到可发布的公众号平台包",
        deliverable="公众号草稿发布准备包",
        industry="media",
    )


class SoloInvariant1ZeroConfigLoop(unittest.TestCase):
    """① 零配置闭环：不填成员/角色/权限，即可从 INBOX 跑到 DELIVERED。"""

    def test_solo_project_needs_no_configuration(self):
        from sayelf_agent_ops.actors import Project

        project = Project.solo(OWNER)
        humans = [m for m in project.members if m.kind == "human"]
        self.assertEqual([h.id for h in humans], [OWNER])
        self.assertIsNotNone(project.policy)

    def test_low_risk_task_runs_inbox_to_delivered(self):
        rt = _solo_runtime()
        wi = rt.run(_submit_titles(rt))
        self.assertEqual(wi.state, "DELIVERED")
        self.assertTrue(wi.outputs)


class SoloInvariant2SeparatedAgentRoles(unittest.TestCase):
    """② 多 Agent 分工完整：产出者不能审核自己，人数为 1 也不例外。"""

    def test_producer_and_reviewer_are_different_agents(self):
        rt = _solo_runtime()
        wi = rt.run(_submit_titles(rt))
        self.assertIsNotNone(wi.assignee)
        self.assertIsNotNone(wi.reviewer)
        self.assertNotEqual(wi.assignee, wi.reviewer)
        self.assertNotEqual(wi.reviewer, OWNER)

    def test_every_review_event_comes_from_non_producer(self):
        rt = _solo_runtime()
        wi = rt.run(_submit_titles(rt))
        events = rt.events(wi)
        producers = {e["actor"] for e in events if e["event"] == "output"}
        reviewers = {e["actor"] for e in events if e["event"] == "review"}
        self.assertTrue(producers)
        self.assertTrue(reviewers)
        self.assertFalse(producers & reviewers)


class SoloInvariant3HumanOnlyAtGate(unittest.TestCase):
    """③ 人类只在必要处出现：Agent 自动接力，只在 Human Gate 停下。"""

    def test_low_risk_task_has_no_human_events(self):
        rt = _solo_runtime()
        wi = rt.run(_submit_titles(rt))
        self.assertFalse([e for e in rt.events(wi) if e["actor"] == OWNER and e["event"] != "submit"])

    def test_high_risk_task_stops_at_gate_for_the_single_human(self):
        rt = _solo_runtime()
        wi = rt.run(_submit_publish(rt))
        self.assertEqual(wi.state, "APPROVED")
        self.assertIsNotNone(wi.pending_gate)
        self.assertEqual(wi.approver, OWNER)

        wi = rt.decide(wi, OWNER, approve=True, reason="确认发布")
        self.assertEqual(wi.state, "DELIVERED")

    def test_agent_cannot_pass_human_gate(self):
        rt = _solo_runtime()
        wi = rt.run(_submit_publish(rt))
        with self.assertRaises(PermissionError):
            rt.decide(wi, wi.assignee, approve=True, reason="agent 自批")


class SoloInvariant4UpgradeWithoutMigration(unittest.TestCase):
    """④ 升级无迁移：加入第二个成员后，已有任务、证据链、历史原样可用。"""

    def test_adding_member_keeps_existing_work_intact(self):
        from sayelf_agent_ops.actors import Actor

        rt = _solo_runtime()
        wi = rt.run(_submit_titles(rt))
        events_before = [dict(e) for e in rt.events(wi)]
        history_before = [dict(h) for h in wi.history]

        rt.project.add_member(Actor(id="human.partner", kind="human", roles=("media.reviewer",)))

        self.assertEqual(wi.state, "DELIVERED")
        self.assertEqual([dict(e) for e in rt.events(wi)], events_before)
        self.assertEqual([dict(h) for h in wi.history], history_before)

    def test_same_runtime_serves_new_tasks_after_upgrade(self):
        from sayelf_agent_ops.actors import Actor

        rt = _solo_runtime()
        rt.project.add_member(Actor(id="human.partner", kind="human", roles=("media.reviewer",)))
        wi = rt.run(_submit_titles(rt))
        self.assertEqual(wi.state, "DELIVERED")


if __name__ == "__main__":
    unittest.main()
