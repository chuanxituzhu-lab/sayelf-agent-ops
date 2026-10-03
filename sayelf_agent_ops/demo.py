from __future__ import annotations

from .models import WorkItem
from .planner import MinimumPlanner, apply_routing
from .registry import build_default_registry
from .router import Router
from .state import StateEngine, WorkState


def run_first_vertical_slice() -> WorkItem:
    registry = build_default_registry()
    router = Router(registry)
    planner = MinimumPlanner()
    state = StateEngine()

    wi = WorkItem(
        id="WI-0001",
        input='给“一人公司 Agent Ops”生成 5 个公众号标题',
        goal="获得 5 个可用于微信公众号的文章标题",
        deliverable="公众号标题 × 5",
    )

    # Scope determines the business context before routing.
    wi.industry = "media"
    state.transition(wi, WorkState.SCOPED)

    decision = router.route(wi)
    plan = planner.build(wi, decision)
    apply_routing(wi, decision, plan)
    state.transition(wi, WorkState.WORKING)

    # Sprint 01 uses a deterministic placeholder executor only to prove
    # WorkItem → route → plan → output → READY. Real Skill execution is later.
    wi.outputs.append({
        "type": "title-list",
        "items": [
            "一人公司 Agent Ops：不是雇 100 个 AI，而是重新设计一家公司",
            "AI 时代的一人公司，不需要 100 个 Agent",
            "别再堆 Agent 了：一人公司真正需要的是最小专业组织",
            "一个人，一家公司：我正在搭建自己的 Agent Ops",
            "最少岗位，专业闭环：我理解的一人公司 Agent Ops",
        ],
    })
    state.transition(wi, WorkState.READY)
    return wi


def main() -> None:
    wi = run_first_vertical_slice()
    print(f"WorkItem: {wi.id}")
    print(f"Industry: {wi.industry}")
    print(f"Deliverable: {wi.deliverable_type}")
    print(f"Role: {wi.selected_role}")
    print(f"Skills: {', '.join(wi.selected_skills)}")
    print(f"Excluded: {', '.join(wi.excluded_roles)}")
    print(f"State: {wi.state}")


if __name__ == "__main__":
    main()
