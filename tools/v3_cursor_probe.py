"""Probe real Cursor windows / UIA. Never invent Composer observation."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
EVIDENCE = ROOT / "docs" / "evidence" / "v3-cursor"


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    from doubao_typeless.adapters.cursor_windows import cursor_windows, observe_image, observe_text, probe_uia

    report = probe_uia()
    windows = cursor_windows()
    payload = {
        "case_id": "AC3-006",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cursor_windows": windows,
        "uia": report,
        "observe_image": observe_image(),
        "observe_text": observe_text(),
    }
    if not windows:
        payload["status"] = "BLOCKED_NATIVE"
        payload["observed"] = "Cursor 进程窗口未找到；不能把 V3ComposerTarget 写成 Cursor PASS"
    elif not report.get("composer_control"):
        payload["status"] = "BLOCKED_NATIVE"
        payload["observed"] = "Cursor 在跑，但 UIA 未定位 Composer chatinput，附件观察仍为 unknown"
    else:
        payload["status"] = "BLOCKED_NATIVE"
        payload["observed"] = "已见到 Composer 控件，但附件树尚未闭合，observe_* 仍返回 unknown"
    (EVIDENCE / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
