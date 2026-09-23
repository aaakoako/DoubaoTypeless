"""S1 evidence: production page -> real bridge -> native HUD -> real Windows text box.

Not Cursor. Not the design prototype. Isolated data dir only.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import ctypes
import win32gui
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doubao_typeless.app import V3App

EVIDENCE = ROOT / "docs" / "evidence" / "v3-s1"
TARGET_TITLE = "DT-S1-TextTarget"
SAMPLE = "第一段原文仍保留回改\n第二段还在当前稿"


def log(msg: str) -> None:
    print(msg, flush=True)


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


def foreground() -> tuple[str, str]:
    hwnd = win32gui.GetForegroundWindow()
    return win32gui.GetClassName(hwnd), win32gui.GetWindowText(hwnd)


def screenshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab().save(path)


def read_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


async def drive(app: V3App, state_path: Path, out: dict) -> None:
    from playwright.async_api import async_playwright

    code = app.auth.current_pairing_challenge() or app.auth.new_pairing_challenge()
    port = app.bridge.port or app.port
    posts: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.on(
            "request",
            lambda req: posts.append(req.post_data or "")
            if req.method == "POST" and req.url.endswith("/v3/pair")
            else None,
        )
        await page.goto(f"http://127.0.0.1:{port}/")
        await page.wait_for_selector("#pairCode", state="visible")
        await page.fill("#pairCode", code)
        async with page.expect_response(lambda r: r.url.endswith("/v3/pair") and r.request.method == "POST") as info:
            await page.click("#pairGo")
        assert (await info.value).ok
        await page.wait_for_function("() => !document.getElementById('sheet').classList.contains('show')")
        await page.fill("#text", SAMPLE)
        await page.locator("#text").dispatch_event("input")
        for _ in range(50):
            if SAMPLE in app.draft.text:
                break
            await asyncio.sleep(0.05)
        await browser.close()
    out["pair_posts"] = posts
    out["draft_text"] = app.draft.text
    out["hud_visible_flag"] = app.hud.visible
    out["hud_titles"] = titles_matching("DT-V3-HUD")
    out["focus_after_sync"] = foreground()
    hwnd = find_hwnd(TARGET_TITLE)
    out["target_focused"] = focus_hwnd(hwnd)
    time.sleep(0.2)
    out["focus_before_insert"] = foreground()
    app.insert_last()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        observed = str(read_state(state_path).get("text") or "")
        if SAMPLE in observed:
            break
        time.sleep(0.05)
    out["target_state"] = read_state(state_path)
    out["enter_count"] = app.delivery.enter_count
    out["attempt"] = None if app._last_attempt is None else app._last_attempt.to_dict()


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    iso = Path(os.environ.get("DT_V3_S1_DIR") or r"G:\AgentStorage\Temp\User\dt-v3-s1")
    iso.mkdir(parents=True, exist_ok=True)
    state_path = iso / "target.json"
    os.environ["DT_V3_DATA_DIR"] = str(iso / "data")
    target = subprocess.Popen([sys.executable, str(ROOT / "tools" / "v3_s1_text_target.py"), str(state_path)])
    time.sleep(0.8)
    screenshot(EVIDENCE / "01-target-idle.png")
    app = V3App(data_dir=iso / "data", port=0)
    app.hud.start()
    out: dict = {}
    error: str | None = None

    def worker() -> None:
        nonlocal error
        try:
            app.start_background(start_hud=False)
            screenshot(EVIDENCE / "02-after-app-idle.png")
            asyncio.run(drive(app, state_path, out))
            screenshot(EVIDENCE / "03-after-insert.png")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            log(error)
        finally:
            try:
                from PySide6.QtCore import QTimer

                if app.hud._app is not None:
                    QTimer.singleShot(0, app.hud._app, app.hud._app.quit)
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()
    if app.hud._app is not None:
        app.hud._app.exec()
    else:
        time.sleep(8)
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
        "hud_shown": bool(out.get("hud_titles")) or bool(out.get("hud_visible_flag")),
        "target_has_text": SAMPLE in str((out.get("target_state") or {}).get("text") or ""),
        "zero_enter": out.get("enter_count") == 0,
        "hud_not_foreground": "DT-V3-HUD" not in str((out.get("focus_after_sync") or ("", ""))[1]),
        "not_cursor": True,
    }
    result["ok"] = error is None and all(result["gates"].values())
    (EVIDENCE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(json.dumps({"ok": result["ok"], "gates": result["gates"], "error": error}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
