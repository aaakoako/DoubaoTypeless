"""Focus and recovery policy. Process name is not Composer identity."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FocusKind = Literal["composer", "code", "terminal", "paste", "unknown", "other"]


@dataclass(frozen=True)
class TargetContext:
    hwnd: int
    pid: int
    class_name: str
    kind: FocusKind
    adapter: str


def classify_focus(class_name: str, control_type: str = "", automation_id: str = "") -> FocusKind:
    lowered = f"{class_name} {control_type} {automation_id}".lower()
    if any(token in lowered for token in ("terminal", "console", "vte", "pty")):
        return "terminal"
    if any(token in lowered for token in ("scintilla", "editordocument", "monaco", "codeditor")):
        return "code"
    if "dt-s2-pastetarget" in lowered:
        return "paste"
    if "composer" in lowered or "chatinput" in lowered or "promptinput" in lowered:
        return "composer"
    return "unknown"


OWN_WINDOW_MARKERS = (
    "dt-v3-hud",
    "doubaotypeless",
    "当前图文",
    "上次结果未知",
)


def is_own_window(class_name: str, title: str = "", automation_id: str = "") -> bool:
    blob = f"{class_name} {title} {automation_id}".lower()
    return any(token in blob for token in OWN_WINDOW_MARKERS)


def may_inject(kind: FocusKind, *, wants_images: bool, remote: bool = False) -> bool:
    if kind in {"composer", "paste"}:
        return True
    if kind in {"code", "terminal"}:
        return False
    if kind == "unknown" and remote:
        return False
    return not wants_images


def recovery_choice(previous_result: str, same_target: bool, images_observed: int, images_total: int, text_sent: bool) -> str:
    if previous_result in {"NO_STEPS", ""} and same_target:
        return "full"
    if same_target and images_observed == images_total and images_total and not text_sent:
        return "text_only"
    if same_target and 0 < images_observed < images_total:
        return "remaining_verified"
    return "ask"
