import unittest

from sayelf_agent_ops.models import WorkItem
from sayelf_agent_ops.planner import MinimumPlanner, apply_routing
from sayelf_agent_ops.registry import build_default_registry
from sayelf_agent_ops.router import Router
from sayelf_agent_ops.state import StateEngine, WorkState, TransitionRejected


class RegistryAndStateTests(unittest.TestCase):
    def test_registry_is_idle_by_default(self):
        registry = build_default_registry()
        self.assertEqual(0, registry.active_roles)
        self.assertEqual(0, registry.loaded_skills)

    def test_illegal_state_jump_is_rejected(self):
        engine = StateEngine()
        wi = WorkItem(
            id="WI-X",
            input="test",
            goal="test",
            deliverable="test",
            industry="media",
        )
        with self.assertRaises(TransitionRejected):
            engine.transition(wi, WorkState.WORKING)

    def test_first_vertical_slice_can_reach_ready(self):
        registry = build_default_registry()
        router = Router(registry)
        planner = MinimumPlanner()
        state = StateEngine()

        wi = WorkItem(
            id="WI-0001",
            input="写 5 个公众号标题",
            goal="获得 5 个标题",
            deliverable="公众号标题 × 5",
            industry="media",
        )

        state.transition(wi, WorkState.SCOPED)
        decision = router.route(wi)
        plan = planner.build(wi, decision)
        apply_routing(wi, decision, plan)
        state.transition(wi, WorkState.WORKING)
        wi.outputs.append({"type": "title-list", "items": ["a", "b", "c", "d", "e"]})
        state.transition(wi, WorkState.READY)

        self.assertEqual("READY", wi.state)
        self.assertEqual("media.content-planner", wi.selected_role)
        self.assertEqual(["media.title-writing"], wi.selected_skills)
        self.assertIn("media.creative-producer", wi.excluded_roles)
        self.assertIn("media.growth-operator", wi.excluded_roles)


if __name__ == "__main__":
    unittest.main()
