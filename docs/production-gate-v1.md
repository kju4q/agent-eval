# AgentEval OpenClaw v1 Production Gate

Use this as the current launch/readiness checklist for the public OpenClaw-backed AgentEval v1.
Every item is binary: `PASS` or `FAIL`.

## Rules
- `Critical` items must be `PASS` for public use.
- `High` items should be `PASS` for sustained public usage, but do not all block a controlled beta.
- `Owner`
- `System`: enforced by code/runtime behavior.
- `Operator`: enforced by deployment/config/process.

## Critical
| ID | Gate | Owner | PASS Criteria | Status |
|---|---|---|---|---|
| C1 | Session-scoped job/result isolation | System | A connector for Session A cannot fetch/complete jobs for Session B; runs/history/feedback are session-scoped. | PASS |
| C2 | No global connector token dependency | System | Connector authenticates with session token; cross-session access via shared connector secret is impossible. | PASS |
| C3 | Session token quality + TTL | System | Tokens are crypto-random, hashed at rest, expire automatically, and sessions have max eval count. | PASS |
| C4 | Bootstrap-protected session issuance in prod | Operator + System | Production API requires bootstrap token for `/v1/sessions`; missing bootstrap config fails closed in deployed env. | PASS |
| C5 | Prompt/input size bounds | System | Oversized job prompts are rejected with explicit error. | PASS |
| C6 | Parser fails safe | System | Malformed or contradictory agent output cannot produce false verified states; parser falls back to null/unverified paths. | PASS |
| C7 | Raw output is rendered safely | System | Raw agent output is displayed as escaped text/code, not executable HTML. | PASS |

## High
| ID | Gate | Owner | PASS Criteria | Status |
|---|---|---|---|---|
| H1 | Session quota enforcement | System | Sessions enforce max eval count and expired/revoked sessions cannot create jobs. | PASS |
| H2 | IP throttling on job creation | System | Public job creation is rate-limited per IP window. | PASS |
| H3 | Explicit degraded evidence state | System | Missing/blocked/unconfigured providers surface as degraded/provider status instead of silent empty evidence. | PASS |
| H4 | Idempotent job completion | System | Duplicate `/complete` calls do not corrupt run state. | PASS |
| H5 | Sanitized error surface | System + Operator | API returns sanitized 4xx/5xx responses without tracebacks in response bodies. | PASS |
| H6 | SSRF egress protections | System | Evidence fetchers only access allowlisted hosts over HTTPS and reject private/link-local targets. | PASS |
| H7 | Feedback capture + limits | System | Feedback is tied to run/session and has size/rate limits. | PASS |
| H8 | Run history available | System | Users can see their own runs and statuses. | PASS |

## Medium
| ID | Gate | Owner | PASS Criteria | Status |
|---|---|---|---|---|
| M1 | Session creation abuse throttling | System | `/v1/sessions` has explicit rate limiting in addition to bootstrap protection. | FAIL |
| M2 | Dependency audit completed in networked environment | Operator | `pip-audit` or equivalent completed and findings triaged. | FAIL |
| M3 | Log data minimization | System + Operator | Sensitive values are not over-logged; retention/visibility is understood. | PARTIAL |
| M4 | Monitoring + alerting | Operator | Alerts exist for evidence provider failures, timeout spikes, and spend spikes. | FAIL |
| M5 | Broader evaluator coverage | System | More than one real evaluation dimension exists beyond price accuracy. | FAIL |

## Current Interpretation
- OpenClaw v1 price-evaluation beta is live-capable.
- The largest remaining product gap is not core security; it is narrow evaluator scope.
- The largest remaining operational gap is explicit session-creation throttling plus full dependency audit.

## Next Product Priority
1. Build `Safety / Policy Compliance v1`
2. Add tests for safety paths
3. Surface safety as a distinct UI result
4. Revisit ACP after that
