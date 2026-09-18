"""Real-device Doubao IME check. No ADB → BLOCKED_NATIVE, never PASS."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "v3-ime"


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    adb = shutil.which("adb")
    payload = {
        "case_id": "AC3-037/090",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "adb": adb,
        "devices": [],
        "ime": None,
        "status": "BLOCKED_NATIVE",
    }
    if not adb:
        payload["observed"] = "本机没有 adb，无法录制真机豆包输入法 composition"
        (EVIDENCE / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    devices = subprocess.run([adb, "devices"], capture_output=True, text=True, check=False)
    payload["devices_raw"] = devices.stdout
    lines = [ln for ln in devices.stdout.splitlines()[1:] if ln.strip() and "device" in ln]
    payload["devices"] = lines
    if not lines:
        payload["observed"] = "adb 在，但没有已授权设备"
        (EVIDENCE / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    ime = subprocess.run([adb, "shell", "ime", "list", "-s"], capture_output=True, text=True, check=False)
    payload["ime"] = ime.stdout
    if "doubao" in ime.stdout.lower() or "豆包" in ime.stdout:
        payload["status"] = "FAIL"
        payload["observed"] = "看到豆包 IME 包名，但本轮没有 composition 录像，不能 PASS"
    else:
        payload["observed"] = "设备在线但当前 IME 列表没有豆包"
    (EVIDENCE / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
