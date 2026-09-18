"""Remaining auto-testable V3 behaviors: flush, hotkey, clipboard, lock, recovery, instance."""
from __future__ import annotations

import asyncio
import json
import uuid

from aiohttp import ClientSession
from aiohttp.web import AppRunner, TCPSite

from doubao_typeless.core.attempt import Attempt
from doubao_typeless.core.bundle import Draft
from doubao_typeless.core.hotkey_gate import HotkeyGate
from doubao_typeless.platform.windows.guards import clipboard_still_ours, wait_modifiers_up
from doubao_typeless.runtime_lock import InstanceLock
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.services.delivery import DeliveryService
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService
from doubao_typeless.storage.migration import inspect_legacy_config
from doubao_typeless.ui.recovery import plan_retry


def test_hotkey_repeat_fires_once_until_release():
    gate = HotkeyGate()
    assert gate.press() is True
    assert gate.press() is False
    assert gate.press() is False
    gate.release()
    assert gate.press() is True
    assert gate.fires == 2


def test_clipboard_interference_stops_without_paste():
    pasted = []
    svc = DeliveryService(
        paste=lambda: pasted.append("paste"),
        set_clipboard_image=lambda _b: None,
        set_clipboard_text=lambda _t: None,
        read_focus=lambda: ("ComposerPane", "chatinput"),
        observe_text=lambda: "observed",
        read_clipboard_text=lambda: "user copied this instead",
    )
    out = svc.run(Attempt("a", "i", "b", "generic_text"), {"text": "payload", "assets": []})
    assert out.error_code == "CLIPBOARD_INTERFERENCE"
    assert pasted == []


def test_lock_and_elevated_do_not_drop_bundle():
    svc = DeliveryService(
        paste=lambda: None,
        set_clipboard_image=lambda _b: None,
        set_clipboard_text=lambda _t: None,
        read_focus=lambda: ("ComposerPane", "chatinput"),
        is_locked=lambda: True,
    )
    out = svc.run(Attempt("a", "i", "b", "generic_text"), {"text": "keep", "assets": []})
    assert out.result == "NO_STEPS"
    assert out.error_code == "SESSION_LOCKED"
    svc2 = DeliveryService(
        paste=lambda: None,
        set_clipboard_image=lambda _b: None,
        set_clipboard_text=lambda _t: None,
        read_focus=lambda: ("ComposerPane", "chatinput"),
        is_elevated=lambda: True,
    )
    out2 = svc2.run(Attempt("a", "i", "b", "generic_text"), {"text": "keep", "assets": []})
    assert out2.error_code == "TARGET_ELEVATED"


def test_wait_modifiers_true_when_none_held():
    assert wait_modifiers_up(timeout_s=0.05, get_async=lambda _vk: 0) is True
    assert wait_modifiers_up(timeout_s=0.05, get_async=lambda _vk: 0x8000) is False


def test_clipboard_still_ours():
    assert clipboard_still_ours("abc", "abc") is True
    assert clipboard_still_ours("abc", "xyz") is False


def test_unknown_recovery_never_ctrl_a_delete():
    plan = plan_retry(previous_result="UNKNOWN", same_target=True, images_observed=1, images_total=1, text_sent=True)
    assert plan["auto_replay"] is False
    assert plan["ctrl_a_delete"] is False
    assert plan["mode"] == "ask"


def test_instance_lock_does_not_kill_other(tmp_path):
    a = InstanceLock(tmp_path / "instance.lock")
    b = InstanceLock(tmp_path / "instance.lock")
    assert a.acquire() is True
    assert b.acquire() is False
    a.release()
    assert b.acquire() is True
    b.release()


def test_migration_invalid_json_does_not_write(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not-json", encoding="utf-8")
    before = path.read_bytes()
    out = inspect_legacy_config(path)
    assert out["error"] == "invalid json"
    assert path.read_bytes() == before


def test_tail_flush_on_commit_keeps_last_character(tmp_path):
    async def run():
        auth = AuthService()
        draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 0, "phone", "")
        bridge = V3Bridge(port=0, auth=auth, store=AssetStore(tmp_path / "a"), draft=draft)
        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as session:
                code = (await (await session.get(f"http://127.0.0.1:{port}/v3/pair")).json())["challenge"]
                creds = await (
                    await session.post(f"http://127.0.0.1:{port}/v3/pair", json={"code": code, "allow_insert": True})
                ).json()
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
                    await ws.send_json({"type": "session.hello", "session_id": creds["session_id"], "token": creds["token"]})
                    await ws.receive_json()
                    await ws.send_json({"type": "draft.update", "text": "hel", "revision": 1, "asset_refs": []})
                    await ws.receive_json()
                    await ws.send_json({"type": "bundle.commit", "text": "hello", "revision": 2, "asset_refs": []})
                    ready = await ws.receive_json()
                    assert ready["bundle"]["text"] == "hello"
                    assert ready["bundle"]["revision"] == 2
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_hotkeys_do_not_bind_escape():
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath("src/doubao_typeless/platform/windows/hotkeys.py").read_text(encoding="utf-8")
    assert "<esc>" not in text.lower()
    assert "esc_bound" in text
