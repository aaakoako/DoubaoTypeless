"""V3 bridge: pairing reuse, key-script rejection, draft ack, no auto insert."""
from __future__ import annotations

import asyncio
import uuid

from aiohttp import ClientSession, WSMsgType
from aiohttp.web import AppRunner, TCPSite

from doubao_typeless.core.bundle import Draft
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService


async def _serve(tmp_path):
    auth = AuthService()
    draft = Draft(str(uuid.uuid4()), str(uuid.uuid4()), 0, "phone", "")
    intents = []
    bridge = V3Bridge(
        port=0,
        auth=auth,
        store=AssetStore(tmp_path / "assets"),
        draft=draft,
        on_intent=lambda intent, bundle: intents.append((intent, bundle)),
    )
    runner = AppRunner(bridge.make_app())
    await runner.setup()
    site = TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return auth, bridge, intents, runner, port


def test_bridge_protocol(tmp_path):
    async def run():
        auth, bridge, intents, runner, port = await _serve(tmp_path)
        try:
            async with ClientSession() as session:
                first = await session.get(f"http://127.0.0.1:{port}/v3/pair")
                first_body = await first.json()
                assert first.status == 403
                assert "challenge" not in first_body
                code_a = auth.new_pairing_challenge()
                code_b = auth.current_pairing_challenge()
                assert code_a == code_b
                from tests.v3_pairutil import desktop_issue_and_pair

                creds = await desktop_issue_and_pair(session, port, auth, allow_insert=True)
                html = await session.get(f"http://127.0.0.1:{port}/")
                body = await html.text()
                assert "白板" in body
                assert "共享画布" in body or "canvas" in body
                async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
                    await ws.send_json({"type": "insert.intent", "keys": ["CTRL", "V"]})
                    rejected = await ws.receive()
                    assert rejected.type == WSMsgType.TEXT
                    assert "forbidden" in rejected.data
                    await ws.send_json(
                        {
                            "type": "session.hello",
                            "session_id": creds["session_id"],
                            "token": creds["token"],
                        }
                    )
                    ready = await ws.receive_json()
                    assert ready["type"] == "session.ready"
                    await ws.send_json(
                        {
                            "type": "draft.update",
                            "text": "hello v3",
                            "revision": 1,
                            "asset_refs": [],
                        }
                    )
                    ack = await ws.receive_json()
                    assert ack["type"] == "draft.ack"
                    assert ack["revision"] == 1
                    await ws.send_json({"type": "bundle.commit"})
                    ready_bundle = await ws.receive_json()
                    assert ready_bundle["type"] == "bundle.ready"
                    assert ready_bundle["bundle"]["auto_send"] is False
                    nonce = await session.post(
                        f"http://127.0.0.1:{port}/v3/nonce",
                        json=creds,
                    )
                    nonce_body = await nonce.json()
                    await ws.send_json(
                        {
                            "type": "insert.intent",
                            "session_id": creds["session_id"],
                            "token": creds["token"],
                            "nonce": nonce_body["nonce"],
                            "intent_id": "intent-1",
                        }
                    )
                    status = await ws.receive_json()
                    assert status["type"] == "attempt.status"
                assert len(intents) == 1
                assert intents[0][1]["text"] == "hello v3"
        finally:
            await runner.cleanup()

    asyncio.run(run())
