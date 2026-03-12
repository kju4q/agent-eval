from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TaskRulesPayload(BaseModel):
    allow_third_party: bool = False
    allow_refurbished: bool = False
    require_full_set: bool = True


class SessionCreatePayload(BaseModel):
    ttl_seconds: int = Field(default=86400, ge=300, le=604800)
    max_evals: int = Field(default=25, ge=1, le=500)


class SessionResponse(BaseModel):
    session_id: str
    session_token: str
    expires_at: str
    max_evals: int
    evals_used: int


class SessionStatusResponse(BaseModel):
    session_id: str
    expires_at: str
    max_evals: int
    evals_used: int
    revoked: bool


class CreateJobPayload(BaseModel):
    product_name: str
    product_variant: Optional[str] = None
    prompt: str
    budget_usd: Optional[float] = None
    currency: str = "USD"
    allowed_retailers: list[str] = Field(default_factory=list)
    rules: TaskRulesPayload = Field(default_factory=TaskRulesPayload)
    agent_id: str = "main"
    source: str = "openclaw"
    timeout_s: Optional[float] = None


class JobResponse(BaseModel):
    id: str
    status: str
    created_at: str
    updated_at: str


class JobAssignment(BaseModel):
    id: str
    payload: CreateJobPayload


class CompleteJobPayload(BaseModel):
    raw_output: str = Field(min_length=0, max_length=200000)
    error: Optional[str] = Field(default=None, max_length=2000)


class RunResultPayload(BaseModel):
    eval_result: Optional[dict]
    raw_output: Optional[str]
    status: str
    error: Optional[str]
    preview_status: Optional[str] = None
    preview_error: Optional[str] = None
    preview_at: Optional[str] = None
    evidence_preview: Optional[list[dict]] = None
    provider_status_preview: Optional[list[dict]] = None
    final_evidence: Optional[list[dict]] = None
    final_provider_status: Optional[list[dict]] = None
    revalidated_at: Optional[str] = None
    revalidation_skipped_reason: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_s: Optional[float] = None


class RunSummaryPayload(BaseModel):
    id: str
    status: str
    created_at: str
    updated_at: str
    error: Optional[str]
    preview_status: Optional[str] = None
    preview_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_s: Optional[float] = None


class FeedbackCreatePayload(BaseModel):
    run_id: str
    category: str = Field(default="general", max_length=64)
    message: str = Field(min_length=1, max_length=2000)


class FeedbackResponse(BaseModel):
    id: str
    run_id: str
    category: str
    message: str
    created_at: str
