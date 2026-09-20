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
        self.assets: list[dict] = []
        self.revision = 0
        self.phone_primary = False
        self._thumbs = None
        self._thumb_row = None
        self._thumb_signature = None
        self._timer = None
        self._widget = None
        self._app = None
        self._expand = None
        self._bar = None
        self._status = None
        self._insert = None
        self._copy = None
        self._body = None

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
        self._body.setMinimumHeight(40)
        try:
            from PySide6.QtWidgets import QSizePolicy

            self._body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        except Exception:
            pass
        self._body.setFrameShape(self._body.NoFrame if hasattr(self._body, "NoFrame") else self._body.frameShape())
        try:
            from PySide6.QtWidgets import QFrame

            self._body.setFrameShape(QFrame.NoFrame)
        except Exception:
            pass
        self._body.setStyleSheet("border:0; background:transparent; font-size:14px; color:#1D2826;")
        bar = QWidget()
        bar.setFixedHeight(40)
        bar.setStyleSheet("background:transparent;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        expand = QPushButton("展开")
        expand.setFixedHeight(32)
        expand.setStyleSheet("background:#E7EEEC; color:#1D2826; border:0; border-radius:9px; padding:6px 10px;")
        expand.clicked.connect(lambda: self._on_expand and self._on_expand())
        self._expand = expand
        copy = QPushButton("复制")
        copy.setFixedHeight(32)
        copy.setStyleSheet("background:#E7EEEC; color:#1D2826; border:0; border-radius:9px; padding:6px 10px;")
        copy.clicked.connect(lambda: self._on_copy and self._on_copy())
        self._copy = copy
        btn = QPushButton("插入并复制")
        btn.setFixedHeight(32)
        btn.setStyleSheet(f"background:{TOKENS['accent']}; color:white; border:0; border-radius:9px; padding:6px 10px;")
        btn.clicked.connect(lambda: self._on_insert and self._on_insert())
        self._insert = btn
        row.addWidget(expand, 0)
        row.addWidget(copy, 0)
        row.addWidget(btn, 0)
        row.addStretch(1)
        layout.addWidget(self._status, 0)
        layout.addWidget(self._body, 1)
        thumbs = QWidget()
        thumbs.setFixedHeight(62)
        self._thumb_row = QHBoxLayout(thumbs)
        self._thumb_row.setContentsMargins(0, 0, 0, 0)
        self._thumb_row.setSpacing(5)
        thumbs.hide()
        self._thumbs = thumbs
        layout.addWidget(thumbs, 0)
        layout.addWidget(bar, 0)
        self._bar = bar
        w.hide()
        self._widget = w
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        try:
            self._body.selectionChanged.connect(self._pause_or_resume_idle)
            bar = self._body.verticalScrollBar()
            if bar is not None:
                bar.valueChanged.connect(lambda _v: self._pause_or_resume_idle())
        except Exception:
            pass

    def show_receiving(self, text: str, image_count: int = 0, *, assets: list[dict] | None = None,
                       revision: int = 0, phone_primary: bool = False) -> None:
        self.text = text
        self.image_count = image_count
        self.assets = [dict(a) for a in (assets or [])]
        self.revision = revision
        self.phone_primary = phone_primary
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

    def _chrome_height(self) -> int:
        status_h = self._status.sizeHint().height() if getattr(self, "_status", None) else 18
        bar_h = self._bar.height() if getattr(self, "_bar", None) is not None else 40
        margins = 18
        spacing = 12
        try:
            layout = self._widget.layout() if self._widget is not None else None
            if layout is not None:
                box = layout.contentsMargins()
                margins = box.top() + box.bottom()
                spacing = max(layout.spacing(), 0) * 2
        except Exception:
            pass
        return status_h + bar_h + margins + spacing + (68 if self.assets else 0)

    def _text_height(self, text: str) -> int:
        try:
            from PySide6.QtCore import QRect, Qt

            metrics = self._body.fontMetrics()
            inner = max(80, TOKENS["width"] - 36)
            rect = metrics.boundingRect(QRect(0, 0, inner, 10_000), int(Qt.TextWordWrap), text)
            return max(40, rect.height() + 12)
        except Exception:
            return max(40, 21 * max(1, (len(text) + 19) // 20))

    def _reading(self) -> bool:
        if self._body is None:
            return False
        try:
            if self._body.textCursor().hasSelection():
                return True
            bar = self._body.verticalScrollBar()
            if bar is not None and bar.maximum() > 0 and bar.value() < max(0, bar.maximum() - 4):
                return True
        except Exception:
            return False
        return False

    def _pause_or_resume_idle(self) -> None:
        if self._timer is None:
            return
        if self._reading():
            self._timer.stop()
            return
        self._timer.start(TOKENS["idle_ms"])

    def _refresh_thumbnails(self) -> None:
        if self._thumbs is None:
            return
        signature = repr(self.assets)
        if signature == self._thumb_signature:
            return
        self._thumb_signature = signature
        from PySide6.QtCore import Qt, QSize
        from PySide6.QtGui import QImageReader, QPixmap
        from PySide6.QtWidgets import QLabel
        while self._thumb_row.count():
            old = self._thumb_row.takeAt(0).widget()
            if old is not None:
                old.deleteLater()
        for i, asset in enumerate(self.assets[:6], 1):
            thumb = QLabel()
            thumb.setFixedSize(54, 56)
            thumb.setAlignment(Qt.AlignCenter)
            status = asset.get("status", "ready")
            caption = {"editing": "编辑中", "queued": "同步中", "failed": "待重试", "dirty": "未同步"}.get(status, "已收到")
            thumb.setText(f"{i}\n{caption}")
            thumb.setStyleSheet("background:#EEF4F2;border:1px solid #D9E6E1;border-radius:6px;font-size:10px;")
            path = asset.get("path")
            if path and status == "ready":
                reader = QImageReader(path)
                size = reader.size()
                if size.isValid():
                    reader.setScaledSize(size.scaled(QSize(52, 52), Qt.KeepAspectRatio))
                    image = reader.read()
                    if not image.isNull():
                        thumb.setPixmap(QPixmap.fromImage(image))
            thumb.setToolTip(f"图{i} · {caption} · 版本{asset.get('render_revision',1)}")
            self._thumb_row.addWidget(thumb)
        self._thumb_row.addStretch(1)
        self._thumbs.setVisible(bool(self.assets))

    def _apply_show(self) -> None:
        if self._widget is None:
            return
        self._refresh_thumbnails()
        unfinished = sum(a.get("status", "ready") != "ready" for a in self.assets)
        ready = len(self.assets) - unfinished
        status = f"手机稿 · r{self.revision}" if self.phone_primary else "手机输入中"
        if self.assets:
            status += f" · {ready}/{len(self.assets)} 张已收到" if unfinished else f" · {ready} 张图片已更新"
        self._status.setText(status)
        self._insert.setEnabled(not unfinished)
        self._insert.setText("图片同步中" if unfinished else "插入并复制")
        body = self.text if self.text else ("图片准备中，可继续在手机写说明" if unfinished else "")
        # 程序主动写字造成的滚动条变化，不能被误判成用户正在读前文。
        reading = self._widget.isVisible() and self._reading()
        old_cursor = self._body.textCursor()
        position, anchor = old_cursor.position(), old_cursor.anchor()
        scroll = self._body.verticalScrollBar()
        scroll_pos = scroll.value()
        self._body.blockSignals(True)
        scroll.blockSignals(True)
        self._body.setPlainText(body)
        chrome = self._chrome_height()
        max_h = self._max_height()
        doc_h = self._text_height(body)
        min_h = TOKENS["min_image_h"] if self.image_count else TOKENS["min_text_h"]
        body_h = max(40, min(doc_h, max_h - chrome))
        height = max(min_h, min(max_h, body_h + chrome))
        self._body.setMaximumHeight(body_h)
        self._widget.setFixedWidth(TOKENS["width"])
        self._widget.resize(TOKENS["width"], height)
        try:
            layout = self._widget.layout()
            if layout is not None:
                layout.activate()
        except Exception:
            pass
        from PySide6.QtGui import QTextCursor
        cursor = self._body.textCursor()
        if reading:
            cursor.setPosition(min(anchor, len(body)))
            cursor.setPosition(min(position, len(body)), QTextCursor.KeepAnchor)
            self._body.setTextCursor(cursor)
            scroll.setValue(scroll_pos)
        else:
            cursor.movePosition(QTextCursor.End)
            self._body.setTextCursor(cursor)
            scroll.setValue(scroll.maximum())
        self._body.blockSignals(False)
        scroll.blockSignals(False)
        self._widget.show()
        from PySide6.QtCore import QTimer
        # 第一次show后QTextDocument可能再计算一次边距；只在仍然追尾时校正。
        generation = getattr(self, "_render_generation", 0) + 1
        self._render_generation = generation
        def settle_tail():
            if (self._widget.isVisible() and self._render_generation == generation
                    and not reading and not self._reading()):
                self._body.verticalScrollBar().setValue(self._body.verticalScrollBar().maximum())
        QTimer.singleShot(0, self._widget, settle_tail)
        if self._timer:
            if reading:
                self._timer.stop()
            else:
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
