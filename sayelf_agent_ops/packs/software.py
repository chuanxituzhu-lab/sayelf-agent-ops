from __future__ import annotations

from ..models import RoleContract
from . import IndustryPack, RouteRule
from .helpers import skill


CHANGE_ACTIONS = ("实现", "开发", "修复", "修改", "优化", "重构", "构建", "添加", "创建", "搭建", "升级", "改造", "完善")
FRONTEND_ACTIONS = tuple(action for action in CHANGE_ACTIONS if action != "完善")
FRONTEND_TERMS = ("前端", "webui", "ui", "界面", "网页", "页面", "预览", "组件", "css", "react", "vue", "按钮", "交互", "响应式")
BACKEND_TERMS = ("后端", "服务端", "api", "接口", "数据库", "sql", "鉴权", "认证", "token", "服务逻辑")
SOFTWARE_CONTEXT = (
    "软件", "代码", "程序", "应用", "网站", "webui", "前端", "后端", "api", "接口",
    "数据库", "页面", "组件", "功能", "系统", "按钮", "react", "vue", "node", "python",
)


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_frontend_change(text: str) -> bool:
    if _is_platform_operation(text) and not _has_any(text, ("布局", "样式", "组件", "按钮", "响应式", "交互")):
        return False
    symptoms = ("按钮没反应", "页面空白", "布局错位", "样式异常", "显示异常", "交互失败")
    return _has_any(text, FRONTEND_TERMS) and (_has_any(text, FRONTEND_ACTIONS) or _has_any(text, symptoms))


def _is_backend_change(text: str) -> bool:
    symptoms = ("接口报错", "请求失败", "服务返回错误", "数据写入失败", "鉴权失败", "401", "500")
    return _has_any(text, BACKEND_TERMS) and (_has_any(text, CHANGE_ACTIONS) or _has_any(text, symptoms))


def _is_software_test(text: str) -> bool:
    test_intent = ("测试", "验证", "回归", "qa", "test", "质量检查", "测试覆盖率")
    return _has_any(text, test_intent) and _has_any(text, SOFTWARE_CONTEXT)


def _is_platform_operation(text: str) -> bool:
    operation_intent = (
        "部署", "上线", "运维", "启动服务", "服务不可用", "健康检查", "监控", "日志排查",
        "webui打不开", "启动失败", "服务器", "运行状态",
    )
    return _has_any(text, operation_intent) and _has_any(text, SOFTWARE_CONTEXT)


def build_pack() -> IndustryPack:
    roles = (
        RoleContract(
            id="software.engineer", industry="software",
            name="Software Engineer / 软件工程师",
            responsibility="负责通用功能开发、缺陷修复与重构，按验收条件实施最小代码变更。",
            owned_outputs=("code-change",),
            allowed_skills=("software.code-implementation",),
            forbidden_scope=("self-review", "publish-without-human-gate"),
        ),
        RoleContract(
            id="software.frontend",
            industry="software",
            name="Frontend Engineer / 前端工程师",
            responsibility="负责 Web 与桌面端界面、交互、响应式布局和可访问性实现。",
            owned_outputs=("frontend-change",),
            allowed_skills=("software.frontend-implementation",),
        ),
        RoleContract(
            id="software.backend",
            industry="software",
            name="Backend Engineer / 后端工程师",
            responsibility="负责 API、业务逻辑、认证和数据层变更。",
            owned_outputs=("backend-change",),
            allowed_skills=("software.backend-implementation",),
        ),
        RoleContract(
            id="software.qa",
            industry="software",
            name="QA Engineer / 测试工程师",
            responsibility="负责可重复的功能、回归与边界测试，并独立报告验收证据。",
            owned_outputs=("test-report",),
            allowed_skills=("software.test-and-review",),
            forbidden_scope=("approve-own-production-release",),
        ),
        RoleContract(
            id="software.platform-operations",
            industry="software",
            name="Platform Operations / 平台运维",
            responsibility="负责本机或服务器应用的启动诊断、健康检查、日志观察和部署方案；生产变更必须经人工授权。",
            owned_outputs=("runtime-diagnosis", "deployment-plan"),
            allowed_skills=("software.runtime-operations",),
            forbidden_scope=("deploy-without-human-authorization", "secret-egress", "delete-production-data"),
        ),
    )

    skills = (
        skill("software.code-implementation", "software.engineer", "软件实现与修复", ("requirements", "existing-code"), ("code-change",)),
        skill("software.frontend-implementation", "software.frontend", "前端实现", ("requirements", "existing-code", "design-reference"), ("frontend-change",)),
        skill("software.backend-implementation", "software.backend", "后端与 API 实现", ("requirements", "existing-code", "data-contract"), ("backend-change",)),
        skill("software.test-and-review", "software.qa", "软件测试与独立验收", ("requirements", "existing-code", "code-change", "frontend-change", "backend-change"), ("test-report",)),
        skill("software.runtime-operations", "software.platform-operations", "运行状态诊断与部署准备", ("application", "runtime-state", "deployment-config"), ("runtime-diagnosis", "deployment-plan")),
    )

    rules = (
        RouteRule(
            "software.code-change",
            lambda text: _has_any(text, CHANGE_ACTIONS) and _has_any(text, SOFTWARE_CONTEXT),
            30, "code-change", "software", "S2", "software.engineer",
            ("software.code-implementation",),
            "通用代码变更由软件工程师实施，宿主执行后必须提供真实验证与独立审核证据。",
            composition_predicate=lambda text: False,
        ),
        RouteRule(
            "software.platform-operations",
            _is_platform_operation,
            180,
            "runtime-diagnosis", "software", "S2", "software.platform-operations",
            ("software.runtime-operations",),
            "最终交付物是应用运行状态诊断或部署准备；生产环境操作仍需人工授权。",
        ),
        RouteRule(
            "software.test-and-review",
            _is_software_test,
            170,
            "test-report", "software", "S1", "software.qa",
            ("software.test-and-review",),
            "最终交付物是软件功能测试、回归检查或独立验收报告。",
            composition_predicate=lambda text: _has_any(text, ("测试", "验证", "回归", "qa", "test")),
        ),
        RouteRule(
            "software.backend-change",
            _is_backend_change,
            165,
            "backend-change", "software", "S2", "software.backend",
            ("software.backend-implementation",),
            "最终交付物是后端、API、认证或数据层代码变更。",
            composition_predicate=lambda text: _has_any(text, BACKEND_TERMS),
        ),
        RouteRule(
            "software.frontend-change",
            _is_frontend_change,
            165,
            "frontend-change", "software", "S2", "software.frontend",
            ("software.frontend-implementation",),
            "最终交付物是前端界面、交互或响应式布局变更。",
            composition_predicate=lambda text: _has_any(text, FRONTEND_TERMS),
        ),
    )
    return IndustryPack("software", "software", roles, skills, rules)
