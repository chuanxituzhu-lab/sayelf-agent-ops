"""Structured, provider-neutral handlers for the local software workflow."""
from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Any

from ..executor import SkillExecutionError
from ..models import PlanStep, WorkItem
from ._llm import call_json, context_text, evidence, request_text, clean_lines

DESIGN_PROMPT = (
    "你是软件方案设计岗位。只根据用户需求制定最小可交付设计；区分已知事实与假设，"
    "不得声称已查看仓库或运行代码。列出目标、假设、验收标准和预计文件。"
    '仅返回 JSON：{"summary":"...","assumptions":["..."],"acceptance_criteria":["..."],'
    '"files":[{"path":"相对路径","purpose":"..."}]}。'
)
IMPLEMENT_PROMPT = (
    "你是软件开发岗位。按给定设计（如本次工作流包含设计步骤）或用户明确范围生成可供审阅的文件内容；"
    "范围不清时记录假设，不要声称已写入项目、运行或部署。"
    "输出尽量精简、可独立理解；文件路径必须是安全的相对路径。不得输出密钥、凭证或虚构现有仓库内容。"
    '仅返回 JSON：{"summary":"...","files":[{"path":"相对路径","content":"完整文件内容"}],'
    '"limitations":["..."],"apply_instructions":["..."]}。'
)
QA_PROMPT = (
    "你是独立软件 QA 岗位。基于需求、（如有）设计和生成文件，列出可执行的测试用例、风险和发布前检查。"
    "你没有运行这些测试，必须把状态标成未执行，不得伪造通过结果。"
    '仅返回 JSON：{"test_cases":[{"name":"...","steps":["..."],"expected":"..."}],'
    '"risks":["..."],"verification_state":"not_run","review_summary":"..."}。'
)

MAX_FILES = 20
MAX_FILE_CHARS = 24_000
MAX_TOTAL_CHARS = 80_000
_SECRET_PATTERNS = (
    re.compile(r"\b(?:AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_+/=-]{20,}"),
)


