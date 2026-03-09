# AgentEval OpenClaw v1 Production Gate

Use this as the launch blocker checklist for the public OpenClaw v1 release.
Every item is binary: `PASS` or `FAIL`.

## Rules
- Ship only if all `Critical` items are `PASS`.
- `High` items must be `PASS` before public launch.
- `Medium` items can be completed within 48h after launch only if explicitly accepted.
- Owner:
  - `System`: code/runtime behavior must enforce it.
  - `Operator`: infra/deployment/config/process responsibility.

## Critical (Hard Blockers)
| ID | Gate | Owner | PASS Criteria (Binary) | Status |
|---|---|---|---|---|
| C1 | Session-scoped job/result isolation | System | A connector for Session A cannot fetch or complete jobs for Session B; `/v1/runs/{id}` returns 403/404 for non-owner session. | FAIL |
| C2 | Per-session connector auth (no global connector token) | System | Connector authenticates with session token; global token cannot access cross-session jobs. | FAIL |
| C3 | Session token quality + TTL | System | Tokens are crypto-random (>=128 bits), expire automatically, and session has max eval count. | FAIL |
| C4 | Trust boundary enforced | Operator | Public traffic reaches Streamlit only; FastAPI is private/internal and not directly internet-accessible. | FAIL |
| C5 | Cost guardrails for paid evidence APIs | System + Operator | Per-session quota, daily spend cap, and kill-switch all work; when cap is reached, system enters explicit degraded mode. | FAIL |
| C6 | Parser safety against adversarial output | System | Malformed/contradictory agent output cannot produce false verified states; parser falls back to safe null/degraded fields. | FAIL |
| C7 | XSS-safe rendering of raw output | System | Raw agent output is escaped/sanitized in UI/PDF; no arbitrary HTML/JS execution path. | FAIL |

## High (Must Pass Before Public)
| ID | Gate | Owner | PASS Criteria (Binary) | Status |
|---|---|---|---|---|
| H1 | Payload size limits | System | Job creation rejects oversized payloads with 413/validation error (e.g. >32KB prompt/body limits). | FAIL |
| H2 | Structured failure states | System | Every failed run has machine-readable error code + user-visible reason; no silent null-only failures. | FAIL |
| H3 | Ground-truth degraded mode visibility | System | If Best Buy/DataForSEO unavailable/unconfigured, result explicitly marks evidence degraded (not silent empty evidence). | FAIL |
| H4 | Rate limiting + abuse controls | System | Session-level eval caps enforced; IP throttling active; abuse cannot trigger unbounded job creation. | FAIL |
| H5 | Production-safe error surface | Operator + System | Debug/traceback responses disabled in prod; API returns sanitized errors only. | FAIL |
| H6 | SSRF egress protections | System + Operator | Outbound requests blocked to private/link-local/metadata ranges; allowlist used where applicable. | FAIL |
| H7 | Idempotent and safe job completion | System | Duplicate/late `/complete` calls do not corrupt state; invalid state transitions are rejected. | FAIL |
| H8 | Run history + feedback capture | System | Users can view their own run history and submit feedback linked to run_id with size/rate limits. | FAIL |

## Medium (Complete Before/Immediately After Launch Window)
| ID | Gate | Owner | PASS Criteria (Binary) | Status |
|---|---|---|---|---|
| M1 | Feedback spam guard | System | Feedback endpoint enforces max length and per-session/IP submission limits. | FAIL |
| M2 | Log data minimization | System + Operator | Tokens redacted; raw output truncated/redacted in logs; retention policy documented. | FAIL |
| M3 | Dependency security audit | Operator | `pip-audit` (or equivalent) run, findings triaged, critical vulns resolved/accepted with rationale. | FAIL |
| M4 | Monitoring + alerting | Operator | Alerts exist for timeout spikes, evidence-fetch failure spikes, and spend spikes. | FAIL |
| M5 | Fresh-env smoke run | Operator | One full E2E run from clean machine/account succeeds with documented steps. | FAIL |

## Launch Decision
- Launch allowed only when: `C* = PASS` and `H* = PASS`.
- If any critical/high item is `FAIL`, launch is blocked.

