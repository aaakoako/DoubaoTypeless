"""S2 evidence: production album → crop/mask/number → chunked upload → freeze → image then text.

Specified target is DT-S2-PasteTarget. Not Cursor. Isolated data dir only.
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

EVIDENCE = ROOT / "docs" / "evidence" / "v3-s2"
TARGET_TITLE = "DT-S2-PasteTarget"
SAMPLE = "遮住保密区后只投成品，不要原图"


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


def make_source(path: Path) -> dict:
    image = Image.new("RGB", (400, 300), (255, 255, 255))
    px = image.load()
    for x in range(400):
        for y in range(300):
            if x < 200 and y < 150:
                color = (200, 30, 30)
            elif x >= 200 and y < 150:
                color = (30, 180, 50)
            elif x < 200:
                color = (30, 60, 200)
            else:
                color = (220, 200, 40)
            if (x * 13 + y * 7) % 5 == 0:
                color = (color[0], color[1], min(255, color[2] + 3))
            px[x, y] = color
    for x in range(20, 140):
        for y in range(20, 80):
            px[x, y] = (255, 0, 255)
    draw = ImageDraw.Draw(image)
    draw.text((28, 36), "SECRET42", fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    payload = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "width": 400,
        "height": 300,
    }


def magenta_count(image: Image.Image) -> int:
    count = 0
    for pixel in image.getdata():
        if pixel[0] > 220 and pixel[1] < 40 and pixel[2] > 220:
            count += 1
    return count


async def drive(app: V3App, state_path: Path, source: Path, out: dict) -> None:
    from playwright.async_api import async_playwright

    code = app.auth.current_pairing_challenge() or app.auth.new_pairing_challenge()
    port = app.bridge.port or app.port
    posts: list[str] = []
    chunk_puts = 0
    completes = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.on(
            "request",
            lambda req: posts.append(req.post_data or "")
            if req.method == "POST" and req.url.endswith("/v3/pair")
            else None,
        )

        def on_request(req):
            nonlocal chunk_puts, completes
            if req.method == "PUT" and "/chunks/" in req.url:
                chunk_puts += 1
            if req.method == "POST" and req.url.endswith("/complete"):
                completes += 1

        page.on("request", on_request)
        await page.goto(f"http://127.0.0.1:{port}/")
        await page.wait_for_selector("#pairCode", state="visible")
        await page.fill("#pairCode", code)
        async with page.expect_response(lambda r: r.url.endswith("/v3/pair") and r.request.method == "POST") as info:
            await page.click("#pairGo")
        assert (await info.value).ok
        await page.wait_for_function("() => !document.getElementById('sheet').classList.contains('show')")
        await page.set_input_files("#file", str(source))
        await page.wait_for_selector("#editor.show")
        await page.wait_for_function("() => document.getElementById('stage')?.dataset.ready === '1'")
        await page.click('[data-tool="crop"]')
        edited = await page.evaluate(
            """() => {
              const ed = document.getElementById('stage').__dtEditor;
              ed.addMask(20, 20, 120, 60);
              const ok = ed.applyCrop({x:100, y:40, w:250, h:220});
              ed.stampNumber(180, 120);
              return {ok, crop: ed.crop, ops: ed.ops};
            }"""
        )
        out["editor"] = edited
        async with page.expect_response(lambda r: r.url.endswith("/complete") and r.request.method == "POST") as done:
            await page.click("#done")
        complete = await done.value
        out["upload_complete_ok"] = complete.ok
        out["upload_meta"] = await complete.json()
        await page.wait_for_function("() => !document.getElementById('editor').classList.contains('show')")
        await page.fill("#text", SAMPLE)
        await page.locator("#text").dispatch_event("input")
        for _ in range(80):
            if SAMPLE in app.draft.text and app.draft.assets:
                break
            await asyncio.sleep(0.05)
        await page.click("#sendBtn")
        for _ in range(40):
            if app.bridge.last_bundle is not None:
                break
            await asyncio.sleep(0.05)
        await browser.close()
    out["pair_posts"] = posts
    out["chunk_puts"] = chunk_puts
    out["completes"] = completes
    out["draft_text"] = app.draft.text
    out["draft_assets"] = [{k: v for k, v in a.items() if k != "bytes_data"} for a in app.draft.assets]
    out["last_bundle_assets"] = [
        {k: v for k, v in a.items() if k != "bytes_data"} for a in (app.bridge.last_bundle or {}).get("assets") or []
    ]
    out["hud_visible_flag"] = app.hud.visible
    out["hud_titles"] = titles_matching("DT-V3-HUD")
    out["focus_after_sync"] = foreground()
    hwnd = find_hwnd(TARGET_TITLE)
    out["target_focused"] = focus_hwnd(hwnd)
    time.sleep(0.2)
    out["focus_before_insert"] = foreground()
    app.insert_last()
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        observed = read_state(state_path)
        events = observed.get("events") or []
        kinds = [e.get("kind") for e in events]
        if "image" in kinds and "text" in kinds and SAMPLE in str(observed.get("text") or ""):
            break
        time.sleep(0.05)
    out["target_state"] = read_state(state_path)
    out["enter_count"] = app.delivery.enter_count
    out["attempt"] = None if app._last_attempt is None else app._last_attempt.to_dict()


def pixel_gates(source: dict, state: dict) -> dict:
    images = state.get("images") or []
    if not images:
        return {"has_image": False}
    pasted = Image.open(images[0]["path"])
    src = Image.open(source["path"])
    return {
        "has_image": True,
        "delivered_sha": images[0]["sha256"],
        "source_sha": source["sha256"],
        "sha_differs": images[0]["sha256"] != source["sha256"],
        "delivered_size": [pasted.width, pasted.height],
        "source_size": [src.width, src.height],
        "smaller_than_source": pasted.width < src.width or pasted.height < src.height,
        "magenta_source": magenta_count(src.convert("RGB")),
        "magenta_delivered": magenta_count(pasted.convert("RGB")),
        "secret_covered": magenta_count(pasted.convert("RGB")) < 30,
    }


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    iso = Path(os.environ.get("DT_V3_S2_DIR") or r"G:\AgentStorage\Temp\User\dt-v3-s2")
    iso.mkdir(parents=True, exist_ok=True)
    os.environ["DT_V3_DATA_DIR"] = str(iso / "data")
    os.environ["DT_V3_TARGET_STATE"] = str(iso / "target.json")
    os.environ["DT_V3_ALLOW_FILE_OBSERVER"] = "1"
    os.environ["DT_V3_CHUNK_SIZE"] = os.environ.get("DT_V3_CHUNK_SIZE") or "4096"
    state_path = iso / "target.json"
    source = make_source(iso / "s2-source.png")
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
            asyncio.run(drive(app, state_path, Path(source["path"]), out))
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
        time.sleep(20)
    target.terminate()
    pixels = pixel_gates(source, out.get("target_state") or {})
    events = (out.get("target_state") or {}).get("events") or []
    kinds = [e.get("kind") for e in events]
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "sample": SAMPLE,
        "source": source,
        "error": error,
        "cursor_claimed": False,
        "android_claimed": False,
        "prototype_used": False,
        "pixels": pixels,
        **out,
    }
    result["gates"] = {
        "production_frontend_text": SAMPLE in str(out.get("draft_text") or ""),
        "pair_only_code": bool(out.get("pair_posts"))
        and all("allow_insert" not in (p or "") for p in out.get("pair_posts") or []),
        "chunked_upload": int(out.get("chunk_puts") or 0) >= 2 and bool(out.get("upload_complete_ok")),
        "draft_has_finished_asset": bool(out.get("draft_assets")),
        "bundle_frozen": bool(out.get("last_bundle_assets")),
        "image_then_text": kinds[:2] == ["image", "text"] or (kinds.count("image") == 1 and kinds[-1] == "text" and kinds[0] == "image"),
        "target_has_text": SAMPLE in str((out.get("target_state") or {}).get("text") or ""),
        "sha_not_source": bool(pixels.get("sha_differs")),
        "secret_covered": bool(pixels.get("secret_covered")),
        "cropped": bool(pixels.get("smaller_than_source")),
        "zero_enter": out.get("enter_count") == 0,
        "hud_shown": bool(out.get("hud_titles")) or bool(out.get("hud_visible_flag")),
        "not_cursor": True,
        "adapter_not_cursor": (out.get("attempt") or {}).get("adapter_id") != "cursor_windows",
    }
    result["ok"] = error is None and all(result["gates"].values())
    (EVIDENCE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(json.dumps({"ok": result["ok"], "gates": result["gates"], "error": error}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
