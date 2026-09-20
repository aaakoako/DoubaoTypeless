"""Current draft snapshot is not last history, and missing images are not faked."""
from __future__ import annotations

import io

from PIL import Image

from doubao_typeless.app import V3App
from doubao_typeless.core.attempt import Attempt
from doubao_typeless.core.bundle import Draft
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.draft_snapshot import load_draft, save_draft
from doubao_typeless.services.delivery import DeliveryService


def _png(color=(20, 120, 110)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, format="PNG")
    return buf.getvalue()


def test_draft_restore_keeps_bytes_and_reports_missing(tmp_path):
    store = AssetStore(tmp_path / "assets")
    payload = _png()
    meta = store.put_png(payload, width=32, height=32, role="photo")
    draft = Draft("d1", "e1", 3, "phone", "current B", assets=[meta])
    save_draft(tmp_path, draft)
    loaded, missing = load_draft(tmp_path, store)
    assert loaded is not None
    assert loaded.text == "current B"
    assert missing == []
    assert store.get(loaded.assets[0]["asset_id"]) == payload
    (tmp_path / "assets" / f"{meta['asset_id']}.bin").unlink()
    loaded2, missing2 = load_draft(tmp_path, store)
    assert loaded2 is not None
    assert loaded2.text == "current B"
    assert missing2 == [meta["asset_id"]]
    # 缺图必须留下阻断占位，不能把用户的图文悄悄降为纯文字。
    assert len(loaded2.assets) == 1
    assert loaded2.assets[0]["asset_id"] == meta["asset_id"]
    assert loaded2.assets[0]["status"] == "failed"
    from doubao_typeless.core.bundle import freeze_bundle
    import pytest
    with pytest.raises(ValueError, match="IMAGE_EDITING"):
        freeze_bundle(loaded2, bundle_id="missing-must-block")


def test_recall_does_not_swallow_current_draft(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    app.draft.text = "稿B仍在输入"
    app.draft.revision = 4
    app.history.record(
        {
            "bundle_id": "bundle-a",
            "draft_id": "old",
            "epoch": "e",
            "revision": 1,
            "manifest_hash": "h",
            "text": "稿A已投递",
            "assets": [],
        },
        attempt_result="UNKNOWN",
    )
    app.recall_last()
    assert app.draft.text == "稿B仍在输入"
    assert app.bridge.last_bundle["text"] == "稿A已投递"
    assert app.bridge.last_bundle["bundle_id"] == "bundle-a"


def _stub_os_delivery(app, pasted, focus=("DT-S2-PasteTarget", "chatinput")):
    app._read_focus = lambda: focus
    app._saved_target = focus
    app.delivery._read_focus = lambda: focus
    app.delivery._paste = lambda: pasted.append("paste")
    app.delivery._set_text = lambda _t: None
    app.delivery._read_clipboard_text = None
    app.delivery._wait_modifiers = lambda: True
    app.delivery._is_locked = lambda: False
    app.delivery._observe_text = lambda: "unknown"


def test_unknown_result_does_not_auto_replay(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    pasted: list[str] = []
    _stub_os_delivery(app, pasted)
    app.bridge.last_bundle = {"bundle_id": "b", "text": "frozen A", "assets": []}
    app._last_attempt = Attempt("a", "i", "b", "s2_paste_target", result="UNKNOWN")
    app.insert_last()
    assert app._recovery_needed is True
    assert pasted == []
    app.confirm_recovery("full")
    assert "paste" in pasted


def test_target_change_stops_remaining_images():
    focuses = iter(
        [
            ("ComposerPane", "chatinput"),
            ("ComposerPane", "chatinput"),
            ("ComposerPane", "chatinput"),
            ("Notepad", "other"),
        ]
    )
    pasted = []
    svc = DeliveryService(
        paste=lambda: pasted.append("paste"),
        set_clipboard_image=lambda _b: pasted.append("image"),
        set_clipboard_text=lambda _t: pasted.append("text"),
        read_focus=lambda: next(focuses),
        observe_image=lambda: "observed",
        observe_text=lambda: "observed",
    )
    out = svc.run(
        Attempt("a", "i", "b", "cursor_windows"),
        {
            "text": "should not appear",
            "assets": [
                {"asset_id": "1", "bytes_data": b"\x89PNG"},
                {"asset_id": "2", "bytes_data": b"\x89PNG"},
            ],
        },
    )
    assert out.result == "PARTIAL"
    assert out.error_code == "TARGET_CHANGED"
    assert "text" not in pasted
    assert pasted.count("image") == 1


def test_two_unknown_windows_count_as_target_change():
    focuses = iter([
        ("DT-S2-PasteTarget", "notes-a"),
        ("DT-S2-PasteTarget", "notes-a"),
        ("DT-S2-PasteTarget", "notes-a"),
        ("DT-S2-PasteTarget", "notes-b"),
    ])
    pasted = []
    svc = DeliveryService(
        paste=lambda: pasted.append("paste"),
        set_clipboard_image=lambda _b: pasted.append("image"),
        set_clipboard_text=lambda _t: pasted.append("text"),
        read_focus=lambda: next(focuses),
        observe_image=lambda: "observed",
        observe_text=lambda: "observed",
    )
    out = svc.run(
        Attempt("a", "i", "b", "generic"),
        {
            "text": "should not appear",
            "assets": [
                {"asset_id": "1", "bytes_data": b"\x89PNG"},
                {"asset_id": "2", "bytes_data": b"\x89PNG"},
            ],
        },
    )
    assert out.error_code == "TARGET_CHANGED"
    assert "text" not in pasted
