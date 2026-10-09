import unittest

from sayelf_agent_ops.models import WorkItem
from sayelf_agent_ops.registry import build_default_registry
from sayelf_agent_ops.router import Router


class RoutingEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = build_default_registry()
        cls.router = Router(cls.registry)

    def route(self, text: str):
        wi = WorkItem(
            id="T",
            input=text,
            goal=text,
            deliverable=text,
        )
        return self.router.route(wi)

    def assert_role(self, text: str, role: str):
        decision = self.route(text)
        self.assertEqual(role, decision.selected_role)
        return decision

    # R01-R10 normal cases
    def test_r01_wechat_titles(self):
        d = self.assert_role("写 5 个公众号标题", "media.content-planner")
        self.assertEqual(("media.title-writing",), d.selected_skills)

    def test_r02_wechat_article(self):
        d = self.assert_role("写一篇完整公众号文章", "media.content-planner")
        self.assertEqual(
            ("media.content-structure", "media.longform-writing"),
            d.selected_skills,
        )

    def test_wechat_generic_content_keeps_article_route(self):
        d = self.assert_role("公众号内容", "media.content-planner")
        self.assertEqual("article", d.deliverable_type)

    def test_r03_existing_article_images(self):
        self.assert_role("给已有文章生成 6 张配图", "media.creative-producer")

    def test_r04_wechat_draft(self):
        self.assert_role("把现有文章和图片整理成公众号草稿", "media.growth-operator")

    def test_r05_wechat_performance(self):
        self.assert_role("分析公众号数据表现并复盘", "media.growth-operator")

    def test_social_channels_route_titles(self):
        for channel in ("小红书", "公众号", "视频号", "抖音"):
            with self.subTest(channel=channel):
                decision = self.assert_role(f"为{channel}写5个标题", "media.content-planner")
                self.assertEqual("title-list", decision.deliverable_type)

    def test_short_video_channels_route_scripts(self):
        for channel in ("视频号", "抖音"):
            with self.subTest(channel=channel):
                decision = self.assert_role(f"为{channel}写一个口播脚本", "media.content-planner")
                self.assertEqual("video-script", decision.deliverable_type)
                self.assertIn("media.short-video-script", decision.selected_skills)

    def test_r06_boq_compare(self):
        self.assert_role("对比两版 BOQ 的清单特征变化和漏项", "engineering.commercial")

    def test_r07_drawing_diff(self):
        self.assert_role("比较两版施工图的版本变化", "engineering.technical")

    def test_r08_quantity_review(self):
        self.assert_role("工程量复核", "engineering.commercial")

    def test_r09_test_report(self):
        self.assert_role("检查这一批混凝土试验报告", "engineering.qa-records")

    def test_r10_hazard(self):
        self.assert_role("整理施工现场安全隐患记录", "engineering.hse")

    def test_software_bug_fix_routes_to_engineer(self):
        d = self.assert_role("修复 Draftloom 软件代码：微信 access_token 返回 40164 时展示原始公网 IP", "software.engineer")
        self.assertEqual(("software.bug-fix", "software.test"), d.selected_skills)
        self.assertEqual("software", d.industry)
        self.assertEqual(("software.engineer", "software.qa"), tuple(role for role, _ in d.workflow_steps))
        self.assertEqual(2, len(set(role for role, _ in d.workflow_steps)))

    def test_software_frontend_routes_to_frontend_skill(self):
        d = self.assert_role("给软件 WebUI 新增封面预览功能", "software.engineer")
        self.assertEqual(("software.frontend-change", "software.test"), d.selected_skills)

    def test_cross_cutting_software_request_keeps_architect_role(self):
        d = self.assert_role("为软件平台制定跨模块架构和技术选型，并实现与测试", "software.architect")
        self.assertEqual(("software.architecture-design", "software.implementation", "software.test"), d.selected_skills)
        self.assertEqual(3, len(set(role for role, _ in d.workflow_steps)))

    def test_compound_software_scope_uses_one_implementer_and_independent_qa(self):
        d = self.assert_role("同时调整软件前端页面和后端 API", "software.engineer")
        self.assertEqual(("software.implementation", "software.test"), d.selected_skills)
        self.assertEqual(2, len(set(role for role, _ in d.workflow_steps)))

    def test_compound_media_request_adds_only_required_roles_and_orders_dependencies(self):
        d = self.assert_role("为小红书写一篇新品体验笔记并生成配图方案", "media.content-planner")
        self.assertEqual(
            ("visual-package", "article"), d.requested_deliverables,
        )
        self.assertEqual(2, len(set(role for role, _ in d.workflow_steps)))
        self.assertLess(d.selected_skills.index("media.longform-writing"), d.selected_skills.index("media.visual-direction"))
        self.assertLess(d.selected_skills.index("media.visual-direction"), d.selected_skills.index("media.article-image-generation"))

    def test_compound_engineering_request_selects_minimum_roles_for_both_outputs(self):
        d = self.assert_role("对比两版 BOQ 并比较两版施工图版本差异", "engineering.commercial")
        self.assertEqual(("boq-diff", "drawing-diff"), d.requested_deliverables)
        self.assertEqual(2, len(set(role for role, _ in d.workflow_steps)))

    def test_software_tests_route_to_qa(self):
        d = self.assert_role("为软件代码补充回归测试用例", "software.qa")
        self.assertEqual(("software.test",), d.selected_skills)

    def test_software_review_routes_to_qa(self):
        d = self.assert_role("审查软件仓库中的代码 diff", "software.qa")
        self.assertEqual(("software.code-review",), d.selected_skills)

    def test_article_about_software_stays_in_media(self):
        self.assert_role("写一篇关于软件开发的公众号文章", "media.content-planner")

    # X01-X05 confusion cases
    def test_x01_engineering_topic_wechat_article(self):
        self.assert_role(
            "写一篇“工程造价为什么越来越贵”的公众号文章",
            "media.content-planner",
        )

    def test_x02_boq_manager_brief_stays_engineering(self):
        self.assert_role(
            "把 BOQ 差异结果制作成项目经理汇报",
            "engineering.commercial",
        )

    def test_x03_site_photo_to_xiaohongshu_is_media(self):
        self.assert_role(
            "把施工现场照片做成小红书内容",
            "media.content-planner",
        )

    def test_x04_media_operating_cost_is_media(self):
        self.assert_role(
            "统计公众号运营成本并分析表现",
            "media.growth-operator",
        )

    def test_x05_cross_industry_is_split_not_super_agent(self):
        d = self.assert_role(
            "分析工程变更费用，然后写成公众号文章",
            "engineering.commercial",
        )
        self.assertEqual("media", d.followup_industry)
        self.assertEqual("media.content-planner", d.followup_role)


if __name__ == "__main__":
    unittest.main()
