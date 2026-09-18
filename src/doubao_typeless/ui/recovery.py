"""Recovery copy vs replay. Ask when the previous result is unknown."""
from __future__ import annotations

from doubao_typeless.core.policy import recovery_choice


def plan_retry(
    *,
    previous_result: str,
    same_target: bool,
    images_observed: int,
    images_total: int,
    text_sent: bool,
    user_mode: str | None = None,
) -> dict:
    if previous_result == "UNKNOWN" and not user_mode:
        return {"mode": "ask", "auto_replay": False, "ctrl_a_delete": False}
    suggested = recovery_choice(
        previous_result, same_target, images_observed, images_total, text_sent
    )
    mode = user_mode or suggested
    if mode not in {"full", "text_only", "remaining_verified", "ask", "cancel"}:
        mode = "ask"
    return {
        "mode": mode,
        "auto_replay": False,
        "ctrl_a_delete": False,
        "suggested": suggested,
    }
