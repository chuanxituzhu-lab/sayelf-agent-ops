from __future__ import annotations

from ..models import RoleContract
from . import IndustryPack, RouteRule
from .helpers import skill


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _software_work(text: str) -> bool:
    # Require both a software artifact/context and an action. This keeps
    # articles about software routed to media roles.
    strong_artifacts = ("代码", "代码库", "仓库", "webui", "前端", "后端", "api", "mcp", "bug", "缺陷", "npm", "单元测试", "测试用例")
    general_artifacts = ("软件", "程序", "应用", "功能开发")
    actions = (
        "开发", "新增", "添加", "实现", "修复", "调整", "修改", "优化", "重构", "排查", "审查",
        "测试", "构建", "创建", "做一个", "review", "implement", "debug",
    )
    is_media_content = _has_any(text, ("公众号文章", "公众号标题", "小红书笔记", "视频号脚本")) and _has_any(
        text, ("写一篇", "撰写", "生成", "创作", "写作")
    )
    if is_media_content and not _has_any(text, strong_artifacts):
        return False
    return (_has_any(text, strong_artifacts) or _has_any(text, general_artifacts)) and _has_any(text, actions)


def _qa_only(text: str) -> bool:
    qa_terms = ("测试", "回归", "单元", "用例", "质量", "test", "审查", "审阅", "review", "检查 diff", "代码审查")
    implementation_terms = ("开发", "新增", "添加", "实现", "修复", "调整", "修改", "优化", "重构", "构建", "创建", "做一个", "implement", "debug")
    return _has_any(text, qa_terms) and not _has_any(text, implementation_terms)


def _feature_workflow(text: str) -> tuple[tuple[str, str], ...]:
    """Use a design role only when the request signals cross-cutting scope."""
    complex_scope = (
        "架构", "系统设计", "技术方案", "跨模块", "多模块", "全链路", "平台级",
        "微服务", "整体重构", "整体方案", "完整系统", "技术选型",
    )
    steps = []
    if _has_any(text, complex_scope):
        steps.append(("software.architect", "software.architecture-design"))
    scope_kinds = sum((
        _has_any(text, ("bug", "缺陷", "故障", "错误", "异常", "修复")),
        _has_any(text, ("前端", "webui", "界面", "页面", "css", "浏览器")),
        _has_any(text, ("后端", "服务端", "api", "mcp", "接口", "数据库", "server")),
    ))
    implementation_skill = (
        "software.implementation" if scope_kinds > 1
        else "software.bug-fix" if _has_any(text, ("bug", "缺陷", "故障", "错误", "异常", "修复"))
        else "software.frontend-change" if _has_any(text, ("前端", "webui", "界面", "页面", "css", "浏览器"))
        else "software.backend-change" if _has_any(text, ("后端", "服务端", "api", "mcp", "接口", "数据库", "server"))
        else "software.implementation"
    )
    steps.append(("software.engineer", implementation_skill))
    steps.append(("software.qa", "software.test"))
    return tuple(steps)


def build_pack() -> IndustryPack:
    roles = (
        RoleContract(
            id="software.architect",
            industry="software",
            name="Software Architect / 软件方案设计",
            responsibility="把文字需求整理为边界清晰、可交付的软件设计和验收标准。",
            owned_outputs=("software-design",),
            allowed_skills=("software.architecture-design",),
        ),
        RoleContract(
            id="software.engineer",
            industry="software",
            name="Software Engineer / 软件开发",
            responsibility="将明确的软件需求转为最小、可验证、可回滚的代码变更。",
            owned_outputs=("software-change",),
            allowed_skills=("software.implementation", "software.bug-fix", "software.frontend-change", "software.backend-change", "software.refactor"),
            forbidden_scope=("publish-without-human-gate", "read-or-export-credentials"),
        ),
        RoleContract(
            id="software.qa",
            industry="software",
            name="Software QA / 软件测试与审查",
            responsibility="负责范围明确的软件测试、回归验证与独立审查。",
            owned_outputs=("software-test-report", "software-review"),
            allowed_skills=("software.test", "software.code-review"),
            forbidden_scope=("modify-production-code-without-assignment", "approve-own-work"),
        ),
    )

    skills = (
        skill("software.architecture-design", "software.architect", "需求澄清与技术设计", ("feature-request",), ("software-design",)),
        skill("software.implementation", "software.engineer", "按需求实现软件功能", ("feature-request", "software-design"), ("software-change",)),
        skill("software.bug-fix", "software.engineer", "软件缺陷修复", ("bug-report", "source-scope"), ("software-change",)),
        skill("software.frontend-change", "software.engineer", "前端与 WebUI 功能开发", ("feature-request", "source-scope"), ("software-change",)),
        skill("software.backend-change", "software.engineer", "后端、API 与 MCP 功能开发", ("feature-request", "source-scope"), ("software-change",)),
        skill("software.refactor", "software.engineer", "受约束的代码重构", ("refactor-scope", "acceptance-criteria"), ("software-change",)),
        skill("software.test", "software.qa", "软件测试与回归验证", ("source-scope", "acceptance-criteria", "software-change"), ("software-test-report",)),
        skill("software.code-review", "software.qa", "独立代码审查", ("diff", "acceptance-criteria"), ("software-review",)),
    )

    testing = ("测试", "回归", "单元", "用例", "质量", "test")
    review = ("审查", "审阅", "review", "检查 diff", "代码审查")
    front = ("前端", "webui", "界面", "页面", "css", "浏览器")
    back = ("后端", "服务端", "api", "mcp", "接口", "数据库", "server")
    bugfix = ("bug", "缺陷", "故障", "错误", "异常", "修复")
    rules = (
        RouteRule(
            "software.feature-workflow",
            lambda text: _software_work(text) and not _qa_only(text), 550,
            "software-feature-package", "software", "S1", "software.architect",
            ("software.architecture-design",),
            "软件功能需求按设计 → 实现 → QA 顺序生成各岗位成果。",
            workflow_steps=(
                ("software.architect", "software.architecture-design"),
                ("software.engineer", "software.implementation"),
                ("software.qa", "software.test"),
            ),
            workflow_selector=_feature_workflow,
        ),
        RouteRule("software.code-review", lambda text: _software_work(text) and _has_any(text, review), 500,
                  "software-review", "software", "S1", "software.qa", ("software.code-review",),
                  "交付物是独立软件代码审查结果。"),
        RouteRule("software.test", lambda text: _software_work(text) and _has_any(text, testing), 490,
                  "software-test-report", "software", "S1", "software.qa", ("software.test",),
                  "交付物是软件测试或回归验证结果。"),
        RouteRule("software.frontend", lambda text: _software_work(text) and _has_any(text, front), 480,
                  "software-change", "software", "S1", "software.engineer", ("software.frontend-change",),
                  "交付物是前端或 WebUI 代码变更。"),
        RouteRule("software.backend", lambda text: _software_work(text) and _has_any(text, back), 470,
                  "software-change", "software", "S1", "software.engineer", ("software.backend-change",),
                  "交付物是后端、API 或 MCP 代码变更。"),
        RouteRule("software.bug-fix", lambda text: _software_work(text) and _has_any(text, bugfix), 460,
                  "software-change", "software", "S1", "software.engineer", ("software.bug-fix",),
                  "交付物是软件缺陷修复。"),
        RouteRule("software.general-change", _software_work, 450,
                  "software-change", "software", "S1", "software.engineer", ("software.refactor",),
                  "交付物是软件代码或功能变更。"),
    )
    return IndustryPack("software", "software", roles, skills, rules)
