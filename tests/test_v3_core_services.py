"""Auth, asset, delivery and focus policy tests for V3-04..08/15."""
from __future__ import annotations

import pytest

from doubao_typeless.core.attempt import Attempt
from doubao_typeless.core.policy import classify_focus, may_inject, recovery_choice
from doubao_typeless.services.delivery import DeliveryService, VK_RETURN
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService, looks_like_key_script


def test_pairing_mismatch_and_insert_grant(tmp_path=None):
    auth = AuthService()
    code = auth.new_pairing_challenge()
    with pytest.raises(ValueError, match="mismatch"):
        auth.complete_pairing("nope")
    code = auth.new_pairing_challenge()
    session = auth.complete_pairing(code, allow_insert=False)
    with pytest.raises(ValueError, match="not granted"):
        auth.authorize(session.session_id, session.token, "insert")
    session.allow_insert = True
    auth.authorize(session.session_id, session.token, "insert")
    nonce = auth.issue_nonce(session)
    auth.consume_nonce(session, nonce)
    with pytest.raises(ValueError):
        auth.consume_nonce(session, nonce)
    assert looks_like_key_script({"keys": ["CTRL", "V"]}) is True


def test_asset_store_atomic_and_magic(tmp_path):
    store = AssetStore(tmp_path / "assets")
    with pytest.raises(ValueError, match="magic"):
        store.put_png(b"not-an-image", width=1, height=1, role="photo")
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00" * 20
    )
    meta = store.put_png(png, width=2, height=2, role="whiteboard")
    assert store.get(meta["asset_id"]) == png
    assert not list(tmp_path.joinpath("assets").glob("*.tmp"))


def test_code_focus_does_not_inject_images():
    assert classify_focus("Chrome_WidgetWin_1", "EditorDocument") == "code"
    assert may_inject("code", wants_images=True) is False
    assert may_inject("composer", wants_images=True) is True


def test_delivery_unknown_image_does_not_paste_text_or_enter():
    pasted = []
    keys = []

    def paste():
        pasted.append("paste")

    svc = DeliveryService(
        paste=paste,
        set_clipboard_image=lambda _b: pasted.append("image"),
        set_clipboard_text=lambda _t: pasted.append("text"),
        read_focus=lambda: ("ComposerPane", "chatinput"),
        observe_image=lambda: "unknown",
        send_key=lambda vk, up: keys.append((vk, up)),
    )
    attempt = Attempt("a", "i", "b", "cursor_windows")
    bundle = {
        "text": "should not appear",
        "assets": [{"asset_id": "00000000-0000-4000-8000-000000000005", "bytes_data": b"\x89PNG\r\n\x1a\n"}],
    }
    out = svc.run(attempt, bundle)
    assert out.result == "UNKNOWN"
    assert "text" not in pasted
    assert VK_RETURN not in [k[0] for k in keys]
    assert recovery_choice("UNKNOWN", True, 0, 1, False) == "ask"
