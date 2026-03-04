from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from core.evaluator import EvaluationResult, evaluate_case_study
from core.schema import AgentOutput, AgentSpec, CaseStudy, EvidenceItem, TaskRules, TaskSpec


def build_case_study(
    *,
    job_id: str,
    payload: dict,
    raw_output: str,
    evidence: list[EvidenceItem],
) -> CaseStudy:
    now = datetime.now(timezone.utc).isoformat()
    rules_payload = payload.get("rules", {})

    task = TaskSpec(
        product_name=payload["product_name"],
        product_variant=payload.get("product_variant"),
        budget_usd=payload.get("budget_usd"),
        currency=payload.get("currency", "USD"),
        allowed_retailers=payload.get("allowed_retailers", []),
        rules=TaskRules(
            allow_third_party=rules_payload.get("allow_third_party", False),
            allow_refurbished=rules_payload.get("allow_refurbished", False),
            require_full_set=rules_payload.get("require_full_set", True),
        ),
        canonical_listings=[],
    )

    return CaseStudy(
        version="live-v0",
        id=job_id,
        title=payload.get("prompt", "Live Run"),
        created_at=now,
        agent=AgentSpec(name=payload.get("source", "openclaw"), version=None, run_mode="live"),
        task=task,
        agent_output=AgentOutput(
            raw_text=raw_output,
            captured_at=now,
            source=payload.get("source", "openclaw"),
            status="completed",
        ),
        evidence=evidence,
        notes=None,
    )


def evaluate_live_run(
    *,
    job_id: str,
    payload: dict,
    raw_output: str,
    evidence: list[EvidenceItem],
) -> tuple[Optional[EvaluationResult], str]:
    if not evidence:
        return None, "insufficient-evidence"

    case_study = build_case_study(
        job_id=job_id,
        payload=payload,
        raw_output=raw_output,
        evidence=evidence,
    )
    return evaluate_case_study(case_study), "ok"
