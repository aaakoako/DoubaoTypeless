#!/usr/bin/env python3
"""V3 candidate preflight. Never creates tags or GitHub Releases."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = [
    "src/doubao_typeless/static/composer.html",
    "src/doubao_typeless/app.py",
    "src/doubao_typeless/storage/db.py",
    "web/package.json",
    "web/src/app.ts",
    "web/src/editor/canvas.ts",
    "scripts/启动-v3.bat",
    "docs/release/preview-notes.md",
    "docs/evidence/v3-runtime/BLOCKED_NATIVE.md",
]


def main() -> int:
    print("== v3 files ==")
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    if missing:
        print("FAIL missing " + ", ".join(missing))
        return 1
    html = (ROOT / "src/doubao_typeless/static/composer.html").read_text(encoding="utf-8")
    if "白板" not in html or html.count("<canvas") != 1:
        print("FAIL composer is not a single shared-editor page")
        return 1
    if (ROOT / "config.json").exists():
        print("FAIL repo config.json present; would risk daily-use overwrite")
        return 1
    print("OK files")
    print("== pytest ==")
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)
    if proc.returncode:
        print(f"FAIL pytest {proc.returncode}")
        return proc.returncode
    print("OK pytest")
    print("preflight_v3: candidate only; no tag, no Release, no merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
