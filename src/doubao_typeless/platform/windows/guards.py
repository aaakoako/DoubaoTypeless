"""Delivery-time guards: lock screen, elevation, modifiers, clipboard races."""
from __future__ import annotations

import ctypes
import sys
import time
from typing import Callable

VK_MENU = 0x12
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_LWIN = 0x5B
VK_RWIN = 0x5C


def key_down(vk: int, *, get_async: Callable[[int], int] | None = None) -> bool:
    if get_async is None:
        if sys.platform != "win32":
            return False
        get_async = lambda code: ctypes.windll.user32.GetAsyncKeyState(code)
    return bool(get_async(vk) & 0x8000)


def wait_modifiers_up(*, timeout_s: float = 1.5, now: Callable[[], float] | None = None, get_async=None) -> bool:
    clock = now or time.monotonic
    deadline = clock() + timeout_s
    while clock() < deadline:
        if not any(key_down(vk, get_async=get_async) for vk in (VK_MENU, VK_CONTROL, VK_SHIFT, VK_LWIN, VK_RWIN)):
            return True
        time.sleep(0.02)
    return False


def session_locked(*, query=None) -> bool:
    if query is not None:
        return bool(query())
    try:
        import ctypes.wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        return hwnd == 0
    except Exception:
        return False


def target_elevated(*, ours: bool = False, theirs: bool = False) -> bool:
    return bool(theirs) and not bool(ours)


def clipboard_still_ours(expected: str, actual: str | None) -> bool:
    if actual is None:
        return False
    return actual == expected
