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
from doubao_typeless.services.assets import UploadService, resolve_asset_refs


STATIC = Path(__file__).resolve().parent.parent / "static"
PC_FALLBACK = """<!doctype html><meta charset=utf-8><title>电脑设置</title>
<p>密钥只存在电脑。不配 Key 也能用。拒绝截图仍可同步文字。Alt+I 插入，Alt+Shift+I 召回，不再是跳过纠错。</p>
"""


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
        on_capture: Callable[..., dict] | None = None,
        on_recall: Callable[[], None] | None = None,
        on_phone_draft: Callable[[dict], dict] | None = None,
        is_pc_editing: Callable[[], bool] | None = None,
        history_list: Callable[[], list] | None = None,
        uploads: UploadService | None = None,
        logger: Callable[[str], None] | None = None,
        byok: Any | None = None,
        data_dir: Path | None = None,
    ):
        self.port = port
        self.auth = auth
        self.store = store
        self.draft = draft
        self.last_bundle: dict[str, Any] | None = None
        self._on_activity = on_activity
        self._on_intent = on_intent
        self._on_capture = on_capture
        self._on_recall = on_recall
        self._on_phone_draft = on_phone_draft
        self._is_pc_editing = is_pc_editing or (lambda: False)
        self._history_list = history_list
        self.uploads = uploads
        self.byok = byok
        self.data_dir = Path(data_dir) if data_dir else None
        self._log = logger or (lambda _m: None)
        self.paused = False
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
        app = web.Application(middlewares=[self._origin_host_gate], client_max_size=2 * 1024 * 1024)
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
        app.router.add_get("/pc", self._pc)
        app.router.add_get("/v3/sessions", self._sessions)
        app.router.add_post("/v3/sessions/revoke", self._revoke)
        app.router.add_post("/v3/grants", self._grants)
        app.router.add_get("/v3/byok", self._byok_get)
        app.router.add_post("/v3/byok", self._byok_post)
        app.router.add_post("/v3/byok/probe", self._byok_probe)
        app.router.add_get("/v3/hotkeys", self._hotkeys_get)
        app.router.add_post("/v3/hotkeys", self._hotkeys_post)
        app.router.add_get("/v3/terms", self._terms)
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

    def _require_loopback(self, request: web.Request) -> web.Response | None:
        if not is_loopback_host(peer_host(request)):
            return web.json_response({"error": "pc only"}, status=403)
        return None

    async def _pc(self, request: web.Request) -> web.Response:
        denied = self._require_loopback(request)
        if denied:
            return denied
        path = STATIC / "pc.html"
        if path.is_file():
            return web.FileResponse(path)
        return web.Response(text=PC_FALLBACK, content_type="text/html; charset=utf-8")

    async def _sessions(self, request: web.Request) -> web.Response:
        denied = self._require_loopback(request)
        if denied:
            return denied
        return web.json_response({"items": self.auth.public_sessions()})

    async def _grants(self, request: web.Request) -> web.Response:
        denied = self._require_loopback(request)
        if denied:
            return denied
        body = await request.json()
        try:
            session = self.auth.set_grants(
                str(body.get("session_id") or ""),
                allow_insert=body.get("allow_insert"),
                allow_capture=body.get("allow_capture"),
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(
            {
                "session_id": session.session_id,
                "allow_insert": session.allow_insert,
                "allow_capture": session.allow_capture,
            }
        )

    async def revoke_session(self, session_id: str) -> bool:
        removed = self.auth.revoke(session_id)
        for ws in list(self._clients):
            bound = self._ws_auth.get(id(ws))
            if bound is None or bound.session_id != session_id:
                continue
            try:
                await ws.send_json({"type": "error", "error": "session revoked"})
                await ws.close()
            except Exception:
                pass
            self._ws_auth.pop(id(ws), None)
        return removed

    async def _revoke(self, request: web.Request) -> web.Response:
        denied = self._require_loopback(request)
        if denied:
            return denied
        body = await request.json()
        removed = await self.revoke_session(str(body.get("session_id") or ""))
        return web.json_response({"ok": removed})

    async def _byok_get(self, request: web.Request) -> web.Response:
        denied = self._require_loopback(request)
        if denied:
            return denied
        from doubao_typeless.services.byok import redact_for_log

        byok = self.byok
        key = getattr(byok, "api_key", "") if byok else ""
        return web.json_response(
            {
                "endpoint": getattr(byok, "endpoint", "") if byok else "",
                "api_key_set": bool(key),
                "redacted": redact_for_log(key),
                "phone_cannot_set": True,
            }
        )

    async def _byok_post(self, request: web.Request) -> web.Response:
        denied = self._require_loopback(request)
        if denied:
            return denied
        body = await request.json()
        if self.byok is None:
            return web.json_response({"error": "byok unavailable"}, status=400)
        from doubao_typeless.services.byok import endpoint_host, redact_for_log

        new_endpoint = str(body.get("endpoint") or "").strip()
        old_host = endpoint_host(self.byok.endpoint)
        new_host = endpoint_host(new_endpoint)
        if new_endpoint and old_host and new_host and new_host != old_host and "api_key" not in body:
            return web.json_response(
                {
                    "needs_reauth": True,
                    "message": "更换服务地址后，需重新授权密钥",
                    "endpoint": self.byok.endpoint,
                }
            )
        self.byok.endpoint = new_endpoint
        if "api_key" in body:
            self.byok.api_key = str(body.get("api_key") or "").strip()
        if "model" in body:
            self.byok.model = str(body.get("model") or "").strip()
        if self.data_dir is not None:
            from doubao_typeless.storage.settings_store import save_settings

            save_settings(
                self.data_dir,
                {
                    "byok_endpoint": self.byok.endpoint,
                    "byok_api_key": self.byok.api_key,
                    "byok_model": getattr(self.byok, "model", ""),
                },
            )
        return web.json_response({"ok": True, "redacted": redact_for_log(self.byok.api_key)})

    async def _byok_probe(self, request: web.Request) -> web.Response:
        denied = self._require_loopback(request)
        if denied:
            return denied
        if self.byok is None:
            return web.json_response({"status": "skipped", "reason": "no_key", "text": "probe"})
        body = await request.json()
        text = str(body.get("text") or "probe")
        out = self.byok.polish(
            text,
            draft_id=self.draft.draft_id,
            revision=self.draft.revision,
            current_draft_id=self.draft.draft_id,
            current_revision=self.draft.revision,
        )
        dumped = json.dumps(out, ensure_ascii=False)
        key = getattr(self.byok, "api_key", "")
        if key and key in dumped:
            return web.json_response({"error": "key leaked"}, status=500)
        return web.json_response(out)

    async def _hotkeys_get(self, request: web.Request) -> web.Response:
        denied = self._require_loopback(request)
        if denied:
            return denied
        from doubao_typeless.platform.windows.hotkeys import probe_hotkey_conflicts
        from doubao_typeless.storage.settings_store import load_settings

        stored = load_settings(self.data_dir) if self.data_dir else {}
        probe = probe_hotkey_conflicts()
        return web.json_response(
            {
                "insert": stored.get("hotkey_insert") or "<alt>+i",
                "recall": stored.get("hotkey_recall") or "<alt>+<shift>+i",
                "probe": probe,
                "note": "Alt+Shift+I 现为召回上次图文，不再同时绑定跳过纠错。语法合法不等于注册成功。",
                "restart_required_to_apply": True,
            }
        )

    async def _hotkeys_post(self, request: web.Request) -> web.Response:
        denied = self._require_loopback(request)
        if denied:
            return denied
        if self.data_dir is None:
            return web.json_response({"error": "no isolated settings"}, status=400)
        body = await request.json()
        from doubao_typeless.storage.settings_store import save_settings

        save_settings(
            self.data_dir,
            {
                "hotkey_insert": str(body.get("hotkey_insert") or "<alt>+i"),
                "hotkey_recall": str(body.get("hotkey_recall") or "<alt>+<shift>+i"),
            },
        )
        return web.json_response({"ok": True, "restart_required": True, "hint": "失败请改键，语法合法不等于注册成功"})

    async def _terms(self, request: web.Request) -> web.Response:
        self._session_from(request)
        from doubao_typeless.services.terms import hints

        return web.json_response({"hints": hints(str(request.query.get("q") or "")), "auto_replace": False})

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
        try:
            session = self.auth.authorize(body["session_id"], body["token"], "insert")
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=403)
        return web.json_response({"nonce": self.auth.issue_nonce(session)})

    def _session_from(self, request: web.Request):
        session_id = request.headers.get("X-DT-Session", "")
        token = request.headers.get("X-DT-Token", "")
        try:
            return self.auth.authorize(session_id, token, "sync")
        except ValueError as exc:
            raise web.HTTPUnauthorized(text=str(exc)) from exc

    async def _asset_post(self, request: web.Request) -> web.Response:
        session = self._session_from(request)
        data = await request.read()
        width = int(request.query.get("w", "1"))
        height = int(request.query.get("h", "1"))
        role = request.query.get("role", "photo")
        meta = self.store.put_png(data, width=width, height=height, role=role)
        db = getattr(self.uploads, "db", None)
        if db is not None:
            db.upsert_asset(
                meta["asset_id"],
                meta["sha256"],
                meta["bytes"],
                referenced=False,
                owner_session_id=session.session_id,
            )
        if self._on_activity and should_wake("draft.update"):
            self._on_activity(self.draft.text, max(1, len(self.draft.assets)))
        return web.json_response(meta)

    async def _asset_init(self, request: web.Request) -> web.Response:
        owner = self._session_from(request)
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
                owner_session_id=owner.session_id,
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(session)

    async def _asset_chunk(self, request: web.Request) -> web.Response:
        owner = self._session_from(request)
        if self.uploads is None:
            raise web.HTTPNotImplemented()
        data = await request.read()
        try:
            self.uploads.put_chunk(
                request.match_info["upload_id"],
                int(request.match_info["index"]),
                data,
                owner_session_id=owner.session_id,
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True})

    async def _asset_complete(self, request: web.Request) -> web.Response:
        owner = self._session_from(request)
        if self.uploads is None:
            raise web.HTTPNotImplemented()
        try:
            meta = self.uploads.complete(request.match_info["upload_id"], owner_session_id=owner.session_id)
        except ValueError as exc:
            return web.json_response({"error": str(exc), "durable": False}, status=400)
        except OSError as exc:
            return web.json_response({"error": str(exc), "durable": False}, status=507)
        return web.json_response(meta)

    async def _asset_missing(self, request: web.Request) -> web.Response:
        owner = self._session_from(request)
        if self.uploads is None:
            raise web.HTTPNotImplemented()
        try:
            missing = self.uploads.missing_chunks(request.match_info["upload_id"], owner_session_id=owner.session_id)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"missing": missing})

    async def _asset_get(self, request: web.Request) -> web.StreamResponse:
        session = self._session_from(request)
        asset_id = request.match_info["asset_id"]
        db = getattr(self.uploads, "db", None)
        if db is not None:
            row = db.asset_by_id(asset_id)
            owner = str((row or {}).get("owner_session_id") or "")
            if owner and owner != session.session_id:
                raise web.HTTPForbidden(text="asset owner")
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
        refs = data.get("asset_refs")
        if refs is not None:
            assets = resolve_asset_refs(self.store, refs)
        else:
            assets = self.draft.assets
            refs = [a["asset_id"] for a in assets]
        apply_draft_update(
            self.draft,
            {
                "text": data.get("text", self.draft.text),
                "revision": int(data.get("revision") or self.draft.revision + 1),
                "asset_refs": refs,
                "assets": assets,
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
        live = self._ws_auth.get(id(ws))
        if live is None or live.session_id not in self.auth.sessions:
            await ws.send_json({"type": "error", "error": "session revoked"})
            return False
        try:
            self.auth.authorize(live.session_id, live.token, "sync")
        except ValueError:
            await ws.send_json({"type": "error", "error": "session revoked"})
            return False
        if self.paused and kind in {
            "draft.update",
            "editor.activity",
            "bundle.commit",
            "insert.intent",
            "capture.request",
        }:
            await ws.send_json({"type": "error", "error": "paused"})
            return True
        try:
            if kind == "draft.update":
                if self._on_phone_draft:
                    ack = self._on_phone_draft(data)
                    await ws.send_json({"type": "draft.ack", **ack})
                    return True
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
                if self._is_pc_editing():
                    await ws.send_json({"type": "error", "error": "pc_editing", "message": "电脑正在改字"})
                    return True
                if "text" in data or "revision" in data:
                    self._apply_draft_fields(data)
                bundle = freeze_bundle(self.draft, bundle_id=str(uuid.uuid4()))
                self.last_bundle = bundle
                public = {k: v for k, v in bundle.items() if k != "bytes_data"}
                await ws.send_json({"type": "bundle.ready", "bundle": public})
                return True
            if kind == "insert.intent":
                if self._is_pc_editing():
                    await ws.send_json({"type": "error", "error": "pc_editing", "message": "电脑正在改字"})
                    return True
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
                try:
                    session = self.auth.authorize(data["session_id"], data.get("token") or "", "capture")
                except ValueError:
                    await ws.send_json(
                        {
                            "type": "capture.result",
                            "error": "CAPTURE_DENIED",
                            "message": "这台手机还没有截图权限，文字仍可同步",
                        }
                    )
                    return True
                if not self._on_capture:
                    await ws.send_json({"type": "capture.result", "error": "unavailable"})
                    return True
                try:
                    meta = self._on_capture(
                        str(data.get("scope") or "primary"),
                        str(data.get("request_id") or uuid.uuid4()),
                        session,
                    )
                except ValueError as exc:
                    await ws.send_json({"type": "capture.result", "error": str(exc)})
                    return True
                await ws.send_json({"type": "capture.result", "asset": meta})
                return True
            if kind == "recall.last":
                before = (self.draft.text, [a.get("asset_id") for a in self.draft.assets])
                if self._on_recall:
                    self._on_recall()
                await ws.send_json(
                    {
                        "type": "recall.ready",
                        "current_kept": True,
                        "draft_revision": self.draft.revision,
                        "text_unchanged": self.draft.text == before[0],
                        "assets_unchanged": [a.get("asset_id") for a in self.draft.assets] == before[1],
                    }
                )
                return True
            if kind == "byok.request":
                await ws.send_json({"type": "error", "error": "byok stays on desktop"})
                return True
        except ValueError as exc:
            await ws.send_json({"type": "error", "error": str(exc)})
            return authorized
        return authorized

