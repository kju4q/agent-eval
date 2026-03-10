from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

from .parser import ParsedOffer, parse_agent_output
from .schema import CaseStudy, EvidenceItem, TaskRules


@dataclass(frozen=True)
class EvaluationResult:
    best_first_party_price_usd: Optional[float]
    best_first_party_retailer: Optional[str]
    best_first_party_url: Optional[str]
    best_first_party_confidence: Optional[float]
    best_first_party_source_type: Optional[str]
    best_first_party_seller: Optional[str]
    agent_chosen_price_usd: Optional[float]
    agent_chosen_retailer: Optional[str]
    agent_chosen_url: Optional[str]
    agent_choice_qualified: Optional[bool]
    agent_choice_verified: Optional[bool]
    verification_failure_reason: Optional[str]
    found_best_first_party_price: Optional[bool]
    within_budget: Optional[bool]
    money_left_on_table_usd: Optional[float]
    disputed_price: Optional[bool]


def evaluate_case_study(case_study: CaseStudy) -> EvaluationResult:
    parsed = parse_agent_output(case_study.agent_output.raw_text)

    qualifying = [
        item
        for item in case_study.evidence
        if _qualifies(item, case_study.task.rules)
    ]
    qualifying = _filter_by_confidence(qualifying)
    qualifying_with_price = [item for item in qualifying if item.price_usd is not None]
    best_item = None
    if qualifying_with_price:
        best_item = min(qualifying_with_price, key=lambda item: item.price_usd or float("inf"))

    chosen_offer = parsed.chosen
    chosen_evidence, verification_reason = _match_offer_to_evidence(chosen_offer, case_study.evidence)

    agent_chosen_price = None
    agent_chosen_retailer = None
    agent_chosen_url = None
    if chosen_offer:
        agent_chosen_price = chosen_offer.price_usd
        agent_chosen_retailer = chosen_offer.retailer
        agent_chosen_url = chosen_offer.url
    if chosen_evidence and chosen_evidence.price_usd is not None:
        agent_chosen_price = chosen_evidence.price_usd
        agent_chosen_retailer = chosen_evidence.retailer
        agent_chosen_url = chosen_evidence.url

    agent_choice_qualified = None
    if chosen_evidence is not None:
        agent_choice_qualified = _qualifies(chosen_evidence, case_study.task.rules)
    agent_choice_verified = None
    if chosen_offer:
        agent_choice_verified = chosen_evidence is not None
    verification_failure_reason = None
    if chosen_offer and chosen_evidence is None:
        verification_failure_reason = (
            verification_reason or "No evidence item matched the agent's chosen offer."
        )

    found_best = None
    if best_item and agent_chosen_price is not None:
        if agent_choice_qualified is False:
            found_best = False
        elif agent_choice_verified is False:
            found_best = None
        else:
            found_best = _prices_equal(agent_chosen_price, best_item.price_usd)

    within_budget = None
    if case_study.task.budget_usd is not None and agent_chosen_price is not None:
        within_budget = agent_chosen_price <= case_study.task.budget_usd
    if within_budget is None:
        within_budget = parsed.within_budget

    money_left = None
    if (
        best_item
        and best_item.price_usd is not None
        and agent_chosen_price is not None
        and agent_choice_qualified is not False
        and agent_choice_verified is not False
    ):
        delta = agent_chosen_price - best_item.price_usd
        money_left = round(delta, 2) if delta > 0 else 0.0

    disputed_price = None
    if (
        best_item
        and best_item.price_usd is not None
        and agent_chosen_price is not None
        and agent_choice_verified is False
    ):
        disputed_price = agent_chosen_price < best_item.price_usd - 0.01

    return EvaluationResult(
        best_first_party_price_usd=best_item.price_usd if best_item else None,
        best_first_party_retailer=best_item.retailer if best_item else None,
        best_first_party_url=best_item.url if best_item else None,
        best_first_party_confidence=best_item.confidence if best_item else None,
        best_first_party_source_type=best_item.source_type if best_item else None,
        best_first_party_seller=best_item.seller if best_item else None,
        agent_chosen_price_usd=agent_chosen_price,
        agent_chosen_retailer=agent_chosen_retailer,
        agent_chosen_url=agent_chosen_url,
        agent_choice_qualified=agent_choice_qualified,
        agent_choice_verified=agent_choice_verified,
        verification_failure_reason=verification_failure_reason,
        found_best_first_party_price=found_best,
        within_budget=within_budget,
        money_left_on_table_usd=money_left,
        disputed_price=disputed_price,
    )


def _qualifies(item: EvidenceItem, rules: TaskRules) -> bool:
    if item.price_usd is None:
        return False
    if rules.require_full_set and item.variant_match is not True:
        return False
    if not rules.allow_refurbished and _looks_refurbished(item):
        return False
    if not rules.allow_third_party and not _is_first_party(item):
        return False
    return True


