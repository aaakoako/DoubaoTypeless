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

STYLESHEET = f"""
QWidget {{ background: {TOKENS['surface']}; color: {TOKENS['ink']}; font-size: 13px; font-family: "Microsoft YaHei UI","Microsoft YaHei","Segoe UI"; }}
QTabWidget::pane {{ border: 0; }}
QTabBar::tab {{ padding: 8px 16px; }}
QTabBar::tab:selected {{ color: {TOKENS['accent']}; font-weight: 600; }}
QFrame#card {{ background: {TOKENS['card']}; border-radius: 12px; }}
QPushButton {{ border: 0; border-radius: 9px; padding: 8px 12px; }}
QPushButton#primary {{ background: {TOKENS['accent']}; color: white; }}
QPushButton#ghost {{ background: #E7EEEC; color: {TOKENS['ink']}; }}
QPushButton#danger {{ background: #F4E4E1; color: {TOKENS['danger']}; }}
QLineEdit, QPlainTextEdit {{ background: white; border: 1px solid #D5DDDA; border-radius: 8px; padding: 6px; }}
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
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"):
        if name in families:
            qt.setFont(QFont(name, 10))
            return name
    return ""


def app_icon():
    from PySide6.QtGui import QColor, QIcon, QPixmap

    ico = _repo_root() / "assets" / "icon.ico"
    if ico.is_file():
        return QIcon(str(ico))
    pm = QPixmap(32, 32)
    pm.fill(QColor(TOKENS["accent"]))
    return QIcon(pm)


class RecoveryDialog:
    def __init__(self, parent=None):
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

        self.choice = "cancel"
        dlg = QDialog(parent)
        dlg.setWindowTitle("上次结果未知")
        dlg.setModal(True)
        dlg.resize(420, 180)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("上次插入结果不确定。不自动重贴，也不全选删除。"))
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
        self.banner.hide()
        layout.addWidget(self.banner)
        self.images = QLabel("没有图片")
        self.images.setObjectName("muted")
        layout.addWidget(self.images)
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
        copy = QPushButton("复制")
        copy.setObjectName("ghost")
        copy.clicked.connect(self.copy_only)
        insert = QPushButton("插入并复制")
        insert.setObjectName("primary")
        insert.clicked.connect(self.insert)
        row.addWidget(use_phone)
        row.addWidget(keep)
        row.addStretch(1)
        row.addWidget(copy)
        row.addWidget(insert)
        layout.addLayout(row)
        self.widget = w
        self.reload()

    def _mark_editing(self) -> None:
        self._editing = True
        self.app.review_editing = True

    def reload(self) -> None:
        self._editing = False
        self.app.review_editing = False
        self.banner.hide()
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.app.draft.text or "")
        self.editor.blockSignals(False)
        count = len(self.app.draft.assets)
        self.images.setText(f"{count} 张图，顺序即投递顺序" if count else "没有图片")

    def note_phone_pending(self) -> None:
        if not self._editing:
            self.reload()
            return
        self.banner.setText("手机有更新。采用手机版或保留电脑稿，插入时冻结当前这一版。")
        self.banner.show()

    def take_phone(self) -> None:
        self.app.accept_phone_pending()
        self.reload()

    def keep_pc(self) -> None:
        self.app.keep_pc_edit()
        self.banner.hide()

    def copy_only(self) -> None:
        self.app.draft.text = self.editor.toPlainText()
        self.app.review_editing = False
        self.app._save_draft()
        self.app.copy_text()

    def insert(self) -> None:
        self.app.draft.text = self.editor.toPlainText()
        self.app.draft.revision += 1
        self.app.review_editing = False
        self.app._save_draft()
        self.app.insert_current()
        self.widget.hide()

    def show(self) -> None:
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
        w.setWindowTitle("DoubaoTypeless")
        w.resize(560, 600)
        w.setStyleSheet(STYLESHEET)
        root = QVBoxLayout(w)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        connect = QWidget()
        cl = QVBoxLayout(connect)
        cl.addWidget(QLabel("让手机成为更顺手的输入工具。"))
        card = QFrame()
        card.setObjectName("card")
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
        self.grant_row = QHBoxLayout()
        cl.addLayout(self.grant_row)
        cl.addWidget(QLabel("本机练习框（引导用，不是 Cursor）"))
        self.practice = QPlainTextEdit()
        self.practice.setPlaceholderText("点这里，再按 Alt+I 练习插入并复制。")
        self.practice.setFixedHeight(88)
        cl.addWidget(self.practice)
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
        self.hotkey_insert = QLineEdit(str(stored.get("hotkey_insert") or "<alt>+i"))
        self.hotkey_recall = QLineEdit(str(stored.get("hotkey_recall") or "<alt>+<shift>+i"))
        sl.addRow("插入并复制", self.hotkey_insert)
        sl.addRow("召回上次", self.hotkey_recall)
        self.autostart = QCheckBox("登录 Windows 时启动（到托盘）")
        self.autostart.setChecked(bool(stored.get("autostart")))
        self.start_min = QCheckBox("启动后先到托盘")
        self.start_min.setChecked(bool(stored.get("start_minimized")))
        sl.addRow(self.autostart)
        sl.addRow(self.start_min)
        sl.addRow(QLabel("可选模型。不配密钥也能用文字、图片和白板。"))
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
        self.byok_status = QLabel("")
        self.byok_status.setObjectName("muted")
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
        save = QPushButton("保存设置")
        save.setObjectName("primary")
        save.clicked.connect(self.save_settings)
        srow.addWidget(probe)
        srow.addWidget(export)
        srow.addWidget(save)
        sl.addRow(srow)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.NoFrame)
        settings_scroll.setWidget(settings)
        tabs.addTab(settings_scroll, "常用设置")

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
        self.timer = QTimer(w)
        self.timer.timeout.connect(self.refresh)
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

        log = self.app.data_dir / "logs" / "v3.log"
        QMessageBox.information(
            self.widget,
            "帮助与诊断",
            "1. 手机浏览器打开上面的地址或扫码。\n"
            "2. 电脑点允许插入后，手机说话，电脑点目标再按 Alt+I 插入并复制。\n"
            "3. 不要改 JSON、不要设环境变量、不必打开 pc.html。\n"
            f"日志：{log}",
        )

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

    def refresh(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidgetItem, QPushButton

        url = self.pairing_url()
        self.url_label.setText(url)
        code = self.app.auth.current_pairing_challenge() or ""
        short = self.app.auth.current_short_code() or ""
        remain = int(self.app.auth.pairing_remaining_s())
        self.code_label.setText(f"扫码即连。备用短码 {short}  （{remain}s）")
        pix = qr_pixmap(url)
        if not pix.isNull():
            self.qr.setPixmap(pix)
        sessions = self.app.auth.public_sessions()
        sig = tuple((s["session_id"], s["allow_insert"], s["allow_capture"]) for s in sessions)
        if sig != self._session_sig:
            self._session_sig = sig
            self._clear_grant_row()
            if not sessions:
                self.qr.show()
                self.practice.show()
                self.device_box.setText("还没有手机连上。扫码后在这里批准插入和截图。")
            else:
                self.qr.hide()
                self.practice.hide()
                lines = []
                for item in sessions:
                    lines.append(
                        f"设备 {item['device_id'][:8]}  插入={'开' if item['allow_insert'] else '关'}  "
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
                    self.grant_row.addWidget(allow_i)
                    self.grant_row.addWidget(allow_c)
                    self.grant_row.addWidget(revoke)
                self.device_box.setText("\n".join(lines))
        hist_sig = tuple(
            (item["bundle"].get("bundle_id"), item.get("attempt_result"))
            for item in self.app.history.items[-20:]
        )
        if hist_sig != self._hist_sig:
            self._hist_sig = hist_sig
            self.recent_list.clear()
            for item in reversed(self.app.history.items[-20:]):
                bundle = item["bundle"]
                preview = (bundle.get("text") or "").replace("\n", " ")[:48] or "（无文字）"
                row = QListWidgetItem(f"{item.get('attempt_result')}  {len(bundle.get('assets') or [])}图  {preview}")
                row.setData(Qt.UserRole, bundle)
                self.recent_list.addItem(row)

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
        payload = {
            "hotkey_insert": self.hotkey_insert.text().strip() or "<alt>+i",
            "hotkey_recall": self.hotkey_recall.text().strip() or "<alt>+<shift>+i",
            "autostart": self.autostart.isChecked(),
            "start_minimized": self.start_min.isChecked(),
            "byok_endpoint": self.byok_endpoint.text().strip(),
            "byok_api_key": self.byok_key.text().strip(),
            "byok_model": self.byok_model.text().strip(),
        }
        save_settings(self.app.data_dir, payload)
        save_vocab(self.app.data_dir, self.vocab.toPlainText())
        stored = load_settings(self.app.data_dir)
        self.app.byok.endpoint = stored["byok_endpoint"]
        self.app.byok.api_key = stored["byok_api_key"]
        self.app.byok.model = stored["byok_model"]
        ok, err = apply_v3_autostart(bool(stored["autostart"]))
        if stored["autostart"] and not ok:
            self.byok_status.setText(f"设置已保存。开机自启未写入：{err}")
            self.byok_status.setObjectName("error")
        else:
            self.byok_status.setText("已保存。热键改动下次启动生效；失败请改键。")
            self.byok_status.setObjectName("muted")

    def probe_byok(self) -> None:
        from doubao_typeless.services.byok import ByokService, ERROR_LABELS

        endpoint = self.byok_endpoint.text().strip()
        key = self.byok_key.text().strip()
        model = self.byok_model.text().strip()
        if not endpoint or not key:
            self.byok_status.setText(ERROR_LABELS["no_key"])
            return
        from doubao_typeless.app import _httpx_json_post

        svc = ByokService(endpoint=endpoint, api_key=key, model=model, post=_httpx_json_post)
        out = svc.polish("ping", draft_id="probe", revision=1, current_draft_id="probe", current_revision=1)
        used = out.get("model") or model
        self.byok_status.setText(f"{out.get('message') or out.get('status') or ''}  model={used}")

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
        self.app._last_attempt = None
        self.app.insert_last()

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
        menu.addAction("召回上次", app.recall_last)
        menu.addAction("截图给手机", app.capture_region)
        self._pause_action = menu.addAction("暂停连接", self.toggle_pause)
        menu.addSeparator()
        menu.addAction("退出", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("DoubaoTypeless")
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self._wake = listen_for_commands(self._on_ipc)
        self.app.ui_hook = self._from_service
        if app.hud._widget is not None:
            expand = getattr(app.hud, "_expand", None)
            if expand is not None:
                expand.clicked.connect(self.review.show)

    def _explained_tray(self) -> None:
        if not load_settings(self.app.data_dir).get("tray_explained"):
            self.tray.showMessage("DoubaoTypeless", "已在托盘运行。点图标可再打开窗口。")
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
        if event == "recovery_ask":
            QTimer.singleShot(0, host, self._ask_recovery)
        elif event == "phone_pending":
            QTimer.singleShot(0, host, self.review.note_phone_pending)
        elif event == "activity":
            QTimer.singleShot(0, host, self.client.refresh)
        elif event == "expand":
            QTimer.singleShot(0, host, self.review.show)
        elif event in {"hide_after_insert", "new_draft"}:
            QTimer.singleShot(0, self.review.widget, self.review.widget.hide)

    def _ask_recovery(self) -> None:
        mode = RecoveryDialog(self.client.widget).exec()
        if mode != "cancel":
            self.app.confirm_recovery(mode)

    def quit(self) -> None:
        from PySide6.QtWidgets import QApplication

        self.client._closing_for_quit = True
        self.tray.hide()
        try:
            import asyncio

            loop = getattr(self.app, "_loop", None)
            if loop is not None:
                asyncio.run_coroutine_threadsafe(self.app.stop(), loop).result(5)
        except Exception:
            pass
        QApplication.instance().quit()


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
    app = V3App(data_dir=data_dir)
    app._lock = lock
    try:
        app.hud.start()
        try:
            from doubao_typeless.platform.windows.hotkeys import start_hotkeys

            stored = load_settings(app.data_dir)
            start = start_hotkeys(
                on_insert=app.insert_current,
                on_recall=app.recall_last,
                on_region=app.capture_region,
                insert_combo=str(stored.get("hotkey_insert") or "<alt>+i"),
                recall_combo=str(stored.get("hotkey_recall") or "<alt>+<shift>+i"),
            )
            app._hotkeys = start
            if start.get("failures"):
                logger(f"[v3] 热键注册失败: {start['failures']}")
        except Exception as exc:
            logger(f"[v3] 热键未启动: {exc}")
        loop = app.start_background(start_hud=False)
        app._loop = loop
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
