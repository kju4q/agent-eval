from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from agenteval.openclaw import OpenClawMessage, chat_completions

CONFIG_PATH = Path.home() / ".agenteval" / "config.json"


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
    connect.add_argument("--api-url", help="AgentEval API base URL")
    connect.add_argument("--gateway-url", help="OpenClaw Gateway URL")
    connect.add_argument("--agent-id", help="OpenClaw agent id")
    connect.add_argument("--poll-interval", type=float, help="Seconds between polls")
    connect.add_argument("--timeout", type=float, help="OpenClaw request timeout (seconds)")

    init = sub.add_parser("init", help="Create or update ~/.agenteval/config.json")
    init.add_argument("--path", default=str(CONFIG_PATH), help="Config file path")

    status = sub.add_parser("status", help="Check AgentEval and OpenClaw connectivity")
    status.add_argument("--api-url", help="AgentEval API base URL")
    status.add_argument("--gateway-url", help="OpenClaw Gateway URL")

    start = sub.add_parser("start", help="Start AgentEval API + connector")
    start.add_argument("--api-url", help="AgentEval API base URL")
    start.add_argument("--api-host", help="API host for uvicorn")
    start.add_argument("--api-port", type=int, help="API port for uvicorn")
    start.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload")

    session = sub.add_parser("session", help="Create a session token for API/connector")
    session.add_argument("--api-url", help="AgentEval API base URL")
    session.add_argument("--ttl-seconds", type=int, default=86400, help="Session TTL (seconds)")
    session.add_argument("--max-evals", type=int, default=25, help="Max evals for the session")

    args = parser.parse_args()
    if args.command == "connect":
        config = _resolve_connect_config(args)
        run_connector(config)
        return
    if args.command == "init":
        _init_config(Path(args.path))
        return
    if args.command == "status":
        _print_status(args)
        return
    if args.command == "start":
        _start_services(args)
        return
    if args.command == "session":
        _create_session_command(args)
        return


def run_connector(config: ConnectorConfig) -> None:
    logger = logging.getLogger("agenteval.connector")
    headers = {
        "Authorization": f"Bearer {config.api_token}",
        "X-AgentEval-Agent-Id": config.agent_id,
        "X-AgentEval-Gateway-Url": config.gateway_url,
    }
    logger.info("Connector started")
    logger.info("AgentEval API: %s", config.api_url)
    logger.info("OpenClaw Gateway: %s (agent_id=%s)", config.gateway_url, config.agent_id)
    _log_health_checks(config, headers)
    logger.info("Polling every %.1fs", config.poll_interval)
    last_wait_log = 0.0
    while True:
        job = _fetch_next_job(config.api_url, headers)
        if not job:
            now = time.time()
            if now - last_wait_log > 30:
                logger.info("Waiting for jobs...")
                last_wait_log = now
            time.sleep(config.poll_interval)
            continue

        job_id = job.get("id")
        payload = job.get("payload", {})
        prompt = payload.get("prompt") or ""
        logger.info(
            "Picked up job %s (agent_id=%s, prompt_chars=%s)",
            job_id,
            payload.get("agent_id") or config.agent_id,
            len(prompt),
        )
        raw_output, error, elapsed = _execute_job(config, job)
        if error:
            logger.error("Job %s failed: %s", job_id, error)
        else:
            logger.info("Job %s completed in %.1fs", job_id, elapsed)
        _complete_job(config.api_url, headers, job["id"], raw_output, error)
        logger.info("Submitted job %s result to API", job_id)


def _fetch_next_job(api_url: str, headers: dict[str, str]) -> dict | None:
    logger = logging.getLogger("agenteval.connector")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{api_url}/v1/jobs/next", headers=headers)
            if resp.status_code == 204:
                return None
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Polling error: %s", exc)
        return None


def _execute_job(config: ConnectorConfig, job: dict) -> tuple[str, str | None, float]:
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

    start = time.time()
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
        elapsed = time.time() - start
        logger.info("OpenClaw responded in %.1fs", elapsed)
        return response.text or json.dumps(response.raw), None, elapsed
    except Exception as exc:
        elapsed = time.time() - start
        return "", str(exc), elapsed


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


