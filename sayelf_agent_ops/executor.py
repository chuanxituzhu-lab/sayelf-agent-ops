"""Executor —— 技能执行接口。

Sprint 02 只接入一条真实技能：media.title-writing（本地模板生成，不调用外部服务）。
其余技能返回明确标记 placeholder=True 的结构化占位产出，界面与审核会如实显示，
不会伪装成真实成果。后续接入 LLM 或外部工具时，只需新增 SkillHandler 并注册。
"""
from __future__ import annotations

import re
from typing import Any, Callable, Protocol

from .models import PlanStep, WorkItem

_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
DEFAULT_TITLE_COUNT = 5
MAX_TITLE_COUNT = 10


def requested_count(text: str, default: int = DEFAULT_TITLE_COUNT) -> int:
    m = re.search(r"(\d+)\s*个", text) or re.search(r"[×xX*]\s*(\d+)", text)
    if m:
        n = int(m.group(1))
    else:
        m = re.search(r"([一二两三四五六七八九十])\s*个", text)
        n = _CN_NUM[m.group(1)] if m else default
    return max(1, min(n, MAX_TITLE_COUNT))


def extract_topic(text: str) -> str:
    m = re.search(r"[“\"「『](.+?)[”\"」』]", text)
    if m:
        return m.group(1).strip()
    topic = re.sub(r"(给|为|帮我|请|生成|写|起|想|做)", "", text)
    topic = re.sub(r"\d+\s*个|[一二两三四五六七八九十]\s*个", "", topic)
    topic = re.sub(r"(公众号|小红书|文章)?(的)?(标题|题目)(\s*[×xX*]\s*\d+)?", "", topic)
    topic = topic.strip(" ，,。:：的")
    return topic or "这个主题"


_TITLE_TEMPLATES = (
    "{t}：一个人也能跑通的专业闭环",
    "别再堆工具了，{t}真正需要的是最少岗位",
    "我用{t}重新设计了自己的工作方式",
    "关于{t}，大多数人第一步就做错了",
    "{t}的三个真相：人做决定，AI 做接力",
    "从零到交付：我的{t}实践记录",
    "为什么说{t}的关键是可信交付",
    "{t}不是更多 AI，而是更少返工",
    "一张图看懂{t}的完整流程",
    "如果今天开始做{t}，我会这样起步",
)


def generate_titles(topic: str, n: int, round_no: int = 0) -> list[str]:
    start = (round_no * n) % len(_TITLE_TEMPLATES)
    picked = [_TITLE_TEMPLATES[(start + i) % len(_TITLE_TEMPLATES)] for i in range(n)]
    return [_space_mixed(tpl.format(t=topic)) for tpl in picked]


def _space_mixed(s: str) -> str:
    """中英文之间补一个空格，避免"Ops真正"这类粘连。"""
    s = re.sub(r"([A-Za-z0-9])([\u4e00-\u9fff])", r"\1 \2", s)
    return re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", s)


class SkillExecutionError(RuntimeError):
    """A skill could not run. ``code`` is safe to show and log (no inputs, keys or paths)."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Executor(Protocol):
    def run(self, step: PlanStep, workitem: WorkItem, feedback: list[str]) -> dict[str, Any]: ...


SkillHandler = Callable[[PlanStep, WorkItem, list[str]], dict[str, Any]]


def _title_writing(step: PlanStep, wi: WorkItem, feedback: list[str]) -> dict[str, Any]:
    n = requested_count(wi.input)
    topic = extract_topic(wi.input)
    items = generate_titles(topic, n, round_no=wi.rework_count)
    return {
        "type": "title-list",
        "skill": step.skill,
        "items": items,
        "placeholder": False,
        "evidence": {
            "method": "builtin-template",
            "topic": topic,
            "requested_count": n,
            "round": wi.rework_count,
            "feedback_applied": list(feedback),
        },
    }


class BuiltinExecutor:
    def __init__(self, handlers: dict[str, SkillHandler] | None = None, registry: Any | None = None,
                 fallback: SkillHandler | None = None):
        self.handlers: dict[str, SkillHandler] = {"media.title-writing": _title_writing}
        if handlers:
            self.handlers.update(handlers)
        self.registry = registry
        # Runs skills that have no dedicated handler (e.g. the generic model
        # executor). Without it they return honestly marked placeholders.
        self.fallback = fallback

    def _declared_type(self, step: PlanStep) -> str:
        # Placeholders must carry the output type the SkillContract declares,
        # otherwise the AcceptanceGate cannot match them to the contract.
        if self.registry is not None:
            skill = self.registry.skills.get(step.skill)
            if skill is not None and skill.produced_outputs:
                return skill.produced_outputs[0]
        return step.output

    def run(self, step: PlanStep, workitem: WorkItem, feedback: list[str]) -> dict[str, Any]:
        handler = self.handlers.get(step.skill)
        if handler is not None:
            return handler(step, workitem, feedback)
        if self.fallback is not None:
            return self.fallback(step, workitem, feedback)
        return {
            "type": self._declared_type(step),
            "skill": step.skill,
            "items": [],
            "placeholder": True,
            "note": "该技能尚未接入真实执行器，此为结构占位产出。",
            "evidence": {"method": "placeholder", "round": workitem.rework_count},
        }
