"""V3 preview autostart. Never writes the daily-use DoubaoTypeless Run value."""
from __future__ import annotations

import sys
import subprocess
from pathlib import Path

V3_RUN_NAME = "DoubaoTypelessV3Preview"
DAILY_RUN_NAME = "DoubaoTypeless"


def startup_command(*, data_dir: Path | None = None) -> str:
    from doubao_typeless.runtime import v3_data_dir
    from doubao_typeless.ui.single_instance import pipe_name
    if getattr(sys, "frozen", False):
        args = [str(Path(sys.executable).resolve())]
    else:
        root = Path(__file__).resolve().parents[3]
        launcher = Path(sys.executable).resolve()
        pythonw = launcher.parent / "pythonw.exe"
        if pythonw.is_file():
            launcher = pythonw
        args = [str(launcher), str(root / "tools" / "run_v3.py")]
    args += ["--minimized", "--data-dir", str((data_dir or v3_data_dir()).resolve()), "--instance-name", pipe_name()]
    return subprocess.list2cmdline(args)


def apply_v3_autostart(enabled: bool, *, data_dir: Path | None = None) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "仅 Windows 支持开机自启"
    try:
        import winreg
    except ImportError:
        return False, "无法加载 winreg"
    if V3_RUN_NAME == DAILY_RUN_NAME:
        return False, "拒绝写入日用自启动项"
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
    except OSError as exc:
        return False, str(exc)
    try:
        if enabled:
            winreg.SetValueEx(key, V3_RUN_NAME, 0, winreg.REG_SZ, startup_command(data_dir=data_dir))
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
