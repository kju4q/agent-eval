from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass(frozen=True)
class OpenClawMessage:
    role: str
    content: str


@dataclass(frozen=True)
class OpenClawChatResponse:
    raw: dict[str, Any]
    text: str


class OpenClawError(RuntimeError):
    pass


def chat_completions(
    *,
    base_url: str,
    token: str,
    agent_id: str,
    messages: list[OpenClawMessage],
    user: Optional[str] = None,
    timeout_s: float = 60.0,
) -> OpenClawChatResponse:
    token = "".join(token.split())
    payload: dict[str, Any] = {
        "model": f"openclaw:{agent_id}",
        "messages": [message.__dict__ for message in messages],
    }
    if user:
        payload["user"] = user

    url = base_url.rstrip("/") + "/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise OpenClawError(f"OpenClaw request failed: {exc}") from exc
    except ValueError as exc:
        raise OpenClawError("OpenClaw returned non-JSON response.") from exc

    text = _extract_text(data)
    return OpenClawChatResponse(raw=data, text=text)


def _extract_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    first = choices[0]
    message = first.get("message") or {}
    content = message.get("content")
    return content or ""
