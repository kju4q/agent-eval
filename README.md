# AgentEval

Pre-deployment evaluation for commerce agents.

Status: Work in progress (early demo).

## Demo
- Streamlit app: `app/streamlit_app.py`
- Run: `streamlit run app/streamlit_app.py`

## Live OpenClaw (Local)
1. Enable OpenClaw chat completions in `~/.openclaw/openclaw.json`:
   - `gateway.http.endpoints.chatCompletions.enabled = true`
2. Restart OpenClaw Gateway.
3. Start AgentEval API:
   - `python3 -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload`
   - Set `AGENTEVAL_CONNECTOR_TOKEN` in your environment.
   - (Optional) Set `BESTBUY_API_KEY` for live price evidence.
4. Start the connector:
   - Recommended first-time setup:
     - `agenteval init` (writes `~/.agenteval/config.json`)
     - `agenteval status` (verifies API + gateway)
   - Then run:
     - `agenteval connect`
   - You can still override via flags:
     - `agenteval connect --api-url http://localhost:8000 --gateway-url http://127.0.0.1:18789 --agent-id main --timeout 600`
   - Increase `--timeout` for large prompts or slow browsing tasks.

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
- `AGENTEVAL_CONNECTOR_TOKEN` (required) — token shared between API and connector.
- `OPENCLAW_GATEWAY_TOKEN` (required) — OpenClaw Gateway token for chat completions.
- `AGENTEVAL_API_URL` (optional) — overrides config.
- `OPENCLAW_GATEWAY_URL` (optional) — overrides config.
- `OPENCLAW_AGENT_ID` (optional) — overrides config.
- `AGENTEVAL_POLL_INTERVAL` (optional) — overrides config.
- `AGENTEVAL_TIMEOUT` (optional) — overrides config.
- `BESTBUY_API_KEY` (optional) — enables Best Buy price evidence.
- `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` (optional) — enables Amazon price evidence via DataForSEO.
