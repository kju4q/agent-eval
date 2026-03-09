from __future__ import annotations

import logging
import os
from urllib.parse import quote_plus

import httpx

from core.schema import EvidenceItem
from server.ground_truth.safe_http import EgressPolicyError, safe_request
from server.ground_truth.utils import _normalize_query, _tokenize, _utc_now

LOGGER = logging.getLogger("agenteval.ground_truth")
BESTBUY_ALLOWED_HOSTS = {"api.bestbuy.com"}


def fetch_bestbuy_evidence(query: str) -> list[EvidenceItem]:
    api_key = os.getenv("BESTBUY_API_KEY")
    if not api_key:
        return []

    normalized = _normalize_query(query)
    search_value = f"\"{normalized}\"" if normalized else ""
    query = quote_plus(search_value)
    url = "https://api.bestbuy.com/v1/products((search={query}))"
    params = {
        "apiKey": api_key,
        "format": "json",
        "show": "name,sku,salePrice,regularPrice,onlineAvailability,url",
        "pageSize": 5,
    }
    try:
        with httpx.Client(timeout=12.0) as client:
            resp = safe_request(
                client,
                "GET",
                url.format(query=query),
                allowed_hosts=BESTBUY_ALLOWED_HOSTS,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
    except EgressPolicyError as exc:
        LOGGER.warning("Best Buy API egress blocked: %s", exc)
        return []
    except httpx.HTTPError as exc:
        LOGGER.warning("Best Buy API request failed: %s", exc)
        return []
    except ValueError as exc:
        LOGGER.warning("Best Buy API returned invalid JSON: %s", exc)
        return []

    results = []
    for item in data.get("products", []):
        price = item.get("salePrice")
        if price is None:
            price = item.get("regularPrice")
        name = item.get("name") or ""
        results.append(
            EvidenceItem(
                retailer="Best Buy",
                url=item.get("url") or "",
                price_usd=price,
                availability="In Stock" if item.get("onlineAvailability") else "Unavailable",
                seller="Best Buy",
                timestamp=_utc_now(),
                variant_match=_variant_match(normalized, name),
                listing_id=str(item.get("sku")) if item.get("sku") else None,
                listing_id_type="sku" if item.get("sku") else None,
                notes=f"source=bestbuy_api;confidence=0.9;name={name}",
                source_type="verified-retailer",
                confidence=0.9,
            )
        )
    return results


def _variant_match(query: str, name: str) -> bool | None:
    query_tokens = [token for token in _tokenize(query) if len(token) > 1]
    if not query_tokens:
        return None
    name_tokens = set(_tokenize(name))
    return all(token in name_tokens for token in query_tokens[:4])
