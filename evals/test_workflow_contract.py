import copy
import tempfile
import unittest
from pathlib import Path

from sayelf_agent_ops.service import AgentOpsService
from sayelf_agent_ops.workflow_contract import validate_host_evidence, validate_workflow_contract


class WorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.service = AgentOpsService(home=Path(self.temporary.name), packs=("software", "media"))

    def test_single_route_is_one_bounded_agent_as_tool(self):
        result = self.service.route("修复 Python 程序的文件解析功能")
        contract = result["workflow_contract"]
        self.assertEqual("agent-as-tool", contract["pattern"])
        self.assertEqual(["router", "agent-as-tool"], contract["pattern_chain"])
        self.assertEqual(1, contract["gate"]["minimum_roles"])
        self.assertTrue(result["workflow_validation"]["ok"])
        self.assertEqual("not_run", result["host_execution_evidence"]["status"])

    def test_compound_route_is_ordered_sequential_and_keeps_review_wall(self):
        result = self.service.route("实现 WebUI 界面并添加自动化回归测试")
        contract = result["workflow_contract"]
        self.assertEqual("sequential", contract["pattern"])
        self.assertEqual(2, len(contract["roles"]))
        self.assertEqual("software.qa", contract["roles"][-1]["role"])
        self.assertTrue(contract["review"]["independent_review"]["separate_from_producer"])
        self.assertEqual("planned", contract["state"]["status"])

    def test_contract_validator_rejects_unbounded_loop_and_self_review(self):
        result = self.service.route("写 5 个公众号标题")
        invalid = copy.deepcopy(result["workflow_contract"])
        invalid["loop"] = {"enabled": True, "max_iterations": 0, "exit_condition": ""}
        invalid["review"]["independent_review"]["separate_from_producer"] = False
        checked = validate_workflow_contract(invalid)
        self.assertFalse(checked["ok"])
        self.assertIn("LOOP_MAX_ITERATIONS_REQUIRED", checked["violations"])
        self.assertIn("REVIEWER_MUST_BE_INDEPENDENT", checked["violations"])

    def test_host_evidence_requires_real_checks_and_distinct_reviewer(self):
        result = self.service.route("修复 Python 程序的文件解析功能")
        evidence = copy.deepcopy(result["host_execution_evidence"]["template"])
        evidence.update({
            "status": "executed",
            "source_revision": "abc123",
            "route_digest": "sha256:route",
            "steps": [{"step": 1, "status": "executed"}],
            "changed_files": ["sayelf_agent_ops/parser.py"],
            "verification": ["python -m unittest discover -s evals -v"],
            "producer_self_check": {"status": "passed", "actor_id": "codex.producer"},
            "independent_review": {"status": "not_run", "actor_id": "codex.producer"},
            "limitations": [],
        })
        pending = validate_host_evidence(evidence)
        self.assertFalse(pending["ok"])
        self.assertEqual("review_pending", pending["status"])

        evidence["independent_review"] = {"status": "passed", "actor_id": "codex.reviewer"}
        verified = validate_host_evidence(evidence)
        self.assertTrue(verified["ok"])
        self.assertEqual("verified", verified["status"])

        evidence["status"] = "review_pending"
        inconsistent = validate_host_evidence(evidence)
        self.assertFalse(inconsistent["ok"])
        self.assertIn("STATUS_PENDING_CONTRADICTS_PASSED_REVIEW", inconsistent["violations"])

    def test_host_evidence_rejects_producer_as_reviewer(self):
        result = self.service.route("修复 Python 程序的文件解析功能")
        evidence = copy.deepcopy(result["host_execution_evidence"]["template"])
        evidence.update({
            "status": "executed",
            "source_revision": "abc123", "route_digest": "sha256:route",
            "steps": [{"step": 1, "status": "executed"}],
            "changed_files": ["parser.py"], "verification": ["unit"], "limitations": [],
            "producer_self_check": {"status": "passed", "actor_id": "same"},
            "independent_review": {"status": "passed", "actor_id": "same"},
        })
        checked = validate_host_evidence(evidence)
        self.assertFalse(checked["ok"])
        self.assertIn("REVIEWER_EQUALS_PRODUCER", checked["violations"])


if __name__ == "__main__":
    unittest.main()
