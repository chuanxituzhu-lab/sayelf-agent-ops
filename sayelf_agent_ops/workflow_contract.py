"""Small, deterministic workflow contracts for host-side Agent Ops execution.

The v1.5 workflow archive describes a useful division sheet, but it does not
provide an executable runtime.  This module turns the already routed plan into
that sheet and validates the safety/evidence fields before a host executes it.
It deliberately does not call a model, persist user content, or execute tools.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import ExecutionPlan, RoutingDecision
from .registry import Registry

PATTERNS = ("router", "sequential", "parallel", "loop", "agent-as-tool")
HOST_EVIDENCE_FIELDS = (
    "source_revision",
    "route_digest",
    "steps",
    "changed_files",
    "verification",
    "producer_self_check",
    "independent_review",
    "limitations",
)
REQUIRED_EXECUTION_EVIDENCE = (
    "changed_files",
    "verification",
    "producer_self_check",
    "independent_review",
    "limitations",
)


def _repeatability(text: str) -> str:
    lowered = text.casefold()
    if any(marker in lowered for marker in ("每天", "每日", "每周", "每月", "定期", "daily", "weekly", "monthly")):
        return "recurring"
    return "one_off"


def build_workflow_contract(
    text: str,
    decision: RoutingDecision,
    plan: ExecutionPlan,
    registry: Registry,
) -> dict[str, Any]:
    """Compile a routed plan into a host-readable division sheet."""
    pattern = "agent-as-tool" if len(plan.steps) == 1 else "sequential"
    role_steps: list[dict[str, Any]] = []
    for step in plan.steps:
        role = registry.roles[step.role]
        skill = registry.skills[step.skill]
        role_steps.append({
            "step": step.step,
            "role": step.role,
            "responsibility": role.responsibility,
            "skill": step.skill,
            "inputs": list(skill.accepted_inputs),
            "output": step.output,
            "done_when": step.done_when,
            "forbidden_scope": list(role.forbidden_scope),
            "tool_boundary": {
                "executor": "codex",
                "scope": "local",
                "model_call": False,
                "external_write": "human-gated",
            },
        })

    handoffs = []
    for previous, current in zip(role_steps, role_steps[1:]):
        handoffs.append({
            "from_step": previous["step"],
            "to_step": current["step"],
            "artifact": previous["output"],
            "accepted_as": current["inputs"],
        })

    contract: dict[str, Any] = {
        "schema": "workflow-contract-v1",
        "task": text,
        "epistemic": {"task": "source_fact", "route": "deterministic_inference", "execution": "unverified"},
        "gate": {
            "status": "agent_required",
            "reason": "任务已匹配登记的专业交付物；按最少技能闭环执行。",
            "minimum_roles": len({step["role"] for step in role_steps}),
        },
        "pattern": pattern,
        "pattern_chain": ["router", pattern],
        "repeatability": _repeatability(text),
        "roles": role_steps,
        "handoffs": handoffs,
        "communication": {
            "protocol": "structured-step-fields",
            "state_scope": "host-local",
            "raw_task_retention": "none",
        },
        "memory": {
            "scope": "current-run",
            "long_term_facts": "none",
            "host_must_persist_evidence": True,
        },
        "review": {
            "producer_self_check": {"required": True, "evidence": "producer_self_check"},
            "independent_review": {"required": True, "separate_from_producer": True, "evidence": "independent_review"},
        },
        "loop": {
            "enabled": False,
            "max_iterations": 0,
            "exit_condition": "失败即停，由宿主明确安排返工；本路由不自动循环。",
        },
        "human_gate": {
            "required_for": ["publish", "deploy", "external_write", "send", "delete", "spend"],
            "approval_scope": "one-action-one-target-one-artifact",
        },
        "state": {"status": "planned", "truth": "host_execution_evidence", "storage": "local"},
        "acceptance": [step["done_when"] for step in role_steps],
        "stop_conditions": [
            "技能未登记、能力不足或工具边界不明确时停止。",
            "产出者自检或独立复核失败时停止并记录原因。",
            "实际变更、验证或限制条件缺少证据时不得标记完成。",
        ],
        "required_evidence": list(REQUIRED_EXECUTION_EVIDENCE),
        "unverified": ["host execution", "changed files", "verification", "independent review"],
        "decision": {
            "industry": decision.industry,
            "deliverable_type": decision.deliverable_type,
            "selected_roles": list(dict.fromkeys(step["role"] for step in role_steps)),
            "selected_skills": list(decision.selected_skills),
        },
    }
    return contract


def validate_workflow_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the division sheet without executing or trusting its claims."""
    violations: list[str] = []
    if not isinstance(contract, Mapping):
        return {"ok": False, "status": "invalid", "violations": ["CONTRACT_NOT_OBJECT"]}
    if contract.get("schema") != "workflow-contract-v1":
        violations.append("SCHEMA_UNSUPPORTED")
    pattern = contract.get("pattern")
    if pattern not in PATTERNS or pattern == "router":
        violations.append("PATTERN_MUST_DESCRIBE_EXECUTION")
    roles = contract.get("roles")
    if not isinstance(roles, list) or not roles:
        violations.append("ROLES_REQUIRED")
        roles = []
    if pattern == "agent-as-tool" and len(roles) != 1:
        violations.append("AGENT_AS_TOOL_MUST_HAVE_ONE_ROLE")
    if pattern == "sequential" and len(roles) < 1:
        violations.append("SEQUENTIAL_STEPS_REQUIRED")
    gate = contract.get("gate")
    if not isinstance(gate, Mapping) or gate.get("status") != "agent_required":
        violations.append("MINIMUM_GATE_REQUIRED")
    elif not isinstance(gate.get("minimum_roles"), int) or gate.get("minimum_roles", 0) < 1:
        violations.append("MINIMUM_ROLE_COUNT_REQUIRED")
    for index, role in enumerate(roles):
        if not isinstance(role, Mapping):
            violations.append(f"ROLE_{index}_NOT_OBJECT")
            continue
        for key in ("role", "skill", "inputs", "output", "done_when", "forbidden_scope", "tool_boundary"):
            if key not in role:
                violations.append(f"ROLE_{index}_{key.upper()}_REQUIRED")
        boundary = role.get("tool_boundary")
        if isinstance(boundary, Mapping):
            if boundary.get("executor") != "codex" or boundary.get("scope") != "local":
                violations.append(f"ROLE_{index}_TOOL_BOUNDARY_INVALID")
            if boundary.get("model_call") is not False:
                violations.append(f"ROLE_{index}_MODEL_CALL_NOT_DISABLED")
            if boundary.get("external_write") != "human-gated":
                violations.append(f"ROLE_{index}_EXTERNAL_WRITE_NOT_GATED")
    review = contract.get("review")
    if not isinstance(review, Mapping):
        violations.append("REVIEW_REQUIRED")
    else:
        self_check = review.get("producer_self_check")
        independent = review.get("independent_review")
        if not isinstance(self_check, Mapping) or self_check.get("required") is not True:
            violations.append("PRODUCER_SELF_CHECK_REQUIRED")
        if not isinstance(independent, Mapping) or independent.get("required") is not True:
            violations.append("INDEPENDENT_REVIEW_REQUIRED")
        elif independent.get("separate_from_producer") is not True:
            violations.append("REVIEWER_MUST_BE_INDEPENDENT")
    loop = contract.get("loop")
    if not isinstance(loop, Mapping):
        violations.append("LOOP_POLICY_REQUIRED")
    elif loop.get("enabled"):
        if not isinstance(loop.get("max_iterations"), int) or loop.get("max_iterations", 0) <= 0:
            violations.append("LOOP_MAX_ITERATIONS_REQUIRED")
        if not isinstance(loop.get("exit_condition"), str) or not loop.get("exit_condition", "").strip():
            violations.append("LOOP_EXIT_CONDITION_REQUIRED")
    elif loop.get("max_iterations") != 0:
        violations.append("DISABLED_LOOP_MUST_HAVE_ZERO_ITERATIONS")
    state = contract.get("state")
    if not isinstance(state, Mapping) or state.get("status") != "planned":
        violations.append("PLAN_MUST_REMAIN_UNVERIFIED")
    if not isinstance(contract.get("acceptance"), list) or not contract.get("acceptance"):
        violations.append("ACCEPTANCE_REQUIRED")
    if not isinstance(contract.get("stop_conditions"), list) or not contract.get("stop_conditions"):
        violations.append("STOP_CONDITIONS_REQUIRED")
    evidence = contract.get("required_evidence")
    if not isinstance(evidence, list) or not set(REQUIRED_EXECUTION_EVIDENCE).issubset(evidence):
        violations.append("REQUIRED_EVIDENCE_INCOMPLETE")
    unverified = contract.get("unverified")
    if not isinstance(unverified, list) or not unverified:
        violations.append("UNVERIFIED_BOUNDARY_REQUIRED")
    return {
        "ok": not violations,
        "status": "valid" if not violations else "invalid",
        "violations": violations,
        "checked": ["minimum_roles", "role_contracts", "tool_boundary", "review_separation", "loop_exit", "acceptance", "stop_conditions", "truthful_status"],
    }


