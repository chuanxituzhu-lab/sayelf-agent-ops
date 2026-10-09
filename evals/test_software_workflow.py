import unittest
import json
import tempfile
from pathlib import Path

from sayelf_agent_ops.actors import Project
from sayelf_agent_ops.executor import BuiltinExecutor, SkillExecutionError
from sayelf_agent_ops.registry import build_registry
from sayelf_agent_ops.runtime import Runtime
from sayelf_agent_ops.skills.software_llm import _files, make_software_handlers
from desktop.runtime import bootstrap
from desktop.runtime.kernel_tasks import run_kernel_task


class FakeProvider:
    adapter_id = "test-provider"
    model = "offline-fixture"
    last_usage = {"total_tokens": 1}

    def __init__(self):
        self.calls = []

    def complete_json(self, system_prompt, user_payload):
        self.calls.append((system_prompt, user_payload))
        if system_prompt.startswith("你是软件方案设计岗位"):
            return {
                "summary": "本地待办页，状态仅保存在浏览器内存。",
                "assumptions": ["本轮仅提供前端静态文件。"],
                "acceptance_criteria": ["可新增任务", "可切换完成状态"],
                "files": [{"path": "index.html", "purpose": "页面入口"}],
            }
        if system_prompt.startswith("你是软件开发岗位"):
            return {
                "summary": "生成静态待办页面和交互脚本。",
                "files": [{"path": "index.html", "content": "<!doctype html><title>Todos</title>"}],
                "limitations": ["尚未执行浏览器验证。"],
                "apply_instructions": ["审阅后复制到目标目录。"],
            }
        return {
            "test_cases": [{"name": "新增任务", "steps": ["输入任务", "点击新增"], "expected": "列表出现任务"}],
            "risks": ["尚未验证浏览器兼容性。"],
            "verification_state": "not_run",
            "review_summary": "测试用例已列出，尚未执行。",
        }


class SoftwareWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.registry = build_registry(("software",))
        for role_id in ("software.architect", "software.engineer", "software.qa"):
            self.registry.activate_role(role_id)
        self.provider = FakeProvider()
        handlers = make_software_handlers(self.provider, remote=False, consent=False)
        self.runtime = Runtime(
            Project.solo("human.owner", registry=self.registry),
            registry=self.registry,
            executor=BuiltinExecutor(handlers, registry=self.registry),
        )

    def test_bounded_software_task_uses_minimum_two_roles_and_keeps_independent_qa(self):
        workitem = self.runtime.submit("开发一个本地待办软件网页，支持新增和完成任务", industry="software")
        result = self.runtime.run(workitem)

        self.assertEqual("DELIVERED", result.state)
        self.assertEqual(
            ["software-change", "software-test-report"],
            [output["type"] for output in result.outputs],
        )
        self.assertEqual(
            ["software.engineer", "software.qa"],
            [output["role"] for output in result.outputs],
        )
        self.assertEqual("not_run", result.outputs[-1]["verification_state"])
        self.assertEqual(2, len(self.provider.calls))
        actors = {event["actor"] for event in self.runtime.events(result) if event["event"] == "step-completed"}
        self.assertEqual({
            "agent.software.engineer", "agent.software.qa",
        }, actors)
        self.assertEqual("agent.software.reviewer", result.reviewer)

    def test_cross_cutting_task_adds_architect_only_when_needed(self):
        workitem = self.runtime.submit("规划一个跨模块软件平台架构和技术选型，并实现与测试", industry="software")
        result = self.runtime.run(workitem)

        self.assertEqual("DELIVERED", result.state)
        self.assertEqual(
            ["software.architect", "software.engineer", "software.qa"],
            [output["role"] for output in result.outputs],
        )
        self.assertEqual(3, len(self.provider.calls))

    def test_generated_file_paths_reject_parent_traversal(self):
        with self.assertRaises(SkillExecutionError):
            _files([{"path": "../outside.py", "content": "no"}], content_required=True)

    def test_generated_private_key_material_is_rejected(self):
        with self.assertRaisesRegex(SkillExecutionError, "MODEL_OUTPUT_REDACTION_REQUIRED"):
            _files([{"path": "settings.py", "content": "-----BEGIN PRIVATE KEY-----"}], content_required=True)

    def test_workplan_exposes_minimum_role_count_and_professional_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "software-workspace"
            bootstrap.initialize(root, "software")
            for role_id in ("software.engineer", "software.qa"):
                bootstrap.set_role_active(root, role_id, True)
            workitem_dir = root / "workitems" / "WI-PLAN1"
            workitem_dir.mkdir()
            request_file = workitem_dir / "request.json"
            request_file.write_text(json.dumps({
                "id": "WI-PLAN1", "request": "修复登录界面按钮报错", "channel": "软件开发",
                "attachments": [],
            }, ensure_ascii=False), encoding="utf-8")

            result = bootstrap.create_workplan(root, request_file)

            self.assertEqual(0, result["code"])
            self.assertEqual(2, result["data"]["routing"]["role_count"])
            self.assertEqual(["software.engineer", "software.qa"], result["data"]["routing"]["selected_roles"])
            self.assertIn("独立审核", result["data"]["result_content"])
            self.assertEqual("planned", result["data"]["state"])

    def test_remote_provider_fails_closed_without_consent(self):
        provider = FakeProvider()
        handler = make_software_handlers(provider, remote=True, consent=False)["software.architecture-design"]
        from sayelf_agent_ops.models import PlanStep, WorkItem

        with self.assertRaisesRegex(SkillExecutionError, "MODEL_CONSENT_REQUIRED"):
            handler(PlanStep(1, "software.architect", "software.architecture-design", "software-design", "present"),
                    WorkItem("WI-1", "开发一个应用"), [])
        self.assertEqual([], provider.calls)

    def test_remote_request_with_credential_is_blocked_before_send(self):
        provider = FakeProvider()
        handler = make_software_handlers(provider, remote=True, consent=True)["software.architecture-design"]
        from sayelf_agent_ops.models import PlanStep, WorkItem

        with self.assertRaisesRegex(SkillExecutionError, "MODEL_INPUT_REDACTION_REQUIRED"):
            handler(PlanStep(1, "software.architect", "software.architecture-design", "software-design", "present"),
                    WorkItem("WI-2", "实现 API，api_key=abcdefghijklmnopqrstuvwxyz123456"), [])
        self.assertEqual([], provider.calls)

    def test_desktop_kernel_saves_role_artifacts_locally(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "software-workspace"
            bootstrap.initialize(root, "software")
            bootstrap.configure_provider(root, "http://127.0.0.1:11434/v1", "offline-fixture")
            for role_id in ("software.engineer", "software.qa"):
                bootstrap.set_role_active(root, role_id, True)
            workitem_dir = root / "workitems" / "WI-SW1"
            workitem_dir.mkdir()
            (workitem_dir / "request.json").write_text(json.dumps({
                "id": "WI-SW1", "request": "开发一个本地待办软件网页，支持新增和完成任务",
                "channel": "软件开发", "attachments": [],
            }, ensure_ascii=False), encoding="utf-8")

            result = run_kernel_task(root, "WI-SW1", FakeProvider())

            self.assertEqual(0, result["code"])
            self.assertEqual("software-feature-package", result["data"]["deliverable_type"])
            self.assertNotIn("软件方案设计", result["data"]["result_content"])
            self.assertIn("软件开发成果", result["data"]["result_content"])
            self.assertIn("未执行", result["data"]["result_content"])
            saved = root / "outputs" / result["data"]["output_name"]
            self.assertTrue(saved.is_file())
            log = next((root / "logs").glob("KT-*.json")).read_text(encoding="utf-8")
            self.assertNotIn("开发一个本地待办", log)


if __name__ == "__main__":
    unittest.main()
