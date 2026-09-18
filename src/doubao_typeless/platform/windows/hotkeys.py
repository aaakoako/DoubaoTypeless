"""Alt+I insert, Alt+Shift+I recall. No Enter."""
from __future__ import annotations

from typing import Callable


from doubao_typeless.core.hotkey_gate import HotkeyGate


def start_hotkeys(
    *,
    on_insert: Callable[[], None],
    on_recall: Callable[[], None],
    on_region: Callable[[], None] | None = None,
):
    from pynput.keyboard import GlobalHotKeys, Key, Listener

    insert_gate = HotkeyGate()
    recall_gate = HotkeyGate()
    region_gate = HotkeyGate()
    failures: list[str] = []

    def wrap(gate: HotkeyGate, fn: Callable[[], None]):
        def _inner():
            if gate.press():
                fn()

        return _inner

    mapping = {
        "<alt>+i": wrap(insert_gate, on_insert),
        "<alt>+<shift>+i": wrap(recall_gate, on_recall),
    }
    if on_region:
        mapping["<alt>+<shift>+s"] = wrap(region_gate, on_region)
    try:
        listener = GlobalHotKeys(mapping)
        listener.start()
    except Exception as exc:
        failures.append(str(exc))
        listener = None

    def on_release(key):
        if key in {Key.alt, Key.alt_l, Key.alt_r, Key.shift, Key.shift_l, Key.shift_r} or getattr(key, "char", "") in {"i", "I", "s", "S"}:
            insert_gate.release()
            recall_gate.release()
            region_gate.release()

    release_listener = Listener(on_release=on_release)
    try:
        release_listener.start()
    except Exception as exc:
        failures.append(str(exc))
    return {"listener": listener, "release": release_listener, "failures": failures, "esc_bound": False}
