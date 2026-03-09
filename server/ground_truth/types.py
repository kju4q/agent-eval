from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.schema import EvidenceItem


@dataclass(frozen=True)
class ProviderFetchStatus:
    provider: str
    state: str
    detail: Optional[str] = None
    calls_today: Optional[int] = None
    daily_cap: Optional[int] = None
    spend_usd_today: Optional[float] = None
    daily_spend_cap_usd: Optional[float] = None

    def as_dict(self) -> dict:
        payload = {
            "provider": self.provider,
            "state": self.state,
        }
        if self.detail:
            payload["detail"] = self.detail
        if self.calls_today is not None:
            payload["calls_today"] = self.calls_today
        if self.daily_cap is not None:
            payload["daily_cap"] = self.daily_cap
        if self.spend_usd_today is not None:
            payload["spend_usd_today"] = round(float(self.spend_usd_today), 4)
        if self.daily_spend_cap_usd is not None:
            payload["daily_spend_cap_usd"] = round(float(self.daily_spend_cap_usd), 4)
        return payload


@dataclass(frozen=True)
class GroundTruthResult:
    evidence: list[EvidenceItem]
    provider_status: list[ProviderFetchStatus]

    @property
    def degraded(self) -> bool:
        return any(status.state != "ok" for status in self.provider_status)
