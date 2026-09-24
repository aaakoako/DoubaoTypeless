"""macOS AX target identity and Quartz input. Never infer focus from app name."""
import os
import threading
import time
from collections import OrderedDict

from .accessible import input_kind
from .windows.focus import FocusSnapshot, same_target

_elements = OrderedDict()
_lock = threading.RLock()


def trusted():
    import ApplicationServices as AX
    return bool(AX.AXIsProcessTrusted())


def attribute(element, name):
    import ApplicationServices as AX
    error, value = AX.AXUIElementCopyAttributeValue(element, name, None)
    return value if error == 0 else None


def read_target():
    import ApplicationServices as AX
    from AppKit import NSWorkspace
    from CoreFoundation import CFHash
    with _lock:
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front is None:
            return FocusSnapshot('', '', 0)
        pid = int(front.processIdentifier())
        if pid == os.getpid():
            return FocusSnapshot('dt-v3-hud', '', pid, pid)
        if not trusted():
            return FocusSnapshot('', '', pid, pid)
        app = AX.AXUIElementCreateApplication(pid)
        AX.AXUIElementSetMessagingTimeout(app, .3)
        element = attribute(app, 'AXFocusedUIElement')
        if element is None:
            return FocusSnapshot('', '', pid, pid)
        role = str(attribute(element, 'AXRole') or '')
        subrole = str(attribute(element, 'AXSubrole') or '')
        description = ' '.join(str(attribute(element, key) or '') for key in
                               ('AXDescription', 'AXHelp', 'AXIdentifier', 'AXTitle'))
        error, settable = AX.AXUIElementIsAttributeSettable(element, 'AXValue', None)
        editable = role in {'AXTextField', 'AXTextArea', 'AXComboBox'} and error == 0 and bool(settable)
        kind = input_kind(role + subrole, description, editable=editable)
        token = int(CFHash(element))
        window = attribute(element, 'AXWindow')
        window_id = int(CFHash(window)) if window is not None else pid
        _elements[(pid, token)] = element
        _elements.move_to_end((pid, token))
        while len(_elements) > 64:
            _elements.popitem(last=False)
        after = NSWorkspace.sharedWorkspace().frontmostApplication()
        if after is None or int(after.processIdentifier()) != pid:
            return FocusSnapshot('', '', 0)
        return FocusSnapshot(role, '', window_id, pid, token, (pid, token), kind)


def restore_target(saved):
    import ApplicationServices as AX
    from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
    if len(saved) < 7 or not saved[5] or not trusted():
        return False
    with _lock:
        element = _elements.get((saved[3], saved[4]))
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(saved[3])
        if element is None or app is None:
            return False
        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        AX.AXUIElementSetAttributeValue(element, 'AXFocused', True)
        for _ in range(8):
            if same_target(saved, read_target()):
                return True
            time.sleep(.025)
    return False


def modifiers_down():
    import Quartz as Q
    flags = Q.CGEventSourceFlagsState(Q.kCGEventSourceStateCombinedSessionState)
    return bool(flags & (Q.kCGEventFlagMaskShift | Q.kCGEventFlagMaskControl |
                         Q.kCGEventFlagMaskAlternate | Q.kCGEventFlagMaskCommand))


def _key(code, flags=0):
    import Quartz as Q
    if not trusted():
        raise RuntimeError('需要 macOS 辅助功能权限')
    for down in (True, False):
        event = Q.CGEventCreateKeyboardEvent(None, code, down)
        if event is None:
            raise RuntimeError('无法创建键盘事件')
        Q.CGEventSetFlags(event, flags)
        Q.CGEventPost(Q.kCGHIDEventTap, event)
    return 2


def send_paste():
    import Quartz as Q
    return _key(9, Q.kCGEventFlagMaskCommand)  # Command+V, never Enter


def send_submit(mode):
    import Quartz as Q
    if mode not in {'enter', 'ctrl_enter'}:
        raise ValueError('Unknown submit mode')
    return _key(36, Q.kCGEventFlagMaskControl if mode == 'ctrl_enter' else 0)


def require_screen_permission():
    import Quartz as Q
    if not Q.CGPreflightScreenCaptureAccess():
        Q.CGRequestScreenCaptureAccess()
        raise RuntimeError('请允许屏幕录制权限后重试截图')
