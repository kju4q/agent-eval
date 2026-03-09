from __future__ import annotations

import os
from datetime import datetime, timezone

from server.db import JobStore


PROVIDER_DATAFORSEO = "dataforseo"


def is_kill_switch_enabled() -> bool:
    return os.getenv("AGENTEVAL_EVIDENCE_KILL_SWITCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def dataforseo_daily_cap() -> int:
    raw = os.getenv("AGENTEVAL_DATAFORSEO_DAILY_CALL_CAP", "200")
    try:
        value = int(raw)
    except ValueError:
        return 200
    return max(1, value)


def dataforseo_daily_usd_cap() -> float:
    raw = os.getenv("AGENTEVAL_DATAFORSEO_DAILY_USD_CAP", "10.0")
    try:
        value = float(raw)
    except ValueError:
        return 10.0
    return max(0.01, value)


def dataforseo_cost_per_call_usd() -> float:
    raw = os.getenv("AGENTEVAL_DATAFORSEO_COST_PER_CALL_USD", "0.05")
    try:
        value = float(raw)
    except ValueError:
        return 0.05
    return max(0.0, value)


def current_usage(provider: str) -> int:
    store = JobStore()
    return store.get_provider_calls(provider, _usage_day())


def consume(provider: str, amount: int = 1) -> int:
    store = JobStore()
    return store.increment_provider_calls(provider, _usage_day(), amount=amount)


def current_spend_usd(provider: str) -> float:
    store = JobStore()
    return store.get_provider_spend_usd(provider, _usage_day())


def consume_spend_usd(provider: str, amount_usd: float) -> float:
    store = JobStore()
    return store.increment_provider_spend_usd(provider, _usage_day(), amount_usd=amount_usd)


def _usage_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
