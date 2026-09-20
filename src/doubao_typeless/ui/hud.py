"""On-demand HUD. Idle is invisible and never steals focus."""
from __future__ import annotations

from typing import Callable
from doubao_typeless.ui.theme import style_root
from doubao_typeless.ui.theme_generated import COLORS

TOKENS = {
    "accent": COLORS["accent"],
    "surface": COLORS["surface"],
    "ink": COLORS["ink"],
    "muted": COLORS["muted"],
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
        self._mode = "receiving"
        self._operation_message = ""
        self._content_serial = 0
        self._operation_content_serial = 0
        self._dispatch = None

    def start(self) -> None:
        try:
            from PySide6.QtCore import Qt, QTimer, QObject, Signal
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
        style_root(w, hud=True)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16,12,16,12)
        layout.setSpacing(8)
        self._status = QLabel("手机输入中")
        self._status.setProperty("role", "status")
        self._status.setWordWrap(True)
        self._status.setObjectName("DTInsertStatus")
        self._status.setWordWrap(True)
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
        self._body.setObjectName("hudBody")
        bar = QWidget()
        bar.setFixedHeight(40)
        bar.setStyleSheet("background:transparent;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        expand = QPushButton("展开")
        expand.setFixedHeight(32)
        expand.clicked.connect(lambda: self._on_expand and self._on_expand())
        self._expand = expand
        copy = QPushButton("复制")
        copy.setFixedHeight(32)
        copy.clicked.connect(lambda: self._on_copy and self._on_copy())
        self._copy = copy
        btn = QPushButton("插入并复制")
        btn.setObjectName("DTInsertAction")
        btn.setProperty("role", "primary")
        btn.setAccessibleName("插入并复制")
        btn.setFixedHeight(32)
        btn.clicked.connect(lambda: self._on_insert and self._on_insert())
        self._insert = btn
        row.addWidget(expand, 0)
        row.addWidget(copy, 0)
        row.addWidget(btn, 0)
        row.addStretch(1)
        dismiss = QPushButton("×")
        dismiss.setToolTip("收起，不清空草稿")
        dismiss.setFixedSize(24, 28)
        dismiss.clicked.connect(self.dismiss)
        row.addWidget(dismiss)
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
        controller = self
        class Dispatcher(QObject):
            called = Signal(object)
            def __init__(inner):
                super().__init__(w)
                inner.called.connect(inner.receive, Qt.QueuedConnection)
            def receive(inner, message):
                kind, payload = message
                if kind == "show":
                    controller._apply_content_update()
                elif kind == "hide":
                    controller._apply_hide()
                elif kind == "operation":
                    controller._apply_operation(**payload)
        self._dispatch = Dispatcher()
        self._timer = QTimer(w)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._idle_timeout)
        try:
            self._body.selectionChanged.connect(self._pause_or_resume_idle)
            bar = self._body.verticalScrollBar()
            if bar is not None:
                bar.valueChanged.connect(lambda _v: self._pause_or_resume_idle())
        except Exception:
            pass

    def show_receiving(self, text: str, image_count: int = 0, *, assets: list[dict] | None = None,
                       revision: int = 0, phone_primary: bool = False) -> None:
        self._content_serial += 1
        self.text = text
        self.image_count = image_count
        self.assets = [dict(a) for a in (assets or [])]
        self.revision = revision
        self.phone_primary = phone_primary
        self.visible = True
        if self._widget is None:
            return
        self._invoke("show")

    def _invoke(self, kind: str, **payload) -> None:
        if self._widget is None:
            return
        from PySide6.QtCore import QThread
        if QThread.currentThread() != self._widget.thread():
            if self._dispatch is not None:
                self._dispatch.called.emit((kind, payload))
            else:
                # 支持既有嵌入式HUD：外部提供widget、尚未创建专用接收器。
                from PySide6.QtCore import QTimer
                slot = self._apply_show if kind == "show" else (self._apply_hide if kind == "hide" else lambda: self._apply_operation(**payload))
                QTimer.singleShot(0, self._widget, slot)
        elif kind == "show":
            self._apply_content_update()
        elif kind == "hide":
            self._apply_hide()
        else:
            self._apply_operation(**payload)

    def operation_event(self, event: str, **payload) -> None:
        if self._widget is None:
            self._apply_operation(event, **payload)
        else:
            self._invoke("operation", event=event, **payload)

    def _apply_operation(self, event: str, **payload) -> None:
        from doubao_typeless.ui.insert_status import error_message
        if event in {"sync_wait", "delivery_start"}:
            self._mode = "busy"
            self._operation_message = "正在确认手机最新内容…" if event == "sync_wait" else "正在插入，请勿切换输入框…"
            self._operation_content_serial = self._content_serial
        elif event == "delivery_progress":
            stage,index,total=payload.get("stage"),payload.get("index",0),payload.get("total",0)
            message = (f"正在插入第 {index}/{total} 张图片…" if stage=="image" else
                       f"图片 {index}/{total} 已发出，正在等待附件反馈…" if stage=="image_wait" else
                       "图片已接收，正在插入文字…" if total else "正在插入文字…")
            self._mode,self._operation_message="busy",message
        elif event == "composer_locating":
            self._mode, self._operation_message = "busy", "正在查找当前窗口的对话输入框…"
        elif event == "composer_located":
            self._mode, self._operation_message = "failed", "已定位输入框，未插入任何内容；可继续插入或恢复"
        elif event == "delivery_failed":
            self._mode = "failed"
            self._operation_message = error_message(payload)
        elif event == "delivery_complete":
            new_content = self._content_serial > self._operation_content_serial and (self.text or self.assets)
            if new_content and not payload.get("rotated"):
                self._mode, self._operation_message = "receiving", ""
            else:
                self._mode = "result"
                if payload.get("result") == "CONFIRMED":
                    self._operation_message = "目标已接收，上次图文可恢复"
                elif payload.get("text_sent"):
                    self._operation_message = "已发出粘贴并复制；上次内容可恢复"
                else:
                    self._mode = "failed"
                    self._operation_message = (payload.get("progress") or {}).get("message") or "接收结果待确认，图文已保留；请查看目标"
        self.visible = self._mode != "result" or self._widget is not None
        if self._widget is not None:
            self._apply_show()

    def _apply_content_update(self) -> None:
        # 新的一次编辑解除旧结果提示；忙碌期间的同步不得覆盖进度。
        if self._mode in {"failed", "result"}:
            self._mode, self._operation_message = "receiving", ""
        self._apply_show()

    def _idle_timeout(self) -> None:
        if self._mode == "busy":
            return
        if self._mode != "result" and (self._reading() or (self._widget is not None and self._widget.underMouse())):
            self._timer.start(TOKENS["idle_ms"])
            return
        self._apply_hide()

    def dismiss(self) -> None:
        # 用户主动收起不取消已发出的操作，也不清空草稿。
        self.visible = False
        if self._widget is not None:
            if self._timer:
                self._timer.stop()
            self._widget.hide()


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
        if self._mode == "busy" or (self._mode != "result" and self._reading()):
            self._timer.stop()
            return
        self._timer.start(12000 if self._mode == "failed" else (900 if self._mode == "result" else TOKENS["idle_ms"]))

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
            thumb.setStyleSheet("background:#F1F3FA;border:1px solid #DCE1EC;border-radius:6px;font-size:10px;")
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
        self._status.setText(self._operation_message if self._mode != "receiving" else status)
        self._insert.setEnabled(not unfinished and self._mode != "busy")
        self._copy.setEnabled(self._mode != "busy")
        self._insert.setText("处理中…" if self._mode == "busy" else ("图片同步中" if unfinished else "插入并复制"))
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
            if self._mode == "busy" or (reading and self._mode != "result"):
                self._timer.stop()
            else:
                self._timer.start(12000 if self._mode == "failed" else (900 if self._mode == "result" else TOKENS["idle_ms"]))

    def hide(self) -> None:
        # 普通空稿/活动回执不能提前隐藏等待中的操作。
        if self._mode == "busy":
            return
        self.visible = False
        self._invoke("hide")

    def _apply_hide(self) -> None:
        if self._mode == "busy":
            return
        self.visible = False
        if self._timer is not None:
            self._timer.stop()
        if self._widget is not None:
            self._widget.hide()
        self._mode, self._operation_message = "receiving", ""
