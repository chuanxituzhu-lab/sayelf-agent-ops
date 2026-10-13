"""Shared plumbing for model-backed skills: consent, safe errors, evidence."""
from __future__ import annotations

import re
from typing import Any

from ..executor import SkillExecutionError
from ..models import WorkItem

MAX_CONTEXT_CHARS = 12_000
PLATFORMS = ("公众号", "小红书", "视频号", "抖音", "快手", "B站", "YouTube", "TikTok")


def request_text(wi: WorkItem) -> str:
    """The person's own request (goal), falling back to the routing input."""
    return (wi.goal or wi.input or "").strip()


def channel_of(wi: WorkItem) -> str:
    text = f"{wi.input}\n{wi.goal}".lower()
    for name in PLATFORMS:
        if name.lower() in text:
            return name
    return "通用"


def context_text(wi: WorkItem) -> str:
    """Request plus bounded extracted attachment text, only after consent."""
    return materials_text(wi, MAX_CONTEXT_CHARS)


def materials_text(wi: WorkItem, limit: int = 40_000) -> str:
    """Keep material useful to an executor without logging or returning it."""
    parts = [wi.input or ""]
    for attachment in getattr(wi, "attachments", []) or []:
        name = str(attachment.get("name", "附件"))
        text = attachment.get("text")
        if text:
            parts.append(f"\n\n===== 附件《{name}》 =====\n{text}")
        else:
            parts.append(f"\n\n===== 附件《{name}》（未提取文字） =====")
    result = "".join(parts)
    return result if len(result) <= limit else result[:limit] + "\n（材料过长，已截断）"


def call_json(provider: Any, *, remote: bool, consent: bool, system: str, payload: dict) -> dict:
    if remote and not consent:
        # Checked before any network call: nothing leaves the device without consent.
        raise SkillExecutionError("MODEL_CONSENT_REQUIRED")
    try:
        response = provider.complete_json(system, payload)
    except Exception as error:  # provider errors carry safe codes only
        raise SkillExecutionError(getattr(error, "code", "MODEL_CALL_FAILED")) from None
    if not isinstance(response, dict):
        raise SkillExecutionError("MODEL_RESPONSE_INVALID")
    return response


def evidence(provider: Any, *, remote: bool, consent: bool, wi: WorkItem, feedback: list[str], **extra) -> dict:
    return {
        "method": "llm",
        "adapter": getattr(provider, "adapter_id", "custom"),
        "model": getattr(provider, "model", None),
        "usage": getattr(provider, "last_usage", None),
        "remote": bool(remote),
        "consent": bool(consent),
        "round": wi.rework_count,
        "feedback_applied": list(feedback),
        **extra,
    }


def clean_lines(values: Any) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise SkillExecutionError("MODEL_RESPONSE_INVALID")
    out: list[str] = []
    for value in values:
        value = " ".join(value.split())
        if value and value not in out:
            out.append(value)
    return out


def requested_seconds(text: str, default: int = 60) -> int:
    m = re.search(r"(\d+)\s*(秒|s\b|sec)", text, re.IGNORECASE)
    if m:
        return max(5, min(int(m.group(1)), 600))
    m = re.search(r"(\d+)\s*分钟", text)
    if m:
        return max(5, min(int(m.group(1)) * 60, 600))
    return default
