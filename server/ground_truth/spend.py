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


def current_usage(provider: str) -> int:
    store = JobStore()
    return store.get_provider_calls(provider, _usage_day())


def consume(provider: str, amount: int = 1) -> int:
    store = JobStore()
    return store.increment_provider_calls(provider, _usage_day(), amount=amount)


def _usage_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

