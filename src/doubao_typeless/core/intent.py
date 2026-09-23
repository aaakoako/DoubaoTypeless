"""一次性投递登记：重放不补发，异常释放 busy，不覆盖其他操作的锁。"""
from __future__ import annotations
from collections import OrderedDict
import threading
from typing import Literal

Decision = Literal["accept", "duplicate", "busy"]

class IntentLedger:
    def __init__(self):
        self.busy = False
        self._seen: OrderedDict[str, str] = OrderedDict()
        self._owner: str | None = None
        self._lock = threading.RLock()

    def begin(self, intent_id: str) -> Decision:
        if not intent_id:
            raise ValueError("intent_id required")
        with self._lock:
            if intent_id in self._seen:
                return "duplicate"
            if self.busy:
                return "busy"
            self.busy = True
            self._owner = intent_id
            self._seen[intent_id] = "RUNNING"
            return "accept"

    def finish(self, intent_id: str, result: str) -> None:
        with self._lock:
            self._seen[intent_id] = result
            if self._owner == intent_id:
                self._owner = None
                self.busy = False
            while len(self._seen) > 2048:
                self._seen.popitem(last=False)

    def status(self, intent_id: str) -> str | None:
        with self._lock:
            return self._seen.get(intent_id)