def _load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _resolve_connect_config(args: argparse.Namespace) -> ConnectorConfig:
    cfg = _load_config()
    api_url = _pick_value(
        getattr(args, "api_url", None),
        os.getenv("AGENTEVAL_API_URL"),
        cfg.get("api_url"),
    )
    api_token = _pick_value(
        os.getenv("AGENTEVAL_SESSION_TOKEN"),
        cfg.get("api_token"),
    )
    gateway_url = _pick_value(
        getattr(args, "gateway_url", None),
        os.getenv("OPENCLAW_GATEWAY_URL"),
        cfg.get("gateway_url"),
        "http://127.0.0.1:18789",
    )
    gateway_token = _pick_value(
        os.getenv("OPENCLAW_GATEWAY_TOKEN"),
        cfg.get("gateway_token"),
    )
    agent_id = _pick_value(
        getattr(args, "agent_id", None),
        os.getenv("OPENCLAW_AGENT_ID"),
        cfg.get("agent_id"),
        "main",
    )
    poll_interval = _pick_float(
        getattr(args, "poll_interval", None),
        os.getenv("AGENTEVAL_POLL_INTERVAL"),
        cfg.get("poll_interval"),
        2.0,
    )
    request_timeout = _pick_float(
        getattr(args, "timeout", None),
        os.getenv("AGENTEVAL_TIMEOUT"),
        cfg.get("timeout"),
        600.0,
    )

    missing = []
    if not api_url:
        missing.append("api_url")
    if not api_token:
        missing.append("api_token (AGENTEVAL_SESSION_TOKEN)")
    if not gateway_token:
        missing.append("gateway_token (OPENCLAW_GATEWAY_TOKEN)")
    if missing:
        raise SystemExit(f"Missing required configuration: {', '.join(missing)}")

    return ConnectorConfig(
        api_url=str(api_url).rstrip("/"),
        api_token=str(api_token),
        gateway_url=str(gateway_url).rstrip("/"),
        gateway_token=str(gateway_token),
        agent_id=str(agent_id),
        poll_interval=float(poll_interval),
        request_timeout=float(request_timeout),
    )


def _pick_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _pick_float(*values: Any) -> float:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return float(values[-1])


def _init_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_config(path)
    defaults = {
        "api_url": existing.get("api_url", "http://localhost:8000"),
        "gateway_url": existing.get("gateway_url", "http://127.0.0.1:18789"),
        "agent_id": existing.get("agent_id", "main"),
        "poll_interval": existing.get("poll_interval", 2.0),
        "timeout": existing.get("timeout", 600.0),
    }
    print("AgentEval config setup")
    api_url = _prompt("AgentEval API URL", defaults["api_url"])
    gateway_url = _prompt("OpenClaw Gateway URL", defaults["gateway_url"])
    agent_id = _prompt("OpenClaw agent id", defaults["agent_id"])
    poll_interval = float(_prompt("Poll interval seconds", str(defaults["poll_interval"])))
    timeout = float(_prompt("OpenClaw request timeout seconds", str(defaults["timeout"])))

    config = {
        "api_url": api_url,
        "gateway_url": gateway_url,
        "agent_id": agent_id,
        "poll_interval": poll_interval,
        "timeout": timeout,
    }
    path.write_text(json.dumps(config, indent=2))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    print(f"Wrote config to {path}")
    print("Tokens are read from env vars: AGENTEVAL_SESSION_TOKEN and OPENCLAW_GATEWAY_TOKEN.")


def _prompt(label: str, default: str) -> str:
    prompt = f"{label} [{default}]: "
    value = input(prompt).strip()
    return value or default


def _print_status(args: argparse.Namespace) -> None:
    cfg = _load_config()
    api_url = _pick_value(args.api_url, os.getenv("AGENTEVAL_API_URL"), cfg.get("api_url"))
    gateway_url = _pick_value(args.gateway_url, os.getenv("OPENCLAW_GATEWAY_URL"), cfg.get("gateway_url"))
    gateway_token = _pick_value(os.getenv("OPENCLAW_GATEWAY_TOKEN"), cfg.get("gateway_token"))

    session_token = _pick_value(
        os.getenv("AGENTEVAL_SESSION_TOKEN"),
        cfg.get("api_token"),
    )

    print("AgentEval status")
    _print_check("AgentEval API URL", api_url)
    _print_check("OpenClaw Gateway URL", gateway_url)
    _print_check("AGENTEVAL_SESSION_TOKEN", session_token)
    _print_check("OPENCLAW_GATEWAY_TOKEN", gateway_token)

    if api_url:
        _check_http(f"{api_url.rstrip('/')}/healthz", "AgentEval API health")
        if session_token:
            _check_http_auth(
                f"{api_url.rstrip('/')}/v1/sessions/me",
                "AgentEval session",
                session_token,
            )
    if gateway_url:
        _check_gateway(gateway_url.rstrip("/"), gateway_token)


def _print_check(label: str, value: Any) -> None:
    status = "OK" if value else "MISSING"
    print(f"[{status}] {label}")


def _check_http(url: str, label: str) -> None:
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                print(f"[OK] {label}")
                return
            print(f"[FAIL] {label} (status {resp.status_code})")
    except httpx.HTTPError as exc:
        print(f"[FAIL] {label} ({exc})")


def _check_http_auth(url: str, label: str, token: str) -> None:
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                print(f"[OK] {label}")
                return
            print(f"[FAIL] {label} (status {resp.status_code})")
    except httpx.HTTPError as exc:
        print(f"[FAIL] {label} ({exc})")


