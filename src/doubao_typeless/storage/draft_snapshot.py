"""Persist the current draft separately from last delivered history."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from doubao_typeless.core.bundle import Draft
from doubao_typeless.services.assets import resolve_asset_refs
from doubao_typeless.storage.asset_store import AssetStore


def draft_path(data_dir: Path) -> Path:
    return Path(data_dir) / "draft.json"


def save_draft(data_dir: Path, draft: Draft) -> None:
    payload = {
        "draft_id": draft.draft_id,
        "epoch": draft.epoch,
        "revision": draft.revision,
        "editor_device_id": draft.editor_device_id,
        "text": draft.text,
        "asset_ids": [a.get("asset_id") for a in draft.assets if a.get("asset_id")],
    }
    path = draft_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_draft(data_dir: Path, store: AssetStore) -> tuple[Draft | None, list[str]]:
    path = draft_path(data_dir)
    if not path.is_file():
        return None, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, []
    refs = [str(x) for x in payload.get("asset_ids") or [] if x]
    missing: list[str] = []
    present: list[str] = []
    for ref in refs:
        try:
            store.get(ref)
            present.append(ref)
        except FileNotFoundError:
            missing.append(ref)
    assets: list[dict[str, Any]] = resolve_asset_refs(store, present) if present else []
    draft = Draft(
        draft_id=str(payload.get("draft_id") or ""),
        epoch=str(payload.get("epoch") or ""),
        revision=int(payload.get("revision") or 0),
        editor_device_id=str(payload.get("editor_device_id") or "pc"),
        text=str(payload.get("text") or ""),
        assets=assets,
    )
    return draft, missing
