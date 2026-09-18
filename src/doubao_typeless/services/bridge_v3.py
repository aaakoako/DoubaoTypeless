"""V3 aiohttp bridge: draft sync, assets, insert intent. Data messages never inject."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from aiohttp import web, WSMsgType

from doubao_typeless.core.bundle import Draft, apply_draft_update, freeze_bundle
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService, looks_like_key_script
from doubao_typeless.ui.tokens import should_wake


STATIC = Path(__file__).resolve().parent.parent / "static"


class V3Bridge:
    def __init__(
        self,
        *,
        port: int,
        auth: AuthService,
        store: AssetStore,
        draft: Draft,
        on_activity: Callable[[str, int], None] | None = None,
        on_intent: Callable[[dict, dict], None] | None = None,
        on_capture: Callable[[str, str], dict] | None = None,
        history_list: Callable[[], list] | None = None,
        logger: Callable[[str], None] | None = None,
    ):
        self.port = port
        self.auth = auth
        self.store = store
        self.draft = draft
        self.last_bundle: dict[str, Any] | None = None
        self._on_activity = on_activity
        self._on_intent = on_intent
        self._on_capture = on_capture
        self._history_list = history_list
        self._log = logger or (lambda _m: None)
        self._runner: Optional[web.AppRunner] = None
        self._clients: set[web.WebSocketResponse] = set()

    def make_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/", self._index)
        app.router.add_get("/ws", self._ws)
        app.router.add_get("/v3/pair", self._pair_get)
        app.router.add_post("/v3/pair", self._pair_post)
        app.router.add_post("/v3/nonce", self._nonce)
        app.router.add_post("/v3/assets", self._asset_post)
        app.router.add_get("/v3/assets/{asset_id}", self._asset_get)
        app.router.add_get("/v3/history", self._history)
        app.router.add_get("/v3/status", self._status)
        return app

    async def start(self) -> None:
        self._runner = web.AppRunner(self.make_app())
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        self._log(f"[v3.bridge] http://127.0.0.1:{self.port}")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def _index(self, request: web.Request) -> web.Response:
        path = STATIC / "composer.html"
        return web.FileResponse(path)

    async def _status(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "protocol": 3,
                "draft_id": self.draft.draft_id,
                "epoch": self.draft.epoch,
                "revision": self.draft.revision,
                "idle_hud": True,
            }
        )

    async def _pair_get(self, request: web.Request) -> web.Response:
        return web.json_response({"challenge": self.auth.new_pairing_challenge()})

    async def _pair_post(self, request: web.Request) -> web.Response:
        body = await request.json()
        session = self.auth.complete_pairing(
            str(body.get("code") or ""),
            allow_insert=bool(body.get("allow_insert", True)),
            allow_capture=bool(body.get("allow_capture")),
        )
        return web.json_response(
            {
                "session_id": session.session_id,
                "device_id": session.device_id,
                "token": session.token,
            }
        )

    async def _nonce(self, request: web.Request) -> web.Response:
        body = await request.json()
        session = self.auth.authorize(body["session_id"], body["token"], "insert")
        return web.json_response({"nonce": self.auth.issue_nonce(session)})

    def _session_from(self, request: web.Request):
        session_id = request.headers.get("X-DT-Session", "")
        token = request.headers.get("X-DT-Token", "")
        return self.auth.authorize(session_id, token, "sync")

    async def _asset_post(self, request: web.Request) -> web.Response:
        self._session_from(request)
        data = await request.read()
        width = int(request.query.get("w", "1"))
        height = int(request.query.get("h", "1"))
        role = request.query.get("role", "photo")
        meta = self.store.put_png(data, width=width, height=height, role=role)
        self.draft.assets.append(meta)
        self.draft.revision += 1
        if self._on_activity:
            self._on_activity(self.draft.text, len(self.draft.assets))
        return web.json_response(meta)

    async def _asset_get(self, request: web.Request) -> web.StreamResponse:
        self._session_from(request)
        asset_id = request.match_info["asset_id"]
        blob = self.store.get(asset_id)
        return web.Response(
            body=blob,
            content_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    async def _history(self, request: web.Request) -> web.Response:
        self._session_from(request)
        items = self._history_list() if self._history_list else []
        return web.json_response({"items": items})

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(max_msg_size=256 * 1024)
        await ws.prepare(request)
        self._clients.add(ws)
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                if looks_like_key_script(data):
                    await ws.send_json({"type": "error", "error": "forbidden payload"})
                    continue
                await self._handle(ws, data)
        finally:
            self._clients.discard(ws)
        return ws

    async def _handle(self, ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
        kind = data.get("type")
        if kind == "ping":
            await ws.send_json({"type": "pong"})
            return
        if kind == "session.hello":
            if data.get("session_id"):
                self.auth.authorize(data["session_id"], data.get("token") or "", "sync")
            await ws.send_json(
                {
                    "type": "session.ready",
                    "protocol": 3,
                    "draft_id": self.draft.draft_id,
                    "epoch": self.draft.epoch,
                    "revision": self.draft.revision,
                }
            )
            return
        if kind == "draft.update":
            apply_draft_update(
                self.draft,
                {
                    "text": data.get("text", self.draft.text),
                    "revision": int(data.get("revision") or self.draft.revision + 1),
                    "asset_refs": data.get("asset_refs", [a["asset_id"] for a in self.draft.assets]),
                    "assets": data.get("assets", self.draft.assets),
                },
            )
            if self._on_activity and should_wake("draft.update"):
                self._on_activity(self.draft.text, len(self.draft.assets))
            await ws.send_json(
                {
                    "type": "draft.ack",
                    "revision": self.draft.revision,
                    "durable": True,
                    "hash": self.draft.acked_hash,
                }
            )
            return
        if kind == "editor.activity":
            if self._on_activity and should_wake("editor.activity"):
                self._on_activity(self.draft.text, len(self.draft.assets))
            return
        if kind == "bundle.commit":
            bundle = freeze_bundle(self.draft, bundle_id=str(uuid.uuid4()))
            self.last_bundle = bundle
            public = {k: v for k, v in bundle.items() if k != "bytes_data"}
            await ws.send_json({"type": "bundle.ready", "bundle": public})
            return
        if kind == "insert.intent":
            session = self.auth.authorize(data["session_id"], data.get("token") or "", "insert")
            self.auth.consume_nonce(session, str(data.get("nonce") or ""))
            if self.last_bundle is None:
                self.last_bundle = freeze_bundle(self.draft, bundle_id=str(uuid.uuid4()))
            frozen = dict(self.last_bundle)
            status = {"result": "RUNNING"}
            if self._on_intent:
                status = self._on_intent(data, frozen) or status
            await ws.send_json({"type": "attempt.status", **status})
            return
        if kind == "capture.request":
            self.auth.authorize(data["session_id"], data.get("token") or "", "capture")
            if not self._on_capture:
                await ws.send_json({"type": "capture.result", "error": "unavailable"})
                return
            try:
                meta = self._on_capture(
                    str(data.get("scope") or "primary"),
                    str(data.get("request_id") or uuid.uuid4()),
                )
            except ValueError as exc:
                await ws.send_json({"type": "capture.result", "error": str(exc)})
                return
            await ws.send_json({"type": "capture.result", "asset": meta})
            return
        if kind == "byok.request":
            await ws.send_json({"type": "error", "error": "byok stays on desktop"})
            return
