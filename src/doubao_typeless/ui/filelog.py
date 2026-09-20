"""有大小上限的尽力日志：日志/控制台故障不得打断一次用户操作。"""
from __future__ import annotations

import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 512 * 1024
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+)", re.I)


class FileLogger:
    def __init__(self, path: Path, *, also_print: bool = True, max_bytes: int = MAX_BYTES):
        self.path = Path(path)
        self.also_print = also_print
        self.max_bytes = max(256, int(max_bytes))
        self._lock = threading.RLock()
        # 只记录异常类型，不把异常消息里的正文/密钥复制到降级状态。
        self.last_error: str | None = None
        self.console_error: str | None = None

    def __call__(self, message: str) -> None:
        try:
            text = SECRET_RE.sub("…", str(message))
            stamp = datetime.now(timezone.utc).isoformat()
            prefix = f"{stamp} "
            budget = self.max_bytes - len(prefix.encode("utf-8")) - 32
            raw = text.encode("utf-8", errors="replace")
            if len(raw) > budget:
                text = raw[:budget].decode("utf-8", errors="ignore") + " …[truncated]"
            line = f"{prefix}{text}\n"
            with self._lock:
                # 先保存文件，再尝试控制台；console=False / 断管不能丢文件日志。
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    size = len(line.encode("utf-8"))
                    if self.path.is_file() and self.path.stat().st_size + size > self.max_bytes:
                        self.path.replace(self.path.with_suffix(".old.log"))
                    with self.path.open("a", encoding="utf-8") as fh:
                        fh.write(line)
                    self.last_error = None
                except Exception as exc:
                    self.last_error = type(exc).__name__
                try:
                    if self.also_print and sys.stdout is not None:
                        print(text, flush=True)
                    self.console_error = None
                except Exception as exc:
                    self.console_error = type(exc).__name__
        except Exception as exc:
            # 包含格式化错误，不拦 KeyboardInterrupt / SystemExit。
            self.last_error = type(exc).__name__
