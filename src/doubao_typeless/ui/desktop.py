"""Windows graphical client. Same V3App/bridge as the phone; not a static page."""
from __future__ import annotations

import io
import sys
import traceback
from pathlib import Path
from typing import Callable

from doubao_typeless.runtime import lan_ip
from doubao_typeless.storage.credentials import pairing_page_url
from doubao_typeless.storage.settings_store import load_settings, save_settings
from doubao_typeless.storage.vocab_store import load_vocab, save_vocab

PROVIDER_PRESETS = [
    ("自定义", "", ""),
    ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    ("智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
]
from doubao_typeless.ui.filelog import FileLogger
from doubao_typeless.ui.single_instance import listen_for_commands, request_quit, request_show
from doubao_typeless.ui.v3_startup import apply_v3_autostart

TOKENS = {
    "accent": "#167D71",
    "surface": "#F7F6F2",
    "card": "#FFFFFF",
    "ink": "#1D2826",
    "muted": "#63716D",
    "danger": "#B42318",
}

RESULT_LABELS = {
    "CONFIRMED": "已插入",
    "UNKNOWN": "上次结果未知",
    "PARTIAL": "只完成一部分",
    "NO_STEPS": "没有贴出",
    "CANCELLED": "已取消",
    "BUSY": "正忙",
}


def _result_label(code: object) -> str:
    if not code:
        return "未记录"
    return RESULT_LABELS.get(str(code), str(code))

STYLESHEET = f"""
QWidget {{ background: {TOKENS['surface']}; color: {TOKENS['ink']}; font-size: 13px; font-family: "Microsoft YaHei UI","Microsoft YaHei","Noto Sans CJK SC","Segoe UI"; }}
QTabWidget::pane {{ border: 0; }}
QTabBar::tab {{ background: transparent; border: 0; padding: 10px 16px; color: {TOKENS['muted']}; border-bottom: 2px solid transparent; }}
QTabBar::tab:hover {{ color: {TOKENS['ink']}; background: #E7EEEC; }}
QTabBar::tab:selected {{ color: {TOKENS['accent']}; font-weight: 600; border-bottom: 2px solid {TOKENS['accent']}; }}
QTabBar::tab:focus {{ outline: 2px solid {TOKENS['accent']}; }}
QLabel {{ background: transparent; }}
QToolButton {{ border:0; padding:6px 4px; border-radius:6px; color:{TOKENS['muted']}; background:transparent; }}
QToolButton:hover {{ background:#E7EEEC; }}
QToolButton:checked {{ color:{TOKENS['accent']}; }}
QScrollArea {{ border:0; }}
QFrame#card {{ background: {TOKENS['card']}; border-radius: 12px; }}
QPushButton {{ border: 0; border-radius: 9px; padding: 8px 12px; }}
QPushButton:hover {{ background: #D8E4E1; }}
QPushButton:pressed {{ background: #C5D6D2; }}
QPushButton:disabled {{ color: #9AA6A3; background: #EEF1F0; }}
QPushButton:focus {{ outline: 2px solid {TOKENS['accent']}; }}
QPushButton#primary {{ background: {TOKENS['accent']}; color: white; }}
QPushButton#primary:hover {{ background: #12655B; }}
QPushButton#primary:pressed {{ background: #0E524A; }}
QPushButton#primary:disabled {{ background: #8BB8B2; color: #F4F7F6; }}
QPushButton#ghost {{ background: #E7EEEC; color: {TOKENS['ink']}; }}
QPushButton#ghost:hover {{ background: #D5E0DD; }}
QPushButton#danger {{ background: #F4E4E1; color: {TOKENS['danger']}; }}
QPushButton#danger:hover {{ background: #EED3CE; }}
QComboBox {{ padding: 7px 10px; border: 1px solid #D5DDDA; border-radius: 8px; background:white; }}
QComboBox::drop-down {{ border:0; width:24px; }}
QLineEdit, QPlainTextEdit {{ background: white; border: 1px solid #D5DDDA; border-radius: 8px; padding: 6px; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {TOKENS['accent']}; }}
QLineEdit:disabled, QPlainTextEdit:disabled {{ background: #EEF1F0; color: #9AA6A3; }}
QListWidget::item:selected {{ background: #E3F2EF; color: {TOKENS['ink']}; }}
QListWidget::item:hover {{ background: #F0F5F3; }}
QLabel#muted {{ color: {TOKENS['muted']}; }}
QLabel#error {{ color: {TOKENS['danger']}; }}
"""


def _repo_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[3]


def qr_pixmap(url: str, size: int = 168):
    from PySide6.QtGui import QImage, QPixmap

    try:
        import qrcode
    except ImportError:
        return QPixmap()
    image = qrcode.make(url)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    qimg = QImage.fromData(buf.getvalue())
    return QPixmap.fromImage(qimg).scaled(size, size)


def apply_ui_font(qt=None) -> str:
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    qt = qt or QApplication.instance()
    if qt is None:
        return ""
    families = set(QFontDatabase.families())
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI"):
        if name in families:
            qt.setFont(QFont(name, 10))
            return name
    return ""


def app_icon():
    from PySide6.QtGui import QColor, QIcon, QPixmap

    candidates = [
        _repo_root() / "assets" / "icon.ico",
        Path(sys.executable).parent / "assets" / "icon.ico",
    ]
    for ico in candidates:
        if ico.is_file():
            return QIcon(str(ico))
    pm = QPixmap(32, 32)
    pm.fill(QColor(TOKENS["accent"]))
    return QIcon(pm)


class RecoveryDialog:
    def __init__(self, parent=None, *, confirm_image: bool = False):
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

        self.choice = "cancel"
        dlg = QDialog(parent)
        dlg.setWindowTitle("上次结果未知")
        dlg.setModal(True)
        dlg.resize(420, 180)
        layout = QVBoxLayout(dlg)
        message = QLabel("程序不能确认刚才的图片是否已加入。请查看目标输入框，再决定继续或重贴。"
                         if confirm_image else "上次插入结果不确定。不自动重贴，也不全选删除。")
        message.setWordWrap(True)
        layout.addWidget(message)
        if confirm_image:
            confirmed = QPushButton("我已看到刚才的图片，继续剩余内容")
            confirmed.setObjectName("primary")
            confirmed.clicked.connect(lambda: self._pick(dlg, "confirm_continue"))
            layout.addWidget(confirmed)
        row = QHBoxLayout()
        for label, mode, name in (
            ("完整重贴", "full", "primary"),
            ("只贴文字", "text_only", "ghost"),
            ("取消", "cancel", "danger"),
        ):
            btn = QPushButton(label)
            btn.setObjectName(name)
            btn.clicked.connect(lambda _=False, m=mode: self._pick(dlg, m))
            row.addWidget(btn)
        layout.addLayout(row)
        self._dlg = dlg

    def _pick(self, dlg, mode: str) -> None:
        self.choice = mode
        dlg.accept() if mode != "cancel" else dlg.reject()

    def exec(self) -> str:
        self._dlg.exec()
        return self.choice


class ReviewPanel:
    def __init__(self, app, parent=None):
        from PySide6.QtWidgets import (
            QHBoxLayout,
            QLabel,
            QPlainTextEdit,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        self.app = app
        self._editing = False
        w = QWidget(parent)
        w.setWindowTitle("当前图文")
        w.resize(420, 320)
        w.setStyleSheet(STYLESHEET)
        layout = QVBoxLayout(w)
        self.banner = QLabel("")
        self.banner.setObjectName("error")
        self.banner.setWordWrap(True)
        self.banner.hide()
        layout.addWidget(self.banner)
        self.images = QLabel("没有图片")
        self.images.setObjectName("muted")
        layout.addWidget(self.images)
        self.image_row = QHBoxLayout()
        layout.addLayout(self.image_row)
        self.editor = QPlainTextEdit()
        self.editor.textChanged.connect(self._mark_editing)
        layout.addWidget(self.editor, 1)
        row = QHBoxLayout()
        use_phone = QPushButton("采用手机版")
        use_phone.setObjectName("ghost")
        use_phone.clicked.connect(self.take_phone)
        keep = QPushButton("保留电脑稿")
        keep.setObjectName("ghost")
        keep.clicked.connect(self.keep_pc)
        terms_btn = QPushButton("检查术语")
        terms_btn.setObjectName("ghost")
        terms_btn.clicked.connect(self.check_terms)
        suggest = QPushButton("建议改写")
        suggest.setObjectName("ghost")
        suggest.clicked.connect(self.suggest_rewrite)
        apply_s = QPushButton("采用建议")
        apply_s.setObjectName("ghost")
        apply_s.clicked.connect(self.apply_rewrite)
        reject_s = QPushButton("不用建议")
        reject_s.setObjectName("ghost")
        reject_s.clicked.connect(self.reject_rewrite)
        copy = QPushButton("复制")
        copy.setObjectName("ghost")
        copy.clicked.connect(self.copy_only)
        insert = QPushButton("插入并复制")
        insert.setObjectName("primary")
        insert.clicked.connect(self.insert)
        context_row = QHBoxLayout()
        for button in (use_phone, keep, apply_s, reject_s):
            context_row.addWidget(button)
        context_row.addStretch(1)
        layout.addLayout(context_row)
        tools_row = QHBoxLayout()
        tools_row.addWidget(terms_btn)
        tools_row.addWidget(suggest)
        tools_row.addStretch(1)
        layout.addLayout(tools_row)
        row.addStretch(1)
        row.addWidget(copy)
        row.addWidget(insert)
        layout.addLayout(row)
        self.btn_use_phone = use_phone
        self.btn_keep = keep
        self.btn_apply = apply_s
        self.btn_reject = reject_s
        use_phone.hide()
        keep.hide()
        apply_s.hide()
        reject_s.hide()
        self.widget = w
        from PySide6.QtCore import QEvent, QObject

        class _HideRelease(QObject):
            def eventFilter(inner, _obj, ev):
                if ev.type() == QEvent.Hide:
                    self.app.review_editing = False
                    self._editing = False
                return False

        self._hide_filter = _HideRelease(w)
        w.installEventFilter(self._hide_filter)
        self.reload()

    def _mark_editing(self) -> None:
        self._editing = True
        self.app.review_editing = True
        self.app.update_pc_text(self.editor.toPlainText())

    def _sync_buttons(self) -> None:
        pending = bool(self.app.phone_pending)
        self.btn_use_phone.setVisible(pending)
        self.btn_keep.setVisible(pending)
        last = getattr(self.app, "_last_suggestion", None) or {}
        has = bool(last.get("suggested"))
        self.btn_apply.setVisible(has)
        self.btn_reject.setVisible(has)

    def reload(self) -> None:
        self._editing = False
        self.app.review_editing = False
        self.banner.hide()
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.app.review_text() or "")
        self.editor.blockSignals(False)
        self._refresh_images()
        self._sync_buttons()

    def note_phone_pending(self) -> None:
        if not self._editing:
            self.reload()
            return
        self.banner.setText("手机有更新；电脑修改仍保留。默认以手机为准，可复制电脑修改或采用手机版继续。")
        self.banner.show()
        self._sync_buttons()

    def take_phone(self) -> None:
        self.app.accept_phone_pending()
        self.reload()

    def keep_pc(self) -> None:
        self.app.keep_pc_edit()
        self.banner.hide()
        self._sync_buttons()

    def copy_only(self) -> None:
        self.app.update_pc_text(self.editor.toPlainText())
        self.app.review_editing = False
        self.app._save_draft()
        self.app.copy_text(self.editor.toPlainText())

    def _clear_image_row(self) -> None:
        while self.image_row.count():
            item = self.image_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_images(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QLabel, QPushButton

        previews = self.app.draft_image_previews()
        if not previews:
            self.images.setText("没有图片")
            self._clear_image_row()
            return
        missing = sum(1 for item in previews if not item["present"])
        self.images.setText(
            f"{len(previews)} 张图，顺序即投递顺序"
            + ("，有图还没传到电脑" if missing else "")
        )
        self._clear_image_row()
        for item in previews:
            thumb = QPushButton(f"{item['order']}")
            thumb.setFixedSize(72, 72)
            if item["present"] and item["data"]:
                pix = QPixmap()
                pix.loadFromData(item["data"])
                from PySide6.QtGui import QIcon
                thumb.setIcon(QIcon(pix))
                thumb.setIconSize(thumb.size() * 0.9)
                thumb.clicked.connect(lambda _=False, payload=item["data"]: self._enlarge(payload))
            else:
                thumb.setText(f"{item['order']}\n缺图")
            self.image_row.addWidget(thumb)
        self.image_row.addStretch(1)

    def _enlarge(self, payload: bytes) -> None:
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

        dlg = QDialog(self.widget)
        dlg.setWindowTitle("查看图片")
        box = QVBoxLayout(dlg)
        label = QLabel()
        pix = QPixmap()
        pix.loadFromData(payload)
        from PySide6.QtCore import Qt

        if not pix.isNull():
            label.setPixmap(pix.scaled(480, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            label.setPixmap(pix)
        box.addWidget(label)
        dlg.resize(500, 500)
        dlg.exec()

    def suggest_rewrite(self) -> None:
        import threading

        text = self.editor.toPlainText()
        self.app.update_pc_text(text)
        self.banner.setText("正在请求建议，仍可改字或插入")
        self.banner.show()

        def work() -> None:
            out = self.app.suggest_text(text)
            def apply() -> None:
                suggested = out.get("suggested") or ""
                if suggested and suggested != out.get("original"):
                    self.banner.setText(f"建议：{suggested}")
                else:
                    self.banner.setText(out.get("message") or "没有可用的改写建议")
                self.banner.show()
                self._sync_buttons()
            try:
                from PySide6.QtCore import QTimer

                QTimer.singleShot(0, self.widget, apply)
            except RuntimeError:
                pass  # 窗口已销毁，不能在工作线程操作 Qt 控件。

        threading.Thread(target=work, daemon=True).start()

    def apply_rewrite(self) -> None:
        self.app.update_pc_text(self.editor.toPlainText())
        if not self.app.apply_suggestion():
            self.banner.setText("建议已过期，请再点建议改写")
            self.banner.show()
            return
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.app.review_text())
        self.editor.blockSignals(False)
        self.banner.setText("已采用建议；继续编辑前可撤回这次改写。")
        self.banner.show()
        self._sync_buttons()

    def reject_rewrite(self) -> None:
        self.app.reject_suggestion()
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.app.review_text())
        self.editor.blockSignals(False)
        self.banner.setText("已取消本次建议；较新的编辑不会被覆盖。")
        self.banner.show()
        self._sync_buttons()

    def check_terms(self) -> None:
        from doubao_typeless.services.terms import hints
        from doubao_typeless.storage.vocab_store import load_vocab, parse_mappings

        text = self.editor.toPlainText()
        notes = [item["hint"] for item in hints(text)]
        vocab_hits = [src for src, _dst in parse_mappings(load_vocab(self.app.data_dir)) if src and src in text]
        if vocab_hits:
            notes.append("词库命中：" + "、".join(vocab_hits[:8]))
        self.banner.setText("；".join(notes) if notes else "当前稿没有命中术语或词库")
        self.banner.show()

    def insert(self) -> None:
        self.app.update_pc_text(self.editor.toPlainText())
        self.app.review_editing = False
        self.app._save_draft()
        self.widget.hide()
        self._editing = False
        self.app.request_review_insert()

    def show(self) -> None:
        self.app._remember_external_target()
        if not self._editing:
            self.reload()
        self.widget.show()
        self.widget.raise_()
        self.widget.activateWindow()


class ClientWindow:
    def __init__(self, app, *, on_hide: Callable[[], None] | None = None, on_quit: Callable[[], None] | None = None):
        from PySide6.QtCore import QTimer, Qt
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import (
            QCheckBox,
            QComboBox,
            QFormLayout,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QPlainTextEdit,
            QPushButton,
            QScrollArea,
            QTabWidget,
            QToolButton,
            QVBoxLayout,
            QWidget,
        )

        self.app = app
        self._on_hide = on_hide
        self._on_quit = on_quit
        self._closing_for_quit = False
        self._session_sig = None
        stored = load_settings(app.data_dir)

        class ShellWindow(QWidget):
            def closeEvent(inner_self, event):
                self._close_event(event)

        w = ShellWindow()
        w.setWindowTitle("DoubaoTypeless V3 · 体验版")
        w.resize(560, 600)
        w.setStyleSheet(STYLESHEET)
        root = QVBoxLayout(w)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        connect = QWidget()
        cl = QVBoxLayout(connect)
        cl.addWidget(QLabel("让手机成为更顺手的输入工具。"))
        from doubao_typeless.services.v3_update import preview_version_label

        version = QLabel(preview_version_label())
        version.setObjectName("muted")
        cl.addWidget(version)
        card = QFrame()
        card.setObjectName("card")
        from PySide6.QtWidgets import QSizePolicy
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card_l = QHBoxLayout(card)
        self.qr = QLabel()
        self.qr.setFixedSize(168, 168)
        card_l.addWidget(self.qr)
        info = QVBoxLayout()
        self.url_label = QLabel("")
        self.url_label.setWordWrap(True)
        info.addWidget(self.url_label)
        self.code_label = QLabel("")
        info.addWidget(self.code_label)
        hint = QLabel("用手机浏览器打开并连接。手机与电脑须在同一局域网。二维码不含截图或插入权限。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        info.addWidget(hint)
        btns = QHBoxLayout()
        copy = QPushButton("复制地址")
        copy.setObjectName("ghost")
        copy.clicked.connect(self.copy_url)
        help_btn = QPushButton("连接帮助")
        help_btn.setObjectName("ghost")
        help_btn.clicked.connect(self.show_help)
        rotate = QPushButton("重新配对")
        rotate.setObjectName("ghost")
        rotate.clicked.connect(self.rotate_code)
        btns.addWidget(copy)
        btns.addWidget(help_btn)
        btns.addWidget(rotate)
        info.addLayout(btns)
        info.addStretch(1)
        card_l.addLayout(info, 1)
        cl.addWidget(card)
        self.device_box = QLabel("还没有手机连上。扫码后在这里批准插入和截图。")
        self.device_box.setWordWrap(True)
        cl.addWidget(self.device_box)
        self.device_name = QLineEdit()
        self.device_name.setPlaceholderText("给已连接的手机起个名字")
        self.device_name.hide()
        cl.addWidget(self.device_name)
        self.grant_row = QVBoxLayout()
        cl.addLayout(self.grant_row)
        self.remember_box = QCheckBox("记住这台设备 30 天（需明确勾选，不是默认）")
        self.remember_box.clicked.connect(self._toggle_remember)
        cl.addWidget(self.remember_box)
        self.practice_toggle = QToolButton()
        self.practice_toggle.setText("试一段文字（可选）")
        self.practice_toggle.setCheckable(True)
        self.practice_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.practice_toggle.setArrowType(Qt.RightArrow)
        cl.addWidget(self.practice_toggle)
        self.practice = QPlainTextEdit()
        self.practice.setPlaceholderText("可选：输入测试文字，再到「当前图文」预览。实际插入请选中外部输入框。")
        self.practice.textChanged.connect(lambda: self.app.update_pc_text(self.practice.toPlainText()))
        self.practice.setFixedHeight(88)
        cl.addWidget(self.practice)
        self.practice.hide()
        self.practice_toggle.toggled.connect(lambda opened: (
            self.practice.setVisible(opened),
            self.practice_toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)))
        cl.addStretch(1)
        foot = QHBoxLayout()
        start = QPushButton("开始使用，收起窗口")
        start.setObjectName("primary")
        start.clicked.connect(self.hide_to_tray)
        diag = QPushButton("帮助与诊断")
        diag.setObjectName("ghost")
        diag.clicked.connect(self.show_help)
        foot.addWidget(start)
        foot.addStretch(1)
        foot.addWidget(diag)
        cl.addLayout(foot)
        connect_scroll = QScrollArea()
        connect_scroll.setWidgetResizable(True)
        connect_scroll.setFrameShape(QFrame.NoFrame)
        connect_scroll.setWidget(connect)
        tabs.addTab(connect_scroll, "连接手机")

        settings = QWidget()
        sl = QFormLayout(settings)
        sl.setVerticalSpacing(12)
        sl.addRow(QLabel("输入与启动"))
        self.hotkey_insert = QLineEdit(str(stored.get("hotkey_insert") or "<alt>+i"))
        self.hotkey_recall = QLineEdit(str(stored.get("hotkey_recall") or "<alt>+<shift>+i"))
        sl.addRow("插入并复制", self.hotkey_insert)
        sl.addRow("召回上次", self.hotkey_recall)
        self.hotkey_expand = QLineEdit(str(stored.get("hotkey_expand") or "<alt>+<shift>+e"))
        self.hotkey_capture = QLineEdit(str(stored.get("hotkey_capture") or "<alt>+<shift>+s"))
        sl.addRow("展开当前图文", self.hotkey_expand)
        sl.addRow("截图给手机", self.hotkey_capture)
        self.autostart = QCheckBox("登录 Windows 时启动（到托盘）")
        self.autostart.setChecked(bool(stored.get("autostart")))
        self.start_min = QCheckBox("启动后先到托盘")
        self.start_min.setChecked(bool(stored.get("start_minimized")))
        sl.addRow(self.autostart)
        sl.addRow(self.start_min)
        ai_intro = QLabel("AI 文字辅助（可选）\n仅在「当前图文」主动检查时调用。不负责语音识别，不影响普通输入和画图。")
        ai_intro.setWordWrap(True)
        sl.addRow(ai_intro)
        self.byok_provider = QComboBox()
        for name, _url, _model in PROVIDER_PRESETS:
            self.byok_provider.addItem(name)
        self.byok_provider.currentIndexChanged.connect(self._apply_provider)
        sl.addRow("服务商", self.byok_provider)
        self.byok_endpoint = QLineEdit(str(stored.get("byok_endpoint") or ""))
        self.byok_key = QLineEdit(str(stored.get("byok_api_key") or ""))
        self.byok_key.setEchoMode(QLineEdit.Password)
        self.byok_model = QLineEdit(str(stored.get("byok_model") or ""))
        sl.addRow("Base URL", self.byok_endpoint)
        sl.addRow("API Key", self.byok_key)
        sl.addRow("模型 ID", self.byok_model)
        from doubao_typeless.services.byok import url_join_note

        self.byok_url_note = QLabel(url_join_note(self.byok_endpoint.text()))
        self.byok_url_note.setObjectName("muted")
        self.byok_url_note.setWordWrap(True)
        self.byok_endpoint.textChanged.connect(lambda t: self.byok_url_note.setText(url_join_note(t)))
        sl.addRow(self.byok_url_note)
        from PySide6.QtWidgets import QGroupBox

        advanced_toggle = QToolButton()
        advanced_toggle.setText("高级模型参数")
        advanced_toggle.setCheckable(True)
        advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        advanced = QWidget()
        adv = QFormLayout(advanced)
        self.byok_prompt = QPlainTextEdit()
        self.byok_prompt.setPlainText(str(stored.get("byok_prompt") or ""))
        self.byok_prompt.setFixedHeight(64)
        self.byok_temperature = QLineEdit(str(stored.get("byok_temperature") or ""))
        self.byok_timeout = QLineEdit(str(stored.get("byok_timeout") or ""))
        adv.addRow("附加说明", self.byok_prompt)
        adv.addRow("温度", self.byok_temperature)
        adv.addRow("超时秒", self.byok_timeout)
        sl.addRow(advanced_toggle)
        sl.addRow(advanced)
        opened = bool(stored.get("byok_prompt") or stored.get("byok_temperature") or stored.get("byok_timeout"))
        advanced_toggle.setChecked(opened)
        advanced_toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
        advanced.setVisible(opened)
        advanced_toggle.toggled.connect(lambda yes: (
            advanced.setVisible(yes), advanced_toggle.setArrowType(Qt.DownArrow if yes else Qt.RightArrow)))
        self.byok_advanced = advanced
        self.byok_status = QLabel("")
        self.byok_status.setObjectName("muted")
        self.byok_status.setWordWrap(True)
        sl.addRow(self.byok_status)
        sl.addRow(QLabel("词库（仅本预览目录，一行 错词 -> 正确）"))
        self.vocab = QPlainTextEdit()
        self.vocab.setPlainText(load_vocab(app.data_dir))
        self.vocab.setFixedHeight(120)
        sl.addRow(self.vocab)
        srow = QHBoxLayout()
        probe = QPushButton("测试连接")
        probe.setObjectName("ghost")
        probe.clicked.connect(self.probe_byok)
        export = QPushButton("导出诊断")
        export.setObjectName("ghost")
        export.clicked.connect(self.export_diagnostics)
        import_vocab = QPushButton("导入日用词库")
        import_vocab.setObjectName("ghost")
        import_vocab.clicked.connect(self.import_daily_vocab)
        update = QPushButton("检查更新")
        update.setObjectName("ghost")
        update.clicked.connect(self.check_update)
        save = QPushButton("保存设置")
        save.setObjectName("primary")
        save.clicked.connect(self.save_settings)
        model_actions = QHBoxLayout()
        model_actions.addWidget(probe)
        model_actions.addWidget(import_vocab)
        model_actions.addStretch(1)
        sl.addRow(model_actions)
        srow.addWidget(export)
        srow.addWidget(update)
        srow.addStretch(1)
        srow.addWidget(save)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.NoFrame)
        settings_scroll.setWidget(settings)
        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setContentsMargins(0,0,0,0)
        settings_layout.addWidget(settings_scroll, 1)
        settings_layout.addLayout(srow)
        tabs.addTab(settings_page, "常用设置")

        recent = QWidget()
        rl = QVBoxLayout(recent)
        self.recent_list = QListWidget()
        rl.addWidget(self.recent_list, 1)
        rrow = QHBoxLayout()
        restore = QPushButton("恢复为当前新稿")
        restore.setObjectName("ghost")
        restore.clicked.connect(self.restore_as_draft)
        replay = QPushButton("重投上次快照")
        replay.setObjectName("ghost")
        replay.clicked.connect(self.replay_snapshot)
        rrow.addWidget(restore)
        rrow.addWidget(replay)
        rl.addLayout(rrow)
        note = QLabel("恢复为当前新稿会复制内容，不覆盖手机正在写的稿。重投使用已冻结快照。")
        note.setObjectName("muted")
        note.setWordWrap(True)
        rl.addWidget(note)
        tabs.addTab(recent, "最近内容")

        self.tabs = tabs
        self.widget = w
        self._clipboard = QGuiApplication.clipboard()
        self._hist_sig = None
        self._pairing_url = ""
        self.timer = QTimer(w)
        self.timer.timeout.connect(self._tick_countdown)
        self.timer.start(1000)
        self.refresh()

    def _apply_provider(self, index: int) -> None:
        if index <= 0 or index >= len(PROVIDER_PRESETS):
            return
        _name, url, model = PROVIDER_PRESETS[index]
        if url:
            self.byok_endpoint.setText(url)
        if model:
            self.byok_model.setText(model)

    def phone_url(self) -> str:
        return f"http://{lan_ip()}:{self.app.port}/"

    def pairing_url(self) -> str:
        code = self.app.auth.current_pairing_challenge() or self.app.auth.new_pairing_challenge()
        return pairing_page_url(self.phone_url(), code)

    def copy_url(self) -> None:
        self._clipboard.setText(self.pairing_url())

    def rotate_code(self) -> None:
        self.app.auth.rotate_pairing_challenge()
        self.refresh()

    def show_help(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from doubao_typeless.services.v3_update import preview_version_label

        log = self.app.data_dir / "logs" / "v3.log"
        QMessageBox.information(
            self.widget,
            "帮助与诊断",
            f"{preview_version_label()}\n\n"
            "1. 手机浏览器扫码或打开窗口里的地址。\n"
            "2. 电脑批准插入后，点外部目标，再按「插入并复制」或 Alt+I。\n"
            "3. 不要改 JSON、不要设环境变量、不必打开 pc.html、不必读 pair.txt。\n"
            "4. 检查更新只打开公开下载页，不会覆盖日用安装。\n"
            f"日志：{log}",
        )

    def check_update(self) -> None:
        import webbrowser

        from PySide6.QtWidgets import QMessageBox

        from doubao_typeless.services.v3_update import DOWNLOAD_PAGE, check_preview_update

        info = check_preview_update()
        QMessageBox.information(self.widget, "检查更新", info["message"])
        webbrowser.open(DOWNLOAD_PAGE)

    def import_daily_vocab(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        from doubao_typeless.storage.vocab_store import daily_vocab_candidates, import_vocab_preview, inspect_vocab_file

        source = next((path for path in daily_vocab_candidates() if path.is_file()), None)
        if source is None:
            picked, _ok = QFileDialog.getOpenFileName(self.widget, "选择只读词库", "", "Text (*.txt);;All (*)")
            if not picked:
                return
            source = Path(picked)
        info = inspect_vocab_file(source)
        reply = QMessageBox.question(
            self.widget,
            "导入日用词库",
            f"从 {info['path']} 复制 {info['mappings']} 条到本预览词库。\n不会改源文件，也不会写日用 config.json。",
        )
        if reply != QMessageBox.Yes:
            return
        result = import_vocab_preview(self.app.data_dir, source)
        self.vocab.setPlainText(load_vocab(self.app.data_dir))
        self.byok_status.setText(f"已复制 {result['imported']} 条新词到预览词库")

    def hide_to_tray(self) -> None:
        stored = load_settings(self.app.data_dir)
        if not stored.get("tray_explained") and self._on_hide:
            self._on_hide()
            save_settings(self.app.data_dir, {"tray_explained": True})
        self.widget.hide()
        if getattr(self, "timer", None):
            self.timer.stop()
        if self._on_hide:
            self._on_hide()

    def _close_event(self, event) -> None:
        if self._closing_for_quit:
            event.accept()
            return
        event.ignore()
        self.hide_to_tray()

    def _clear_grant_row(self) -> None:
        from PySide6.QtWidgets import QLayoutItem

        while self.grant_row.count():
            item: QLayoutItem = self.grant_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _pair_caption(self) -> str:
        short = self.app.auth.current_short_code() or ""
        remain = int(self.app.auth.pairing_remaining_s())
        return f"扫码即连。备用短码 {short}  （{remain}s）"

    def _tick_countdown(self) -> None:
        if not self.widget.isVisible() or self.qr.isHidden():
            return
        self.code_label.setText(self._pair_caption())

    def _toggle_remember(self) -> None:
        if not self.remember_box.isChecked():
            count = self.app.forget_connected()
            self.device_box.setText(f"已忘记 {count} 台设备，下次需要重新配对。")
            return
        count = self.app.remember_connected()
        self.device_box.setText(
            (self.device_box.text() + "\n" if self.device_box.text() else "")
            + (f"已记住 {count} 台设备，30 天内可直接续接。" if count else "还没有已连接的手机可记住。")
        )

    def refresh(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidgetItem, QPushButton, QWidget, QHBoxLayout

        url = self.pairing_url()
        if url != getattr(self, "_pairing_url", ""):
            self._pairing_url = url
            self.url_label.setText(self.phone_url())
            self.url_label.setToolTip("扫码已包含一次性配对信息，无需抄写长码")
            pix = qr_pixmap(url)
            if not pix.isNull():
                self.qr.setPixmap(pix)
        self.code_label.setText(self._pair_caption())
        sessions = self.app.auth.public_sessions()
        sig = tuple((s["session_id"], s["allow_insert"], s["allow_capture"]) for s in sessions)
        if sig != self._session_sig:
            self._session_sig = sig
            self._clear_grant_row()
            if not sessions:
                self.qr.show()
                self.practice_toggle.show()
                self.practice.setVisible(self.practice_toggle.isChecked())
                self.device_box.setText("还没有手机连上。扫码后在这里批准插入和截图。")
                self.device_name.hide()
            else:
                self.qr.hide()
                self.practice.hide()
                self.practice_toggle.hide()
                from doubao_typeless.storage.credentials import device_label

                nicks = load_settings(self.app.data_dir).get("device_nicknames") or {}
                lines = []
                for index, item in enumerate(sessions, start=1):
                    name = device_label(item["device_id"], nicks, index)
                    lines.append(
                        f"{name}  插入={'开' if item['allow_insert'] else '关'}  "
                        f"截图={'开' if item['allow_capture'] else '关'}"
                    )
                    sid = item["session_id"]
                    allow_i = QPushButton("允许插入" if not item["allow_insert"] else "关闭插入")
                    allow_i.setObjectName("primary" if not item["allow_insert"] else "ghost")
                    allow_i.clicked.connect(lambda _=False, s=sid, v=not item["allow_insert"]: self.set_insert(s, v))
                    allow_c = QPushButton("允许截图" if not item["allow_capture"] else "关闭截图")
                    allow_c.setObjectName("ghost")
                    allow_c.clicked.connect(lambda _=False, s=sid, v=not item["allow_capture"]: self.set_capture(s, v))
                    revoke = QPushButton("撤销设备")
                    revoke.setObjectName("danger")
                    revoke.clicked.connect(lambda _=False, s=sid: self.revoke(s))
                    row_widget = QWidget()
                    row = QHBoxLayout(row_widget)
                    row.setContentsMargins(0,0,0,0)
                    row.addWidget(allow_i)
                    row.addWidget(allow_c)
                    row.addWidget(revoke)
                    self.grant_row.addWidget(row_widget)
                self.device_name.show()
                if not self.device_name.hasFocus():
                    self.device_name.setText(device_label(sessions[0]["device_id"], nicks, 1))
                self.device_box.setText("\n".join(lines))
                if any(item.get("remembered") for item in sessions):
                    self.remember_box.blockSignals(True)
                    self.remember_box.setChecked(True)
                    self.remember_box.blockSignals(False)
        hist_sig = tuple(
            (item["bundle"].get("bundle_id"), item.get("attempt_result"))
            for item in self.app.history.items[-20:]
        )
        if hist_sig != self._hist_sig:
            selected = None
            current = self.recent_list.currentItem()
            if current is not None:
                selected = (current.data(Qt.UserRole) or {}).get("bundle_id")
            self._hist_sig = hist_sig
            self.recent_list.clear()
            restore_row = None
            for item in reversed(self.app.history.items[-20:]):
                bundle = item["bundle"]
                preview = (bundle.get("text") or "").replace("\n", " ")[:48] or "（无文字）"
                result = _result_label(item.get("attempt_result"))
                row = QListWidgetItem(f"{result}  {len(bundle.get('assets') or [])}图  {preview}")
                row.setData(Qt.UserRole, bundle)
                if selected and bundle.get("bundle_id") == selected:
                    restore_row = row
                self.recent_list.addItem(row)
            if restore_row is not None:
                self.recent_list.setCurrentItem(restore_row)

    def set_insert(self, session_id: str, value: bool) -> None:
        self.app.auth.set_grants(session_id, allow_insert=value)
        self.refresh()

    def set_capture(self, session_id: str, value: bool) -> None:
        self.app.auth.set_grants(session_id, allow_capture=value)
        self.refresh()

    def revoke(self, session_id: str) -> None:
        loop = getattr(self.app, "_loop", None)
        if loop is not None:
            import asyncio

            asyncio.run_coroutine_threadsafe(self.app.bridge.revoke_session(session_id), loop).result(3)
        else:
            self.app.auth.revoke(session_id)
        self.refresh()

    def save_settings(self) -> None:
        nicks = dict(load_settings(self.app.data_dir).get("device_nicknames") or {})
        sessions = self.app.auth.public_sessions()
        if sessions and self.device_name.text().strip():
            nicks[sessions[0]["device_id"]] = self.device_name.text().strip()
        payload = {
            "hotkey_insert": self.hotkey_insert.text().strip() or "<alt>+i",
            "hotkey_recall": self.hotkey_recall.text().strip() or "<alt>+<shift>+i",
            "hotkey_expand": self.hotkey_expand.text().strip() or "<alt>+<shift>+e",
            "hotkey_capture": self.hotkey_capture.text().strip() or "<alt>+<shift>+s",
            "autostart": self.autostart.isChecked(),
            "start_minimized": self.start_min.isChecked(),
            "byok_endpoint": self.byok_endpoint.text().strip(),
            "byok_api_key": self.byok_key.text().strip(),
            "byok_model": self.byok_model.text().strip(),
            "byok_prompt": self.byok_prompt.toPlainText().strip(),
            "byok_temperature": self.byok_temperature.text().strip(),
            "byok_timeout": self.byok_timeout.text().strip(),
            "device_nicknames": nicks,
        }
        save_settings(self.app.data_dir, payload)
        save_vocab(self.app.data_dir, self.vocab.toPlainText())
        stored = load_settings(self.app.data_dir)
        self.app.byok.endpoint = stored["byok_endpoint"]
        self.app.byok.api_key = stored["byok_api_key"]
        self.app.byok.model = stored["byok_model"]
        self.app.byok.extra_prompt = stored["byok_prompt"]
        from doubao_typeless.app import _optional_float

        self.app.byok.temperature = _optional_float(stored["byok_temperature"])
        self.app.byok.timeout = _optional_float(stored.get("byok_timeout")) or 8.0
        failures = self.app.apply_hotkeys(
            stored["hotkey_insert"],
            stored["hotkey_recall"],
            expand=stored["hotkey_expand"],
            capture=stored["hotkey_capture"],
        )
        ok, err = apply_v3_autostart(bool(stored["autostart"]))
        if stored["autostart"] and not ok:
            self.byok_status.setText(f"设置已保存。开机自启未写入：{err}")
            self.byok_status.setObjectName("error")
        elif failures:
            self.byok_status.setText("已保存。热键注册失败，请改键。不会把语法合法当成成功。")
            self.byok_status.setObjectName("error")
        else:
            self.byok_status.setText("已保存。热键已按新组合重新注册。")
            self.byok_status.setObjectName("muted")

    def probe_byok(self) -> None:
        from doubao_typeless.services.byok import ByokService, ERROR_LABELS

        endpoint = self.byok_endpoint.text().strip()
        key = self.byok_key.text().strip()
        model = self.byok_model.text().strip()
        if not endpoint or not key:
            self.byok_status.setText(ERROR_LABELS["no_key"])
            return
        from doubao_typeless.storage.settings_store import endpoint_authority, load_settings

        stored = load_settings(self.app.data_dir)
        if endpoint_authority(stored.get("byok_endpoint") or "") != endpoint_authority(endpoint):
            if key == (stored.get("byok_api_key") or ""):
                self.byok_status.setText("换了服务地址，请重新填写并批准密钥后再测试")
                return
        from doubao_typeless.app import _httpx_json_post, _optional_float
        import threading

        timeout = _optional_float(self.byok_timeout.text()) or 8.0
        svc = ByokService(endpoint=endpoint, api_key=key, model=model, timeout=timeout, post=_httpx_json_post)
        self.byok_status.setText("正在测试连接…")
        host = self.widget

        def work() -> None:
            out = svc.polish("ping", draft_id="probe", revision=1, current_draft_id="probe", current_revision=1)
            used = out.get("model") or model
            def apply() -> None:
                self.byok_status.setText(f"{out.get('message') or out.get('status') or ''}  model={used}")
            try:
                from PySide6.QtCore import QTimer

                QTimer.singleShot(0, host, apply)
            except RuntimeError:
                pass  # 窗口已销毁，不能在工作线程操作 Qt 控件。

        threading.Thread(target=work, daemon=True).start()

    def _selected_bundle(self):
        from PySide6.QtCore import Qt

        item = self.recent_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def restore_as_draft(self) -> None:
        bundle = self._selected_bundle()
        if bundle is None:
            return
        status = self.app.restore_history(bundle)
        if status != "ask":
            return
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox(self.widget)
        box.setWindowTitle("当前稿还在")
        box.setText("恢复上次会替换当前稿。当前稿不会自动丢掉，除非你确认替换。")
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        if box.exec() != QMessageBox.Ok:
            return
        self.app.restore_history(bundle, replace=True)

    def replay_snapshot(self) -> None:
        bundle = self._selected_bundle()
        if bundle is None:
            return
        self.app.bridge.last_bundle = self.app.history.replay_bundle(bundle)
        self.app._commands.submit(self.app.insert_last)

    def export_diagnostics(self) -> None:
        from doubao_typeless.services.v3_diagnostics import write_snapshot

        path = write_snapshot(self.app)
        self.byok_status.setText(f"诊断已写出 {path.name}，不含密钥和正文")

    def show_window(self) -> None:
        self.widget.show()
        self.widget.raise_()
        self.widget.activateWindow()
        if getattr(self, "timer", None):
            self.timer.start(1000)
        self.refresh()


class DesktopShell:
    def __init__(self, app):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

        qt = QApplication.instance()
        qt.setQuitOnLastWindowClosed(False)
        qt.setWindowIcon(app_icon())
        self.app = app
        self.client = ClientWindow(app, on_hide=self._explained_tray)
        self.review = ReviewPanel(app)
        self.tray = QSystemTrayIcon(app_icon())
        menu = QMenu()
        menu.addAction("打开客户端", self.client.show_window)
        menu.addAction("当前图文", self.review.show)
        menu.addAction("召回上次", app.request_recall)
        menu.addAction("截图给手机", app.capture_region)
        self._pause_action = menu.addAction("暂停连接", self.toggle_pause)
        menu.addSeparator()
        menu.addAction("退出", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("DoubaoTypeless 预览")
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self._wake = listen_for_commands(self._on_ipc)
        self.app.ui_hook = self._from_service

    def _explained_tray(self) -> None:
        if not load_settings(self.app.data_dir).get("tray_explained"):
            self.tray.showMessage("DoubaoTypeless 预览", "已在托盘运行。点图标可再打开窗口。")
            save_settings(self.app.data_dir, {"tray_explained": True})

    def _on_ipc(self, command: str) -> None:
        from PySide6.QtCore import QTimer

        host = self.client.widget
        if command == "show":
            QTimer.singleShot(0, host, self.client.show_window)
        elif command == "quit":
            QTimer.singleShot(0, host, self.quit)

    def _tray_activated(self, reason) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon

        if reason == QSystemTrayIcon.Trigger:
            self.client.show_window()

    def toggle_pause(self) -> None:
        self.app.bridge.paused = not self.app.bridge.paused
        self._pause_action.setText("恢复连接" if self.app.bridge.paused else "暂停连接")

    def _from_service(self, event: str, **_kw) -> None:
        from PySide6.QtCore import QTimer

        host = self.client.widget
        if event == "sync_wait":
            pass  # 统一HUD状态机已处理，不能只改一行文字却忘记停空闲计时。
        elif event == "restore_on_phone":
            QTimer.singleShot(0, host, lambda: self.tray.showMessage("恢复图文", "已发到手机，请在手机确认；当前内容没有被覆盖"))
        elif event == "delivery_failed":
            code = str(_kw.get("error_code") or "")
            from doubao_typeless.ui.insert_status import error_message
            text = error_message(_kw)
            def show_error():
                self.client.byok_status.setText(text)
                if self.review.widget.isVisible():
                    self.review.banner.setText(text)
                    self.review.banner.show()
            QTimer.singleShot(0, host, show_error)
        elif event == "capture_region":
            QTimer.singleShot(0, host, self.app.capture_region)
        elif event == "recovery_ask":
            QTimer.singleShot(0, host, self._ask_recovery)
        elif event == "phone_pending":
            QTimer.singleShot(0, host, self.review.note_phone_pending)
        elif event == "activity":
            QTimer.singleShot(0, host, self.client.refresh)
            def refresh_visible_review():
                if self.review.widget.isVisible() and not self.review._editing:
                    self.review.reload()
            QTimer.singleShot(0, self.review.widget, refresh_visible_review)
        elif event == "expand":
            QTimer.singleShot(0, host, self.review.show)
        elif event in {"hide_after_insert", "new_draft"}:
            QTimer.singleShot(0, self.review.widget, self.review.widget.hide)

    def _ask_recovery(self) -> None:
        mode = RecoveryDialog(self.client.widget, confirm_image=self.app.can_confirm_image()).exec()
        if mode != "cancel":
            self.app.request_recovery(mode)

    def quit(self) -> None:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        import asyncio

        if getattr(self, "_quit_pending", False):
            return
        loop = getattr(self.app, "_loop", None)
        if loop is None:
            QApplication.instance().quit()
            return
        self._quit_pending = True
        future = asyncio.run_coroutine_threadsafe(self.app.stop(), loop)
        self.tray.showMessage("DoubaoTypeless", "正在结束当前操作，草稿已保留")

        def check() -> None:
            if not future.done():
                QTimer.singleShot(75, self.client.widget, check)
                return
            self._quit_pending = False
            try:
                stopped = future.result()
            except Exception:
                stopped = False
            if stopped is False:
                self.tray.showMessage("暂未退出", "目标程序尚未返回，未强制终止。请稍后再点退出。")
                return
            self.client._closing_for_quit = True
            self.tray.hide()
            QApplication.instance().quit()
        QTimer.singleShot(0, self.client.widget, check)


def _show_startup_error(exc: BaseException) -> None:
    text = f"{exc}\n\n可在帮助与诊断中查看日志。程序没有在无界面状态下继续运行。"
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        qt = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, "无法启动 DoubaoTypeless", text)
        if qt is not None:
            pass
    except Exception:
        traceback.print_exc()
        print(text, file=sys.stderr)


def run_desktop(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    minimized = "--minimized" in argv
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError as exc:
        print("需要 PySide6 才能打开图形客户端", flush=True)
        raise SystemExit(1) from exc

    qt = QApplication.instance() or QApplication(argv)
    qt.setQuitOnLastWindowClosed(False)
    apply_ui_font(qt)
    if "--quit" in argv:
        return 0 if request_quit() else 1
    from doubao_typeless.ui.single_instance import identify_running
    from doubao_typeless.build_info import build_info
    active = identify_running()
    if active:
        expected = build_info()["source_sha"]
        if active.get("unknown") or active.get("source_sha") != expected:
            QMessageBox.warning(None, "已有另一版本正在运行",
                "为避免重复快捷键和打开错版本，请先从旧版托盘正常退出，再打开这份新版本。\n"
                "程序不会结束旧进程，也不会覆盖其数据。")
            return 1
        if request_show():
            return 0

    from doubao_typeless.app import V3App, set_log
    from doubao_typeless.runtime import v3_data_dir
    from doubao_typeless.runtime_lock import InstanceLock

    data_dir = v3_data_dir()
    lock = InstanceLock(data_dir / "instance.lock")
    if not lock.acquire():
        if request_show():
            return 0
        QMessageBox.warning(
            None,
            "已经在运行",
            "另一个预览实例已在运行，但没能唤起窗口。请从托盘打开，或结束后再试。不会强杀已有进程。",
        )
        return 1

    logger = FileLogger(data_dir / "logs" / "v3.log", also_print=True)
    set_log(logger)
    try:
        app = V3App(data_dir=data_dir, instance_lock=lock)
        app.hud.start()
        loop = app.start_background(start_hud=False)
        app._loop = loop
        try:
            from doubao_typeless.platform.windows.hotkeys import start_hotkeys

            stored = load_settings(app.data_dir)
            start = start_hotkeys(
                on_insert=app.request_insert,
                on_recall=app.request_recall,
                on_expand=lambda: app._notify_ui("expand"),
                on_region=lambda: app._notify_ui("capture_region"),
                insert_combo=str(stored.get("hotkey_insert") or "<alt>+i"),
                recall_combo=str(stored.get("hotkey_recall") or "<alt>+<shift>+i"),
                expand_combo=str(stored.get("hotkey_expand") or "<alt>+<shift>+e"),
                capture_combo=str(stored.get("hotkey_capture") or "<alt>+<shift>+s"),
            )
            app._hotkeys = start
            if start.get("failures"):
                logger(f"[v3] 热键注册失败: {start['failures']}")
        except Exception as exc:
            logger(f"[v3] 热键未启动: {exc}")
        shell = DesktopShell(app)
        stored = load_settings(app.data_dir)
        if minimized or stored.get("start_minimized"):
            shell.tray.show()
        else:
            shell.client.show_window()
        return qt.exec()
    except Exception as exc:
        logger(f"[v3] 启动失败: {exc}")
        _show_startup_error(exc)
        try:
            lock.release()
        except Exception:
            pass
        return 1
