"""Screen capture. Only enumerated scopes; never a raw HWND from the network."""
from __future__ import annotations

from typing import Callable

from doubao_typeless.storage.credentials import Session


class CaptureService:
    def __init__(self, *, grab: Callable[[str], bytes], allowed_scopes: tuple[str, ...] = ("primary",)):
        self._grab = grab
        self.allowed_scopes = allowed_scopes

    def capture(self, session: Session, scope: str) -> bytes:
        if not session.allow_capture:
            raise ValueError("capture not granted")
        if scope not in self.allowed_scopes:
            raise ValueError("unknown capture scope")
        return self._grab(scope)
