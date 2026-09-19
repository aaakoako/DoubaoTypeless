"""Product PASS harness for Pocket Composer v3. Uses the real app, never the design prototype."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import ctypes
import win32gui
from aiohttp import ClientSession
from PIL import Image, ImageDraw, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EVIDENCE = ROOT / "docs" / "evidence" / "v3-product"
TARGET_TITLE = "V3ComposerTarget · chatinput"
SAMPLE = "把按钮右移\nOpus 与 Image2"


def log(msg: str) -> None:
    print(msg, flush=True)


def screenshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab().save(path)


def visible_titles() -> list[str]:
    titles: list[str] = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                titles.append(title)
        return True

    win32gui.EnumWindows(cb, None)
    return titles


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
    x = (left + right) // 2
    y = (top + bottom) // 2 + 40
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.2)
    return True


def make_png(color: tuple[int, int, int], label: str) -> bytes:
    image = Image.new("RGB", (160, 100), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 152, 92), outline=(255, 255, 255), width=3)
    draw.text((20, 40), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def hud_visible() -> bool:
    return any("DT-V3-HUD" in t for t in visible_titles())


def composer_checks(html: str) -> dict:
    return {
        "served_product_composer": "白板" in html and "<canvas" in html,
        "single_canvas": html.count("<canvas") == 1,
        "has_insert": "插入电脑" in html,
        "not_design_prototype": "设计演示 · 非真实截图/投递" not in html,
        "hit_44": "min-height:44px" in html,
    }


async def drive_phone(port: int, pngs: list[bytes], text: str, before_insert=None, *, pair_code: str, grant=None) -> dict:
    async with ClientSession() as session:
        page = await session.get(f"http://127.0.0.1:{port}/")
        html = await page.text()
        creds = await (
            await session.post(
                f"http://127.0.0.1:{port}/v3/pair",
                json={"code": pair_code},
            )
        ).json()
        if grant:
            grant(creds["session_id"])
            creds["allow_insert"] = True
        headers = {"X-DT-Session": creds["session_id"], "X-DT-Token": creds["token"]}
        assets = []
        for blob in pngs:
            meta = await (
                await session.post(
                    f"http://127.0.0.1:{port}/v3/assets?w=160&h=100&role=markup",
                    data=blob,
                    headers=headers,
                )
            ).json()
            assets.append(meta)
        async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
            await ws.send_json(
                {
                    "type": "session.hello",
                    "session_id": creds["session_id"],
                    "token": creds["token"],
                }
            )
            await ws.receive_json()
            await ws.send_json(
                {
                    "type": "draft.update",
                    "text": text,
                    "revision": 1,
                    "asset_refs": [a["asset_id"] for a in assets],
                    "assets": assets,
                }
            )
            ack = await ws.receive_json()
            await ws.send_json({"type": "bundle.commit"})
            ready = await ws.receive_json()
            nonce = await (
                await session.post(f"http://127.0.0.1:{port}/v3/nonce", json=creds)
            ).json()
            if before_insert:
                before_insert()
            await ws.send_json(
                {
                    "type": "insert.intent",
                    "session_id": creds["session_id"],
                    "token": creds["token"],
                    "nonce": nonce["nonce"],
                    "intent_id": str(uuid.uuid4()),
                    "trigger": "phone",
                    "recovery_mode": "full",
                }
            )
            status = await ws.receive_json()
        return {
            "html": html,
            "ack": ack,
            "bundle_auto_send": ready.get("bundle", {}).get("auto_send"),
            "attempt": status,
        }


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    isolated = Path(os.environ.get("TEMP", str(ROOT / "tmp"))) / f"dt-v3-product-{os.getpid()}"
    isolated.mkdir(parents=True, exist_ok=True)
    os.environ["DT_V3_DATA_DIR"] = str(isolated)
    os.environ["PYTHONPATH"] = str(ROOT / "src")
    state_path = isolated / "target-state.json"
    os.environ["DT_V3_TARGET_STATE"] = str(state_path)
    os.environ["DT_V3_ALLOW_FILE_OBSERVER"] = "1"

    events: list[str] = []
    png_a = make_png((212, 82, 67), "IMG1")
    png_b = make_png((22, 125, 113), "IMG2")
    hash_a = hashlib.sha256(png_a).hexdigest()
    hash_b = hashlib.sha256(png_b).hexdigest()

    result: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "prototype_used": False,
        "repo_config_exists_before": (ROOT / "config.json").exists(),
        "isolated_data_dir": str(isolated),
        "image_sha256": [hash_a, hash_b],
    }

    target = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "v3_product_target.py"), str(state_path)],
        cwd=str(ROOT),
    )
    app = None
    loop = None
    try:
        deadline = time.monotonic() + 8
        hwnd = None
        while time.monotonic() < deadline:
            hwnd = find_hwnd(TARGET_TITLE)
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            result["error"] = "product target window missing"
            (EVIDENCE / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return 2
        events.append("target_visible")
        screenshot(EVIDENCE / "01-idle-target.png")

        from doubao_typeless.app import V3App

        app = V3App(data_dir=isolated, port=18766)
        app.hud.start()
        if app.hud._app is not None:
            app.hud._app.processEvents()
        idle_hud = hud_visible()
        events.append(f"idle_hud_visible={idle_hud}")
        screenshot(EVIDENCE / "02-idle-after-app.png")
        loop = app.start_background(start_hud=False)
        events.append(f"bridge_port={app.port}")

        focus_hwnd(hwnd)
        pair_code = app.auth.current_pairing_challenge()
        if not pair_code:
            raise RuntimeError("desktop did not issue pairing challenge")

        def grant(session_id: str) -> None:
            app.auth.set_grants(session_id, allow_insert=True, allow_capture=False)

        drive = asyncio.run(
            drive_phone(
                app.port,
                [png_a, png_b],
                SAMPLE,
                before_insert=lambda: focus_hwnd(hwnd),
                pair_code=pair_code,
                grant=grant,
            )
        )
        if app.hud._app is not None:
            app.hud._app.processEvents()
        events.append(f"attempt={drive['attempt']}")
        screenshot(EVIDENCE / "03-after-insert.png")

        state = {}
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        received = [img.get("sha256") for img in state.get("images") or []]
        text = str(state.get("text") or "")
        enter_count = int(state.get("enter_count") or 0)
        ui = composer_checks(drive["html"])
        hud_after = hud_visible() or app.hud.visible

        gates = {
            "idle_hud_hidden": idle_hud is False,
            "product_composer": all(ui.values()),
            "two_images": len(received) == 2 and len(set(received)) == 2,
            "text_after_images": SAMPLE.split("\n")[0] in text,
            "zero_enter": enter_count == 0 and app.delivery.enter_count == 0,
            "no_auto_send": drive["bundle_auto_send"] is False,
            "attempt_confirmed": drive["attempt"].get("result") == "CONFIRMED",
            "repo_config_untouched": not (ROOT / "config.json").exists(),
        }
        result.update(
            {
                "events": events,
                "gates": gates,
                "ui": ui,
                "received_images": received,
                "received_text": text,
                "enter_count": enter_count,
                "attempt": drive["attempt"],
                "hud_after_insert": hud_after,
                "repo_config_exists_after": (ROOT / "config.json").exists(),
            }
        )
        (EVIDENCE / "target-state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (EVIDENCE / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        failed = [k for k, v in gates.items() if not v]
        log(json.dumps({"gates": gates, "failed": failed}, ensure_ascii=False))
        return 0 if not failed else 1
    finally:
        if app is not None and loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(app.stop(), loop).result(5)
            except Exception:
                pass
        target.kill()
        try:
            target.wait(timeout=3)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
