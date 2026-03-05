from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from core.schema import EvidenceItem


DATAFORSEO_BASE = "https://api.dataforseo.com/v3"
DEFAULT_LOCATION_CODE = 2840  # United States
DEFAULT_LANGUAGE_CODE = "en_US"
POLL_ATTEMPTS = 20
POLL_SLEEP_S = 3.0


@dataclass(frozen=True)
class AmazonCandidate:
    asin: str
    url: str
    price: float | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_amazon_evidence(query: str) -> list[EvidenceItem]:
    auth_header = _build_auth_header()
    if not auth_header:
        return []

    task_id = _post_products_task(query, auth_header)
    if not task_id:
        return []

    product_payload = _poll_task(f"/merchant/amazon/products/task_get/advanced/{task_id}", auth_header)
    if not product_payload:
        return []

    candidates = _extract_amazon_candidates(product_payload)
    if not candidates:
        return []

    evidence: list[EvidenceItem] = []
    for candidate in candidates[:3]:
        seller_payload = _post_sellers_task(candidate.asin, auth_header)
        if not seller_payload:
            continue
        seller_task_id = seller_payload
        sellers_result = _poll_task(
            f"/merchant/amazon/sellers/task_get/advanced/{seller_task_id}",
            auth_header,
        )
        evidence.extend(_extract_seller_evidence(candidate, sellers_result))

    if evidence:
        return evidence

    # Fallback: no sellers data, emit a single candidate evidence record.
    top = candidates[0]
    return [
        EvidenceItem(
            retailer="Amazon",
            url=top.url,
            price_usd=top.price,
            availability=None,
            seller=None,
            timestamp=_utc_now(),
            variant_match=None,
            listing_id=top.asin,
            listing_id_type="asin",
            notes="source=dataforseo_products;confidence=0.8",
            source_type="aggregator",
            confidence=0.8,
        )
    ]


def _build_auth_header() -> str | None:
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        return None
    token = base64.b64encode(f"{login}:{password}".encode("utf-8")).decode("utf-8")
    return f"Basic {token}"


def _post_products_task(query: str, auth_header: str) -> str | None:
    payload = [
        {
            "keyword": query,
            "location_code": DEFAULT_LOCATION_CODE,
            "language_code": DEFAULT_LANGUAGE_CODE,
            "sort_by": "price_low_to_high",
            "priority": "high",
        }
    ]
    response = _request(
        "POST",
        "/merchant/amazon/products/task_post",
        auth_header,
        json_payload=payload,
    )
    return _extract_task_id(response)


def _post_sellers_task(asin: str, auth_header: str) -> str | None:
    payload = [
        {
            "asin": asin,
            "location_code": DEFAULT_LOCATION_CODE,
            "language_code": DEFAULT_LANGUAGE_CODE,
            "priority": "high",
        }
    ]
    response = _request(
        "POST",
        "/merchant/amazon/sellers/task_post",
        auth_header,
        json_payload=payload,
    )
    return _extract_task_id(response)


def _poll_task(path: str, auth_header: str) -> dict[str, Any] | None:
    response: dict[str, Any] | None = None
    for _ in range(POLL_ATTEMPTS):
        response = _request("GET", path, auth_header)
        if response and _has_results(response):
            return response
        time.sleep(POLL_SLEEP_S)
    return response


def _request(
    method: str,
    path: str,
    auth_header: str,
    json_payload: Any | None = None,
) -> dict[str, Any] | None:
    url = f"{DATAFORSEO_BASE}{path}"
    headers = {"Authorization": auth_header, "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.request(method, url, json=json_payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        return None
    except ValueError:
        return None


def _extract_task_id(response: dict[str, Any] | None) -> str | None:
    if not response:
        return None
    tasks = response.get("tasks") or []
    if not tasks:
        return None
    return tasks[0].get("id")


def _has_results(response: dict[str, Any]) -> bool:
    tasks = response.get("tasks") or []
    if not tasks:
        return False
    result = tasks[0].get("result") or []
    return bool(result)


def _extract_amazon_candidates(response: dict[str, Any]) -> list[AmazonCandidate]:
    items = _find_items(response)
    candidates: list[AmazonCandidate] = []
    for item in items:
        asin = item.get("asin") or item.get("data_asin")
        url = item.get("url")
        if not asin or not url:
            continue
        price = _extract_price(item)
        candidates.append(AmazonCandidate(asin=asin, url=url, price=price))
    return candidates


def _extract_seller_evidence(candidate: AmazonCandidate, response: dict[str, Any] | None) -> list[EvidenceItem]:
    if not response:
        return []
    items = _find_items(response)
    evidence: list[EvidenceItem] = []
    for item in items:
        seller = item.get("seller_name") or item.get("seller") or item.get("seller_title")
        price = _extract_price(item) or candidate.price
        url = item.get("url") or candidate.url
        availability = item.get("availability")
        evidence.append(
            EvidenceItem(
                retailer="Amazon",
                url=url,
                price_usd=price,
                availability=availability,
                seller=seller,
                timestamp=_utc_now(),
                variant_match=None,
                listing_id=candidate.asin,
                listing_id_type="asin",
                notes="source=dataforseo_sellers;confidence=0.8",
                source_type="aggregator",
                confidence=0.8,
            )
        )
    return evidence


def _find_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = response.get("tasks") or []
    if not tasks:
        return []
    result = tasks[0].get("result") or []
    if not result:
        return []
    items = result[0].get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return [item for item in _walk_dicts(result[0]) if "asin" in item or "data_asin" in item]


def _walk_dicts(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _walk_dicts(value)
    elif isinstance(data, list):
        for value in data:
            yield from _walk_dicts(value)


def _extract_price(item: dict[str, Any]) -> float | None:
    for key in ("price", "price_from", "price_current", "current_price"):
        value = item.get(key)
        parsed = _parse_price_value(value)
        if parsed is not None:
            return parsed
    return None


def _parse_price_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("current", "value", "amount", "price"):
            parsed = _parse_price_value(value.get(key))
            if parsed is not None:
                return parsed
    if isinstance(value, str):
        match = re.search(r"([0-9]+(?:\\.[0-9]{2})?)", value.replace(",", ""))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    return None
