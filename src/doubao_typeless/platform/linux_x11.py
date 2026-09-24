"""X11 input with AT-SPI2 control identity. Native Wayland is not injected into."""
import ctypes as C
import os
import threading
import time
from collections import OrderedDict
from ctypes.util import find_library

from .accessible import input_kind
from .windows.focus import FocusSnapshot, same_target

_lock = threading.RLock()
_api = None


def require_x11():
    if os.environ.get('XDG_SESSION_TYPE') == 'wayland' or not os.environ.get('DISPLAY'):
        raise RuntimeError('自动插入需要 X11 桌面会话')


class Accessibility:
    def __init__(self):
        self.lib = C.CDLL(find_library('atspi') or 'libatspi.so.0')
        self.gobject = C.CDLL(find_library('gobject-2.0'))
        self.glib = C.CDLL(find_library('glib-2.0'))
        self.gobject.g_object_unref.argtypes = [C.c_void_p]
        self.glib.g_free.argtypes = [C.c_void_p]
        self.functions = {}
        signatures = {
            'init': (C.c_int, []),
            'set_timeout': (None, [C.c_int, C.c_int]),
            'get_desktop': (C.c_void_p, [C.c_int]),
            'accessible_get_child_count': (C.c_int, [C.c_void_p, C.c_void_p]),
            'accessible_get_child_at_index': (C.c_void_p, [C.c_void_p, C.c_int, C.c_void_p]),
            'accessible_get_process_id': (C.c_uint, [C.c_void_p, C.c_void_p]),
            'accessible_get_state_set': (C.c_void_p, [C.c_void_p]),
            'accessible_set_cache_mask': (None, [C.c_void_p, C.c_uint]),
            'state_set_contains': (C.c_int, [C.c_void_p, C.c_int]),
            'accessible_get_role_name': (C.c_void_p, [C.c_void_p, C.c_void_p]),
            'accessible_get_name': (C.c_void_p, [C.c_void_p, C.c_void_p]),
            'accessible_get_description': (C.c_void_p, [C.c_void_p, C.c_void_p]),
            'accessible_get_component_iface': (C.c_void_p, [C.c_void_p]),
            'component_grab_focus': (C.c_int, [C.c_void_p, C.c_void_p]),
        }
        for name, (result, args) in signatures.items():
            fn = getattr(self.lib, 'atspi_' + name)
            fn.restype, fn.argtypes = result, args
            self.functions[name] = fn
        if self.fn('init') != 0:
            raise RuntimeError('AT-SPI unavailable')
        self.fn('set_timeout', 150, 300)
        self.saved = OrderedDict()

    def fn(self, name, *args):
        return self.functions[name](*args)

    def unref(self, ptr):
        if ptr:
            self.gobject.g_object_unref(ptr)

    def string(self, name, ptr):
        value = self.fn('accessible_get_' + name, ptr, None)
        try:
            return C.string_at(value).decode('utf-8', errors='replace') if value else ''
        finally:
            if value:
                self.glib.g_free(value)

    def focused(self, pid):
        root = self.fn('get_desktop', 0)
        if not root:
            return None
        todo = []
        found = None
        deadline = time.monotonic() + 1.2
        try:
            for index in range(min(128, self.fn('accessible_get_child_count', root, None))):
                child = self.fn('accessible_get_child_at_index', root, index, None)
                if child and self.fn('accessible_get_process_id', child, None) == pid:
                    todo.append(child)
                else:
                    self.unref(child)
            visited = 0
            while todo and visited < 600 and time.monotonic() < deadline:
                ptr = todo.pop()
                visited += 1
                # No GLib event loop drives cache invalidations in the delivery worker.
                self.fn('accessible_set_cache_mask', ptr, 0)
                states = self.fn('accessible_get_state_set', ptr)
                # AtspiStateType: EDITABLE=7, ENABLED=8, FOCUSED=12.
                focused = states and self.fn('state_set_contains', states, 12)
                editable = states and self.fn('state_set_contains', states, 7) and self.fn('state_set_contains', states, 8)
                self.unref(states)
                if focused:
                    role = self.string('role_name', ptr)
                    description = self.string('name', ptr) + ' ' + self.string('description', ptr)
                    kind = input_kind(role, description, editable=bool(editable))
                    if ptr in self.saved:
                        self.unref(ptr)  # The saved reference already owns it.
                    self.saved[ptr] = pid
                    self.saved.move_to_end(ptr)
                    while len(self.saved) > 64:
                        old, _ = self.saved.popitem(last=False)
                        self.unref(old)
                    found = (ptr, role, kind)
                    break
                count = min(600 - visited - len(todo), self.fn('accessible_get_child_count', ptr, None))
                for index in range(max(0, count)):
                    child = self.fn('accessible_get_child_at_index', ptr, index, None)
                    if child:
                        todo.append(child)
                self.unref(ptr)
        finally:
            self.unref(root)
            for ptr in todo:
                self.unref(ptr)
        return found


