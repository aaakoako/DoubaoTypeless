"""Cursor Composer adapter. G0 observation is not closed; do not fake CONFIRMED."""
from __future__ import annotations

from doubao_typeless.core.policy import classify_focus


def identify(class_name: str, control_type: str = "", automation_id: str = "") -> str:
    kind = classify_focus(class_name, control_type, automation_id)
    if kind == "composer":
        return "cursor_windows"
    if kind == "code":
        return "unsupported_code"
    return "generic_text"


def observe_image() -> str:
    # 未闭合 Composer UIA 附件观察时必须 UNKNOWN，不能把粘贴成功当接收。
    return "unknown"


def observe_text() -> str:
    return "unknown"
