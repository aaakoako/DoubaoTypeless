"""Jev settings and non-modal draft feedback."""
import threading
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QLineEdit, QPushButton, QPlainTextEdit
from doubao_typeless.services.input_check import evaluate, presentation, VOICE_NOTE


class InputCheckSettings:
    def __init__(self, form, stored, parent):
        self.enabled = QCheckBox('启用 Jev 输入检查')
        self.enabled.setChecked(bool(stored.get('jev_enabled')))
        form.addRow(self.enabled)
        notice = QLabel('开启后将当前稿文字发送至 TypeSafe，检查疑似转写错误、歧义和缺项；不发送图片或历史，不影响直接插入。')
        notice.setWordWrap(True); notice.setObjectName('muted')
        form.addRow(notice)
        self.key = QLineEdit(str(stored.get('jev_api_key') or ''))
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText('TypeSafe API Key，与改写模型分开配置')
        form.addRow('Jev API Key', self.key)
        self.emotion = QCheckBox('显示表达语气判断')
        self.emotion.setChecked(bool(stored.get('jev_emotion', True)))
        form.addRow(self.emotion)
        self.note = QCheckBox('疑似转写错误时，自动附加语音说明')
        self.note.setChecked(bool(stored.get('jev_voice_note')))
        self.note.setToolTip(VOICE_NOTE+'\n只提示可能有误，不要求目标模型追问。可在浮窗为本段取消。')
        form.addRow(self.note)
        row = QHBoxLayout()
        self.probe = QPushButton('检测 Jev 连接')
        get_key = QPushButton('申请 API Key')
        get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://console.typesafe.ai/')))
        row.addWidget(self.probe); row.addWidget(get_key); row.addStretch(1)
        form.addRow(row)
        self.status = QLabel('保存设置后生效；检测连接只发送固定示例文字。')
        self.status.setWordWrap(True); self.status.setObjectName('muted')
        form.addRow(self.status)
        def probe():
            key = self.key.text().strip()
            if not key:
                self.status.setText('请先填写 Jev API Key'); return
            self.probe.setEnabled(False); self.status.setText('正在检测 Jev 连接…')
            def work():
                result = evaluate('这是一条连接检测示例。', key, False)
                def done():
                    self.probe.setEnabled(True)
                    if self.key.text().strip() != key:
                        self.status.setText('Key 已变化，请重新检测'); return
                    self.status.setText('Jev 已连接；请保存设置以启用检查。' if result['status']=='ready' else result['message'])
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
        self.note = QPushButton('本段不附说明')
        self.note.clicked.connect(app.toggle_input_note)
        self.retry = QPushButton('重新检查')
        self.retry.clicked.connect(lambda: app.input_check.retry(app.input_check_identity()))
        layout.addWidget(self.summary); layout.addWidget(self.details)
        actions = QHBoxLayout(); actions.addWidget(self.note); actions.addWidget(self.retry)
        layout.addLayout(actions)
        self._timer = QTimer(self); self._timer.setInterval(250)
        def refresh():
            result = app.input_check.view(app.input_check_identity())
            summary, details = presentation(result)
            self.setVisible(bool(summary))
            self.summary.setText(summary)
            if self.details.toPlainText()!=details:self.details.setPlainText(details)
            self.note.setVisible(bool(result.get('note') or result.get('suppressed')))
            self.note.setText('本段附上说明' if result.get('suppressed') else '本段不附说明')
            self.retry.setVisible(result.get('status') == 'error')
        self._timer.timeout.connect(refresh); self._timer.start(); refresh()
