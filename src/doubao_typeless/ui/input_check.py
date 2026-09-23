"""Jev settings and non-modal draft feedback."""
import threading
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QLineEdit, QPushButton, QPlainTextEdit
from doubao_typeless.services.input_check import evaluate, presentation, VOICE_NOTE
from doubao_typeless.ui.icons import icon, judgment_icon, ToneBadge


class InputCheckSettings:
    def __init__(self, form, stored, parent):
        self.enabled = QCheckBox('输入检查 · Jev')
        self.enabled.setIcon(icon('inspect'))
        self.enabled.setChecked(bool(stored.get('jev_enabled')))
        form.addRow(self.enabled)
        notice = QLabel('开启后发送当前文字至 TypeSafe；不含图片和历史。')
        notice.setToolTip('检查疑似转写错误、歧义和缺项。检查在后台进行，可随时复制或插入。')
        notice.setWordWrap(True); notice.setObjectName('muted')
        form.addRow(notice)
        self.key = QLineEdit(str(stored.get('jev_api_key') or ''))
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText('粘贴 TypeSafe API Key')
        form.addRow('Jev API Key', self.key)
        self.emotion = QCheckBox('显示语气')
        self.emotion.setIcon(icon('positive'))
        self.emotion.setToolTip('仅判断文字语气，不代表真实情绪；不会随正文发送。')
        self.emotion.setChecked(bool(stored.get('jev_emotion', True)))
        form.addRow(self.emotion)
        self.note = QCheckBox('疑似误字时附语音说明')
        self.note.setIcon(icon('mic'))
        self.note.setChecked(bool(stored.get('jev_voice_note')))
        self.note.setToolTip(VOICE_NOTE+'\n只提示可能有误，不要求目标模型追问。可在浮窗为本段取消。')
        form.addRow(self.note)
        row = QHBoxLayout()
        self.probe = QPushButton('检测连接'); self.probe.setIcon(icon('waiting'))
        get_key = QPushButton('申请 API Key')
        get_key.setIcon(icon('key'))
        get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://console.typesafe.ai/')))
        row.addWidget(self.probe); row.addWidget(get_key); row.addStretch(1)
        form.addRow(row)
        self.status = QLabel('保存后生效')
        self.status.setToolTip('检测连接只发送固定示例文字。')
        self.status.setWordWrap(True); self.status.setObjectName('muted')
        form.addRow(self.status)
        def probe():
            key = self.key.text().strip()
            if not key:
                self.status.setText('请先填写 Jev API Key'); return
            self.probe.setEnabled(False); self.status.setText('连接中…')
            def work():
                result = evaluate('这是一条连接检测示例。', key, False)
                def done():
                    self.probe.setEnabled(True)
                    if self.key.text().strip() != key:
                        self.status.setText('Key 已变化，请重新检测'); return
                    self.status.setText('已连接 · 保存后生效' if result['status']=='ready' else result['message'])
                QTimer.singleShot(0, parent, done)
            threading.Thread(target=work, daemon=True).start()
        self.probe.clicked.connect(probe)

    def values(self):
        return {'jev_enabled': self.enabled.isChecked(), 'jev_api_key': self.key.text().strip(),
                'jev_emotion': self.emotion.isChecked(), 'jev_voice_note': self.note.isChecked()}


class InputCheckDetails(QWidget):
    def __init__(self, app, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel(); self.summary.setTextFormat(Qt.PlainText); self.summary.setWordWrap(True)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True); self.details.setMaximumHeight(110)
        self.note = QPushButton('附注已开')
        self.note.setCheckable(True)
        self.note.setToolTip(VOICE_NOTE+'\n点击切换本段附注，不修改原稿。')
        self.note.clicked.connect(app.toggle_input_note)
        self.retry = QPushButton('重新检查')
        self.retry.setIcon(icon('waiting'))
        self.retry.clicked.connect(lambda: app.input_check.retry(app.input_check_identity()))
        header=QHBoxLayout()
        self.symbol=QLabel();self.tone=ToneBadge()
        header.addWidget(self.symbol);header.addWidget(self.summary,1);header.addWidget(self.tone)
        layout.addLayout(header); layout.addWidget(self.details)
        actions = QHBoxLayout(); actions.addWidget(self.note); actions.addWidget(self.retry)
        layout.addLayout(actions)
        self._timer = QTimer(self); self._timer.setInterval(250)
        def refresh():
            result = app.input_check.view(app.input_check_identity())
            summary, details = presentation(result)
            self.setVisible(bool(summary))
            self.summary.setText(summary)
            self.symbol.setPixmap(icon(judgment_icon(result)).pixmap(18,18))
            self.tone.set_tone(result.get('tone',''))
            if self.details.toPlainText()!=details:self.details.setPlainText(details)
            self.details.setVisible(bool(details))
            self.note.setVisible(bool(result.get('note') or result.get('suppressed')))
            self.note.setText('附注已关' if result.get('suppressed') else '附注已开')
            self.note.setChecked(bool(result.get('note')))
            self.note.setIcon(icon('note_off' if result.get('suppressed') else 'mic'))
            self.retry.setVisible(result.get('status') == 'error')
        self._timer.timeout.connect(refresh); self._timer.start(); refresh()
