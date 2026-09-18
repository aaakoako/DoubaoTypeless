"""DPI-aware primary/region PNG capture. Scopes are physical-pixel bboxes, never HWND."""
from __future__ import annotations

import ctypes
import io
from ctypes import wintypes
from typing import Callable

user32 = ctypes.windll.user32
shcore = getattr(ctypes.windll, "shcore", None)


def ensure_dpi_aware() -> str:
    if shcore is not None:
        try:
            shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            return "per_monitor"
        except Exception:
            pass
    try:
        user32.SetProcessDPIAware()
        return "system"
    except Exception:
        return "unaware"


def _monitor_enum() -> list[tuple[int, int, int, int]]:
    monitors: list[tuple[int, int, int, int]] = []

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
    )

    def _cb(hmon, _hdc, _lprc, _lp):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        r = info.rcMonitor
        monitors.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return 1

    user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_cb), 0)
    return monitors


def list_monitors() -> list[dict]:
    ensure_dpi_aware()
    out = []
    for i, (l, t, r, b) in enumerate(_monitor_enum(), start=1):
        out.append(
            {
                "scope": "primary" if i == 1 else f"display:{i}",
                "left": l,
                "top": t,
                "width": r - l,
                "height": b - t,
            }
        )
    if not out:
        w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        out.append({"scope": "primary", "left": 0, "top": 0, "width": w, "height": h})
    return out


def primary_bbox() -> tuple[int, int, int, int]:
    mons = list_monitors()
    m = mons[0]
    return m["left"], m["top"], m["left"] + m["width"], m["top"] + m["height"]


def parse_scope(scope: str) -> tuple[int, int, int, int]:
    if scope in {"primary", "display:1"}:
        return primary_bbox()
    if scope.startswith("display:"):
        idx = int(scope.split(":", 1)[1])
        mons = list_monitors()
        if idx < 1 or idx > len(mons):
            raise ValueError("unknown capture scope")
        m = mons[idx - 1]
        return m["left"], m["top"], m["left"] + m["width"], m["top"] + m["height"]
    if scope.startswith("region:"):
        x, y, w, h = [int(p) for p in scope.split(":", 1)[1].split(",")]
        if w <= 0 or h <= 0:
            raise ValueError("unknown capture scope")
        return x, y, x + w, y + h
    raise ValueError("unknown capture scope")


def grab_bbox(bbox: tuple[int, int, int, int], *, hide: Callable[[], None] | None = None) -> bytes:
    ensure_dpi_aware()
    if hide:
        hide()
    from PIL import ImageGrab

    image = ImageGrab.grab(bbox=bbox, all_screens=True)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def grab_primary(scope: str = "primary", *, hide: Callable[[], None] | None = None) -> bytes:
    return grab_bbox(parse_scope(scope), hide=hide)
