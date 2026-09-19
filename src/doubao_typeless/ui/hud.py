"""On-demand HUD. Idle is invisible and never steals focus."""
from __future__ import annotations

from typing import Callable

TOKENS = {
    "accent": "#167D71",
    "surface": "#FFFFFF",
    "ink": "#1D2826",
    "muted": "#63716D",
    "width": 400,
    "min_text_h": 88,
    "min_image_h": 132,
    "max_h": 300,
    "text_size": (400, 88),
    "image_size": (400, 132),
    "idle_ms": 6000,
}


class HudController:
    def __init__(
        self,
        *,
        on_insert: Callable[[], None] | None = None,
        on_expand: Callable[[], None] | None = None,
        on_copy: Callable[[], None] | None = None,
    ):
        self._on_insert = on_insert
        self._on_expand = on_expand
        self._on_copy = on_copy
        self.visible = False
        self.text = ""
        self.image_count = 0
        self._timer = None
        self._widget = None
        self._app = None
        self._expand = None

    def start(self) -> None:
        try:
            from PySide6.QtCore import Qt, QTimer
            from PySide6.QtWidgets import (
                QApplication,
                QHBoxLayout,
                QLabel,
                QPushButton,
                QTextEdit,
                QVBoxLayout,
                QWidget,
            )
        except ImportError:
            return
        self._app = QApplication.instance() or QApplication([])
        w = QWidget()
        w.setWindowTitle("DT-V3-HUD")
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
        self._body = QTextEdit()
        self._body.setReadOnly(True)
        self._body.setFrameShape(self._body.NoFrame if hasattr(self._body, "NoFrame") else self._body.frameShape())
        try:
            from PySide6.QtWidgets import QFrame

            self._body.setFrameShape(QFrame.NoFrame)
        except Exception:
            pass
        self._body.setStyleSheet("border:0; background:transparent;")
        row = QHBoxLayout()
        expand = QPushButton("展开")
        expand.setStyleSheet("background:#E7EEEC; color:#1D2826; border:0; border-radius:9px; padding:6px 10px;")
        expand.clicked.connect(lambda: self._on_expand and self._on_expand())
        self._expand = expand
        copy = QPushButton("复制")
        copy.setStyleSheet("background:#E7EEEC; color:#1D2826; border:0; border-radius:9px; padding:6px 10px;")
        copy.clicked.connect(lambda: self._on_copy and self._on_copy())
        self._copy = copy
        btn = QPushButton("插入并复制")
        btn.setStyleSheet(f"background:{TOKENS['accent']}; color:white; border:0; border-radius:9px; padding:6px 10px;")
        btn.clicked.connect(lambda: self._on_insert and self._on_insert())
        self._insert = btn
        row.addWidget(expand, 0)
        row.addWidget(copy, 0)
        row.addWidget(btn, 0)
        layout.addWidget(self._status)
        layout.addWidget(self._body, 1)
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
        try:
            from PySide6.QtCore import QThread, QTimer

            if QThread.currentThread() != self._widget.thread():
                QTimer.singleShot(0, self._widget, self._apply_show)
                return
        except Exception:
            return
        self._apply_show()

    def _max_height(self) -> int:
        max_h = TOKENS["max_h"]
        try:
            from PySide6.QtGui import QGuiApplication

            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                max_h = min(TOKENS["max_h"], int(screen.availableGeometry().height() * 0.35))
        except Exception:
            pass
        return max(TOKENS["min_text_h"], max_h)

    def _apply_show(self) -> None:
        if self._widget is None:
            return
        body = self.text if self.text else (f"{self.image_count} 图" if self.image_count else "")
        self._body.setPlainText(body)
        hint = self._body.sizeHint().height()
        min_h = TOKENS["min_image_h"] if self.image_count else TOKENS["min_text_h"]
        height = max(min_h, min(self._max_height(), hint + 64))
        self._widget.resize(TOKENS["width"], height)
        self._widget.show()
        if self._timer:
            self._timer.start(TOKENS["idle_ms"])

    def hide(self) -> None:
        self.visible = False
        if self._widget is None:
            return
        try:
            from PySide6.QtCore import QThread, QTimer

            if QThread.currentThread() != self._widget.thread():
                QTimer.singleShot(0, self._widget, self._widget.hide)
                return
        except Exception:
            pass
        self._widget.hide()
