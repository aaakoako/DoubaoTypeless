"""Cursor Composer adapter. UIA observation is required for CONFIRMED; otherwise UNKNOWN."""
from __future__ import annotations

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
    """Walk focused UI Automation tree. Missing Cursor is not a PASS."""
    report: dict = {
        "cursor_windows": cursor_windows(),
        "focus": None,
        "composer_control": None,
        "image_children": None,
        "text_value": None,
        "engine": None,
        "error": None,
    }
    try:
        import pythoncom
        from win32com.client import Dispatch

        pythoncom.CoInitialize()
        uia = None
        for progid in ("CUIAutomation", "UIAutomationClient.CUIAutomation"):
            try:
                uia = Dispatch(progid)
                report["engine"] = progid
                break
            except Exception as exc:
                report["error"] = f"{progid}: {exc}"
        if uia is None:
            return report
        focused = uia.GetFocusedElement()
        if focused is None:
            report["error"] = "no focused element"
            return report
        name = str(focused.CurrentName or "")
        aid = str(getattr(focused, "CurrentAutomationId", "") or "")
        ctype = str(focused.CurrentClassName or "")
        report["focus"] = {"name": name, "automation_id": aid, "class_name": ctype}
        blob = f"{name} {aid} {ctype}".lower()
        if any(h in blob for h in COMPOSER_HINTS) and not any(h in blob for h in CODE_HINTS):
            report["composer_control"] = report["focus"]
            try:
                report["text_value"] = str(focused.CurrentValue or "")
            except Exception:
                report["text_value"] = None
        return report
    except Exception as exc:
        report["error"] = str(exc)
        report["engine"] = None
        return report


def observe_image() -> str:
    report = probe_uia()
    if not report.get("composer_control"):
        return "unknown"
    # 附件树未闭合前不能把粘贴成功当接收。
    return "unknown"


def observe_text() -> str:
    report = probe_uia()
    if not report.get("composer_control"):
        return "unknown"
    return "unknown"
