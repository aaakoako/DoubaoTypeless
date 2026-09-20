"""构建身份只读信息；不依据目录名字猜版本。"""
from pathlib import Path
import json
import sys


def build_info() -> dict:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    try:
        value = json.loads((root / "build-info.json").read_text(encoding="utf-8"))
        sha = value.get("source_sha", "")
        if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha):
            return {"source_sha": sha, "channel":"v3-private-trial", "release_ready":False}
    except (OSError, ValueError, TypeError):
        pass
    return {"source_sha":"development", "channel":"v3-private-trial", "release_ready":False}
