"""One-shot insert intents. Replays and reconnects never paste again."""
from __future__ import annotations

from typing import Literal

Decision = Literal["accept", "duplicate", "busy"]


class IntentLedger:
    def __init__(self):
        self.busy = False
        self._seen: dict[str, str] = {}

    def begin(self, intent_id: str) -> Decision:
        if not intent_id:
            raise ValueError("intent_id required")
        if intent_id in self._seen:
            return "duplicate"
        if self.busy:
            return "busy"
        self.busy = True
        self._seen[intent_id] = "RUNNING"
        return "accept"

    def finish(self, intent_id: str, result: str) -> None:
        self._seen[intent_id] = result
        self.busy = False

    def status(self, intent_id: str) -> str | None:
        return self._seen.get(intent_id)
