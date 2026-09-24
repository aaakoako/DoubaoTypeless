"""Platform boundary. Native target identity is required before injecting keys."""
import os
import sys
import time

from doubao_typeless.platform.windows.focus import FocusSnapshot, same_target


def native():
    if sys.platform == 'darwin':
        from . import macos
        return macos
    if sys.platform.startswith('linux'):
        from . import linux_x11
        return linux_x11
    raise RuntimeError('Unsupported desktop platform')


def read_target():
    if sys.platform == 'win32':
        from .windows.focus import read_target as impl
        return impl()
    return native().read_target()


def restore_target(saved):
    if sys.platform == 'win32':
        from .windows.focus import restore_target as impl
        return impl(saved)
    return native().restore_target(saved)


def locate_current(saved=None):
    if sys.platform == 'win32':
        from .windows.composer_locator import locate_current as impl
        return impl(saved)
    current = read_target()
    if current.kind not in {'composer', 'edit'}:
        if saved and restore_target(saved):
            current = read_target()
        else:
            return {'status': 'not_found'}
    return {'status': 'found', 'candidate': current._asdict()}


def read_clipboard_text():
    if sys.platform == 'win32':
        from .windows.clipboard import read_clipboard_text as impl
        return impl()
    from .qt_bridge import call
    from PySide6.QtWidgets import QApplication
    return call(lambda: QApplication.clipboard().text())


def set_clipboard_text(text):
    if sys.platform == 'win32':
        from .windows.clipboard import set_clipboard_text as impl
        return impl(text)
    from .qt_bridge import call
    from PySide6.QtWidgets import QApplication
    call(lambda: QApplication.clipboard().setText(text))


def set_clipboard_png(data):
    if sys.platform == 'win32':
        from .windows.clipboard import set_clipboard_png as impl
        return impl(data)
    from .qt_bridge import call
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    image = QImage.fromData(data, 'PNG')
    if image.isNull():
        raise ValueError('Invalid PNG')
    call(lambda: QApplication.clipboard().setImage(image))


def send_paste():
    if sys.platform == 'win32':
        from .windows.clipboard import send_paste as impl
        return impl()
    return native().send_paste()


def send_submit(mode):
    if sys.platform == 'win32':
        from .windows.native_input import send_submit as impl
        return impl(mode)
    return native().send_submit(mode)


def wait_modifiers_up():
    if sys.platform == 'win32':
        from .windows.guards import wait_modifiers_up as impl
        return impl()
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        if not native().modifiers_down():
            return True
        time.sleep(.02)
    return False


def session_locked():
    if sys.platform == 'win32':
        from .windows.guards import session_locked as impl
        return impl()
    try:
        target = read_target()
        return not target.hwnd or not target.runtime_id
    except Exception:
        return True


def target_above_ours():
    if sys.platform == 'win32':
        from .windows.integrity import target_above_ours as impl
        return impl()
    return False


def start_input_activity():
    if sys.platform == 'win32':
        from .windows.input_activity import InputActivityMonitor
        return InputActivityMonitor().start()
    return None


def grab_primary(scope='primary', *, hide=None):
    if sys.platform == 'win32':
        from .windows.capture import grab_primary as impl
        return impl(scope, hide=hide)
    if sys.platform.startswith('linux') and os.environ.get('XDG_SESSION_TYPE') == 'wayland':
        raise RuntimeError('Wayland 截屏尚未接入桌面授权，请从手机上传图片')
    if sys.platform == 'darwin':
        native().require_screen_permission()
    if hide:
        hide()
    from .qt_bridge import call
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QBuffer, QIODevice
    def capture():
        screens = QApplication.screens()
        screen = QApplication.primaryScreen()
        if scope.startswith('display:'):
            index = int(scope.split(':')[1]) - 1
            if not 0 <= index < len(screens):
                raise ValueError('Unknown display')
            screen = screens[index]
        rect = None
        if scope.startswith('region:'):
            from PySide6.QtCore import QRect
            rect = QRect(*map(int, scope.split(':')[1].split(',')))
            screen = next((s for s in screens if s.geometry().contains(rect)), None)
        elif scope != 'primary' and not scope.startswith('display:'):
            raise ValueError('Unknown capture scope')
        if screen is None:
            raise RuntimeError('请选择单个屏幕内的截图区域')
        pixmap = screen.grabWindow(0)
        if rect:
            ratio = pixmap.devicePixelRatio()
            rect.translate(-screen.geometry().x(), -screen.geometry().y())
            pixmap = pixmap.copy(int(rect.x()*ratio), int(rect.y()*ratio),
                                 int(rect.width()*ratio), int(rect.height()*ratio))
        if pixmap.isNull():
            raise RuntimeError('无法截屏，请检查屏幕录制权限')
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, 'PNG')
        return bytes(buffer.data())
    return call(capture)


def start_hotkeys(**kwargs):
    if os.environ.get('DT_V3_DISABLE_HOTKEYS') == '1':
        return {'failures': []}
    from .windows.hotkeys import start_hotkeys as impl
    if sys.platform.startswith('linux') and os.environ.get('XDG_SESSION_TYPE') == 'wayland':
        return {'failures': ['Wayland 暂不支持全局快捷键和自动插入；请使用 X11 会话']}
    if sys.platform == 'darwin' and not native().trusted():
        return {'failures': ['请在系统设置 → 隐私与安全性 → 辅助功能中允许 Pocket Composer，然后重启应用']}
    return impl(**kwargs)


def platform_hint():
    if sys.platform == 'darwin':
        return 'macOS 体验版 · 插入需辅助功能权限，截屏需屏幕录制权限；请先选中目标输入框。升级请下载对应安装包。'
    if sys.platform.startswith('linux'):
        if os.environ.get('XDG_SESSION_TYPE') == 'wayland':
            return 'Wayland · 可编辑、同步和复制；自动插入、全局快捷键与截屏需切换 X11 会话。'
        return 'Linux X11 体验版 · 请开启桌面辅助功能，并先选中目标输入框。升级请下载对应安装包。'
    return ''
