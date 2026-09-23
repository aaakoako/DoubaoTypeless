"""具体输入控件身份与焦点恢复。

UIA对象只在创建它的COM线程内使用；跨线程仅传数值指纹，不传COM指针。
不能取得具体控件时，本机只允许用户主动触发的纯文字，远端拒绝。
"""
from __future__ import annotations

from contextlib import contextmanager
import sys
from typing import NamedTuple


class FocusSnapshot(NamedTuple):
    class_name: str
    title: str
    hwnd: int
    pid: int = 0
    control_hwnd: int = 0
    runtime_id: tuple[int, ...] = ()
    kind: str = "unknown"


_INSIDE_HELPER = False
_AUTOMATION_ROOT = None


@contextmanager
def automation():
    """仅在自建MTA辅助进程调用，保持COM根对象到进程退出，不逐次拆公寓。"""
    global _AUTOMATION_ROOT
    if not _INSIDE_HELPER:
        raise RuntimeError("UIA must run in the isolated helper")
    if _AUTOMATION_ROOT is None:
        import comtypes.client
        module = comtypes.client.GetModule("UIAutomationCore.dll")
        _AUTOMATION_ROOT = comtypes.client.CreateObject(
            "{FF48DBA4-60EF-4201-AA87-54103EEF594E}", interface=module.IUIAutomation)
    yield _AUTOMATION_ROOT


def property_value(element, name: str, fallback=None):
    try:
        return getattr(element, name)
    except Exception:
        return fallback


def runtime_id(element) -> tuple[int, ...]:
    try:
        return tuple(int(v) for v in element.GetRuntimeId())
    except Exception:
        return ()


def classify_element(descriptors: list[dict]) -> str:
    """只判断当前可编辑控件，祖先只用于阻止代码/终端和定位消息框。"""
    if not descriptors:
        return "unknown"
    item = descriptors[0]
    if item.get("password"):
        return "password"
    if item.get("readonly") is True:
        return "readonly"
    # Ancestor names can include the conversation/project title. A task called
    # "PowerShell" does not turn its message input into a terminal.
    context = (" ".join(str(d.get(k) or "") for d in descriptors
                       for k in ("class_name", "automation_id")) + " " + str(item.get('name') or '')).lower()
    if any(k in context for k in ("monaco", "scintilla", "codeditor", "editordocument", "view-lines")):
        return "code"
    if any(k in context for k in ("terminal", "powershell", "cmd.exe", "consolewindowclass")):
        return "terminal"
    editable = item.get("control_type") == 50004 or item.get("value_editable")
    editable = editable or (item.get("control_type") == 50030 and item.get("keyboard_focusable") is True
                            and item.get("readonly") is False)
    if not editable or not item.get("enabled", True) or item.get("offscreen"):
        return "unknown"
    from doubao_typeless.platform.windows.composer_locator import composer_candidate
    if composer_candidate(descriptors):
        return "composer"
    if any(k in context for k in ("composer", "chatinput", "promptinput", "prompt-textarea",
                                  "ask anything", "send a message", "message", "prompt", "发送消息", "输入消息", "询问任何")):
        return "composer"
    return "edit"


def describe(element) -> dict:
    editable = False
    readonly = None
    try:
        # UIA_IsValuePatternAvailablePropertyId=30043, Value.IsReadOnly=30046.
        available = bool(element.GetCurrentPropertyValue(30043))
        readonly = bool(element.GetCurrentPropertyValue(30046)) if available else None
        editable = available and readonly is False
    except Exception:
        pass
    return {
        "class_name": str(property_value(element, "CurrentClassName", "") or ""),
        "name": str(property_value(element, "CurrentName", "") or "")[:512],
        "automation_id": str(property_value(element, "CurrentAutomationId", "") or ""),
        "control_type": int(property_value(element, "CurrentControlType", 0) or 0),
        "password": bool(property_value(element, "CurrentIsPassword", False)),
        "enabled": bool(property_value(element, "CurrentIsEnabled", False)),
        "offscreen": bool(property_value(element, "CurrentIsOffscreen", False)),
        "keyboard_focusable": bool(property_value(element, "CurrentIsKeyboardFocusable", False)),
        "value_editable": editable,
        "readonly": readonly,
    }


def focused_chain(uia, element, limit: int = 6):
    chain = []
    current = element
    for _ in range(limit):
        if not current:
            break
        chain.append((current, describe(current)))
        try:
            current = uia.ControlViewWalker.GetParentElement(current)
        except Exception:
            break
    return chain


