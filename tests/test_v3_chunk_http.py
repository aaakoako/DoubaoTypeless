"""HTTP chunked upload through the V3 bridge."""
from __future__ import annotations

import hashlib
import io
import math
import uuid

from aiohttp import ClientSession
from aiohttp.web import AppRunner, TCPSite
from PIL import Image

from doubao_typeless.core.bundle import Draft
from doubao_typeless.services.assets import UploadService
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService
from doubao_typeless.storage.db import V3DB


def _png(w=80, h=80) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (22, 125, 113)).save(buf, format="PNG")
    return buf.getvalue()


def test_http_chunked_upload_resume(tmp_path):
    async def run():
        auth = AuthService()
        store = AssetStore(tmp_path / "assets")
        db = V3DB(tmp_path / "v3.sqlite")
        uploads = UploadService(store, db)
        draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 0, "phone", "")
        bridge = V3Bridge(port=0, auth=auth, store=store, draft=draft, uploads=uploads)
        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        payload = _png()
        digest = hashlib.sha256(payload).hexdigest()
        try:
            async with ClientSession() as session:
                code = (await (await session.get(f"http://127.0.0.1:{port}/v3/pair")).json())["challenge"]
                creds = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/pair",
                        json={"code": code, "allow_insert": True},
                    )
                ).json()
                headers = {"X-DT-Session": creds["session_id"], "X-DT-Token": creds["token"]}
                chunk = math.ceil(len(payload) / 2)
                init = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/assets/init",
                        json={"mime": "image/png", "bytes": len(payload), "sha256": digest, "width": 80, "height": 80, "chunk_size": chunk},
                        headers=headers,
                    )
                ).json()
                upload_id = init["upload_id"]
                await session.put(
                    f"http://127.0.0.1:{port}/v3/assets/{upload_id}/chunks/0",
                    data=payload[:chunk],
                    headers=headers,
                )
                missing = await (
                    await session.get(f"http://127.0.0.1:{port}/v3/assets/{upload_id}/missing", headers=headers)
                ).json()
                assert missing["missing"] == [1]
                await session.put(
                    f"http://127.0.0.1:{port}/v3/assets/{upload_id}/chunks/1",
                    data=payload[chunk:],
                    headers=headers,
                )
                meta = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/assets/{upload_id}/complete",
                        headers=headers,
                    )
                ).json()
                assert meta["sha256"] == digest
                assert db.asset(digest) is not None
        finally:
            await runner.cleanup()

    import asyncio

    asyncio.run(run())
