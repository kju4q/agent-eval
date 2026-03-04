from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TaskRulesPayload(BaseModel):
    allow_third_party: bool = False
    allow_refurbished: bool = False
    require_full_set: bool = True


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


class JobResponse(BaseModel):
    id: str
    status: str
    created_at: str
    updated_at: str


class JobAssignment(BaseModel):
    id: str
    payload: CreateJobPayload


class CompleteJobPayload(BaseModel):
    raw_output: str
    error: Optional[str] = None


class RunResultPayload(BaseModel):
    eval_result: Optional[dict]
    raw_output: Optional[str]
    status: str
    error: Optional[str]
