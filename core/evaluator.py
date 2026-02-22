from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .parser import ParsedOffer, parse_agent_output
from .schema import CaseStudy, EvidenceItem, TaskRules


@dataclass(frozen=True)
class EvaluationResult:
    best_first_party_price_usd: Optional[float]
    best_first_party_retailer: Optional[str]
    agent_chosen_price_usd: Optional[float]
    agent_chosen_retailer: Optional[str]
    agent_choice_qualified: Optional[bool]
    found_best_first_party_price: Optional[bool]
    within_budget: Optional[bool]
    money_left_on_table_usd: Optional[float]


def evaluate_case_study(case_study: CaseStudy) -> EvaluationResult:
    parsed = parse_agent_output(case_study.agent_output.raw_text)

    qualifying = [
        item
        for item in case_study.evidence
        if _qualifies(item, case_study.task.rules)
    ]
    qualifying_with_price = [item for item in qualifying if item.price_usd is not None]
    best_item = None
    if qualifying_with_price:
        best_item = min(qualifying_with_price, key=lambda item: item.price_usd or float("inf"))

    chosen_offer = parsed.chosen
    chosen_evidence = _match_offer_to_evidence(chosen_offer, case_study.evidence)

    agent_chosen_price = None
    agent_chosen_retailer = None
    if chosen_offer:
        agent_chosen_price = chosen_offer.price_usd
        agent_chosen_retailer = chosen_offer.retailer
    if chosen_evidence and chosen_evidence.price_usd is not None:
        agent_chosen_price = chosen_evidence.price_usd
        agent_chosen_retailer = chosen_evidence.retailer

    agent_choice_qualified = None
    if chosen_evidence is not None:
        agent_choice_qualified = _qualifies(chosen_evidence, case_study.task.rules)

    found_best = None
    if best_item and agent_chosen_price is not None:
        if agent_choice_qualified is False:
            found_best = False
        else:
            found_best = _prices_equal(agent_chosen_price, best_item.price_usd)
            if agent_chosen_retailer and best_item.retailer:
                found_best = found_best and agent_chosen_retailer == best_item.retailer

    within_budget = None
    if case_study.task.budget_usd is not None and agent_chosen_price is not None:
        within_budget = agent_chosen_price <= case_study.task.budget_usd

    money_left = None
    if (
        best_item
        and best_item.price_usd is not None
        and agent_chosen_price is not None
        and agent_choice_qualified is not False
    ):
        delta = agent_chosen_price - best_item.price_usd
        money_left = round(delta, 2) if delta > 0 else 0.0

    return EvaluationResult(
        best_first_party_price_usd=best_item.price_usd if best_item else None,
        best_first_party_retailer=best_item.retailer if best_item else None,
        agent_chosen_price_usd=agent_chosen_price,
        agent_chosen_retailer=agent_chosen_retailer,
        agent_choice_qualified=agent_choice_qualified,
        found_best_first_party_price=found_best,
        within_budget=within_budget,
        money_left_on_table_usd=money_left,
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
) -> Optional[EvidenceItem]:
    if offer is None:
        return None
    if offer.url:
        for item in evidence:
            if item.url == offer.url:
                return item
    if offer.retailer:
        matches = [item for item in evidence if item.retailer == offer.retailer]
        if len(matches) == 1:
            return matches[0]
    return None
