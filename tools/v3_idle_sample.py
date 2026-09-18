"""Idle 10-minute sample: HUD stays hidden, no capture loop."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
EVIDENCE = ROOT / "docs" / "evidence" / "v3-idle"
DURATION_S = int(os.environ.get("DT_V3_IDLE_S", "600"))


def rss_bytes(pid: int) -> int:
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        handle = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
        ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        ctypes.windll.kernel32.CloseHandle(handle)
        return int(counters.WorkingSetSize)
    except Exception:
        return 0


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    from doubao_typeless.app import V3App

    data = EVIDENCE / "data"
    app = V3App(data_dir=data, port=0)
    app.start_background(start_hud=True)
    samples = []
    hud_seen = 0
    t0 = time.monotonic()
    pid = os.getpid()
    while time.monotonic() - t0 < DURATION_S:
        visible = bool(app.hud.visible)
        if visible:
            hud_seen += 1
        samples.append(
            {
                "t": round(time.monotonic() - t0, 1),
                "rss": rss_bytes(pid),
                "hud": visible,
            }
        )
        time.sleep(10 if DURATION_S >= 60 else 1)
    result = {
        "case_id": "AC3-081",
        "status": "PASS" if hud_seen == 0 else "FAIL",
        "duration_s": DURATION_S,
        "samples": samples,
        "hud_visible_samples": hud_seen,
        "max_rss": max((s["rss"] for s in samples), default=0),
        "note": "空闲采样：无手机长连接、无持续截屏。不是 10 分钟真机录像。",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (EVIDENCE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "duration_s", "hud_visible_samples", "max_rss")}, ensure_ascii=False))
    return 0 if hud_seen == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
