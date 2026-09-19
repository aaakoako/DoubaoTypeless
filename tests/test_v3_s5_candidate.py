"""S5: migration retry, dual-instance isolation, expired nonce/pairing, no auto-replay on stop."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

import pytest
from aiohttp import ClientSession
from aiohttp.web import AppRunner, TCPSite

from doubao_typeless.app import V3App
from doubao_typeless.core.bundle import Draft
from doubao_typeless.runtime import pick_port
from doubao_typeless.runtime_lock import InstanceLock
from doubao_typeless.services.assets import resolve_asset_refs
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService
from doubao_typeless.storage.migration import inspect_legacy_config
from doubao_typeless.storage.settings_store import load_settings, settings_path


ROOT = Path(__file__).resolve().parents[1]


def test_migration_invalid_then_valid_never_writes_or_starts_learn(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not-json", encoding="utf-8")
    before = path.read_bytes()
    first = inspect_legacy_config(path)
    assert path.read_bytes() == before
    assert first["start_learn"] is False
    payload = {
        "learn_enabled": True,
        "learn_api_key": "sk-legacy-must-stay",
        "hotkey_insert": "<ctrl>+<alt>+v",
        "hotkey_toggle_review": "<ctrl>+<shift>+u",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    mid = path.read_bytes()
    second = inspect_legacy_config(path)
    third = inspect_legacy_config(path)
    assert path.read_bytes() == mid
    assert second == third
    assert second["start_learn"] is False
    assert second["learn_enabled"] is True
    assert second["hotkeys"]["legacy_skip_polish_removed"] is True
    isolated = tmp_path / "preview-v3"
    assert not settings_path(isolated).exists()
    stored = load_settings(isolated)
    assert stored["byok_api_key"] == ""
    assert "sk-legacy-must-stay" not in json.dumps(stored)


def test_two_preview_dirs_start_same_dir_does_not_kill(tmp_path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    first = V3App(data_dir=a_dir, port=0)
    second = V3App(data_dir=b_dir, port=0)
    first.start_background(start_hud=False)
    try:
        second.start_background(start_hud=False)
        assert first.bridge.port != second.bridge.port
        held = InstanceLock(a_dir / "instance.lock")
        assert held.acquire() is False
        with pytest.raises(RuntimeError, match="instance lock held"):
            V3App(data_dir=a_dir, port=0)
        assert first.bridge._runner is not None

        async def ping():
            async with ClientSession() as session:
                status = await (await session.get(f"http://127.0.0.1:{first.bridge.port}/v3/status")).json()
                assert status["protocol"] == 3

        asyncio.run(ping())
    finally:
        asyncio.run(first.stop())
        try:
            asyncio.run(second.stop())
        except Exception:
            pass


def test_pick_port_does_not_use_daily_8765():
    chosen = pick_port(8766)
    assert chosen != 8765
    assert chosen >= 8766


def test_expired_pairing_and_nonce_are_rejected():
    auth = AuthService(pairing_ttl_s=0.05, session_ttl_s=8 * 3600)
    code = auth.new_pairing_challenge()
    time.sleep(0.12)
    with pytest.raises(ValueError, match="pairing expired"):
        auth.complete_pairing(code)
    auth2 = AuthService()
    code2 = auth2.new_pairing_challenge()
    session = auth2.complete_pairing(code2, allow_insert=True)
    nonce = auth2.issue_nonce(session)
    session.used_nonces[nonce] = time.time() - 1
    with pytest.raises(ValueError, match="nonce invalid"):
        auth2.consume_nonce(session, nonce)


def test_reconnect_does_not_auto_insert(tmp_path):
    async def run():
        auth = AuthService()
        draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 1, "phone", "kept")
        intents: list[dict] = []
        bridge = V3Bridge(
            port=0,
            auth=auth,
            store=AssetStore(tmp_path / "assets"),
            draft=draft,
            on_intent=lambda intent, _bundle: intents.append(intent) or {"result": "RUNNING"},
        )
        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as session:
                from tests.v3_pairutil import desktop_issue_and_pair

                creds = await desktop_issue_and_pair(session, port, auth)
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
                    await ws.send_json({"type": "session.hello", "session_id": creds["session_id"], "token": creds["token"]})
                    await ws.receive_json()
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws2:
                    await ws2.send_json({"type": "session.hello", "session_id": creds["session_id"], "token": creds["token"]})
                    ready = await ws2.receive_json()
                    assert ready["type"] == "session.ready"
        finally:
            await runner.cleanup()
        assert intents == []

    asyncio.run(run())


def test_unknown_asset_ref_does_not_freeze(tmp_path):
    store = AssetStore(tmp_path / "assets")
    with pytest.raises(ValueError, match="unknown"):
        resolve_asset_refs(store, ["deleted-after-edit"])


def test_v3_app_ignores_repo_daily_config(tmp_path, monkeypatch):
    daily = ROOT / "config.json"
    existed = daily.is_file()
    before = daily.read_bytes() if existed else None
    monkeypatch.setenv("DT_V3_DATA_DIR", str(tmp_path / "iso"))
    app = V3App(data_dir=tmp_path / "iso", port=0)
    assert app.data_dir == tmp_path / "iso"
    assert not (tmp_path / "iso" / "config.json").exists()
    if existed:
        assert daily.read_bytes() == before
    else:
        assert not daily.exists()
