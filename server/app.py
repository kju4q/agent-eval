from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.evaluator import EvaluationResult
from server.db import JobStore, SessionRecord
from server.evaluate import evaluate_live_run
from server.ground_truth import fetch_evidence_with_status
from server.models import (
    CompleteJobPayload,
    CreateJobPayload,
    FeedbackCreatePayload,
    FeedbackResponse,
    JobAssignment,
    JobResponse,
    RunResultPayload,
    RunSummaryPayload,
    SessionCreatePayload,
    SessionResponse,
    SessionStatusResponse,
)


app = FastAPI(title="AgentEval API", version="v0", debug=False)
store = JobStore()
LOGGER = logging.getLogger("agenteval.api")

allowed_origins = [item.strip() for item in os.getenv("AGENTEVAL_ALLOWED_ORIGINS", "http://localhost:8501").split(",") if item.strip()]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-AgentEval-Bootstrap", "X-Forwarded-For", "X-Real-IP"],
    )


def _extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing session token.")
    token = authorization.split("Bearer ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing session token.")
    return token


def _is_session_expired(session: SessionRecord) -> bool:
    expires_at = session.expires_at
    if expires_at.endswith("Z"):
        expires_at = expires_at[:-1] + "+00:00"
    return datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc)


def _require_active_session(authorization: Optional[str] = Header(default=None)) -> SessionRecord:
    token = _extract_bearer_token(authorization)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session = store.get_session_by_token(token)
    if session is None:
        raise HTTPException(status_code=403, detail="Invalid session token.")
    if not hmac.compare_digest(token_hash, session.token_hash):
        raise HTTPException(status_code=403, detail="Invalid session token.")
    if session.revoked:
        raise HTTPException(status_code=403, detail="Session revoked.")
    if _is_session_expired(session):
        raise HTTPException(status_code=403, detail="Session expired.")
    return session


def _extract_client_ip(
    request: Optional[Request],
    x_forwarded_for: Optional[str],
    x_real_ip: Optional[str],
) -> str:
    if x_forwarded_for:
        # Use first hop only
        return x_forwarded_for.split(",")[0].strip()
    if x_real_ip:
        return x_real_ip.strip()
    if request is None:
        return "unknown"
    client = request.client
    return client.host if client else "unknown"


