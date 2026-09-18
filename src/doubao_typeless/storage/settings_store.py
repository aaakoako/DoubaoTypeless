"""Isolated V3 settings. Never writes daily-use config.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / "settings.json"


def load_settings(data_dir: Path) -> dict[str, Any]:
    path = settings_path(data_dir)
    if not path.is_file():
        return {"byok_endpoint": "", "byok_api_key": "", "hotkey_insert": "<alt>+i", "hotkey_recall": "<alt>+<shift>+i"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"byok_endpoint": "", "byok_api_key": "", "hotkey_insert": "<alt>+i", "hotkey_recall": "<alt>+<shift>+i"}
    return {
        "byok_endpoint": str(data.get("byok_endpoint") or ""),
        "byok_api_key": str(data.get("byok_api_key") or ""),
        "hotkey_insert": str(data.get("hotkey_insert") or "<alt>+i"),
        "hotkey_recall": str(data.get("hotkey_recall") or "<alt>+<shift>+i"),
    }


def save_settings(data_dir: Path, payload: dict[str, Any]) -> None:
    path = settings_path(data_dir)
    current = load_settings(data_dir)
    current.update({k: payload[k] for k in payload if k in {"byok_endpoint", "byok_api_key", "hotkey_insert", "hotkey_recall"}})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
