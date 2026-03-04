from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "runs" / "agent_eval.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRecord:
    id: str
    status: str
    payload: dict[str, Any]
    raw_output: Optional[str]
    eval_result: Optional[dict[str, Any]]
    created_at: str
    updated_at: str
    error: Optional[str]


class JobStore:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    raw_output TEXT,
                    eval_result TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT
                )
                """
            )

    def create_job(self, job_id: str, payload: dict[str, Any]) -> JobRecord:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, status, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, "queued", json.dumps(payload), now, now),
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> JobRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _row_to_job(row)

    def fetch_next_job(self) -> Optional[JobRecord]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                ("running", _utc_now(), row["id"]),
            )
        return _row_to_job(row)

    def complete_job(
        self,
        job_id: str,
        raw_output: str,
        eval_result: Optional[dict[str, Any]],
        error: Optional[str] = None,
    ) -> JobRecord:
        status = "completed" if error is None else "failed"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, raw_output = ?, eval_result = ?, updated_at = ?, error = ?
                WHERE id = ?
                """,
                (
                    status,
                    raw_output,
                    json.dumps(eval_result) if eval_result else None,
                    _utc_now(),
                    error,
                    job_id,
                ),
            )
        return self.get_job(job_id)


def _row_to_job(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        id=row["id"],
        status=row["status"],
        payload=json.loads(row["payload"]),
        raw_output=row["raw_output"],
        eval_result=json.loads(row["eval_result"]) if row["eval_result"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error=row["error"],
    )
