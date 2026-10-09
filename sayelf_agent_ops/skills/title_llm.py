"""media.title-writing backed by a chat model.

Provider-neutral: any object with ``complete_json(system_prompt, payload) -> dict``
works (the desktop ``OpenAICompatibleProvider`` is one). The handler never sees
or records API keys. A remote endpoint is only called after explicit per-run
consent, checked before any network call.
"""
from __future__ import annotations

from typing import Any

from ..executor import SkillExecutionError, extract_topic, requested_count
from ..models import PlanStep, WorkItem

SYSTEM_PROMPT = (
    "你是自媒体标题策划岗位。只根据用户给出的主题、平台和返工意见写标题；"
    "不编造数据、案例、人物或承诺效果。标题要具体、口语、不夸大，每个不超过 30 个字，互不重复。"
    '只返回 JSON 对象：{"titles": ["标题1", "标题2"]}，数量严格等于 count。'
)
MAX_TITLE_CHARS = 64


def _channel(text: str) -> str:
    for name in ("公众号", "小红书", "视频号", "抖音", "B站", "YouTube"):
        if name.lower() in text.lower():
            return name
    return "通用"


def make_llm_title_handler(provider: Any, *, remote: bool, consent: bool):
    def handler(step: PlanStep, wi: WorkItem, feedback: list[str]) -> dict[str, Any]:
        if remote and not consent:
            raise SkillExecutionError("MODEL_CONSENT_REQUIRED")
        count = requested_count(wi.input)
        payload = {
            "topic": extract_topic(wi.input),
            "channel": _channel(wi.input),
            "count": count,
            "rework_feedback": list(feedback),
        }
        try:
            response = provider.complete_json(SYSTEM_PROMPT, payload)
        except Exception as error:  # provider errors carry safe codes only
            raise SkillExecutionError(getattr(error, "code", "MODEL_CALL_FAILED")) from None
        titles = response.get("titles") if isinstance(response, dict) else None
        if not isinstance(titles, list) or not all(isinstance(t, str) for t in titles):
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        cleaned: list[str] = []
        for title in titles:
            title = " ".join(title.split())
            if title and title not in cleaned:
                cleaned.append(title)
        if not cleaned:
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        return {
            "type": "title-list",
            "skill": step.skill,
            "items": cleaned,
            "placeholder": False,
            "evidence": {
                "method": "llm",
                "adapter": getattr(provider, "adapter_id", "custom"),
                "model": getattr(provider, "model", None),
                "usage": getattr(provider, "last_usage", None),
                "remote": bool(remote),
                "consent": bool(consent),
                "requested_count": count,
                "round": wi.rework_count,
                "feedback_applied": list(feedback),
            },
        }

    return handler
