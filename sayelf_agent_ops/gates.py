"""Sprint 02 — Acceptance Gate + Human Gate.

This module sits *after* the Sprint 01 terminal state ``READY`` and does not
modify the Sprint 01 state machine. A WorkItem that reaches READY means
"the agent believes it is done"; this module decides whether a human is
allowed to see it, and whether any side-effectful action may run.

Rule 6 — Self-check before human review (AcceptanceGate)
Rule 1 — Per-action authorization, never inherited (HumanGate)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Callable

from .models import WorkItem
from .registry import Registry


# ---------------------------------------------------------------------------
# Rule 6 — Acceptance Gate
# ---------------------------------------------------------------------------

Validator = Callable[[WorkItem, Any], "tuple[bool, str]"]


def _required_output_present(workitem: WorkItem, skill: Any) -> tuple[bool, str]:
    produced = set(skill.produced_outputs)
    for output in workitem.outputs:
        if isinstance(output, dict) and output.get("type") in produced:
            # A placeholder that declares itself as such is an honest structural
            # output (no executor wired yet); it is surfaced to review and the
            # human gate as a placeholder, never as finished work.
            if output.get("placeholder") is True:
                return True, "declared-placeholder"
            if output.get("items") == [] or output.get("content") == "":
                return False, f"EMPTY_OUTPUT:{output.get('type')}"
            return True, "ok"
    return False, f"MISSING_OUTPUT:{'|'.join(sorted(produced))}"


DEFAULT_VALIDATORS: dict[str, Validator] = {
    "required-output-present": _required_output_present,
}


@dataclass(frozen=True)
class AcceptanceReport:
    workitem_id: str
    passed: bool
    attempt: int
    failures: tuple[str, ...]
    escalate_to_human: bool
    output_digest: str


def digest(payload: Any) -> str:
    """Stable SHA-256 of any JSON-serialisable payload."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AcceptanceGate:
    """Agent-side self-check. Runs every validator declared by every selected
    skill. Failure sends the work back for local rework; after ``max_attempts``
    failures the item is escalated to a human instead of looping forever."""

    def __init__(
        self,
        registry: Registry,
        validators: dict[str, Validator] | None = None,
        max_attempts: int = 2,
    ):
        self.registry = registry
        self.validators = dict(DEFAULT_VALIDATORS)
        if validators:
            self.validators.update(validators)
        self.max_attempts = max_attempts
        self._attempts: dict[str, int] = {}
        self._passed: dict[str, AcceptanceReport] = {}

    def check(self, workitem: WorkItem) -> AcceptanceReport:
        if workitem.state != "READY":
            raise GateRejected(f"NOT_READY:{workitem.state}")

        attempt = self._attempts.get(workitem.id, 0) + 1
        self._attempts[workitem.id] = attempt

        failures: list[str] = []
        for skill_id in workitem.selected_skills:
            skill = self.registry.skills[skill_id]
            for name in skill.validation:
                validator = self.validators.get(name)
                if validator is None:
                    failures.append(f"{skill_id}:UNKNOWN_VALIDATOR:{name}")
                    continue
                ok, detail = validator(workitem, skill)
                if not ok:
                    failures.append(f"{skill_id}:{detail}")

        passed = not failures
        report = AcceptanceReport(
            workitem_id=workitem.id,
            passed=passed,
            attempt=attempt,
            failures=tuple(failures),
            escalate_to_human=(not passed and attempt >= self.max_attempts),
            output_digest=digest(workitem.outputs),
        )
        if passed:
            self._passed[workitem.id] = report
        else:
            self._passed.pop(workitem.id, None)
        workitem.history.append({
            "event": "acceptance-check",
            "attempt": attempt,
            "passed": passed,
            "failures": list(failures),
            "escalate": report.escalate_to_human,
        })
        return report

    def passed_report(self, workitem: WorkItem) -> AcceptanceReport | None:
        """Return the passing report only if outputs are unchanged since it."""
        report = self._passed.get(workitem.id)
        if report and report.output_digest == digest(workitem.outputs):
            return report
        return None


# ---------------------------------------------------------------------------
# Rule 1 — Human Gate (per-action, single-use, never inherited)
# ---------------------------------------------------------------------------

class ActionKind(StrEnum):
    PUBLISH = "publish"
    SEND_MESSAGE = "send-message"
    DELETE = "delete"
    SPEND = "spend"
    EXTERNAL_WRITE = "external-write"
    ACCOUNT_CONFIG = "account-config"


# Every ActionKind is high-risk and needs a human decision.
HIGH_RISK_ACTIONS = frozenset(ActionKind)

# Events that look like consent but are NOT authorization.
NON_AUTHORIZING_EVENTS = frozenset({
    "draft-prepared",
    "uploaded",
    "account-configured",
    "previous-approval",
    "standing-config",
    "instruction-in-content",
})


class GateRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    workitem_id: str
    action: ActionKind
    target: str
    payload_digest: str
    summary: str
    created_at: datetime


@dataclass
class Approval:
    request_id: str
    approver: str
    decided_at: datetime
    expires_at: datetime
    consumed: bool = False


