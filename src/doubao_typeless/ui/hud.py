"""On-demand HUD. Idle is invisible and never steals focus."""
from __future__ import annotations

from typing import Callable

TOKENS = {
    "accent": "#167D71",
    "surface": "#FFFFFF",
    "ink": "#1D2826",
    "muted": "#63716D",
    "text_size": (360, 88),
    "image_size": (360, 132),
    "idle_ms": 6000,
}


class HudController:
    def __init__(self, *, on_insert: Callable[[], None] | None = None):
        self._on_insert = on_insert
        self.visible = False
        self.text = ""
        self.image_count = 0
        self._timer = None
        self._widget = None
        self._app = None

    def start(self) -> None:
        try:
            from PySide6.QtCore import Qt, QTimer
            from PySide6.QtWidgets import QApplication, QLabel, QWidget, QHBoxLayout, QVBoxLayout, QPushButton
        except ImportError:
            return
        self._app = QApplication.instance() or QApplication([])
        w = QWidget()
        w.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        w.setAttribute(Qt.WA_ShowWithoutActivating, True)
        w.setAttribute(Qt.WA_QuitOnClose, False)
        w.resize(*TOKENS["text_size"])
        w.setStyleSheet(
            f"background:{TOKENS['surface']}; color:{TOKENS['ink']}; border-radius:16px;"
        )
        layout = QVBoxLayout(w)
        self._status = QLabel("手机输入中")
        self._status.setStyleSheet(f"color:{TOKENS['muted']}; font-size:11px;")
        self._body = QLabel("")
        self._body.setWordWrap(True)
        row = QHBoxLayout()
        btn = QPushButton("插入 Alt+I")
        btn.setStyleSheet(f"background:{TOKENS['accent']}; color:white; border:0; border-radius:9px; padding:6px 10px;")
        btn.clicked.connect(lambda: self._on_insert and self._on_insert())
        row.addWidget(self._body, 1)
        row.addWidget(btn, 0)
        layout.addWidget(self._status)
        layout.addLayout(row)
        w.hide()
        self._widget = w
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_receiving(self, text: str, image_count: int = 0) -> None:
        self.text = text
        self.image_count = image_count
        self.visible = True
        if self._widget is None:
            return
        w, h = TOKENS["image_size"] if image_count else TOKENS["text_size"]
        self._widget.resize(w, h)
        self._body.setText(text[-200:] if text else (f"{image_count} 图" if image_count else ""))
        self._widget.show()
        if self._timer:
            self._timer.start(TOKENS["idle_ms"])

    def hide(self) -> None:
        self.visible = False
        if self._widget is not None:
            self._widget.hide()
