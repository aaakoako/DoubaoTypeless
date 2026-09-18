"""Alt+I insert, Alt+Shift+I recall. No Enter."""
from __future__ import annotations

from typing import Callable


def start_hotkeys(*, on_insert: Callable[[], None], on_recall: Callable[[], None]):
    from pynput.keyboard import GlobalHotKeys

    listener = GlobalHotKeys(
        {
            "<alt>+i": on_insert,
            "<alt>+<shift>+i": on_recall,
        }
    )
    listener.start()
    return listener
