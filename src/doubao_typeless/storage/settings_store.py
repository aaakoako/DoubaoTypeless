"""Isolated V3 settings. Never writes daily-use config.json. API keys leave this file."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from doubao_typeless.storage.secret_store import get_secret, put_secret


def endpoint_authority(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse((url or "").strip())
    return ((parsed.scheme or "").lower(), (parsed.hostname or "").lower(), parsed.port)


def settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / "settings.json"


def load_settings(data_dir: Path) -> dict[str, Any]:
    defaults = {
        "byok_endpoint": "",
        "byok_api_key": "",
        "byok_model": "",
        "hotkey_insert": "<alt>+i",
        "hotkey_recall": "<alt>+<shift>+i",
        "hotkey_expand": "<alt>+<shift>+e",
        "hotkey_capture": "<alt>+<shift>+s",
        "autostart": False,
        "start_minimized": False,
        "phone_send_enabled": False,
        "phone_send_mode": "enter",
        "tray_explained": False,
        "device_nicknames": {},
        "byok_temperature": "",
        "byok_timeout": "",
        "byok_prompt": "",
    }
    path = settings_path(data_dir)
    if not path.is_file():
        out = dict(defaults)
        out["byok_api_key"] = get_secret(data_dir, "byok_api_key")
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    out = dict(defaults)
    for key in defaults:
        if key in data:
            out[key] = data[key]
    out["byok_endpoint"] = str(out.get("byok_endpoint") or "")
    out["byok_model"] = str(out.get("byok_model") or "")
    out["hotkey_insert"] = str(out.get("hotkey_insert") or "<alt>+i")
    out["hotkey_recall"] = str(out.get("hotkey_recall") or "<alt>+<shift>+i")
    out["hotkey_expand"] = str(out.get("hotkey_expand") or "<alt>+<shift>+e")
    out["hotkey_capture"] = str(out.get("hotkey_capture") or "<alt>+<shift>+s")
    out["autostart"] = bool(out.get("autostart"))
    out["start_minimized"] = bool(out.get("start_minimized"))
    out["tray_explained"] = bool(out.get("tray_explained"))
    names = out.get("device_nicknames")
    out["device_nicknames"] = {
        str(key): str(value).strip()
        for key, value in (names.items() if isinstance(names, dict) else [])
        if str(value).strip()
    }
    out["byok_temperature"] = str(out.get("byok_temperature") or "")
    out["byok_timeout"] = str(out.get("byok_timeout") or "")
    out["byok_prompt"] = str(out.get("byok_prompt") or "")
    file_key = str(data.get("byok_api_key") or "")
    stored_key = get_secret(data_dir, "byok_api_key")
    if file_key and not stored_key:
        put_secret(data_dir, "byok_api_key", file_key)
        stored_key = file_key
        _rewrite_without_secrets(path, data)
    out["byok_api_key"] = stored_key
    return out


def _rewrite_without_secrets(path: Path, data: dict[str, Any]) -> None:
    cleaned = dict(data)
    cleaned["byok_api_key"] = ""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


ALLOWED = {
    "byok_endpoint",
    "byok_api_key",
    "byok_model",
    "hotkey_insert",
    "hotkey_recall",
    "hotkey_expand",
    "hotkey_capture",
    "autostart",
    "start_minimized",
    "phone_send_enabled",
    "phone_send_mode",
    "tray_explained",
    "device_nicknames",
    "byok_temperature",
    "byok_timeout",
    "byok_prompt",
}


def save_settings(data_dir: Path, payload: dict[str, Any]) -> None:
    path = settings_path(data_dir)
    current = load_settings(data_dir)
    previous_endpoint = str(current.get("byok_endpoint") or "")
    previous_key = str(current.get("byok_api_key") or "")
    current.update({k: payload[k] for k in payload if k in ALLOWED})
    new_endpoint = str(current.get("byok_endpoint") or "")
    new_key = str(current.get("byok_api_key") or "")
    if endpoint_authority(previous_endpoint) != endpoint_authority(new_endpoint) and new_key == previous_key:
        current["byok_api_key"] = ""
    put_secret(data_dir, "byok_api_key", str(current.get("byok_api_key") or ""))
    on_disk = dict(current)
    on_disk["byok_api_key"] = ""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(on_disk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
