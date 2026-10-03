from dataclasses import replace
import unittest

from sayelf_agent_ops.models import RoleContract, SkillContract, WorkItem
from sayelf_agent_ops.planner import MinimumPlanner, apply_routing
from sayelf_agent_ops.packs import IndustryPack, RouteRule
from sayelf_agent_ops.registry import Registry, build_default_registry
from sayelf_agent_ops.router import Router
from sayelf_agent_ops.state import StateEngine, WorkState, TransitionRejected


class RegistryAndStateTests(unittest.TestCase):
    def test_registry_is_idle_by_default(self):
        registry = build_default_registry()
        self.assertEqual(0, registry.active_roles)
        self.assertEqual(0, registry.loaded_skills)

    def test_custom_industry_pack_routes_without_core_changes(self):
        role = RoleContract(
            id="research.editor",
            industry="research",
            name="Research Editor",
            responsibility="Turn notes into a research brief.",
            owned_outputs=("research-brief",),
            allowed_skills=("research.summarize",),
        )
        skill = SkillContract(
            id="research.summarize",
            owner_scope="research.editor",
            purpose="Summarize research notes.",
            accepted_inputs=("notes",),
            produced_outputs=("research-brief",),
        )
        pack = IndustryPack(
            id="research",
            industry="research",
            roles=(role,),
            skills=(skill,),
            route_rules=(
                RouteRule(
                    id="research.brief",
                    predicate=lambda text: "research brief" in text,
                    priority=10,
                    deliverable_type="research-brief",
                    industry="research",
                    level="R1",
                    role="research.editor",
                    skills=("research.summarize",),
                    reason="The requested deliverable is a research brief.",
                ),
            ),
        )
        registry = Registry()
        registry.register_pack(pack)

        decision = Router(registry).route(
            WorkItem(id="WI-R1", input="Create a research brief from these notes")
        )

        self.assertEqual("research.editor", decision.selected_role)
        self.assertEqual(("research.summarize",), decision.selected_skills)
        self.assertEqual(0, registry.active_roles)
        self.assertEqual(0, registry.loaded_skills)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PACK:research"):
            registry.register_pack(pack)

        invalid_role = replace(role, allowed_skills=("research.missing",))
        invalid_pack = IndustryPack(
            id="invalid-research",
            industry="research",
            roles=(invalid_role,),
            skills=(),
            route_rules=(),
        )
        with self.assertRaisesRegex(ValueError, "ROLE_SKILL_MISMATCH"):
            Registry().register_pack(invalid_pack)

        ambiguous_pack = replace(
            pack,
            route_rules=pack.route_rules
            + (replace(pack.route_rules[0], id="research.brief-conflict"),),
        )
        ambiguous_registry = Registry()
        ambiguous_registry.register_pack(ambiguous_pack)
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_ROUTING_RULE"):
            Router(ambiguous_registry).route(
                WorkItem(id="WI-R2", input="Create a research brief from these notes")
            )

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
