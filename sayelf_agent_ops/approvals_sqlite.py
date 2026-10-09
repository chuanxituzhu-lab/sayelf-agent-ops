"""Durable HumanGate store on SQLite (standard library only).

One schema and one implementation for every entry: the desktop app passes its
workspace connection; the MCP server and the approval CLI share a file under
``SAYELF_AGENT_OPS_HOME``. ``consume`` is a single conditional UPDATE, so one
approval can authorize exactly one action even across processes.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, ContextManager

from .gates import ActionKind, Approval, ApprovalRequest

GATE_TABLE_SQL = (
    """CREATE TABLE IF NOT EXISTS gate_approvals (
        request_id TEXT PRIMARY KEY,
        workitem_id TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        summary TEXT NOT NULL,
        created_at TEXT NOT NULL,
        approver TEXT,
        decided_at TEXT,
        expires_at TEXT,
        consumed_at TEXT,
        denied_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS gate_approvals_workitem ON gate_approvals(workitem_id, created_at)",
)


def create_gate_tables(connection: sqlite3.Connection) -> None:
    for statement in GATE_TABLE_SQL:
        connection.execute(statement)


def _ts(value: datetime) -> str:
    return value.isoformat()


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SQLiteApprovalStore:
    def __init__(self, connect: Callable[[], ContextManager[sqlite3.Connection]]):
        self._connect = connect

    @classmethod
    def at_path(cls, path: str | Path) -> "SQLiteApprovalStore":
        database = Path(path)
        database.parent.mkdir(parents=True, exist_ok=True)

        @contextmanager
        def connect():
            connection = sqlite3.connect(database, timeout=5)
            try:
                with connection:
                    yield connection
            finally:
                connection.close()

        with connect() as connection:
            create_gate_tables(connection)
        return cls(connect)

    def add_request(self, req: ApprovalRequest) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO gate_approvals (request_id, workitem_id, action, target, payload_digest, "
                "summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (req.id, req.workitem_id, req.action.value, req.target, req.payload_digest,
                 req.summary, _ts(req.created_at)),
            )

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        with self._connect() as connection:
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
        with self._connect() as connection:
            connection.execute(
                "UPDATE gate_approvals SET approver=?, decided_at=?, expires_at=? "
                "WHERE request_id=? AND consumed_at IS NULL AND denied_at IS NULL",
                (approval.approver, _ts(approval.decided_at), _ts(approval.expires_at),
                 approval.request_id),
            )

    def get_approval(self, request_id: str) -> Approval | None:
        with self._connect() as connection:
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
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE gate_approvals SET consumed_at=? WHERE request_id=? "
                "AND approver IS NOT NULL AND consumed_at IS NULL AND denied_at IS NULL",
                (_ts(at), request_id),
            )
            return cursor.rowcount == 1

    def deny(self, request_id: str, approver: str, at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE gate_approvals SET denied_at=?, approver=? "
                "WHERE request_id=? AND consumed_at IS NULL",
                (_ts(at), approver, request_id),
            )

    def list_requests(self, *, open_only: bool = True, limit: int = 50) -> list[dict]:
        """Requests for the human to review. ``open_only``: not consumed, not denied."""
        sql = ("SELECT request_id, workitem_id, action, target, payload_digest, summary, created_at, "
               "approver, decided_at, expires_at, consumed_at, denied_at FROM gate_approvals")
        if open_only:
            sql += " WHERE consumed_at IS NULL AND denied_at IS NULL"
        sql += " ORDER BY created_at DESC LIMIT ?"
        keys = ("request_id", "workitem_id", "action", "target", "payload_digest", "summary",
                "created_at", "approver", "decided_at", "expires_at", "consumed_at", "denied_at")
        with self._connect() as connection:
            return [dict(zip(keys, row)) for row in connection.execute(sql, (int(limit),))]
