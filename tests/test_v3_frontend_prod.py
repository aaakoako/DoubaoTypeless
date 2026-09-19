"""Production Vite frontend against a real V3Bridge. Do not inject extra protocol fields."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import pytest
from aiohttp.web import AppRunner, TCPSite

from doubao_typeless.core.bundle import Draft
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist" / "index.html"


def test_production_frontend_syncs_text_without_extra_fields(tmp_path):
    assert DIST.is_file(), "web/dist/index.html missing; CI/local must run npm run build first"
    playwright = pytest.importorskip("playwright.async_api")

    async def run():
        auth = AuthService()
        draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 0, "phone", "")
        bridge = V3Bridge(port=0, auth=auth, store=AssetStore(tmp_path / "assets"), draft=draft)
        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        code = auth.new_pairing_challenge()
        posts: list[str] = []
        try:
            async with playwright.async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()

                def on_request(request):
                    if request.method == "POST" and request.url.endswith("/v3/pair"):
                        posts.append(request.post_data or "")

                page.on("request", on_request)
                page.on("console", lambda msg: None)
                await page.goto(f"http://127.0.0.1:{port}/")
                await page.wait_for_selector("#pairCode", state="visible")
                await page.fill("#pairCode", code)
                async with page.expect_response(lambda r: r.url.endswith("/v3/pair") and r.request.method == "POST") as resp_info:
                    await page.click("#pairGo")
                pair_resp = await resp_info.value
                assert pair_resp.ok, await pair_resp.text()
                await page.wait_for_function(
                    "() => !document.getElementById('sheet').classList.contains('show')"
                )
                await page.wait_for_function(
                    "() => (document.getElementById('connText')||{}).textContent && document.getElementById('connText').textContent.indexOf('已连接') >= 0"
                )
                await page.fill("#text", "production frontend text")
                await page.locator("#text").dispatch_event("input")
                for _ in range(40):
                    if "production frontend text" in bridge.draft.text:
                        break
                    await asyncio.sleep(0.05)
                await browser.close()
        finally:
            await runner.cleanup()
        assert posts, "production page must POST /v3/pair"
        body = json.loads(posts[0])
        assert set(body) == {"code"}
        assert "allow_insert" not in body
        assert "assets" not in body
        assert "production frontend text" in bridge.draft.text

    asyncio.run(run())


def test_production_page_reconnect_keeps_local_and_does_not_overwrite(tmp_path):
    assert DIST.is_file(), "web/dist/index.html missing; CI/local must run npm run build first"
    playwright = pytest.importorskip("playwright.async_api")

    async def run():
        auth = AuthService()
        draft = Draft(str(uuid.uuid4()), "E-SERVER", 3, "pc", "服务器新稿")
        bridge = V3Bridge(port=0, auth=auth, store=AssetStore(tmp_path / "assets"), draft=draft)
        runner = AppRunner(bridge.make_app())
        await runner.setup()
        site = TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with playwright.async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.goto(f"http://127.0.0.1:{port}/")
                await page.wait_for_selector("#pairCode", state="visible")
                code = auth.new_pairing_challenge()
                await page.fill("#pairCode", code)
                await page.click("#pairGo")
                await page.wait_for_function(
                    "() => (document.getElementById('connText')||{}).textContent && document.getElementById('connText').textContent.indexOf('已连接') >= 0"
                )
                await page.evaluate(
                    """() => {
                      sessionStorage.setItem('dt.v3.draft', JSON.stringify({
                        text: '离线旧稿A',
                        revision: 10,
                        draft_id: 'D-OLD',
                        epoch: 'E-OLD',
                        assets: []
                      }));
                    }"""
                )
                await page.reload()
                await page.wait_for_function(
                    "() => (document.getElementById('connText')||{}).textContent && document.getElementById('connText').textContent.indexOf('已连接') >= 0"
                )
                for _ in range(20):
                    await asyncio.sleep(0.05)
                local = await page.locator("#text").input_value()
                await browser.close()
        finally:
            await runner.cleanup()
        assert bridge.draft.text == "服务器新稿"
        assert bridge.draft.epoch == "E-SERVER"
        assert local == "离线旧稿A"

    asyncio.run(run())
