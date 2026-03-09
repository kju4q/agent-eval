# Internal QA Checklist (Run Every Evaluation)

This is an internal checklist to keep demos and runs consistent and avoid mid-run fixes.
Do **not** skip steps. If any step fails, fix it before running an evaluation.

## Pre-Run (60–90s)
1. API is live  
   `curl -s http://localhost:8000/v1/healthz` → `ok`
2. OpenClaw gateway is live  
   `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18789/v1/models` → `200`
3. Connector is running  
   Should log “Waiting for jobs…” and **not** only 204s forever.
4. Required env vars set in the same shell as the API  
   `BESTBUY_API_KEY`, plus optional guardrails: `AGENTEVAL_DATAFORSEO_DAILY_CALL_CAP`, `AGENTEVAL_IP_MAX_JOBS_PER_WINDOW`
5. Session token created and exported  
   - `agenteval session --api-url http://localhost:8000`
   - `export AGENTEVAL_SESSION_TOKEN="..."`
6. UI inputs filled (no blanks)
   - AgentEval API URL
   - Session token
   - OpenClaw agent id
   - Product name
   - Budget (USD)
   - Allowed retailers
   - Prompt (must include “Chosen retailer + price + URL” section)

## Run (watch these while it runs)
1. Connector picks up the job (200 OK on `/v1/jobs/next`)
2. OpenClaw responds successfully (200 OK on `/v1/chat/completions`)
3. Job completes (200 OK on `/v1/jobs/{id}/complete`)

## Post-Run (30–60s)
1. Basic sanity (from API)
   - `status` = `completed`
   - `raw_output` present and contains:
     - Per-retailer section
     - Chosen retailer + price + URL
     - Within budget
     - Timestamp
2. Evidence sanity
   - `best_first_party_price_usd` present if any verified evidence exists
   - `best_first_party_source_type` and `confidence` present when best price exists
3. Score logic correctness
   - If `agent_choice_verified == false`:
     - `found_best_first_party_price` must be `null`
     - `price_accuracy` should render “Not evaluated”
     - `money_left_on_table_usd` must be `null`
4. UI consistency
   - If price accuracy is “Not evaluated”, Commerce IQ must be `N/A`
   - No conflicting fields (e.g., N/A accuracy + non-null money left)
