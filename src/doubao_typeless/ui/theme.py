"""桌面、HUD、恢复/定位对话框共用组件语言；颜色由JSON生成。"""
from doubao_typeless.ui.theme_generated import COLORS as C, METRICS as M
from pathlib import Path
import sys

_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[3]))
_checkmark = (_root / 'assets/checkmark.svg').as_posix()
_chevron = (_root / 'assets/chevron-down.svg').as_posix()

QSS = f"""
QWidget {{ color:{C['ink']}; font-size:{M['text_size']}px; font-family: 'Microsoft YaHei UI','Microsoft YaHei','Noto Sans CJK SC','Segoe UI'; }}
QWidget#appWindow, QDialog {{ background:{C['bg']}; }}
QWidget#hudWindow {{ background:transparent; border:0; }}
QFrame#card {{ background:{C['surface']}; border:1px solid {C['line']}; border-radius:{M['radius_card']}px; }}
QLabel {{ background:transparent; border:0; }}
QWidget#referencePanel {{ background:{C['soft']}; border-radius:10px; }}
QLabel#referenceObservation {{ font-size:12px; }}
QLabel#muted {{ color:{C['muted']}; }}
QLabel#error {{ color:{C['danger']}; }}
QLabel[role='title'] {{ font-size:{M['title_size']}px; font-weight:600; }}
QLabel[role='status'] {{ color:{C['muted']}; font-size:12px; }}
QTabWidget::pane {{ border:0; }}
QTabBar::tab {{ background:transparent; border:0; border-bottom: 2px solid transparent; padding:10px 16px; color:{C['muted']}; }}
QTabBar::tab:hover {{ color:{C['ink']}; background:{C['soft']}; }}
QTabBar::tab:selected {{ color:{C['accent']}; border-bottom: 2px solid {C['accent']}; font-weight:600; }}
QPushButton, QToolButton {{ background:{C['disabled']}; color:{C['ink']}; border:1px solid transparent; border-radius:{M['radius_control']}px; padding:6px 12px; min-height:20px; }}
QPushButton:hover, QToolButton:hover {{ background:{C['hover']}; }}
QPushButton:pressed, QToolButton:pressed {{ background:{C['pressed']}; }}
QPushButton:focus, QToolButton:focus {{ border:1px solid {C['accent']}; }}
QPushButton#primary, QPushButton[role='primary'] {{ background:{C['accent']}; color:white; }}
QPushButton#primary:hover, QPushButton[role='primary']:hover {{ background:{C['accent_hover']}; }}
QPushButton#primary:pressed, QPushButton[role='primary']:pressed {{ background:{C['accent_pressed']}; }}
QPushButton#danger {{ background:{C['danger_soft']}; color:{C['danger']}; }}
QPushButton:disabled, QToolButton:disabled {{ background:{C['disabled']}; color:{C['disabled_ink']}; border-color:transparent; }}
QPushButton#primary:disabled, QPushButton[role='primary']:disabled {{ background:{C['soft']}; color:{C['disabled_ink']}; }}
QToolButton[role='quiet'] {{ background:transparent; color:{C['muted']}; padding:6px; }}
QToolButton:checked {{ color:{C['accent']}; background:{C['soft']}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QListWidget {{ background:{C['surface']}; border:1px solid {C['line']}; border-radius:{M['radius_control']}px; padding:6px; selection-background-color:{C['soft']}; selection-color:{C['ink']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color:{C['accent']}; }}
QTextEdit#hudBody {{ background:transparent; border:0; padding:0; font-size:14px; }}
QLineEdit:disabled, QPlainTextEdit:disabled {{ background:{C['disabled']}; color:{C['disabled_ink']}; }}
QComboBox::drop-down {{ border:0; width:24px; }}
QComboBox::down-arrow {{ image:url('{_chevron}'); width:12px; height:12px; }}
QComboBox QAbstractItemView {{ background:{C['surface']}; color:{C['ink']}; selection-background-color:{C['soft']}; selection-color:{C['ink']}; }}
QListWidget::item {{ padding:8px; border-radius:6px; }}
QListWidget::item:selected {{ background:{C['soft']}; color:{C['ink']}; }}
QListWidget::item:hover {{ background:{C['hover']}; }}
QCheckBox {{ spacing:8px; background:transparent; padding:4px 0; }}
QCheckBox::indicator {{ width:16px; height:16px; border:1px solid {C['line']}; border-radius:4px; background:{C['surface']}; }}
QCheckBox::indicator:checked {{ background:{C['accent']}; border:1px solid {C['accent']}; image:url('{_checkmark}'); }}
QCheckBox::indicator:hover {{ border-color:{C['accent']}; }}
QScrollArea {{ background:transparent; border:0; }}
QScrollArea > QWidget, QScrollArea > QWidget > QWidget, QTabWidget > QStackedWidget {{ background:{C['bg']}; }}
QScrollBar:vertical {{ background:transparent; width:8px; margin:0; }}
QScrollBar::handle:vertical {{ background:{C['line']}; min-height:24px; border-radius:4px; }}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{ background:transparent; }}
QMenu {{ background:{C['surface']}; border:1px solid {C['line']}; padding:4px; }}
QMenu::item {{ padding:8px 16px; border-radius:4px; }}
QMenu::item:selected {{ background:{C['soft']}; color:{C['ink']}; }}
QToolTip {{ background:{C['ink']}; color:white; border:0; padding:6px; }}
"""

def style_root(widget, *, hud=False):
    from doubao_typeless.ui.motion import interface_motion
    interface_motion()
    widget.setObjectName('hudWindow' if hud else 'appWindow')
    widget.setStyleSheet(QSS)
    layout=widget.layout()
    if layout:
        layout.setContentsMargins(16,12,16,12)
        layout.setSpacing(8)
