from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_RE_PRICE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]{2})?)")
_RE_URL = re.compile(r"https?://[^\s)]+")

_RE_CHOSEN = re.compile(
    r"chosen retailer\s*\+\s*price\s*\+\s*url\s*:\s*(.+)",
    re.IGNORECASE,
)

_RE_WITHIN_BUDGET = re.compile(
    r"within budget\s*\(?\$?[0-9.]+\s*hard cap\)?\?\s*(yes|no)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedOffer:
    retailer: str
    price_usd: Optional[float]
    url: Optional[str]
    availability: Optional[str]
    seller: Optional[str]
    variant_match: Optional[bool]
    listing_id: Optional[str]
    listing_id_type: Optional[str]


@dataclass(frozen=True)
class ParsedAgentOutput:
    raw_text: str
    offers: list[ParsedOffer]
    chosen: Optional[ParsedOffer]
    within_budget: Optional[bool]


def parse_agent_output(raw_text: Optional[str]) -> ParsedAgentOutput:
    normalized_text = raw_text or ""
    lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]

    offers_by_retailer: dict[str, dict[str, Optional[str]]] = {}
    current_retailer: Optional[str] = None

    for line in lines:
        lower = line.lower()
        if "amazon" in lower:
            current_retailer = "Amazon"
        elif "best buy" in lower or "bestbuy" in lower:
            current_retailer = "Best Buy"
        elif "apple" in lower:
            current_retailer = "Apple"

        if current_retailer:
            offers_by_retailer.setdefault(current_retailer, {})
            _capture_line_fields(offers_by_retailer[current_retailer], line)

    offers: list[ParsedOffer] = []
    for retailer, fields in offers_by_retailer.items():
        offers.append(_build_offer(retailer, fields))

    chosen = _parse_chosen_offer(normalized_text, lines)
    within_budget = _parse_within_budget(normalized_text, lines)

    return ParsedAgentOutput(
        raw_text=normalized_text,
        offers=offers,
        chosen=chosen,
        within_budget=within_budget,
    )


def _capture_line_fields(fields: dict[str, Optional[str]], line: str) -> None:
    price_match = _RE_PRICE.search(line)
    if price_match and not fields.get("price"):
        fields["price"] = price_match.group(1)

    url_match = _RE_URL.search(line)
    if url_match and not fields.get("url"):
        fields["url"] = url_match.group(0)

    if "availability" in line.lower() and not fields.get("availability"):
        fields["availability"] = _after_colon(line)

    if "seller" in line.lower() and not fields.get("seller"):
        fields["seller"] = _after_colon(line)

    if "variant match" in line.lower() and not fields.get("variant_match"):
        value = _after_colon(line).lower()
        if value in {"yes", "true"}:
            fields["variant_match"] = "true"
        elif value in {"no", "false"}:
            fields["variant_match"] = "false"


def _build_offer(retailer: str, fields: dict[str, Optional[str]]) -> ParsedOffer:
    price_value = None
    if fields.get("price"):
        try:
            price_value = float(fields["price"])
        except ValueError:
            price_value = None

    variant_match = None
    if fields.get("variant_match") == "true":
        variant_match = True
    elif fields.get("variant_match") == "false":
        variant_match = False

    return ParsedOffer(
        retailer=retailer,
        price_usd=price_value,
        url=fields.get("url"),
        availability=fields.get("availability"),
        seller=fields.get("seller"),
        variant_match=variant_match,
        listing_id=None,
        listing_id_type=None,
    )


def _parse_chosen_offer(raw_text: str, lines: list[str]) -> Optional[ParsedOffer]:
    match = _RE_CHOSEN.search(raw_text)
    if not match:
        return _parse_chosen_offer_by_lines(lines)

    text = match.group(1)
    url_match = _RE_URL.search(text)
    price_match = _RE_PRICE.search(text)

    retailer = _infer_retailer(text)
    price_value = float(price_match.group(1)) if price_match else None
    url = url_match.group(0) if url_match else None

    return ParsedOffer(
        retailer=retailer or "Unknown",
        price_usd=price_value,
        url=url,
        availability=None,
        seller=None,
        variant_match=None,
        listing_id=None,
        listing_id_type=None,
    )


def _parse_within_budget(raw_text: str, lines: list[str]) -> Optional[bool]:
    match = _RE_WITHIN_BUDGET.search(raw_text)
    if not match:
        return _parse_within_budget_by_lines(lines)
    return match.group(1).lower() == "yes"


def _infer_retailer(text: str) -> Optional[str]:
    lower = text.lower()
    if "amazon" in lower:
        return "Amazon"
    if "best buy" in lower or "bestbuy" in lower:
        return "Best Buy"
    if "apple" in lower:
        return "Apple"
    return None


def _after_colon(line: str) -> str:
    if ":" in line:
        return line.split(":", 1)[1].strip()
    return line.strip()


def _parse_chosen_offer_by_lines(lines: list[str]) -> Optional[ParsedOffer]:
    for idx, line in enumerate(lines):
        normalized = line.strip().lower().rstrip(":")
        if normalized in {"chosen retailer + price + url", "chosen retailer + price + url"}:
            # Look ahead for retailer/price line and URL line
            next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            next_next_line = lines[idx + 2] if idx + 2 < len(lines) else ""
            if "no valid choice" in next_line.lower():
                return None
            url_match = _RE_URL.search(next_line) or _RE_URL.search(next_next_line)
            price_match = _RE_PRICE.search(next_line) or _RE_PRICE.search(next_next_line)

            retailer = _infer_retailer(next_line)
            price_value = float(price_match.group(1)) if price_match else None
            url = url_match.group(0) if url_match else None

            return ParsedOffer(
                retailer=retailer or "Unknown",
                price_usd=price_value,
                url=url,
                availability=None,
                seller=None,
                variant_match=None,
                listing_id=None,
                listing_id_type=None,
            )
    return None


def _parse_within_budget_by_lines(lines: list[str]) -> Optional[bool]:
    for idx, line in enumerate(lines):
        normalized = line.strip().lower()
        if normalized.startswith("within budget"):
            next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            if next_line.lower().startswith("yes"):
                return True
            if next_line.lower().startswith("no"):
                return False
    return None
