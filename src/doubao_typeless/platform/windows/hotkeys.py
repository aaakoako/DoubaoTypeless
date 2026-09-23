"""Alt+I insert, Alt+Shift+I recall. No Enter."""
from __future__ import annotations

from typing import Callable
import sys


from doubao_typeless.core.hotkey_gate import HotkeyGate


def start_hotkeys(**kwargs):
    """Windows 使用真实系统注册；其他环境保留非产品的兼容测试路径。"""
    if sys.platform == "win32":
        from doubao_typeless.platform.windows.native_hotkeys import start_native_hotkeys
        return start_native_hotkeys(**kwargs)
    return _start_pynput_hotkeys(**kwargs)


def _start_pynput_hotkeys(
    *,
    on_insert: Callable[[], None],
    on_recall: Callable[[], None],
    on_expand: Callable[[], None] | None = None,
    on_region: Callable[[], None] | None = None,
    insert_combo: str = "<alt>+i",
    recall_combo: str = "<alt>+<shift>+i",
    expand_combo: str = "<alt>+<shift>+e",
    capture_combo: str = "<alt>+<shift>+s",
):
    from pynput.keyboard import GlobalHotKeys, HotKey, Listener

    insert_gate = HotkeyGate()
    recall_gate = HotkeyGate()
    region_gate = HotkeyGate()
    failures: list[str] = []

    def wrap(gate: HotkeyGate, fn: Callable[[], None]):
        def _inner():
            if gate.press():
                try:
                    fn()  # 正式调用者只提交队列或GUI信号，不在钩子执行投递。
                except Exception as exc:
                    from doubao_typeless.runtime_diagnostics import record_runtime_exception
                    record_runtime_exception("hotkey_dispatch", exc)

        return _inner

    mapping = {
        insert_combo or "<alt>+i": wrap(insert_gate, on_insert),
        recall_combo or "<alt>+<shift>+i": wrap(recall_gate, on_recall),
    }
    expand_gate = HotkeyGate()
    if on_expand:
        mapping[expand_combo or "<alt>+<shift>+e"] = wrap(expand_gate, on_expand)
    if on_region:
        mapping[capture_combo or "<alt>+<shift>+s"] = wrap(region_gate, on_region)
    try:
        listener = GlobalHotKeys(mapping)
        listener.start()
    except Exception as exc:
        failures.append(f"热键注册失败，不会把语法合法当成成功: {exc}")
        listener = None

    # 按实际配置的组合释放，不能把用户改成Ctrl+Q后仍只识别I/S/E。
    configured = [(insert_combo or "<alt>+i", insert_gate),
                  (recall_combo or "<alt>+<shift>+i", recall_gate)]
    if on_expand:
        configured.append((expand_combo or "<alt>+<shift>+e", expand_gate))
    if on_region:
        configured.append((capture_combo or "<alt>+<shift>+s", region_gate))
    release_keys = []
    for combo, gate in configured:
        try:
            release_keys.append((set(HotKey.parse(combo)), gate))
        except ValueError:
            failures.append("快捷键格式无效，请重新设置")

    def on_release(key):
        canonical = listener.canonical(key) if listener is not None else key
        for keys, gate in release_keys:
            if canonical in keys:
                gate.release()

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
