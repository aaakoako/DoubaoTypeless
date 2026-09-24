"""Jev settings and non-modal draft feedback."""
import threading
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QLineEdit, QPushButton, QPlainTextEdit, QComboBox
from doubao_typeless.services.input_check import evaluate, presentation, VOICE_NOTE
from doubao_typeless.ui.icons import icon, judgment_icon, ToneBadge


class InputCheckSettings:
    def __init__(self, form, stored, parent):
        self.enabled = QCheckBox('输入参考 · Jev')
        self.enabled.setIcon(icon('inspect'))
        self.enabled.setChecked(bool(stored.get('jev_enabled')))
        form.addRow(self.enabled)
        self.provider = QComboBox()
        self.provider.addItem('TypeSafe','typesafe');self.provider.addItem('Vercel AI Gateway','vercel')
        self.provider.addItem('OpenRouter','openrouter');self.provider.addItem('自定义','custom')
        self.provider.setCurrentIndex(max(0,self.provider.findData(stored.get('jev_provider','typesafe'))))
        form.addRow('服务商',self.provider)
        notice = QLabel('开启后发送当前文字至 TypeSafe；不含图片和历史。')
        notice.setToolTip('检查疑似转写错误、歧义和缺项。检查在后台进行，可随时复制或插入。')
        notice.setWordWrap(True); notice.setObjectName('muted')
        form.addRow(notice)
        self.key = QLineEdit(str(stored.get('jev_api_key') or ''))
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText('粘贴 TypeSafe API Key')
        form.addRow('TypeSafe Key', self.key)
        self.gateway_key = QLineEdit(str(stored.get('jev_vercel_key') or ''))
        self.gateway_key.setEchoMode(QLineEdit.Password)
        self.gateway_key.setPlaceholderText('粘贴 Vercel AI Gateway Key')
        form.addRow('Vercel Key',self.gateway_key)
        self.openrouter_key=QLineEdit(str(stored.get('jev_openrouter_key') or ''))
        self.custom_key=QLineEdit(str(stored.get('jev_custom_key') or ''))
        for label,field in (('OpenRouter Key',self.openrouter_key),('自定义 Key',self.custom_key)):
            field.setEchoMode(QLineEdit.Password);form.addRow(label,field)
        self.custom_endpoint=QLineEdit(str(stored.get('jev_custom_endpoint') or ''))
        self.custom_endpoint.setPlaceholderText('域名、Base URL 或完整接口地址')
        self.custom_model=QLineEdit(str(stored.get('jev_custom_model') or 'jev-latest'))
        from doubao_typeless.services.endpoints import endpoint_origin
        self._custom_key_origin=endpoint_origin(self.custom_endpoint.text()) if self.custom_key.text() else None
        self._custom_key_edited=False
        form.addRow('接口地址',self.custom_endpoint);form.addRow('模型 ID',self.custom_model)
        self._key_fields={'typesafe':self.key,'vercel':self.gateway_key,'openrouter':self.openrouter_key,'custom':self.custom_key}
        def key_field():
            return self._key_fields[self.provider.currentData()]
        def provider_changed():
            provider=self.provider.currentData()
            for name,field in self._key_fields.items():
                field.setVisible(name==provider);form.labelForField(field).setVisible(name==provider)
            for field in (self.custom_endpoint,self.custom_model):
                field.setVisible(provider=='custom');form.labelForField(field).setVisible(provider=='custom')
            notice.setText({'typesafe':'当前文字发送至 TypeSafe；不含图片和历史。',
                'vercel':'文字经 Vercel 发给 TypeSafe；不含图片和历史。',
                'openrouter':'文字经 OpenRouter 发给 TypeSafe；不含图片和历史。',
                'custom':'使用 TypeSafe 兼容接口；仅发送当前文字。'}[provider])
        self.provider.currentIndexChanged.connect(provider_changed);provider_changed()
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
        self.motion=QCheckBox('界面动效与语气彩蛋');self.motion.setIcon(icon('positive'))
        self.motion.setChecked(bool(stored.get('ui_motion',True)))
        form.addRow(self.motion)
        row = QHBoxLayout()
        self.probe = QPushButton('检测连接'); self.probe.setIcon(icon('waiting'))
        get_key = QPushButton('申请 API Key')
        get_key.setIcon(icon('key'))
        get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl({'vercel':'https://vercel.com/ai-gateway',
            'openrouter':'https://openrouter.ai/keys'}.get(self.provider.currentData(),'https://console.typesafe.ai/'))))
        row.addWidget(self.probe); row.addWidget(get_key); row.addStretch(1)
        form.addRow(row)
        self.status = QLabel('保存后生效')
        self.status.setToolTip('检测连接只发送固定示例文字。')
        self.status.setWordWrap(True); self.status.setObjectName('muted')
        form.addRow(self.status)
        def configuration_changed():
            self.status.setText('配置已变 · 待检测')
            self.status.setToolTip('保存后生效；检测连接只发送固定示例文字。')
        self.provider.currentIndexChanged.connect(configuration_changed)
        self.key.textChanged.connect(configuration_changed)
        self.gateway_key.textChanged.connect(configuration_changed)
        self.openrouter_key.textChanged.connect(configuration_changed);self.custom_key.textChanged.connect(configuration_changed)
        self.custom_endpoint.textChanged.connect(configuration_changed);self.custom_model.textChanged.connect(configuration_changed)
        def bind_custom_key():
            origin=endpoint_origin(self.custom_endpoint.text())
            self._custom_key_origin=origin if self.custom_key.text() and origin[1] else None
            self._custom_key_edited=True
        self.custom_key.textChanged.connect(bind_custom_key)
        def normalize_custom():
            from doubao_typeless.services.endpoints import normalize_endpoint,endpoint_origin
            try:
                normalized=normalize_endpoint(self.custom_endpoint.text(),'systemone')
                self.custom_endpoint.setText(normalized)
                if (self._custom_key_origin and endpoint_origin(normalized)!=self._custom_key_origin
                        and self.custom_key.text()):
                    self.custom_key.clear();self.status.setText('地址已变 · 请填写 Key')
                else:
                    if self.custom_key.text():self._custom_key_origin=endpoint_origin(normalized)
                    self.status.setText('地址已补全');self.status.setToolTip(normalized)
                return True
            except ValueError as exc:self.status.setText(str(exc));return False
        self.custom_endpoint.editingFinished.connect(normalize_custom)
        self.normalize_custom=normalize_custom
        def probe():
            key = key_field().text().strip();provider=self.provider.currentData()
            if provider=='custom' and not normalize_custom():return
            key=key_field().text().strip()
            endpoint=self.custom_endpoint.text();model=self.custom_model.text()
            if not key:
                self.status.setText('请先填写 Jev API Key'); return
            self.probe.setEnabled(False); self.status.setText('连接中…')
            def work():
                result = evaluate('这是一条连接检测示例。', key, False, provider=provider,
                                  endpoint=endpoint,model=model if provider=='custom' else '')
                def done():
                    self.probe.setEnabled(True)
                    if (key_field().text().strip()!=key or self.provider.currentData()!=provider or
                        (provider=='custom' and (self.custom_endpoint.text(),self.custom_model.text())!=(endpoint,model))):
                        self.status.setText('配置已变化，请重新检测'); return
                    self.status.setText('已连接 · 保存后生效' if result['status']=='ready' else result['message'])
                    self.status.setToolTip(result.get('detail','检测连接只发送固定示例文字。'))
                QTimer.singleShot(0, parent, done)
            threading.Thread(target=work, daemon=True).start()
        self.probe.clicked.connect(probe)

    def values(self):
        from doubao_typeless.services.endpoints import endpoint_origin
        return {'jev_enabled': self.enabled.isChecked(), 'jev_api_key': self.key.text().strip(),
                'jev_vercel_key':self.gateway_key.text().strip(),'jev_provider':self.provider.currentData(),
                'jev_openrouter_key':self.openrouter_key.text().strip(),'jev_custom_key':self.custom_key.text().strip(),
                'jev_custom_endpoint':self.custom_endpoint.text().strip(),'jev_custom_model':self.custom_model.text().strip(),
                'jev_custom_key_reentered':bool(self._custom_key_edited and self._custom_key_origin==endpoint_origin(self.custom_endpoint.text())),
                'ui_motion':self.motion.isChecked(),
                'jev_emotion': self.emotion.isChecked(), 'jev_voice_note': self.note.isChecked()}


