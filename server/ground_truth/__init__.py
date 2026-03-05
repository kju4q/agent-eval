from __future__ import annotations

from typing import Iterable

from core.schema import EvidenceItem

from server.ground_truth.apple import fetch_apple_evidence
from server.ground_truth.bestbuy import fetch_bestbuy_evidence
from server.ground_truth.dataforseo_amazon import fetch_amazon_evidence


def fetch_evidence(payload: dict) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    product_name = payload.get("product_name")
    if not product_name:
        return evidence

    allowed = {retailer.lower() for retailer in payload.get("allowed_retailers", [])}

    if _allows(allowed, "best buy", "bestbuy"):
        evidence.extend(fetch_bestbuy_evidence(product_name))
    if _allows(allowed, "apple"):
        evidence.extend(fetch_apple_evidence(product_name))
    if _allows(allowed, "amazon"):
        evidence.extend(fetch_amazon_evidence(product_name))

    return list(_dedupe(evidence))


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
