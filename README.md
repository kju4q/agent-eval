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
   - `uvicorn server.app:app --host 0.0.0.0 --port 8000`
   - Set `AGENTEVAL_CONNECTOR_TOKEN` in your environment.
   - (Optional) Set `BESTBUY_API_KEY` for live price evidence.
4. Start the connector:
   - `agenteval connect --api-url http://localhost:8000 --api-token <token> --gateway-url http://127.0.0.1:18789 --gateway-token <gateway_token> --agent-id main`
