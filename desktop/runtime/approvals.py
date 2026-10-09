"""Durable HumanGate approvals for the desktop app.

One rule set for every human approval: the kernel ``HumanGate`` decides what
an approval covers (action, target, payload digest; single use; expiry), and
this module only stores it in the workspace SQLite so it survives restarts.
"""
from __future__ import annotations

from dataclasses import dataclass

from desktop.runtime import bootstrap
from sayelf_agent_ops.approvals_sqlite import SQLiteApprovalStore as KernelSQLiteApprovalStore
from sayelf_agent_ops.gates import HumanGate

# Solo desktop: the person at this computer is the only human member.
LOCAL_HUMAN = "human.local-user"


class SQLiteApprovalStore(KernelSQLiteApprovalStore):
    """The kernel store, bound to this workspace's runtime database."""

    def __init__(self, root):
        super().__init__(lambda: bootstrap._opened(root))
        self.root = root


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
