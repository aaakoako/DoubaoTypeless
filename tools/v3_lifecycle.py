"""Start, second-launch wake, and tray-equivalent quit. Never taskkill a healthy instance."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EVIDENCE = ROOT / "docs" / "evidence" / "v3-lifecycle"
EXE = ROOT / "dist" / "DoubaoTypelessV3Preview" / "DoubaoTypelessV3Preview.exe"


def wait_http(url: str, timeout_s: float = 25.0) -> dict | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            time.sleep(0.25)
    return None


def http_down(url: str, timeout_s: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
        except Exception:
            return True
        time.sleep(0.2)
    return False


def run(cmd: list[str], *, env: dict, cwd: Path, log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=fh, stderr=subprocess.STDOUT, text=True)


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    iso = Path(os.environ.get("DT_V3_LIFE_DIR") or r"G:\AgentStorage\Temp\User\dt-v3-life")
    data = iso / "data"
    data.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DT_V3_DATA_DIR"] = str(data)
    env["PYTHONUTF8"] = "1"
    launcher = [str(EXE)] if EXE.is_file() else [sys.executable, str(ROOT / "tools" / "run_v3.py")]
    cwd = EXE.parent if EXE.is_file() else ROOT
    pre = subprocess.run(launcher + ["--quit"], cwd=str(cwd), env=env, capture_output=True, text=True, timeout=8)
    first = run(launcher, env=env, cwd=cwd, log_path=iso / "first.log")
    status = wait_http("http://127.0.0.1:8766/v3/status")
    second = subprocess.run(launcher, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=8)
    still = wait_http("http://127.0.0.1:8766/v3/status", timeout_s=4)
    quitter = subprocess.run(launcher + ["--quit"], cwd=str(cwd), env=env, capture_output=True, text=True, timeout=8)
    first.wait(timeout=12)
    down = http_down("http://127.0.0.1:8766/v3/status")
    settings = data / "settings.json"
    log_file = data / "logs" / "v3.log"
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "launcher": launcher[0],
        "used_exe": EXE.is_file(),
        "pre_quit_code": pre.returncode,
        "status_protocol": (status or {}).get("protocol"),
        "second_exit": second.returncode,
        "first_still_serving_after_second": still is not None,
        "quit_exit": quitter.returncode,
        "first_exit_after_quit": first.returncode,
        "http_down_after_quit": down,
        "taskkill_used": False,
        "file_log": log_file.is_file(),
        "settings_path_isolated": str(settings),
    }
    payload["ok"] = (
        (status or {}).get("protocol") == 3
        and second.returncode == 0
        and still is not None
        and quitter.returncode == 0
        and first.returncode == 0
        and down
        and not payload["taskkill_used"]
    )
    (EVIDENCE / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], **{k: payload[k] for k in ("second_exit", "first_exit_after_quit", "http_down_after_quit", "used_exe")}}, ensure_ascii=False))
    if not payload["ok"] and first.poll() is None:
        # last resort only after quit failed; record it
        first.kill()
        payload["taskkill_used"] = True
        (EVIDENCE / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
