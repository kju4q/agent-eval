from __future__ import annotations

import re
from datetime import datetime, timezone


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _normalize_query(value: str) -> str:
    tokens = _tokenize(value)
    if not tokens:
        return value
    return " ".join(tokens)
