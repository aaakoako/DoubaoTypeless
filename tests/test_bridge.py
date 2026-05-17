from __future__ import annotations

import asyncio
import socket

import aiohttp

from bridge import PhoneBridge
from diagnostics import run_connection_self_check


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


def test_phone_bridge_serves_page_and_ws_protocol():
    async def run() -> None:
        updates: list[tuple[str, dict]] = []
        stable: list[tuple[str, dict]] = []
        port = _free_port()
        bridge = PhoneBridge(
            port=port,
            on_update=lambda text, meta: updates.append((text, meta)),
            on_text=lambda text, meta: stable.append((text, meta)),
            logger=lambda _m: None,
            redact_text_in_logs=True,
        )
        await bridge.start(asyncio.get_running_loop())
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{port}/") as resp:
                    body = await resp.text()
                    assert resp.status == 200
                    assert "DoubaoTypeless" in body
                    assert "{{WS_URL}}" not in body

                async with session.ws_connect(f"ws://127.0.0.1:{port}/ws") as ws:
                    await ws.send_json({"type": "hello", "meta": {"clientVersion": "test"}})
                    await ws.send_json({"type": "update", "text": "预览", "meta": {"inputType": "test"}})
                    await ws.send_json({"type": "stable", "text": "稳定", "meta": {"stableReason": "test"}})
                    await ws.send_json({"type": "ping"})
                    msg = await ws.receive(timeout=1.0)
                    assert msg.type == aiohttp.WSMsgType.TEXT
                    assert '"pong"' in msg.data

                    await bridge.notify_cleared()
                    msg = await ws.receive(timeout=1.0)
                    assert msg.type == aiohttp.WSMsgType.TEXT
                    assert '"cleared"' in msg.data

                assert updates == [("预览", {"inputType": "test"})]
                assert stable == [("稳定", {"stableReason": "test"})]
                diag = bridge.diagnostics()
                assert diag["last_client_version"] == "test"
                assert diag["last_update_len"] == 2
                assert diag["last_stable_reason"] == "test"
        finally:
            await bridge.stop()

    asyncio.run(run())


def test_connection_self_check_against_running_bridge():
    async def run() -> None:
        port = _free_port()
        bridge = PhoneBridge(port=port, logger=lambda _m: None, redact_text_in_logs=True)
        await bridge.start(asyncio.get_running_loop())
        try:
            result = await run_connection_self_check(port=port, connected_clients=1, last_stable_at="now")
            assert result["overall"] == "ok"
            assert any(c["name"] == "WebSocket" and c["status"] == "ok" for c in result["checks"])
        finally:
            await bridge.stop()

    asyncio.run(run())
