"""Small, consistent 24px SVG icons. Labels remain the accessible meaning."""
from functools import lru_cache

PATHS = {
    'calm': '<path d="M4 10c3-5 5 5 8 0s5 5 8 0M4 16c3-5 5 5 8 0s5 5 8 0"/>',
    'positive': '<circle cx="12" cy="12" r="9"/><path d="M8 14c2 3 6 3 8 0M8 9h.1M16 9h.1"/>',
    'urgent': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'forceful': '<path d="m13 2-9 12h7l-1 8 10-13h-7z"/>',
    'frustrated': '<circle cx="12" cy="12" r="9"/><path d="M8 16c2-3 6-3 8 0M8 9h.1M16 9h.1"/>',
    'check': '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    'inspect': '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M10 7v4M10 13h.1"/>',
    'help': '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4M12 17h.1"/>',
    'waiting': '<path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/>',
    'mic': '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 11v1a6 6 0 0 0 12 0v-1M12 18v3M9 21h6"/>',
    'note_off': '<path d="M6 11v1a6 6 0 0 0 9 5M12 18v3M9 21h6M9 5a3 3 0 0 1 6 1v5M3 3l18 18"/>',
    'copy': '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M15 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3"/>',
    'insert': '<path d="M8 4H5a2 2 0 0 0-2 2v14h14v-3M13 3h8v8M21 3l-9 9"/>',
    'expand': '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/>',
    'back': '<path d="m9 6-6 6 6 6M3 12h18"/>',
    'edit': '<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-4-4L5 15z"/>',
    'target': '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    'key': '<circle cx="8" cy="9" r="5"/><path d="m12 13 8 8M16 17l3-3M18 19l3-3"/>',
}
TONE_ICONS = {'平和':'calm','积极':'positive','急切':'urgent','强烈':'forceful','不满':'frustrated'}


def svg_source(name, color='#6254e8'):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
            + PATHS[name] + '</svg>')


@lru_cache(maxsize=64)
def icon(name, color='#6254e8'):
    from PySide6.QtCore import QByteArray
    from PySide6.QtGui import QIcon, QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer
    result = QIcon()
    renderer = QSvgRenderer(QByteArray(svg_source(name, color).encode()))
    for size in (16, 20, 24, 32, 40, 48):
        pixmap = QPixmap(size,size);pixmap.fill('transparent')
        painter = QPainter(pixmap);renderer.render(painter);painter.end()
        result.addPixmap(pixmap)
    return result


def judgment_icon(result):
    if result.get('status') in {'waiting','checking'}:return 'waiting'
    if result.get('status') != 'ready' or result.get('inconclusive'):return 'help'
    return 'inspect' if result.get('issues') else 'check'


from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout


class ToneBadge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout=QHBoxLayout(self);layout.setContentsMargins(3,0,3,0);layout.setSpacing(4)
        self.symbol=QLabel();self.label=QLabel()
        layout.addWidget(self.symbol);layout.addWidget(self.label)
        self.setToolTip('仅判断文字语气，不代表真实情绪；不会随正文发送。')

    def set_tone(self, tone):
        self.setVisible(tone in TONE_ICONS)
        if tone in TONE_ICONS:
            self.symbol.setPixmap(icon(TONE_ICONS[tone]).pixmap(18,18))
            self.label.setText(tone)
            self.setAccessibleName('表达语气：'+tone)
