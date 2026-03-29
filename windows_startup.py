"""Windows 当前用户「登录时启动」注册表项（HKCU Run）。"""
from __future__ import annotations

import sys
from pathlib import Path

_RUN_VALUE_NAME = "DoubaoTypeless"


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    main_py = Path(__file__).resolve().parent / "main.py"
    py = Path(sys.executable).resolve()
    pythonw = py.parent / "pythonw.exe"
    launcher = pythonw if pythonw.is_file() else py
    return f'"{launcher}" "{main_py}"'


def apply_start_with_windows(enabled: bool) -> tuple[bool, str]:
    """写入或删除注册表；返回 (是否成功, 错误说明)。"""
    if sys.platform != "win32":
        return False, "仅 Windows 支持开机自启"
    try:
        import winreg
    except ImportError:
        return False, "无法加载 winreg"

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            winreg.KEY_SET_VALUE,
        )
    except OSError as e:
        return False, str(e)

    try:
        if enabled:
            winreg.SetValueEx(
                key,
                _RUN_VALUE_NAME,
                0,
                winreg.REG_SZ,
                _startup_command(),
            )
        else:
            try:
                winreg.DeleteValue(key, _RUN_VALUE_NAME)
            except FileNotFoundError:
                pass
        return True, ""
    except OSError as e:
        return False, str(e)
    finally:
        winreg.CloseKey(key)
