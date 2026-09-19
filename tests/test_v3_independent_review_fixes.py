"""Fixes required by independent Bugbot / security review."""
from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import ClientSession

from doubao_typeless.core.bundle import Draft
from doubao_typeless.services.assets import UploadService
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService
from doubao_typeless.storage.db import V3DB
from tests.test_v3_s4_conflict import _pair

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
    b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_windows_pack_ci_installs_qrcode_and_httpx():
    text = Path(".github/workflows/preview-v3.yml").read_text(encoding="utf-8")
    pack_block = text.split("Install pack dependencies", 1)[1]
    assert "qrcode" in pack_block
    assert "httpx" in pack_block
    needs = text.split("windows-min-pack:", 1)[1].split("steps:", 1)[0]
    assert "windows-pytest" in needs


def test_product_entry_preview_uses_run_v3_and_src_path():
    text = Path("docs/v3-product/START_HERE.md").read_text(encoding="utf-8")
    assert "python tools/run_v3.py" in text
    assert "PYTHONPATH" in text
    freeze = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "python -m doubao_typeless" in freeze


def test_legacy_asset_post_binds_owner(tmp_path):
    async def run():
        auth = AuthService()
        store = AssetStore(tmp_path / "assets")
        db = V3DB(tmp_path / "v3.sqlite")
        uploads = UploadService(store, db)
        draft = Draft("d", "e", 0, "phone", "")
        bridge = V3Bridge(port=0, auth=auth, store=store, draft=draft, uploads=uploads)
        from aiohttp.web import AppRunner, TCPSite

        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as session:
                owner = await _pair(session, port)
                other = await _pair(session, port)
                posted = await session.post(
                    f"http://127.0.0.1:{port}/v3/assets?w=1&h=1",
                    data=PNG,
                    headers={"X-DT-Session": owner["session_id"], "X-DT-Token": owner["token"]},
                )
                assert posted.status == 200
                asset_id = (await posted.json())["asset_id"]
                denied = await session.get(
                    f"http://127.0.0.1:{port}/v3/assets/{asset_id}",
                    headers={"X-DT-Session": other["session_id"], "X-DT-Token": other["token"]},
                )
                assert denied.status == 403
                allowed = await session.get(
                    f"http://127.0.0.1:{port}/v3/assets/{asset_id}",
                    headers={"X-DT-Session": owner["session_id"], "X-DT-Token": owner["token"]},
                )
                assert allowed.status == 200
        finally:
            await runner.cleanup()

    asyncio.run(run())
