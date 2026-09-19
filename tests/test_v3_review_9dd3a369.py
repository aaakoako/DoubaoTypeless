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