class ReferencePanel(QWidget):
    """Four observations with equal visual weight; the rail is not a score."""
    def __init__(self, parent=None, *, compact=False):
        super().__init__(parent)
        from PySide6.QtWidgets import QGridLayout
        from doubao_typeless.services.input_check import REFERENCE_DIMENSIONS
        self.setObjectName('referencePanel')
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        self.labels = {}
        for i, (key, (title, _)) in enumerate(REFERENCE_DIMENSIONS.items()):
            label = QLabel(title + ' · 暂无法判断')
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setObjectName('referenceObservation')
            grid.addWidget(label, i // 2, i % 2)
            self.labels[key] = label
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.setToolTip('仅参考本段文字；未读取对话历史、图片或执行结果。各项独立，不代表成功率。')
        scope = QLabel('本段参考 · 未读取上文')
        scope.setObjectName('muted')
        scope.setWordWrap(True)
        grid.addWidget(scope, 2, 0, 1, 2)
        self.hide()

    def set_result(self, result):
        from doubao_typeless.services.input_check import REFERENCE_DIMENSIONS, REFERENCE_STATES
        from doubao_typeless.ui.theme_generated import COLORS
        rows = {r['id']: r for r in result.get('references', []) if r.get('id') in self.labels}
        self.setVisible(result.get('status') == 'ready' and bool(rows))
        for key, label in self.labels.items():
            state = rows.get(key, {}).get('state', 'unknown')
            text = REFERENCE_STATES.get(state, REFERENCE_STATES['unknown'])
            label.setText(REFERENCE_DIMENSIONS[key][0] + ' · ' + text)
            color = COLORS['accent'] if state == 'clear' else COLORS['muted']
            label.setStyleSheet('border-left: 3px solid ' + color + '; padding-left:6px;')
            label.setAccessibleName(label.text())


class InputCheckDetails(QWidget):
    def __init__(self, app, parent,feedback=None):
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
        layout.addLayout(header)
        self.references = ReferencePanel(self)
        layout.addWidget(self.references)
        layout.addWidget(self.details)
        actions = QHBoxLayout(); actions.addWidget(self.note); actions.addWidget(self.retry)
        layout.addLayout(actions)
        self._timer = QTimer(self); self._timer.setInterval(250)
        def refresh():
            result = app.input_check.view(app.input_check_identity())
            if feedback is not None:
                feedback.configure(app.input_check.options.get('ui_motion',True))
                feedback.set_tone(result.get('tone_kind',''))
            self.references.set_result(result)
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
