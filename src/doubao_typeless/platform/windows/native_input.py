"""一次明确的 Ctrl+V；检查系统接收事件数量，不把发键等同于目标接收。

原子发送完整组合；系统拒绝/只接收部分时不重发粘贴，最多释放本次已按下的键。
不发送 Enter，不提权，不改变目标权限，不更改前台窗口。
"""
from __future__ import annotations

import ctypes
import sys
from typing import Callable
from doubao_typeless.platform.windows.input_activity import INJECTION_MARKER

# Windows ABI 的 LONG/DWORD 始终32位，不能使用 Linux上的 c_long 代替。
DWORD, WORD, LONG = ctypes.c_uint32, ctypes.c_uint16, ctypes.c_int32
ULONG_PTR = ctypes.c_size_t
VK_CONTROL, VK_V, KEYUP = 0x11, 0x56, 0x0002


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD),
                ("dwFlags", DWORD), ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]


class INPUTDATA(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", DWORD), ("data", INPUTDATA)]


class InputInjectionError(OSError):
    def __init__(self, accepted: int, expected: int, winerror: int = 0):
        self.accepted = accepted
        self.expected = expected
        self.error_code = "INPUT_REJECTED" if accepted == 0 else "INPUT_PARTIAL"
        super().__init__(winerror, self.error_code)
        # Windows OSError.__init__ 会初始化 winerror；在其后保存原系统错误号。
        self.winerror = winerror


def _key(vk: int, up: bool = False) -> INPUT:
    value = INPUT()
    value.type = 1  # INPUT_KEYBOARD
    value.data.ki = KEYBDINPUT(vk, 0, KEYUP if up else 0, 0, INJECTION_MARKER)
    return value


def inject_paste(send: Callable, get_error: Callable[[], int] = lambda: 0) -> int:
    """`send` 与 Win32 SendInput 同签名；测试替身可检查真实事件数组。"""
    keys = (INPUT * 4)(_key(VK_CONTROL), _key(VK_V), _key(VK_V, True), _key(VK_CONTROL, True))
    accepted = int(send(4, keys, ctypes.sizeof(INPUT)))
    if accepted == 4:
        return accepted
    error = int(get_error())
    # 只有已知系统接收了前缀时才释放相应键。不重复按下，不再次触发 Ctrl+V。
    # 若调用失败原因不明确，调用者保留 UNKNOWN/原稿，不把清理当成成功。
    releases = []
    if accepted == 2:
        releases.append(_key(VK_V, True))
    if 0 < accepted < 4:
        releases.append(_key(VK_CONTROL, True))
    if releases:
        try:
            send(len(releases), (INPUT * len(releases))(*releases), ctypes.sizeof(INPUT))
        except Exception:
            pass
    raise InputInjectionError(accepted, 4, error)


def send_paste() -> int:
    if sys.platform != "win32":
        raise OSError("WINDOWS_INPUT_UNAVAILABLE")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    send = user32.SendInput
    send.argtypes = [ctypes.c_uint32, ctypes.POINTER(INPUT), ctypes.c_int]
    send.restype = ctypes.c_uint32
    ctypes.set_last_error(0)
    return inject_paste(send, ctypes.get_last_error)


def inject_submit(mode: str, send: Callable, get_error: Callable[[], int] = lambda: 0) -> int:
    """独立的明确发送动作。仅支持白名单两种组合，不接受客户端按键脚本。"""
    if mode not in {"enter", "ctrl_enter"}:
        raise ValueError("INVALID_SEND_MODE")
    vk = 0x0D
    events = ([_key(vk), _key(vk, True)] if mode == "enter" else
              [_key(VK_CONTROL), _key(vk), _key(vk, True), _key(VK_CONTROL, True)])
    size = len(events)
    accepted = int(send(size, (INPUT * size)(*events), ctypes.sizeof(INPUT)))
    if accepted == size:
        return accepted
    error = int(get_error())
    releases = []
    if mode == "enter" and accepted == 1:
        releases = [_key(vk, True)]
    elif mode == "ctrl_enter" and 0 < accepted < size:
        if accepted == 2:
            releases.append(_key(vk, True))
        releases.append(_key(VK_CONTROL, True))
    if releases:
        try:
            send(len(releases), (INPUT * len(releases))(*releases), ctypes.sizeof(INPUT))
        except Exception:
            pass
    raise InputInjectionError(accepted, size, error)


def send_submit(mode: str) -> int:
    if sys.platform != "win32":
        raise OSError("WINDOWS_INPUT_UNAVAILABLE")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    send = user32.SendInput
    send.argtypes = [ctypes.c_uint32, ctypes.POINTER(INPUT), ctypes.c_int]
    send.restype = ctypes.c_uint32
    ctypes.set_last_error(0)
    return inject_submit(mode, send, ctypes.get_last_error)
