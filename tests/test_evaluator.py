import unittest

from core.evaluator import evaluate_case_study
from core.schema import AgentOutput, AgentSpec, CaseStudy, EvidenceItem, TaskRules, TaskSpec


def _make_case(raw_text: str, evidence: list[EvidenceItem]) -> CaseStudy:
    ts = "2026-03-06T15:00:00+00:00"
    agent = AgentSpec(name="openclaw", version=None, run_mode="live")
    task = TaskSpec(
        product_name="Apple 20W USB-C Power Adapter",
        product_variant=None,
        budget_usd=25.0,
        currency="USD",
        allowed_retailers=["Amazon", "Best Buy", "Apple"],
        rules=TaskRules(allow_third_party=False, allow_refurbished=False, require_full_set=True),
        canonical_listings=[],
    )
    agent_output = AgentOutput(raw_text=raw_text, captured_at=ts, source=None, status=None)
    return CaseStudy(
        version="1",
        id="test",
        title="test",
        created_at=ts,
        agent=agent,
        task=task,
        agent_output=agent_output,
        evidence=evidence,
        notes=None,
    )


class EvaluatorTests(unittest.TestCase):
    def test_unverified_choice_sets_money_left_none(self) -> None:
        evidence = [
            EvidenceItem(
                retailer="Best Buy",
                url="https://api.bestbuy.com/click/-/6437121/pdp",
                price_usd=14.99,
                availability="In Stock",
                seller="Best Buy",
                timestamp="2026-03-06T15:00:00+00:00",
                variant_match=True,
                listing_id="6437121",
                listing_id_type="sku",
                notes=None,
                source_type="verified-retailer",
                confidence=0.9,
            )
        ]
        raw_text = (
            "2) Chosen retailer + price + URL\n"
            "Apple — $19.00\n"
            "https://www.apple.com/shop/product/mwvv3am/a/20w-usb-c-power-adapter\n"
            "3) Within budget ($25 hard cap)? Yes"
        )
        result = evaluate_case_study(_make_case(raw_text, evidence))
        self.assertIsNone(result.found_best_first_party_price)
        self.assertIsNone(result.money_left_on_table_usd)
        self.assertFalse(result.agent_choice_verified)

    def test_verified_choice_can_match_best_price_without_retailer_match(self) -> None:
        evidence = [
            EvidenceItem(
                retailer="Best Buy",
                url="https://api.bestbuy.com/click/-/6437121/pdp",
                price_usd=14.99,
                availability="In Stock",
                seller="Best Buy",
                timestamp="2026-03-06T15:00:00+00:00",
                variant_match=True,
                listing_id="6437121",
                listing_id_type="sku",
                notes=None,
                source_type="verified-retailer",
                confidence=0.9,
            ),
            EvidenceItem(
                retailer="Amazon",
                url="https://www.amazon.com/Apple-20W-USB-C-Power-Adapter/dp/B0DJFW7PNM",
                price_usd=14.99,
                availability="In Stock",
                seller="Amazon.com",
                timestamp="2026-03-06T15:00:00+00:00",
                variant_match=True,
                listing_id="B0DJFW7PNM",
                listing_id_type="asin",
                notes=None,
                source_type="aggregator",
                confidence=0.8,
            ),
        ]
        raw_text = (
            "2) Chosen retailer + price + URL\n"
            "Amazon — $14.99\n"
            "https://www.amazon.com/Apple-20W-USB-C-Power-Adapter/dp/B0DJFW7PNM\n"
            "3) Within budget ($25 hard cap)? Yes"
        )
        result = evaluate_case_study(_make_case(raw_text, evidence))
        self.assertTrue(result.agent_choice_verified)
        self.assertTrue(result.found_best_first_party_price)


if __name__ == "__main__":
    unittest.main()
