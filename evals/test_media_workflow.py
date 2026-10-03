import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from desktop.runtime import bootstrap
from desktop.runtime.media_workflow import (
    ROLE_IDS,
    approve_and_export,
    execute_media_workflow,
    record_performance_review,
)
from desktop.runtime.model_provider import OpenAICompatibleProvider, ProviderError


class FakeProvider:
    def __init__(self, fail_stage=None):
        self.calls = []
        self.fail_stage = fail_stage

    def complete_json(self, system_prompt, user_payload):
        self.calls.append((system_prompt, user_payload))
        if self.fail_stage and self.fail_stage in system_prompt and self.fail_stage not in {
            prompt for prompt, _ in self.calls[:-1]
        }:
            raise ProviderError("MODEL_UNAVAILABLE")
        if "自媒体内容策划" in system_prompt:
            return {
                "core_message": "围绕产品核心价值，给出清晰实用的体验信息。",
                "title_options": ["标题一", "标题二", "标题三"],
                "outline": ["开场", "体验", "总结"],
                "draft_content": "这是一段基于用户提供资料整理的内容草稿。\n\n重点说明实际体验和适用场景。",
                "claims_to_verify": [{
                    "claim": "产品体验来自用户素材",
                    "source_reference": "材料1：product.txt",
                    "status": "supported_by_input",
                }],
            }
        if "自媒体内容制作岗位" in system_prompt:
            return {
                "cover_concept": "突出产品与自然光下的使用场景。",
                "visual_brief": "主体清晰，保留真实环境，不添加未提供的产品功能。",
                "image_prompt": "自然光产品体验场景，真实摄影风格。",
                "asset_checklist": ["确认图片来源和使用权", "检查封面可读性"],
            }
        if "自媒体运营增长岗位" in system_prompt:
            return {
                "platform_title": "小红书体验分享标题",
                "platform_body": "根据素材整理的发布正文，具体事实请人工核对。",
                "hashtags": ["#体验分享", "#内容创作"],
                "call_to_action": "欢迎分享你的使用体验。",
                "publishing_checklist": [
                    "核对账号与平台当前规范",
                    "核对正文事实及产品信息",
                    "确认素材版权与链接有效性",
                ],
            }
        raise AssertionError("unknown stage")


class MediaWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "Sayelf"
        bootstrap.initialize(self.root, "media")
        for role_id in ROLE_IDS:
            bootstrap.set_role_active(self.root, role_id, True)
        bootstrap.configure_provider(
            self.root, "http://127.0.0.1:11434/v1", "offline-test-model"
        )
        item_dir = self.root / "workitems" / "WI-MEDIA-1"
        evidence_dir = self.root / "evidence" / "WI-MEDIA-1"
        item_dir.mkdir()
        evidence_dir.mkdir()
        (evidence_dir / "product.txt").write_text("产品资料文本", encoding="utf-8")
        (item_dir / "request.json").write_text(json.dumps({
            "id": "WI-MEDIA-1",
            "request": "根据资料写一篇小红书产品体验笔记。",
            "channel": "小红书",
            "attachments": [{
                "name": "product.txt",
                "relative_path": "evidence/WI-MEDIA-1/product.txt",
                "extracted_text": "产品特点来自用户提交的本地资料。",
                "extraction_status": "文字文件已读取",
            }],
        }, ensure_ascii=False), encoding="utf-8")

    def test_full_flow_generates_reviewable_package_and_local_zip(self):
        provider = FakeProvider()
        response = execute_media_workflow(self.root, "WI-MEDIA-1", provider)
        self.assertEqual(0, response["code"])
        result = response["data"]
        self.assertEqual("NEEDS_REVIEW", result["state"])
        self.assertEqual(3, len(provider.calls))
        self.assertEqual("产品特点来自用户提交的本地资料。", provider.calls[0][1]["sources"][1]["text"])
        self.assertNotIn("relative_path", str(provider.calls[0][1]))
        self.assertNotIn("产品资料文本", str(provider.calls[0][1]))
        self.assertIn("发布前人工检查", result["markdown"])
        self.assertIn("待核实事实", result["markdown"])

        edited = result["markdown"] + "\n人工补充的校对说明。\n"
        approved = approve_and_export(self.root, "WI-MEDIA-1", edited)
        package = Path(approved["data"]["package_path"])
        self.assertTrue(package.is_file())
        with zipfile.ZipFile(package) as archive:
            files = set(archive.namelist())
            self.assertEqual({"publish-package.md", "manifest.json", "source-index.json"}, files)
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual("approved-for-manual-publishing", manifest["state"])
            self.assertEqual(edited, archive.read("publish-package.md").decode("utf-8"))
        self.assertEqual(0, approve_and_export(self.root, "WI-MEDIA-1", edited)["code"])
        review = record_performance_review(self.root, "WI-MEDIA-1", {
            "views": 1000, "likes": 40, "saves": 25, "comments": 5, "shares": 10,
        })
        self.assertEqual(0.08, review["data"]["rates"]["engagement_rate"])
        self.assertEqual(2, review["data"]["approved_version"])
        report_path = Path(review["data"]["report_path"])
        self.assertIn("没有同平台、同类型内容的历史基线", report_path.read_text(encoding="utf-8"))
        with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection, connection:
            states = connection.execute(
                "SELECT state FROM workflow_runs WHERE workitem_id='WI-MEDIA-1'"
            ).fetchall()
            self.assertEqual([("COMPLETED",)], states)
            saved_reviews = connection.execute(
                "SELECT COUNT(*) FROM performance_reviews WHERE workitem_id='WI-MEDIA-1'"
            ).fetchone()[0]
            self.assertEqual(1, saved_reviews)

    def test_performance_review_requires_approved_package_and_valid_counts(self):
        with self.assertRaisesRegex(Exception, "WORKFLOW_INVALID"):
            record_performance_review(self.root, "WI-MEDIA-1", {"views": 10})
        provider = FakeProvider()
        draft = execute_media_workflow(self.root, "WI-MEDIA-1", provider)["data"]["markdown"]
        approve_and_export(self.root, "WI-MEDIA-1", draft)
        with self.assertRaisesRegex(Exception, "WORKFLOW_INVALID"):
            record_performance_review(self.root, "WI-MEDIA-1", {"views": True})
        with self.assertRaisesRegex(Exception, "WORKFLOW_INVALID"):
            record_performance_review(self.root, "WI-MEDIA-1", {"views": -1})

    def test_performance_review_is_bound_to_latest_approved_version(self):
        draft = execute_media_workflow(self.root, "WI-MEDIA-1", FakeProvider())["data"]["markdown"]
        approved = approve_and_export(self.root, "WI-MEDIA-1", draft)
        self.assertEqual(1, approved["data"]["version"])
        with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection, connection:
            row = connection.execute(
                "SELECT run_id, content_json FROM workflow_results WHERE workitem_id='WI-MEDIA-1'"
            ).fetchone()
            pending = json.loads(row[1])
            pending["version"] = 2
            pending["markdown"] += "\n未审核修改"
            content = json.dumps(pending, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            connection.execute(
                "INSERT INTO workflow_results "
                "(workitem_id, version, run_id, content_json, content_sha256, review_state, created_at) "
                "VALUES ('WI-MEDIA-1', 2, ?, ?, ?, 'NEEDS_REVIEW', '2026-10-04T00:00:00Z')",
                (row[0], content, "pending-digest"),
            )
        with self.assertRaisesRegex(Exception, "WORKFLOW_INVALID"):
            record_performance_review(self.root, "WI-MEDIA-1", {"views": 50})

    def test_remote_provider_requires_per_run_consent_before_any_call(self):
        bootstrap.configure_provider(self.root, "https://example.invalid/v1", "remote-test")
        provider = FakeProvider()
        with self.assertRaisesRegex(Exception, "MODEL_CONSENT_REQUIRED"):
            execute_media_workflow(self.root, "WI-MEDIA-1", provider, allow_external=False)
        self.assertEqual([], provider.calls)

    def test_missing_role_blocks_without_calling_provider(self):
        bootstrap.set_role_active(self.root, "media.creative-producer", False)
        provider = FakeProvider()
        response = execute_media_workflow(self.root, "WI-MEDIA-1", provider)
        self.assertEqual(11, response["code"])
        self.assertEqual(["media.creative-producer"], response["data"]["missing_roles"])
        self.assertEqual([], provider.calls)

    def test_failure_resume_reuses_accepted_upstream_stage(self):
        first = FakeProvider(fail_stage="自媒体内容制作岗位")
        failed = execute_media_workflow(self.root, "WI-MEDIA-1", first)
        self.assertEqual(20, failed["code"])
        self.assertTrue(failed["data"]["resumable"])
        self.assertEqual(2, len(first.calls))

        retry = FakeProvider()
        resumed = execute_media_workflow(
            self.root, "WI-MEDIA-1", retry, resume_run_id=failed["data"]["run_id"]
        )
        self.assertEqual(0, resumed["code"])
        self.assertEqual(2, len(retry.calls))
        with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection, connection:
            stages = connection.execute(
                "SELECT stage FROM workflow_stages WHERE run_id=? ORDER BY stage",
                (failed["data"]["run_id"],),
            ).fetchall()
        self.assertEqual(3, len(stages))

    def test_provider_adapter_rejects_invalid_json_without_leaking_input(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self, _limit):
                return b'{"choices":[{"message":{"content":"not-json"}}]}'

        provider = OpenAICompatibleProvider(
            "http://127.0.0.1:8000/v1", "test", "secret", opener=lambda *_args, **_kwargs: Response()
        )
        with self.assertRaisesRegex(ProviderError, "MODEL_RESPONSE_INVALID"):
            provider.complete_json("private prompt", {"private": "request"})

    def test_provider_adapter_sends_only_json_payload_and_keeps_key_in_header(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self, _limit):
                return b'{"choices":[{"message":{"content":"{\\"status\\":\\"ok\\"}"}}]}'

        seen = {}
        def opener(request, timeout):
            seen["url"] = request.full_url
            seen["auth"] = request.get_header("Authorization")
            seen["body"] = request.data.decode("utf-8")
            seen["timeout"] = timeout
            return Response()

        provider = OpenAICompatibleProvider(
            "https://model.example/v1", "model-test", "secret-value", opener=opener
        )
        self.assertEqual({"status": "ok"}, provider.complete_json("system", {"request": "public test"}))
        self.assertEqual("https://model.example/v1/chat/completions", seen["url"])
        self.assertEqual("Bearer secret-value", seen["auth"])
        self.assertNotIn("secret-value", seen["body"])
        self.assertEqual(90, seen["timeout"])


if __name__ == "__main__":
    unittest.main()
