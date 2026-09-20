"""Windows 原生全局快捷键；只接收已注册组合，不监听用户的其他按键。

注册/注销与 WM_HOTKEY 消息循环在同一线程；MOD_NOREPEAT 防止长按重复。
回调仅提交现有命令队列或 GUI 信号。注册失败不偷偷回退到低级键盘钩子。
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import threading
from typing import Callable

MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MODIFIERS = {"alt": 1, "alt_l": 1, "alt_r": 1,
              "ctrl": 2, "ctrl_l": 2, "ctrl_r": 2,
              "shift": 4, "shift_l": 4, "shift_r": 4,
              "cmd": 8, "cmd_l": 8, "cmd_r": 8, "win": 8}
_KEYS = {"space": 0x20, "tab": 0x09, "enter": 0x0D,
         "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
         "home": 0x24, "end": 0x23, "page_up": 0x21, "page_down": 0x22,
         "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28}


@dataclass(frozen=True)
class Combination:
    modifiers: int
    vk: int


def parse_combination(text: str) -> Combination:
    """解析原配置语法。无修饰键/重复主键/不支持组合明确报错，不猜测。"""
    parts = [p.strip().lower() for p in text.split("+")]
    modifiers = 0
    keys = []
    for part in parts:
        token = part[1:-1] if part.startswith("<") and part.endswith(">") else part
        if not token:
            raise ValueError("快捷键不能为空")
        if token in _MODIFIERS:
            modifiers |= _MODIFIERS[token]
        elif len(token) == 1 and token.isascii() and token.isalnum():
            keys.append(ord(token.upper()))
        elif token in _KEYS:
            keys.append(_KEYS[token])
        elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", token):
            number = int(token[1:])
            if number == 12:
                raise ValueError("F12 被 Windows 调试器保留，请换一个组合")
            keys.append(0x70 + number - 1)
        else:
            raise ValueError("快捷键包含不支持的按键；请使用字母、数字或功能键")
    if not modifiers or len(keys) != 1:
        raise ValueError("快捷键需要修饰键和一个主键，例如 <alt>+i")
    return Combination(modifiers, keys[0])


class Win32Backend:
    """ctypes Windows API；在纯 Python 测试中以明确的消息队列替身替换。"""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.c = ctypes
        self.msg = wintypes.MSG()
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.api.RegisterHotKey.restype = wintypes.BOOL
        self.api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.UnregisterHotKey.restype = wintypes.BOOL
        self.api.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self.api.GetMessageW.restype = ctypes.c_int
        self.api.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        self.api.PeekMessageW.restype = wintypes.BOOL
        self.api.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.api.PostThreadMessageW.restype = wintypes.BOOL
        self.kernel.GetCurrentThreadId.restype = wintypes.DWORD

    def open(self) -> int:
        self.api.PeekMessageW(self.c.byref(self.msg), None, 0x400, 0x400, 0)
        return int(self.kernel.GetCurrentThreadId())

    def register(self, ident: int, combination: Combination) -> int:
        ok = self.api.RegisterHotKey(None, ident, combination.modifiers | MOD_NOREPEAT, combination.vk)
        return 0 if ok else int(self.c.get_last_error() or 1)

    def unregister(self, ident: int) -> None:
        self.api.UnregisterHotKey(None, ident)

    def receive(self) -> int | None:
        while True:
            result = self.api.GetMessageW(self.c.byref(self.msg), None, 0, 0)
            if result == 0:
                return None
            if result == -1:
                raise OSError(self.c.get_last_error(), "GetMessageW failed")
            if self.msg.message == WM_HOTKEY:
                return int(self.msg.wParam)

    def wake_stop(self, thread_id: int) -> None:
        self.api.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)


def _log(event: str, **fields) -> None:
    try:
        from doubao_typeless.app import _log as app_log
        safe = " ".join(f"{key}={value}" for key, value in fields.items())
        app_log(f"[v3.hotkey] {event} {safe}")
    except Exception:
        pass


class NativeHotkeys:
    def __init__(self, bindings: list[tuple[str, Callable]], *, backend_factory=Win32Backend):
        self.failures: list[str] = []
        self.registered: list[str] = []
        self._bindings = bindings
        self._backend_factory = backend_factory
        self._backend = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name="DT-Windows-hotkeys", daemon=True)

    def start(self, timeout: float = 3.0) -> "NativeHotkeys":
        self._thread.start()
        if not self._ready.wait(timeout):
            self.failures.append("Windows 快捷键注册超时，请查看诊断")
            self.stop()
        return self

    def _run(self) -> None:
        registered: dict[int, Callable] = {}
        try:
            backend = self._backend_factory()
            self._backend = backend
            self._thread_id = backend.open()
            seen = set()
            for index, (combo, callback) in enumerate(self._bindings):
                if self._stopping.is_set():
                    break
                ident = 0x5100 + index  # 应用私有范围，低于 0xBFFF。
                try:
                    parsed = parse_combination(combo)
                    if parsed in seen:
                        raise ValueError("两个动作使用了相同快捷键")
                    seen.add(parsed)
                    error = backend.register(ident, parsed)
                    if error:
                        self.failures.append(f"快捷键 {combo} 注册失败（Windows {error}），请修改组合")
                        _log("registration_failed", action=index, error=error)
                    else:
                        registered[ident] = callback
                        self.registered.append(combo)
                except ValueError as exc:
                    self.failures.append(str(exc))
            _log("ready", registered=len(registered), failed=len(self.failures))
            self._ready.set()
            while registered and not self._stopping.is_set():
                ident = backend.receive()
                if ident is None or self._stopping.is_set():
                    break
                callback = registered.get(ident)
                if callback is not None:
                    _log("dispatch", action=ident - 0x5100)
                    try:
                        callback()
                    except Exception as exc:
                        from doubao_typeless.runtime_diagnostics import record_runtime_exception
                        record_runtime_exception("native_hotkey_dispatch", exc)
        except Exception as exc:
            self.failures.append(f"快捷键服务未就绪：{type(exc).__name__}")
            _log("failed", exception_type=type(exc).__name__)
        finally:
            if self._backend is not None:
                for ident in registered:
                    try:
                        self._backend.unregister(ident)
                    except Exception:
                        pass
            self._ready.set()
            _log("stopped", registered=len(registered))

    def stop(self, timeout: float = 2.0) -> None:
        self._stopping.set()
        if self._backend is not None and self._thread_id:
            self._backend.wake_stop(self._thread_id)
        if self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout)


def start_native_hotkeys(*, on_insert, on_recall, on_expand=None, on_region=None,
                         insert_combo="<alt>+i", recall_combo="<alt>+<shift>+i",
                         expand_combo="<alt>+<shift>+e", capture_combo="<alt>+<shift>+s"):
    bindings = [(insert_combo or "<alt>+i", on_insert),
                (recall_combo or "<alt>+<shift>+i", on_recall)]
    if on_expand:
        bindings.append((expand_combo or "<alt>+<shift>+e", on_expand))
    if on_region:
        bindings.append((capture_combo or "<alt>+<shift>+s", on_region))
    service = NativeHotkeys(bindings).start()
    return {"listener": service, "release": None, "failures": list(service.failures),
            "registered": list(service.registered), "backend": "RegisterHotKey", "esc_bound": False}
