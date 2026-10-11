import tempfile
import unittest
from pathlib import Path
from sayelf_agent_ops.service import AgentOpsService

class SoftwareHostRoutingTests(unittest.TestCase):
    def test_host_plan_is_not_execution(self):
        with tempfile.TemporaryDirectory() as home:
            svc = AgentOpsService(home=Path(home), packs=('software',))
            result = svc.route('修复 Python 程序的文件解析功能')
            self.assertTrue(result['ok'])
            self.assertEqual('software.engineer', result['decision']['selected_role'])
            contract = result['host_execution']
            self.assertEqual('planned', contract['status'])
            self.assertEqual('code-change', contract['steps'][0]['output'])
            self.assertIsNone(contract['execute_tool'])
            self.assertIn('independent_review', contract['required_evidence'])
            self.assertFalse(svc.runtime.items)

    def test_specialists_remain_available(self):
        with tempfile.TemporaryDirectory() as home:
            svc = AgentOpsService(home=Path(home), packs=('software',))
            for text, role in [('修复前端按钮功能', 'software.frontend'), ('实现后端 API 功能', 'software.backend'), ('验证软件回归测试', 'software.qa')]:
                self.assertEqual(role, svc.route(text)['decision']['selected_role'])
