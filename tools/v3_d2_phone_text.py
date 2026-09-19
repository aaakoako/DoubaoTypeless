"""Production phone page -> live V3App -> desktop review/grants -> specified text target.

Not Cursor. Not the HTML prototype. Isolated data dir only.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ctypes
import win32gui

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doubao_typeless.app import V3App
from doubao_typeless.storage.settings_store import load_settings
from doubao_typeless.ui.desktop import ClientWindow, ReviewPanel, apply_ui_font

EVIDENCE = ROOT / "docs" / "evidence" / "v3-d2"
TARGET_TITLE = "DT-S1-TextTarget"
SAMPLE = "桌面批准后的正式前端文字\n第二行仍是当前稿"


def titles_matching(part: str) -> list[str]:
    found: list[str] = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if part in title:
                found.append(title)
        return True

    win32gui.EnumWindows(cb, None)
    return found


def find_hwnd(title: str):
    found = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == title:
            found.append(hwnd)
        return True

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def focus_hwnd(hwnd) -> bool:
    if not hwnd:
        return False
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    ctypes.windll.user32.SetCursorPos((left + right) // 2, (top + bottom) // 2)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.2)
    return True


def read_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


async def drive(app: V3App, win: ClientWindow, panel: ReviewPanel, state_path: Path, out: dict) -> None:
    from playwright.async_api import async_playwright

    code = app.auth.current_pairing_challenge() or app.auth.new_pairing_challenge()
    port = app.bridge.port or app.port
    posts: list[str] = []
    drafts: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.on(
            "request",
            lambda req: posts.append(req.post_data or "")
            if req.method == "POST" and req.url.endswith("/v3/pair")
            else None,
        )
        page.on(
            "request",
            lambda req: drafts.append(req.post_data or "")
            if req.method == "POST" and "/ws" not in req.url and "draft" in (req.post_data or "")
            else None,
        )
        await page.goto(f"http://127.0.0.1:{port}/")
        await page.wait_for_selector("#pairCode", state="visible")
        await page.fill("#pairCode", code)
        async with page.expect_response(lambda r: r.url.endswith("/v3/pair") and r.request.method == "POST") as info:
            await page.click("#pairGo")
        assert (await info.value).ok
        await page.wait_for_function("() => !document.getElementById('sheet').classList.contains('show')")
        sessions = app.auth.public_sessions()
        assert sessions, "production pair must create a session"
        sid = sessions[0]["session_id"]
        win.set_insert(sid, True)
        out["desktop_grant_insert"] = app.auth.sessions[sid].allow_insert
        await page.fill("#text", SAMPLE)
        await page.locator("#text").dispatch_event("input")
        for _ in range(80):
            if SAMPLE in app.draft.text:
                break
            await asyncio.sleep(0.05)
        win.refresh()
        panel.reload()
        out["review_text"] = panel.editor.toPlainText()
        out["window_url"] = win.phone_url()
        ws_msgs = []
        page.on("websocket", lambda ws: ws.on("framereceived", lambda payload: ws_msgs.append(str(payload))))
        await browser.close()
    out["pair_posts"] = posts
    out["draft_text"] = app.draft.text
    out["ws_seen"] = bool(ws_msgs)
    hwnd = find_hwnd(TARGET_TITLE)
    out["target_focused"] = focus_hwnd(hwnd)
    time.sleep(0.2)
    app.insert_last()
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        if SAMPLE in str(read_state(state_path).get("text") or ""):
            break
        time.sleep(0.05)
    out["target_state"] = read_state(state_path)
    out["enter_count"] = app.delivery.enter_count
    out["attempt"] = None if app._last_attempt is None else app._last_attempt.to_dict()
    win.hotkey_insert.setText("<alt>+i")
    win.byok_endpoint.setText("")
    win.save_settings()
    out["settings_saved"] = load_settings(app.data_dir)["hotkey_insert"] == "<alt>+i"


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    iso = Path(os.environ.get("DT_V3_D2_DIR") or r"G:\AgentStorage\Temp\User\dt-v3-d2")
    iso.mkdir(parents=True, exist_ok=True)
    state_path = iso / "target.json"
    os.environ["DT_V3_DATA_DIR"] = str(iso / "data")
    target = subprocess.Popen([sys.executable, str(ROOT / "tools" / "v3_s1_text_target.py"), str(state_path)])
    time.sleep(0.8)
    from PySide6.QtWidgets import QApplication

    qt = QApplication.instance() or QApplication([])
    apply_ui_font(qt)
    qt.setQuitOnLastWindowClosed(False)
    app = V3App(data_dir=iso / "data", port=0)
    app.hud.start()
    win = ClientWindow(app)
    panel = ReviewPanel(app)
    out: dict = {}
    error: str | None = None
    try:
        app.start_background(start_hud=False)
        win.show_window()
        qt.processEvents()
        asyncio.run(drive(app, win, panel, state_path, out))
        qt.processEvents()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            loop = getattr(app, "_loop", None)
            if loop is not None:
                asyncio.run_coroutine_threadsafe(app.stop(), loop).result(5)
        except Exception:
            pass
        target.terminate()
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "sample": SAMPLE,
        "error": error,
        "cursor_claimed": False,
        "android_claimed": False,
        "prototype_used": False,
        **out,
    }
    result["gates"] = {
        "production_frontend_text": SAMPLE in str(out.get("draft_text") or ""),
        "pair_only_code": bool(out.get("pair_posts"))
        and all("allow_insert" not in (p or "") for p in out.get("pair_posts") or []),
        "desktop_grant": bool(out.get("desktop_grant_insert")),
        "review_has_text": SAMPLE in str(out.get("review_text") or ""),
        "target_has_text": SAMPLE in str((out.get("target_state") or {}).get("text") or ""),
        "zero_enter": out.get("enter_count") == 0,
        "settings_saved": bool(out.get("settings_saved")),
        "not_cursor": True,
    }
    result["ok"] = error is None and all(result["gates"].values())
    (EVIDENCE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "gates": result["gates"], "error": error}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
