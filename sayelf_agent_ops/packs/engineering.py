from __future__ import annotations

from ..models import RoleContract
from . import IndustryPack, RouteRule
from .helpers import skill


def build_pack() -> IndustryPack:
    roles = (
        RoleContract(
            id="engineering.commercial",
            industry="engineering",
            name="Commercial / 商务造价",
            responsibility="负责 BOQ、工程量、价格、变更与费用影响。",
            owned_outputs=("boq-diff", "quantity-review", "cost-impact", "professional-brief"),
            allowed_skills=(
                "engineering.boq-parse",
                "engineering.boq-feature-diff",
                "engineering.missing-item-detection",
                "engineering.quantity-review",
            ),
        ),
        RoleContract(
            id="engineering.technical",
            industry="engineering",
            name="Technical / 技术负责人",
            responsibility="负责图纸、技术变化与技术判断。",
            owned_outputs=("drawing-diff", "change-object"),
            allowed_skills=("engineering.drawing-version-compare",),
        ),
        RoleContract(
            id="engineering.production",
            industry="engineering",
            name="Site Engineer / 施工员",
            responsibility="负责计划、现场生产与进度。",
            owned_outputs=("progress-review", "site-event"),
            allowed_skills=("engineering.progress-tracking",),
        ),
        RoleContract(
            id="engineering.document-control",
            industry="engineering",
            name="Document Control / 资料员",
            responsibility="负责施工资料收集、分类、报验资料整理与证据包归档；不代替专业岗位作技术或质量结论。",
            owned_outputs=("evidence-package",),
            allowed_skills=("engineering.evidence-package",),
            forbidden_scope=("engineering-approval", "quality-acceptance"),
        ),
        RoleContract(
            id="engineering.qa-records",
            industry="engineering",
            name="Testing / QA / 试验员/质量员",
            responsibility="兼任试验与质量资料岗位，负责试验报告检查和质量记录完整性；不替代技术负责人审批。",
            owned_outputs=("test-report-check",),
            allowed_skills=("engineering.test-report-check",),
        ),
        RoleContract(
            id="engineering.hse",
            industry="engineering",
            name="HSE / 安全管理",
            responsibility="负责安全检查、隐患与整改记录。",
            owned_outputs=("hazard-record",),
            allowed_skills=("engineering.hazard-register",),
        ),
    )

    skills = (
        skill("engineering.boq-parse", "engineering.commercial", "解析 BOQ", ("boq",), ("boq-structure",)),
        skill("engineering.boq-feature-diff", "engineering.commercial", "清单特征差异", ("boq-a", "boq-b"), ("boq-diff",)),
        skill("engineering.missing-item-detection", "engineering.commercial", "漏项识别", ("boq-a", "boq-b"), ("missing-items",)),
        skill("engineering.quantity-review", "engineering.commercial", "工程量复核", ("quantity-data",), ("quantity-review",)),
        skill("engineering.drawing-version-compare", "engineering.technical", "图纸版本比对", ("drawing-a", "drawing-b"), ("drawing-diff",)),
        skill("engineering.progress-tracking", "engineering.production", "进度跟踪", ("site-data",), ("progress-review",)),
        skill("engineering.evidence-package", "engineering.document-control", "资料整理与证据包归档", ("project-documents", "site-records"), ("evidence-package",)),
        skill("engineering.test-report-check", "engineering.qa-records", "试验报告检查", ("test-report",), ("test-report-check",)),
        skill("engineering.hazard-register", "engineering.hse", "安全隐患整理", ("site-observation",), ("hazard-record",)),
    )

    rules = (
        RouteRule(
            "engineering.boq-diff",
            lambda text: "boq" in text or (
                "清单" in text and any(term in text for term in ("对比", "漏项", "特征"))
            ),
            100,
            "boq-diff", "engineering", "E1", "engineering.commercial",
            ("engineering.boq-parse", "engineering.boq-feature-diff", "engineering.missing-item-detection"),
            "最终交付物是 BOQ 专业差异结果。",
        ),
        RouteRule(
            "engineering.drawing-diff",
            lambda text: any(term in text for term in ("施工图", "图纸"))
            and any(term in text for term in ("差异", "变化", "版本")),
            90,
            "drawing-diff", "engineering", "E1", "engineering.technical",
            ("engineering.drawing-version-compare",), "最终交付物是图纸专业差异。",
        ),
        RouteRule(
            "engineering.quantity-review",
            lambda text: "工程量" in text and any(term in text for term in ("复核", "检查")),
            80,
            "quantity-review", "engineering", "E1", "engineering.commercial",
            ("engineering.quantity-review",), "最终交付物是工程量复核结果。",
        ),
        RouteRule(
            "engineering.progress-review",
            lambda text: "形象进度" in text or ("进度" in text and "进度款" not in text and any(
                term in text for term in ("跟踪", "滞后", "偏差", "核对", "检查", "复盘", "周报", "月报", "计划")
            )),
            75,
            "progress-review", "engineering", "E1", "engineering.production",
            ("engineering.progress-tracking",), "最终交付物是生产进度核查结果。",
        ),
        RouteRule(
            "engineering.evidence-package",
            lambda text: any(term in text for term in ("资料员", "资料归档", "竣工资料", "报验资料", "资料整理", "资料组卷", "证据包", "档案整理")),
            72,
            "evidence-package", "engineering", "E1", "engineering.document-control",
            ("engineering.evidence-package",), "最终交付物是施工资料整理或证据包归档。",
        ),
        RouteRule(
            "engineering.test-report-check",
            lambda text: "试验报告" in text or ("试验" in text and "报告" in text),
            70,
            "test-report-check", "engineering", "E1", "engineering.qa-records",
            ("engineering.test-report-check",), "最终交付物是质量资料检查结果。",
        ),
        RouteRule(
            "engineering.hazard-record",
            lambda text: "安全隐患" in text or ("安全" in text and "隐患" in text),
            60,
            "hazard-record", "engineering", "E1", "engineering.hse",
            ("engineering.hazard-register",), "最终交付物是安全隐患记录。",
        ),
        RouteRule(
            "engineering.professional-brief",
            lambda text: any(term in text for term in ("项目经理", "汇报"))
            and any(term in text for term in ("boq", "清单", "工程")),
            50,
            "professional-brief", "engineering", "E1", "engineering.commercial",
            ("engineering.boq-feature-diff",), "呈现方式是汇报，但责任对象仍是工程专业结论。",
        ),
    )
    return IndustryPack("engineering", "engineering", roles, skills, rules)
