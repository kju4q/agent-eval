from __future__ import annotations

import logging
import os
from typing import Iterable

from core.schema import EvidenceItem

from server.ground_truth.apple import fetch_apple_evidence
from server.ground_truth.bestbuy import fetch_bestbuy_evidence
from server.ground_truth.dataforseo_amazon import fetch_amazon_evidence
from server.ground_truth.spend import (
    PROVIDER_DATAFORSEO,
    consume,
    consume_spend_usd,
    current_spend_usd,
    current_usage,
    dataforseo_cost_per_call_usd,
    dataforseo_daily_cap,
    dataforseo_daily_usd_cap,
    is_kill_switch_enabled,
)
from server.ground_truth.types import GroundTruthResult, ProviderFetchStatus

LOGGER = logging.getLogger("agenteval.ground_truth")


def fetch_evidence(payload: dict) -> list[EvidenceItem]:
    return fetch_evidence_with_status(payload).evidence


def fetch_evidence_with_status(payload: dict) -> GroundTruthResult:
    evidence: list[EvidenceItem] = []
    statuses: list[ProviderFetchStatus] = []
    product_name = payload.get("product_name")
    if not product_name:
        return GroundTruthResult(evidence=[], provider_status=[])

    allowed = {retailer.lower() for retailer in payload.get("allowed_retailers", [])}

    if _allows(allowed, "best buy", "bestbuy"):
        api_key = os.getenv("BESTBUY_API_KEY")
        if not api_key:
            statuses.append(
                ProviderFetchStatus(
                    provider="bestbuy",
                    state="disabled",
                    detail="BESTBUY_API_KEY is not configured.",
                )
            )
        else:
            bestbuy_items = fetch_bestbuy_evidence(product_name)
            evidence.extend(bestbuy_items)
            statuses.append(
                ProviderFetchStatus(
                    provider="bestbuy",
                    state="ok" if bestbuy_items else "unavailable",
                    detail=None if bestbuy_items else "No Best Buy evidence returned.",
                )
            )
    if _allows(allowed, "apple"):
        apple_items = fetch_apple_evidence(product_name)
        evidence.extend(apple_items)
        statuses.append(
            ProviderFetchStatus(
                provider="apple",
                state="ok" if apple_items else "unavailable",
                detail=None if apple_items else "No Apple evidence returned.",
            )
        )
    if _allows(allowed, "amazon"):
        login = os.getenv("DATAFORSEO_LOGIN")
        password = os.getenv("DATAFORSEO_PASSWORD")
        cap = dataforseo_daily_cap()
        used = current_usage(PROVIDER_DATAFORSEO)
        spend_cap = dataforseo_daily_usd_cap()
        spend_used = current_spend_usd(PROVIDER_DATAFORSEO)
        est_call_cost = dataforseo_cost_per_call_usd()
        if is_kill_switch_enabled():
            statuses.append(
                ProviderFetchStatus(
                    provider="dataforseo",
                    state="blocked",
                    detail="Evidence kill switch is enabled.",
                    calls_today=used,
                    daily_cap=cap,
                    spend_usd_today=spend_used,
                    daily_spend_cap_usd=spend_cap,
                )
            )
        elif not login or not password:
            statuses.append(
                ProviderFetchStatus(
                    provider="dataforseo",
                    state="disabled",
                    detail="DATAFORSEO_LOGIN/DATAFORSEO_PASSWORD are not configured.",
                    calls_today=used,
                    daily_cap=cap,
                    spend_usd_today=spend_used,
                    daily_spend_cap_usd=spend_cap,
                )
            )
        elif spend_used >= spend_cap:
            statuses.append(
                ProviderFetchStatus(
                    provider="dataforseo",
                    state="blocked",
                    detail="Daily DataForSEO spend cap reached.",
                    calls_today=used,
                    daily_cap=cap,
                    spend_usd_today=spend_used,
                    daily_spend_cap_usd=spend_cap,
                )
            )
        elif used >= cap:
            statuses.append(
                ProviderFetchStatus(
                    provider="dataforseo",
                    state="blocked",
                    detail="Daily DataForSEO call cap reached.",
                    calls_today=used,
                    daily_cap=cap,
                    spend_usd_today=spend_used,
                    daily_spend_cap_usd=spend_cap,
                )
            )
        else:
            amazon_items = fetch_amazon_evidence(product_name)
            used_after = consume(PROVIDER_DATAFORSEO, amount=1)
            spend_after = consume_spend_usd(PROVIDER_DATAFORSEO, est_call_cost)
            if used_after >= int(cap * 0.8):
                LOGGER.warning(
                    "DataForSEO usage near cap: %s/%s calls today.",
                    used_after,
                    cap,
                )
            if spend_after >= (spend_cap * 0.8):
                LOGGER.warning(
                    "DataForSEO spend near cap: $%.4f/$%.4f today.",
                    spend_after,
                    spend_cap,
                )
            evidence.extend(amazon_items)
            statuses.append(
                ProviderFetchStatus(
                    provider="dataforseo",
                    state="ok" if amazon_items else "unavailable",
                    detail=None if amazon_items else "No Amazon evidence returned.",
                    calls_today=used_after,
                    daily_cap=cap,
                    spend_usd_today=spend_after,
                    daily_spend_cap_usd=spend_cap,
                )
            )

    return GroundTruthResult(
        evidence=list(_dedupe(evidence)),
        provider_status=statuses,
    )


def _allows(allowed: set[str], *names: str) -> bool:
    return any(name in allowed for name in names)


def _dedupe(evidence: Iterable[EvidenceItem]) -> Iterable[EvidenceItem]:
    seen: set[tuple[str, str, float | None]] = set()
    for item in evidence:
        key = (item.retailer, item.url, item.price_usd)
        if key in seen:
            continue
        seen.add(key)
        yield item
