from __future__ import annotations

import os
from datetime import datetime, timezone
import re

import httpx

from core.schema import EvidenceItem


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_bestbuy_evidence(query: str) -> list[EvidenceItem]:
    api_key = os.getenv("BESTBUY_API_KEY")
    if not api_key:
        return []

    query = _normalize_query(query)
    url = "https://api.bestbuy.com/v1/products((search={query}))"
    params = {
        "apiKey": api_key,
        "format": "json",
        "show": "name,sku,salePrice,regularPrice,onlineAvailability,url",
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
                variant_match=_variant_match(query, name),
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


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _normalize_query(value: str) -> str:
    tokens = _tokenize(value)
    if not tokens:
        return value
    return " ".join(tokens)
