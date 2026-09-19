"""S3 evidence: two photos + whiteboard, reorder, recall keeps current draft, restart bytes.

Specified target DT-S2-PasteTarget. Not Cursor. Isolated data dir only.
"""
from __future__ import annotations

import asyncio
import hashlib
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
from PIL import Image, ImageDraw, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doubao_typeless.app import V3App
from doubao_typeless.storage.draft_snapshot import load_draft

EVIDENCE = ROOT / "docs" / "evidence" / "v3-s3"
TARGET_TITLE = "DT-S2-PasteTarget"
SAMPLE_A = "两图加白板，编号跟顺序走"
SAMPLE_B = "这是当前稿B，召回不得吞掉"


def log(msg: str) -> None:
    print(msg, flush=True)


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


def make_block(path: Path, color: tuple[int, int, int], label: str) -> Path:
    image = Image.new("RGB", (160, 120), color)
    ImageDraw.Draw(image).text((12, 48), label, fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return path


async def pair_and_ready(page, app: V3App, posts: list[str]) -> None:
    code = app.auth.current_pairing_challenge() or app.auth.new_pairing_challenge()
    port = app.bridge.port or app.port
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


async def upload_file(page, path: Path, number_at=(40, 40)) -> dict:
    await page.set_input_files("#file", str(path))
    await page.wait_for_selector("#editor.show")
    await page.wait_for_function("() => document.getElementById('stage')?.dataset.ready === '1'")
    edited = await page.evaluate(
        """([x, y]) => {
          const ed = document.getElementById('stage').__dtEditor;
          ed.stampNumber(x, y);
          return {ops: ed.ops, undo: ed.undoDepth};
        }""",
        number_at,
    )
    async with page.expect_response(lambda r: r.url.endswith("/complete") and r.request.method == "POST") as done:
        await page.click("#done")
    meta = await (await done.value).json()
    await page.wait_for_function("() => !document.getElementById('editor').classList.contains('show')")
    return {"editor": edited, "meta": meta}


async def drive(app: V3App, state_path: Path, red: Path, blue: Path, out: dict) -> None:
    from playwright.async_api import async_playwright

    posts: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await pair_and_ready(page, app, posts)
        out["red"] = await upload_file(page, red, (30, 30))
        out["blue"] = await upload_file(page, blue, (50, 40))
        out["caption_before"] = await page.locator("#captionHint").inner_text()
        await page.locator(".attach-card .right").first.click()
        await asyncio.sleep(0.1)
        out["caption_after"] = await page.locator("#captionHint").inner_text()
        await page.click("#boardBtn")
        await page.wait_for_selector("#editor.show")
        await page.click("#done")
        out["empty_board_blocked"] = await page.evaluate("() => document.getElementById('editor').classList.contains('show')")
        out["empty_toast"] = await page.locator("#sync").inner_text()
        board = await page.evaluate(
            """() => {
              const ed = document.getElementById('stage').__dtEditor;
              ed.addBlankBoard(320, 200);
              ed.addStroke([20, 20, 80, 40]);
              ed.addStroke([30, 60, 90, 90]);
              ed.addStroke([40, 120, 120, 80]);
              const after3 = {ops: ed.ops, undo: ed.undoDepth, redo: ed.redoDepth, grids: ed.imageLayer.find('.grid').length};
              ed.undo();
              const undid = {ops: ed.ops, undo: ed.undoDepth, redo: ed.redoDepth};
              ed.redo();
              ed.addWireframe();
              ed.renameWireTitle('登录按钮');
              ed.moveNode('wire', 8, 4);
              const ready = {ops: ed.ops, undo: ed.undoDepth, redo: ed.redoDepth, moved: true};
              return {after3, undid, ready, redoClearsOnNew: false};
            }"""
        )
        out["board"] = board
        new_stroke_redo = await page.evaluate(
            """() => {
              const ed = document.getElementById('stage').__dtEditor;
              ed.addStroke([10, 10, 12, 12]);
              return {redo: ed.redoDepth, undo: ed.undoDepth};
            }"""
        )
        out["new_stroke_clears_redo"] = new_stroke_redo["redo"] == 0
        async with page.expect_response(lambda r: r.url.endswith("/complete") and r.request.method == "POST") as done:
            await page.click("#done")
        out["board_meta"] = await (await done.value).json()
        await page.wait_for_function("() => !document.getElementById('editor').classList.contains('show')")
        await page.locator(".attach-card img").last.click()
        await page.wait_for_selector("#editor.show")
        out["reedit"] = await page.evaluate(
            """() => {
              const ed = document.getElementById('stage').__dtEditor;
              const before = ed.ops;
              ed.addStroke([15, 15, 40, 50]);
              return {before, after: ed.ops};
            }"""
        )
        async with page.expect_response(lambda r: r.url.endswith("/complete") and r.request.method == "POST") as done2:
            await page.click("#done")
        await (await done2.value).json()
        await page.wait_for_function("() => !document.getElementById('editor').classList.contains('show')")
        await page.fill("#text", SAMPLE_A)
        await page.locator("#text").dispatch_event("input")
        for _ in range(80):
            if SAMPLE_A in app.draft.text and len(app.draft.assets) >= 3:
                break
            await asyncio.sleep(0.05)
        await page.click("#sendBtn")
        for _ in range(40):
            if app.bridge.last_bundle is not None:
                break
            await asyncio.sleep(0.05)
        out["bundle_order"] = [a.get("role") or a.get("asset_id") for a in (app.bridge.last_bundle or {}).get("assets") or []]
        out["draft_ids"] = [a.get("asset_id") for a in app.draft.assets]
        hwnd = find_hwnd(TARGET_TITLE)
        out["target_focused"] = focus_hwnd(hwnd)
        app.insert_last()
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            observed = read_state(state_path)
            kinds = [e.get("kind") for e in observed.get("events") or []]
            if kinds[:3] == ["image", "image", "image"] and SAMPLE_A in str(observed.get("text") or ""):
                break
            time.sleep(0.05)
        out["after_insert"] = read_state(state_path)
        await page.fill("#text", SAMPLE_B)
        await page.locator("#text").dispatch_event("input")
        for _ in range(40):
            if SAMPLE_B in app.draft.text:
                break
            await asyncio.sleep(0.05)
        kept_before = app.draft.text
        await page.click("#historyBtn")
        await page.click("#recallLast")
        await asyncio.sleep(0.2)
        out["page_text_after_recall"] = await page.locator("#text").input_value()
        out["draft_after_recall"] = app.draft.text
        out["last_bundle_after_recall"] = (app.bridge.last_bundle or {}).get("text")
        out["current_kept"] = app.draft.text == kept_before == SAMPLE_B
        out["pair_posts"] = posts
        await browser.close()
    out["enter_count"] = app.delivery.enter_count
    out["attempt"] = None if app._last_attempt is None else app._last_attempt.to_dict()


def dominant_rgb(path: str) -> tuple[int, int, int]:
    image = Image.open(path).convert("RGB")
    pixels = list(image.getdata())
    sample = pixels[:: max(1, len(pixels) // 200)]
    r = sum(p[0] for p in sample) // max(1, len(sample))
    g = sum(p[1] for p in sample) // max(1, len(sample))
    b = sum(p[2] for p in sample) // max(1, len(sample))
    return r, g, b


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    iso = Path(os.environ.get("DT_V3_S3_DIR") or r"G:\AgentStorage\Temp\User\dt-v3-s3")
    iso.mkdir(parents=True, exist_ok=True)
    os.environ["DT_V3_DATA_DIR"] = str(iso / "data")
    os.environ["DT_V3_TARGET_STATE"] = str(iso / "target.json")
    os.environ["DT_V3_ALLOW_FILE_OBSERVER"] = "1"
    os.environ["DT_V3_CHUNK_SIZE"] = os.environ.get("DT_V3_CHUNK_SIZE") or "4096"
    state_path = iso / "target.json"
    red = make_block(iso / "red.png", (200, 30, 30), "RED")
    blue = make_block(iso / "blue.png", (30, 60, 200), "BLUE")
    target = subprocess.Popen([sys.executable, str(ROOT / "tools" / "v3_s2_paste_target.py"), str(state_path)])
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
            asyncio.run(drive(app, state_path, red, blue, out))
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
        time.sleep(30)
    target.terminate()
    images = (out.get("after_insert") or {}).get("images") or []
    kinds = [e.get("kind") for e in (out.get("after_insert") or {}).get("events") or []]
    restart = None
    missing = []
    if error is None:
        loaded, missing = load_draft(iso / "data", app.store)
        restart = None if loaded is None else {"text": loaded.text, "asset_ids": [a["asset_id"] for a in loaded.assets]}
        bytes_ok = []
        if loaded:
            for asset in loaded.assets:
                try:
                    payload = app.store.get(asset["asset_id"])
                    bytes_ok.append(hashlib.sha256(payload).hexdigest() == asset["sha256"])
                except FileNotFoundError:
                    bytes_ok.append(False)
        restart = {**(restart or {}), "bytes_ok": bytes_ok, "missing": missing}
    first_rgb = dominant_rgb(images[0]["path"]) if images else (0, 0, 0)
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
        "cursor_claimed": False,
        "android_claimed": False,
        "prototype_used": False,
        "restart": restart,
        "first_delivered_rgb": first_rgb,
        **out,
    }
    result["gates"] = {
        "pair_only_code": bool(out.get("pair_posts"))
        and all("allow_insert" not in (p or "") for p in out.get("pair_posts") or []),
        "two_photos_plus_board": len(out.get("draft_ids") or []) >= 3,
        "empty_board_blocked": bool(out.get("empty_board_blocked")),
        "undo_redo": bool((out.get("board") or {}).get("undid")),
        "new_stroke_clears_redo": bool(out.get("new_stroke_clears_redo")),
        "reedit_added_ops": int((out.get("reedit") or {}).get("after") or 0)
        > int((out.get("reedit") or {}).get("before") or 0),
        "reorder_blue_first": ((out.get("draft_ids") or [None])[0] == ((out.get("blue") or {}).get("meta") or {}).get("asset_id")),
        "image_order": kinds[:3] == ["image", "image", "image"],
        "text_after_images": kinds[-1] == "text" if kinds else False,
        "target_has_text": SAMPLE_A in str((out.get("after_insert") or {}).get("text") or ""),
        "current_kept": bool(out.get("current_kept")),
        "recall_last_is_a": SAMPLE_A in str(out.get("last_bundle_after_recall") or ""),
        "restart_bytes": bool(restart and restart.get("bytes_ok") and all(restart["bytes_ok"])),
        "zero_enter": out.get("enter_count") == 0,
        "not_cursor": (out.get("attempt") or {}).get("adapter_id") != "cursor_windows",
    }
    result["ok"] = error is None and all(result["gates"].values())
    (EVIDENCE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(json.dumps({"ok": result["ok"], "gates": result["gates"], "error": error}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
