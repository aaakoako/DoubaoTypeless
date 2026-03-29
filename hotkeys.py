"""
全局快捷键：pynput GlobalHotKeys 格式，例如 "<ctrl>+<shift>+r"。
空字符串表示不注册该动作。无法检测与系统/其他软件占用的冲突，仅做格式与保留键校验。
"""

from __future__ import annotations

from typing import Callable, Optional


def normalize_hotkey(s: str) -> str:
    s = (s or "").strip().lower()
    return s.replace(" ", "")


_RESERVED = frozenset(
    {
        "<alt>+<f4>",
        "<ctrl>+<alt>+<delete>",
        "<ctrl>+<shift>+<esc>",
    }
)


def validate_hotkey_syntax(combo: str) -> tuple[bool, str]:
    combo = (combo or "").strip()
    if not combo:
        return True, ""
    try:
        from pynput.keyboard import HotKey

        HotKey.parse(combo)
    except Exception as e:
        return False, str(e)
    return True, ""


def check_reserved(combo: str) -> tuple[bool, str]:
    nk = normalize_hotkey(combo)
    if nk in _RESERVED:
        return False, "该组合为系统保留或高风险，请换一组键"
    if "f4" in nk and "<alt>" in nk:
        return False, "Alt+F4 类组合不可用"
    return True, ""


def check_internal_conflicts(mapping: dict[str, Callable]) -> tuple[bool, str]:
    """mapping: hotkey_str -> callback, 仅包含非空快捷键。"""
    seen: dict[str, str] = {}
    for raw in mapping:
        nk = normalize_hotkey(raw)
        if nk in seen:
            return False, f"内部冲突：{raw!r} 与 {seen[nk]!r} 等价"
        seen[nk] = raw
    return True, ""


def build_bindings(
    toggle_review: str,
    insert: str,
    on_toggle_review: Callable[[], None],
    on_insert: Callable[[], None],
) -> dict[str, Callable]:
    out: dict[str, Callable] = {}
    tr = (toggle_review or "").strip()
    ins = (insert or "").strip()
    if tr:
        out[tr] = on_toggle_review
    if ins:
        out[ins] = on_insert
    return out


def validate_all_for_save(
    toggle_review: str,
    insert: str,
) -> tuple[bool, str]:
    for label, combo in (
        ("唤起审阅窗口", toggle_review),
        ("插入并复制", insert),
    ):
        combo = (combo or "").strip()
        if not combo:
            continue
        ok, err = validate_hotkey_syntax(combo)
        if not ok:
            return False, f"{label}: {err}"
        ok, err = check_reserved(combo)
        if not ok:
            return False, f"{label}: {err}"
    mapping = build_bindings(toggle_review, insert, lambda: None, lambda: None)
    ok, err = check_internal_conflicts(mapping)
    if not ok:
        return False, err
    return True, ""


class GlobalHotkeyService:
    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        self._log = logger or (lambda _m: None)
        self._listener = None

    def start(self, bindings: dict[str, Callable]) -> bool:
        self.stop()
        if not bindings:
            self._log("[hotkey] 未配置全局快捷键")
            return True
        try:
            from pynput.keyboard import GlobalHotKeys

            self._listener = GlobalHotKeys(bindings)
            self._listener.daemon = True
            self._listener.start()
            self._log(f"[hotkey] 已注册 {len(bindings)} 个全局快捷键")
            return True
        except Exception as e:
            self._log(f"[hotkey] 注册失败: {e}")
            self._listener = None
            return False

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
