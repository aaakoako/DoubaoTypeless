"""Alt+I insert, Alt+Shift+I recall. No Enter."""
from __future__ import annotations

from typing import Callable


from doubao_typeless.core.hotkey_gate import HotkeyGate


def start_hotkeys(
    *,
    on_insert: Callable[[], None],
    on_recall: Callable[[], None],
    on_region: Callable[[], None] | None = None,
    insert_combo: str = "<alt>+i",
    recall_combo: str = "<alt>+<shift>+i",
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
        insert_combo or "<alt>+i": wrap(insert_gate, on_insert),
        recall_combo or "<alt>+<shift>+i": wrap(recall_gate, on_recall),
    }
    if on_region:
        mapping["<alt>+<shift>+s"] = wrap(region_gate, on_region)
    try:
        listener = GlobalHotKeys(mapping)
        listener.start()
    except Exception as exc:
        failures.append(f"热键注册失败，不会把语法合法当成成功: {exc}")
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


def probe_hotkey_conflicts() -> dict:
    """RegisterHotKey probe. Syntax-legal combos can still be occupied."""
    import sys

    result = {"insert": "unknown", "recall": "unknown", "hint": "失败请改键，语法合法不等于注册成功", "esc_bound": False}
    if sys.platform != "win32":
        result["insert"] = "unsupported"
        result["recall"] = "unsupported"
        return result
    import ctypes

    user32 = ctypes.windll.user32
    MOD_ALT = 0x0001
    MOD_SHIFT = 0x0004
    VK_I = 0x49

    def _probe(ident: int, mods: int) -> str:
        ok = user32.RegisterHotKey(None, ident, mods, VK_I)
        if ok:
            user32.UnregisterHotKey(None, ident)
            return "free"
        return "conflict"

    result["insert"] = _probe(0xD701, MOD_ALT)
    result["recall"] = _probe(0xD702, MOD_ALT | MOD_SHIFT)
    return result
