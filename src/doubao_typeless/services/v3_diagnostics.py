"""Redacted V3 diagnostics. No API keys, tokens, or user body text."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def snapshot(app) -> dict[str, Any]:
    stored = {}
    try:
        from doubao_typeless.storage.settings_store import load_settings

        stored = load_settings(app.data_dir)
    except Exception:
        stored = {}
    return {
        "data_dir": str(Path(app.data_dir)),
        "port": int(getattr(app, "port", 0) or 0),
        "sessions": len(getattr(app.auth, "sessions", {}) or {}),
        "history_count": len(getattr(app.history, "items", []) or []),
        "draft_revision": int(getattr(app.draft, "revision", 0) or 0),
        "has_text": bool(getattr(app.draft, "text", "")),
        "asset_count": len(getattr(app.draft, "assets", []) or []),
        "byok_configured": bool(getattr(app.byok, "available", lambda: False)()),
        "byok_model_set": bool(getattr(app.byok, "model", "")),
        "byok_endpoint_host": _host(stored.get("byok_endpoint") or getattr(app.byok, "endpoint", "")),
        "autostart": bool(stored.get("autostart")),
        "vocab_lines": _vocab_lines(app.data_dir),
    }


def write_snapshot(app, path: Path | None = None) -> Path:
    import json

    out = Path(path or (Path(app.data_dir) / "diagnostics.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot(app)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url or "").hostname or "").lower()


def _vocab_lines(data_dir) -> int:
    from doubao_typeless.storage.vocab_store import load_vocab, parse_mappings

    return len(parse_mappings(load_vocab(data_dir)))
