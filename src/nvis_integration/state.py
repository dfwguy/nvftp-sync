"""SQLite audit log and idempotent job state."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import pathlib
import sqlite3
import uuid

from .models import ImportRequest


@dataclasses.dataclass(frozen=True)
class Job:
    id: str
    idempotency_key: str
    requester: str
    channel: str
    source: str
    artifact: str
    target: str
    status: str
    result_url: str | None
    error: str | None


@dataclasses.dataclass(frozen=True)
class AuditEvent:
    sequence: int
    timestamp: str
    job_id: str
    event_type: str
    actor: str
    details: dict[str, object]
    previous_hash: str
    event_hash: str


class JobStore:
    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    requester TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    source TEXT NOT NULL,
                    artifact TEXT NOT NULL,
                    target TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_url TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS audit_events_job ON audit_events(job_id, sequence)"
            )

    def create(
        self,
        request: ImportRequest,
        *,
        requester: str,
        channel: str,
        idempotency_key: str,
    ) -> Job:
        now = dt.datetime.now(dt.UTC).isoformat()
        job_id = uuid.uuid4().hex
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO jobs
                (id, idempotency_key, requester, channel, source, artifact, target,
                 status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?)
                """,
                (
                    job_id,
                    idempotency_key,
                    requester,
                    channel,
                    request.source,
                    request.artifact,
                    request.target,
                    now,
                    now,
                ),
            )
            if cursor.rowcount == 1:
                self._append_event(
                    connection,
                    job_id=job_id,
                    event_type="job.created",
                    actor=requester,
                    details={
                        "channel": channel,
                        "source": request.source,
                        "artifact": request.artifact,
                        "target": request.target,
                        "idempotency_key": idempotency_key,
                    },
                    timestamp=now,
                )
            row = connection.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
        return _row_to_job(row)

    def get(self, job_id: str) -> Job:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _row_to_job(row)

    def transition(
        self,
        job_id: str,
        *,
        expected: tuple[str, ...],
        status: str,
        result_url: str | None = None,
        error: str | None = None,
        actor: str = "system",
        details: dict[str, object] | None = None,
    ) -> Job:
        placeholders = ",".join("?" for _ in expected)
        now = dt.datetime.now(dt.UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                f"""UPDATE jobs SET status = ?, result_url = ?, error = ?, updated_at = ?
                    WHERE id = ? AND status IN ({placeholders})""",
                (status, result_url, error, now, job_id, *expected),
            )
            if cursor.rowcount != 1:
                current = connection.execute(
                    "SELECT status FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
                actual = current["status"] if current else "missing"
                raise RuntimeError(f"job {job_id} is {actual}, expected one of {expected}")
            self._append_event(
                connection,
                job_id=job_id,
                event_type=f"job.{status}",
                actor=actor,
                details={
                    "from": list(expected),
                    "to": status,
                    "result_url": result_url,
                    "error": error,
                    **(details or {}),
                },
                timestamp=now,
            )
        return self.get(job_id)

    def events(self, job_id: str | None = None) -> list[AuditEvent]:
        query = "SELECT * FROM audit_events"
        parameters: tuple[str, ...] = ()
        if job_id is not None:
            query += " WHERE job_id = ?"
            parameters = (job_id,)
        query += " ORDER BY sequence"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            AuditEvent(
                sequence=row["sequence"],
                timestamp=row["timestamp"],
                job_id=row["job_id"],
                event_type=row["event_type"],
                actor=row["actor"],
                details=json.loads(row["details_json"]),
                previous_hash=row["previous_hash"],
                event_hash=row["event_hash"],
            )
            for row in rows
        ]

    def verify_audit_chain(self) -> tuple[bool, int]:
        previous_hash = "0" * 64
        events = self.events()
        for event in events:
            expected = _event_hash(
                previous_hash,
                event.timestamp,
                event.job_id,
                event.event_type,
                event.actor,
                event.details,
            )
            if event.previous_hash != previous_hash or event.event_hash != expected:
                return False, event.sequence
            previous_hash = event.event_hash
        return True, len(events)

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        job_id: str,
        event_type: str,
        actor: str,
        details: dict[str, object],
        timestamp: str,
    ) -> None:
        row = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = str(row["event_hash"]) if row else "0" * 64
        event_hash = _event_hash(
            previous_hash, timestamp, job_id, event_type, actor, details
        )
        connection.execute(
            """
            INSERT INTO audit_events
            (timestamp, job_id, event_type, actor, details_json, previous_hash, event_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                job_id,
                event_type,
                actor,
                json.dumps(details, sort_keys=True, separators=(",", ":")),
                previous_hash,
                event_hash,
            ),
        )


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(**{field.name: row[field.name] for field in dataclasses.fields(Job)})


def _event_hash(
    previous_hash: str,
    timestamp: str,
    job_id: str,
    event_type: str,
    actor: str,
    details: dict[str, object],
) -> str:
    canonical = json.dumps(details, sort_keys=True, separators=(",", ":"))
    payload = f"{previous_hash}\0{timestamp}\0{job_id}\0{event_type}\0{actor}\0{canonical}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
