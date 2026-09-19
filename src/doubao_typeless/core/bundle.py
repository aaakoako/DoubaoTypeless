"""Draft, frozen DeliveryBundle, and archive matching."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

PROTOCOL = 3
TEXT_UTF8_LIMIT = 65536
MAX_ASSETS = 6
MAX_ASSET_BYTES = 8 * 1024 * 1024
MAX_BUNDLE_IMAGE_BYTES = 24 * 1024 * 1024


@dataclass
class Draft:
    draft_id: str
    epoch: str
    revision: int
    editor_device_id: str
    text: str
    assets: list[dict[str, Any]] = field(default_factory=list)
    acked_revision: int | None = None
    acked_hash: str | None = None


def _sorted(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sorted(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_sorted(item) for item in value]
    return value


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        _sorted(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_manifest_hash(bundle: dict[str, Any]) -> str:
    clean = {k: v for k, v in bundle.items() if k != "manifest_hash"}
    return hashlib.sha256(canonical_bytes(clean)).hexdigest()


def draft_content_hash(text: str, asset_refs: list[Any]) -> str:
    return hashlib.sha256(
        canonical_bytes({"text": text, "asset_refs": asset_refs})
    ).hexdigest()


def freeze_bundle(draft: Draft, *, bundle_id: str) -> dict[str, Any]:
    text = draft.text
    if len(text.encode("utf-8")) > TEXT_UTF8_LIMIT:
        raise ValueError("text byte limit")
    assets = copy.deepcopy(draft.assets)
    processed = [a for a in assets if str(a.get("role") or "") not in {"screenshot", "source"}]
    if processed and len(processed) < len(assets):
        assets = processed
    if len(assets) > MAX_ASSETS:
        raise ValueError("more than six")
    if not text.strip() and not assets:
        raise ValueError("empty bundle")
    for asset in assets:
        status = str(asset.get("status") or "ready")
        if status in {"queued", "editing", "failed", "dirty"}:
            raise ValueError("IMAGE_EDITING")
    ids = [a["asset_id"] for a in assets]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate asset id")
    captions = []
    for index, asset in enumerate(assets, start=1):
        caption = str(asset.get("caption") or "").strip()
        if caption:
            captions.append(f"图{index}：{caption}")
    if captions:
        extra = "\n".join(captions)
        text = f"{text.rstrip()}\n\n{extra}" if text.strip() else extra
    if sum(int(a.get("bytes", 0)) for a in assets) > MAX_BUNDLE_IMAGE_BYTES:
        raise ValueError("total byte limit")
    bundle = {
        "protocol": PROTOCOL,
        "bundle_id": bundle_id,
        "device_id": draft.editor_device_id,
        "draft_id": draft.draft_id,
        "epoch": draft.epoch,
        "revision": int(draft.revision),
        "text": text,
        "assets": assets,
        "auto_send": False,
    }
    bundle["manifest_hash"] = canonical_manifest_hash(bundle)
    return bundle


def apply_draft_update(draft: Draft, update: dict[str, Any]) -> Draft:
    revision = update["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise ValueError("invalid revision")
    text = update.get("text", draft.text)
    if not isinstance(text, str):
        raise ValueError("invalid text")
    refs = update.get("asset_refs", [a["asset_id"] for a in draft.assets])
    incoming_hash = draft_content_hash(text, refs)
    if revision < draft.revision:
        return draft
    if revision == draft.revision:
        current_hash = draft_content_hash(
            draft.text, [a["asset_id"] for a in draft.assets]
        )
        if incoming_hash != current_hash:
            raise ValueError("conflict: same revision different hash")
        draft.acked_revision = revision
        draft.acked_hash = incoming_hash
        return draft
    draft.text = text
    draft.revision = revision
    if "assets" in update:
        draft.assets = copy.deepcopy(update["assets"])
    draft.acked_revision = revision
    draft.acked_hash = incoming_hash
    return draft


def archive_if_match(draft: Draft, receipt: dict[str, Any], *, current_hash: str) -> Draft:
    same_identity = (
        receipt.get("draft_id") == draft.draft_id
        and receipt.get("epoch") == draft.epoch
        and receipt.get("revision") == draft.revision
        and receipt.get("manifest_hash") == current_hash
    )
    if not same_identity:
        return draft
    draft.text = ""
    draft.assets = []
    draft.revision += 1
    draft.epoch = str(uuid.uuid4())
    return draft
