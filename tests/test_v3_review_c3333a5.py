"""Production-module counterexamples from independent review c3333a5.

These import the live package, not the review-zip archive. They do not
operate a real screen, Cursor, or Android device.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from aiohttp import ClientSession
from aiohttp.web import AppRunner, TCPSite

from doubao_typeless.app import V3App
from doubao_typeless.core.bundle import Draft, freeze_bundle
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService
from tests.test_v3_s1_commands import _stub_delivery
from tests.test_v3_s4_conflict import _pair


def paired(tmp_path):
    auth = AuthService(store_path=tmp_path / "trusted.json")
    original = auth.complete_pairing(auth.new_pairing_challenge(), allow_insert=True, allow_capture=True)
    secret = auth.remember_device(original)
    resumed = auth.resume_trusted(original.device_id, secret)
    return auth, original, resumed, secret


def test_revoking_device_rejects_other_live_session(tmp_path):
    auth, original, resumed, _ = paired(tmp_path)
    assert auth.revoke(original.session_id)
    with pytest.raises(ValueError):
        auth.authorize(resumed.session_id, resumed.token, "capture")


def test_disabling_capture_applies_to_resumed_session(tmp_path):
    auth, original, resumed, _ = paired(tmp_path)
    auth.set_grants(original.session_id, allow_capture=False)
    with pytest.raises(ValueError):
        auth.authorize(resumed.session_id, resumed.token, "capture")


def test_control_revoking_named_session_rejects_it(tmp_path):
    auth, original, _, _ = paired(tmp_path)
    auth.revoke(original.session_id)
    with pytest.raises(ValueError):
        auth.authorize(original.session_id, original.token, "capture")


def test_control_trusted_device_restores_from_disk(tmp_path):
    auth, original, _, secret = paired(tmp_path)
    restarted = AuthService(store_path=tmp_path / "trusted.json")
    resumed = restarted.resume_trusted(original.device_id, secret)
    assert resumed.device_id == original.device_id and resumed.allow_capture


def test_stale_ai_cannot_replace_newer_edit_in_same_draft(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    app.draft.draft_id = "D"
    app.draft.epoch = "E1"
    app.draft.revision = 11
    app.draft.text = "用户已经修改的新文字B"
    app._last_suggestion = {
        "draft_id": "D",
        "epoch": "E1",
        "revision": 10,
        "original": "旧文字A",
        "suggested": "针对A的建议",
    }
    assert app.apply_suggestion() is False
    assert app.draft.text == "用户已经修改的新文字B"


def test_reject_old_suggestion_cannot_restore_text_into_new_epoch(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    app.draft.draft_id = "D"
    app.draft.epoch = "E2"
    app.draft.revision = 11
    app.draft.text = "下一轮新稿B"
    app._last_suggestion = {
        "draft_id": "D",
        "epoch": "E1",
        "revision": 10,
        "original": "旧文字A",
        "suggested": "针对A的建议",
        "before_apply": "上一轮原文A",
        "after_revision": 11,
    }
    app.reject_suggestion()
    assert app.draft.text == "下一轮新稿B"


def test_unknown_image_only_does_not_clear_or_rotate(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    bundle = {
        "draft_id": app.draft.draft_id,
        "epoch": app.draft.epoch,
        "revision": app.draft.revision,
        "text": "",
        "assets": [{"asset_id": "PHOTO-A"}],
        "manifest_hash": "h",
    }
    app.draft.assets = [{"asset_id": "PHOTO-A", "status": "ready"}]
    rotated = app._maybe_start_next_draft(bundle, {"result": "UNKNOWN", "steps": []})
    assert rotated is False
    event = app._phone_rotate_event(bundle, False, "UNKNOWN")
    assert event["archived"] is None
    assert app.draft.assets[0]["asset_id"] == "PHOTO-A"


def test_confirmed_emits_archived_identity(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    pasted: list[str] = []
    _stub_delivery(app, pasted)
    app.delivery._observe_text = lambda: "observed"
    app.draft.text = "已确认投递A"
    app.draft.revision = 3
    before = (app.draft.draft_id, app.draft.epoch, app.draft.revision)
    out = app.insert_current()
    assert out["result"] == "CONFIRMED"
    event = app.bridge.last_phone_event
    assert event["type"] == "draft.rotated"
    assert event["archived"]["text"] == "已确认投递A"
    assert event["archived"]["draft_id"] == before[0]
    assert event["archived"]["epoch"] == before[1]
    assert event["archived"]["revision"] == before[2]


def test_editing_source_blocks_insert(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    app.draft.text = "说明"
    app.draft.assets = [{"asset_id": "SRC", "status": "editing", "role": "source", "bytes": 1}]
    with pytest.raises(ValueError, match="IMAGE_EDITING"):
        freeze_bundle(app.draft, bundle_id="b1")
    out = app.insert_current()
    assert out["error_code"] == "IMAGE_EDITING"


def test_caption_is_appended_on_freeze(tmp_path):
    draft = Draft("d", "e", 1, "phone", "正文")
    draft.assets = [{"asset_id": "A", "bytes": 1, "caption": "圈出登录按钮"}]
    bundle = freeze_bundle(draft, bundle_id="b1")
    assert "正文" in bundle["text"]
    assert "图1：圈出登录按钮" in bundle["text"]


def test_forget_connected_revokes_trusted(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    session = app.auth.complete_pairing(app.auth.new_pairing_challenge(), allow_insert=True)
    secret = app.auth.remember_device(session)
    assert app.forget_connected() >= 1
    later = AuthService(store_path=app.data_dir / "trusted_devices.json")
    with pytest.raises(ValueError):
        later.resume_trusted(session.device_id, secret)


def test_windows_min_pack_needs_windows_pytest():
    text = Path(".github/workflows/preview-v3.yml").read_text(encoding="utf-8")
    block = text.split("windows-min-pack:", 1)[1]
    assert "windows-pytest" in block.split("steps:", 1)[0]


def test_desktop_hotkey_event_is_readable(tmp_path):
    async def run():
        app = V3App(data_dir=tmp_path / "data", port=0)
        pasted: list[str] = []
        _stub_delivery(app, pasted)
        app.delivery._observe_text = lambda: "observed"
        app.draft.text = "热键稿"
        app.insert_current()
        auth = app.auth
        store = app.store
        draft = app.draft
        bridge = V3Bridge(port=0, auth=auth, store=store, draft=draft)
        bridge.last_phone_event = app.bridge.last_phone_event
        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as session:
                creds = await _pair(session, port, auth)
                got = await session.get(
                    f"http://127.0.0.1:{port}/v3/phone/event",
                    headers={"X-DT-Session": creds["session_id"], "X-DT-Token": creds["token"]},
                )
                body = await got.json()
                assert body["type"] == "draft.rotated"
                assert body["archived"]["text"] == "热键稿"
        finally:
            await runner.cleanup()

    asyncio.run(run())
