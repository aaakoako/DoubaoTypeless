"""Read-only legacy config migration. Never writes daily-use files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LEGACY_SKIP_POLISH = "<alt>+<shift>+i"
NEW_RECALL = "<alt>+<shift>+i"
NEW_INSERT = "<alt>+i"


def migrate_hotkeys(old: dict[str, Any]) -> dict[str, Any]:
    insert = str(old.get("hotkey_insert") or NEW_INSERT)
    return {
        "insert": insert,
        "recall": NEW_RECALL,
        "legacy_skip_polish_removed": True,
        "note": "Alt+Shift+I 现为召回上次图文，不再同时绑定跳过纠错",
        "old_toggle_review": old.get("hotkey_toggle_review") or "",
    }


def inspect_legacy_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False, "learn_enabled": False, "hotkeys": migrate_hotkeys({})}
    before = path.read_bytes()
    data = json.loads(before.decode("utf-8"))
    after = path.read_bytes()
    if after != before:
        raise RuntimeError("migration must not write the legacy file")
    return {
        "present": True,
        "learn_enabled": bool(data.get("learn_enabled")),
        "start_learn": False,
        "hotkeys": migrate_hotkeys(data),
        "api_key_present": bool(data.get("llm_api_key") or data.get("learn_api_key")),
    }
