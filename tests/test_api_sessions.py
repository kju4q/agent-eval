from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import os

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - optional in minimal test envs
    TestClient = None  # type: ignore[assignment]

if TestClient is not None:
    from server import app as app_module
    from server.db import JobStore
    from server.ground_truth.types import GroundTruthResult, ProviderFetchStatus
else:  # pragma: no cover
    app_module = None  # type: ignore[assignment]
    JobStore = None  # type: ignore[assignment]


@unittest.skipIf(TestClient is None, "fastapi testclient is not available in this environment")
class ApiSessionIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        assert app_module is not None
        assert JobStore is not None
        self._old_ip_window = os.getenv("AGENTEVAL_IP_WINDOW_SECONDS")
        self._old_ip_limit = os.getenv("AGENTEVAL_IP_MAX_JOBS_PER_WINDOW")
        os.environ["AGENTEVAL_IP_WINDOW_SECONDS"] = "60"
        os.environ["AGENTEVAL_IP_MAX_JOBS_PER_WINDOW"] = "100"
        self._old_fetch = app_module.fetch_evidence_with_status
        app_module.store = JobStore(Path(self.tmpdir.name) / "test.db")
        self.client = TestClient(app_module.app)

    def tearDown(self) -> None:
        assert app_module is not None
        app_module.fetch_evidence_with_status = self._old_fetch
        if self._old_ip_window is None:
            os.environ.pop("AGENTEVAL_IP_WINDOW_SECONDS", None)
        else:
            os.environ["AGENTEVAL_IP_WINDOW_SECONDS"] = self._old_ip_window
        if self._old_ip_limit is None:
            os.environ.pop("AGENTEVAL_IP_MAX_JOBS_PER_WINDOW", None)
        else:
            os.environ["AGENTEVAL_IP_MAX_JOBS_PER_WINDOW"] = self._old_ip_limit
        self.tmpdir.cleanup()

    def _new_session(self) -> tuple[str, str]:
        headers: dict[str, str] = {}
        bootstrap_token = getattr(app_module, "_BOOTSTRAP_TOKEN", None) or os.getenv(
            "AGENTEVAL_SESSION_BOOTSTRAP_TOKEN"
        )
        if bootstrap_token:
            headers["X-AgentEval-Bootstrap"] = str(bootstrap_token)
        resp = self.client.post(
            "/v1/sessions",
            json={"ttl_seconds": 3600, "max_evals": 3},
            headers=headers or None,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        return data["session_id"], data["session_token"]

    def test_runs_are_session_scoped(self) -> None:
        _, token_a = self._new_session()
        _, token_b = self._new_session()

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        payload = {
            "product_name": "Apple 20W USB-C Power Adapter",
            "prompt": "Reply with ok",
            "allowed_retailers": [],
        }
        created = self.client.post("/v1/jobs", json=payload, headers=headers_a)
        self.assertEqual(created.status_code, 200)
        run_id = created.json()["id"]

        denied = self.client.get(f"/v1/runs/{run_id}", headers=headers_b)
        self.assertEqual(denied.status_code, 404)

    def test_complete_endpoint_is_idempotent(self) -> None:
        _, token = self._new_session()
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "product_name": "Apple 20W USB-C Power Adapter",
            "prompt": "Reply with ok",
            "allowed_retailers": [],
        }
        created = self.client.post("/v1/jobs", json=payload, headers=headers)
        self.assertEqual(created.status_code, 200)
        run_id = created.json()["id"]

        next_job = self.client.get("/v1/jobs/next", headers=headers)
        self.assertEqual(next_job.status_code, 200)

        first = self.client.post(
            f"/v1/jobs/{run_id}/complete",
            json={"raw_output": "first", "error": None},
            headers=headers,
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            f"/v1/jobs/{run_id}/complete",
            json={"raw_output": "second", "error": None},
            headers=headers,
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json().get("raw_output"), "first")

    def test_create_job_ip_rate_limited(self) -> None:
        os.environ["AGENTEVAL_IP_MAX_JOBS_PER_WINDOW"] = "1"
        _, token = self._new_session()
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "product_name": "Apple 20W USB-C Power Adapter",
            "prompt": "Reply with ok",
            "allowed_retailers": [],
        }
        first = self.client.post("/v1/jobs", json=payload, headers=headers)
        self.assertEqual(first.status_code, 200)
        second = self.client.post("/v1/jobs", json=payload, headers=headers)
        self.assertEqual(second.status_code, 429)

    def test_degraded_evidence_status_exposed(self) -> None:
        assert app_module is not None

        def fake_fetch(_: dict) -> GroundTruthResult:
            return GroundTruthResult(
                evidence=[],
                provider_status=[
                    ProviderFetchStatus(
                        provider="dataforseo",
                        state="blocked",
                        detail="Daily cap reached.",
                        calls_today=10,
                        daily_cap=10,
                    )
                ],
            )

        app_module.fetch_evidence_with_status = fake_fetch

        _, token = self._new_session()
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "product_name": "Apple 20W USB-C Power Adapter",
            "prompt": "Reply with ok",
            "allowed_retailers": ["Amazon"],
        }
        created = self.client.post("/v1/jobs", json=payload, headers=headers)
        self.assertEqual(created.status_code, 200)
        run_id = created.json()["id"]

        next_job = self.client.get("/v1/jobs/next", headers=headers)
        self.assertEqual(next_job.status_code, 200)
        completed = self.client.post(
            f"/v1/jobs/{run_id}/complete",
            json={"raw_output": "ok", "error": None},
            headers=headers,
        )
        self.assertEqual(completed.status_code, 200)
        data = completed.json()["eval_result"]
        self.assertEqual(data.get("status"), "insufficient-evidence")
        self.assertEqual(data.get("evidence_status"), "degraded")
        provider_status = data.get("provider_status") or []
        self.assertEqual(provider_status[0].get("state"), "blocked")

    def test_connector_presence_updates_on_poll(self) -> None:
        _, token = self._new_session()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-AgentEval-Agent-Id": "shopping-agent",
            "X-AgentEval-Gateway-Url": "http://127.0.0.1:18789",
        }
        poll = self.client.get("/v1/jobs/next", headers=headers)
        self.assertEqual(poll.status_code, 204)

        status = self.client.get("/v1/sessions/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(status.status_code, 200)
        body = status.json()
        self.assertEqual(body.get("connector_agent_id"), "shopping-agent")
        self.assertEqual(body.get("connector_gateway_url"), "http://127.0.0.1:18789")
        self.assertIsNotNone(body.get("last_polled_at"))


if __name__ == "__main__":
    unittest.main()
