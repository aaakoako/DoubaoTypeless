"""Optional BYOK polish. Never uploads images or history. Empty key is a full product."""
from __future__ import annotations

from typing import Any, Callable


class ByokService:
    def __init__(
        self,
        *,
        endpoint: str = "",
        api_key: str = "",
        post: Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]] | None = None,
    ):
        self.endpoint = (endpoint or "").strip()
        self.api_key = (api_key or "").strip()
        self._post = post

    def available(self) -> bool:
        return bool(self.endpoint and self.api_key)

    def polish(
        self,
        text: str,
        *,
        draft_id: str,
        revision: int,
        current_draft_id: str,
        current_revision: int,
        images: list | None = None,
    ) -> dict[str, Any]:
        if images:
            raise ValueError("byok does not accept images")
        if not self.available():
            return {"status": "skipped", "reason": "no_key", "text": text}
        if draft_id != current_draft_id or revision != current_revision:
            return {"status": "stale", "reason": "draft moved", "text": None}
        if self._post is None:
            return {"status": "skipped", "reason": "no_transport", "text": text}
        try:
            body = self._post(
                self.endpoint,
                {"model": "user", "input": text},
                {"Authorization": f"Bearer {self.api_key}"},
            )
        except Exception as exc:
            return {"status": "error", "reason": classify_api_error(exc), "text": text}
        if draft_id != current_draft_id or revision != current_revision:
            return {"status": "stale", "reason": "draft moved after response", "text": None}
        out = str(body.get("text") or text)
        return {"status": "ok", "text": out, "reason": ""}


def classify_api_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "401" in message or "unauthorized" in message:
        return "unauthorized"
    if "404" in message:
        return "not_found"
    if "429" in message:
        return "rate_limited"
    if "timeout" in message:
        return "timeout"
    if "ssl" in message or "tls" in message:
        return "tls"
    return "format"


def redact_for_log(api_key: str) -> str:
    if not api_key:
        return ""
    return api_key[:2] + "…" if len(api_key) > 2 else "…"
