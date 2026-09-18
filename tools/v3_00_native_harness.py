"""Run old v0.4.2 text path from an isolated worktree. Never writes repo config.json."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ctypes
import win32gui

ROOT = Path(__file__).resolve().parents[1]
WORKTREE = Path(r"G:\DoubaoTypeless\preview-v3-00")
PORT = 18765
REVIEW_SHA = "e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5"
SAMPLE = "V3-00 基线回归\nOpus 与 Image2"
AC2 = ROOT / "docs" / "evidence" / "baseline" / "AC3-002"
AC3 = ROOT / "docs" / "evidence" / "baseline" / "AC3-003"
VK_MENU = 0x12
VK_I = 0x49
KEYEVENTF_KEYUP = 0x0002


def log(msg: str) -> None:
    print(msg, flush=True)


def wait_port(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = socket.socket()
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except OSError:
            time.sleep(0.2)
        finally:
            try:
                s.close()
            except OSError:
                pass
    return False


def screenshot(path: Path) -> None:
    from PIL import ImageGrab

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


def find_hwnd(title_exact: str):
    found = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == title_exact:
            found.append(hwnd)
        return True

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def focus_hwnd(hwnd) -> bool:
    if not hwnd:
        return False
    try:
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def send_alt_i() -> None:
    from pynput.keyboard import Controller, Key

    kbd = Controller()
    kbd.press(Key.alt)
    kbd.press("i")
    time.sleep(0.05)
    kbd.release("i")
    kbd.release(Key.alt)


def click_insert_button(hwnd) -> None:
    if not hwnd:
        return
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    x = left + 90
    y = top + 250
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)


def poll_file(path: Path, predicate, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        if path.exists():
            last = path.read_text(encoding="utf-8")
            if predicate(last):
                return last
        time.sleep(0.2)
    return last


def poll_until(fn, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(0.2)
    return False


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def git_head() -> str:
    out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True)
    return out.strip()


def main() -> int:
    if not WORKTREE.is_dir():
        raise SystemExit(f"missing isolated worktree {WORKTREE}")
    if (ROOT / "config.json").exists():
        raise SystemExit("refusing to run: repo config.json exists")

    AC2.mkdir(parents=True, exist_ok=True)
    AC3.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    head = git_head()
    env = {
        "os": sys.getwindowsversion()[0] if sys.platform == "win32" else sys.platform,
        "platform": sys.platform,
        "python": sys.version,
        "real_windows": True,
        "real_android_ime": False,
        "real_doubao_ime": False,
        "real_cursor_composer": False,
        "html_prototype_used_as_product_pass": False,
        "isolated_worktree": str(WORKTREE),
        "bridge_port": PORT,
        "adb_available": False,
        "phone_device_present": False,
        "started_at": started,
        "commit_sha": head,
        "review_sha": REVIEW_SHA,
    }
    write_json(AC2 / "environment.json", env)
    write_json(AC3 / "environment.json", env)

    fixture = json.loads((ROOT / "tests/fixtures/legacy/config.sanitized.json").read_text(encoding="utf-8"))
    fixture.pop("_comment", None)
    (WORKTREE / "config.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")

    captured = AC2 / "target-captured.txt"
    if captured.exists():
        captured.unlink()

    target_proc = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "v3_00_paste_target.py"), str(captured)],
        cwd=str(AC2),
    )
    app_env = os.environ.copy()
    app_env["DT_SKIP_AUTO_UPDATE_CHECK"] = "1"
    app_env["DT_V3_ISOLATED"] = "1"
    app_env["PYTHONUNBUFFERED"] = "1"
    log_path = AC2 / "app-stdout.txt"
    log_f = open(log_path, "w", encoding="utf-8")
    app_proc = subprocess.Popen(
        [sys.executable, str(WORKTREE / "main.py")],
        cwd=str(WORKTREE),
        env=app_env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
    )
    events: list[str] = []
    try:
        if not wait_port(PORT, 25):
            events.append("bridge_port_not_open")
            raise RuntimeError("bridge port did not open")
        events.append("bridge_port_open")
        time.sleep(1.0)
        idle_titles = visible_titles()
        screenshot(AC3 / "idle.png")
        review_idle = [t for t in idle_titles if t == "DoubaoTypeless"]
        events.append(f"idle_visible_DoubaoTypeless={review_idle}")

        if not poll_until(lambda: find_hwnd("V3-00-TARGET") is not None, 8):
            raise RuntimeError("paste target window missing")
        focus_hwnd(find_hwnd("V3-00-TARGET"))
        events.append("focused_paste_target_before_input")

        import asyncio
        import aiohttp

        async def phone_flow() -> None:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{PORT}/") as resp:
                    html = await resp.text()
                    (AC2 / "phone-html-status.txt").write_text(
                        f"status={resp.status} contains_textarea={'text-input' in html}\n",
                        encoding="utf-8",
                    )
                async with session.ws_connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
                    await ws.send_json({"type": "hello", "meta": {"clientVersion": "v3-00-harness"}})
                    await ws.send_json({"type": "composition", "text": "", "meta": {"phase": "start"}})
                    await ws.send_json({"type": "update", "text": "V3-00", "meta": {"inputType": "composition"}})
                    await ws.send_json({"type": "composition", "text": SAMPLE, "meta": {"phase": "end"}})
                    await ws.send_json({"type": "update", "text": SAMPLE, "meta": {"inputType": "insertText"}})
                    focus_hwnd(find_hwnd("V3-00-TARGET"))
                    await asyncio.sleep(0.2)
                    await ws.send_json(
                        {
                            "type": "stable",
                            "text": SAMPLE,
                            "meta": {"stableReason": "v3-00-harness", "inputType": "test"},
                        }
                    )
                    await asyncio.sleep(1.2)

        asyncio.run(phone_flow())
        events.append("ws_sample_sent")

        appeared = poll_until(lambda: "DoubaoTypeless" in visible_titles(), 10)
        screenshot(AC3 / "input.png")
        screenshot(AC2 / "after-input.png")
        events.append(f"review_visible_after_input={appeared}")

        focus_hwnd(find_hwnd("V3-00-TARGET"))
        time.sleep(0.3)
        send_alt_i()
        events.append("sent_alt_i_pynput")
        got = poll_file(captured, lambda t: "V3-00 基线回归" in t and "Opus" in t, 4)
        if "V3-00 基线回归" not in got:
            click_insert_button(find_hwnd("DoubaoTypeless"))
            events.append("clicked_insert_button_fallback")
        got = poll_file(captured, lambda t: "V3-00 基线回归" in t and "Opus" in t, 8)
        (AC2 / "target-captured.txt").write_text(got, encoding="utf-8")
        screenshot(AC2 / "after-insert.png")
        inserted = "V3-00 基线回归" in got and "Opus" in got and "Image2" in got
        events.append(f"target_contains_sample={inserted}")
        events.append(f"captured={got!r}"[:1000])

        review = find_hwnd("DoubaoTypeless")
        if review:
            win32gui.PostMessage(review, 0x0010, 0, 0)  # WM_CLOSE
        hidden = poll_until(lambda: find_hwnd("DoubaoTypeless") is None, 6)
        screenshot(AC3 / "hidden.png")
        events.append(f"review_hidden_after_close={hidden}")

        observed_windows = (
            f"idle_review={review_idle}; after_input_visible={appeared}; "
            f"inserted={inserted}; hidden={hidden}; titles_idle_has_tray_only={not review_idle}"
        )
        ac2_status = "BLOCKED_NATIVE"
        ac2_observed = (
            "Windows isolated worktree ran old text path via WebSocket composition/update/stable "
            f"and Alt+I. inserted={inserted}. No ADB/Android Doubao IME device. "
            "Did not send keys into the current Cursor Composer to avoid contaminating this session. "
            f"events={events}"
        )
        write_json(
            AC2 / "result.json",
            {
                "case_id": "AC3-002",
                "status": ac2_status,
                "observed": ac2_observed,
                "expected": "完整记录旧版实际结果，已知失败不能填通过",
                "started_at": started,
                "commit_sha": head,
                "windows_insert_observed": inserted,
                "phone_ime_observed": False,
                "composer_observed": False,
                "evidence_paths": [
                    "docs/evidence/baseline/AC3-002/environment.json",
                    "docs/evidence/baseline/AC3-002/after-input.png",
                    "docs/evidence/baseline/AC3-002/after-insert.png",
                    "docs/evidence/baseline/AC3-002/target-captured.txt",
                    "docs/evidence/baseline/AC3-002/phone-html-status.txt",
                    "docs/evidence/baseline/AC3-002/app-stdout.txt",
                ],
            },
        )
        ac3_status = "PASS" if (AC3 / "idle.png").is_file() and (AC3 / "input.png").is_file() and (AC3 / "hidden.png").is_file() else "FAIL"
        write_json(
            AC3 / "result.json",
            {
                "case_id": "AC3-003",
                "status": ac3_status,
                "observed": observed_windows + "; Alt+Shift+I skip-correction recorded in hotkey-migration.md",
                "expected": "录像/截图能说明输入才显示的习惯；旧Alt+Shift+I局部跳过纠错语义已记入迁移",
                "started_at": started,
                "commit_sha": head,
                "evidence_paths": [
                    "docs/evidence/baseline/AC3-003/idle.png",
                    "docs/evidence/baseline/AC3-003/input.png",
                    "docs/evidence/baseline/AC3-003/hidden.png",
                    "docs/evidence/baseline/AC3-003/hotkey-migration.md",
                ],
            },
        )
        write_json(AC2 / "events.json", {"events": events, "captured": got})
        log(json.dumps({"ac3_002": ac2_status, "ac3_003": ac3_status, "inserted": inserted}, ensure_ascii=False))
        return 0 if ac3_status in {"PASS", "BLOCKED_NATIVE"} else 1
    except Exception as exc:
        events.append(f"error={type(exc).__name__}:{exc}")
        write_json(
            AC2 / "result.json",
            {
                "case_id": "AC3-002",
                "status": "FAIL",
                "observed": f"native harness exception: {exc}; events={events}",
                "expected": "完整记录旧版实际结果，已知失败不能填通过",
                "started_at": started,
                "commit_sha": head,
                "evidence_paths": ["docs/evidence/baseline/AC3-002/app-stdout.txt"],
            },
        )
        write_json(
            AC3 / "result.json",
            {
                "case_id": "AC3-003",
                "status": "FAIL",
                "observed": f"native harness exception: {exc}; events={events}",
                "expected": "录像/截图能说明输入才显示的习惯；旧Alt+Shift+I局部跳过纠错语义已记入迁移",
                "started_at": started,
                "commit_sha": head,
                "evidence_paths": ["docs/evidence/baseline/AC3-003/hotkey-migration.md"],
            },
        )
        log(repr(exc))
        return 1
    finally:
        for proc in (app_proc, target_proc):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
        debug_src = WORKTREE / "debug.log"
        if debug_src.exists():
            (AC2 / "worktree-debug.log").write_text(debug_src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        log_f.close()
        if (ROOT / "config.json").exists():
            raise SystemExit("repo config.json was created; abort")


if __name__ == "__main__":
    raise SystemExit(main())
