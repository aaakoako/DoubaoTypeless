"""应用图标资源路径：托盘与 Tk/CTk 窗口共用 assets/icon.png。"""
from __future__ import annotations

import sys
from pathlib import Path

from paths import resource_dir

APP_DIR = resource_dir()
ICON_PNG = APP_DIR / "assets" / "icon.png"
ICON_ICO = APP_DIR / "assets" / "icon.ico"


def icon_png_exists() -> bool:
    return ICON_PNG.is_file()


def icon_ico_exists() -> bool:
    return ICON_ICO.is_file()


def _apply_windows_taskbar_identity(root) -> None:
    """Windows：设置 AppUserModelID 与 iconbitmap，改善任务栏显示 python.exe 图标的情况。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "DoubaoTypeless.DoubaoTypeless.App.1"
        )
    except Exception:
        pass
    if not icon_ico_exists():
        return
    try:
        root.iconbitmap(default=str(ICON_ICO))
    except Exception:
        pass


def apply_tk_window_icon(root) -> object | None:
    """在 Tk/CTk 根窗口设置 iconphoto；返回的 PhotoImage 需保存在 root 上防止被回收。"""
    _apply_windows_taskbar_identity(root)
    if not icon_png_exists():
        return None
    import tkinter as tk

    img = tk.PhotoImage(file=str(ICON_PNG))
    root.iconphoto(True, img)
    return img


def load_tray_image():
    """PIL Image RGBA 64x64，供 pystray 使用。"""
    from PIL import Image

    if not icon_png_exists():
        return None
    im = Image.open(ICON_PNG).convert("RGBA")
    if im.size != (64, 64):
        im = im.resize((64, 64), Image.Resampling.LANCZOS)
    return im