def validate_host_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Check a host evidence envelope; missing review keeps it pending."""
    violations: list[str] = []
    if not isinstance(evidence, Mapping):
        return {"ok": False, "status": "invalid", "violations": ["EVIDENCE_NOT_OBJECT"]}
    if evidence.get("schema") != "host-execution-evidence-v1":
        violations.append("SCHEMA_UNSUPPORTED")
    if evidence.get("status") not in {"not_run", "executed", "review_pending", "verified"}:
        violations.append("STATUS_UNSUPPORTED")
    for key in HOST_EVIDENCE_FIELDS:
        if key not in evidence:
            violations.append(f"{key.upper()}_REQUIRED")
    for key in ("source_revision", "route_digest"):
        if evidence.get(key) in (None, "", "host-must-record"):
            violations.append(f"{key.upper()}_MUST_BE_RECORDED")
    if evidence.get("status") in {"DELIVERED", "COMPLETED", "APPROVED"}:
        violations.append("HOST_CLAIM_CANNOT_ESTABLISH_COMPLETION")
    steps = evidence.get("steps")
    if not isinstance(steps, list) or not steps:
        violations.append("EXECUTED_STEPS_REQUIRED")
    for field in ("changed_files", "verification", "limitations"):
        if field in evidence and not isinstance(evidence[field], list):
            violations.append(f"{field.upper()}_MUST_BE_LIST")
    producer = evidence.get("producer_self_check")
    reviewer = evidence.get("independent_review")
    if not isinstance(producer, Mapping) or producer.get("status") != "passed":
        violations.append("PRODUCER_SELF_CHECK_NOT_PASSED")
    if not isinstance(reviewer, Mapping) or reviewer.get("status") != "passed":
        violations.append("INDEPENDENT_REVIEW_NOT_PASSED")
    elif reviewer.get("actor_id") == (producer or {}).get("actor_id"):
        violations.append("REVIEWER_EQUALS_PRODUCER")
    if evidence.get("status") == "not_run" and isinstance(steps, list) and steps:
        violations.append("STATUS_NOT_RUN_CONTRADICTS_STEPS")
    if evidence.get("status") == "review_pending" and isinstance(reviewer, Mapping) and reviewer.get("status") == "passed":
        violations.append("STATUS_PENDING_CONTRADICTS_PASSED_REVIEW")
    complete = not violations
    return {
        "ok": complete,
        "status": "verified" if complete else ("review_pending" if "INDEPENDENT_REVIEW_NOT_PASSED" in violations else "invalid"),
        "violations": violations,
        "required_fields": list(HOST_EVIDENCE_FIELDS),
    }
