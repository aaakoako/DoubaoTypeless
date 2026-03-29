"""
Phone-to-PC text bridge over local HTTP and WebSocket.

The PC serves a page on the LAN; the phone opens it and sends text
(composition or committed) over WebSocket. The PC forwards text into
the review / optional LLM / insert pipeline.
"""

import asyncio
import json
import socket
import time
from typing import Callable, Optional

from aiohttp import web

from paths import resource_dir

_PHONE_HTML = (resource_dir() / "phone.html").read_text(encoding="utf-8")


def _get_local_ip() -> str:
    """Best-effort LAN IP detection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class PhoneBridge:
    """Serves a mobile-friendly page and receives text via WebSocket."""

    def __init__(
        self,
        port: int = 8765,
        on_text: Optional[Callable[[str, dict], None]] = None,
        on_update: Optional[Callable[[str, dict], None]] = None,
        logger: Optional[Callable[[str], None]] = None,
        redact_text_in_logs: bool = False,
    ):
        self.port = port
        self._on_text = on_text
        self._on_update = on_update
        self._log = logger or (lambda m: None)
        self._redact_text_in_logs = redact_text_in_logs
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._ws_clients: set[web.WebSocketResponse] = set()
        self.url: str = ""
        self._update_log_last_ts: float = 0.0
        self._update_log_last_comp: object = None
        self._update_log_last_len: int = -1

    async def start(self, loop: asyncio.AbstractEventLoop):
        self._app = web.Application()
        self._app.router.add_get("/", self._handle_page)
        self._app.router.add_get("/ws", self._handle_ws)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()

        ip = _get_local_ip()
        self.url = f"http://{ip}:{self.port}"
        self._log(f"[bridge] 手机页面已启动: {self.url}")

    async def notify_cleared(self):
        """Tell connected phones to clear input (called after PC inserts text)."""
        for ws in list(self._ws_clients):
            try:
                await ws.send_json({"type": "cleared"})
            except Exception:
                pass

    async def stop(self):
        for ws in list(self._ws_clients):
            await ws.close()
        if self._runner:
            await self._runner.cleanup()

    async def _handle_page(self, request: web.Request) -> web.Response:
        ip = _get_local_ip()
        ws_url = f"ws://{ip}:{self.port}/ws"
        html = _PHONE_HTML.replace("{{WS_URL}}", ws_url)
        return web.Response(
            text=html,
            content_type="text/html",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        self._update_log_last_len = -1
        self._log(f"[bridge] 手机已连接 ({len(self._ws_clients)} 台)")

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        data = {"type": "text", "text": msg.data}

                    msg_type = data.get("type", "text")
                    text = data.get("text", "")
                    meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}

                    if msg_type == "update" and self._on_update:
                        now = time.monotonic()
                        comp = meta.get("isComposing")
                        plen = len(text)
                        if self._update_log_last_len < 0:
                            should_log = True
                        else:
                            should_log = (
                                now - self._update_log_last_ts >= 0.45
                                or comp != self._update_log_last_comp
                                or abs(plen - self._update_log_last_len) >= 28
                            )
                        if should_log:
                            self._update_log_last_ts = now
                            self._update_log_last_comp = comp
                            self._update_log_last_len = plen
                            tail = (
                                ""
                                if self._redact_text_in_logs
                                else f" text='{text[:40]}{'...' if plen > 40 else ''}'"
                            )
                            self._log(
                                "[bridge.update] "
                                f"len={plen} composing={comp} "
                                f"input_type={meta.get('inputType')} "
                                f"since_comp_end_ms={meta.get('sinceCompositionEndMs')}"
                                f"{tail}"
                            )
                        self._on_update(text, meta)
                    elif msg_type == "stable" and text and self._on_text:
                        st = len(text)
                        tail = (
                            ""
                            if self._redact_text_in_logs
                            else f" text='{text[:60]}{'...' if st > 60 else ''}'"
                        )
                        self._log(
                            "[bridge.stable] "
                            f"len={st} composing={meta.get('isComposing')} "
                            f"reason={meta.get('stableReason')} "
                            f"since_comp_end_ms={meta.get('sinceCompositionEndMs')}"
                            f"{tail}"
                        )
                        self._on_text(text, meta)
                    elif msg_type == "send" and text and self._on_text:
                        sn = len(text)
                        tail = (
                            ""
                            if self._redact_text_in_logs
                            else f" text='{text[:60]}{'...' if sn > 60 else ''}'"
                        )
                        self._log(
                            "[bridge.send] "
                            f"len={sn} composing={meta.get('isComposing')}"
                            f"{tail}"
                        )
                        self._on_text(text, meta)
                    elif msg_type == "composition":
                        self._log(
                            "[bridge.composition] "
                            f"phase={meta.get('phase')} "
                            f"len={len(text)} composing={meta.get('isComposing')} "
                            f"since_comp_end_ms={meta.get('sinceCompositionEndMs')}"
                        )
                    elif msg_type == "hello":
                        self._log(
                            "[bridge.hello] "
                            f"client_version={meta.get('clientVersion')} "
                            f"meta_enabled={meta.get('metaEnabled')} "
                            f"composition_support={meta.get('compositionSupport')} "
                            f"user_agent='{meta.get('userAgent', '')[:80]}'"
                        )
                    elif msg_type == "ping":
                        await ws.send_json({"type": "pong"})
                elif msg.type == web.WSMsgType.ERROR:
                    self._log(f"[bridge] WS error: {ws.exception()}")
        finally:
            self._ws_clients.discard(ws)
            self._log(f"[bridge] 手机断开 ({len(self._ws_clients)} 台)")

        return ws
