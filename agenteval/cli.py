from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass

import httpx

from agenteval.openclaw import OpenClawMessage, chat_completions


@dataclass
class ConnectorConfig:
    api_url: str
    api_token: str
    gateway_url: str
    gateway_token: str
    agent_id: str
    poll_interval: float
    request_timeout: float


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s agenteval.connector: %(message)s",
    )
    parser = argparse.ArgumentParser(prog="agenteval", description="AgentEval connector CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    connect = sub.add_parser("connect", help="Start the AgentEval connector")
    connect.add_argument("--api-url", required=True, help="AgentEval API base URL")
    connect.add_argument("--api-token", required=True, help="AgentEval connector token")
    connect.add_argument("--gateway-url", default="http://127.0.0.1:18789", help="OpenClaw Gateway URL")
    connect.add_argument("--gateway-token", required=True, help="OpenClaw Gateway token")
    connect.add_argument("--agent-id", default="main", help="OpenClaw agent id")
    connect.add_argument("--poll-interval", type=float, default=2.0, help="Seconds between polls")
    connect.add_argument("--timeout", type=float, default=600.0, help="OpenClaw request timeout (seconds)")

    args = parser.parse_args()
    if args.command == "connect":
        config = ConnectorConfig(
            api_url=args.api_url.rstrip("/"),
            api_token=args.api_token,
            gateway_url=args.gateway_url.rstrip("/"),
            gateway_token=args.gateway_token,
            agent_id=args.agent_id,
            poll_interval=args.poll_interval,
            request_timeout=args.timeout,
        )
        run_connector(config)


def run_connector(config: ConnectorConfig) -> None:
    logger = logging.getLogger("agenteval.connector")
    headers = {"Authorization": f"Bearer {config.api_token}"}
    logger.info("Connector started. Polling %s every %.1fs", config.api_url, config.poll_interval)
    while True:
        job = _fetch_next_job(config.api_url, headers)
        if not job:
            time.sleep(config.poll_interval)
            continue

        job_id = job.get("id")
        logger.info("Picked up job %s", job_id)
        raw_output, error = _execute_job(config, job)
        if error:
            logger.error("Job %s failed: %s", job_id, error)
        else:
            logger.info("Job %s completed", job_id)
        _complete_job(config.api_url, headers, job["id"], raw_output, error)


def _fetch_next_job(api_url: str, headers: dict[str, str]) -> dict | None:
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{api_url}/v1/jobs/next", headers=headers)
            if resp.status_code == 204:
                return None
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        return None


def _execute_job(config: ConnectorConfig, job: dict) -> tuple[str, str | None]:
    logger = logging.getLogger("agenteval.connector")
    payload = job.get("payload", {})
    prompt = payload.get("prompt") or ""
    messages = [OpenClawMessage(role="user", content=prompt)]
    timeout_s = config.request_timeout
    payload_timeout = payload.get("timeout_s")
    if payload_timeout is not None:
        try:
            parsed_timeout = float(payload_timeout)
            if parsed_timeout > 0:
                timeout_s = parsed_timeout
        except (TypeError, ValueError):
            pass

    try:
        logger.info("Sending job %s to OpenClaw (%s)", job.get("id"), payload.get("agent_id") or config.agent_id)
        response = chat_completions(
            base_url=config.gateway_url,
            token=config.gateway_token,
            agent_id=payload.get("agent_id") or config.agent_id,
            messages=messages,
            user=f"agenteval:{job['id']}",
            timeout_s=timeout_s,
        )
        return response.text or json.dumps(response.raw), None
    except Exception as exc:
        return "", str(exc)


def _complete_job(
    api_url: str,
    headers: dict[str, str],
    job_id: str,
    raw_output: str,
    error: str | None,
) -> None:
    payload = {"raw_output": raw_output, "error": error}
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(f"{api_url}/v1/jobs/{job_id}/complete", json=payload, headers=headers)
    except httpx.HTTPError:
        return


if __name__ == "__main__":
    main()
