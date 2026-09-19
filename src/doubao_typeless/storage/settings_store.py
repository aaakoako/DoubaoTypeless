"""Isolated V3 settings. Never writes daily-use config.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / "settings.json"


def load_settings(data_dir: Path) -> dict[str, Any]:
    defaults = {
        "byok_endpoint": "",
        "byok_api_key": "",
        "byok_model": "",
        "hotkey_insert": "<alt>+i",
        "hotkey_recall": "<alt>+<shift>+i",
        "autostart": False,
        "start_minimized": False,
        "tray_explained": False,
    }
    path = settings_path(data_dir)
    if not path.is_file():
        return dict(defaults)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(defaults)
    out = dict(defaults)
    for key in defaults:
        if key in data:
            out[key] = data[key]
    out["byok_endpoint"] = str(out.get("byok_endpoint") or "")
    out["byok_api_key"] = str(out.get("byok_api_key") or "")
    out["byok_model"] = str(out.get("byok_model") or "")
    out["hotkey_insert"] = str(out.get("hotkey_insert") or "<alt>+i")
    out["hotkey_recall"] = str(out.get("hotkey_recall") or "<alt>+<shift>+i")
    out["autostart"] = bool(out.get("autostart"))
    out["start_minimized"] = bool(out.get("start_minimized"))
    out["tray_explained"] = bool(out.get("tray_explained"))
    return out


ALLOWED = {
    "byok_endpoint",
    "byok_api_key",
    "byok_model",
    "hotkey_insert",
    "hotkey_recall",
    "autostart",
    "start_minimized",
    "tray_explained",
}


def save_settings(data_dir: Path, payload: dict[str, Any]) -> None:
    path = settings_path(data_dir)
    current = load_settings(data_dir)
    current.update({k: payload[k] for k in payload if k in ALLOWED})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
