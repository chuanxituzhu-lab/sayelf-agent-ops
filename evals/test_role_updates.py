from __future__ import annotations

import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from sayelf_agent_ops import role_updates
from sayelf_agent_ops.models import WorkItem
from sayelf_agent_ops.registry import build_registry
from sayelf_agent_ops.role_updates import RoleUpdateStore
from sayelf_agent_ops.router import Router


class RoleUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.registry = build_registry()
        self.store = RoleUpdateStore(self.home / "role-updates.sqlite3")

    @staticmethod
    def software_proposal():
        return {
            "suggested_name": "软件交付工程师",
            "responsibility": "整合前端与后端实现职责，按交付目标完成软件代码变更。",
            "source_skill_ids": [
                "software.frontend-implementation",
                "software.backend-implementation",
            ],
            "aliases_by_skill": {
                "software.frontend-implementation": ["前端界面实现"],
                "software.backend-implementation": ["后端接口实现"],
            },
            "positive_examples_by_skill": {
                "software.frontend-implementation": [
                    "实现前端界面实现模块",
                    "修复前端界面实现问题",
                ],
                "software.backend-implementation": [
                    "实现后端接口实现模块",
                    "修复后端接口实现问题",
                ],
            },
            "negative_examples": ["写一篇公众号文章", "分析产品市场需求"],
        }

    def test_verified_bundle_routes_compound_work_to_one_minimum_role(self):
        result = self.store.reconcile(self.registry, **self.software_proposal())

        self.assertTrue(result["ok"], result)
        self.assertEqual(1, result["role_count_reduction_for_bundle"])
        request = "实现前端界面实现模块并实现后端接口实现模块"
        decision = Router(self.registry).route(WorkItem(id="WI-ROLE", input=request, deliverable=request))
        self.assertEqual(result["role_id"], decision.selected_role)
        self.assertEqual(2, len(decision.selected_skills))
        self.assertEqual({result["role_id"]}, {role for role, _ in decision.workflow_steps})

    def test_applied_bundle_survives_restart_and_can_be_revoked(self):
        result = self.store.reconcile(self.registry, **self.software_proposal())
        self.assertTrue(result["ok"], result)

        restarted_registry = build_registry()
        restarted_store = RoleUpdateStore(self.home / "role-updates.sqlite3")
        restarted_store.load_into(restarted_registry)
        self.assertIn(result["role_id"], restarted_registry.roles)

        revoked = restarted_store.revoke(restarted_registry, result["update_id"])
        self.assertEqual("revoked", revoked["status"])
        self.assertNotIn(result["role_id"], restarted_registry.roles)
        self.assertFalse(any(
            rule.id.startswith(f"user-role.{result['update_id']}.")
            for rule in restarted_registry.route_rules
        ))

    def test_producer_cannot_be_merged_with_independent_qa(self):
        proposal = self.software_proposal()
        proposal["suggested_name"] = "软件开发与验收岗"
        proposal["source_skill_ids"] = [
            "software.frontend-implementation", "software.test-and-review",
        ]
        proposal["aliases_by_skill"] = {
            "software.frontend-implementation": ["前端界面实现"],
            "software.test-and-review": ["软件独立验收测试"],
        }
        proposal["positive_examples_by_skill"] = {
            "software.frontend-implementation": [
                "实现前端界面实现模块", "修复前端界面实现问题",
            ],
            "software.test-and-review": [
                "完成软件独立验收测试报告", "执行软件独立验收测试流程",
            ],
        }

        result = self.store.reconcile(self.registry, **proposal)
        self.assertEqual("INDEPENDENT_REVIEW_MUST_REMAIN_SEPARATE", result["error"])
        self.assertFalse(any(role_id.startswith("custom.") for role_id in self.registry.roles))

    def test_cross_industry_and_non_reducing_bundles_are_rejected(self):
        cross_industry = self.software_proposal()
        cross_industry["source_skill_ids"] = [
            "software.frontend-implementation", "media.longform-writing",
        ]
        result = self.store.reconcile(self.registry, **cross_industry)
        self.assertEqual("CROSS_INDUSTRY_BUNDLE_NOT_ALLOWED", result["error"])

        same_role = self.software_proposal()
        same_role["source_skill_ids"] = ["media.content-structure", "media.title-writing"]
        same_role["aliases_by_skill"] = {
            "media.content-structure": ["媒体内容结构设计"],
            "media.title-writing": ["媒体标题创作"],
        }
        same_role["positive_examples_by_skill"] = {
            "media.content-structure": ["完成媒体内容结构设计方案", "调整媒体内容结构设计"],
            "media.title-writing": ["生成媒体标题创作清单", "优化媒体标题创作方案"],
        }
        result = self.store.reconcile(self.registry, **same_role)
        self.assertEqual("NO_ROLE_REDUCTION", result["error"])

    def test_alias_cannot_override_a_different_industry_route(self):
        proposal = self.software_proposal()
        proposal["aliases_by_skill"]["software.frontend-implementation"] = ["抖音视频脚本"]
        proposal["positive_examples_by_skill"]["software.frontend-implementation"] = [
            "实现抖音视频脚本模块", "修复抖音视频脚本问题",
        ]

        result = self.store.reconcile(self.registry, **proposal)
        self.assertEqual("POSITIVE_ROUTE_MISMATCH", result["error"])

    def test_storage_failure_rolls_back_the_in_memory_overlay(self):
        proposal = self.software_proposal()
        original_connection = role_updates._connection
        connection_count = 0

        @role_updates.contextmanager
        def unavailable_database(path):
            nonlocal connection_count
            connection_count += 1
            if connection_count > 1:
                raise sqlite3.OperationalError("database unavailable")
                yield  # pragma: no cover
            else:
                with original_connection(path) as db:
                    yield db

        with patch.object(role_updates, "_connection", unavailable_database):
            result = self.store.reconcile(self.registry, **proposal)

        self.assertEqual("ROLE_UPDATE_PERSISTENCE_FAILED", result["error"])
        self.assertFalse(any(role_id.startswith("custom.") for role_id in self.registry.roles))
        self.assertFalse(any(rule.id.startswith("user-role.") for rule in self.registry.route_rules))


if __name__ == "__main__":
    unittest.main()
