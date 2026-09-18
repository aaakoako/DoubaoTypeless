"""Isolated V3 data directory. Never the daily-use config.json location."""
from __future__ import annotations

import os
from pathlib import Path

PREVIEW_NAME = "preview-v3"


def v3_data_dir() -> Path:
    override = os.environ.get("DT_V3_DATA_DIR", "").strip()
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "DoubaoTypeless" / PREVIEW_NAME
    return Path.home() / "DoubaoTypeless" / PREVIEW_NAME


def lan_ip() -> str:
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"
