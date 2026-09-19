"""Optional BYOK polish. Never uploads images or history. Empty key is a full product."""
from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlparse

DEFAULT_POLISH_PROMPT = (
    "请在保留原意、专名和用户用词的前提下，整理这段口误或语音识别文字。"
    "不要扩写，不要编造没说过的内容。只返回改写后的正文。"
)


def chat_url(endpoint: str) -> str:
    url = (endpoint or "").rstrip("/")
    if not url:
        return ""
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


def url_join_note(endpoint: str) -> str:
    if not (endpoint or "").strip():
        return "已含 /chat/completions 的完整地址不会再拼接。"
    return f"实际请求 {chat_url(endpoint)}"


def extract_model_text(body: dict[str, Any], original: str) -> str:
    if not isinstance(body, dict):
        return ""
    direct = str(body.get("text") or "").strip()
    if direct:
        return direct
    choices = body.get("choices") or []
    if choices:
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


class ByokService:
    def __init__(
        self,
        *,
        endpoint: str = "",
        api_key: str = "",
        model: str = "",
        extra_prompt: str = "",
        temperature: float | None = None,
        post: Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]] | None = None,
    ):
        self.endpoint = (endpoint or "").strip()
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.temperature = temperature
        self.extra_prompt = (extra_prompt or "").strip()
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
            return {"status": "skipped", "reason": "no_key", "message": ERROR_LABELS["no_key"], "text": text}
        if draft_id != current_draft_id or revision != current_revision:
            return {"status": "stale", "reason": "draft moved", "text": None}
        if self._post is None:
            return {"status": "skipped", "reason": "no_transport", "message": ERROR_LABELS["no_transport"], "text": text}
        try:
            messages = [{"role": "system", "content": self.extra_prompt or DEFAULT_POLISH_PROMPT}]
            messages.append({"role": "user", "content": text})
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "input": text,
            }
            if self.temperature is not None:
                payload["temperature"] = self.temperature
            body = self._post(
                chat_url(self.endpoint),
                payload,
                {"Authorization": f"Bearer {self.api_key}"},
            )
        except Exception as exc:
            reason = classify_api_error(exc, self.api_key)
            return {
                "status": "error",
                "reason": reason,
                "message": ERROR_LABELS[reason],
                "text": text,
            }
        if draft_id != current_draft_id or revision != current_revision:
            return {"status": "stale", "reason": "draft moved after response", "text": None}
        out = extract_model_text(body or {}, text)
        if not out:
            return {
                "status": "error",
                "reason": "format",
                "message": ERROR_LABELS["format"],
                "text": text,
            }
        return {"status": "ok", "text": out, "reason": "", "model": self.model}


ERROR_LABELS = {
    "unauthorized": "密钥无效（401），原文仍可插入",
    "not_found": "接口不存在（404），原文仍可插入",
    "rate_limited": "请求过于频繁（429），原文仍可插入",
    "timeout": "模型超时，原文仍可插入",
    "tls": "证书或 TLS 失败，原文仍可插入",
    "format": "返回格式无法使用，原文仍可插入",
    "no_key": "未配置密钥，跳过模型，原文可用",
    "no_transport": "模型通道未接通，原文可用",
}


def classify_api_error(exc: Exception, api_key: str = "") -> str:
    raw = str(exc)
    if api_key and api_key in raw:
        raw = raw.replace(api_key, "…")
    message = raw.lower()
    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError) or "timeout" in message or "timeout" in name:
        return "timeout"
    if "ssl" in message or "tls" in message or "ssl" in name:
        return "tls"
    if "401" in message or "unauthorized" in message:
        return "unauthorized"
    if "404" in message or "not found" in message:
        return "not_found"
    if "429" in message or "rate" in message:
        return "rate_limited"
    return "format"


def redact_for_log(api_key: str) -> str:
    if not api_key:
        return ""
    return api_key[:2] + "…" if len(api_key) > 2 else "…"


def endpoint_host(url: str) -> str:
    return (urlparse(url or "").hostname or "").lower()
