"""Sprint 03：模型标题技能、Pack 级按需加载、桌面内核任务入口。"""
from __future__ import annotations

import io
import json
import subprocess
from contextlib import redirect_stdout
import sys
import tempfile
import unittest
from pathlib import Path

from desktop.runtime import bootstrap
from desktop.runtime.kernel_tasks import run_kernel_task
from sayelf_agent_ops.actors import Project
from sayelf_agent_ops.executor import BuiltinExecutor
from sayelf_agent_ops.loader import SkillLoader, SkillManifest
from sayelf_agent_ops.models import ExecutionPlan, PlanStep, WorkItem
from sayelf_agent_ops.registry import build_registry
from sayelf_agent_ops.router import Router
from sayelf_agent_ops.runtime import Runtime
from sayelf_agent_ops.skills.title_llm import make_llm_title_handler

ROOT = Path(__file__).resolve().parents[1]
OWNER = "human.nicola"


class TitleModel:
    """Fake chat model: first answer has duplicates, later answers are clean."""

    model = "fake-model"
    adapter_id = "fake"

    def __init__(self, answers=None):
        self.calls = []
        self.answers = answers
        self.last_usage = {"total_tokens": 42}

    def complete_json(self, system_prompt, payload):
        self.calls.append(payload)
        if self.answers is not None:
            return self.answers[min(len(self.calls), len(self.answers)) - 1]
        n = payload["count"]
        if len(self.calls) == 1:
            return {"titles": ["同一个标题"] * n}
        return {"titles": [f"{payload['topic']}的第{i}种写法" for i in range(1, n + 1)]}


def runtime_with(provider, remote=False, consent=False):
    registry = build_registry(("media",))
    handler = make_llm_title_handler(provider, remote=remote, consent=consent)
    return Runtime(
        Project.solo(OWNER, registry=registry),
        registry=registry,
        executor=BuiltinExecutor({"media.title-writing": handler}, registry=registry),
    )


class LlmTitleSkillTests(unittest.TestCase):
    def test_t01_model_titles_pass_review_after_rework(self):
        model = TitleModel()
        rt = runtime_with(model)
        wi = rt.run(rt.submit('给"一人公司 Agent Ops"生成 4 个公众号标题'))
        self.assertEqual("DELIVERED", wi.state)
        self.assertEqual(1, wi.rework_count)
        self.assertEqual(4, len(wi.outputs[0]["items"]))
        self.assertTrue(model.calls[1]["rework_feedback"], "second call must carry review feedback")
        evidence = wi.outputs[0]["evidence"]
        self.assertEqual(("llm", "fake-model", {"total_tokens": 42}),
                         (evidence["method"], evidence["model"], evidence["usage"]))

    def test_t02_remote_without_consent_never_calls_model(self):
        model = TitleModel()
        rt = runtime_with(model, remote=True, consent=False)
        wi = rt.run(rt.submit("写 3 个小红书标题"))
        self.assertEqual([], model.calls)
        self.assertEqual("WORKING", wi.state)
        failed = [e for e in rt.events(wi) if e["event"] == "executor-failed"]
        self.assertEqual("MODEL_CONSENT_REQUIRED", failed[-1]["code"])

    def test_t03_invalid_model_response_escalates_with_safe_code(self):
        rt = runtime_with(TitleModel(answers=[{"titles": "不是列表"}]))
        wi = rt.run(rt.submit("写 3 个公众号标题"))
        self.assertEqual("WORKING", wi.state)
        self.assertEqual("MODEL_RESPONSE_INVALID",
                         [e for e in rt.events(wi) if e["event"] == "executor-failed"][-1]["code"])

    def test_t04_rerun_after_failure_can_succeed(self):
        model = TitleModel(answers=[{"titles": 1}, {"titles": ["甲", "乙", "丙"]}])
        rt = runtime_with(model)
        wi = rt.run(rt.submit("写 3 个公众号标题"))
        self.assertEqual("WORKING", wi.state)
        rt.run(wi)
        self.assertEqual("DELIVERED", wi.state)


