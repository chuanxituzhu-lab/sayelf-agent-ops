"""Durable HumanGate approvals for the desktop app.

One rule set for every human approval: the kernel ``HumanGate`` decides what
an approval covers (action, target, payload digest; single use; expiry), and
this module only stores it in the workspace SQLite so it survives restarts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from desktop.runtime import bootstrap
from sayelf_agent_ops.gates import ActionKind, Approval, ApprovalRequest, HumanGate

# Solo desktop: the person at this computer is the only human member.
LOCAL_HUMAN = "human.local-user"


def _ts(value: datetime) -> str:
    return value.isoformat()


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SQLiteApprovalStore:
    def __init__(self, root):
        self.root = root

    def add_request(self, req: ApprovalRequest) -> None:
        with bootstrap._opened(self.root) as connection:
            connection.execute(
                "INSERT INTO gate_approvals (request_id, workitem_id, action, target, payload_digest, "
                "summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (req.id, req.workitem_id, req.action.value, req.target, req.payload_digest,
                 req.summary, _ts(req.created_at)),
            )

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        with bootstrap._opened(self.root) as connection:
            row = connection.execute(
                "SELECT request_id, workitem_id, action, target, payload_digest, summary, created_at "
                "FROM gate_approvals WHERE request_id=? AND denied_at IS NULL",
                (request_id,),
            ).fetchone()
        if not row:
            return None
        return ApprovalRequest(
            id=row[0], workitem_id=row[1], action=ActionKind(row[2]), target=row[3],
            payload_digest=row[4], summary=row[5], created_at=_dt(row[6]),
        )

    def put_approval(self, approval: Approval) -> None:
        with bootstrap._opened(self.root) as connection:
            connection.execute(
                "UPDATE gate_approvals SET approver=?, decided_at=?, expires_at=? "
                "WHERE request_id=? AND consumed_at IS NULL AND denied_at IS NULL",
                (approval.approver, _ts(approval.decided_at), _ts(approval.expires_at),
                 approval.request_id),
            )

    def get_approval(self, request_id: str) -> Approval | None:
        with bootstrap._opened(self.root) as connection:
            row = connection.execute(
                "SELECT approver, decided_at, expires_at, consumed_at FROM gate_approvals "
                "WHERE request_id=? AND denied_at IS NULL AND approver IS NOT NULL",
                (request_id,),
            ).fetchone()
        if not row:
            return None
        return Approval(
            request_id=request_id, approver=row[0], decided_at=_dt(row[1]),
            expires_at=_dt(row[2]), consumed=row[3] is not None,
        )

    def consume(self, request_id: str, at: datetime) -> bool:
        # Atomic: exactly one caller can move an approval to consumed.
        with bootstrap._opened(self.root) as connection:
            cursor = connection.execute(
                "UPDATE gate_approvals SET consumed_at=? WHERE request_id=? "
                "AND approver IS NOT NULL AND consumed_at IS NULL AND denied_at IS NULL",
                (_ts(at), request_id),
            )
            return cursor.rowcount == 1

    def deny(self, request_id: str, approver: str, at: datetime) -> None:
        with bootstrap._opened(self.root) as connection:
            connection.execute(
                "UPDATE gate_approvals SET denied_at=?, approver=? "
                "WHERE request_id=? AND consumed_at IS NULL",
                (_ts(at), approver, request_id),
            )


@dataclass(frozen=True)
class _VersionReport:
    output_digest: str


class ResultVersionAcceptance:
    """Acceptance for desktop results: the payload must name a stored result
    version whose recorded content digest matches. Stage outputs were already
    validated by the media workflow before that version was stored."""

    def __init__(self, root):
        self.root = root

    def passed_report(self, workitem):
        if len(workitem.outputs) != 1 or not isinstance(workitem.outputs[0], dict):
            return None
        output = workitem.outputs[0]
        with bootstrap._opened(self.root) as connection:
            row = connection.execute(
                "SELECT content_sha256 FROM workflow_results WHERE workitem_id=? AND version=?",
                (workitem.id, output.get("version")),
            ).fetchone()
        if not row or row[0] != output.get("content_sha256"):
            return None
        return _VersionReport(output_digest=row[0])


def desktop_human_gate(root) -> HumanGate:
    return HumanGate(
        ResultVersionAcceptance(root),
        approver_policy=lambda approver, req: approver == LOCAL_HUMAN,
        store=SQLiteApprovalStore(root),
    )
