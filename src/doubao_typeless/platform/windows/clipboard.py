"""Windows focus/clipboard helpers. Do not treat process name as Composer."""
from __future__ import annotations

import ctypes
import io
import sys
from typing import Callable

if sys.platform == "win32":
    import win32clipboard
    import win32con
    import win32gui
    from PIL import Image

VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002


def read_focus() -> tuple[str, str]:
    if sys.platform != "win32":
        return ("", "")
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    class_name = win32gui.GetClassName(hwnd)
    return class_name, title


def send_paste() -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def read_clipboard_text() -> str | None:
    if sys.platform != "win32":
        return None
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return str(win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT))
        return None
    except Exception:
        return None
    finally:
        win32clipboard.CloseClipboard()


def set_clipboard_text(text: str) -> None:
    if sys.platform != "win32":
        return
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def set_clipboard_png(data: bytes) -> None:
    if sys.platform != "win32":
        return
    image = Image.open(io.BytesIO(data)).convert("RGB")
    with io.BytesIO() as buf:
        image.save(buf, "BMP")
        dib = buf.getvalue()[14:]
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
    finally:
        win32clipboard.CloseClipboard()
