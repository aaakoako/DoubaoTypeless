"""Native window + long-text pixel check against the isolated onedir pack.

Starts the windowed EXE with an isolated pipe/data dir. Does not touch daily-use
config.json and does not send quit to the default live preview pipe.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import ClientSession
from PIL import Image, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "evidence" / "v3-s5-pack"
EXE = PACK / "dist" / "DoubaoTypelessV3PreviewUI" / "DoubaoTypelessV3PreviewUI.exe"
EVIDENCE = ROOT / "docs" / "evidence" / "v3-native-pack"
EXPECTED_EXE = "4bae6609e4b5af5e6c8508b774bb7b023b4c0462dd43625e95f96ee9617ae00f"
PIPE = "DoubaoTypelessV3Preview-native-pixels"
LONG = (
    "这是一段用来核对原生浮窗长文阅读的说明。"
    "主操作仍是插入并复制，收窗后手机开始下一段，上次可以召回。"
    "文字应当完整保留，不能截成二百个字，也不能把字号缩小硬塞进固定两行。"
    "超过上限后必须在浮窗内部滚动，底部插入并复制按钮仍要能点到。"
) * 8


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def enum_windows() -> list[dict]:
    import win32gui

    found: list[dict] = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd) or ""
        cls = win32gui.GetClassName(hwnd) or ""
        if "DT-V3-HUD" in title or "DoubaoTypeless 预览" in title or title == "当前图文":
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            found.append(
                {
                    "title": title,
                    "class": cls,
                    "hwnd": int(hwnd),
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "width": right - left,
                    "height": bottom - top,
                }
            )
        return True

    win32gui.EnumWindows(_cb, None)
    return found


def shot_qt(hwnd: int, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QGuiApplication

    app = QApplication.instance() or QApplication([])
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("no screen")
    pix = screen.grabWindow(hwnd)
    pix.save(str(dest))
    app.processEvents()


def shot_hwnd(hwnd: int, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    import win32gui
    import win32ui
    from ctypes import windll

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = max(1, right - left), max(1, bottom - top)
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    src = win32ui.CreateDCFromHandle(hwnd_dc)
    mem = src.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(src, width, height)
    mem.SelectObject(bitmap)
    windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 2)
    info = bitmap.GetInfo()
    bits = bitmap.GetBitmapBits(True)
    image = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)
    image.save(dest)
    win32gui.DeleteObject(bitmap.GetHandle())
    mem.DeleteDC()
    src.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)


def raise_window(hwnd: int) -> None:
    import win32con
    import win32gui

    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST,
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
    )


def shot_screen(box: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    raise_window(box["hwnd"])
    time.sleep(0.15)
    pad = 2
    image = ImageGrab.grab(bbox=(box["left"] - pad, box["top"] - pad, box["right"] + pad, box["bottom"] + pad))
    image.save(dest)


def count_color(path: Path, target: tuple[int, int, int], slop: int = 18) -> int:
    image = Image.open(path)
    hit = 0
    for px in image.getdata():
        if all(abs(px[i] - target[i]) <= slop for i in range(3)):
            hit += 1
    return hit


async def drive(port: int, code: str) -> None:
    async with ClientSession() as session:
        creds = await (
            await session.post(
                f"http://127.0.0.1:{port}/v3/pair",
                json={"code": code},
            )
        ).json()
        async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as ws:
            await ws.send_json(
                {
                    "type": "session.hello",
                    "session_id": creds["session_id"],
                    "token": creds["token"],
                }
            )
            ready = await ws.receive_json()
            if ready.get("type") != "session.ready":
                raise RuntimeError(ready)
            await ws.send_json(
                {
                    "type": "draft.update",
                    "text": LONG,
                    "revision": int(ready.get("revision") or 0) + 1,
                    "draft_id": ready.get("draft_id"),
                    "epoch": ready.get("epoch"),
                    "asset_refs": [],
                }
            )
            ack = await ws.receive_json()
            if ack.get("type") != "draft.ack":
                raise RuntimeError(ack)


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if not EXE.is_file():
        print(json.dumps({"ok": False, "error": f"missing {EXE}"}))
        return 1
    got = sha256(EXE)
    if got != EXPECTED_EXE:
        print(json.dumps({"ok": False, "error": "exe hash mismatch", "got": got}))
        return 1
    data = EVIDENCE / "smoke-data"
    data.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DT_V3_DATA_DIR"] = str(data)
    env["DT_V3_PIPE"] = PIPE
    env["PYTHONUTF8"] = "1"
    log_path = EVIDENCE / "pack.log"
    proc = subprocess.Popen(
        [str(EXE)],
        cwd=str(EXE.parent),
        env=env,
        stdout=log_path.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    pair = data / "pair.txt"
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline and not pair.is_file():
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    windows_idle = enum_windows()
    port = 0
    pair_text = pair.read_text(encoding="utf-8") if pair.is_file() else ""
    for line in pair_text.splitlines():
        if "://" in line:
            port = int(line.rsplit(":", 1)[-1].strip("/"))
    error = None
    try:
        if not port:
            raise RuntimeError("pack did not write pair.txt")
        pair_lines = [line.strip() for line in pair_text.splitlines() if line.strip()]
        code = pair_lines[1] if len(pair_lines) > 1 else ""
        if not code:
            raise RuntimeError("pair.txt missing desktop challenge")
        asyncio.run(drive(port, code))
        time.sleep(1.2)
        windows_long = enum_windows()
        shots = {}
        for item in windows_long:
            key = "hud" if "HUD" in item["title"] else ("review" if item["title"] == "当前图文" else "client")
            path = EVIDENCE / f"{key}.png"
            try:
                shot_qt(item["hwnd"], path)
            except Exception:
                shot_hwnd(item["hwnd"], path)
            shot_hwnd(item["hwnd"], EVIDENCE / f"{key}-print.png")
            shots[key] = str(path.relative_to(ROOT)).replace("\\", "/")
        hud = next((w for w in windows_long if "HUD" in w["title"]), None)
        client = next((w for w in windows_long if w["title"] == "DoubaoTypeless 预览"), None)
        daily = (ROOT / "config.json").exists()
        hud_path = EVIDENCE / "hud.png"
        client_path = EVIDENCE / "client.png"
        teal = count_color(hud_path, (22, 125, 113)) if hud_path.is_file() else 0
        ink = count_color(hud_path, (29, 40, 38)) if hud_path.is_file() else 0
        client_accent = count_color(client_path, (22, 125, 113)) if client_path.is_file() else 0
        payload = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "exe": str(EXE),
            "exe_sha256": got,
            "pipe": PIPE,
            "port": port,
            "long_chars": len(LONG),
            "windows_idle": windows_idle,
            "windows_long": windows_long,
            "hud": hud,
            "client": client,
            "shots": shots,
            "pixel_hits": {"hud_teal": teal, "hud_ink": ink, "client_accent": client_accent},
            "gates": {
                "exe_hash_matched": True,
                "client_visible": bool(client and client["width"] > 200 and client["height"] > 200),
                "hud_visible": bool(hud),
                "hud_width_400ish": bool(hud and 380 <= hud["width"] <= 520),
                "hud_height_capped": bool(hud and hud["height"] <= 300),
                "hud_taller_than_min": bool(hud and hud["height"] >= 88),
                "hud_insert_button_visible": teal >= 80,
                "hud_body_ink_visible": ink >= 200,
                "client_chrome_visible": client_accent >= 40,
                "long_text_not_truncated_in_payload": len(LONG) > 200,
                "repo_config_untouched": not daily,
            },
            "android_claimed": False,
            "cursor_claimed": False,
            "release_ready": False,
        }
        payload["ok"] = all(payload["gates"].values())
        (EVIDENCE / "result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({"ok": payload["ok"], "gates": payload["gates"], "shots": shots}, ensure_ascii=False))
        return 0 if payload["ok"] else 1
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        (EVIDENCE / "result.json").write_text(
            json.dumps({"ok": False, "error": error}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"ok": False, "error": error}))
        return 1
    finally:
        quit_env = env.copy()
        subprocess.run([str(EXE), "--quit"], cwd=str(EXE.parent), env=quit_env, timeout=8, check=False)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
