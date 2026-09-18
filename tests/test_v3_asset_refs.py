"""Server resolves completed asset_refs; client assets objects are ignored."""
from __future__ import annotations

import asyncio
import hashlib
import io
import uuid

from aiohttp import ClientSession
from aiohttp.web import AppRunner, TCPSite
from PIL import Image

from doubao_typeless.core.bundle import Draft
from doubao_typeless.services.assets import UploadService, resolve_asset_refs
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService
from doubao_typeless.storage.db import V3DB


def _png(w=48, h=48, color=(20, 120, 110)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def test_resolve_rejects_unknown_and_duplicate(tmp_path):
    store = AssetStore(tmp_path / "assets")
    meta = store.put_png(_png(), width=48, height=48, role="photo")
    resolved = resolve_asset_refs(store, [meta["asset_id"]])
    assert resolved[0]["sha256"] == meta["sha256"]
    assert "bytes_data" not in resolved[0]
    try:
        resolve_asset_refs(store, ["missing-id"])
        assert False, "expected unknown"
    except ValueError as exc:
        assert "unknown" in str(exc)
    try:
        resolve_asset_refs(store, [meta["asset_id"], meta["asset_id"]])
        assert False, "expected duplicate"
    except ValueError as exc:
        assert "duplicate" in str(exc)


def test_ws_asset_refs_use_store_not_client_assets(tmp_path):
    async def run():
        auth = AuthService()
        store = AssetStore(tmp_path / "assets")
        db = V3DB(tmp_path / "v3.sqlite")
        uploads = UploadService(store, db, chunk_size=2048)
        draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 0, "phone", "")
        bridge = V3Bridge(port=0, auth=auth, store=store, draft=draft, uploads=uploads)
        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        payload = _png(80, 80, (200, 10, 10))
        digest = hashlib.sha256(payload).hexdigest()
        try:
            async with ClientSession() as session:
                code = (await (await session.get(f"http://127.0.0.1:{port}/v3/pair")).json())["challenge"]
                creds = await (
                    await session.post(f"http://127.0.0.1:{port}/v3/pair", json={"code": code})
                ).json()
                headers = {"X-DT-Session": creds["session_id"], "X-DT-Token": creds["token"]}
                init = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/assets/init",
                        json={
                            "mime": "image/png",
                            "bytes": len(payload),
                            "sha256": digest,
                            "width": 80,
                            "height": 80,
                        },
                        headers=headers,
                    )
                ).json()
                upload_id = init["upload_id"]
                chunk = init["chunk_size"]
                for i in range(init["expected_chunks"]):
                    await session.put(
                        f"http://127.0.0.1:{port}/v3/assets/{upload_id}/chunks/{i}",
                        data=payload[i * chunk : (i + 1) * chunk],
                        headers=headers,
                    )
                meta = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/assets/{upload_id}/complete",
                        headers=headers,
                    )
                ).json()
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
                    await ws.send_json(
                        {
                            "type": "session.hello",
                            "session_id": creds["session_id"],
                            "token": creds["token"],
                        }
                    )
                    await ws.receive_json()
                    await ws.send_json(
                        {
                            "type": "draft.update",
                            "text": "caption",
                            "revision": 1,
                            "asset_refs": [meta["asset_id"]],
                            "assets": [{"asset_id": "forged", "bytes": 999, "sha256": "deadbeef"}],
                        }
                    )
                    ack = await ws.receive_json()
                    assert ack["type"] == "draft.ack"
                    await ws.send_json(
                        {
                            "type": "bundle.commit",
                            "text": "caption",
                            "revision": 1,
                            "asset_refs": [meta["asset_id"]],
                        }
                    )
                    ready = await ws.receive_json()
                    assert ready["type"] == "bundle.ready"
                    assets = ready["bundle"]["assets"]
                    assert len(assets) == 1
                    assert assets[0]["asset_id"] == meta["asset_id"]
                    assert assets[0]["sha256"] == digest
                    assert "bytes_data" not in assets[0]
                    await ws.send_json(
                        {
                            "type": "draft.update",
                            "text": "caption",
                            "revision": 2,
                            "asset_refs": ["not-a-real-asset"],
                        }
                    )
                    err = await ws.receive_json()
                    assert err["type"] == "error"
        finally:
            await runner.cleanup()

    asyncio.run(run())
