from __future__ import annotations

import unittest

from core.parser import parse_agent_output


class ParserTests(unittest.TestCase):
    def test_parse_chosen_offer_block(self) -> None:
        raw = """
        1) Amazon: price $19.00
        2) Best Buy: price $14.99
        Chosen retailer + price + URL:
        Best Buy — $14.99
        https://www.bestbuy.com/site/apple-20w-usb-c-power-adapter-white/6437121.p?skuId=6437121
        Within budget ($25 hard cap)? Yes
        """
        parsed = parse_agent_output(raw)
        self.assertIsNotNone(parsed.chosen)
        assert parsed.chosen is not None
        self.assertEqual(parsed.chosen.retailer, "Best Buy")
        self.assertEqual(parsed.chosen.price_usd, 14.99)
        self.assertTrue(parsed.within_budget)

    def test_parse_leading_index_lines(self) -> None:
        raw = """
        1) Chosen retailer + price + URL:
        2) Amazon — $13.30
        3) https://www.amazon.com/dp/B0DJFW7PNM
        4) Within budget ($25 hard cap)? Yes
        """
        parsed = parse_agent_output(raw)
        self.assertIsNotNone(parsed.chosen)
        assert parsed.chosen is not None
        self.assertEqual(parsed.chosen.retailer, "Amazon")
        self.assertEqual(parsed.chosen.price_usd, 13.30)

    def test_chosen_section_takes_precedence_over_earlier_text(self) -> None:
        raw = """
        Heads up: chosen retailer + price + URL might be stale in older logs.
        - Amazon
          - Price: $14.99
        Chosen retailer + price + URL:
        - Best Buy — $19.00
        - https://www.bestbuy.com/site/apple-20w-usb-c-power-adapter-white/6437121.p?skuId=6437121
        """
        parsed = parse_agent_output(raw)
        self.assertIsNotNone(parsed.chosen)
        assert parsed.chosen is not None
        self.assertEqual(parsed.chosen.retailer, "Best Buy")
        self.assertEqual(parsed.chosen.price_usd, 19.00)

    def test_parse_markdown_inline_chosen_with_url_next_line(self) -> None:
        raw = """
        **Chosen retailer:** **Best Buy — $14.99**
        **URL:** https://www.bestbuy.com/site/apple-20w-usb-c-power-adapter-white/6437121.p?skuId=6437121
        **Within budget ($25 hard cap)?** **Yes**
        """
        parsed = parse_agent_output(raw)
        self.assertIsNotNone(parsed.chosen)
        assert parsed.chosen is not None
        self.assertEqual(parsed.chosen.retailer, "Best Buy")
        self.assertEqual(parsed.chosen.price_usd, 14.99)
        self.assertEqual(
            parsed.chosen.url,
            "https://www.bestbuy.com/site/apple-20w-usb-c-power-adapter-white/6437121.p?skuId=6437121",
        )
        self.assertTrue(parsed.within_budget)


if __name__ == "__main__":
    unittest.main()
