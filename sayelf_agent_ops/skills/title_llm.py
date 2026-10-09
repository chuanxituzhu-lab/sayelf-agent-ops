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
from ._llm import call_json, channel_of, clean_lines, context_text, evidence, request_text

SYSTEM_PROMPT = (
    "你是自媒体标题策划岗位。只根据用户的需求、材料、平台和返工意见写标题；"
    "不编造数据、案例、人物或承诺效果。标题要具体、口语、不夸大，每个不超过 30 个字，互不重复。"
    '只返回 JSON 对象：{"titles": ["标题1", "标题2"]}，数量严格等于 count。'
)
MAX_TITLE_CHARS = 64


def make_llm_title_handler(provider: Any, *, remote: bool, consent: bool):
    def handler(step: PlanStep, wi: WorkItem, feedback: list[str]) -> dict[str, Any]:
        request = request_text(wi)
        count = requested_count(request)
        payload = {
            "topic": extract_topic(request),
            "request": request,
            "context": context_text(wi),
            "channel": channel_of(wi),
            "count": count,
            "rework_feedback": list(feedback),
        }
        response = call_json(provider, remote=remote, consent=consent, system=SYSTEM_PROMPT, payload=payload)
        titles = clean_lines(response.get("titles"))
        if not titles:
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        return {
            "type": "title-list",
            "skill": step.skill,
            "items": titles,
            "placeholder": False,
            "evidence": evidence(provider, remote=remote, consent=consent, wi=wi,
                                 feedback=feedback, requested_count=count),
        }

    return handler
