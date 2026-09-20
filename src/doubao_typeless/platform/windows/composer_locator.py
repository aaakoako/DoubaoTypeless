"""用户主动调用的 Composer 查找：只查询指定窗口，不全桌面猜测输入目标。

不读 Value/TextPattern 正文，不点击发送，不粘贴。结果仅含控件数值身份和
固定提示。多个候选/遍历不完整时拒绝自动选择。UIA 仍由既有辅助进程隔离。
"""
from __future__ import annotations

import time
from typing import Iterable

# 标签用于识别候选而非证明某产品兼容；真实应用仍需逐版本测试。
_ID_HINTS = ("prompt-textarea", "chat-input", "chatinput", "promptinput", "composer-input", "composerinput")
_NAME_HINTS = ("ask anything", "send a message", "type a message", "message chatgpt",
               "reply to claude", "问问 chatgpt", "问问chatgpt", "询问 chatgpt", "询问chatgpt", "向 chatgpt 发送消息", "message claude", "message input", "chat input", "ask a question", "输入消息", "发送消息", "询问任何问题")
_BLOCKED = ("search", "find", "搜索", "查找", "password", "密码", "terminal", "console", "monaco", "scintilla", "codeeditor")


def composer_candidate(descriptors: list[dict]) -> bool:
    """仅靠当前元素的可编辑属性与明确名称，不把祖先整段文本当证据。"""
    if not descriptors:
        return False
    item = descriptors[0]
    if item.get("password") or item.get("readonly") is True:
        return False
    if item.get("enabled") is not True or item.get("offscreen") is True:
        return False
    editable = item.get("control_type") == 50004 or item.get("value_editable") is True
    # 浏览器富文本可能暴露为 Document。必须明确可聚焦且有编辑语义。
    editable |= (item.get("control_type") == 50030 and item.get("keyboard_focusable") is True
                 and item.get("readonly") is False)
    if not editable:
        return False
    identity = " ".join(str(item.get(k) or "") for k in ("automation_id", "class_name")).lower()
    label = " ".join(str(item.get("name") or "").lower().split())
    context = " ".join(str(d.get(k) or "") for d in descriptors[:4]
                       for k in ("automation_id", "class_name")).lower()
    if any(token in context + " " + label for token in _BLOCKED):
        return False
    # 不采用泛化的 'prompt'/'message' 子串，避免日志区、列表和搜索框误中。
    known_id = any(token in identity for token in _ID_HINTS)
    known_label = label in _NAME_HINTS
    return bool(known_id or known_label)


def choose_candidate(candidates: Iterable[dict], *, complete: bool, remembered: list | tuple | None = None) -> dict:
    unique = {}
    for item in candidates:
        key = (int(item["hwnd"]), int(item["pid"]), tuple(item["runtime_id"]))
        if key[0] and key[1] and key[2]:
            unique[key] = item
    items = list(unique.values())
    if remembered and len(remembered) >= 6 and remembered[5]:
        match = unique.get((int(remembered[2]), int(remembered[3]), tuple(remembered[5])))
        if match:
            return {"status": "found", "candidate": match, "reason": "remembered_exact"}
    if not complete:
        return {"status": "incomplete", "candidates": items}
    if len(items) == 1:
        return {"status": "found", "candidate": items[0], "reason": "unique_in_window"}
    return {"status": "ambiguous" if items else "not_found", "candidates": items}


def discover_direct(hwnd: int, pid: int, remembered=None) -> dict:
    """必须在既有UIA辅助进程调用。窗口/进程稳定且完整遍历才判唯一。"""
    import win32gui, win32process
    from doubao_typeless.platform.windows.focus import automation, describe, runtime_id
    if not hwnd or not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
        return {"status": "not_found"}
    if win32process.GetWindowThreadProcessId(hwnd)[1] != pid:
        return {"status": "changed"}
    with automation() as uia:
        root = uia.ElementFromHandle(hwnd)
        todo = [(root, [], 0)]
        candidates = []
        complete = True
        inspected = 0
        deadline = time.monotonic() + 0.45
        walker = uia.ControlViewWalker
        while todo:
            if inspected >= 600 or time.monotonic() >= deadline:
                complete = False
                break
            element, parents, depth = todo.pop()
            inspected += 1
            current = describe(element)
            chain = [current, *parents[:3]]
            if composer_candidate(chain):
                rid = runtime_id(element)
                if rid:
                    candidates.append({"hwnd": hwnd, "pid": pid, "runtime_id": list(rid),
                        "control_hwnd": int(getattr(element, "CurrentNativeWindowHandle", 0) or 0),
                        "class_name": win32gui.GetClassName(hwnd), "title": win32gui.GetWindowText(hwnd),
                        "kind": "composer", "label": f"对话输入框 {len(candidates)+1}"})
            # 深度上限意味着不能证明扫描完整，不能把所见第一个当成唯一。
            child = walker.GetFirstChildElement(element)
            if child and depth >= 14:
                complete = False
                continue
            while child:
                if len(todo) + inspected >= 600 or time.monotonic() >= deadline:
                    complete = False
                    break
                todo.append((child, chain, depth + 1))
                child = walker.GetNextSiblingElement(child)
        return choose_candidate(candidates, complete=complete, remembered=remembered)


def locate_current(remembered=None) -> dict:
    """只返回候选，焦点移动由主进程在用户动作后执行并再次验证。"""
    import os, sys
    if sys.platform != "win32":
        return {"status": "unsupported"}
    import win32gui, win32process
    from doubao_typeless.platform.windows.automation_host import host
    hwnd = int(win32gui.GetForegroundWindow() or 0)
    pid = win32process.GetWindowThreadProcessId(hwnd)[1] if hwnd else 0
    if pid == os.getpid():
        if not remembered or len(remembered) < 4:
            return {"status": "not_found"}
        hwnd, pid = int(remembered[2]), int(remembered[3])
    return host().call("find_composer", {"hwnd": hwnd, "pid": pid,
                                         "remembered": list(remembered) if remembered else None})
