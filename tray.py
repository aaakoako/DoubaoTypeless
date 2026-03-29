import threading
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw, ImageFont

from app_icon import load_tray_image


STATE_READY = "ready"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"

COLORS = {
    STATE_READY: "#4CAF50",
    STATE_RECORDING: "#F44336",
    STATE_PROCESSING: "#FF9800",
}

# 托盘图标状态角标颜色（RGBA），叠加在基础图标上
_STATE_DOT = {
    STATE_READY: (76, 175, 80, 220),
    STATE_RECORDING: (244, 67, 54, 220),
    STATE_PROCESSING: (255, 152, 0, 220),
}


def _create_icon_image(state: str, size: int = 64) -> Image.Image:
    base = load_tray_image()
    if base is None:
        return _fallback_icon_image(state, size)
    img = base.copy()
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    dot = _STATE_DOT.get(state, (136, 136, 136, 200))
    draw.ellipse([size - 22, 4, size - 4, 22], fill=dot)
    return Image.alpha_composite(img, overlay)


def _fallback_icon_image(state: str, size: int = 64) -> Image.Image:
    color = COLORS.get(state, "#888888")
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
    )
    try:
        font = ImageFont.truetype("arial.ttf", size // 2)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "D", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
        "D",
        fill="white",
        font=font,
    )
    return img


class SystemTray:
    """System tray icon with state display."""

    def __init__(
        self,
        on_settings: Optional[Callable] = None,
        on_quit: Optional[Callable] = None,
        on_debug_log: Optional[Callable] = None,
        on_check_update: Optional[Callable] = None,
        app_version: str = "",
    ):
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._on_debug_log = on_debug_log
        self._on_check_update = on_check_update
        self._app_version = (app_version or "").strip()
        self._state = STATE_READY
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def _build_menu(self):
        items = []
        if self._on_settings:
            items.append(pystray.MenuItem("设置", lambda: self._on_settings()))
        if self._on_check_update:
            items.append(pystray.MenuItem("检查更新", lambda: self._on_check_update()))
        if self._on_debug_log:
            items.append(pystray.MenuItem("调试日志", lambda: self._on_debug_log()))
        items.append(pystray.MenuItem("退出", self._handle_quit))
        return pystray.Menu(*items)

    def _handle_quit(self):
        if self._icon:
            self._icon.stop()
        if self._on_quit:
            self._on_quit()

    def _title_for_state(self, state: str) -> str:
        ver = self._app_version
        prefix = f"DoubaoTypeless v{ver}" if ver else "DoubaoTypeless"
        tails = {
            STATE_READY: "就绪",
            STATE_RECORDING: "录音中...",
            STATE_PROCESSING: "识别中...",
        }
        return f"{prefix} - {tails.get(state, '就绪')}"

    def set_state(self, state: str):
        self._state = state
        if self._icon:
            self._icon.icon = _create_icon_image(state)
            self._icon.title = self._title_for_state(state)

    def start(self):
        self._icon = pystray.Icon(
            "DoubaoTypeless",
            icon=_create_icon_image(self._state),
            title=self._title_for_state(self._state),
            menu=self._build_menu(),
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._icon:
            self._icon.stop()
