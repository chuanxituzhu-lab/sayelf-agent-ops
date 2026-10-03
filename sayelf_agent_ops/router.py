from __future__ import annotations

from dataclasses import dataclass

from .models import RoutingDecision, WorkItem
from .registry import Registry


@dataclass(frozen=True)
class RouteRule:
    deliverable_type: str
    industry: str
    level: str
    role: str
    skills: tuple[str, ...]
    reason: str
    followup_industry: str | None = None
    followup_role: str | None = None


class Router:
    """Deterministic deliverable-first router for Sprint 01.

    It intentionally proves responsibility boundaries before introducing
    model-based routing.
    """

    def __init__(self, registry: Registry):
        self.registry = registry

    def route(self, workitem: WorkItem) -> RoutingDecision:
        text = " ".join([workitem.input, workitem.goal, workitem.deliverable]).lower()
        rule = self._classify_deliverable(text)

        excluded_roles = tuple(
            role.id
            for role in self.registry.roles.values()
            if role.industry == rule.industry and role.id != rule.role
        )

        for skill_id in rule.skills:
            if skill_id not in self.registry.skills:
                raise KeyError(f"UNKNOWN_SKILL:{skill_id}")
            if self.registry.skills[skill_id].owner_scope != rule.role:
                raise ValueError(f"SKILL_OWNER_MISMATCH:{skill_id}")

        return RoutingDecision(
            industry=rule.industry,
            deliverable_type=rule.deliverable_type,
            deliverable_level=rule.level,
            selected_role=rule.role,
            selected_skills=rule.skills,
            excluded_roles=excluded_roles,
            reason=rule.reason,
            confidence="high",
            followup_industry=rule.followup_industry,
            followup_role=rule.followup_role,
        )

    def _classify_deliverable(self, text: str) -> RouteRule:
        # Explicit cross-industry task:
        # first produce engineering professional facts, then Media can transform them.
        if (
            ("工程" in text or "boq" in text or "变更" in text)
            and ("公众号" in text or "文章" in text)
            and ("分析" in text or "费用" in text)
        ):
            return RouteRule(
                deliverable_type="cost-analysis",
                industry="engineering",
                level="X1",
                role="engineering.commercial",
                skills=("engineering.boq-feature-diff",),
                reason="先形成工程专业分析对象，再由 Media 子任务转化为文章；不创建跨行业超级 Agent。",
                followup_industry="media",
                followup_role="media.content-planner",
            )

        # Media: judge the requested deliverable, not domain words inside the topic.
        if "标题" in text and ("公众号" in text or "文章" in text or "小红书" in text):
            return RouteRule(
                "title-list", "media", "M1", "media.content-planner",
                ("media.title-writing",),
                "最终交付物是标题文本。",
            )

        if "配图" in text or "生成图片" in text or "文章图片" in text:
            return RouteRule(
                "visual-package", "media", "M2", "media.creative-producer",
                (
                    "media.visual-direction",
                    "media.article-image-generation",
                    "media.image-content-matching",
                ),
                "最终交付物是已有内容的视觉成果。",
            )

        if ("草稿" in text or "发布准备" in text) and ("公众号" in text or "微信" in text):
            return RouteRule(
                "platform-package", "media", "M3", "media.growth-operator",
                ("media.wechat-adaptation", "media.publishing-check"),
                "最终交付物是公众号平台就绪包。",
            )

        if (
            ("公众号" in text or "小红书" in text)
            and ("数据" in text or "表现" in text or "运营成本" in text or "复盘" in text)
        ):
            return RouteRule(
                "performance-review", "media", "M1", "media.growth-operator",
                ("media.performance-analysis",),
                "最终交付物是媒体运营复盘。",
            )

        if (
            ("公众号" in text or "小红书" in text)
            and ("文章" in text or "长文" in text or "写一篇" in text or "内容" in text)
        ):
            return RouteRule(
                "article", "media", "M1", "media.content-planner",
                ("media.content-structure", "media.longform-writing"),
                "最终交付物是媒体文章；工程、造价等词仅可作为主题或输入材料。",
            )

        if ("工地" in text or "施工现场" in text) and ("小红书" in text or "公众号" in text):
            return RouteRule(
                "article", "media", "M1", "media.content-planner",
                ("media.content-structure", "media.longform-writing"),
                "最终交付物是对外媒体内容，不是工程分析。",
            )

        # Engineering.
        if "boq" in text or (
            "清单" in text and ("对比" in text or "漏项" in text or "特征" in text)
        ):
            return RouteRule(
                "boq-diff", "engineering", "E1", "engineering.commercial",
                (
                    "engineering.boq-parse",
                    "engineering.boq-feature-diff",
                    "engineering.missing-item-detection",
                ),
                "最终交付物是 BOQ 专业差异结果。",
            )

        if ("施工图" in text or "图纸" in text) and (
            "差异" in text or "变化" in text or "版本" in text
        ):
            return RouteRule(
                "drawing-diff", "engineering", "E1", "engineering.technical",
                ("engineering.drawing-version-compare",),
                "最终交付物是图纸专业差异。",
            )

        if "工程量" in text and ("复核" in text or "检查" in text):
            return RouteRule(
                "quantity-review", "engineering", "E1", "engineering.commercial",
                ("engineering.quantity-review",),
                "最终交付物是工程量复核结果。",
            )

        if "试验报告" in text or ("试验" in text and "报告" in text):
            return RouteRule(
                "test-report-check", "engineering", "E1", "engineering.qa-records",
                ("engineering.test-report-check",),
                "最终交付物是质量资料检查结果。",
            )

        if "安全隐患" in text or ("安全" in text and "隐患" in text):
            return RouteRule(
                "hazard-record", "engineering", "E1", "engineering.hse",
                ("engineering.hazard-register",),
                "最终交付物是安全隐患记录。",
            )

        if (
            ("项目经理" in text or "汇报" in text)
            and ("boq" in text or "清单" in text or "工程" in text)
        ):
            return RouteRule(
                "professional-brief", "engineering", "E1", "engineering.commercial",
                ("engineering.boq-feature-diff",),
                "呈现方式是汇报，但责任对象仍是工程专业结论。",
            )

        raise ValueError("UNROUTABLE_DELIVERABLE")