def _is_first_party(item: EvidenceItem) -> bool:
    if item.seller is None:
        return False
    seller = item.seller.strip().lower()
    retailer = item.retailer.strip().lower()
    expected = {
        "amazon": "amazon.com",
        "best buy": "best buy",
        "apple": "apple",
    }
    expected_seller = expected.get(retailer)
    if not expected_seller:
        return False
    return expected_seller in seller


def _looks_refurbished(item: EvidenceItem) -> bool:
    haystack = " ".join(
        part.lower()
        for part in [item.availability, item.notes, item.seller]
        if part
    )
    return any(token in haystack for token in ["refurb", "renewed", "open-box", "used"])


def _prices_equal(left: Optional[float], right: Optional[float]) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) < 0.01


def _match_offer_to_evidence(
    offer: Optional[ParsedOffer],
    evidence: list[EvidenceItem],
) -> tuple[Optional[EvidenceItem], Optional[str]]:
    if offer is None:
        return None, None
    if not evidence:
        return None, "No evidence was available to verify the chosen offer."
    if offer.url:
        for item in evidence:
            if item.url == offer.url:
                return item, "Matched exact URL to evidence."
    offer_listing_id = offer.listing_id
    offer_listing_id_type = offer.listing_id_type
    if not offer_listing_id and offer.url:
        extracted = _extract_listing_id_from_url(offer.url, offer.retailer)
        if extracted:
            offer_listing_id, offer_listing_id_type = extracted
    offer_listing_id = _normalize_listing_id(offer_listing_id, offer_listing_id_type)
    if offer_listing_id:
        candidates = [
            item
            for item in evidence
            if _normalize_listing_id(item.listing_id, item.listing_id_type) == offer_listing_id
        ]
        if offer_listing_id_type:
            typed = [item for item in candidates if item.listing_id_type == offer_listing_id_type]
            if typed:
                candidates = typed
        if candidates:
            return max(candidates, key=_confidence_key), "Matched listing ID to evidence."
    if offer.retailer and offer.price_usd is not None:
        matches = [
            item
            for item in evidence
            if item.retailer == offer.retailer and _prices_equal(item.price_usd, offer.price_usd)
        ]
        if len(matches) == 1:
            return max(matches, key=_confidence_key), "Matched retailer and price to evidence."
        if len(matches) > 1:
            return None, "Multiple evidence entries matched retailer and price; could not verify uniquely."
    if offer.retailer and offer.url is None and offer_listing_id is None and offer.price_usd is None:
        matches = [item for item in evidence if item.retailer == offer.retailer]
        if len(matches) == 1:
            return matches[0], "Matched by retailer only (single evidence entry)."
    if offer.url or offer_listing_id:
        return None, "Chosen URL/listing ID did not match evidence."
    if offer.retailer and offer.price_usd is not None:
        return None, "No evidence entry matched chosen retailer and price."
    return None, "Chosen offer lacked enough identifiers to verify."


def _filter_by_confidence(evidence: list[EvidenceItem]) -> list[EvidenceItem]:
    if not evidence:
        return evidence
    if any(item.confidence is not None for item in evidence):
        high_conf = [item for item in evidence if (item.confidence or 0.0) >= 0.8]
        if high_conf:
            return high_conf
    return evidence


def _confidence_key(item: EvidenceItem) -> float:
    return item.confidence or 0.0


def _normalize_listing_id(listing_id: Optional[str], listing_id_type: Optional[str]) -> Optional[str]:
    if not listing_id:
        return None
    if listing_id_type in {"asin", "apple_sku"}:
        return listing_id.upper()
    return listing_id


def _extract_listing_id_from_url(
    url: str,
    retailer: Optional[str],
) -> Optional[tuple[str, str]]:
    normalized_retailer = (retailer or _infer_retailer_from_url(url) or "").strip().lower()
    if normalized_retailer in {"best buy", "bestbuy"}:
        for pattern in [
            r"/sku/(\d+)",
            r"skuid=(\d+)",
            r"/click/-/(\d+)/pdp",
            r"/(\d+)\.p",
        ]:
            match = re.search(pattern, url, flags=re.IGNORECASE)
            if match:
                return match.group(1), "sku"
    if normalized_retailer == "amazon":
        for pattern in [r"/dp/([A-Z0-9]{10})", r"/gp/product/([A-Z0-9]{10})"]:
            match = re.search(pattern, url, flags=re.IGNORECASE)
            if match:
                return match.group(1).upper(), "asin"
    if normalized_retailer == "apple":
        match = re.search(r"/shop/product/([^/]+)/", url, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper(), "apple_sku"
    return None


def _infer_retailer_from_url(url: str) -> Optional[str]:
    lowered = url.lower()
    if "bestbuy." in lowered:
        return "best buy"
    if "amazon." in lowered:
        return "amazon"
    if "apple.com" in lowered:
        return "apple"
    return None
