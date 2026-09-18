"""On-demand HUD tokens. Keep sizes exact; ping must not wake."""
from __future__ import annotations

ACCENT = "#167D71"
SURFACE = "#FFFFFF"
INK = "#1D2826"
MUTED = "#63716D"
TEXT_SIZE = (360, 88)
IMAGE_SIZE = (360, 132)
IDLE_MS = 6000
RESULT_HIDE_MS = 900

WAKE_EVENTS = frozenset({"draft.update", "editor.activity", "insert.progress"})


def should_wake(event_type: str) -> bool:
    return event_type in WAKE_EVENTS
