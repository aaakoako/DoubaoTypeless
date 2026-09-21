"""S4: BYOK errors, PC grants, isolated settings, terms hints. Production page must not inject extra pair fields."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import pytest
from aiohttp import ClientSession
from aiohttp.web import AppRunner, TCPSite

from doubao_typeless.core.bundle import Draft
from doubao_typeless.services import bridge_v3
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.services.byok import ERROR_LABELS, ByokService, classify_api_error, redact_for_log
from doubao_typeless.services.terms import apply_permanent, hints
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService
from doubao_typeless.storage.settings_store import load_settings, save_settings

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist" / "index.html"


async def _serve(tmp_path, *, byok=None):
    auth = AuthService()
    draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 0, "phone", "")
    bridge = V3Bridge(
        port=0,
        auth=auth,
        store=AssetStore(tmp_path / "assets"),
        draft=draft,
        byok=byok,
        data_dir=tmp_path,
    )
    runner = AppRunner(bridge.make_app())
    await runner.setup()
    site = TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return auth, bridge, runner, port


def test_byok_error_labels_keep_original_and_hide_key():
    key = "sk-secret-s4-key"
    cases = [
        (Exception("HTTP 401 unauthorized " + key), "unauthorized"),
        (Exception("404 not found"), "not_found"),
        (Exception("429 rate limited"), "rate_limited"),
        (TimeoutError("timeout waiting"), "timeout"),
        (Exception("SSL: CERTIFICATE_VERIFY_FAILED"), "tls"),
        (Exception("cannot parse json " + key), "format"),
    ]
    for exc, reason in cases:
        assert classify_api_error(exc, key) == reason

        def boom(_url, _body, _headers, err=exc):
            raise err

        svc = ByokService(endpoint="https://example.invalid/v1", api_key=key, post=boom)
        out = svc.polish("原文可插入", draft_id="d", revision=1, current_draft_id="d", current_revision=1)
        assert out["status"] == "error"
        assert out["reason"] == reason
        assert out["text"] == "原文可插入"
        assert out["message"] == ERROR_LABELS[reason]
        blob = json.dumps(out, ensure_ascii=False)
        assert key not in blob
        assert redact_for_log(key) != key


def test_byok_no_key_is_full_product_message():
    out = ByokService().polish("hello", draft_id="d", revision=1, current_draft_id="d", current_revision=1)
    assert out["status"] == "skipped"
    assert out["reason"] == "no_key"
    assert out["text"] == "hello"
    assert "未配置密钥" in out["message"]


def test_settings_store_never_writes_daily_use(tmp_path):
    daily = tmp_path / "daily" / "config.json"
    daily.parent.mkdir()
    daily.write_text('{"llm_api_key":"keep"}', encoding="utf-8")
    data_dir = tmp_path / "preview-v3"
    save_settings(data_dir, {"byok_api_key": "sk-isolated", "byok_endpoint": "https://example.invalid/v1"})
    stored = load_settings(data_dir)
    assert stored["byok_api_key"] == "sk-isolated"
    assert (data_dir / "settings.json").is_file()
    assert "sk-isolated" not in (data_dir / "settings.json").read_text(encoding="utf-8")
    assert daily.read_text(encoding="utf-8") == '{"llm_api_key":"keep"}'
    assert not (tmp_path / "config.json").exists()


def test_terms_hint_only():
    notes = hints("试试 Midjourney 和 O pass 以及 O PU S")
    tokens = {n["token"] for n in notes}
    assert "midjourney" in tokens
    assert "o pass" in tokens
    with pytest.raises(RuntimeError):
        apply_permanent("Opus")


def test_pc_routes_are_loopback_only(tmp_path, monkeypatch):
    async def run():
        byok = ByokService(endpoint="https://old.example/v1", api_key="sk-old")
        auth, _bridge, runner, port = await _serve(tmp_path, byok=byok)
        try:
            async with ClientSession() as session:
                html = await session.get(f"http://127.0.0.1:{port}/pc")
                text = await html.text()
                assert html.status == 200
                assert "密钥只存在电脑" in text or "只存本机" in text
                monkeypatch.setattr(bridge_v3, "peer_host", lambda _request: "192.168.8.44")
                denied = await session.get(f"http://127.0.0.1:{port}/pc")
                assert denied.status == 403
                origin = {"Origin": f"http://192.168.8.44:{port}"}
                byok_denied = await session.get(f"http://127.0.0.1:{port}/v3/byok", headers=origin)
                assert byok_denied.status == 403
                grants = await session.post(
                    f"http://127.0.0.1:{port}/v3/grants",
                    json={"session_id": "x", "allow_insert": True},
                    headers=origin,
                )
                assert grants.status == 403
                assert auth.sessions == {}
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_pc_can_grant_after_phone_pairs_without_self_grant(tmp_path):
    async def run():
        auth, _bridge, runner, port = await _serve(tmp_path, byok=ByokService())
        try:
            async with ClientSession() as session:
                from tests.v3_pairutil import desktop_issue_and_pair

                creds = await desktop_issue_and_pair(session, port, auth)
                assert creds["allow_insert"] is False
                listed = await (await session.get(f"http://127.0.0.1:{port}/v3/sessions")).json()
                assert listed["items"][0]["session_id"] == creds["session_id"]
                granted = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/grants",
                        json={"session_id": creds["session_id"], "allow_insert": True, "allow_capture": False},
                    )
                ).json()
                assert granted["allow_insert"] is True
                nonce = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/nonce",
                        json={"session_id": creds["session_id"], "token": creds["token"]},
                    )
                ).json()
                assert nonce["nonce"]
                terms = await (
                    await session.get(
                        f"http://127.0.0.1:{port}/v3/terms?q=Midjourney",
                        headers={"X-DT-Session": creds["session_id"], "X-DT-Token": creds["token"]},
                    )
                ).json()
                assert terms["auto_replace"] is False
                assert terms["hints"]
                revoked = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/sessions/revoke",
                        json={"session_id": creds["session_id"]},
                    )
                ).json()
                assert revoked["ok"] is True
                again = await session.post(
                    f"http://127.0.0.1:{port}/v3/nonce",
                    json={"session_id": creds["session_id"], "token": creds["token"]},
                )
                assert again.status == 403
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_byok_host_change_requires_reauth(tmp_path):
    async def run():
        byok = ByokService(endpoint="https://old.example/v1", api_key="sk-keep")
        _auth, _bridge, runner, port = await _serve(tmp_path, byok=byok)
        try:
            async with ClientSession() as session:
                warned = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/byok",
                        json={"endpoint": "https://new.example/v1"},
                    )
                ).json()
                assert warned["needs_reauth"] is True
                assert byok.endpoint == "https://old.example/v1"
                assert byok.api_key == "sk-keep"
                ok = await (
                    await session.post(
                        f"http://127.0.0.1:{port}/v3/byok",
                        json={"endpoint": "https://new.example/v1", "api_key": "sk-new"},
                    )
                ).json()
                assert ok["ok"] is True
                assert "sk-new" not in json.dumps(ok)
                assert load_settings(tmp_path)["byok_endpoint"] == "https://new.example/v1"
                probe = await (await session.post(f"http://127.0.0.1:{port}/v3/byok/probe", json={"text": "probe"})).json()
                assert probe["status"] == "skipped"
                assert "sk-new" not in json.dumps(probe)
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_hotkey_probe_does_not_treat_syntax_as_success():
    from doubao_typeless.platform.windows.hotkeys import probe_hotkey_conflicts

    out = probe_hotkey_conflicts()
    assert "语法合法不等于注册成功" in out["hint"]
    assert out["esc_bound"] is False


def test_phone_cannot_set_byok_over_websocket(tmp_path):
    async def run():
        auth, _bridge, runner, port = await _serve(tmp_path, byok=ByokService())
        try:
            async with ClientSession() as session:
                from tests.v3_pairutil import desktop_issue_and_pair

                creds = await desktop_issue_and_pair(session, port, auth)
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
                    await ws.send_json({"type": "session.hello", "session_id": creds["session_id"], "token": creds["token"]})
                    await ws.receive_json()
                    await ws.send_json({"type": "byok.request", "api_key": "sk-from-phone"})
                    msg = await ws.receive_json()
                    assert msg["type"] == "error"
                    assert "desktop" in msg["error"]
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_production_settings_and_pc_copy(tmp_path):
    assert DIST.is_file(), "web/dist/index.html missing; npm run build first"
    playwright = pytest.importorskip("playwright.async_api")

    async def run():
        auth, bridge, runner, port = await _serve(tmp_path, byok=ByokService())
        posts: list[str] = []
        try:
            async with playwright.async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                page.on(
                    "request",
                    lambda req: posts.append(req.post_data or "")
                    if req.method == "POST" and req.url.endswith("/v3/pair")
                    else None,
                )
                await page.goto(f"http://127.0.0.1:{port}/")
                await page.locator("#sheetCard summary").click()
                await page.wait_for_selector("#pairCode")
                pair_copy = await page.locator("#sheetCard").inner_text()
                assert "二维码" in pair_copy
                assert "短码" in pair_copy
                assert "备用短码" in pair_copy
                assert "草稿会保留" in pair_copy
                await page.fill("#pairCode", auth.new_pairing_challenge())
                async with page.expect_response(lambda r: r.url.endswith("/v3/pair") and r.request.method == "POST") as info:
                    await page.click("#pairGo")
                assert (await info.value).ok
                await page.wait_for_function("() => !document.getElementById('sheet').classList.contains('show')")
                await page.wait_for_function(
                    "() => (document.getElementById('connText')||{}).textContent && document.getElementById('connText').textContent.indexOf('已连接') >= 0"
                )
                await page.fill("#text", "无Key文字仍可同步")
                await page.locator("#text").dispatch_event("input")
                for _ in range(40):
                    if "无Key文字仍可同步" in bridge.draft.text:
                        break
                    await asyncio.sleep(0.05)
                await page.click("#sendBtn")
                await page.wait_for_function("() => (document.getElementById('sync')||{}).textContent && document.getElementById('sync').textContent.indexOf('电脑确认插入') >= 0")
                await page.click("#settingsBtn")
                settings = await page.locator("#sheetCard").inner_text()
                assert "密钥只存在电脑" in settings
                assert "拒绝截图仍可同步" in settings
                await page.goto(f"http://127.0.0.1:{port}/pc")
                assert "允许插入" in await page.content()
                await browser.close()
        finally:
            await runner.cleanup()
        assert posts
        assert set(json.loads(posts[0])) == {"code"}
        assert "无Key文字仍可同步" in bridge.draft.text

    asyncio.run(run())
