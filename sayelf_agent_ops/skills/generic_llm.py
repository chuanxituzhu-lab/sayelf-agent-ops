"""Generic model executor: any registered skill can run on a model.

Skills with a dedicated handler (titles, outline, short-video script) keep it.
Every other skill — BOQ diff, drawing compare, progress review … — gets a
draft written by the model from the skill's own contract: its purpose, the
owning role's responsibility, the request, earlier steps' outputs and rework
feedback. The output says plainly that it is a model draft, not a calculation
or a site check, so reviewers and approvers know what they are signing.
"""
from __future__ import annotations

import json
from typing import Any

from ..executor import SkillExecutionError
from ..models import PlanStep, WorkItem
from ._llm import call_json, clean_lines, context_text, evidence, request_text

MAX_PRIOR_CHARS = 8_000
SYSTEM_PROMPT = (
    "你是专业团队中的一个岗位，只完成分配给你的这一步。"
    "只依据用户需求、提供的材料和前序步骤的产出工作；材料里没有的数字、日期、规范条文、人名一律不编造，"
    "缺什么就写进 missing_inputs。结论要具体、可核对。"
    '只返回 JSON 对象：{"summary": "一段结论", "items": ["逐条结果"], '
    '"assumptions": ["做了哪些假设"], "missing_inputs": ["还缺哪些材料"]}。'
)
DRAFT_NOTE = "模型起草，未经计算或现场核实，需由人复核后使用。"


def _prior_outputs(wi: WorkItem) -> list[dict[str, Any]]:
    prior = [{k: v for k, v in out.items() if k in ("type", "content", "items", "role")}
             for out in wi.outputs if isinstance(out, dict)]
    kept: list[dict[str, Any]] = []
    for out in reversed(prior):  # the nearest earlier steps matter most
        if len(json.dumps(kept + [out], ensure_ascii=False)) > MAX_PRIOR_CHARS:
            break
        kept.insert(0, out)
    return kept


def make_generic_handler(provider: Any, registry: Any, *, remote: bool, consent: bool):
    def handler(step: PlanStep, wi: WorkItem, feedback: list[str]) -> dict[str, Any]:
        skill = registry.skills.get(step.skill)
        if skill is None:
            raise SkillExecutionError("UNREGISTERED_SKILL")
        role = registry.roles.get(step.role)
        output_type = skill.produced_outputs[0] if skill.produced_outputs else step.output
        payload = {
            "role": step.role,
            "role_responsibility": getattr(role, "responsibility", ""),
            "skill": skill.id,
            "skill_purpose": skill.purpose,
            "expected_output": output_type,
            "accepted_inputs": list(skill.accepted_inputs),
            "request": request_text(wi),
            "materials": context_text(wi),
            "earlier_steps": _prior_outputs(wi),
            "rework_feedback": list(feedback),
        }
        response = call_json(provider, remote=remote, consent=consent, system=SYSTEM_PROMPT, payload=payload)
        summary = response.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        items = clean_lines(response.get("items", []))
        assumptions = clean_lines(response.get("assumptions", []))
        missing = clean_lines(response.get("missing_inputs", []))
        return {
            "type": output_type,
            "skill": step.skill,
            "role": step.role,
            "content": summary.strip(),
            "items": items,
            "assumptions": assumptions,
            "missing_inputs": missing,
            "placeholder": False,
            "note": DRAFT_NOTE,
            "evidence": evidence(provider, remote=remote, consent=consent, wi=wi, feedback=feedback,
                                 draft=True, generic=True),
        }

    return handler
