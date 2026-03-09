from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

import httpx

from core.schema import EvidenceItem
from server.ground_truth.safe_http import EgressPolicyError, safe_request
from server.ground_truth.utils import _normalize_query, _tokenize, _utc_now


APPLE_BASE = "https://www.apple.com"
APPLE_SEARCH = "https://www.apple.com/shop/search/{query}"
APPLE_ALLOWED_HOSTS = {"apple.com", "www.apple.com"}
LOGGER = logging.getLogger("agenteval.ground_truth")


def fetch_apple_evidence(query: str) -> list[EvidenceItem]:
    search_url = APPLE_SEARCH.format(query=quote_plus(_normalize_query(query)))
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            resp = safe_request(
                client,
                "GET",
                search_url,
                allowed_hosts=APPLE_ALLOWED_HOSTS,
            )
            resp.raise_for_status()
            html = resp.text
    except EgressPolicyError as exc:
        LOGGER.warning("Apple egress blocked: %s", exc)
        return []
    except httpx.HTTPError as exc:
        LOGGER.warning("Apple search request failed: %s", exc)
        return []

    product_url = _extract_product_url(html)
    if not product_url:
        return []

    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            resp = safe_request(
                client,
                "GET",
                product_url,
                allowed_hosts=APPLE_ALLOWED_HOSTS,
            )
            resp.raise_for_status()
            product_html = resp.text
    except EgressPolicyError as exc:
        LOGGER.warning("Apple product egress blocked: %s", exc)
        return []
    except httpx.HTTPError as exc:
        LOGGER.warning("Apple product request failed: %s", exc)
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
    match = re.search(r"\$\s?([0-9]+(?:\.[0-9]{2})?)", html)
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
