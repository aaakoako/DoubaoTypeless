"""V3 preview autostart. Never writes the daily-use DoubaoTypeless Run value."""
from __future__ import annotations

import sys
from pathlib import Path

V3_RUN_NAME = "DoubaoTypelessV3Preview"


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}" --minimized'
    root = Path(__file__).resolve().parents[3]
    launcher = Path(sys.executable).resolve()
    pythonw = launcher.parent / "pythonw.exe"
    if pythonw.is_file():
        launcher = pythonw
    script = root / "tools" / "run_v3.py"
    return f'"{launcher}" "{script}" --minimized'


def apply_v3_autostart(enabled: bool) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "仅 Windows 支持开机自启"
    try:
        import winreg
    except ImportError:
        return False, "无法加载 winreg"
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
    except OSError as exc:
        return False, str(exc)
    try:
        if enabled:
            winreg.SetValueEx(key, V3_RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, V3_RUN_NAME)
            except FileNotFoundError:
                pass
        return True, ""
    except OSError as exc:
        return False, str(exc)
    finally:
        winreg.CloseKey(key)
