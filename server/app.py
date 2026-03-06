from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException

from core.evaluator import EvaluationResult
from server.db import JobStore
from server.evaluate import evaluate_live_run
from server.ground_truth import fetch_evidence
from server.models import (
    CompleteJobPayload,
    CreateJobPayload,
    JobAssignment,
    JobResponse,
    RunResultPayload,
)


app = FastAPI(title="AgentEval API", version="v0")
store = JobStore()


def _require_connector_token(authorization: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("AGENTEVAL_CONNECTOR_TOKEN")
    if not expected:
        raise HTTPException(status_code=500, detail="Connector token not configured.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing connector token.")
    token = authorization.split("Bearer ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid connector token.")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/jobs", response_model=JobResponse)
def create_job(payload: CreateJobPayload) -> JobResponse:
    job_id = str(uuid.uuid4())
    record = store.create_job(job_id, payload.model_dump())
    return JobResponse(
        id=record.id,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@app.get("/v1/jobs/next", response_model=JobAssignment)
def next_job(_: None = Depends(_require_connector_token)) -> JobAssignment:
    record = store.fetch_next_job()
    if not record:
        raise HTTPException(status_code=204, detail="No jobs queued.")
    return JobAssignment(id=record.id, payload=CreateJobPayload(**record.payload))


@app.post("/v1/jobs/{job_id}/complete")
def complete_job(
    job_id: str,
    payload: CompleteJobPayload,
    _: None = Depends(_require_connector_token),
) -> RunResultPayload:
    record = store.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found.")

    evidence = fetch_evidence(record.payload)
    eval_result, status = evaluate_live_run(
        job_id=job_id,
        payload=record.payload,
        raw_output=payload.raw_output,
        evidence=evidence,
    )
    eval_payload = _serialize_eval_result(eval_result, status)
    stored = store.complete_job(
        job_id,
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


@app.get("/v1/runs/{job_id}", response_model=RunResultPayload)
def get_run(job_id: str) -> RunResultPayload:
    try:
        record = store.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found.")
    return RunResultPayload(
        eval_result=record.eval_result,
        raw_output=record.raw_output,
        status=record.status,
        error=record.error,
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
