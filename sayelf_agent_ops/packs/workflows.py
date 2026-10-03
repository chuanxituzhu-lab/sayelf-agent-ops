from . import RouteRule


def cross_industry_rules() -> tuple[RouteRule, ...]:
    return (
        RouteRule(
            "workflow.engineering-analysis-to-media",
            lambda text: ("工程" in text or "boq" in text or "变更" in text)
            and ("公众号" in text or "文章" in text)
            and ("分析" in text or "费用" in text),
            300,
            "cost-analysis", "engineering", "X1", "engineering.commercial",
            ("engineering.boq-feature-diff",),
            "先形成工程专业分析对象，再由 Media 子任务转化为文章；不创建跨行业超级 Agent。",
            followup_industry="media",
            followup_role="media.content-planner",
        ),
    )