def _check_gateway(gateway_url: str, token: str | None) -> None:
    url = f"{gateway_url}/v1/models"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            if resp.status_code == 401 and token:
                resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                print("[OK] OpenClaw Gateway")
                return
            print(f"[FAIL] OpenClaw Gateway (status {resp.status_code})")
    except httpx.HTTPError as exc:
        print(f"[FAIL] OpenClaw Gateway ({exc})")


def _log_health_checks(config: ConnectorConfig, headers: dict[str, str]) -> None:
    logger = logging.getLogger("agenteval.connector")
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{config.api_url}/healthz")
            if resp.status_code == 200:
                logger.info("AgentEval API health OK")
            else:
                logger.warning("AgentEval API health check failed (%s)", resp.status_code)
    except httpx.HTTPError as exc:
        logger.warning("AgentEval API health check failed (%s)", exc)
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{config.gateway_url}/v1/models")
            if resp.status_code == 401:
                resp = client.get(
                    f"{config.gateway_url}/v1/models",
                    headers={"Authorization": f"Bearer {config.gateway_token}"},
                )
            if resp.status_code == 200:
                logger.info("OpenClaw Gateway OK")
            else:
                logger.warning("OpenClaw Gateway check failed (%s)", resp.status_code)
    except httpx.HTTPError as exc:
        logger.warning("OpenClaw Gateway check failed (%s)", exc)


def _start_services(args: argparse.Namespace) -> None:
    logger = logging.getLogger("agenteval.connector")
    config = _resolve_connect_config(args)
    api_url = _pick_value(args.api_url, os.getenv("AGENTEVAL_API_URL"), config.api_url)
    if not api_url:
        raise SystemExit("Missing api_url (set AGENTEVAL_API_URL or run agenteval init)")
    api_url = str(api_url).rstrip("/")
    api_host, api_port = _parse_api_host_port(api_url)
    if args.api_host:
        api_host = args.api_host
    if args.api_port:
        api_port = args.api_port

    started_api = False
    api_process: subprocess.Popen[str] | None = None
    if _api_health_ok(api_url):
        logger.info("AgentEval API already running at %s", api_url)
    else:
        logger.info("Starting AgentEval API on %s:%s", api_host, api_port)
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "server.app:app",
            "--host",
            api_host,
            "--port",
            str(api_port),
        ]
        if args.reload:
            cmd.append("--reload")
        api_process = subprocess.Popen(cmd)
        started_api = True
        _wait_for_api(api_url)

    try:
        run_connector(
            ConnectorConfig(
                api_url=api_url,
                api_token=config.api_token,
                gateway_url=config.gateway_url,
                gateway_token=config.gateway_token,
                agent_id=config.agent_id,
                poll_interval=config.poll_interval,
                request_timeout=config.request_timeout,
            )
        )
    finally:
        if started_api and api_process:
            logger.info("Shutting down AgentEval API")
            api_process.terminate()
            try:
                api_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api_process.kill()


def _parse_api_host_port(api_url: str) -> tuple[str, int]:
    parsed = urlparse(api_url if "://" in api_url else f"http://{api_url}")
    host = parsed.hostname or "0.0.0.0"
    port = parsed.port or 8000
    return host, port


def _api_health_ok(api_url: str) -> bool:
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{api_url.rstrip('/')}/healthz")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _wait_for_api(api_url: str, timeout_s: float = 15.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _api_health_ok(api_url):
            return
        time.sleep(0.5)
    raise SystemExit(f"AgentEval API failed to start at {api_url}")


def _create_session_command(args: argparse.Namespace) -> None:
    cfg = _load_config()
    api_url = _pick_value(args.api_url, os.getenv("AGENTEVAL_API_URL"), cfg.get("api_url"))
    if not api_url:
        raise SystemExit("Missing api_url (set AGENTEVAL_API_URL, run agenteval init, or pass --api-url)")
    api_url = str(api_url).rstrip("/")

    headers: dict[str, str] = {}
    bootstrap = os.getenv("AGENTEVAL_SESSION_BOOTSTRAP_TOKEN")
    if bootstrap:
        headers["X-AgentEval-Bootstrap"] = bootstrap

    payload = {"ttl_seconds": int(args.ttl_seconds), "max_evals": int(args.max_evals)}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{api_url}/v1/sessions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise SystemExit(f"Failed to create session: {exc}")

    token = data.get("session_token")
    session_id = data.get("session_id")
    expires_at = data.get("expires_at")
    max_evals = data.get("max_evals")
    print("Session created")
    print(f"  session_id: {session_id}")
    print(f"  expires_at: {expires_at}")
    print(f"  max_evals: {max_evals}")
    print("")
    print("Export token for connector/UI:")
    print(f'  export AGENTEVAL_SESSION_TOKEN=\"{token}\"')


if __name__ == "__main__":
    main()