def _contains_secret(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in _SECRET_PATTERNS)
    if isinstance(value, dict):
        return any(_contains_secret(key) or _contains_secret(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(item) for item in value)
    return False


def _call_software_model(provider: Any, *, remote: bool, consent: bool,
                         system: str, payload: dict) -> dict:
    if remote and _contains_secret(payload):
        raise SkillExecutionError("MODEL_INPUT_REDACTION_REQUIRED")
    response = call_json(provider, remote=remote, consent=consent, system=system, payload=payload)
    if _contains_secret(response):
        raise SkillExecutionError("MODEL_OUTPUT_REDACTION_REQUIRED")
    return response


def _text(value: Any, code: str = "MODEL_RESPONSE_INVALID") -> str:
    if not isinstance(value, str):
        raise SkillExecutionError(code)
    return " ".join(value.split())


def _safe_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "`" in value or "|" in value or any(ord(ch) < 32 for ch in value):
        raise SkillExecutionError("MODEL_RESPONSE_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise SkillExecutionError("MODEL_RESPONSE_INVALID")
    return path.as_posix()


def _files(value: Any, *, content_required: bool) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_FILES:
        raise SkillExecutionError("MODEL_RESPONSE_INVALID")
    parsed = []
    seen = set()
    total = 0
    for item in value:
        if not isinstance(item, dict):
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        path = _safe_path(item.get("path"))
        if path in seen:
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        seen.add(path)
        key = "content" if content_required else "purpose"
        raw = item.get(key)
        if not isinstance(raw, str) or not raw.strip():
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        if len(raw) > MAX_FILE_CHARS:
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        total += len(raw)
        if content_required and (
            re.search(r"\bAKIA[0-9A-Z]{16}\b|\bsk-[A-Za-z0-9_-]{20,}\b", raw)
            or "-----BEGIN PRIVATE KEY-----" in raw
        ):
            raise SkillExecutionError("MODEL_OUTPUT_REDACTION_REQUIRED")
        parsed.append({"path": path, key: raw.strip()})
    if total > MAX_TOTAL_CHARS:
        raise SkillExecutionError("MODEL_RESPONSE_INVALID")
    return parsed


def _payload(wi: WorkItem, feedback: list[str], **extra) -> dict:
    return {
        "request": request_text(wi),
        "context": context_text(wi),
        "rework_feedback": list(feedback),
        **extra,
    }


def make_architecture_handler(provider: Any, *, remote: bool, consent: bool):
    def handler(step: PlanStep, wi: WorkItem, feedback: list[str]) -> dict[str, Any]:
        response = _call_software_model(provider, remote=remote, consent=consent,
                                        system=DESIGN_PROMPT, payload=_payload(wi, feedback))
        summary = _text(response.get("summary"))
        assumptions = clean_lines(response.get("assumptions"))
        criteria = clean_lines(response.get("acceptance_criteria"))
        files = _files(response.get("files"), content_required=False)
        if not summary or not criteria:
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        return {
            "type": "software-design", "skill": step.skill, "role": step.role,
            "summary": summary, "assumptions": assumptions,
            "acceptance_criteria": criteria, "files": files, "placeholder": False,
            "evidence": evidence(provider, remote=remote, consent=consent, wi=wi,
                                 feedback=feedback, stage="design"),
        }
    return handler


def make_implementation_handler(provider: Any, *, remote: bool, consent: bool):
    def handler(step: PlanStep, wi: WorkItem, feedback: list[str]) -> dict[str, Any]:
        design = next((out for out in wi.outputs if out.get("type") == "software-design"), None)
        response = _call_software_model(provider, remote=remote, consent=consent,
                                        system=IMPLEMENT_PROMPT,
                                        payload=_payload(wi, feedback, design=design or {}))
        summary = _text(response.get("summary"))
        files = _files(response.get("files"), content_required=True)
        limitations = clean_lines(response.get("limitations"))
        instructions = clean_lines(response.get("apply_instructions"))
        if not summary:
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        return {
            "type": "software-change", "skill": step.skill, "role": step.role,
            "summary": summary, "files": files, "limitations": limitations,
            "apply_instructions": instructions, "placeholder": False,
            "evidence": evidence(provider, remote=remote, consent=consent, wi=wi,
                                 feedback=feedback, stage="implementation",
                                 design_files=len(design.get("files", [])) if design else 0),
        }
    return handler


def make_qa_handler(provider: Any, *, remote: bool, consent: bool):
    def handler(step: PlanStep, wi: WorkItem, feedback: list[str]) -> dict[str, Any]:
        design = next((out for out in wi.outputs if out.get("type") == "software-design"), None)
        change = next((out for out in wi.outputs if out.get("type") == "software-change"), None)
        if not change:
            raise SkillExecutionError("SOFTWARE_IMPLEMENTATION_MISSING")
        response = _call_software_model(provider, remote=remote, consent=consent,
                                        system=QA_PROMPT,
                                        payload=_payload(wi, feedback, design=design or {}, implementation=change))
        cases = response.get("test_cases")
        if not isinstance(cases, list) or not 1 <= len(cases) <= 30:
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        parsed_cases = []
        for case in cases:
            if not isinstance(case, dict):
                raise SkillExecutionError("MODEL_RESPONSE_INVALID")
            steps = clean_lines(case.get("steps"))
            name = _text(case.get("name"))
            expected = _text(case.get("expected"))
            if not name or not steps or not expected:
                raise SkillExecutionError("MODEL_RESPONSE_INVALID")
            parsed_cases.append({"name": name, "steps": steps, "expected": expected})
        state = response.get("verification_state")
        if state != "not_run":
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        risks = clean_lines(response.get("risks"))
        summary = _text(response.get("review_summary"))
        if not summary:
            raise SkillExecutionError("MODEL_RESPONSE_INVALID")
        return {
            "type": "software-test-report", "skill": step.skill, "role": step.role,
            "test_cases": parsed_cases, "risks": risks,
            "verification_state": "not_run", "review_summary": summary,
            "placeholder": False,
            "evidence": evidence(provider, remote=remote, consent=consent, wi=wi,
                                 feedback=feedback, stage="qa", implementation_files=len(change["files"])),
        }
    return handler


def make_software_handlers(provider: Any, *, remote: bool, consent: bool) -> dict[str, Any]:
    return {
        "software.architecture-design": make_architecture_handler(provider, remote=remote, consent=consent),
        "software.implementation": make_implementation_handler(provider, remote=remote, consent=consent),
        "software.frontend-change": make_implementation_handler(provider, remote=remote, consent=consent),
        "software.backend-change": make_implementation_handler(provider, remote=remote, consent=consent),
        "software.bug-fix": make_implementation_handler(provider, remote=remote, consent=consent),
        "software.refactor": make_implementation_handler(provider, remote=remote, consent=consent),
        "software.test": make_qa_handler(provider, remote=remote, consent=consent),
    }
