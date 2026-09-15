"""Durable state for approved control-plane operations other than imports."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import pathlib
import sqlite3
import uuid


@dataclasses.dataclass(frozen=True)
class BranchOperation:
    id: str
    requester: str
    channel: str
    project: str
    branch: str
    base: str
    status: str
    result_url: str | None


class OperationStore:
    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS branch_operations (
                    id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                    requester TEXT NOT NULL, channel TEXT NOT NULL,
                    project TEXT NOT NULL, branch TEXT NOT NULL, base TEXT NOT NULL,
                    status TEXT NOT NULL, result_url TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS operation_audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                    operation_id TEXT NOT NULL, event_type TEXT NOT NULL, actor TEXT NOT NULL,
                    details_json TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def create_branch(
        self,
        *,
        requester: str,
        channel: str,
        project: str,
        branch: str,
        base: str,
        idempotency_key: str,
    ) -> BranchOperation:
        now = dt.datetime.now(dt.UTC).isoformat()
        operation_id = uuid.uuid4().hex
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO branch_operations
                   (id, idempotency_key, requester, channel, project, branch, base,
                    status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)""",
                (
                    operation_id,
                    idempotency_key,
                    requester,
                    channel,
                    project,
                    branch,
                    base,
                    now,
                    now,
                ),
            )
            if cursor.rowcount == 1:
                self._audit(
                    connection,
                    operation_id,
                    "branch.planned",
                    requester,
                    {
                        "project": project,
                        "branch": branch,
                        "base": base,
                        "channel": channel,
                    },
                    now,
                )
            row = connection.execute(
                "SELECT * FROM branch_operations WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
        return _row(row)

    def get_branch(self, operation_id: str) -> BranchOperation:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM branch_operations WHERE id = ?", (operation_id,)
            ).fetchone()
        if row is None:
            raise KeyError(operation_id)
        return _row(row)

    def transition_branch(
        self,
        operation_id: str,
        *,
        expected: tuple[str, ...],
        status: str,
        actor: str,
        result_url: str | None = None,
    ) -> BranchOperation:
        placeholders = ",".join("?" for _ in expected)
        now = dt.datetime.now(dt.UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                f"""UPDATE branch_operations SET status = ?, result_url = ?, updated_at = ?
                    WHERE id = ? AND status IN ({placeholders})""",
                (status, result_url, now, operation_id, *expected),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("operation is missing or no longer in the expected state")
            self._audit(
                connection,
                operation_id,
                f"branch.{status}",
                actor,
                {
                    "from": list(expected),
                    "to": status,
                    "result_url": result_url,
                },
                now,
            )
        return self.get_branch(operation_id)

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        operation_id: str,
        event_type: str,
        actor: str,
        details: dict[str, object],
        timestamp: str,
    ) -> None:
        connection.execute(
            """INSERT INTO operation_audit
               (timestamp, operation_id, event_type, actor, details_json)
               VALUES (?, ?, ?, ?, ?)""",
            (timestamp, operation_id, event_type, actor, json.dumps(details, sort_keys=True)),
        )


def _row(row: sqlite3.Row) -> BranchOperation:
    return BranchOperation(
        **{field.name: row[field.name] for field in dataclasses.fields(BranchOperation)}
    )
