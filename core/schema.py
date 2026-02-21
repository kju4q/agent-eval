from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


ISO8601Format = str


def _parse_iso8601(value: str) -> datetime:
    # Support Zulu timestamps by converting to +00:00
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class AgentSpec:
    name: str
    version: Optional[str]
    run_mode: Optional[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentSpec":
        name = _require_str(data, "name")
        version = _opt_str(data, "version")
        run_mode = _opt_str(data, "run_mode")
        return cls(name=name, version=version, run_mode=run_mode)


@dataclass(frozen=True)
class ListingRef:
    retailer: str
    url: str
    listing_id: Optional[str]
    listing_id_type: Optional[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ListingRef":
        return cls(
            retailer=_require_str(data, "retailer"),
            url=_require_str(data, "url"),
            listing_id=_opt_str(data, "listing_id"),
            listing_id_type=_opt_str(data, "listing_id_type"),
        )


@dataclass(frozen=True)
class TaskRules:
    allow_third_party: bool
    allow_refurbished: bool
    require_full_set: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskRules":
        return cls(
            allow_third_party=_require_bool(data, "allow_third_party"),
            allow_refurbished=_require_bool(data, "allow_refurbished"),
            require_full_set=_require_bool(data, "require_full_set"),
        )


@dataclass(frozen=True)
class TaskSpec:
    product_name: str
    product_variant: Optional[str]
    budget_usd: Optional[float]
    currency: str
    allowed_retailers: list[str]
    rules: TaskRules
    canonical_listings: list[ListingRef]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskSpec":
        product_name = _require_str(data, "product_name")
        product_variant = _opt_str(data, "product_variant")
        budget_usd = _opt_float(data, "budget_usd")
        currency = _require_str(data, "currency")
        allowed_retailers = _require_str_list(data, "allowed_retailers")
        rules = TaskRules.from_dict(_require_dict(data, "rules"))
        canonical_listings = [
            ListingRef.from_dict(item)
            for item in _opt_list(data, "canonical_listings")
        ]
        return cls(
            product_name=product_name,
            product_variant=product_variant,
            budget_usd=budget_usd,
            currency=currency,
            allowed_retailers=allowed_retailers,
            rules=rules,
            canonical_listings=canonical_listings,
        )


@dataclass(frozen=True)
class AgentOutput:
    raw_text: str
    captured_at: ISO8601Format
    source: Optional[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentOutput":
        raw_text = _require_str(data, "raw_text")
        captured_at = _require_str(data, "captured_at")
        _parse_iso8601(captured_at)
        source = _opt_str(data, "source")
        return cls(raw_text=raw_text, captured_at=captured_at, source=source)


@dataclass(frozen=True)
class EvidenceItem:
    retailer: str
    url: str
    price_usd: Optional[float]
    availability: Optional[str]
    seller: Optional[str]
    timestamp: ISO8601Format
    variant_match: Optional[bool]
    listing_id: Optional[str]
    listing_id_type: Optional[str]
    notes: Optional[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceItem":
        timestamp = _require_str(data, "timestamp")
        _parse_iso8601(timestamp)
        return cls(
            retailer=_require_str(data, "retailer"),
            url=_require_str(data, "url"),
            price_usd=_opt_float(data, "price_usd"),
            availability=_opt_str(data, "availability"),
            seller=_opt_str(data, "seller"),
            timestamp=timestamp,
            variant_match=_opt_bool(data, "variant_match"),
            listing_id=_opt_str(data, "listing_id"),
            listing_id_type=_opt_str(data, "listing_id_type"),
            notes=_opt_str(data, "notes"),
        )


@dataclass(frozen=True)
class CaseStudy:
    version: str
    id: str
    title: str
    created_at: ISO8601Format
    agent: AgentSpec
    task: TaskSpec
    agent_output: AgentOutput
    evidence: list[EvidenceItem]
    notes: Optional[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaseStudy":
        version = _require_str(data, "version")
        id_value = _require_str(data, "id")
        title = _require_str(data, "title")
        created_at = _require_str(data, "created_at")
        _parse_iso8601(created_at)
        agent = AgentSpec.from_dict(_require_dict(data, "agent"))
        task = TaskSpec.from_dict(_require_dict(data, "task"))
        agent_output = AgentOutput.from_dict(_require_dict(data, "agent_output"))
        evidence = [
            EvidenceItem.from_dict(item)
            for item in _require_list(data, "evidence")
        ]
        notes = _opt_str(data, "notes")
        return cls(
            version=version,
            id=id_value,
            title=title,
            created_at=created_at,
            agent=agent,
            task=task,
            agent_output=agent_output,
            evidence=evidence,
            notes=notes,
        )


class SchemaError(ValueError):
    pass


def _require_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise SchemaError(f"Expected object for '{key}'.")
    return value


def _require_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise SchemaError(f"Expected list for '{key}'.")
    return value


def _opt_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise SchemaError(f"Expected list for '{key}'.")
    return value


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"Expected non-empty string for '{key}'.")
    return value.strip()


def _opt_str(data: dict[str, Any], key: str) -> Optional[str]:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SchemaError(f"Expected string for '{key}'.")
    return value.strip()


def _require_bool(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise SchemaError(f"Expected boolean for '{key}'.")
    return value


def _opt_bool(data: dict[str, Any], key: str) -> Optional[bool]:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise SchemaError(f"Expected boolean for '{key}'.")
    return value


def _opt_float(data: dict[str, Any], key: str) -> Optional[float]:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raise SchemaError(f"Expected number for '{key}'.")


def _require_str_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise SchemaError(f"Expected non-empty list for '{key}'.")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SchemaError(f"Expected string items for '{key}'.")
        items.append(item.strip())
    return items
