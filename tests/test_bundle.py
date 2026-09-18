"""V3-03: expose bundle freeze, conflict, exact text, and archive isolation risks."""
from __future__ import annotations

import copy
import uuid

import pytest

from doubao_typeless.core.bundle import (
    Draft,
    archive_if_match,
    canonical_manifest_hash,
    freeze_bundle,
    apply_draft_update,
)


def _ids():
    return {
        "device_id": str(uuid.UUID(int=2)),
        "draft_id": str(uuid.UUID(int=3)),
        "epoch": str(uuid.UUID(int=4)),
    }


def test_freeze_is_isolated_from_later_draft_edits():
    ids = _ids()
    draft = Draft(
        draft_id=ids["draft_id"],
        epoch=ids["epoch"],
        revision=3,
        editor_device_id=ids["device_id"],
        text="r3 body\n",
        assets=[
            {
                "asset_id": str(uuid.UUID(int=5)),
                "render_revision": 1,
                "sha256": "a" * 64,
                "mime": "image/png",
                "bytes": 10,
                "width": 2,
                "height": 2,
                "role": "whiteboard",
            }
        ],
    )
    bundle = freeze_bundle(draft, bundle_id=str(uuid.UUID(int=1)))
    draft.text = "r4 changed"
    draft.revision = 4
    draft.assets.reverse()
    assert bundle["text"] == "r3 body\n"
    assert bundle["revision"] == 3
    assert bundle["assets"][0]["role"] == "whiteboard"
    assert bundle["auto_send"] is False


def test_same_revision_different_hash_is_rejected():
    ids = _ids()
    draft = Draft(
        draft_id=ids["draft_id"],
        epoch=ids["epoch"],
        revision=2,
        editor_device_id=ids["device_id"],
        text="acked",
        assets=[],
    )
    apply_draft_update(draft, {"text": "acked", "revision": 2, "asset_refs": []})
    with pytest.raises(ValueError, match="conflict"):
        apply_draft_update(draft, {"text": "other", "revision": 2, "asset_refs": []})
    assert draft.text == "acked"


def test_text_roundtrip_preserves_whitespace_emoji_and_mixed_scripts():
    sample = "  Opus 和 Image2\n🙂\t尾换行\n"
    ids = _ids()
    draft = Draft(
        draft_id=ids["draft_id"],
        epoch=ids["epoch"],
        revision=1,
        editor_device_id=ids["device_id"],
        text=sample,
        assets=[],
    )
    bundle = freeze_bundle(draft, bundle_id=str(uuid.UUID(int=9)))
    assert bundle["text"] == sample
    assert "\t" in bundle["text"]
    digest = canonical_manifest_hash(bundle)
    again = canonical_manifest_hash(copy.deepcopy(bundle))
    assert digest == again
    assert digest == bundle["manifest_hash"]


def test_archive_receipt_for_r3_does_not_clear_r4():
    ids = _ids()
    draft = Draft(
        draft_id=ids["draft_id"],
        epoch=ids["epoch"],
        revision=4,
        editor_device_id=ids["device_id"],
        text="new r4",
        assets=[],
    )
    r3 = {
        "draft_id": ids["draft_id"],
        "epoch": ids["epoch"],
        "revision": 3,
        "manifest_hash": "b" * 64,
    }
    kept = archive_if_match(draft, r3, current_hash="c" * 64)
    assert kept is draft
    assert draft.text == "new r4"
    assert draft.revision == 4
