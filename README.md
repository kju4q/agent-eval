# AgentEval

Pre-deployment evaluation for commerce agents.

Status: Work in progress (early demo).

## Demo
- Streamlit app: `app/streamlit_app.py`
- Run: `streamlit run app/streamlit_app.py`

## Production Deploy (Render)
- Blueprint: [`render.yaml`](/Users/qendresahoti/Downloads/agent-eval/render.yaml)
- Runbook: [`docs/deploy-render.md`](/Users/qendresahoti/Downloads/agent-eval/docs/deploy-render.md)

## Live OpenClaw (Local)
1. Enable OpenClaw chat completions in `~/.openclaw/openclaw.json`:
   - `gateway.http.endpoints.chatCompletions.enabled = true`
2. Restart OpenClaw Gateway.
3. Start AgentEval API:
   - `python3 -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload`
   - (Optional) Set `BESTBUY_API_KEY` for live price evidence.
4. Create a session token:
   - `agenteval session --api-url http://localhost:8000`
   - Export the returned token:
     - `export AGENTEVAL_SESSION_TOKEN=\"...\"`
5. Start the connector:
   - Recommended first-time setup:
     - `agenteval init` (writes `~/.agenteval/config.json`)
     - `agenteval status` (verifies API + gateway)
   - Then run:
     - `agenteval connect`
   - You can still override via flags:
     - `agenteval connect --api-url http://localhost:8000 --gateway-url http://127.0.0.1:18789 --agent-id main --timeout 600`
   - Increase `--timeout` for large prompts or slow browsing tasks.

## Single Command (API + Connector)
Once config + tokens are set:
```bash
agenteval start
```
Flags:
- `--api-host` / `--api-port` to override the API bind address
- `--reload` to enable uvicorn auto-reload

## Config File
`agenteval init` creates `~/.agenteval/config.json`:
```json
{
  "api_url": "http://localhost:8000",
  "gateway_url": "http://127.0.0.1:18789",
  "agent_id": "main",
  "poll_interval": 2.0,
  "timeout": 600.0
}
```
Tokens are read from env vars (see below).

## Environment Variables
- `AGENTEVAL_SESSION_TOKEN` (required) — session-scoped token for connector + UI/API access.
- `AGENTEVAL_SESSION_BOOTSTRAP_TOKEN` (required when `AGENTEVAL_REQUIRE_BOOTSTRAP=1`) — protects `/v1/sessions`.
- `AGENTEVAL_REQUIRE_BOOTSTRAP` (optional, default `0`) — when `1`, API startup fails if bootstrap token is missing.
- `OPENCLAW_GATEWAY_TOKEN` (required) — OpenClaw Gateway token for chat completions.
- `AGENTEVAL_API_URL` (optional) — overrides config.
- `AGENTEVAL_DEFAULT_API_URL` (optional, UI only) — pre-fills Live API URL in Streamlit.
- `OPENCLAW_GATEWAY_URL` (optional) — overrides config.
- `OPENCLAW_AGENT_ID` (optional) — overrides config.
- `AGENTEVAL_POLL_INTERVAL` (optional) — overrides config.
- `AGENTEVAL_TIMEOUT` (optional) — overrides config.
- `BESTBUY_API_KEY` (optional) — enables Best Buy price evidence.
- `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` (optional) — enables Amazon price evidence via DataForSEO.
- `AGENTEVAL_DATAFORSEO_DAILY_CALL_CAP` (optional, default `200`) — max DataForSEO calls per UTC day before fetches are blocked.
- `AGENTEVAL_DATAFORSEO_DAILY_USD_CAP` (optional, default `10.0`) — max estimated DataForSEO spend per UTC day before fetches are blocked.
- `AGENTEVAL_DATAFORSEO_COST_PER_CALL_USD` (optional, default `0.05`) — estimated USD cost used for daily spend accounting.
- `AGENTEVAL_EVIDENCE_KILL_SWITCH` (optional, default off) — hard-stop all paid evidence fetching.
- `AGENTEVAL_IP_WINDOW_SECONDS` (optional, default `60`) — window size for IP job-create throttling.
- `AGENTEVAL_IP_MAX_JOBS_PER_WINDOW` (optional, default `20`) — max job creates per IP per window.
- `AGENTEVAL_MAX_PROMPT_BYTES` (optional, default `32768`) — prompt payload hard cap.
- `AGENTEVAL_ALLOWED_ORIGINS` (optional, default `http://localhost:8501`) — comma-separated CORS allowlist.
- `AGENTEVAL_TRUST_PROXY_HEADERS` (optional, default `0`) — trust forwarded IP headers only when enabled.
- `AGENTEVAL_TRUSTED_PROXY_IPS` (optional) — comma-separated proxy IPs/CIDRs allowed to supply forwarded IP headers.
- `AGENTEVAL_PREFETCH_TIMEOUT_S` (optional, default `30`) — max seconds for background preview evidence prefetch.
- `AGENTEVAL_REVALIDATE_TIMEOUT_S` (optional, default `30`) — max seconds for completion-time chosen-retailer revalidation before preview fallback.
- `AGENTEVAL_REVALIDATE_FRESHNESS_SECONDS` (optional, default `60`) — skip completion-time revalidation when preview is fresher than this threshold.

## Evidence Health
Run results include provider health metadata:
- `provider_status`: state per provider (`ok`, `disabled`, `blocked`, `unavailable`)
- `evidence_status`: `degraded` when providers are unavailable/blocked and evidence is insufficient
- `evidence_degraded`: boolean summary for UI rendering
- `preview_status`: preview evidence lifecycle (`pending`, `ready`, `failed`)
- `revalidation_skipped_reason`: why completion-time selective revalidation was skipped
