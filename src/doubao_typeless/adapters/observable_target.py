"""Observe a product paste target via its state file. Poll until change; never treat sleep as success."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


class FileTargetObserver:
    def __init__(self, path: Path, *, timeout_s: float = 3.0):
        self.path = Path(path)
        snap = self._read()
        self._images = len(snap.get("images") or [])
        self._text = str(snap.get("text") or "")

    def _read(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def observe_image(self) -> str:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            images = self._read().get("images") or []
            if len(images) > self._images:
                self._images = len(images)
                return "observed"
            time.sleep(0.05)
        return "unknown"

    def observe_text(self) -> str:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            text = str(self._read().get("text") or "")
            if text != self._text and "BEFORE" in text and len(text) > len(self._text):
                self._text = text
                return "observed"
            if text != self._text and text.strip() and "BEFORE" not in text:
                self._text = text
                return "observed"
            time.sleep(0.05)
        return "unknown"


def from_env() -> FileTargetObserver | None:
    raw = os.environ.get("DT_V3_TARGET_STATE", "").strip()
    allow = os.environ.get("DT_V3_ALLOW_FILE_OBSERVER", "").strip().lower() in {"1", "true", "yes"}
    if not raw or not allow:
        return None
    return FileTargetObserver(Path(raw))
