"""Animated categorical reference map. No radial scores or implied success rate."""
import time
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget, QSizePolicy
from doubao_typeless.services.input_check import REFERENCE_DIMENSIONS, REFERENCE_STATES
from doubao_typeless.ui.icons import icon


class ReferenceChart(QWidget):
    def __init__(self, parent=None, *, compact=False):
        super().__init__(parent)
        self.states = {}
        self.presentation_enabled = True
        self.motion = True
        self.started = 0.
        self.phase = 1.
        self.setMinimumHeight(132)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self._tick)
        self.setAccessibleName('本段输入参考图')
        self.hide()

    def sizeHint(self):
        return QSize(300, 132)

    def set_motion(self, enabled):
        self.motion = bool(enabled)
        if not self.motion:
            self.timer.stop(); self.phase = 1.; self.update()

    def set_result(self, result):
        rows = {r['id']: r.get('state', 'unknown') for r in result.get('references', [])
                if r.get('id') in REFERENCE_DIMENSIONS}
        self.setVisible(self.presentation_enabled and result.get('status') == 'ready' and bool(rows))
        if rows == self.states:
            return
        self.states = rows
        descriptions = [title + '：' + REFERENCE_STATES.get(rows.get(key), '暂无法判断')
                        for key, (title, _) in REFERENCE_DIMENSIONS.items()]
        detail = '本段参考，未读取上文；不代表成功率。\n' + '\n'.join(descriptions)
        self.setToolTip(detail)
        self.setAccessibleDescription(detail)
        self.started = time.monotonic()
        self.phase = 0. if self.motion else 1.
        if self.motion and self.isVisible():
            self.timer.start()
        self.update()

    def _tick(self):
        self.phase = min(1., (time.monotonic() - self.started) / .55)
        if self.phase >= 1. or not self.isVisible():
            self.timer.stop()
        self.update()

    def showEvent(self, event):
        if self.motion and self.states:
            self.started = time.monotonic(); self.phase = 0.; self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont(self.font()); font.setPixelSize(12); painter.setFont(font)
        center = QPointF(self.width() / 2, 64)
        reach = max(45, min(115, self.width() / 2 - 32))
        nodes = [QPointF(center.x(), 27), QPointF(center.x() + reach, 64),
                 QPointF(center.x(), 101), QPointF(center.x() - reach, 64)]
        names = list(REFERENCE_DIMENSIONS)
        for i, (key, point) in enumerate(zip(names, nodes)):
            state = self.states.get(key, 'unknown')
            unknown = state in {'unknown', 'na', 'tentative_na'}
            provisional = state.startswith('tentative_')
            color = '#8b94aa' if unknown else '#6156dc'
            pen = QPen(QColor('#dce1ec'), 1.5)
            pen.setStyle(Qt.DashLine if unknown or provisional else Qt.SolidLine)
            painter.setPen(pen); painter.drawLine(center, point)
            if not unknown:
                pulse = center + (point - center) * (1 - (1 - self.phase) ** 3)
                painter.setPen(Qt.NoPen); painter.setBrush(QColor(color)); painter.drawEllipse(pulse, 2.5, 2.5)
            painter.setPen(QPen(QColor(color), 1.3, Qt.DashLine if unknown or provisional else Qt.SolidLine))
            painter.setBrush(QColor('#f1f0ff' if not unknown else '#f6f7fb'))
            painter.drawEllipse(point, 12, 12)
            symbol = ('check' if state == 'clear' else 'help' if 'partial' in state else
                      'link' if 'context' in state else 'inspect' if state == 'tentative_clear' else None)
            if symbol:
                icon(symbol, color).paint(painter, int(point.x()-8), int(point.y()-8), 16, 16)
            else:
                painter.setPen(QPen(QColor(color), 1.5))
                if state in {'na','tentative_na'}:
                    painter.drawLine(point + QPointF(-4,0), point + QPointF(4,0))
                # Unknown remains hollow; it is never a zero value.
            painter.setPen(QColor('#515b72'))
            label = REFERENCE_DIMENSIONS[key][0]
            rect = (QRectF(point.x()-30, 0 if i == 0 else 115, 60, 16) if i in {0,2}
                    else QRectF(point.x()-30, 82, 60, 16))
            painter.drawText(rect, Qt.AlignCenter, label)
        painter.setPen(Qt.NoPen); painter.setBrush(QColor('#ffffff'))
        painter.drawRoundedRect(QRectF(center.x()-30, 46, 60, 36), 9, 9)
        painter.setPen(QColor('#687087'))
        painter.drawText(QRectF(center.x()-30, 47, 60, 16), Qt.AlignCenter, '仅本段')
        small = QFont(font); small.setPixelSize(10); painter.setFont(small)
        painter.drawText(QRectF(center.x()-30, 63, 60, 14), Qt.AlignCenter, '上文未读')


class ReferenceStrip(ReferenceChart):
    """Four quiet markers in the HUD toolbar; full diagram belongs in details."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(24)
        self.setFixedSize(88, 24)

    def sizeHint(self):
        return QSize(88, 24)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for i, key in enumerate(REFERENCE_DIMENSIONS):
            state = self.states.get(key, 'unknown')
            x = 11 + i * 22
            unknown = state in {'unknown', 'na', 'tentative_na'}
            color = '#8b94aa' if unknown else '#6156dc'
            painter.setPen(QPen(QColor(color), 1, Qt.DashLine if unknown or state.startswith('tentative_') else Qt.SolidLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(x, 12), 8, 8)
            symbol = ('check' if state == 'clear' else 'help' if 'partial' in state else
                      'link' if 'context' in state else 'inspect' if state == 'tentative_clear' else None)
            if symbol:
                painter.setOpacity(.65 + .35 * self.phase)
                icon(symbol, color).paint(painter, x-6, 6, 12, 12)
                painter.setOpacity(1.)
