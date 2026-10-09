from __future__ import annotations

from ..models import RoleContract
from . import IndustryPack, RouteRule
from .helpers import skill


def build_pack() -> IndustryPack:
    roles = (
        RoleContract(
            id="media.content-planner",
            industry="media",
            name="Content Planner / 内容策划",
            responsibility="将主题、事实和输入材料转化为内容成果。",
            owned_outputs=("title-list", "outline", "article", "script", "image-brief"),
            allowed_skills=(
                "media.research",
                "media.source-verification",
                "media.content-structure",
                "media.title-writing",
                "media.longform-writing",
                "media.short-video-script",
            ),
            forbidden_scope=("actual-image-generation", "platform-publishing", "account-operation"),
        ),
        RoleContract(
            id="media.creative-producer",
            industry="media",
            name="Creative Producer / 内容制作",
            responsibility="将已确认内容转化为视觉与多媒体成果。",
            owned_outputs=("cover", "article-image", "visual-package"),
            allowed_skills=(
                "media.visual-direction",
                "media.article-image-generation",
                "media.image-content-matching",
            ),
            forbidden_scope=("redefine-core-article-view", "platform-publishing"),
        ),
        RoleContract(
            id="media.growth-operator",
            industry="media",
            name="Growth Operator / 运营增长",
            responsibility="负责平台适配、发布准备与表现复盘。",
            owned_outputs=("platform-package", "publishing-check", "performance-review"),
            allowed_skills=(
                "media.wechat-adaptation",
                "media.publishing-check",
                "media.performance-analysis",
            ),
            forbidden_scope=("rewrite-professional-source-facts", "publish-without-human-gate"),
        ),
    )

    skills = (
        skill("media.research", "media.content-planner", "内容研究", ("topic",), ("research-notes",)),
        skill("media.source-verification", "media.content-planner", "来源核验", ("claims",), ("verified-sources",)),
        skill("media.content-structure", "media.content-planner", "内容结构", ("topic",), ("outline",)),
        skill("media.title-writing", "media.content-planner", "标题生成", ("topic", "article"), ("title-list",)),
        skill("media.longform-writing", "media.content-planner", "长文写作", ("outline", "topic"), ("article",)),
        skill("media.short-video-script", "media.content-planner", "短视频脚本结构", ("topic", "source-material"), ("video-script",)),
        skill("media.visual-direction", "media.creative-producer", "视觉方向", ("article",), ("visual-direction",)),
        skill("media.article-image-generation", "media.creative-producer", "文章配图", ("article", "visual-direction"), ("article-image",)),
        skill("media.image-content-matching", "media.creative-producer", "图文匹配", ("article", "article-image"), ("visual-package",)),
        skill("media.wechat-adaptation", "media.growth-operator", "公众号适配", ("article", "visual-package"), ("platform-package",)),
        skill("media.publishing-check", "media.growth-operator", "发布前检查", ("platform-package",), ("publishing-check",)),
        skill("media.performance-analysis", "media.growth-operator", "公众号表现分析", ("metrics",), ("performance-review",)),
    )

    social_platforms = ("小红书", "公众号", "微信公众号", "视频号", "抖音", "抖音号", "通用媒体内容")
    video_platforms = ("视频号", "抖音", "抖音号", "短视频")

    rules = (
        RouteRule(
            "media.short-video-script",
            lambda text: any(platform in text for platform in video_platforms)
            and any(term in text for term in ("脚本", "口播", "分镜", "短视频", "视频内容")),
            210,
            "video-script", "media", "M1", "media.content-planner",
            ("media.content-structure", "media.short-video-script"),
            "最终交付物是视频号或抖音短视频脚本。",
        ),
        RouteRule(
            "media.title-list",
            lambda text: "标题" in text and any(platform in text for platform in social_platforms + ("文章",)),
            200,
            "title-list", "media", "M1", "media.content-planner",
            ("media.title-writing",), "最终交付物是标题文本。",
        ),
        RouteRule(
            "media.visual-package",
            lambda text: any(term in text for term in ("配图", "生成图片", "文章图片")),
            190,
            "visual-package", "media", "M2", "media.creative-producer",
            ("media.visual-direction", "media.article-image-generation", "media.image-content-matching"),
            "最终交付物是已有内容的视觉成果。",
            composition_predicate=lambda text: any(term in text for term in ("生成配图", "制作配图", "生成图片", "制作图片", "设计封面", "生成封面")),
        ),
        RouteRule(
            "media.platform-package",
            lambda text: any(term in text for term in ("草稿", "发布准备"))
            and any(term in text for term in ("公众号", "微信")),
            180,
            "platform-package", "media", "M3", "media.growth-operator",
            ("media.wechat-adaptation", "media.publishing-check"), "最终交付物是公众号平台就绪包。",
        ),
        RouteRule(
            "media.performance-review",
            lambda text: any(platform in text for platform in ("公众号", "小红书"))
            and any(term in text for term in ("数据", "表现", "运营成本", "复盘")),
            170,
            "performance-review", "media", "M1", "media.growth-operator",
            ("media.performance-analysis",), "最终交付物是媒体运营复盘。",
        ),
        RouteRule(
            "media.article",
            lambda text: any(platform in text for platform in social_platforms)
            and (
                any(term in text for term in ("文章", "长文", "笔记", "写一篇", "图文内容"))
                or ("内容" in text and any(platform in text for platform in ("公众号", "微信公众号", "小红书")))
            ),
            160,
            "article", "media", "M1", "media.content-planner",
            ("media.content-structure", "media.longform-writing"),
            "最终交付物是媒体文章；工程、造价等词仅可作为主题或输入材料。",
            composition_predicate=lambda text: any(term in text for term in ("写", "撰写", "创作", "生成文章", "写一篇")),
        ),
        RouteRule(
            "media.site-content",
            lambda text: any(term in text for term in ("工地", "施工现场"))
            and any(platform in text for platform in ("小红书", "公众号")),
            150,
            "article", "media", "M1", "media.content-planner",
            ("media.content-structure", "media.longform-writing"),
            "最终交付物是对外媒体内容，不是工程分析。",
        ),
        RouteRule(
            "media.platform-content",
            lambda text: any(platform in text for platform in social_platforms)
            and any(term in text for term in ("内容", "文案", "策划", "选题", "运营", "做一条", "做一期")),
            100,
            "platform-content", "media", "M1", "media.content-planner",
            ("media.content-structure",),
            "最终交付物是所选自媒体平台的内容方案。",
        ),
        RouteRule(
            "media.platform-default",
            lambda text: any(platform in text for platform in social_platforms),
            10,
            "platform-content", "media", "M1", "media.content-planner",
            ("media.content-structure",),
            "需求已指定自媒体平台；先由内容策划角色形成可审核的工作方案。",
        ),
    )
    return IndustryPack("media", "media", roles, skills, rules)
