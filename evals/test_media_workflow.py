import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from desktop.runtime import bootstrap
from desktop.runtime.media_workflow import (
    ROLE_IDS,
    approve_and_export,
    execute_media_workflow,
    record_performance_review,
)
from desktop.runtime.model_provider import OpenAICompatibleProvider, ProviderError


class FakeProvider:
    def __init__(self, fail_stage=None, error_code="MODEL_UNAVAILABLE"):
        self.calls = []
        self.fail_stage = fail_stage
        self.error_code = error_code

    def complete_json(self, system_prompt, user_payload):
        self.calls.append((system_prompt, user_payload))
        if self.fail_stage and self.fail_stage in system_prompt and self.fail_stage not in {
            prompt for prompt, _ in self.calls[:-1]
        }:
            raise ProviderError(self.error_code)
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
        self.assertTrue(result["output_saved"])
        with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection:
            events = connection.execute(
                "SELECT event_type, evidence_json FROM workflow_events "
                "WHERE run_id=? AND event_type LIKE 'provider-call-%' ORDER BY event_id",
                (result["run_id"],),
            ).fetchall()
        call_events = [(event_type, json.loads(evidence)) for event_type, evidence in events]
        starts = [evidence for event_type, evidence in call_events if event_type == "provider-call-started"]
        successes = [evidence for event_type, evidence in call_events if event_type == "provider-call-succeeded"]
        self.assertEqual(3, len(starts))
        self.assertEqual(3, len(successes))
        self.assertEqual({item["call_id"] for item in starts}, {item["call_id"] for item in successes})
        contract_fields = {
            "tool", "call_id", "permission", "scope", "approval", "evidence",
            "data_classification", "state_change", "next_check",
        }
        for evidence in starts + successes:
            self.assertTrue(contract_fields.issubset(evidence))
        self.assertEqual("Sensitive", starts[0]["data_classification"])
        self.assertEqual("ModelProvider.complete_json", starts[0]["tool"])
        self.assertEqual("configured-local-endpoint", starts[0]["permission"])
        self.assertEqual("not-required", starts[0]["approval"]["status"])
        self.assertIsNone(starts[0]["approval"]["approval_id"])
        self.assertEqual(starts[0]["call_id"], starts[0]["approval"]["call_id"])
        self.assertIn("request_sha256", starts[0]["evidence"])
        self.assertEqual("1", starts[0]["adapter_version"])
        self.assertEqual("not-reported-by-provider", successes[0]["usage"]["status"])
        with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection:
            accepted = connection.execute(
                "SELECT evidence_json FROM workflow_events "
                "WHERE run_id=? AND event_type='stage-accepted' ORDER BY event_id",
                (result["run_id"],),
            ).fetchall()
        stage_by_call = {json.loads(evidence)["call_id"]: json.loads(evidence)["output_sha256"] for (evidence,) in accepted}
        for evidence in successes:
            self.assertEqual(
                evidence["evidence"]["validated_output_sha256"],
                stage_by_call[evidence["call_id"]],
            )
        self.assertNotIn("产品特点来自用户提交的本地资料。", json.dumps(call_events, ensure_ascii=False))
        with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection:
            draft_event = connection.execute(
                "SELECT state, evidence_json FROM workflow_events "
                "WHERE run_id=? AND event_type='draft-mirror-saved'",
                (result["run_id"],),
            ).fetchone()
        self.assertEqual("NEEDS_REVIEW", draft_event[0])
        self.assertEqual(result["output_name"], json.loads(draft_event[1])["output_name"])

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
        self.assertFalse(package.parent.joinpath("manifest.json").exists())
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

    def test_remote_run_records_per_run_scope_without_persisting_material(self):
        endpoint = "https://example.invalid/v1"
        bootstrap.configure_provider(self.root, endpoint, "remote-test")
        response = execute_media_workflow(
            self.root, "WI-MEDIA-1", FakeProvider(), allow_external=True
        )
        self.assertEqual(0, response["code"])
        with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection:
            rows = connection.execute(
                "SELECT evidence_json FROM workflow_events "
                "WHERE run_id=? AND event_type='provider-call-started'",
                (response["data"]["run_id"],),
            ).fetchall()
        self.assertEqual(3, len(rows))
        approval_ids = set()
        for (serialized,) in rows:
            evidence = json.loads(serialized)
            self.assertEqual("per-run-user-confirmed", evidence["permission"])
            self.assertEqual("granted", evidence["approval"]["status"])
            self.assertEqual(evidence["call_id"], evidence["approval"]["call_id"])
            approval_ids.add(evidence["approval"]["approval_id"])
            self.assertEqual(evidence["evidence"]["request_sha256"], evidence["approval"]["request_sha256"])
            self.assertEqual([], evidence["scope"]["tools"])
            self.assertEqual(
                sorted(evidence["scope"]["payload_fields"]),
                evidence["scope"]["payload_fields"],
            )
            self.assertNotIn("产品特点来自用户提交的本地资料。", serialized)
        self.assertEqual(3, len(approval_ids))

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
        with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection:
            events = connection.execute(
                "SELECT event_type, evidence_json FROM workflow_events "
                "WHERE run_id=? AND event_type LIKE 'provider-call-%' ORDER BY event_id",
                (failed["data"]["run_id"],),
            ).fetchall()
        decoded = [(kind, json.loads(evidence)) for kind, evidence in events]
        started = [data for kind, data in decoded if kind == "provider-call-started"]
        failed_calls = [data for kind, data in decoded if kind == "provider-call-failed"]
        self.assertEqual(2, len(started))
        self.assertEqual(1, len(failed_calls))
        self.assertEqual(started[-1]["call_id"], failed_calls[0]["call_id"])
        self.assertEqual("MODEL_UNAVAILABLE", failed_calls[0]["error_code"])
        self.assertIn("manual-confirmation-required", failed_calls[0]["retry_policy"])
        self.assertNotIn("产品特点来自用户提交的本地资料。", json.dumps(decoded, ensure_ascii=False))

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

    def test_invalid_checkpoint_is_rejected_before_new_provider_calls(self):
        for matching_digest in (False, True):
            with self.subTest(matching_digest=matching_digest):
                failed = execute_media_workflow(
                    self.root, "WI-MEDIA-1", FakeProvider(fail_stage="自媒体内容制作岗位")
                )
                run_id = failed["data"]["run_id"]
                corrupted = '{"core_message":"incomplete checkpoint"}'
                digest = hashlib.sha256(corrupted.encode("utf-8")).hexdigest() if matching_digest else "invalid"
                with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection, connection:
                    connection.execute(
                        "UPDATE workflow_stages SET output_json=?, output_sha256=? WHERE run_id=?",
                        (corrupted, digest, run_id),
                    )
                retry = FakeProvider()
                response = execute_media_workflow(
                    self.root, "WI-MEDIA-1", retry, resume_run_id=run_id
                )
                self.assertEqual(20, response["code"])
                self.assertEqual("WORKFLOW_CHECKPOINT_INVALID", response["data"]["reason"])
                self.assertFalse(response["data"]["resumable"])
                self.assertEqual([], retry.calls)
                with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection:
                    state = connection.execute(
                        "SELECT state FROM workflow_runs WHERE run_id=?", (run_id,)
                    ).fetchone()[0]
                self.assertEqual("FAILED", state)

    def test_unrecognized_provider_error_code_is_redacted(self):
        secret_marker = "USER_SUPPLIED_ERROR_MARKER"
        response = execute_media_workflow(
            self.root,
            "WI-MEDIA-1",
            FakeProvider(fail_stage="自媒体内容策划", error_code=secret_marker),
        )
        self.assertEqual(20, response["code"])
        self.assertEqual("MODEL_CALL_FAILED", response["data"]["reason"])
        with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection:
            evidence = " ".join(
                row[0]
                for row in connection.execute(
                    "SELECT evidence_json FROM workflow_events WHERE run_id=?",
                    (response["data"]["run_id"],),
                ).fetchall()
            )
        self.assertNotIn(secret_marker, evidence)

    def test_draft_mirror_failure_keeps_persisted_result_in_review_state(self):
        original_open = Path.open
        output_dir = self.root / "outputs" / "WI-MEDIA-1"
        output_dir.mkdir(parents=True)
        (output_dir / "draft-v1.md").write_text("stale file content", encoding="utf-8")

        def fail_draft_write(path, mode="r", *args, **kwargs):
            if path.name.startswith(".draft-v1.md.") and mode == "x":
                raise PermissionError("simulated file permission failure")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail_draft_write):
            response = execute_media_workflow(self.root, "WI-MEDIA-1", FakeProvider())
        self.assertEqual(0, response["code"])
        self.assertFalse(response["data"]["output_saved"])
        self.assertEqual("OUTPUT_WRITE_FAILED", response["data"]["output_error_code"])
        with closing(sqlite3.connect(self.root / "runtime.sqlite3")) as connection:
            run_state = connection.execute(
                "SELECT state FROM workflow_runs WHERE run_id=?",
                (response["data"]["run_id"],),
            ).fetchone()[0]
            review_state = connection.execute(
                "SELECT review_state FROM workflow_results WHERE workitem_id='WI-MEDIA-1'"
            ).fetchone()[0]
            mirror_event = connection.execute(
                "SELECT state, evidence_json FROM workflow_events "
                "WHERE run_id=? AND event_type='draft-mirror-failed'",
                (response["data"]["run_id"],),
            ).fetchone()
        self.assertEqual("NEEDS_REVIEW", run_state)
        self.assertEqual("NEEDS_REVIEW", review_state)
        self.assertEqual("NEEDS_REVIEW", mirror_event[0])
        self.assertEqual("OUTPUT_WRITE_FAILED", json.loads(mirror_event[1])["error_code"])

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
                return b'{"choices":[{"message":{"content":"{\\"status\\":\\"ok\\"}"}}],"usage":{"prompt_tokens":11,"completion_tokens":7,"total_tokens":18}}'

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
        self.assertEqual(
            {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            provider.last_usage,
        )


if __name__ == "__main__":
    unittest.main()
