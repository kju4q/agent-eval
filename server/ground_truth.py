from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from core.schema import EvidenceItem


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_evidence(payload: dict) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []

    product_name = payload.get("product_name")
    if not product_name:
        return evidence

    allowed = {r.lower() for r in payload.get("allowed_retailers", [])}

    if "best buy" in allowed or "bestbuy" in allowed:
        evidence.extend(_fetch_bestbuy(product_name))

    # Placeholder for Amazon/Apple integrations (DataForSEO, etc.)
    return evidence


def _fetch_bestbuy(query: str) -> list[EvidenceItem]:
    api_key = os.getenv("BESTBUY_API_KEY")
    if not api_key:
        return []

    url = "https://api.bestbuy.com/v1/products((search={query}))"
    params = {
        "apiKey": api_key,
        "format": "json",
        "show": "name,sku,price,onlineAvailability,url",
        "pageSize": 5,
    }
    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.get(url.format(query=query), params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return []
    except ValueError:
        return []

    results = []
    for item in data.get("products", []):
        results.append(
            EvidenceItem(
                retailer="Best Buy",
                url=item.get("url") or "",
                price_usd=item.get("price"),
                availability="In Stock" if item.get("onlineAvailability") else "Unavailable",
                seller="Best Buy",
                timestamp=_utc_now(),
                variant_match=None,
                listing_id=str(item.get("sku")) if item.get("sku") else None,
                listing_id_type="sku" if item.get("sku") else None,
                notes="source=bestbuy_api;confidence=0.9",
                source_type="verified-retailer",
                confidence=0.9,
            )
        )
    return results
