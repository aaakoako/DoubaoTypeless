from __future__ import annotations

from doubao_typeless.platform.windows.clipboard import read_focus
from doubao_typeless.core.policy import classify_focus


def current_kind() -> str:
    class_name, title = read_focus()
    return classify_focus(class_name, title)
