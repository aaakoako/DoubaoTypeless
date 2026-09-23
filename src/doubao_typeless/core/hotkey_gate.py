"""Ignore OS key-repeat until the chord is released."""
from __future__ import annotations


class HotkeyGate:
    def __init__(self) -> None:
        self.held = False
        self.fires = 0

    def press(self) -> bool:
        if self.held:
            return False
        self.held = True
        self.fires += 1
        return True

    def release(self) -> None:
        self.held = False
