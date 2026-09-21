"""生产 TypeScript 页面、IndexedDB、异步反馈；WS/nonce 是明确的平台替身。"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def vite_url():
    node = shutil.which("node")
    vite = ROOT / "web/node_modules/vite/bin/vite.js"
    assert node and vite.is_file(), "Run npm ci in web first"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([node, str(vite), "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        cwd=ROOT / "web", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=.2).close()
                break
            except OSError:
                assert process.poll() is None, "Vite failed to start"
                time.sleep(.05)
        else:
            raise AssertionError("Vite startup timed out")
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_late_feedback_cannot_unlock_or_duplicate_current_durable_intent(vite_url):
    playwright = pytest.importorskip("playwright.async_api")

    async def run():
        messages, sockets, nonce_calls = [], [], []
        release = asyncio.Event()
        async with playwright.async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page()
                await page.add_init_script("sessionStorage.setItem('dt.v3.session',JSON.stringify({session_id:'s',token:'t',device_id:'phone'}));")
                async def api(route):
                    if route.request.url.endswith("/v3/nonce"):
                        nonce_calls.append(1)
                        await release.wait()
                        await route.fulfill(json={"nonce": "n"})
                    else:
                        await route.fulfill(json={})
                await page.route("**/v3/**", api)
                def connected(ws):
                    sockets.append(ws)
                    def incoming(raw):
                        msg = json.loads(raw)
                        messages.append(msg)
                        if msg["type"] == "session.hello":
                            ws.send(json.dumps({"type":"session.ready", "capabilities":["phone-primary-v1"]}))
                        elif msg["type"] == "draft.update":
                            ws.send(json.dumps({**msg,"type":"draft.ack","durable":True}))
                        elif msg["type"] == "ping":
                            ws.send(json.dumps({"type":"pong"}))
                    ws.on_message(incoming)
                await page.route_web_socket("**/ws", connected)
                await page.goto(vite_url)
                await page.fill("#text", "durable draft")
                await page.wait_for_function("!document.getElementById('sendBtn').disabled")
                await page.click("#sendBtn")
                for _ in range(100):
                    if nonce_calls: break
                    await asyncio.sleep(.02)
                assert len(nonce_calls) == 1
                # Simulate reentrant invocation and late unrelated responses while nonce awaits.
                await page.evaluate("document.getElementById('sendBtn').onclick()")
                for kind in ("attempt.status", "error", "delivery.progress", "draft.rotated"):
                    sockets[-1].send(json.dumps({"type":kind,"intent_id":"old-intent", "result":"NO_STEPS", "rotated":False,
                        "progress":{"message":"stale progress"},"error":"stale error"}))
                await page.evaluate("new Promise(r=>setTimeout(r,100))")
                assert await page.locator("#sendBtn").is_disabled()
                assert len(nonce_calls) == 1
                assert "stale progress" not in await page.locator("#deliveryStatus").inner_text()
                assert "stale error" not in await page.locator("body").inner_text()
                release.set()
                for _ in range(100):
                    if any(m["type"]=="insert.intent" for m in messages): break
                    await asyncio.sleep(.02)
                attempts = [m for m in messages if m["type"]=="insert.intent"]
                assert len(attempts) == 1
                intent = attempts[0]["intent_id"]
                sockets[-1].send(json.dumps({"type":"attempt.status","intent_id":intent,"result":"NO_STEPS"}))
                await page.wait_for_function("!document.getElementById('sendBtn').disabled")
                await page.click("#sendBtn")
                for _ in range(100):
                    if len([m for m in messages if m["type"]=="insert.intent"])==2: break
                    await asyncio.sleep(.02)
                attempts = [m for m in messages if m["type"]=="insert.intent"]
                assert len(attempts)==2 and attempts[1]["intent_id"]==intent
                sockets[-1].send(json.dumps({"type":"attempt.status","intent_id":"other","result":"CONFIRMED"}))
                await page.evaluate("new Promise(r=>setTimeout(r,100))")
                assert await page.locator("#sendBtn").is_disabled()
                assert await page.locator("#text").input_value()=="durable draft"
                sockets[-1].send(json.dumps({"type":"attempt.status","intent_id":intent,"result":"NO_STEPS"}))
                await page.wait_for_function("!document.getElementById('sendBtn').disabled")
                release.clear()
                await page.click("#sendBtn")
                for _ in range(100):
                    if len(nonce_calls)==3: break
                    await asyncio.sleep(.02)
                assert len(nonce_calls)==3
                await sockets[-1].close()
                for _ in range(150):
                    if len(sockets)==2: break
                    await asyncio.sleep(.02)
                assert len(sockets)==2
                await page.wait_for_function("!document.getElementById('sendBtn').disabled")
                await page.click("#sendBtn")
                for _ in range(100):
                    if len(nonce_calls)==4: break
                    await asyncio.sleep(.02)
                assert len(nonce_calls)==4
                release.set()
                for _ in range(100):
                    if len([m for m in messages if m['type']=='insert.intent'])==3: break
                    await asyncio.sleep(.02)
                await page.evaluate("new Promise(r=>setTimeout(r,100))")
                # The old disconnected nonce continuation must not send through the new socket.
                attempts=[m for m in messages if m['type']=='insert.intent']
                assert len(attempts)==3 and attempts[-1]['intent_id']==intent
            finally:
                release.set()
                await browser.close()
    asyncio.run(run())
