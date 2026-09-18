"""Auth isolation: public pairing, remote grants, unauthenticated drafts, lock abort.

Existing protocol tests are unchanged; these cases cover the independent-review
counterexamples that those tests did not exercise.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from aiohttp import ClientSession, WSMsgType
from aiohttp.web import AppRunner, TCPSite

from doubao_typeless.app import V3App
from doubao_typeless.core.bundle import Draft
from doubao_typeless.runtime_lock import InstanceLock
from doubao_typeless.services import bridge_v3
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


def test_lan_pair_get_does_not_mint_or_return_challenge(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge_v3, "peer_host", lambda _request: "192.168.8.20")

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


def test_lan_pair_post_cannot_self_grant_insert_or_capture(tmp_path, monkeypatch):
    async def run():
        auth, _bridge, runner, port = await _serve(tmp_path)
        try:
            code = auth.new_pairing_challenge()
            monkeypatch.setattr(bridge_v3, "peer_host", lambda _request: "192.168.8.21")
            async with ClientSession() as session:
                response = await session.post(
                    f"http://127.0.0.1:{port}/v3/pair",
                    json={"code": code, "allow_insert": True, "allow_capture": True},
                )
                body = await response.json()
                assert response.status == 200
                assert body["allow_insert"] is False
                assert body["allow_capture"] is False
            session_obj = auth.sessions[body["session_id"]]
            assert session_obj.allow_insert is False
            assert session_obj.allow_capture is False
            with pytest.raises(ValueError, match="not granted"):
                auth.authorize(session_obj.session_id, session_obj.token, "insert")
            with pytest.raises(ValueError, match="not granted"):
                auth.authorize(session_obj.session_id, session_obj.token, "capture")
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_unauthenticated_ws_draft_update_is_rejected(tmp_path):
    async def run():
        _auth, bridge, runner, port = await _serve(tmp_path)
        try:
            async with ClientSession() as session:
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
                    await ws.send_json(
                        {
                            "type": "draft.update",
                            "text": "pwned draft",
                            "revision": 1,
                            "asset_refs": [],
                        }
                    )
                    msg = await ws.receive_json()
                    assert msg["type"] == "error"
                    assert msg["error"] == "unauthorized"
                    commit = {"type": "bundle.commit", "text": "pwned draft", "revision": 1}
                    await ws.send_json(commit)
                    msg2 = await ws.receive_json()
                    assert msg2["type"] == "error"
                    assert msg2["error"] == "unauthorized"
            assert bridge.draft.text == ""
            assert bridge.draft.revision == 0
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_unauthenticated_asset_get_is_rejected(tmp_path):
    async def run():
        _auth, _bridge, runner, port = await _serve(tmp_path)
        try:
            async with ClientSession() as session:
                response = await session.get(f"http://127.0.0.1:{port}/v3/assets/nope")
                assert response.status == 401
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_start_stops_without_writers_when_lock_held(tmp_path):
    held = InstanceLock(tmp_path / "instance.lock")
    assert held.acquire() is True
    app = V3App(data_dir=tmp_path, port=0)
    pair_note = tmp_path / "pair.txt"
    if pair_note.exists():
        pair_note.unlink()
    with pytest.raises(RuntimeError, match="instance lock held"):
        asyncio.run(app.start())
    assert app.bridge._runner is None
    assert not pair_note.exists()
    held.release()
