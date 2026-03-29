"""应用目录：打包后只读资源在 _MEIPASS，可写数据在 exe 所在目录。"""
from __future__ import annotations

import sys
from pathlib import Path


def resource_dir() -> Path:
    """随程序分发的只读文件（phone.html、providers.json、assets 等）。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent


def app_root() -> Path:
    """config.json、debug.log、data/ 等可写路径（与可执行文件同目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent
