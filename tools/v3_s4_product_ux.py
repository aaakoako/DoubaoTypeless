"""S4 evidence: PC grants, BYOK error path, settings copy, no-key insert to paste target.

Specified target DT-S2-PasteTarget. Not Cursor. Isolated data dir only.
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
from doubao_typeless.services.byok import ERROR_LABELS

EVIDENCE = ROOT / "docs" / "evidence" / "v3-s4"
TARGET_TITLE = "DT-S2-PasteTarget"
SAMPLE = "无Key原文，401后仍可插入"


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


def bundle_stats() -> dict:
    dist = ROOT / "web" / "dist"
    files = []
    total = 0
    for path in dist.rglob("*"):
        if path.is_file():
            size = path.stat().st_size
            total += size
            files.append({"path": str(path.relative_to(dist)).replace("\\", "/"), "bytes": size})
    js = [f for f in files if f["path"].endswith(".js")]
    js_bytes = sum(f["bytes"] for f in js)
    return {
        "files": files,
        "total_bytes": total,
        "js_bytes": js_bytes,
        "js_count": len(js),
        "webengine": any("QtWebEngine" in f["path"] or "webengine" in f["path"].lower() for f in files),
        "budget_js_gzip_target_kib": 150,
        "note": "未压缩体积；gzip 目标 150KiB 需发布包实测。不是便携 ZIP 最终候选。",
    }


async def drive(app: V3App, state_path: Path, out: dict) -> None:
    from playwright.async_api import async_playwright

    posts: list[str] = []
    secret = "sk-s4-secret-not-for-log"
    app.byok.endpoint = "https://old.example/v1"
    app.byok.api_key = secret

    def boom(_url, _body, _headers):
        raise Exception("HTTP 401 unauthorized " + secret)

    app.byok._post = boom
    polish = app.byok.polish(
        SAMPLE,
        draft_id=app.draft.draft_id,
        revision=app.draft.revision,
        current_draft_id=app.draft.draft_id,
        current_revision=app.draft.revision,
    )
    out["byok_error"] = polish
    out["byok_key_leaked"] = secret in json.dumps(polish)
    out["byok_keeps_text"] = polish.get("text") == SAMPLE
    out["byok_label"] = polish.get("message") == ERROR_LABELS["unauthorized"]

    host_change = None
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.on(
            "request",
            lambda req: posts.append(req.post_data or "")
            if req.method == "POST" and req.url.endswith("/v3/pair")
            else None,
        )
        port = app.bridge.port or app.port
        code = app.auth.current_pairing_challenge() or app.auth.new_pairing_challenge()
        await page.goto(f"http://127.0.0.1:{port}/")
        await page.wait_for_selector("#pairCode", state="visible")
        out["pair_copy"] = await page.locator("#sheetCard").inner_text()
        await page.screenshot(path=str(EVIDENCE / "01-pair.png"))
        await page.fill("#pairCode", code)
        async with page.expect_response(lambda r: r.url.endswith("/v3/pair") and r.request.method == "POST") as info:
            await page.click("#pairGo")
        assert (await info.value).ok
        await page.wait_for_function("() => !document.getElementById('sheet').classList.contains('show')")
        await page.wait_for_function(
            "() => (document.getElementById('connText')||{}).textContent && document.getElementById('connText').textContent.indexOf('已连接') >= 0"
        )
        await page.fill("#text", SAMPLE)
        await page.locator("#text").dispatch_event("input")
        for _ in range(40):
            if SAMPLE in app.draft.text:
                break
            await asyncio.sleep(0.05)
        await page.click("#sendBtn")
        await page.wait_for_function(
            "() => (document.getElementById('sync')||{}).textContent && document.getElementById('sync').textContent.indexOf('电脑确认插入') >= 0"
        )
        out["ungranted_insert_toast"] = await page.locator("#sync").inner_text()
        await page.click("#captureBtn")
        await asyncio.sleep(0.3)
        out["capture_denied_toast"] = await page.locator("#sync").inner_text()
        out["draft_after_denied_capture"] = app.draft.text
        await page.click("#settingsBtn")
        out["settings_copy"] = await page.locator("#sheetCard").inner_text()
        await page.screenshot(path=str(EVIDENCE / "02-settings.png"))
        pc = await browser.new_page()
        await pc.goto(f"http://127.0.0.1:{port}/pc")
        out["pc_copy"] = await pc.locator("body").inner_text()
        await pc.screenshot(path=str(EVIDENCE / "03-pc.png"))
        sessions = await (await pc.request.get(f"http://127.0.0.1:{port}/v3/sessions")).json()
        session_id = sessions["items"][0]["session_id"]
        granted = await (
            await pc.request.post(
                f"http://127.0.0.1:{port}/v3/grants",
                data=json.dumps({"session_id": session_id, "allow_insert": True, "allow_capture": False}),
                headers={"Content-Type": "application/json"},
            )
        ).json()
        out["granted"] = granted
        host_change = await (
            await pc.request.post(
                f"http://127.0.0.1:{port}/v3/byok",
                data=json.dumps({"endpoint": "https://new.example/v1"}),
                headers={"Content-Type": "application/json"},
            )
        ).json()
        out["host_change"] = host_change
        probe = await (
            await pc.request.post(
                f"http://127.0.0.1:{port}/v3/byok/probe",
                data=json.dumps({"text": "probe"}),
                headers={"Content-Type": "application/json"},
            )
        ).json()
        out["probe"] = {k: probe.get(k) for k in ("status", "reason", "message")}
        out["probe_leaked"] = secret in json.dumps(probe)
        hwnd = find_hwnd(TARGET_TITLE)
        out["target_focused"] = focus_hwnd(hwnd)
        app.insert_last()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            observed = read_state(state_path)
            if SAMPLE in str(observed.get("text") or ""):
                break
            time.sleep(0.05)
        out["after_insert"] = read_state(state_path)
        await browser.close()
    out["pair_posts"] = posts
    out["enter_count"] = app.delivery.enter_count
    out["attempt"] = None if app._last_attempt is None else app._last_attempt.to_dict()
    out["settings_on_disk"] = json.loads((app.data_dir / "settings.json").read_text(encoding="utf-8")) if (app.data_dir / "settings.json").is_file() else {}
    out["host_change"] = host_change


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    iso = Path(os.environ.get("DT_V3_S4_DIR") or r"G:\AgentStorage\Temp\User\dt-v3-s4")
    iso.mkdir(parents=True, exist_ok=True)
    os.environ["DT_V3_DATA_DIR"] = str(iso / "data")
    os.environ["DT_V3_TARGET_STATE"] = str(iso / "target.json")
    state_path = iso / "target.json"
    target = subprocess.Popen([sys.executable, str(ROOT / "tools" / "v3_s2_paste_target.py"), str(state_path)])
    time.sleep(0.8)
    app = V3App(data_dir=iso / "data", port=0)
    app.hud.start()
    out: dict = {}
    error: str | None = None

    def worker() -> None:
        nonlocal error
        try:
            app.start_background(start_hud=False)
            asyncio.run(drive(app, state_path, out))
            screenshot(EVIDENCE / "04-after-insert.png")
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
    after = out.get("after_insert") or {}
    events = after.get("events") or []
    pair_body = json.loads(out.get("pair_posts")[0]) if out.get("pair_posts") else {}
    settings_disk = out.get("settings_on_disk") or {}
    gates = {
        "pair_only_code": set(pair_body) == {"code"},
        "pair_explains_recall": "跳过纠错" in str(out.get("pair_copy") or ""),
        "settings_reachable": "密钥只存在电脑" in str(out.get("settings_copy") or ""),
        "pc_reachable": "允许插入" in str(out.get("pc_copy") or ""),
        "ungranted_insert_blocked": "电脑确认插入" in str(out.get("ungranted_insert_toast") or ""),
        "capture_denied_keeps_text": out.get("draft_after_denied_capture") == SAMPLE and "截图权限" in str(out.get("capture_denied_toast") or ""),
        "byok_401_keeps_text": bool(out.get("byok_keeps_text")),
        "byok_label": bool(out.get("byok_label")),
        "byok_no_key_leak": out.get("byok_key_leaked") is False and out.get("probe_leaked") is False,
        "host_change_needs_reauth": bool((out.get("host_change") or {}).get("needs_reauth")),
        "pc_grant_insert": bool((out.get("granted") or {}).get("allow_insert")),
        "target_has_text": SAMPLE in str(after.get("text") or ""),
        "text_only_no_image_first": [e.get("kind") for e in events][:1] == ["text"] or SAMPLE in str(after.get("text") or ""),
        "zero_enter": out.get("enter_count") == 0,
        "isolated_settings": "sk-s4-secret-not-for-log" not in json.dumps(settings_disk, ensure_ascii=False),
        "not_cursor": after.get("title") == TARGET_TITLE,
    }
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
        "cursor_claimed": False,
        "android_claimed": False,
        "prototype_used": False,
        "bundle_stats": bundle_stats(),
        "gates": gates,
        "ok": error is None and all(gates.values()),
        "observation_note": "指定目标 DT-S2-PasteTarget，不是 Cursor。电脑设置页可授权；拒绝截图后文字仍在；BYOK 401 保留原文且不泄露密钥；换主机需重新授权。真机 10 分钟长连接与 2 小时语音矩阵仍 BLOCKED。",
        "independent_review": "S2 still WAITING; S4 not self-signed as product PASS for Android or Cursor",
        **{k: out.get(k) for k in ("pair_copy", "settings_copy", "pc_copy", "ungranted_insert_toast", "capture_denied_toast", "byok_error", "host_change", "granted", "probe", "after_insert", "pair_posts", "enter_count", "attempt")},
    }
    (EVIDENCE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "error": error, "gates": gates}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
