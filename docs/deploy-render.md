# Deploy on Render (API + UI)

This setup deploys two public services:
- `agenteval-api` (FastAPI for sessions/jobs/runs)
- `agenteval-ui` (Streamlit frontend)

## 1) Create from blueprint
1. Push this repo to GitHub.
2. In Render: **New** -> **Blueprint**.
3. Select this repo (uses [`render.yaml`](/Users/qendresahoti/Downloads/agent-eval/render.yaml)).

## 2) Set required env vars
### API service (`agenteval-api`)
- `AGENTEVAL_ALLOWED_ORIGINS` = your Streamlit URL (for example `https://app.agenteval.xyz`)
- `AGENTEVAL_REQUIRE_BOOTSTRAP` = `1`
- `AGENTEVAL_SESSION_BOOTSTRAP_TOKEN` = long random secret
- `BESTBUY_API_KEY` = Best Buy API key

Optional:
- `AGENTEVAL_TRUST_PROXY_HEADERS` = `1`
- `AGENTEVAL_TRUSTED_PROXY_IPS` = Render proxy IP/CIDR list (if you maintain one)
- `DATAFORSEO_LOGIN`
- `DATAFORSEO_PASSWORD`
- `AGENTEVAL_EVIDENCE_KILL_SWITCH` (`1` disables paid evidence calls)
- `AGENTEVAL_DATAFORSEO_DAILY_CALL_CAP`
- `AGENTEVAL_DATAFORSEO_DAILY_USD_CAP`

### UI service (`agenteval-ui`)
- `AGENTEVAL_DEFAULT_API_URL` = public URL of `agenteval-api`

## 3) Set domains
Recommended:
- UI on `app.agenteval.xyz`
- API on `api.agenteval.xyz`

DNS:
- `app` CNAME -> Render UI hostname
- `api` CNAME -> Render API hostname

## 4) Smoke test (production)
1. Open UI URL.
2. In a terminal on your machine:
   - `agenteval session --api-url https://api.agenteval.xyz`
   - export `AGENTEVAL_SESSION_TOKEN` + `OPENCLAW_GATEWAY_TOKEN`
   - `agenteval connect --api-url https://api.agenteval.xyz --gateway-url http://127.0.0.1:18789 --agent-id main --timeout 600`
3. In UI (Live mode), paste session token and run one eval.
4. Verify:
   - run reaches `completed`
   - run history row appears
   - provider status visible (`ok/disabled/blocked/unavailable`)
   - feedback submission succeeds