def _read_target_direct() -> FocusSnapshot:
    if sys.platform != "win32":
        return FocusSnapshot("", "", 0)
    import win32gui
    import win32process
    from doubao_typeless.core.policy import classify_focus
    hwnd = int(win32gui.GetForegroundWindow() or 0)
    if not hwnd:
        return FocusSnapshot("", "", 0)
    cls, title = win32gui.GetClassName(hwnd), win32gui.GetWindowText(hwnd)
    _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
    base_kind = classify_focus(cls, title)
    try:
        with automation() as uia:
            element = uia.GetFocusedElement()
            if not element or int(element.CurrentProcessId) != int(pid):
                return FocusSnapshot(cls, title, hwnd, pid)
            chain = focused_chain(uia, element)
            kind = classify_element([d for _, d in chain])
            structural_kind = classify_focus(cls, "")
            if structural_kind in {"code", "terminal", "paste"}:
                kind = structural_kind
            elif kind == "unknown" and base_kind in {"code", "terminal", "paste"}:
                kind = base_kind
            return FocusSnapshot(cls, title, hwnd, pid,
                int(property_value(element, "CurrentNativeWindowHandle", 0) or 0), runtime_id(element), kind)
    except Exception:
        # UIA不可用时仍能复制；不猜一个Composer来放行图片。
        return FocusSnapshot(cls, title, hwnd, pid,
            kind=base_kind if base_kind in {"code", "terminal", "paste"} else "unknown")


def same_target(left, right) -> bool:
    if not left or not right:
        return False
    if len(left) >= 7 and len(right) >= 7:
        # 标题可随着输入/网络变化，不能把动态标题当控件身份。
        return (left[2], left[3], left[4], tuple(left[5]), left[6]) == (
            right[2], right[3], right[4], tuple(right[5]), right[6])
    return tuple(left) == tuple(right)


def _restore_target_direct(saved) -> bool:
    """只恢复明确保存的那一个控件；不按同名窗口枚举兜底。"""
    if sys.platform != "win32" or len(saved) < 3 or not saved[2]:
        return False
    import win32gui
    import win32process
    hwnd = int(saved[2])
    if not win32gui.IsWindow(hwnd):
        return False
    if len(saved) > 3 and win32process.GetWindowThreadProcessId(hwnd)[1] != saved[3]:
        return False
    try:
        win32gui.SetForegroundWindow(hwnd)
        if len(saved) > 5 and saved[5]:
            with automation() as uia:
                root = uia.ElementFromHandle(hwnd)
                # CompareElements依赖活对象；根据稳定RuntimeId找回，不按文本/坐标猜测。
                expected = tuple(saved[5])
                todo, count = [root], 0
                while todo and count < 600:
                    element = todo.pop(); count += 1
                    if runtime_id(element) == expected:
                        element.SetFocus()
                        break
                    child = uia.ControlViewWalker.GetFirstChildElement(element)
                    while child and len(todo) + count < 600:
                        todo.append(child)
                        child = uia.ControlViewWalker.GetNextSiblingElement(child)
                else:
                    return False
        current = _read_target_direct()
        return same_target(saved, current) if len(saved) > 3 else current.hwnd == hwnd
    except Exception:
        return False


def read_target() -> FocusSnapshot:
    if sys.platform != "win32":
        return FocusSnapshot("", "", 0)
    import os
    import win32gui, win32process
    from doubao_typeless.platform.windows.automation_host import host, TargetProbeError
    hwnd = int(win32gui.GetForegroundWindow() or 0)
    if not hwnd:
        return FocusSnapshot("", "", 0)
    pid = win32process.GetWindowThreadProcessId(hwnd)[1]
    cls, title = win32gui.GetClassName(hwnd), win32gui.GetWindowText(hwnd)
    # 不让UIA查询自身窗口，避免GUI线程等待自己的无障碍请求。
    if pid == os.getpid():
        return FocusSnapshot(cls, title, hwnd, pid)
    result = host().call("focus")
    snap = FocusSnapshot(*result[:5], tuple(result[5]), result[6])
    if int(win32gui.GetForegroundWindow() or 0) != hwnd or snap.hwnd != hwnd or snap.pid != pid:
        raise TargetProbeError("TARGET_CHANGED")
    return snap


def restore_target(saved) -> bool:
    if sys.platform != "win32" or len(saved) < 3 or not saved[2]:
        return False
    import win32gui, win32process
    hwnd = int(saved[2])
    if not win32gui.IsWindow(hwnd):
        return False
    if len(saved) > 3 and win32process.GetWindowThreadProcessId(hwnd)[1] != saved[3]:
        return False
    try:
        # 前台申请仍由用户正在操作的主程序做，不让辅助进程抢窗口。
        win32gui.SetForegroundWindow(hwnd)
        from doubao_typeless.platform.windows.automation_host import host
        return bool(host().call("restore", {"saved": list(saved)}))
    except Exception:
        return False
