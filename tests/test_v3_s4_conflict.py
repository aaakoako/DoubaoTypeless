"""PC edit parks phone WS writes; revoke closes the live socket."""
from __future__ import annotations

import asyncio
import uuid

from aiohttp import ClientSession, WSMsgType

from doubao_typeless.app import V3App
from doubao_typeless.core.bundle import Draft
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService
from doubao_typeless.storage.db import V3DB


async def _pair(session, port):
    code = (await (await session.get(f"http://127.0.0.1:{port}/v3/pair")).json())["challenge"]
    return await (
        await session.post(
            f"http://127.0.0.1:{port}/v3/pair",
            json={"code": code, "allow_insert": True, "allow_capture": True},
        )
    ).json()


def test_phone_ws_does_not_write_shared_draft_while_pc_edits(tmp_path):
    app = V3App(data_dir=tmp_path / "data", port=0)
    app.start_background(start_hud=False)
    try:
        app.draft.text = "电脑稿"
        app.draft.revision = 2
        app.review_editing = True

        async def run():
            async with ClientSession() as session:
                creds = await _pair(session, app.port)
                async with session.ws_connect(f"http://127.0.0.1:{app.port}/ws") as ws:
                    await ws.send_json(
                        {
                            "type": "session.hello",
                            "session_id": creds["session_id"],
                            "token": creds["token"],
                        }
                    )
                    assert (await ws.receive_json())["type"] == "session.ready"
                    await ws.send_json(
                        {
                            "type": "draft.update",
                            "text": "手机新稿",
                            "revision": 3,
                            "asset_refs": [],
                        }
                    )
                    ack = await ws.receive_json()
                    assert ack["type"] == "draft.ack"
                    assert ack.get("parked") is True
                    assert app.draft.text == "电脑稿"
                    assert app.phone_pending["text"] == "手机新稿"
                    await ws.send_json({"type": "bundle.commit", "text": "手机新稿", "revision": 3})
                    err = await ws.receive_json()
                    assert err["error"] == "pc_editing"
                app.accept_phone_pending()
                assert app.draft.text == "手机新稿"
                assert app.review_editing is False

        asyncio.run(run())
    finally:
        asyncio.run_coroutine_threadsafe(app.stop(), app._loop).result(5)


def test_revoke_closes_authed_websocket(tmp_path):
    async def run():
        auth = AuthService()
        draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 0, "phone", "")
        bridge = V3Bridge(port=0, auth=auth, store=AssetStore(tmp_path / "assets"), draft=draft)
        from aiohttp.web import AppRunner, TCPSite

        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as session:
                creds = await _pair(session, port)
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
                    await ws.send_json(
                        {
                            "type": "session.hello",
                            "session_id": creds["session_id"],
                            "token": creds["token"],
                        }
                    )
                    assert (await ws.receive_json())["type"] == "session.ready"
                    await bridge.revoke_session(creds["session_id"])
                    msg = await ws.receive()
                    if msg.type == WSMsgType.TEXT:
                        assert "revoked" in msg.data
                        closed = await ws.receive()
                        assert closed.type in {WSMsgType.CLOSED, WSMsgType.CLOSING, WSMsgType.CLOSE}
                    else:
                        assert msg.type in {WSMsgType.CLOSED, WSMsgType.CLOSING}
                    assert creds["session_id"] not in auth.sessions
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_asset_get_rejects_other_session(tmp_path):
    async def run():
        auth = AuthService()
        store = AssetStore(tmp_path / "assets")
        db = V3DB(tmp_path / "v3.sqlite")
        from doubao_typeless.services.assets import UploadService

        uploads = UploadService(store, db)
        draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 0, "phone", "")
        bridge = V3Bridge(
            port=0,
            auth=auth,
            store=store,
            draft=draft,
            uploads=uploads,
        )
        from aiohttp.web import AppRunner, TCPSite

        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            meta = store.put_png(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, width=1, height=1, role="photo")
            async with ClientSession() as session:
                owner = await _pair(session, port)
                other = await _pair(session, port)
                db.upsert_asset(meta["asset_id"], meta["sha256"], meta["bytes"], owner_session_id=owner["session_id"])
                denied = await session.get(
                    f"http://127.0.0.1:{port}/v3/assets/{meta['asset_id']}",
                    headers={"X-DT-Session": other["session_id"], "X-DT-Token": other["token"]},
                )
                assert denied.status == 403
                allowed = await session.get(
                    f"http://127.0.0.1:{port}/v3/assets/{meta['asset_id']}",
                    headers={"X-DT-Session": owner["session_id"], "X-DT-Token": owner["token"]},
                )
                assert allowed.status == 200
        finally:
            await runner.cleanup()

    asyncio.run(run())
