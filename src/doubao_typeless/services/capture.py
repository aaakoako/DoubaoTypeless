"""Screen capture. Only enumerated scopes; never a raw HWND from the network."""
from __future__ import annotations

import time
from typing import Callable

from doubao_typeless.storage.credentials import Session

REQUEST_TTL_S = 15.0
MIN_INTERVAL_S = 1.0


class CaptureService:
    def __init__(
        self,
        *,
        grab: Callable[[str], bytes],
        allowed_scopes: tuple[str, ...] = ("primary", "display:1"),
        hide_surfaces: Callable[[], None] | None = None,
    ):
        self._grab = grab
        self.allowed_scopes = allowed_scopes
        self._hide_surfaces = hide_surfaces
        self._requests: dict[str, tuple[float, str]] = {}
        self._last_grab_at = 0.0
        self.cancelled: set[str] = set()

    def begin(self, session: Session, scope: str, request_id: str, *, now: float | None = None) -> None:
        if not session.allow_capture:
            raise ValueError("capture not granted")
        if scope.startswith("hwnd:") or scope.startswith("0x"):
            raise ValueError("unknown capture scope")
        if scope not in self.allowed_scopes:
            raise ValueError("unknown capture scope")
        now = time.monotonic() if now is None else now
        self._requests[request_id] = (now + REQUEST_TTL_S, scope)

    def cancel(self, request_id: str) -> None:
        self.cancelled.add(request_id)
        self._requests.pop(request_id, None)

    def capture(self, session: Session, scope: str, *, request_id: str = "", now: float | None = None) -> bytes:
        if request_id:
            self.begin(session, scope, request_id, now=now)
            return self.complete(request_id, session, now=now)
        if not session.allow_capture:
            raise ValueError("capture not granted")
        if scope not in self.allowed_scopes:
            raise ValueError("unknown capture scope")
        return self._do_grab(scope, now=now)

    def complete(self, request_id: str, session: Session, *, now: float | None = None) -> bytes:
        if request_id in self.cancelled:
            raise ValueError("capture cancelled")
        if not session.allow_capture:
            raise ValueError("capture not granted")
        pending = self._requests.pop(request_id, None)
        if pending is None:
            raise ValueError("capture request missing")
        expiry, scope = pending
        now = time.monotonic() if now is None else now
        if now > expiry:
            raise ValueError("capture expired")
        return self._do_grab(scope, now=now)

    def _do_grab(self, scope: str, *, now: float | None = None) -> bytes:
        now = time.monotonic() if now is None else now
        if now - self._last_grab_at < MIN_INTERVAL_S:
            raise ValueError("capture rate limited")
        if self._hide_surfaces:
            self._hide_surfaces()
        self._last_grab_at = now
        return self._grab(scope)
