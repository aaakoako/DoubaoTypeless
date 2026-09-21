"""On-demand HUD. Idle is invisible and never steals focus."""
from __future__ import annotations

from typing import Callable
from contextlib import contextmanager
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
        on_recover: Callable[[], None] | None = None,
        position: list | None = None,
        on_position: Callable | None = None,
    ):
        self._on_insert = on_insert
        self._on_expand = on_expand
        self._on_copy = on_copy
        self._on_recover = on_recover
        self._on_position = on_position
        self._saved_position = position
        self._user_positioned = False
        self._companions = []
        self._drag_offset = None
        self._recover = None
        self.visible = False
        self.text = ""
        self.image_count = 0
        self.assets: list[dict] = []
        self.revision = 0
        self.phone_primary = False
        self.phone_online = True
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
        self._foreground_surfaces = set()
        self._updating = False
        self._follow_tail = True
        self._latest = None
        self._draft_key = None
        self._rendered_draft_key = None

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
        w.setAttribute(Qt.WA_TranslucentBackground, True)
        w.setAttribute(Qt.WA_ShowWithoutActivating, True)
        w.setAttribute(Qt.WA_QuitOnClose, False)
        w.resize(*TOKENS["text_size"])
        style_root(w, hud=True)
        from PySide6.QtWidgets import QFrame
        outer = QVBoxLayout(w)
        outer.setContentsMargins(1, 1, 1, 1)
        card = QFrame(w)
        card.setObjectName("card")
        outer.addWidget(card)
        self._card = card
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16,12,16,10)
        layout.setSpacing(8)
        self._status = QLabel("手机输入中")
        self._status.setProperty("role", "status")
        self._status.setWordWrap(True)
        self._status.setObjectName("DTInsertStatus")
        self._status.setWordWrap(True)
        self._status.setCursor(Qt.SizeAllCursor)
        self._status.setToolTip("拖动这里移动浮窗")
        controller = self
        from PySide6.QtCore import QEvent
        class DragHeader(QObject):
            def eventFilter(inner, obj, event):
                if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    controller._drag_offset = event.globalPosition().toPoint() - w.pos()
                    return True
                if event.type() == QEvent.MouseMove and controller._drag_offset is not None:
                    w.move(event.globalPosition().toPoint() - controller._drag_offset)
                    controller._user_positioned = True
                    return True
                if event.type() == QEvent.MouseButtonRelease and controller._drag_offset is not None:
                    controller._drag_offset = None
                    if controller._on_position:
                        controller._on_position([w.x(), w.y()])
                    return True
                return False
        self._drag_filter = DragHeader(w)
        self._status.installEventFilter(self._drag_filter)
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
        bar.setObjectName("hudActions")
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
        self._recover = QPushButton("恢复")
        self._recover.setFocusPolicy(Qt.NoFocus)
        self._recover.setToolTip("查看已插入的部分，再决定如何继续")
        self._recover.clicked.connect(lambda: self._on_recover and self._on_recover())
        self._recover.hide()
        row.addWidget(self._recover, 0)
        row.addWidget(btn, 0)
        row.addStretch(1)
        dismiss = QPushButton("×")
        dismiss.setToolTip("收起，不清空草稿")
        dismiss.setFixedSize(24, 28)
        dismiss.setStyleSheet("QPushButton { padding:0; }")
        dismiss.clicked.connect(self.dismiss)
        row.addWidget(dismiss)
        for action in (expand, copy, btn, dismiss):
            action.setFocusPolicy(Qt.NoFocus)
        header = QHBoxLayout()
        header.addWidget(self._status, 1)
        self._latest = QPushButton("回到最新 ↓")
        self._latest.setFocusPolicy(Qt.NoFocus)
        self._latest.clicked.connect(self._resume_tail)
        self._latest.hide()
        header.addWidget(self._latest)
        layout.addLayout(header)
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
                bar.valueChanged.connect(self._scroll_changed)
                bar.sliderPressed.connect(self._pause_or_resume_idle)
                bar.sliderReleased.connect(self._reading_changed)
            self._body.selectionChanged.connect(self._reading_changed)
        except Exception:
            pass

    def show_receiving(self, text: str, image_count: int = 0, *, assets: list[dict] | None = None,
                       revision: int = 0, phone_primary: bool = False, draft_key: tuple | None = None) -> None:
        self._content_serial += 1
        self.text = text
        self.image_count = image_count
        self.assets = [dict(a) for a in (assets or [])]
        self.revision = revision
        self.phone_primary = phone_primary
        if draft_key is not None:
            self._draft_key = draft_key
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
            if self._recover is not None: self._recover.hide()
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
            if payload.get("copied"):
                self._mode = "result"
                self._operation_message = f"{error_message(payload).split('，')[0].split('；')[0]}；已复制{payload['copied']}，可按 Ctrl+V 粘贴"
        elif event == "recovery_available":
            self._mode = "failed"
            self._operation_message = (payload.get("progress") or {}).get("message") or "部分图文待确认；可点恢复继续"
            if self._recover is not None: self._recover.show()
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
        # 未完成的稿件常驻；切换应用、停止说话都不是用户收起的意图。
        if self._mode == "result":
            self._apply_hide()

    def register_companion(self, widget):
        """普通设置不独占HUD；默认摆放尽量避开它，用户仍能自由拖动。"""
        import weakref
        self._companions.append(weakref.ref(widget))

    def _place(self):
        from PySide6.QtCore import QPoint, QRect
        from PySide6.QtGui import QGuiApplication
        w = self._widget
        if self._saved_position and not self._user_positioned:
            if len(self._saved_position) == 2 and all(isinstance(v, int) for v in self._saved_position):
                target = QPoint(*self._saved_position)
                if any(screen.availableGeometry().contains(target) for screen in QGuiApplication.screens()):
                    w.move(target); self._user_positioned = True
            self._saved_position = None
        if self._user_positioned:
            return
        screen = w.screen() or QGuiApplication.primaryScreen()
        if not screen: return
        area = screen.availableGeometry().adjusted(16, 16, -16, -16)
        xs = [area.right()-w.width()+1, area.left()]
        ys = [area.bottom()-w.height()+1, area.top()]
        candidates = [QRect(x,y,w.width(),w.height()) for y in ys for x in xs]
        occupied=[]
        for ref in self._companions:
            other=ref()
            try:
                if other is not None and other.isVisible(): occupied.append(other.frameGeometry())
            except RuntimeError: pass
        def overlap(rect):
            return sum(max(0,rect.intersected(o).width())*max(0,rect.intersected(o).height()) for o in occupied)
        w.move(min(candidates,key=overlap).topLeft())

    def bind_foreground_surface(self, widget):
        """GUI-thread binding: one desktop action surface at a time.

        Visibility, not activation, owns the lease: clicking a non-activating HUD
        must never hit an action sitting above the expanded review/settings UI.
        No content is discarded and hiding a surface never starts an insertion.
        """
        from PySide6.QtCore import QObject, QEvent
        identity = id(widget)
        hud = self
        class SurfaceGate(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Show:
                    hud._foreground_surfaces.add(identity)
                    hud.dismiss()
                elif event.type() == QEvent.Hide:
                    hud._foreground_surfaces.discard(identity)
                return False
        gate = SurfaceGate(widget)
        widget.installEventFilter(gate)
        widget._dt_hud_surface_gate = gate
        widget.destroyed.connect(lambda *_: hud._foreground_surfaces.discard(identity))
        if widget.isVisible():
            self._foreground_surfaces.add(identity)
            self.dismiss()

    @contextmanager
    def modal_pause(self):
        """GUI-thread scope: retain data while yielding the screen to a dialog."""
        self._modal_depth = getattr(self, "_modal_depth", 0) + 1
        self.dismiss()
        try:
            yield
        finally:
            self._modal_depth -= 1
            # Do not pop the overlay back on cancellation. The next actual action
            # or phone edit can show it normally, without consuming any draft.

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
            layout = self._card.layout() if getattr(self, "_card", None) is not None else None
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

    def _scroll_changed(self, _value=0):
        if self._updating:
            return
        scroll = self._body.verticalScrollBar()
        self._follow_tail = not self._body.textCursor().hasSelection() and not scroll.isSliderDown() and scroll.value() >= scroll.maximum() - 4
        self._latest.setVisible(not self._follow_tail)
        self._pause_or_resume_idle()

    def _reading_changed(self):
        if self._updating:
            return
        self._scroll_changed()
        if not self._body.textCursor().hasSelection() and not self._body.verticalScrollBar().isSliderDown():
            self._apply_show()

    def _reset_reading(self):
        if self._body is None:
            return
        from PySide6.QtGui import QTextCursor
        self._updating = True
        cursor = self._body.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._body.setTextCursor(cursor)
        scroll = self._body.verticalScrollBar()
        scroll.setSliderDown(False)
        scroll.setValue(scroll.maximum())
        self._follow_tail = True
        self._updating = False

    def _resume_tail(self):
        self._updating = True
        cursor = self._body.textCursor()
        cursor.clearSelection()
        self._body.setTextCursor(cursor)
        self._updating = False
        self._follow_tail = True
        self._apply_show()

    def _reading(self) -> bool:
        if self._body is None:
            return False
        try:
            if self._body.textCursor().hasSelection() or self._body.verticalScrollBar().isSliderDown():
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
        if self._mode != "result":
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
        if getattr(self, "_modal_depth", 0) or self._foreground_surfaces:
            # A non-activating always-on-top HUD must not cover a modal action.
            # Incoming phone changes are retained, but no overlay is re-shown.
            self.visible = False
            if self._widget is not None:
                self._widget.hide()
            return
        if self._widget is None:
            return
        if self._rendered_draft_key != self._draft_key or (not self.text and not self.assets):
            self._reset_reading()
            self._rendered_draft_key = self._draft_key
        self._refresh_thumbnails()
        unfinished = sum(a.get("status", "ready") != "ready" for a in self.assets)
        ready = len(self.assets) - unfinished
        status = (f"手机稿 · r{self.revision}" if self.phone_online else f"手机离线 · 电脑保留稿 r{self.revision}") if self.phone_primary else "手机输入中"
        if self.assets:
            status += f" · {ready}/{len(self.assets)} 张已收到" if unfinished else f" · {ready} 张图片已更新"
        self._status.setText(self._operation_message if self._mode != "receiving" else status)
        self._insert.setEnabled(not unfinished and self._mode != "busy")
        self._copy.setEnabled(self._mode != "busy")
        self._insert.setText("处理中…" if self._mode == "busy" else ("图片同步中" if unfinished else "插入并复制"))
        body = self.text if self.text else ("图片准备中，可继续在手机写说明" if unfinished else "")
        # 程序主动写字造成的滚动条变化，不能被误判成用户正在读前文。
        reading = not self._follow_tail or self._reading()
        if self._body.textCursor().hasSelection() or self._body.verticalScrollBar().isSliderDown():
            self._follow_tail = False
            self._latest.show()
            self._pause_or_resume_idle()
            return
        self._updating = True
        old_cursor = self._body.textCursor()
        position, anchor = old_cursor.position(), old_cursor.anchor()
        scroll = self._body.verticalScrollBar()
        scroll_pos = scroll.value()
        self._body.blockSignals(True)
        scroll.blockSignals(True)
        previous = self._body.toPlainText()
        if body != previous:
            if body.startswith(previous):
                from PySide6.QtGui import QTextCursor
                edit = QTextCursor(self._body.document())
                edit.movePosition(QTextCursor.End)
                edit.insertText(body[len(previous):])
            else:
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
        self._latest.setVisible(reading)
        self._place()
        self._widget.show()
        self._updating = False
        from PySide6.QtCore import QTimer
        # 第一次show后QTextDocument可能再计算一次边距；只在仍然追尾时校正。
        generation = getattr(self, "_render_generation", 0) + 1
        self._render_generation = generation
        def settle_tail():
            if (self._widget.isVisible() and self._render_generation == generation
                    and not reading and self._follow_tail):
                self._updating = True
                self._body.verticalScrollBar().setValue(self._body.verticalScrollBar().maximum())
                self._updating = False
        QTimer.singleShot(0, self._widget, settle_tail)
        if self._timer:
            if self._mode != "result":
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
        self._reset_reading()
        self.visible = False
        if self._timer is not None:
            self._timer.stop()
        if self._widget is not None:
            self._widget.hide()
        self._mode, self._operation_message = "receiving", ""
