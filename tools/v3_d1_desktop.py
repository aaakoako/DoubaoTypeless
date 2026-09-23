"""Grab native Qt windows from a live V3App. Not an HTML prototype."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EVIDENCE = ROOT / "docs" / "evidence" / "v3-d1"


def _shot(widget, name: str) -> str:
    from PySide6.QtGui import QGuiApplication

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / f"{name}.png"
    pix = widget.grab()
    if pix.isNull():
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            pix = screen.grabWindow(int(widget.winId()))
    pix.save(str(path), "PNG")
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    from PySide6.QtWidgets import QApplication

    from doubao_typeless.app import V3App
    from doubao_typeless.ui.desktop import ClientWindow, RecoveryDialog, ReviewPanel, apply_ui_font
    from doubao_typeless.ui.filelog import FileLogger

    iso = Path(os.environ.get("DT_V3_D1_DIR") or r"G:\AgentStorage\Temp\User\dt-v3-d1")
    data = iso / "data"
    data.mkdir(parents=True, exist_ok=True)
    qt = QApplication.instance() or QApplication([])
    qt.setQuitOnLastWindowClosed(False)
    apply_ui_font(qt)
    log = FileLogger(data / "logs" / "v3.log", also_print=True)
    from doubao_typeless.app import set_log

    set_log(log)
    app = V3App(data_dir=data, port=0)
    app.start_background(start_hud=True)
    shots = {}
    try:
        win = ClientWindow(app)
        win.show_window()
        qt.processEvents()
        time.sleep(0.3)
        qt.processEvents()
        shots["welcome"] = _shot(win.widget, "01-welcome")
        shots["settings"] = None
        win.tabs.setCurrentIndex(1)
        qt.processEvents()
        shots["settings"] = _shot(win.widget, "02-settings")
        win.tabs.setCurrentIndex(2)
        qt.processEvents()
        shots["recent"] = _shot(win.widget, "03-recent")
        panel = ReviewPanel(app)
        panel.show()
        panel.editor.setPlainText("电脑可编辑详情")
        qt.processEvents()
        shots["review"] = _shot(panel.widget, "04-review")
        dlg = RecoveryDialog(win.widget)
        dlg._dlg.show()
        qt.processEvents()
        shots["recovery"] = _shot(dlg._dlg, "05-recovery")
        dlg._dlg.hide()
        win.hide_to_tray()
        qt.processEvents()
        shots["closed_visible"] = win.widget.isVisible()
        status = None
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{app.port}/v3/status", timeout=3) as resp:
            status = json.loads(resp.read().decode("utf-8"))
        payload = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "port": app.port,
            "url": win.phone_url(),
            "pairing_code_shown": "配对码" in win.code_label.text(),
            "qr_non_null": bool(win.qr.pixmap() and not win.qr.pixmap().isNull()),
            "status_protocol": (status or {}).get("protocol"),
            "closed_to_tray": shots["closed_visible"] is False,
            "shots": {k: v for k, v in shots.items() if k != "closed_visible"},
            "console_false_only": False,
            "uses_pc_html": False,
            "engineering_preview": True,
            "desktop_complete": False,
        }
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "port": app.port, "shots": payload["shots"]}, ensure_ascii=False))
        return 0
    finally:
        import asyncio

        loop = getattr(app, "_loop", None)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(app.stop(), loop).result(5)


if __name__ == "__main__":
    raise SystemExit(main())
