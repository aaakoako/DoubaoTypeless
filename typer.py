import time
import ctypes
import ctypes.wintypes

import win32gui
import win32con
import win32clipboard


VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002


class Typer:
    """Handles pasting text at the previously focused window via clipboard."""

    def __init__(self, clipboard_protection: bool = True):
        self.clipboard_protection = clipboard_protection
        self._saved_hwnd = None
        self._saved_clipboard = None

    def save_focus(self):
        self._saved_hwnd = win32gui.GetForegroundWindow()

    def _restore_focus(self) -> bool:
        if not self._saved_hwnd:
            return False
        try:
            if not win32gui.IsWindow(self._saved_hwnd):
                return False
            ctypes.windll.user32.SetForegroundWindow(self._saved_hwnd)
            return True
        except Exception:
            return False

    def _save_clipboard(self):
        if not self.clipboard_protection:
            return
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                self._saved_clipboard = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            else:
                self._saved_clipboard = None
            win32clipboard.CloseClipboard()
        except Exception:
            self._saved_clipboard = None

    def _restore_clipboard(self):
        if not self.clipboard_protection:
            return
        try:
            time.sleep(0.05)
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            if self._saved_clipboard is not None:
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, self._saved_clipboard)
            win32clipboard.CloseClipboard()
        except Exception:
            pass

    def _set_clipboard_text(self, text: str):
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        win32clipboard.CloseClipboard()

    def _send_paste(self):
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_V, 0, 0, 0)
        time.sleep(0.02)
        ctypes.windll.user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    def paste_text(self, text: str, *, keep_in_clipboard: bool = False) -> dict:
        result = {
            "attempted": False,
            "focus_restored": False,
            "paste_sent": False,
            "clipboard_kept": keep_in_clipboard,
        }
        if not text:
            return result
        self._save_clipboard()
        try:
            result["attempted"] = True
            self._set_clipboard_text(text)
            if self._restore_focus():
                result["focus_restored"] = True
                time.sleep(0.05)
                self._send_paste()
                result["paste_sent"] = True
        finally:
            if not keep_in_clipboard:
                self._restore_clipboard()
        return result