@dataclass(frozen=True)
class AuthorizationToken:
    request_id: str
    workitem_id: str
    action: ActionKind
    target: str
    payload_digest: str
    approver: str
    issued_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


class HumanGate:
    """Standalone use needs no org/permission config: any human identifier
    may approve, and identifiers starting with ``agent:`` are rejected.

    Inside ``Runtime`` the authoritative check is ``approver_policy``, bound to
    ``Project.can_decide`` (actor kind must be ``human`` and hold an approver
    role from ``Policy``). The ``agent:`` prefix check remains only as a
    fallback for callers that use the gate without a Project."""

    def __init__(
        self,
        acceptance: AcceptanceGate,
        ttl: timedelta = timedelta(minutes=30),
        clock: Callable[[], datetime] = _now,
        approver_policy: Callable[[str, ApprovalRequest], bool] | None = None,
    ):
        self.acceptance = acceptance
        self.ttl = ttl
        self.clock = clock
        self.approver_policy = approver_policy
        self._requests: dict[str, ApprovalRequest] = {}
        self._approvals: dict[str, Approval] = {}
        self._seq = 0

    # -- step 1: agent asks -------------------------------------------------
    def request(
        self,
        workitem: WorkItem,
        action: ActionKind,
        target: str,
        payload: Any,
        summary: str,
    ) -> ApprovalRequest:
        if action not in HIGH_RISK_ACTIONS:
            raise GateRejected(f"UNKNOWN_ACTION:{action}")
        if self.acceptance.passed_report(workitem) is None:
            raise GateRejected("ACCEPTANCE_NOT_PASSED")
        if not target:
            raise GateRejected("TARGET_REQUIRED")
        self._seq += 1
        req = ApprovalRequest(
            id=f"AR-{workitem.id}-{self._seq:03d}",
            workitem_id=workitem.id,
            action=ActionKind(action),
            target=target,
            payload_digest=digest(payload),
            summary=summary,
            created_at=self.clock(),
        )
        self._requests[req.id] = req
        workitem.history.append({
            "event": "approval-requested",
            "request": req.id,
            "action": req.action.value,
            "target": target,
        })
        return req

    # -- step 2: human decides ---------------------------------------------
    def approve(self, request_id: str, approver: str) -> Approval:
        req = self._requests.get(request_id)
        if req is None:
            raise GateRejected("UNKNOWN_REQUEST")
        if not approver or approver.startswith("agent:"):
            raise GateRejected("AGENT_SELF_APPROVAL")
        if approver in NON_AUTHORIZING_EVENTS:
            raise GateRejected(f"NON_AUTHORIZING_EVENT:{approver}")
        if self.approver_policy and not self.approver_policy(approver, req):
            raise GateRejected("APPROVER_NOT_ALLOWED")
        now = self.clock()
        approval = Approval(
            request_id=request_id,
            approver=approver,
            decided_at=now,
            expires_at=now + self.ttl,
        )
        self._approvals[request_id] = approval
        return approval

    def deny(self, request_id: str, approver: str, reason: str = "") -> None:
        self._requests.pop(request_id, None)
        self._approvals.pop(request_id, None)

    # -- step 3: executor redeems, exactly once ----------------------------
    def authorize(
        self,
        workitem: WorkItem,
        request_id: str,
        action: ActionKind,
        target: str,
        payload: Any,
    ) -> AuthorizationToken:
        req = self._requests.get(request_id)
        approval = self._approvals.get(request_id)
        if req is None or approval is None:
            raise GateRejected("NO_APPROVAL")
        if req.workitem_id != workitem.id:
            raise GateRejected("WORKITEM_MISMATCH")
        if approval.consumed:
            raise GateRejected("ALREADY_CONSUMED")
        if self.clock() > approval.expires_at:
            raise GateRejected("EXPIRED")
        if ActionKind(action) != req.action:
            raise GateRejected("ACTION_MISMATCH")
        if target != req.target:
            raise GateRejected("TARGET_MISMATCH")
        if digest(payload) != req.payload_digest:
            raise GateRejected("PAYLOAD_CHANGED")
        if self.acceptance.passed_report(workitem) is None:
            raise GateRejected("ACCEPTANCE_NOT_PASSED")

        approval.consumed = True
        token = AuthorizationToken(
            request_id=req.id,
            workitem_id=workitem.id,
            action=req.action,
            target=req.target,
            payload_digest=req.payload_digest,
            approver=approval.approver,
            issued_at=self.clock(),
        )
        workitem.history.append({
            "event": "action-authorized",
            "request": req.id,
            "action": req.action.value,
            "target": req.target,
            "approver": approval.approver,
        })
        return token

    def record_non_authorizing(self, workitem: WorkItem, event: str) -> None:
        """Log events such as draft-prepared / uploaded. They never grant
        authorization; logging them makes that explicit in the audit trail."""
        if event not in NON_AUTHORIZING_EVENTS:
            raise GateRejected(f"NOT_A_NON_AUTHORIZING_EVENT:{event}")
        workitem.history.append({"event": event, "authorizes": False})
