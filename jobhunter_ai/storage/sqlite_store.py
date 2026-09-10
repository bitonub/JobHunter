from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from ..models import Job
from .base import (
    JobStateKey,
    JobStateStatus,
    JobStateStore,
    StoredJobState,
    build_job_state_key,
)


class SQLiteJobStateStore(JobStateStore):
    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = str(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS job_state (
                identifier_hash TEXT NOT NULL,
                source TEXT NOT NULL,
                link_hash TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('visto', 'descartado', 'revisable', 'compatible', 'alertado')
                ),
                score REAL,
                PRIMARY KEY (identifier_hash, source, link_hash)
            )
            """
        )
        self._connection.commit()

    def get(self, job: Job) -> StoredJobState | None:
        key = build_job_state_key(job)
        row = self._connection.execute(
            """
            SELECT identifier_hash, source, link_hash, first_seen, last_seen, status, score
            FROM job_state
            WHERE identifier_hash = ? AND source = ? AND link_hash = ?
            """,
            (key.identifier_hash, key.source, key.link_hash),
        ).fetchone()
        return self._from_row(row) if row is not None else None

    def record(
        self,
        job: Job,
        status: JobStateStatus | str,
        score: float | None = None,
    ) -> StoredJobState:
        return self._record(job, status, score, allow_alerted=False)

    def mark_alerted(
        self,
        job: Job,
        score: float | None = None,
    ) -> StoredJobState:
        return self._record(job, JobStateStatus.ALERTED, score, allow_alerted=True)

    def _record(
        self,
        job: Job,
        status: JobStateStatus | str,
        score: float | None,
        *,
        allow_alerted: bool,
    ) -> StoredJobState:
        key = build_job_state_key(job)
        status_value = status.value if isinstance(status, JobStateStatus) else str(status)
        allowed_statuses = {item.value for item in JobStateStatus}
        if status_value not in allowed_statuses:
            raise ValueError(f"unsupported job state: {status_value}")
        if status_value == JobStateStatus.ALERTED.value and not allow_alerted:
            raise ValueError("use mark_alerted() only after a successful alert delivery")
        now = self._clock().astimezone(timezone.utc).isoformat()
        self._connection.execute(
            """
            INSERT INTO job_state (
                identifier_hash, source, link_hash, first_seen, last_seen, status, score
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(identifier_hash, source, link_hash) DO UPDATE SET
                last_seen = excluded.last_seen,
                status = excluded.status,
                score = excluded.score
            """,
            (
                key.identifier_hash,
                key.source,
                key.link_hash,
                now,
                now,
                status_value,
                float(score) if score is not None else None,
            ),
        )
        self._connection.commit()
        state = self.get(job)
        if state is None:
            raise RuntimeError("failed to persist job state")
        return state

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StoredJobState:
        return StoredJobState(
            key=JobStateKey(
                identifier_hash=row["identifier_hash"],
                source=row["source"],
                link_hash=row["link_hash"],
            ),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            status=row["status"],
            score=row["score"],
        )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteJobStateStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
