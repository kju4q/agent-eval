from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "runs" / "agent_eval.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRecord:
    id: str
    session_id: Optional[str]
    status: str
    payload: dict[str, Any]
    raw_output: Optional[str]
    eval_result: Optional[dict[str, Any]]
    created_at: str
    updated_at: str
    error: Optional[str]


@dataclass
class SessionRecord:
    id: str
    token_hash: str
    created_at: str
    updated_at: str
    expires_at: str
    max_evals: int
    evals_used: int
    revoked: bool


@dataclass
class FeedbackRecord:
    id: str
    session_id: str
    run_id: str
    category: str
    message: str
    created_at: str


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
                    session_id TEXT,
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    max_evals INTEGER NOT NULL,
                    evals_used INTEGER NOT NULL DEFAULT 0,
                    revoked INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ip_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_usage (
                    provider TEXT NOT NULL,
                    usage_day TEXT NOT NULL,
                    calls INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, usage_day)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_spend (
                    provider TEXT NOT NULL,
                    usage_day TEXT NOT NULL,
                    usd_total REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, usage_day)
                )
                """
            )

            columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "session_id" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN session_id TEXT")

    def create_session(self, *, ttl_seconds: int, max_evals: int) -> tuple[SessionRecord, str]:
        session_id = secrets.token_hex(16)
        raw_token = secrets.token_hex(32)  # 256-bit
        token_hash = _hash_token(raw_token)
        now = _utc_now()
        expires_at = _future_iso(ttl_seconds)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, token_hash, created_at, updated_at, expires_at, max_evals, evals_used, revoked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, token_hash, now, now, expires_at, int(max_evals), 0, 0),
            )
        return self.get_session(session_id), raw_token

    def get_session(self, session_id: str) -> SessionRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(session_id)
        return _row_to_session(row)

    def get_session_by_token(self, token: str) -> Optional[SessionRecord]:
        token_hash = _hash_token(token)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE token_hash = ?", (token_hash,)).fetchone()
        if row is None:
            return None
        return _row_to_session(row)

    def revoke_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET revoked = 1, updated_at = ? WHERE id = ?",
                (_utc_now(), session_id),
            )

    def consume_eval_quota(self, session_id: str) -> bool:
        session = self.get_session(session_id)
        if session.revoked:
            return False
        if _parse_iso(session.expires_at) <= datetime.now(timezone.utc):
            return False
        if session.evals_used >= session.max_evals:
            return False
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET evals_used = evals_used + 1, updated_at = ?
                WHERE id = ? AND revoked = 0 AND evals_used < max_evals
                """,
                (_utc_now(), session_id),
            )
        return True

    def create_job(self, job_id: str, session_id: str, payload: dict[str, Any]) -> JobRecord:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, session_id, status, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, session_id, "queued", json.dumps(payload), now, now),
            )
        return self.get_job(job_id, session_id=session_id)

    def get_job(self, job_id: str, *, session_id: Optional[str] = None) -> JobRecord:
        with self._connect() as conn:
            if session_id is None:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM jobs WHERE id = ? AND session_id = ?",
                    (job_id, session_id),
                ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _row_to_job(row)

    def fetch_next_job(self, session_id: str) -> Optional[JobRecord]:
        self.mark_stale_running()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'queued' AND session_id = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                ("running", _utc_now(), row["id"]),
            )
        return self.get_job(row["id"], session_id=session_id)

    def mark_stale_running(self) -> int:
        now = datetime.now(timezone.utc)
        updated_rows = 0
        with self._connect() as conn:
            rows = conn.execute("SELECT id, payload, updated_at FROM jobs WHERE status = 'running'").fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                timeout_s = _parse_timeout(payload.get("timeout_s"))
                max_age_s = max(900.0, timeout_s + 120.0)
                updated_at = _parse_iso(row["updated_at"])
                if (now - updated_at).total_seconds() > max_age_s:
                    conn.execute(
                        """
                        UPDATE jobs
                        SET status = ?, updated_at = ?, error = ?
                        WHERE id = ?
                        """,
                        ("failed", _utc_now(), "stale-running-timeout", row["id"]),
                    )
                    updated_rows += 1
        return updated_rows

    def complete_job(
        self,
        job_id: str,
        session_id: str,
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
                WHERE id = ? AND session_id = ?
                """,
                (
                    status,
                    raw_output,
                    json.dumps(eval_result) if eval_result else None,
                    _utc_now(),
                    error,
                    job_id,
                    session_id,
                ),
            )
        return self.get_job(job_id, session_id=session_id)

    def list_runs_for_session(self, session_id: str, limit: int = 50) -> list[JobRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
        return [_row_to_job(row) for row in rows]

    def add_feedback(
        self,
        *,
        feedback_id: str,
        session_id: str,
        run_id: str,
        category: str,
        message: str,
    ) -> FeedbackRecord:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feedback (id, session_id, run_id, category, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (feedback_id, session_id, run_id, category, message, now),
            )
            row = conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
        if row is None:
            raise KeyError(feedback_id)
        return _row_to_feedback(row)

    def list_feedback_for_session(self, session_id: str, limit: int = 50) -> list[FeedbackRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM feedback
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, int(limit)),
            ).fetchall()
        return [_row_to_feedback(row) for row in rows]

    def count_feedback_since(self, session_id: str, since_iso: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c FROM feedback
                WHERE session_id = ? AND created_at >= ?
                """,
                (session_id, since_iso),
            ).fetchone()
        if not row:
            return 0
        return int(row["c"])

    def record_ip_request(self, ip: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO ip_requests (ip, created_at) VALUES (?, ?)",
                (ip, _utc_now()),
            )

    def count_ip_requests_since(self, ip: str, since_iso: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c FROM ip_requests
                WHERE ip = ? AND created_at >= ?
                """,
                (ip, since_iso),
            ).fetchone()
        if not row:
            return 0
        return int(row["c"])

    def get_provider_calls(self, provider: str, usage_day: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT calls FROM provider_usage
                WHERE provider = ? AND usage_day = ?
                """,
                (provider, usage_day),
            ).fetchone()
        if not row:
            return 0
        return int(row["calls"])

    def increment_provider_calls(self, provider: str, usage_day: str, amount: int = 1) -> int:
        amount = max(1, int(amount))
        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT calls FROM provider_usage
                WHERE provider = ? AND usage_day = ?
                """,
                (provider, usage_day),
            ).fetchone()
            if existing is None:
                calls = amount
                conn.execute(
                    """
                    INSERT INTO provider_usage (provider, usage_day, calls, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (provider, usage_day, calls, now),
                )
            else:
                calls = int(existing["calls"]) + amount
                conn.execute(
                    """
                    UPDATE provider_usage
                    SET calls = ?, updated_at = ?
                    WHERE provider = ? AND usage_day = ?
                    """,
                    (calls, now, provider, usage_day),
                )
        return calls

    def get_provider_spend_usd(self, provider: str, usage_day: str) -> float:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT usd_total FROM provider_spend
                WHERE provider = ? AND usage_day = ?
                """,
                (provider, usage_day),
            ).fetchone()
        if not row:
            return 0.0
        return float(row["usd_total"])

    def increment_provider_spend_usd(self, provider: str, usage_day: str, amount_usd: float) -> float:
        amount_usd = max(0.0, float(amount_usd))
        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT usd_total FROM provider_spend
                WHERE provider = ? AND usage_day = ?
                """,
                (provider, usage_day),
            ).fetchone()
            if existing is None:
                total = amount_usd
                conn.execute(
                    """
                    INSERT INTO provider_spend (provider, usage_day, usd_total, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (provider, usage_day, total, now),
                )
            else:
                total = float(existing["usd_total"]) + amount_usd
                conn.execute(
                    """
                    UPDATE provider_spend
                    SET usd_total = ?, updated_at = ?
                    WHERE provider = ? AND usage_day = ?
                    """,
                    (total, now, provider, usage_day),
                )
        return total


def _row_to_job(row: sqlite3.Row) -> JobRecord:
    keys = row.keys()
    return JobRecord(
        id=row["id"],
        session_id=row["session_id"] if "session_id" in keys else None,
        status=row["status"],
        payload=json.loads(row["payload"]),
        raw_output=row["raw_output"],
        eval_result=json.loads(row["eval_result"]) if row["eval_result"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error=row["error"],
    )


def _row_to_session(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        id=row["id"],
        token_hash=row["token_hash"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
        max_evals=int(row["max_evals"]),
        evals_used=int(row["evals_used"]),
        revoked=bool(row["revoked"]),
    )


def _row_to_feedback(row: sqlite3.Row) -> FeedbackRecord:
    return FeedbackRecord(
        id=row["id"],
        session_id=row["session_id"],
        run_id=row["run_id"],
        category=row["category"],
        message=row["message"],
        created_at=row["created_at"],
    )


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _parse_timeout(value: Any) -> float:
    try:
        parsed = float(value)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return 600.0


def _future_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=float(seconds))).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
