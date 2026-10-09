"""Review —— 独立审核。审核者永远不是产出者。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .executor import requested_count
from .models import WorkItem

WECHAT_TITLE_MAX = 64


@dataclass
class ReviewResult:
    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def failures(self) -> list[str]:
        return [c["detail"] for c in self.checks if not c["ok"]]


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "ok": bool(ok), "detail": detail}


class RuleReviewer:
    def review(self, wi: WorkItem, outputs: list[dict[str, Any]]) -> ReviewResult:
        checks: list[dict[str, Any]] = []
        plan_steps = wi.execution_plan.steps if wi.execution_plan else ()
        checks.append(_check(
            "required-output-present",
            len(outputs) >= len(plan_steps) and len(outputs) > 0,
            f"计划 {len(plan_steps)} 步，产出 {len(outputs)} 项",
        ))

        for out in outputs:
            if out.get("placeholder"):
                checks.append(_check(
                    "placeholder-declared", True,
                    f"{out.get('skill')} 为占位产出，已如实标记",
                ))
            if out.get("type") == "title-list":
                items = [str(x).strip() for x in out.get("items", [])]
                want = requested_count(wi.input)
                checks.append(_check("title-count", len(items) == want, f"要求 {want} 个，实际 {len(items)} 个"))
                checks.append(_check("title-non-empty", all(items), "标题均非空" if all(items) else "存在空标题"))
                checks.append(_check("title-unique", len(set(items)) == len(items),
                                     "标题无重复" if len(set(items)) == len(items) else "存在重复标题"))
                too_long = [t for t in items if len(t) > WECHAT_TITLE_MAX]
                checks.append(_check("title-length", not too_long,
                                     f"均不超过 {WECHAT_TITLE_MAX} 字" if not too_long else f"{len(too_long)} 个超过 {WECHAT_TITLE_MAX} 字"))

        return ReviewResult(passed=all(c["ok"] for c in checks), checks=checks)
