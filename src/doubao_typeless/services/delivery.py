"""Windows delivery: images then text, never Enter."""
from __future__ import annotations

import time
from typing import Callable

from doubao_typeless.core.attempt import Attempt, Step
from doubao_typeless.core.policy import classify_focus, may_inject

VK_CONTROL = 0x11
VK_V = 0x56
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002


class DeliveryService:
    def __init__(
        self,
        *,
        paste: Callable[[], None],
        set_clipboard_image: Callable[[bytes], None],
        set_clipboard_text: Callable[[str], None],
        read_focus: Callable[[], tuple[str, str]],
        observe_image: Callable[[], str] | None = None,
        observe_text: Callable[[], str] | None = None,
        send_key: Callable[[int, bool], None] | None = None,
    ):
        self._paste = paste
        self._set_image = set_clipboard_image
        self._set_text = set_clipboard_text
        self._read_focus = read_focus
        self._observe_image = observe_image
        self._observe_text = observe_text
        self._send_key = send_key
        self.enter_count = 0

    def run(
        self,
        attempt: Attempt,
        bundle: dict,
        *,
        mode: str = "full",
        skip_asset_ids: set[str] | None = None,
    ) -> Attempt:
        class_name, control = self._read_focus()
        kind = classify_focus(class_name, control)
        assets = list(bundle.get("assets") or [])
        skip_asset_ids = skip_asset_ids or set()
        if mode == "text_only":
            assets = []
        elif mode == "remaining_verified":
            assets = [a for a in assets if a.get("asset_id") not in skip_asset_ids]
        elif mode == "cancel":
            attempt.result = "CANCELLED"
            return attempt
        wants_images = bool(assets)
        if not may_inject(kind, wants_images=wants_images):
            attempt.result = "NO_STEPS"
            attempt.error_code = "NEEDS_TARGET"
            return attempt
        index = 0
        for asset in assets:
            class_name, control = self._read_focus()
            if classify_focus(class_name, control) != kind:
                attempt.result = "PARTIAL" if attempt.steps else "NO_STEPS"
                attempt.error_code = "TARGET_CHANGED"
                return attempt
            self._set_image(asset["bytes_data"] if "bytes_data" in asset else b"")
            self._paste()
            evidence = "os_input_count"
            state = "injected"
            if self._observe_image:
                observed = self._observe_image()
                if observed == "observed":
                    state, evidence = "observed", "target_attachment"
                elif observed == "unknown":
                    state, evidence = "unknown", "none"
                    attempt.steps.append(Step(index, "image", asset["asset_id"], state, evidence))
                    attempt.result = "UNKNOWN"
                    return attempt
            else:
                state, evidence = "unknown", "none"
                attempt.steps.append(Step(index, "image", asset["asset_id"], state, evidence))
                attempt.result = "UNKNOWN"
                return attempt
            attempt.steps.append(Step(index, "image", asset["asset_id"], state, evidence))
            index += 1
        text = bundle.get("text") or ""
        if text:
            class_name, control = self._read_focus()
            if classify_focus(class_name, control) != kind:
                attempt.result = "PARTIAL" if attempt.steps else "NO_STEPS"
                attempt.error_code = "TARGET_CHANGED"
                return attempt
            self._set_text(text)
            self._paste()
            if self._observe_text:
                observed = self._observe_text()
                state = "observed" if observed == "observed" else "unknown"
                evidence = "target_text" if state == "observed" else "none"
            else:
                state, evidence = "injected", "os_input_count"
            attempt.steps.append(Step(index, "text", None, state, evidence))
        if self._send_key:
            # 明确禁止 Enter：接口存在也不调用 VK_RETURN
            pass
        try:
            attempt.confirm_if_observed()
        except ValueError:
            if attempt.steps and all(s.state in {"injected", "observed"} for s in attempt.steps):
                attempt.result = "UNKNOWN"
        if attempt.result == "RUNNING":
            attempt.result = "UNKNOWN"
        return attempt
