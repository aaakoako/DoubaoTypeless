"""Single-instance advisory lock. Never kills the other process."""
from __future__ import annotations

import os
from pathlib import Path


class InstanceLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._fh = None
        self.owned = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+", encoding="utf-8")
        try:
            import msvcrt

            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.owned = False
            return False
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(str(os.getpid()))
        self._fh.flush()
        self.owned = True
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            import msvcrt

            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        self._fh.close()
        self._fh = None
        self.owned = False
