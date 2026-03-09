from __future__ import annotations

import os
import tempfile
import unittest
import importlib.util
from pathlib import Path

HTTPX_AVAILABLE = importlib.util.find_spec("httpx") is not None

if HTTPX_AVAILABLE:
    from server.db import JobStore
    import server.ground_truth as ground_truth_module
    import server.ground_truth.spend as spend_module
else:  # pragma: no cover
    JobStore = None  # type: ignore[assignment]
    ground_truth_module = None  # type: ignore[assignment]
    spend_module = None  # type: ignore[assignment]


@unittest.skipIf(not HTTPX_AVAILABLE, "httpx is not available in this environment")
class GroundTruthSpendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        assert JobStore is not None
        assert spend_module is not None
        assert ground_truth_module is not None
        self.store = JobStore(Path(self.tmpdir.name) / "test.db")

        self._orig_jobstore = spend_module.JobStore
        self._orig_fetch_amazon = ground_truth_module.fetch_amazon_evidence
        self._orig_env = {
            "DATAFORSEO_LOGIN": os.getenv("DATAFORSEO_LOGIN"),
            "DATAFORSEO_PASSWORD": os.getenv("DATAFORSEO_PASSWORD"),
            "AGENTEVAL_DATAFORSEO_DAILY_CALL_CAP": os.getenv("AGENTEVAL_DATAFORSEO_DAILY_CALL_CAP"),
            "AGENTEVAL_DATAFORSEO_DAILY_USD_CAP": os.getenv("AGENTEVAL_DATAFORSEO_DAILY_USD_CAP"),
            "AGENTEVAL_DATAFORSEO_COST_PER_CALL_USD": os.getenv("AGENTEVAL_DATAFORSEO_COST_PER_CALL_USD"),
            "AGENTEVAL_EVIDENCE_KILL_SWITCH": os.getenv("AGENTEVAL_EVIDENCE_KILL_SWITCH"),
        }

        spend_module.JobStore = lambda: self.store  # type: ignore[assignment]
        ground_truth_module.fetch_amazon_evidence = lambda _: []  # type: ignore[assignment]

        os.environ["DATAFORSEO_LOGIN"] = "test-login"
        os.environ["DATAFORSEO_PASSWORD"] = "test-password"
        os.environ["AGENTEVAL_EVIDENCE_KILL_SWITCH"] = "0"

    def tearDown(self) -> None:
        spend_module.JobStore = self._orig_jobstore  # type: ignore[assignment]
        ground_truth_module.fetch_amazon_evidence = self._orig_fetch_amazon  # type: ignore[assignment]
        for key, value in self._orig_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmpdir.cleanup()

    def test_blocks_when_daily_spend_cap_reached(self) -> None:
        os.environ["AGENTEVAL_DATAFORSEO_DAILY_CALL_CAP"] = "100"
        os.environ["AGENTEVAL_DATAFORSEO_DAILY_USD_CAP"] = "0.05"
        os.environ["AGENTEVAL_DATAFORSEO_COST_PER_CALL_USD"] = "0.05"

        spend_module.consume_spend_usd(spend_module.PROVIDER_DATAFORSEO, 0.05)

        result = ground_truth_module.fetch_evidence_with_status(
            {
                "product_name": "Apple 20W USB-C Power Adapter",
                "allowed_retailers": ["Amazon"],
            }
        )
        self.assertEqual(result.evidence, [])
        self.assertTrue(result.provider_status)
        status = result.provider_status[0]
        self.assertEqual(status.provider, "dataforseo")
        self.assertEqual(status.state, "blocked")
        self.assertIn("spend cap", status.detail or "")

    def test_records_spend_when_fetch_allowed(self) -> None:
        os.environ["AGENTEVAL_DATAFORSEO_DAILY_CALL_CAP"] = "100"
        os.environ["AGENTEVAL_DATAFORSEO_DAILY_USD_CAP"] = "10.0"
        os.environ["AGENTEVAL_DATAFORSEO_COST_PER_CALL_USD"] = "0.25"

        result = ground_truth_module.fetch_evidence_with_status(
            {
                "product_name": "Apple 20W USB-C Power Adapter",
                "allowed_retailers": ["Amazon"],
            }
        )
        self.assertTrue(result.provider_status)
        status = result.provider_status[0]
        self.assertEqual(status.provider, "dataforseo")
        self.assertEqual(status.state, "unavailable")
        self.assertAlmostEqual(status.spend_usd_today or 0.0, 0.25, places=4)
        self.assertAlmostEqual(status.daily_spend_cap_usd or 0.0, 10.0, places=4)


if __name__ == "__main__":
    unittest.main()
