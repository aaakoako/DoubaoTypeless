"""Size-capped file log. Users open it from 帮助与诊断, not a console."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 512 * 1024
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9]{8,}|Bearer\s+\S+)", re.I)


class FileLogger:
    def __init__(self, path: Path, *, also_print: bool = True, max_bytes: int = MAX_BYTES):
        self.path = Path(path)
        self.also_print = also_print
        self.max_bytes = max_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, message: str) -> None:
        text = SECRET_RE.sub("…", str(message))
        line = f"{datetime.now(timezone.utc).isoformat()} {text}\n"
        if self.also_print:
            print(text, flush=True)
        if self.path.is_file() and self.path.stat().st_size > self.max_bytes:
            rotated = self.path.with_suffix(".old.log")
            try:
                self.path.replace(rotated)
            except OSError:
                pass
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)
