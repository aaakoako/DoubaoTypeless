"""Production-module counterexamples from independent review 9dd3a369 R0/R1.

These import the live package, not the review-zip archive. They do not
operate a real screen, Cursor, or Android device.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from aiohttp import ClientSession
from aiohttp.web import AppRunner, TCPSite

from doubao_typeless.app import V3App
from doubao_typeless.core.bundle import Draft
from doubao_typeless.runtime_lock import InstanceLock
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService


async def _serve(tmp_path):
    auth = AuthService()
    draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 0, "phone", "")
    bridge = V3Bridge(
        port=0,
        auth=auth,
        store=AssetStore(tmp_path / "assets"),
        draft=draft,
    )
    runner = AppRunner(bridge.make_app())
    await runner.setup()
    site = TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return auth, bridge, runner, port


def test_R01_public_get_does_not_return_challenge_or_mint(tmp_path):
    async def run():
        auth, _bridge, runner, port = await _serve(tmp_path)
        try:
            async with ClientSession() as session:
                response = await session.get(f"http://127.0.0.1:{port}/v3/pair")
                body = await response.json()
                assert response.status == 403
                assert "challenge" not in body
                assert auth.current_pairing_challenge() is None
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_R01_unapproved_client_cannot_self_grant_capture_and_insert(tmp_path):
    async def run():
        auth, _bridge, runner, port = await _serve(tmp_path)
        try:
            code = auth.new_pairing_challenge()
            async with ClientSession() as session:
                paired = await session.post(
                    f"http://127.0.0.1:{port}/v3/pair",
                    json={"code": code, "allow_insert": True, "allow_capture": True},
                )
                creds = await paired.json()
                assert paired.status == 200
                assert creds["allow_insert"] is False
                assert creds["allow_capture"] is False
                with pytest.raises(ValueError):
                    auth.authorize(creds["session_id"], creds["token"], "capture")
                with pytest.raises(ValueError):
                    auth.authorize(creds["session_id"], creds["token"], "insert")
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_R02_unpaired_websocket_cannot_modify_draft(tmp_path):
    async def run():
        _auth, bridge, runner, port = await _serve(tmp_path)
        try:
            async with ClientSession() as session:
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
                    await ws.send_json(
                        {
                            "type": "draft.update",
                            "text": "unapproved change",
                            "revision": 1,
                            "asset_refs": [],
                        }
                    )
                    reply = await ws.receive_json()
                    assert reply.get("type") == "error"
                    assert reply.get("error") == "unauthorized"
                    await ws.send_json({"type": "insert.intent", "text": "unapproved change", "revision": 1})
                    reply2 = await ws.receive_json()
                    assert reply2.get("type") == "error"
            assert bridge.draft.text == ""
            assert bridge.draft.revision == 0
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_F14_lock_failure_stops_before_writers(tmp_path):
    data = tmp_path / "preview"
    data.mkdir()
    held = InstanceLock(data / "instance.lock")
    assert held.acquire() is True
    with pytest.raises(RuntimeError, match="instance lock held"):
        V3App(data_dir=data, port=0)
    assert not (data / "pair.txt").exists()
    assert not (data / "v3.sqlite").exists()
    assert not (data / "history.json").exists()
    held.release()


def _png(color=(20, 120, 110)):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(buf, format="PNG")
    return buf.getvalue()


def test_R03_asset_refs_resolve_into_frozen_bundle(tmp_path):
    store = AssetStore(tmp_path / "assets")
    processed = store.put_png(_png((200, 10, 10)), width=16, height=16, role="markup")
    app = V3App(data_dir=tmp_path / "data", port=0)
    app.store = store
    app.apply_phone_update(
        {
            "text": "explain this",
            "revision": 1,
            "asset_refs": [processed["asset_id"]],
        }
    )
    from doubao_typeless.core.bundle import freeze_bundle

    bundle = freeze_bundle(app.draft, bundle_id="b1")
    assert [a["asset_id"] for a in bundle["assets"]] == [processed["asset_id"]]
    assert bundle["assets"][0]["role"] == "markup"


def test_R04_processed_ref_replaces_raw_screenshot(tmp_path):
    store = AssetStore(tmp_path / "assets")
    raw = store.put_png(_png((9, 9, 9)), width=16, height=16, role="screenshot")
    processed = store.put_png(_png((1, 2, 3)), width=16, height=16, role="markup")
    app = V3App(data_dir=tmp_path / "data", port=0)
    app.store = store
    app.draft.assets = [{"asset_id": raw["asset_id"], "role": "screenshot", "bytes": raw["bytes"]}]
    app.apply_phone_update(
        {
            "text": "use only redacted crop",
            "revision": app.draft.revision + 1,
            "asset_refs": [processed["asset_id"]],
        }
    )
    from doubao_typeless.core.bundle import freeze_bundle

    bundle = freeze_bundle(app.draft, bundle_id="b2")
    assert [a["asset_id"] for a in bundle["assets"]] == [processed["asset_id"]]
    assert raw["asset_id"] not in [a["asset_id"] for a in bundle["assets"]]


def test_R05_same_class_different_hwnd_stops_remaining():
    from doubao_typeless.core.attempt import Attempt
    from doubao_typeless.services.delivery import DeliveryService

    events = []
    current = [("ComposerPane", "chatinput", 11)]

    def focus():
        return current[0]

    def observed():
        current[0] = ("ComposerPane", "chatinput", 22)
        return "observed"

    svc = DeliveryService(
        paste=lambda: events.append(("paste", current[0])),
        set_clipboard_image=lambda _b: events.append(("image", 10)),
        set_clipboard_text=lambda _t: events.append(("text", _t)),
        read_focus=focus,
        observe_image=observed,
        observe_text=lambda: "observed",
    )
    outcome = svc.run(
        Attempt("a", "i", "b", "cursor_windows"),
        {
            "text": "text",
            "assets": [
                {"asset_id": "image-0", "bytes_data": b"x"},
                {"asset_id": "image-1", "bytes_data": b"y"},
            ],
        },
    )
    pastes = [e for e in events if e[0] == "paste"]
    assert len(pastes) == 1
    assert outcome.error_code == "TARGET_CHANGED"
    assert outcome.result == "PARTIAL"


def test_R06_modifier_failure_after_first_image_is_not_no_steps():
    from doubao_typeless.core.attempt import Attempt
    from doubao_typeless.services.delivery import DeliveryService

    waits = iter([True, False])
    events = []
    svc = DeliveryService(
        paste=lambda: events.append("paste"),
        set_clipboard_image=lambda _b: events.append("image"),
        set_clipboard_text=lambda _t: events.append("text"),
        read_focus=lambda: ("ComposerPane", "chatinput", 1),
        observe_image=lambda: "observed",
        wait_modifiers=lambda: next(waits),
    )
    outcome = svc.run(
        Attempt("a", "i", "b", "cursor_windows"),
        {"assets": [{"asset_id": "image-0", "bytes_data": b"x"}, {"asset_id": "image-1", "bytes_data": b"y"}]},
    )
    assert outcome.result != "NO_STEPS"
    assert outcome.result == "PARTIAL"


def test_R07_focus_rechecked_after_modifier_wait():
    from doubao_typeless.core.attempt import Attempt
    from doubao_typeless.services.delivery import DeliveryService

    current = [("Composer_A", "chatinput", 3)]
    events = []

    def wait():
        current[0] = ("Scintilla", "code", 4)
        return True

    svc = DeliveryService(
        paste=lambda: events.append(("paste", current[0])),
        set_clipboard_image=lambda _b: events.append("image"),
        set_clipboard_text=lambda _t: None,
        read_focus=lambda: current[0],
        wait_modifiers=wait,
        observe_image=lambda: "observed",
    )
    svc.run(Attempt("a", "i", "b", "cursor_windows"), {"assets": [{"asset_id": "image-0", "bytes_data": b"x"}]})
    assert not any(e[0] == "paste" for e in events)


def test_R08_insert_current_uses_draft_B(tmp_path):
    from tests.test_v3_s1_commands import _stub_delivery

    app = V3App(data_dir=tmp_path / "data", port=0)
    pasted: list[str] = []
    _stub_delivery(app, pasted)
    app.delivery._observe_text = lambda: "observed"
    app.draft.text = "B"
    app.bridge.last_bundle = {"bundle_id": "A", "text": "A", "assets": []}
    out = app.insert_current()
    assert out is not None
    assert any(item == "text:B" for item in pasted)
    assert "text:A" not in pasted


def test_R09_unknown_asks_instead_of_full_replay(tmp_path):
    from doubao_typeless.core.attempt import Attempt, Step

    app = V3App(data_dir=tmp_path / "data", port=0)
    calls = []
    app.deliver_and_finish = lambda intent, bundle: calls.append((intent, bundle)) or {"result": "RUNNING"}
    app.bridge.last_bundle = {"bundle_id": "A", "text": "A", "assets": []}
    app._last_attempt = Attempt("a", "i", "b", "cursor_windows")
    app._last_attempt.result = "UNKNOWN"
    app._last_attempt.steps = [Step(0, "image", "x", "unknown", "none")]
    app._last_target_fp = ("Composer", "chat", 1)
    app._read_focus = lambda: ("Composer", "chat", 1)
    notified = []
    app.ui_hook = lambda event, **_k: notified.append(event)
    assert app.insert_last() is None
    assert calls == []
    assert "recovery_ask" in notified


def test_R10_recall_retries_after_no_steps(tmp_path):
    from doubao_typeless.core.attempt import Attempt
    from tests.test_v3_s1_commands import _stub_delivery

    app = V3App(data_dir=tmp_path / "data", port=0)
    pasted: list[str] = []
    _stub_delivery(app, pasted)
    app.delivery._observe_text = lambda: "observed"
    app.history.record({"bundle_id": "A", "text": "A", "assets": [], "manifest_hash": "h"}, attempt_result="NO_STEPS")
    app._last_attempt = Attempt("a", "i", "b", "cursor_windows")
    app._last_attempt.result = "NO_STEPS"
    app.draft.text = "current B"
    out = app.recall_last()
    assert out is not None
    assert any(item == "text:A" for item in pasted)
    assert app.draft.text == "current B"


def test_R11_network_thread_schedules_widget_show(monkeypatch):
    from doubao_typeless.ui.hud import HudController

    scheduled = []

    class FakeTimer:
        @staticmethod
        def singleShot(_ms, _host, slot):
            scheduled.append(slot)

    class FakeThread:
        @staticmethod
        def currentThread():
            return "network"

    monkeypatch.setattr("PySide6.QtCore.QTimer", FakeTimer)
    monkeypatch.setattr("PySide6.QtCore.QThread", FakeThread)
    hud = HudController()

    class Widget:
        def thread(self):
            return "gui"

    hud._widget = Widget()
    hud._apply_show = lambda: scheduled.append("applied")
    hud.show_receiving("hello", 0)
    assert hud.visible is True
    assert scheduled == [hud._apply_show]


def test_R12_one_mib_chunk_is_accepted(tmp_path):
    async def run():
        from doubao_typeless.services.assets import UploadService
        from doubao_typeless.storage.db import V3DB

        auth = AuthService()
        store = AssetStore(tmp_path / "assets")
        uploads = UploadService(store, V3DB(tmp_path / "v3.sqlite"))
        draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 0, "phone", "")
        bridge = V3Bridge(port=0, auth=auth, store=store, draft=draft, uploads=uploads)
        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        payload = b"\x00" * (1024 * 1024)
        try:
            async with ClientSession() as session:
                from tests.v3_pairutil import desktop_issue_and_pair

                creds = await desktop_issue_and_pair(session, port, auth)
                headers = {"X-DT-Session": creds["session_id"], "X-DT-Token": creds["token"]}
                init = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/assets/init",
                        json={
                            "mime": "image/png",
                            "bytes": len(payload),
                            "sha256": "pending",
                            "width": 1,
                            "height": 1,
                            "chunk_size": len(payload),
                        },
                        headers=headers,
                    )
                ).json()
                put = await session.put(
                    f"http://127.0.0.1:{port}/v3/assets/{init['upload_id']}/chunks/0",
                    data=payload,
                    headers=headers,
                )
                assert put.status == 200
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_remote_unknown_target_is_rejected():
    from doubao_typeless.core.attempt import Attempt
    from doubao_typeless.services.delivery import DeliveryService

    svc = DeliveryService(
        paste=lambda: None,
        set_clipboard_image=lambda _b: None,
        set_clipboard_text=lambda _t: None,
        read_focus=lambda: ("Notepad", "Untitled", 9),
    )
    out = svc.run(Attempt("a", "i", "b", "generic"), {"text": "hi", "assets": []}, remote=True)
    assert out.result == "NO_STEPS"
    assert out.error_code == "NEEDS_TARGET"


def test_byok_classifies_401_404_429_timeout_tls():
    from doubao_typeless.services.byok import classify_api_error

    assert classify_api_error(RuntimeError("401 unauthorized"), "sk-secret") == "unauthorized"
    assert classify_api_error(RuntimeError("404 not found")) == "not_found"
    assert classify_api_error(RuntimeError("429 rate limited")) == "rate_limited"
    assert classify_api_error(TimeoutError("timeout")) == "timeout"
    assert classify_api_error(RuntimeError("SSL: CERTIFICATE_VERIFY_FAILED")) == "tls"
    assert "sk-secret" not in classify_api_error(RuntimeError("401 sk-secret"), "sk-secret")


def test_memory_ack_is_not_durable_without_data_dir(tmp_path):
    async def run():
        auth, bridge, runner, port = await _serve(tmp_path)
        try:
            async with ClientSession() as session:
                from tests.v3_pairutil import desktop_issue_and_pair

                creds = await desktop_issue_and_pair(session, port, auth)
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
                    await ws.send_json(
                        {"type": "session.hello", "session_id": creds["session_id"], "token": creds["token"]}
                    )
                    await ws.receive_json()
                    await ws.send_json({"type": "draft.update", "text": "mem", "revision": 1, "asset_refs": []})
                    ack = await ws.receive_json()
                    assert ack["type"] == "draft.ack"
                    assert ack["durable"] is False
        finally:
            await runner.cleanup()

    asyncio.run(run())
