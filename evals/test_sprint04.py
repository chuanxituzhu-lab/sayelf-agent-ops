"""Sprint 04：第二条真实技能链（大纲 → 短视频脚本）与桌面内核任务入口。"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from desktop.runtime import bootstrap
from desktop.runtime.kernel_tasks import run_kernel_task
from sayelf_agent_ops.actors import Project
from sayelf_agent_ops.executor import BuiltinExecutor
from sayelf_agent_ops.registry import build_registry
from sayelf_agent_ops.runtime import Runtime
from sayelf_agent_ops.skills.video_llm import make_model_handlers

from test_sprint03 import make_workitem

VIDEO_REQUEST = "根据资料做一条 45 秒的抖音短视频，介绍山野精灵工作台"


def scene(seconds, shot="近景", voice="口播"):
    return {"seconds": seconds, "shot": shot, "voiceover": voice, "caption": "字幕"}


class VideoModel:
    """Fake chat model for the outline → script chain."""

    model = "fake-model"

    def __init__(self, scripts=None, outline=None):
        self.calls = []
        self.scripts = scripts or [{"hook": "三秒看懂", "scenes": [scene(10), scene(15), scene(15)], "cta": "关注"}]
        self.outline = outline or {"outline": ["痛点", "方案", "演示", "结尾"]}
        self.last_usage = None

    def complete_json(self, system_prompt, payload):
        self.calls.append((system_prompt, payload))
        if "内容结构" in system_prompt:
            return self.outline
        script_calls = [c for c in self.calls if "短视频脚本" in c[0]]
        return self.scripts[min(len(script_calls), len(self.scripts)) - 1]


def runtime_with(model, remote=False, consent=False):
    registry = build_registry(("media",))
    return Runtime(
        Project.solo("human.nicola", registry=registry),
        registry=registry,
        executor=BuiltinExecutor(make_model_handlers(model, remote=remote, consent=consent), registry=registry),
    )


class VideoChainTests(unittest.TestCase):
    def test_v01_script_follows_outline_and_is_delivered(self):
        model = VideoModel()
        rt = runtime_with(model)
        wi = rt.run(rt.submit(VIDEO_REQUEST))
        self.assertEqual("DELIVERED", wi.state)
        self.assertEqual(["outline", "video-script"], [o["type"] for o in wi.outputs])
        script_payload = [p for s, p in model.calls if "短视频脚本" in s][0]
        self.assertEqual(["痛点", "方案", "演示", "结尾"], script_payload["outline"])
        self.assertEqual(45, script_payload["duration_seconds"])
        self.assertIn("| 1 | 10s |", wi.outputs[1]["content"])

    def test_v02_overlong_script_is_reworked_with_feedback(self):
        too_long = {"hook": "钩子", "scenes": [scene(30), scene(30), scene(30)], "cta": ""}
        ok = {"hook": "钩子", "scenes": [scene(10), scene(15), scene(15)], "cta": ""}
        model = VideoModel(scripts=[too_long, ok])
        rt = runtime_with(model)
        wi = rt.run(rt.submit(VIDEO_REQUEST))
        self.assertEqual("DELIVERED", wi.state)
        self.assertEqual(1, wi.rework_count)
        second = [p for s, p in model.calls if "短视频脚本" in s][1]
        self.assertTrue(any("总时长" in f for f in second["rework_feedback"]))

    def test_v03_scene_without_voiceover_fails_review(self):
        bad = {"hook": "钩子", "scenes": [scene(10), scene(10, voice=""), scene(10)], "cta": ""}
        rt = runtime_with(VideoModel(scripts=[bad]))
        wi = rt.run(rt.submit(VIDEO_REQUEST))
        self.assertEqual("REWORK", wi.state)
        review = [e for e in rt.events(wi) if e["event"] == "review"][-1]
        self.assertFalse({c["check"]: c["ok"] for c in review["checks"]}["script-scene-complete"])

    def test_v04_thin_outline_fails_review(self):
        rt = runtime_with(VideoModel(outline={"outline": ["只有一点"]}))
        wi = rt.run(rt.submit(VIDEO_REQUEST))
        self.assertNotEqual("DELIVERED", wi.state)

    def test_v05_malformed_scene_is_safe_error(self):
        rt = runtime_with(VideoModel(scripts=[{"hook": "h", "scenes": [{"seconds": "十"}], "cta": ""}]))
        wi = rt.run(rt.submit(VIDEO_REQUEST))
        self.assertEqual("WORKING", wi.state)
        self.assertEqual("MODEL_RESPONSE_INVALID",
                         [e for e in rt.events(wi) if e["event"] == "executor-failed"][-1]["code"])

    def test_v06_remote_without_consent_makes_no_call(self):
        model = VideoModel()
        rt = runtime_with(model, remote=True, consent=False)
        rt.run(rt.submit(VIDEO_REQUEST))
        self.assertEqual([], model.calls)


class DesktopKernelRunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "Sayelf"
        bootstrap.initialize(self.root, "media")
        bootstrap.configure_provider(self.root, "http://127.0.0.1:11434/v1", "local-model")
        bootstrap.set_role_active(self.root, "media.content-planner", True)

    def test_k01_video_script_workitem_runs_on_kernel(self):
        make_workitem(self.root, "WI-V1", VIDEO_REQUEST, channel="抖音")
        result = run_kernel_task(self.root, "WI-V1", VideoModel())
        self.assertEqual(0, result["code"])
        self.assertEqual("video-script", result["data"]["deliverable_type"])
        self.assertTrue(result["data"]["kernel_result"])
        self.assertIn("# 短视频脚本", result["data"]["result_content"])
        self.assertIn("## 内容大纲", result["data"]["result_content"])

    def test_k02_sidecar_action_uses_stored_request_and_key_env(self):
        make_workitem(self.root, "WI-V2", VIDEO_REQUEST, channel="抖音")
        model = VideoModel()
        out = io.StringIO()
        with patch("desktop.runtime.model_provider.OpenAICompatibleProvider", return_value=model), \
                patch.dict("os.environ", {"SAYELF_MODEL_API_KEY": "test-key"}), redirect_stdout(out):
            code = bootstrap.main(["kernel-run", "--data-dir", str(self.root), "--workitem-id", "WI-V2"])
        result = json.loads(out.getvalue())
        self.assertEqual(0, code)
        self.assertEqual("video-script", result["data"]["deliverable_type"])
        self.assertNotIn("test-key", out.getvalue())

    def test_k03_sidecar_without_key_reports_not_configured(self):
        make_workitem(self.root, "WI-V3", VIDEO_REQUEST, channel="抖音")
        out = io.StringIO()
        with patch.dict("os.environ", {"SAYELF_MODEL_API_KEY": ""}), redirect_stdout(out):
            code = bootstrap.main(["kernel-run", "--data-dir", str(self.root), "--workitem-id", "WI-V3"])
        self.assertEqual(10, code)
        self.assertEqual("MODEL_NOT_CONFIGURED", json.loads(out.getvalue())["data"]["reason"])

    def test_k04_review_failure_returns_reason_and_no_output_file(self):
        bad = {"hook": "", "scenes": [scene(10)], "cta": ""}
        make_workitem(self.root, "WI-V4", VIDEO_REQUEST, channel="抖音")
        result = run_kernel_task(self.root, "WI-V4", VideoModel(scripts=[bad]))
        self.assertEqual(20, result["code"])
        self.assertEqual("REVIEW_NOT_PASSED", result["data"]["reason"])
        self.assertEqual([], list((self.root / "outputs").glob("WI-V4-*")))


if __name__ == "__main__":
    unittest.main()
