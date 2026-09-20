"""Cursor Composer adapter. UIA observation is required for CONFIRMED; otherwise UNKNOWN."""
from __future__ import annotations
import time

from doubao_typeless.core.policy import classify_focus

try:
    import win32gui
except ImportError:  # pragma: no cover
    win32gui = None


COMPOSER_HINTS = ("composer", "chatinput", "promptinput", "aicreator")
CODE_HINTS = ("scintilla", "editordocument", "monaco", "codeditor")


def identify(class_name: str, control_type: str = "", automation_id: str = "") -> str:
    kind = classify_focus(class_name, control_type, automation_id)
    if kind == "composer":
        return "cursor_windows"
    if kind == "code":
        return "unsupported_code"
    return "generic_text"


def cursor_windows() -> list[dict]:
    if win32gui is None:
        return []
    found: list[dict] = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if "cursor" in title.lower() or class_name.startswith("Chrome_WidgetWin"):
            if title:
                found.append({"hwnd": int(hwnd), "title": title, "class_name": class_name})
        return True

    win32gui.EnumWindows(cb, None)
    return [w for w in found if "cursor" in w["title"].lower()]


def probe_uia() -> dict:
    """通过UIA类型库调用真实接口；失败保持unknown，不按进程名猜输入框。"""
    report = {"cursor_windows": [], "focus": None, "composer_control": None,
              "image_children": [], "text_value": None, "engine": None, "error": None}
    if win32gui is None:
        return report
    try:
        from doubao_typeless.platform.windows.focus import automation, focused_chain, runtime_id, classify_element
        with automation() as uia:
            focused = uia.GetFocusedElement()
            if not focused:
                return report
            chain = focused_chain(uia, focused, limit=5)
            kind = classify_element([desc for _, desc in chain])
            report["engine"] = "IUIAutomation"
            report["focus"] = {"runtime_id": runtime_id(focused), "pid": int(focused.CurrentProcessId)}
            if kind != "composer":
                return report
            report["composer_control"] = report["focus"]
            # 附件常在输入控件的同级容器。最多取明确的composer祖先，
            # 不扫描整个窗口/桌面并把其他对话里的图片当作附件。
            container = chain[1][0] if len(chain) > 1 else focused
            for element, desc in chain[1:4]:
                identity = f"{desc['automation_id']} {desc['class_name']}".lower()
                if any(token in identity for token in ("composer", "chatinput", "promptinput")):
                    container = element
                    break
            report["image_children"] = _collect_image_children(uia, container)
            return report
    except Exception as exc:
        report["error"] = type(exc).__name__
        return report


def _collect_image_children(uia, element, *, depth: int = 0, found: list | None = None, budget: list | None = None) -> list:
    found = found if found is not None else []
    budget = budget if budget is not None else [0, time.monotonic() + .3]
    budget[0] += 1
    if depth > 8 or len(found) >= 8 or budget[0] > 256 or time.monotonic() > budget[1]:
        return found
    try:
        ctl = str(getattr(element, "CurrentControlType", "") or "")
        name = str(getattr(element, "CurrentName", "") or "")
        cls = str(getattr(element, "CurrentClassName", "") or "")
        blob = f"{ctl} {name} {cls}".lower()
        if ctl == "50006":
            try:
                runtime_id = list(element.GetRuntimeId())
            except Exception:
                runtime_id = []
            found.append({"name": name, "class_name": cls, "control_type": ctl,
                          "runtime_id": runtime_id,
                          "pending": any(x in blob for x in ("uploading", "loading", "failed", "上传中", "失败"))})
    except Exception:
        pass
    try:
        walker = uia.ControlViewWalker
        child = walker.GetFirstChildElement(element)
        while child and len(found) < 8 and budget[0] < 256 and time.monotonic() <= budget[1]:
            _collect_image_children(uia, child, depth=depth + 1, found=found, budget=budget)
            child = walker.GetNextSiblingElement(child)
    except Exception:
        pass
    return found


def capture_image_baseline() -> dict:
    """只做投递前采样；没有可比的具体节点ID时，不承诺自动确认。"""
    report = probe_uia()
    if win32gui is not None:
        report["window"] = int(win32gui.GetForegroundWindow() or 0)
    return report


def observe_image(baseline: dict | None = None, *, timeout_s: float = 1.5) -> str:
    if not baseline or not baseline.get("composer_control"):
        return "unknown"
    previous = {tuple(n["runtime_id"]) for n in baseline.get("image_children") or [] if n.get("runtime_id")}
    deadline = time.monotonic() + max(0, timeout_s)
    stable = None
    while True:
        report = capture_image_baseline()
        if report.get("window") != baseline.get("window") or report.get("focus") != baseline.get("focus"):
            return "unknown"
        candidates = {tuple(n["runtime_id"]) for n in report.get("image_children") or []
                      if n.get("runtime_id") and n.get("control_type") == "50006" and not n.get("pending")}
        added = candidates - previous
        if added and added == stable:
            return "observed"
        stable = added
        if time.monotonic() >= deadline:
            return "unknown"
        time.sleep(0.075)


def observe_text() -> str:
    report = probe_uia()
    if not report.get("composer_control"):
        return "unknown"
    if report.get("text_value"):
        return "observed"
    return "unknown"
