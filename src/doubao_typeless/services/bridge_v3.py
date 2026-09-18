"""V3 aiohttp bridge: draft sync, assets, insert intent. Data messages never inject."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from aiohttp import web, WSMsgType

from doubao_typeless.core.bundle import Draft, apply_draft_update, freeze_bundle
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService, looks_like_key_script
from doubao_typeless.ui.tokens import should_wake
from doubao_typeless.services.assets import UploadService


STATIC = Path(__file__).resolve().parent.parent / "static"
def _web_dist() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "web" / "dist",
        here.parents[2] / "web" / "dist",
    ]
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return candidates[0]


WEB_DIST = _web_dist()
AUTH_DEADLINE_S = 5.0
WS_RATE_LIMIT = 40
WS_RATE_WINDOW_S = 2.0


def peer_host(request: web.Request) -> str:
    return str(request.remote or "")


def is_loopback_host(host: str) -> bool:
    value = (host or "").strip().lower()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if "%" in value:
        value = value.split("%", 1)[0]
    if value.startswith("::ffff:"):
        value = value[7:]
    return value in {"127.0.0.1", "::1", "localhost"} or value.startswith("127.")


def hostname_from_host_header(header: str) -> str:
    value = (header or "").strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end > 1 else ""
    return value.split(":")[0]


def is_trusted_hostname(name: str | None) -> bool:
    host = (name or "").strip().lower()
    if not host:
        return False
    if host in {"localhost"} or is_loopback_host(host):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


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
        uploads: UploadService | None = None,
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
        self.uploads = uploads
        self._log = logger or (lambda _m: None)
        self._runner: Optional[web.AppRunner] = None
        self._clients: set[web.WebSocketResponse] = set()
        self._ws_auth: dict[int, Any] = {}
        self._ws_rate: dict[int, list[float]] = {}

    @web.middleware
    async def _origin_host_gate(self, request: web.Request, handler):
        host = hostname_from_host_header(request.headers.get("Host", ""))
        if not is_trusted_hostname(host):
            return web.json_response({"error": "bad host"}, status=403)
        origin = request.headers.get("Origin", "")
        api = request.path == "/ws" or request.path.startswith("/v3/")
        if origin:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not is_trusted_hostname(parsed.hostname):
                return web.json_response({"error": "bad origin"}, status=403)
        elif api and not is_loopback_host(peer_host(request)):
            return web.json_response({"error": "origin required"}, status=403)
        return await handler(request)

    def make_app(self) -> web.Application:
        app = web.Application(middlewares=[self._origin_host_gate])
        app.router.add_get("/", self._index)
        app.router.add_get("/ws", self._ws)
        app.router.add_get("/v3/pair", self._pair_get)
        app.router.add_post("/v3/pair", self._pair_post)
        app.router.add_post("/v3/nonce", self._nonce)
        app.router.add_post("/v3/assets", self._asset_post)
        app.router.add_post("/v3/assets/init", self._asset_init)
        app.router.add_put("/v3/assets/{upload_id}/chunks/{index}", self._asset_chunk)
        app.router.add_post("/v3/assets/{upload_id}/complete", self._asset_complete)
        app.router.add_get("/v3/assets/{upload_id}/missing", self._asset_missing)
        app.router.add_get("/v3/assets/{asset_id}", self._asset_get)
        if (_web_dist() / "assets").is_dir():
            app.router.add_static("/assets", _web_dist() / "assets")
        app.router.add_get("/v3/history", self._history)
        app.router.add_get("/v3/status", self._status)
        return app

    async def start(self) -> None:
        self._runner = web.AppRunner(self.make_app())
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        if self.port == 0 and getattr(site, "_server", None) and site._server.sockets:
            self.port = int(site._server.sockets[0].getsockname()[1])
        self._log(f"[v3.bridge] http://127.0.0.1:{self.port}")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def _index(self, request: web.Request) -> web.Response:
        dist_index = _web_dist() / "index.html"
        path = dist_index if dist_index.is_file() else STATIC / "composer.html"
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
        if not is_loopback_host(peer_host(request)):
            return web.json_response({"pairing": True}, status=403)
        return web.json_response({"challenge": self.auth.new_pairing_challenge()})

    async def _pair_post(self, request: web.Request) -> web.Response:
        body = await request.json()
        loopback = is_loopback_host(peer_host(request))
        allow_insert = bool(body.get("allow_insert", False)) if loopback else False
        allow_capture = bool(body.get("allow_capture", False)) if loopback else False
        try:
            session = self.auth.complete_pairing(
                str(body.get("code") or ""),
                allow_insert=allow_insert,
                allow_capture=allow_capture,
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(
            {
                "session_id": session.session_id,
                "device_id": session.device_id,
                "token": session.token,
                "allow_insert": session.allow_insert,
                "allow_capture": session.allow_capture,
            }
        )

    async def _nonce(self, request: web.Request) -> web.Response:
        body = await request.json()
        session = self.auth.authorize(body["session_id"], body["token"], "insert")
        return web.json_response({"nonce": self.auth.issue_nonce(session)})

    def _session_from(self, request: web.Request):
        session_id = request.headers.get("X-DT-Session", "")
        token = request.headers.get("X-DT-Token", "")
        try:
            return self.auth.authorize(session_id, token, "sync")
        except ValueError as exc:
            raise web.HTTPUnauthorized(text=str(exc)) from exc

    async def _asset_post(self, request: web.Request) -> web.Response:
        self._session_from(request)
        data = await request.read()
        width = int(request.query.get("w", "1"))
        height = int(request.query.get("h", "1"))
        role = request.query.get("role", "photo")
        meta = self.store.put_png(data, width=width, height=height, role=role)
        if self._on_activity and should_wake("draft.update"):
            self._on_activity(self.draft.text, max(1, len(self.draft.assets)))
        return web.json_response(meta)

    async def _asset_init(self, request: web.Request) -> web.Response:
        self._session_from(request)
        if self.uploads is None:
            raise web.HTTPNotImplemented()
        body = await request.json()
        try:
            session = self.uploads.init(
                mime=str(body.get("mime") or "image/png"),
                total_bytes=int(body["bytes"]),
                sha256=str(body["sha256"]),
                width=int(body.get("width") or 1),
                height=int(body.get("height") or 1),
                chunk_size=int(body["chunk_size"]) if body.get("chunk_size") else None,
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(session)

    async def _asset_chunk(self, request: web.Request) -> web.Response:
        self._session_from(request)
        if self.uploads is None:
            raise web.HTTPNotImplemented()
        data = await request.read()
        try:
            self.uploads.put_chunk(request.match_info["upload_id"], int(request.match_info["index"]), data)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True})

    async def _asset_complete(self, request: web.Request) -> web.Response:
        self._session_from(request)
        if self.uploads is None:
            raise web.HTTPNotImplemented()
        try:
            meta = self.uploads.complete(request.match_info["upload_id"])
        except ValueError as exc:
            return web.json_response({"error": str(exc), "durable": False}, status=400)
        except OSError as exc:
            return web.json_response({"error": str(exc), "durable": False}, status=507)
        return web.json_response(meta)

    async def _asset_missing(self, request: web.Request) -> web.Response:
        self._session_from(request)
        if self.uploads is None:
            raise web.HTTPNotImplemented()
        try:
            missing = self.uploads.missing_chunks(request.match_info["upload_id"])
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"missing": missing})

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
        authorized = False
        deadline = time.monotonic() + AUTH_DEADLINE_S
        try:
            while True:
                timeout = None if authorized else max(0.0, deadline - time.monotonic())
                if not authorized and timeout == 0.0:
                    await ws.send_json({"type": "error", "error": "auth timeout"})
                    await ws.close()
                    break
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
                except asyncio.TimeoutError:
                    if not authorized:
                        await ws.send_json({"type": "error", "error": "auth timeout"})
                        await ws.close()
                    break
                if msg.type in {WSMsgType.CLOSED, WSMsgType.CLOSING, WSMsgType.ERROR}:
                    break
                if msg.type != WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                if looks_like_key_script(data):
                    await ws.send_json({"type": "error", "error": "forbidden payload"})
                    continue
                if not self._rate_ok(ws):
                    await ws.send_json({"type": "error", "error": "rate limited"})
                    continue
                authorized = await self._handle(ws, data, authorized)
        finally:
            self._clients.discard(ws)
            self._ws_auth.pop(id(ws), None)
            self._ws_rate.pop(id(ws), None)
        return ws

    def _rate_ok(self, ws: web.WebSocketResponse) -> bool:
        now = time.monotonic()
        bucket = self._ws_rate.setdefault(id(ws), [])
        bucket.append(now)
        cutoff = now - WS_RATE_WINDOW_S
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        return len(bucket) <= WS_RATE_LIMIT

    def _apply_draft_fields(self, data: dict[str, Any]) -> None:
        apply_draft_update(
            self.draft,
            {
                "text": data.get("text", self.draft.text),
                "revision": int(data.get("revision") or self.draft.revision + 1),
                "asset_refs": data.get("asset_refs", [a["asset_id"] for a in self.draft.assets]),
                "assets": data.get("assets", self.draft.assets),
            },
        )

    async def _handle(self, ws: web.WebSocketResponse, data: dict[str, Any], authorized: bool) -> bool:
        kind = data.get("type")
        if kind == "ping":
            await ws.send_json({"type": "pong"})
            return authorized
        if kind == "session.hello":
            try:
                session = self.auth.authorize(
                    str(data.get("session_id") or ""),
                    str(data.get("token") or ""),
                    "sync",
                )
            except ValueError as exc:
                await ws.send_json({"type": "error", "error": str(exc)})
                return False
            self._ws_auth[id(ws)] = session
            await ws.send_json(
                {
                    "type": "session.ready",
                    "protocol": 3,
                    "draft_id": self.draft.draft_id,
                    "epoch": self.draft.epoch,
                    "revision": self.draft.revision,
                }
            )
            return True
        if not authorized:
            await ws.send_json({"type": "error", "error": "unauthorized"})
            return False
        try:
            if kind == "draft.update":
                self._apply_draft_fields(data)
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
                return True
            if kind == "editor.activity":
                if self._on_activity and should_wake("editor.activity"):
                    self._on_activity(self.draft.text, len(self.draft.assets))
                return True
            if kind == "bundle.commit":
                if "text" in data or "revision" in data:
                    self._apply_draft_fields(data)
                bundle = freeze_bundle(self.draft, bundle_id=str(uuid.uuid4()))
                self.last_bundle = bundle
                public = {k: v for k, v in bundle.items() if k != "bytes_data"}
                await ws.send_json({"type": "bundle.ready", "bundle": public})
                return True
            if kind == "insert.intent":
                session = self.auth.authorize(data["session_id"], data.get("token") or "", "insert")
                self.auth.consume_nonce(session, str(data.get("nonce") or ""))
                if "text" in data or "revision" in data:
                    self._apply_draft_fields(data)
                if self.last_bundle is None or int(self.last_bundle.get("revision") or -1) != self.draft.revision:
                    self.last_bundle = freeze_bundle(self.draft, bundle_id=str(uuid.uuid4()))
                frozen = dict(self.last_bundle)
                status = {"result": "RUNNING"}
                if self._on_intent:
                    status = self._on_intent(data, frozen) or status
                await ws.send_json({"type": "attempt.status", **status})
                return True
            if kind == "capture.request":
                self.auth.authorize(data["session_id"], data.get("token") or "", "capture")
                if not self._on_capture:
                    await ws.send_json({"type": "capture.result", "error": "unavailable"})
                    return True
                try:
                    meta = self._on_capture(
                        str(data.get("scope") or "primary"),
                        str(data.get("request_id") or uuid.uuid4()),
                    )
                except ValueError as exc:
                    await ws.send_json({"type": "capture.result", "error": str(exc)})
                    return True
                await ws.send_json({"type": "capture.result", "asset": meta})
                return True
            if kind == "byok.request":
                await ws.send_json({"type": "error", "error": "byok stays on desktop"})
                return True
        except ValueError as exc:
            await ws.send_json({"type": "error", "error": str(exc)})
            return authorized
        return authorized

