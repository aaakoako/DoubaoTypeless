#!/usr/bin/env python3
"""发版前本地预检：跑测试、语法检查，并检查常见发布遗漏。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMPILE_TARGETS = [
    "main.py",
    "paths.py",
    "bridge.py",
    "gui.py",
    "gui_vocab.py",
    "polish.py",
    "config.py",
    "hotkeys.py",
    "typer.py",
    "app_icon.py",
    "app_version.py",
    "windows_startup.py",
    "term_bank.py",
    "providers_registry.py",
    "updater.py",
    "diagnostics.py",
    "scripts/preflight_release.py",
]


def run(label: str, cmd: list[str]) -> bool:
    print(f"\n== {label} ==")
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode:
        print(f"FAIL: {label} ({proc.returncode})")
        return False
    print(f"OK: {label}")
    return True


def check_files() -> bool:
    print("\n== release files ==")
    required = [
        "DoubaoTypeless.spec",
        "DoubaoTypeless_portable.spec",
        "requirements.txt",
        "phone.html",
        "providers.json",
        "assets/icon.ico",
        ".github/workflows/release.yml",
    ]
    missing = [x for x in required if not (ROOT / x).exists()]
    if missing:
        print("FAIL: missing " + ", ".join(missing))
        return False
    print("OK: release files")
    return True


def check_version() -> bool:
    print("\n== version ==")
    text = (ROOT / "app_version.py").read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
    if not m:
        print("FAIL: APP_VERSION not found")
        return False
    version = m.group(1).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        print(f"FAIL: APP_VERSION should look like 0.4.2, got {version!r}")
        return False
    print(f"OK: APP_VERSION={version}")
    return True


def check_gitignore() -> bool:
    print("\n== gitignore ==")
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    needed = ["config.json", "debug.log", "doubao_diagnostics_*.json"]
    missing = [x for x in needed if x not in text]
    if missing:
        print("FAIL: .gitignore missing " + ", ".join(missing))
        return False
    print("OK: gitignore protects local config/log/diagnostics")
    return True


def main() -> int:
    py = sys.executable
    checks = [
        run("pytest", [py, "-m", "pytest", "-q"]),
        run("py_compile", [py, "-m", "py_compile", *COMPILE_TARGETS]),
        check_files(),
        check_version(),
        check_gitignore(),
    ]
    print("\n== summary ==")
    if all(checks):
        print("OK: preflight passed")
        return 0
    print("FAIL: preflight failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