class PackLoadingTests(unittest.TestCase):
    def test_k01_media_only_registry_never_imports_engineering(self):
        code = ("import sys; from sayelf_agent_ops.registry import build_registry; "
                "r = build_registry(('media',)); "
                "print(r.loaded_industries, 'sayelf_agent_ops.packs.engineering' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
        self.assertEqual("('media',) False", out)

    def test_k02_other_industry_is_unroutable_not_misrouted(self):
        router = Router(build_registry(("media",)))
        with self.assertRaisesRegex(ValueError, "UNROUTABLE_DELIVERABLE"):
            router.route(WorkItem(id="X", input="对比两版 BOQ 的清单特征变化和漏项"))

    def test_k03_cross_industry_rule_needs_both_packs(self):
        both = build_registry(("media", "engineering"))
        self.assertIn("workflow.engineering-analysis-to-media", {r.id for r in both.route_rules})
        only = build_registry(("engineering",))
        self.assertNotIn("workflow.engineering-analysis-to-media", {r.id for r in only.route_rules})

    def test_k04_unknown_pack_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_PACK"):
            build_registry(("finance",))

    def test_k05_pack_manifest_license_applies_to_all_its_skills(self):
        registry = build_registry(("media",))
        loader = SkillLoader(
            registry, capabilities={"python"},
            pack_manifests={"media": SkillManifest("media", source="distilled:x/y",
                                                   license="CC-BY-NC-4.0", commercial_use=False)},
        )
        plan = ExecutionPlan(id="P", workitem_id="P", steps=(
            PlanStep(1, "media.content-planner", "media.title-writing", "title-list", "d"),))
        result = loader.load_for_plan(plan)
        self.assertIn("LICENSE_NONCOMMERCIAL", result.blocked["media.title-writing"])

    def test_k06_loaded_packs_tracks_context(self):
        loader = SkillLoader(build_registry(None), capabilities={"python"})
        plan = ExecutionPlan(id="P", workitem_id="P", steps=(
            PlanStep(1, "media.content-planner", "media.title-writing", "title-list", "d"),))
        loader.load_for_plan(plan)
        self.assertEqual(("media",), loader.loaded_packs)
        loader.release(plan)
        self.assertEqual((), loader.loaded_packs)


def make_workitem(root, workitem_id, request, channel=""):
    item_dir = root / "workitems" / workitem_id
    item_dir.mkdir()
    (item_dir / "request.json").write_text(json.dumps(
        {"id": workitem_id, "request": request, "channel": channel, "attachments": []},
        ensure_ascii=False), encoding="utf-8")
    return item_dir / "request.json"


class DesktopKernelTitlesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "Sayelf"
        bootstrap.initialize(self.root, "media")
        bootstrap.configure_provider(self.root, "http://127.0.0.1:11434/v1", "local-model")

    def test_d01_role_must_be_active(self):
        make_workitem(self.root, "WI-T1", "写 3 个公众号标题")
        with self.assertRaises(bootstrap.BootstrapError) as ctx:
            run_kernel_task(self.root, "WI-T1", TitleModel())
        self.assertEqual("ROLE_NOT_ACTIVE", ctx.exception.reason)

    def test_d02_titles_delivered_and_saved_locally(self):
        bootstrap.set_role_active(self.root, "media.content-planner", True)
        make_workitem(self.root, "WI-T2", '给"山野精灵"生成 3 个标题', channel="小红书")
        result = run_kernel_task(self.root, "WI-T2", TitleModel())
        self.assertEqual(0, result["code"])
        self.assertEqual("title-list", result["data"]["deliverable_type"])
        self.assertIn("1. ", result["data"]["result_content"])
        self.assertTrue((self.root / "outputs" / result["data"]["output_name"]).is_file())
        log = json.loads((self.root / "logs" / f"{result['data']['task_id']}.json").read_text(encoding="utf-8"))
        self.assertNotIn("山野精灵", json.dumps([e for e in log["events"] if e["event"] == "submit"],
                                                 ensure_ascii=False))

    def test_d03_remote_endpoint_requires_consent_before_call(self):
        bootstrap.set_role_active(self.root, "media.content-planner", True)
        bootstrap.configure_provider(self.root, "https://example.invalid/v1", "remote-model")
        make_workitem(self.root, "WI-T3", "写 3 个公众号标题")
        model = TitleModel()
        with self.assertRaises(bootstrap.BootstrapError) as ctx:
            run_kernel_task(self.root, "WI-T3", model)
        self.assertEqual("MODEL_CONSENT_REQUIRED", ctx.exception.reason)
        self.assertEqual([], model.calls)

    def test_d04_non_kernel_deliverable_is_rejected(self):
        bootstrap.set_role_active(self.root, "media.content-planner", True)
        make_workitem(self.root, "WI-T4", "写一篇完整公众号文章")
        with self.assertRaises(bootstrap.BootstrapError) as ctx:
            run_kernel_task(self.root, "WI-T4", TitleModel())
        self.assertEqual("UNROUTABLE_DELIVERABLE", ctx.exception.reason)

    def test_d05_workplan_outside_pack_gets_clear_message(self):
        request = make_workitem(self.root, "WI-ENG-1", "对比两版 BOQ 的清单特征变化和漏项")
        out = io.StringIO()
        with redirect_stdout(out):
            code = bootstrap.main(["plan", "--data-dir", str(self.root), "--request-file", str(request)])
        self.assertEqual(10, code)
        self.assertEqual("UNROUTABLE_DELIVERABLE", json.loads(out.getvalue())["data"]["reason"])


if __name__ == "__main__":
    unittest.main()