def api():
    global _api
    if _api is None:
        _api = Accessibility()
    return _api


def window(display):
    root = display.screen().root
    prop = root.get_full_property(display.intern_atom('_NET_ACTIVE_WINDOW'), 0)
    return display.create_resource_object('window', int(prop.value[0])) if prop is not None and prop.value[0] else None


def read_target():
    require_x11()
    from Xlib.display import Display
    with _lock:
        display = Display()
        try:
            win = window(display)
            if win is None:
                return FocusSnapshot('', '', 0)
            prop = win.get_full_property(display.intern_atom('_NET_WM_PID'), 0)
            pid = int(prop.value[0]) if prop is not None else 0
            if pid == os.getpid():
                return FocusSnapshot('dt-v3-hud', '', win.id, pid)
            focused = api().focused(pid) if pid else None
            after = window(display)
            if after is None or after.id != win.id:
                return FocusSnapshot('', '', 0)
            if not focused:
                return FocusSnapshot('', '', win.id, pid)
            token, role, kind = focused
            return FocusSnapshot(role, '', win.id, pid, token, (pid, token), kind)
        finally:
            display.close()


def restore_target(saved):
    require_x11()
    from Xlib import X, protocol
    from Xlib.display import Display
    if len(saved) < 7 or not saved[5]:
        return False
    with _lock:
        target = api()
        if target.saved.get(saved[4]) != saved[3]:
            return False
        display = Display()
        try:
            event = protocol.event.ClientMessage(window=saved[2], client_type=display.intern_atom('_NET_ACTIVE_WINDOW'),
                                                  data=(32, [2, X.CurrentTime, 0, 0, 0]))
            display.screen().root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
            display.sync()
            component = target.fn('accessible_get_component_iface', saved[4])
            try:
                if not component or not target.fn('component_grab_focus', component, None):
                    return False
            finally:
                target.unref(component)
            for _ in range(8):
                if same_target(saved, read_target()):
                    return True
                time.sleep(.025)
            return False
        finally:
            display.close()


def modifiers_down():
    require_x11()
    from Xlib.display import Display
    display = Display()
    try:
        return bool(display.screen().root.query_pointer().mask & (1 | 4 | 8 | 64))
    finally:
        display.close()


def _key(key, modifier=None):
    require_x11()
    from Xlib import X, XK
    from Xlib.display import Display
    from Xlib.ext.xtest import fake_input
    display = Display()
    held = []
    try:
        for name in ([modifier] if modifier else []) + [key]:
            code = display.keysym_to_keycode(XK.string_to_keysym(name))
            if not code:
                raise RuntimeError('Key is unavailable')
            fake_input(display, X.KeyPress, code)
            held.append(code)
        count = len(held) * 2
        return count
    finally:
        for code in reversed(held):
            fake_input(display, X.KeyRelease, code)
        display.sync()
        display.close()


def send_paste():
    return _key('v', 'Control_L')


def send_submit(mode):
    if mode not in {'enter', 'ctrl_enter'}:
        raise ValueError('Unknown submit mode')
    return _key('Return', 'Control_L' if mode == 'ctrl_enter' else None)
