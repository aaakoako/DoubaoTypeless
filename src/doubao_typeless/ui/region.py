"""Fullscreen region picker. Escape/right-click cancels; drag completes a physical-pixel bbox."""
from __future__ import annotations

from typing import Optional


def select_region() -> Optional[tuple[int, int, int, int]]:
    try:
        from PySide6.QtCore import Qt, QRect, QPoint
        from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QMouseEvent, QKeyEvent
        from PySide6.QtWidgets import QApplication, QWidget
    except ImportError:
        return None

    app = QApplication.instance() or QApplication([])
    result: dict[str, tuple[int, int, int, int] | None] = {"bbox": None}

    class Overlay(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.setWindowTitle("DT-V3-REGION")
            virtual = QRect()
            for screen in QGuiApplication.screens():
                virtual = virtual.united(screen.geometry())
            self.setGeometry(virtual)
            self.setWindowOpacity(0.25)
            self._origin: QPoint | None = None
            self._current: QPoint | None = None
            self.setMouseTracking(True)
            self.show()
            self.raise_()

        def mousePressEvent(self, event: QMouseEvent) -> None:
            if event.button() == Qt.RightButton:
                result["bbox"] = None
                self.close()
                return
            self._origin = event.globalPosition().toPoint()
            self._current = self._origin
            self.update()

        def mouseMoveEvent(self, event: QMouseEvent) -> None:
            if self._origin is None:
                return
            self._current = event.globalPosition().toPoint()
            self.update()

        def mouseReleaseEvent(self, event: QMouseEvent) -> None:
            if self._origin is None or event.button() != Qt.LeftButton:
                return
            end = event.globalPosition().toPoint()
            x1, y1 = min(self._origin.x(), end.x()), min(self._origin.y(), end.y())
            x2, y2 = max(self._origin.x(), end.x()), max(self._origin.y(), end.y())
            if x2 - x1 < 8 or y2 - y1 < 8:
                result["bbox"] = None
            else:
                screen = QGuiApplication.screenAt(QPoint(x1, y1)) or QGuiApplication.primaryScreen()
                dpr = float(screen.devicePixelRatio()) if screen else 1.0
                result["bbox"] = (int(x1 * dpr), int(y1 * dpr), int((x2 - x1) * dpr), int((y2 - y1) * dpr))
            self.close()

        def keyPressEvent(self, event: QKeyEvent) -> None:
            if event.key() == Qt.Key_Escape:
                result["bbox"] = None
                self.close()

        def paintEvent(self, _event) -> None:
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(13, 35, 24, 80))
            if self._origin and self._current:
                rect = QRect(self._origin, self._current).normalized()
                painter.setPen(QPen(QColor(22, 125, 113), 2))
                painter.drawRect(rect)

    overlay = Overlay()
    overlay.show()
    while overlay.isVisible():
        app.processEvents()
    return result["bbox"]
