"""Real loopback WebSockets must not keep the desktop alive on shutdown."""
import asyncio

import pytest
from aiohttp import ClientSession, WSCloseCode, WSMsgType, web

from doubao_typeless.core.bundle import Draft
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService


@pytest.mark.parametrize("phone_reads_close", [True, False])
def test_shutdown_closes_online_phone_without_clearing_draft(tmp_path, phone_reads_close):
    async def run():
        auth = AuthService()
        credential = auth.complete_pairing(auth.new_pairing_challenge())
        draft = Draft("shutdown-draft", "epoch", 1, "phone", "Keep my draft")
        bridge = V3Bridge(port=0, auth=auth, store=AssetStore(tmp_path / "assets"), draft=draft)
        runner = web.AppRunner(bridge.make_app())
        bridge._runner = runner
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        session = ClientSession()
        stop = reader = None
        try:
            ws = await session.ws_connect(f"http://127.0.0.1:{port}/ws")
            await ws.send_json({"type": "session.hello", "session_id": credential.session_id,
                                "token": credential.token})
            assert (await ws.receive_json())["type"] == "session.ready"
            # Include an unpaired connection too: the authentication timeout must
            # not be the mechanism which makes shutdown complete.
            await session.ws_connect(f"http://127.0.0.1:{port}/ws")
            assert len(bridge._clients) == 2
            assert bridge._ws_auth
            if phone_reads_close:
                reader = asyncio.create_task(ws.receive())
            stop = asyncio.create_task(bridge.stop())
            done, _ = await asyncio.wait({stop}, timeout=4)
            assert stop in done, "shutdown waited for the phone instead of closing its WebSocket"
            await stop
            if reader is not None:
                message = await asyncio.wait_for(reader, 1)
                assert message.type == WSMsgType.CLOSE
                assert message.data == WSCloseCode.GOING_AWAY
            assert bridge._runner is None
            assert not bridge._clients
            assert not bridge._ws_auth
            assert not bridge._ws_rate
            assert bridge.draft is draft
            assert draft.text == "Keep my draft"
            assert auth.authorize(credential.session_id, credential.token, "sync") is credential
            await bridge.stop()  # repeated shutdown is harmless
        finally:
            # Close only this test's transports, even when the regression fails.
            await session.close()
            for task in (reader, stop):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*(task for task in (reader, stop) if task is not None),
                                 return_exceptions=True)
            await asyncio.wait_for(runner.cleanup(), 3)

    asyncio.run(run())