def _require_session_bootstrap(x_agenteval_bootstrap: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("AGENTEVAL_SESSION_BOOTSTRAP_TOKEN")
    if not expected:
        return
    if not x_agenteval_bootstrap:
        raise HTTPException(status_code=401, detail="Missing bootstrap token.")
    # compare_digest only makes sense with fixed-size data
    if not secrets.compare_digest(x_agenteval_bootstrap, expected):
        raise HTTPException(status_code=403, detail="Invalid bootstrap token.")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/healthz")
def v1_healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled server error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.post("/v1/sessions", response_model=SessionResponse)
def create_session(
    payload: SessionCreatePayload,
    _: None = Depends(_require_session_bootstrap),
) -> SessionResponse:
    session, session_token = store.create_session(
        ttl_seconds=payload.ttl_seconds,
        max_evals=payload.max_evals,
    )
    return SessionResponse(
        session_id=session.id,
        session_token=session_token,
        expires_at=session.expires_at,
        max_evals=session.max_evals,
        evals_used=session.evals_used,
    )


@app.get("/v1/sessions/me", response_model=SessionStatusResponse)
def session_status(session: SessionRecord = Depends(_require_active_session)) -> SessionStatusResponse:
    return SessionStatusResponse(
        session_id=session.id,
        expires_at=session.expires_at,
        max_evals=session.max_evals,
        evals_used=session.evals_used,
        revoked=session.revoked,
    )


@app.post("/v1/jobs", response_model=JobResponse)
def create_job(
    payload: CreateJobPayload,
    session: SessionRecord = Depends(_require_active_session),
    request: Request = None,
    x_forwarded_for: Optional[str] = Header(default=None),
    x_real_ip: Optional[str] = Header(default=None),
) -> JobResponse:
    max_prompt_bytes = int(os.getenv("AGENTEVAL_MAX_PROMPT_BYTES", "32768"))
    if len(payload.prompt.encode("utf-8")) > max_prompt_bytes:
        raise HTTPException(status_code=413, detail=f"Prompt exceeds {max_prompt_bytes} bytes.")

    ip_window_seconds = int(os.getenv("AGENTEVAL_IP_WINDOW_SECONDS", "60"))
    ip_max_jobs = int(os.getenv("AGENTEVAL_IP_MAX_JOBS_PER_WINDOW", "20"))
    client_ip = _extract_client_ip(request, x_forwarded_for, x_real_ip)
    since = (datetime.now(timezone.utc) - timedelta(seconds=ip_window_seconds)).isoformat()
    if store.count_ip_requests_since(client_ip, since) >= ip_max_jobs:
        raise HTTPException(status_code=429, detail="IP job creation rate limit exceeded.")
    store.record_ip_request(client_ip)

    if not store.consume_eval_quota(session.id):
        raise HTTPException(status_code=429, detail="Session eval quota exceeded or session expired.")

    job_id = str(uuid.uuid4())
    record = store.create_job(job_id, session.id, payload.model_dump())
    return JobResponse(
        id=record.id,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@app.get("/v1/jobs/next", response_model=JobAssignment)
def next_job(session: SessionRecord = Depends(_require_active_session)) -> JobAssignment:
    record = store.fetch_next_job(session.id)
    if not record:
        raise HTTPException(status_code=204, detail="No jobs queued.")
    return JobAssignment(id=record.id, payload=CreateJobPayload(**record.payload))


@app.post("/v1/jobs/{job_id}/complete")
def complete_job(
    job_id: str,
    payload: CompleteJobPayload,
    session: SessionRecord = Depends(_require_active_session),
) -> RunResultPayload:
    try:
        record = store.get_job(job_id, session_id=session.id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found.")

    if record.status in {"completed", "failed"}:
        return RunResultPayload(
            eval_result=record.eval_result,
            raw_output=record.raw_output,
            status=record.status,
            error=record.error,
        )
    if record.status != "running":
        raise HTTPException(status_code=409, detail=f"Job is in invalid state: {record.status}")

    ground_truth = fetch_evidence_with_status(record.payload)
    eval_result, status = evaluate_live_run(
        job_id=job_id,
        payload=record.payload,
        raw_output=payload.raw_output,
        evidence=ground_truth.evidence,
    )
    eval_payload = _serialize_eval_result(eval_result, status)
    eval_payload["evidence_degraded"] = ground_truth.degraded
    eval_payload["provider_status"] = [item.as_dict() for item in ground_truth.provider_status]
    if status == "insufficient-evidence":
        eval_payload["evidence_status"] = "degraded" if ground_truth.degraded else "insufficient"
    stored = store.complete_job(
        job_id,
        session.id,
        raw_output=payload.raw_output,
        eval_result=eval_payload,
        error=payload.error,
    )

    return RunResultPayload(
        eval_result=stored.eval_result,
        raw_output=stored.raw_output,
        status=stored.status,
        error=stored.error,
    )


@app.get("/v1/runs", response_model=list[RunSummaryPayload])
def list_runs(
    limit: int = 50,
    session: SessionRecord = Depends(_require_active_session),
) -> list[RunSummaryPayload]:
    records = store.list_runs_for_session(session.id, limit=max(1, min(limit, 200)))
    return [
        RunSummaryPayload(
            id=record.id,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
            error=record.error,
        )
        for record in records
    ]


@app.get("/v1/runs/{job_id}", response_model=RunResultPayload)
def get_run(
    job_id: str,
    session: SessionRecord = Depends(_require_active_session),
) -> RunResultPayload:
    try:
        record = store.get_job(job_id, session_id=session.id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found.")
    return RunResultPayload(
        eval_result=record.eval_result,
        raw_output=record.raw_output,
        status=record.status,
        error=record.error,
    )


@app.post("/v1/feedback", response_model=FeedbackResponse)
def create_feedback(
    payload: FeedbackCreatePayload,
    session: SessionRecord = Depends(_require_active_session),
) -> FeedbackResponse:
    try:
        _ = store.get_job(payload.run_id, session_id=session.id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Run not found for this session.")

    feedback_limit = int(os.getenv("AGENTEVAL_FEEDBACK_PER_DAY", "20"))
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    if store.count_feedback_since(session.id, since) >= feedback_limit:
        raise HTTPException(status_code=429, detail="Feedback rate limit exceeded for this session.")

    feedback = store.add_feedback(
        feedback_id=str(uuid.uuid4()),
        session_id=session.id,
        run_id=payload.run_id,
        category=payload.category,
        message=payload.message.strip(),
    )
    return FeedbackResponse(
        id=feedback.id,
        run_id=feedback.run_id,
        category=feedback.category,
        message=feedback.message,
        created_at=feedback.created_at,
    )


def _serialize_eval_result(
    eval_result: Optional[EvaluationResult],
    status: str,
) -> Optional[dict]:
    if eval_result is None:
        return {"status": status}
    return {
        "status": status,
        "best_first_party_price_usd": eval_result.best_first_party_price_usd,
        "best_first_party_retailer": eval_result.best_first_party_retailer,
        "best_first_party_url": eval_result.best_first_party_url,
        "best_first_party_confidence": eval_result.best_first_party_confidence,
        "best_first_party_source_type": eval_result.best_first_party_source_type,
        "best_first_party_seller": eval_result.best_first_party_seller,
        "agent_chosen_price_usd": eval_result.agent_chosen_price_usd,
        "agent_chosen_retailer": eval_result.agent_chosen_retailer,
        "agent_chosen_url": eval_result.agent_chosen_url,
        "agent_choice_qualified": eval_result.agent_choice_qualified,
        "agent_choice_verified": eval_result.agent_choice_verified,
        "found_best_first_party_price": eval_result.found_best_first_party_price,
        "within_budget": eval_result.within_budget,
        "money_left_on_table_usd": eval_result.money_left_on_table_usd,
        "disputed_price": eval_result.disputed_price,
    }
