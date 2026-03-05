from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

import httpx

from core.schema import EvidenceItem


APPLE_BASE = "https://www.apple.com"
APPLE_SEARCH = "https://www.apple.com/shop/search/{query}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_apple_evidence(query: str) -> list[EvidenceItem]:
    search_url = APPLE_SEARCH.format(query=quote_plus(_normalize_query(query)))
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            resp = client.get(search_url)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPError:
        return []

    product_url = _extract_product_url(html)
    if not product_url:
        return []

    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            resp = client.get(product_url)
            resp.raise_for_status()
            product_html = resp.text
    except httpx.HTTPError:
        return []

    price = _extract_price(product_html)
    availability = "Available" if "Add to Bag" in product_html else None
    listing_id = _extract_listing_id(product_url)
    variant_match = _maybe_variant_match(query, product_html)

    return [
        EvidenceItem(
            retailer="Apple",
            url=product_url,
            price_usd=price,
            availability=availability,
            seller="Apple",
            timestamp=_utc_now(),
            variant_match=variant_match,
            listing_id=listing_id,
            listing_id_type="apple_sku" if listing_id else None,
            notes="source=apple_scrape;confidence=0.6",
            source_type="scraped",
            confidence=0.6,
        )
    ]


def _extract_product_url(html: str) -> str | None:
    matches = re.findall(r"/shop/product/[^\"'\\s>]+", html)
    if not matches:
        return None
    path = matches[0]
    return f"{APPLE_BASE}{path}"


def _extract_price(html: str) -> float | None:
    match = re.search(r"\\$\\s?([0-9]+(?:\\.[0-9]{2})?)", html)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_listing_id(url: str) -> str | None:
    match = re.search(r"/shop/product/([^/]+)/", url)
    return match.group(1) if match else None


def _maybe_variant_match(query: str, html: str) -> bool | None:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return None
    return all(token in html.lower() for token in query_tokens[:3])


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _normalize_query(value: str) -> str:
    tokens = _tokenize(value)
    if not tokens:
        return value
    return " ".join(tokens)
