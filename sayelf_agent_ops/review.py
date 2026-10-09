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
                want = requested_count(wi.goal or wi.input)
                checks.append(_check("title-count", len(items) == want, f"要求 {want} 个，实际 {len(items)} 个"))
                checks.append(_check("title-non-empty", all(items), "标题均非空" if all(items) else "存在空标题"))
                checks.append(_check("title-unique", len(set(items)) == len(items),
                                     "标题无重复" if len(set(items)) == len(items) else "存在重复标题"))
                too_long = [t for t in items if len(t) > WECHAT_TITLE_MAX]
                checks.append(_check("title-length", not too_long,
                                     f"均不超过 {WECHAT_TITLE_MAX} 字" if not too_long else f"{len(too_long)} 个超过 {WECHAT_TITLE_MAX} 字"))

            if out.get("type") == "outline" and not out.get("placeholder"):
                items = [str(x).strip() for x in out.get("items", [])]
                checks.append(_check("outline-size", 3 <= len(items) <= 10,
                                     f"大纲 {len(items)} 个要点（应为 3–10 个）"))
                checks.append(_check("outline-unique", len(set(items)) == len(items) and all(items),
                                     "要点非空且不重复" if len(set(items)) == len(items) and all(items) else "存在空要点或重复要点"))
            if out.get("type") == "video-script" and not out.get("placeholder"):
                scenes = out.get("scenes") or []
                total = sum(float(s.get("seconds", 0)) for s in scenes)
                limit = out.get("duration_seconds") or 60
                checks.append(_check("script-hook", bool(str(out.get("hook", "")).strip()), "开头钩子已写" if str(out.get("hook", "")).strip() else "缺少开头钩子"))
                checks.append(_check("script-scenes", 3 <= len(scenes) <= 12, f"{len(scenes)} 个镜头（应为 3–12 个）"))
                incomplete = [i + 1 for i, s in enumerate(scenes) if not (s.get("shot") and s.get("voiceover"))]
                checks.append(_check("script-scene-complete", not incomplete,
                                     "每个镜头都有画面和口播" if not incomplete else f"第 {incomplete} 个镜头缺画面或口播"))
                checks.append(_check("script-duration", 0 < total <= limit * 1.1,
                                     f"总时长 {total:g} 秒（上限 {limit} 秒）"))

        return ReviewResult(passed=all(c["ok"] for c in checks), checks=checks)
