"""Short-video chain: media.content-structure (outline) → media.short-video-script.

The script step reads the outline produced by the previous step from
``workitem.outputs``; it never re-plans the content on its own.
"""
from __future__ import annotations

from typing import Any

from ..executor import SkillExecutionError
from ..models import PlanStep, WorkItem
from ._llm import (call_json, channel_of, clean_lines, context_text, evidence,
                   request_text, requested_seconds)

OUTLINE_PROMPT = (
    "你是自媒体内容策划岗位，负责内容结构。根据用户需求、材料、平台和返工意见，"
    "列出 3 到 8 个依次推进的内容要点；只用用户材料里的事实，不编造数据和案例。"
    '只返回 JSON 对象：{"outline": ["要点1", "要点2", "要点3"]}。'
)
SCRIPT_PROMPT = (
    "你是短视频脚本岗位。严格按给定大纲写竖屏短视频脚本：开头 3 秒内的钩子，"
    "3 到 12 个镜头，每个镜头写清画面、口播和字幕，各镜头时长之和不超过 duration_seconds。"
    "只用用户材料里的事实，不编造数据、人物和效果承诺。"
    '只返回 JSON 对象：{"hook": "…", "scenes": [{"seconds": 5, "shot": "画面", '
    '"voiceover": "口播", "caption": "字幕"}], "cta": "结尾引导"}。'
)


def make_outline_handler(provider: Any, *, remote: bool, consent: bool):
    def handler(step: PlanStep, wi: WorkItem, feedback: list[str]) -> dict[str, Any]:
        payload = {
            "request": request_text(wi),
            "context": context_text(wi),
            "channel": channel_of(wi),
            "rework_feedback": list(feedback),
        }
        response = call_json(provider, remote=remote, consent=consent, system=OUTLINE_PROMPT, payload=payload)
        outline = clean_lines(response.get("outline"))
        if not outline:
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        return {
            "type": "outline",
            "skill": step.skill,
            "items": outline,
            "placeholder": False,
            "evidence": evidence(provider, remote=remote, consent=consent, wi=wi, feedback=feedback),
        }

    return handler


def _scene(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SkillExecutionError("MODEL_RESPONSE_INVALID")
    seconds = value.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise SkillExecutionError("MODEL_RESPONSE_INVALID")
    scene = {"seconds": max(0, round(float(seconds), 1))}
    for key in ("shot", "voiceover", "caption"):
        text = value.get(key, "")
        if not isinstance(text, str):
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        scene[key] = " ".join(text.split())
    return scene


def render_script(hook: str, scenes: list[dict[str, Any]], cta: str) -> str:
    lines = ["# 短视频脚本", "", f"**开头钩子：** {hook}", "",
             "| # | 时长 | 画面 | 口播 | 字幕 |", "|---|---|---|---|---|"]
    for i, s in enumerate(scenes, 1):
        cells = [str(i), f"{s['seconds']:g}s", s["shot"], s["voiceover"], s["caption"]]
        lines.append("| " + " | ".join(c.replace("|", "／") for c in cells) + " |")
    lines += ["", f"**结尾引导：** {cta}" if cta else "", ""]
    return "\n".join(lines)


def make_video_script_handler(provider: Any, *, remote: bool, consent: bool):
    def handler(step: PlanStep, wi: WorkItem, feedback: list[str]) -> dict[str, Any]:
        outline = next((o.get("items") for o in wi.outputs
                        if isinstance(o, dict) and o.get("type") == "outline" and not o.get("placeholder")), None)
        if not outline:
            # The plan puts content-structure first; without its outline there is nothing to follow.
            raise SkillExecutionError("OUTLINE_MISSING")
        duration = requested_seconds(request_text(wi))
        payload = {
            "request": request_text(wi),
            "context": context_text(wi),
            "channel": channel_of(wi),
            "outline": outline,
            "duration_seconds": duration,
            "rework_feedback": list(feedback),
        }
        response = call_json(provider, remote=remote, consent=consent, system=SCRIPT_PROMPT, payload=payload)
        hook = response.get("hook")
        cta = response.get("cta", "")
        scenes_raw = response.get("scenes")
        if not isinstance(hook, str) or not isinstance(cta, str) or not isinstance(scenes_raw, list):
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        scenes = [_scene(s) for s in scenes_raw]
        hook, cta = " ".join(hook.split()), " ".join(cta.split())
        return {
            "type": "video-script",
            "skill": step.skill,
            "hook": hook,
            "scenes": scenes,
            "cta": cta,
            "duration_seconds": duration,
            "content": render_script(hook, scenes, cta),
            "placeholder": False,
            "evidence": evidence(provider, remote=remote, consent=consent, wi=wi, feedback=feedback,
                                 outline_items=len(outline)),
        }

    return handler


def make_model_handlers(provider: Any, *, remote: bool, consent: bool) -> dict[str, Any]:
    from .title_llm import make_llm_title_handler

    return {
        "media.title-writing": make_llm_title_handler(provider, remote=remote, consent=consent),
        "media.content-structure": make_outline_handler(provider, remote=remote, consent=consent),
        "media.short-video-script": make_video_script_handler(provider, remote=remote, consent=consent),
    }
