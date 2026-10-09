import unittest
from dataclasses import replace

from sayelf_agent_ops.loader import (
    SkillLoader,
    SkillManifest,
    discover_capabilities,
)
from sayelf_agent_ops.models import ExecutionPlan, PlanStep
from sayelf_agent_ops.registry import build_default_registry


def plan(pid, *skills):
    return ExecutionPlan(
        id=pid,
        workitem_id=pid,
        steps=tuple(
            PlanStep(step=i, role="r", skill=s, output="o", done_when="d")
            for i, s in enumerate(skills, start=1)
        ),
    )


class SkillLoaderTests(unittest.TestCase):
    def setUp(self):
        self.registry = build_default_registry()

    def test_l01_nothing_loaded_by_default(self):
        loader = SkillLoader(self.registry, capabilities={"python"})
        self.assertEqual(0, loader.loaded_skills)
        self.assertEqual(0, self.registry.loaded_skills)  # Sprint 01 rule kept

    def test_l02_loads_only_plan_skills(self):
        loader = SkillLoader(self.registry, capabilities={"python"})
        result = loader.load_for_plan(plan("P1", "media.title-writing"))
        self.assertTrue(result.ok)
        self.assertEqual(("media.title-writing",), result.loaded)
        self.assertEqual(1, loader.loaded_skills)
        self.assertFalse(loader.is_loaded("media.longform-writing"))

    def test_l03_release_unloads(self):
        loader = SkillLoader(self.registry, capabilities={"python"})
        p = plan("P1", "media.title-writing")
        loader.load_for_plan(p)
        self.assertEqual(("media.title-writing",), loader.release(p))
        self.assertEqual(0, loader.loaded_skills)

    def test_l04_shared_skill_survives_other_plan_release(self):
        loader = SkillLoader(self.registry, capabilities={"python"})
        p1, p2 = plan("P1", "media.title-writing"), plan("P2", "media.title-writing")
        loader.load_for_plan(p1)
        loader.load_for_plan(p2)
        loader.release(p1)
        self.assertTrue(loader.is_loaded("media.title-writing"))

    def test_l05_context_budget_blocks_all_or_nothing(self):
        loader = SkillLoader(self.registry, capabilities={"python"}, max_loaded=2)
        result = loader.load_for_plan(plan(
            "P1",
            "media.visual-direction",
            "media.article-image-generation",
            "media.image-content-matching",
        ))
        self.assertFalse(result.ok)
        self.assertEqual(0, loader.loaded_skills)
        self.assertTrue(all(v.startswith("CONTEXT_BUDGET") for v in result.blocked.values()))

    def test_l06_noncommercial_license_blocked_in_commercial_mode(self):
        manifests = {
            "media.title-writing": SkillManifest(
                "media.title-writing",
                source="distilled:example/video-talkcraft",
                license="PolyForm-Noncommercial-1.0.0",
                commercial_use=False,
            )
        }
        loader = SkillLoader(self.registry, capabilities={"python"}, manifests=manifests)
        result = loader.load_for_plan(plan("P1", "media.title-writing"))
        self.assertIn("LICENSE_NONCOMMERCIAL", result.blocked["media.title-writing"])

    def test_l07_noncommercial_allowed_for_study_mode(self):
        manifests = {
            "media.title-writing": SkillManifest(
                "media.title-writing", license="CC-BY-NC-4.0", commercial_use=False
            )
        }
        loader = SkillLoader(
            self.registry, capabilities={"python"}, manifests=manifests, commercial=False
        )
        self.assertTrue(loader.load_for_plan(plan("P1", "media.title-writing")).ok)

    def test_l08_missing_capability_blocks_with_reason(self):
        skills = dict(self.registry.skills)
        skills["media.article-image-generation"] = replace(
            skills["media.article-image-generation"], required_capabilities=("image-model",)
        )
        registry = replace(self.registry, skills=skills)
        loader = SkillLoader(registry, capabilities={"python"})
        result = loader.load_for_plan(plan("P1", "media.article-image-generation"))
        self.assertEqual(
            "MISSING_CAPABILITY:image-model",
            result.blocked["media.article-image-generation"],
        )

    def test_l09_unregistered_skill_blocked(self):
        loader = SkillLoader(self.registry, capabilities={"python"})
        result = loader.load_for_plan(plan("P1", "media.not-a-skill"))
        self.assertEqual("UNREGISTERED", result.blocked["media.not-a-skill"])

    def test_l10_discover_capabilities_uses_probes(self):
        caps = discover_capabilities({
            "image-model": lambda: True,
            "broken": lambda: 1 / 0,
        })
        self.assertIn("python", caps)
        self.assertIn("image-model", caps)
        self.assertNotIn("broken", caps)


if __name__ == "__main__":
    unittest.main()
