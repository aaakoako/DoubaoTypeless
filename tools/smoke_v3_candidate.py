"""离屏启动候选 EXE，禁用有效热键，仅检查 HTTP 服务和 IPC 正常退出。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from urllib.request import urlopen
from urllib.parse import urlparse


def run(exe: Path, data: Path, *, existing_data: bool = False) -> dict:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtNetwork import QLocalSocket
    qt = QCoreApplication.instance() or QCoreApplication([])
    data.mkdir(parents=True, exist_ok=existing_data)
    settings = {name: "<smoke-disabled>" for name in ("hotkey_insert", "hotkey_recall", "hotkey_expand", "hotkey_capture")}
    if existing_data:
        configured = json.loads((data / 'settings.json').read_text(encoding='utf-8'))
        if any(configured.get(k) != v for k,v in settings.items()):
            raise ValueError('Existing test data must already disable native hotkeys')
    else:
        (data / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    pipe = "TypelessSmoke-" + uuid.uuid4().hex
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "DT_V3_DATA_DIR": str(data), "DT_V3_PIPE": pipe}
    # Bootloader errors can show native dialogs before Qt loads. Isolate those
    # too; never switch the user's active desktop.
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.CreateDesktopW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p,
                                     ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    user32.CreateDesktopW.restype = ctypes.c_void_p
    user32.CloseDesktop.argtypes = [ctypes.c_void_p]
    desktop_name = "TypelessSmoke" + uuid.uuid4().hex
    desktop = user32.CreateDesktopW(desktop_name, None, None, 0, 0x10000000, None)
    if not desktop:
        raise ctypes.WinError(ctypes.get_last_error())
    startup = subprocess.STARTUPINFO()
    startup.lpDesktop = desktop_name
    try:
        child = subprocess.Popen([str(exe.resolve()), "--minimized"], env=env, startupinfo=startup,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        user32.CloseDesktop(desktop)
        raise
    result = {"pid": child.pid, "http": False, "ipc_quit": False, "forced_stop": False,
              "real_input_tested": False, "mode": "offscreen; invalid hotkeys; isolated data and IPC"}
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and child.poll() is None:
            qt.processEvents()
            note = data / "pair.txt"
            if note.is_file():
                port = urlparse(note.read_text(encoding="utf-8").splitlines()[0]).port
                with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                    result["http"] = response.status == 200
                sock = QLocalSocket()
                sock.connectToServer(pipe)
                if sock.waitForConnected(250):
                    sock.write(b"quit\n")
                    sock.waitForBytesWritten(1000)
                    sock.waitForReadyRead(1500)
                    try:
                        result["ipc_quit"] = json.loads(bytes(sock.readAll())) .get("accepted") == "quit"
                    except (ValueError, TypeError):
                        result["ipc_quit"] = False
                    sock.disconnectFromServer()
                    sock.close()
                    break
                sock.close()
            time.sleep(0.1)
        try:
            result["exit_code"] = child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            result["forced_stop"] = True
            child.terminate()  # Only the child we created, never an existing preview.
            result["exit_code"] = child.wait(timeout=5)
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
        user32.CloseDesktop(desktop)
        runtime = data / "logs" / "runtime.log"
        events = []
        if runtime.is_file():
            for line in runtime.read_text(encoding="utf-8").splitlines():
                try: events.append(json.loads(line[line.index("{"):]))
                except (ValueError, TypeError): pass
        result["normal_exit_logged"] = any(e.get("event") == "process_exit" and e.get("exit_code") == 0 for e in events)
        process = data / "logs" / "process.json"
        if process.is_file():
            result["process"] = json.loads(process.read_text(encoding="utf-8"))
        bootstrap = data / "logs" / "bootstrap-error.json"
        if bootstrap.is_file():
            result["bootstrap_error"] = json.loads(bootstrap.read_text(encoding="utf-8"))
    result["passed"] = bool(result["http"] and result["ipc_quit"] and result.get("exit_code") == 0
                            and not result["forced_stop"] and result.get("normal_exit_logged"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    parser.add_argument("data", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    result = run(args.exe, args.data)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)
