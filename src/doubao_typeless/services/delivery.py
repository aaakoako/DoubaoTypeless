"""Windows delivery: images then text, never Enter."""
from __future__ import annotations

from typing import Callable

from doubao_typeless.core.attempt import Attempt, Step
from doubao_typeless.core.policy import classify_focus, may_inject
from doubao_typeless.platform.windows.guards import clipboard_still_ours

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
        wait_modifiers: Callable[[], bool] | None = None,
        is_locked: Callable[[], bool] | None = None,
        is_elevated: Callable[[], bool] | None = None,
        read_clipboard_text: Callable[[], str | None] | None = None,
        prepare_image: Callable[[], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ):
        self._paste = paste
        self._set_image = set_clipboard_image
        self._set_text = set_clipboard_text
        self._read_focus = read_focus
        self._observe_image = observe_image
        self._observe_text = observe_text
        self._send_key = send_key
        self._wait_modifiers = wait_modifiers or (lambda: True)
        self._is_locked = is_locked or (lambda: False)
        self._is_elevated = is_elevated or (lambda: False)
        self._read_clipboard_text = read_clipboard_text
        self._prepare_image = prepare_image
        self._is_cancelled = is_cancelled or (lambda: False)
        self.enter_count = 0

    def run(
        self,
        attempt: Attempt,
        bundle: dict,
        *,
        mode: str = "full",
        skip_asset_ids: set[str] | None = None,
        remote: bool = False,
    ) -> Attempt:
        focus = self._read_focus()
        class_name = focus[0] if focus else ""
        control = focus[1] if len(focus) > 1 else ""
        kind = getattr(focus, "kind", None) or (str(focus[6]) if len(focus) > 6 else classify_focus(class_name, control))
        assets = list(bundle.get("assets") or [])
        skip_asset_ids = skip_asset_ids or set()
        if mode == "text_only":
            assets = []
        elif mode == "remaining_verified":
            assets = [a for a in assets if a.get("asset_id") not in skip_asset_ids]
        if mode == "cancel":
            attempt.result = "CANCELLED"
            return attempt
        if self._is_locked():
            attempt.result = "NO_STEPS"
            attempt.error_code = "SESSION_LOCKED"
            return attempt
        if self._is_elevated():
            attempt.result = "NO_STEPS"
            attempt.error_code = "TARGET_ELEVATED"
            return attempt
        wants_images = bool(assets)
        if not may_inject(kind, wants_images=wants_images, remote=remote):
            attempt.result = "NO_STEPS"
            attempt.error_code = "NEEDS_TARGET"
            return attempt
        index = len(attempt.steps)
        for asset in assets:
            current = self._read_focus()
            if current != focus:
                attempt.result = "PARTIAL" if attempt.steps else "NO_STEPS"
                attempt.error_code = "TARGET_CHANGED"
                return attempt
            if self._prepare_image:
                self._prepare_image()
            self._set_image(asset["bytes_data"] if "bytes_data" in asset else b"")
            if not self._wait_modifiers():
                attempt.result = "PARTIAL" if attempt.steps else "NO_STEPS"
                attempt.error_code = "MODIFIERS_HELD"
                return attempt
            current = self._read_focus()
            if current != focus:
                attempt.result = "PARTIAL" if attempt.steps else "NO_STEPS"
                attempt.error_code = "TARGET_CHANGED"
                return attempt
            step = Step(index, "image", asset["asset_id"], "unknown", "none")
            attempt.steps.append(step)
            if self._is_cancelled():
                # 已创建但尚未执行的当前步骤不算发出。
                attempt.steps.pop()
                attempt.result = "PARTIAL" if attempt.steps else "CANCELLED"
                attempt.error_code = "SHUTTING_DOWN"
                return attempt
            self._paste()
            evidence = "os_input_count"
            state = "injected"
            if self._observe_image:
                observed = self._observe_image()
                if observed == "observed":
                    state, evidence = "observed", "target_attachment"
                elif observed == "unknown":
                    state, evidence = "unknown", "none"
                    step.state, step.evidence = state, evidence
                    attempt.result = "UNKNOWN"
                    return attempt
            else:
                state, evidence = "unknown", "none"
                step.state, step.evidence = state, evidence
                attempt.result = "UNKNOWN"
                return attempt
            step.state, step.evidence = state, evidence
            index += 1
        text = bundle.get("text") or ""
        if text:
            if self._read_focus() != focus:
                attempt.result = "PARTIAL" if attempt.steps else "NO_STEPS"
                attempt.error_code = "TARGET_CHANGED"
                return attempt
            self._set_text(text)
            if self._read_clipboard_text is not None and not clipboard_still_ours(text, self._read_clipboard_text()):
                attempt.result = "UNKNOWN"
                attempt.error_code = "CLIPBOARD_INTERFERENCE"
                return attempt
            if not self._wait_modifiers():
                attempt.result = "PARTIAL" if attempt.steps else "NO_STEPS"
                attempt.error_code = "MODIFIERS_HELD"
                return attempt
            if self._read_focus() != focus:
                attempt.result = "PARTIAL" if attempt.steps else "NO_STEPS"
                attempt.error_code = "TARGET_CHANGED"
                return attempt
            if self._read_clipboard_text is not None and not clipboard_still_ours(text, self._read_clipboard_text()):
                attempt.result, attempt.error_code = "UNKNOWN", "CLIPBOARD_INTERFERENCE"
                return attempt
            step = Step(index, "text", None, "unknown", "none")
            attempt.steps.append(step)
            if self._is_cancelled():
                # 已创建但尚未执行的当前步骤不算发出。
                attempt.steps.pop()
                attempt.result = "PARTIAL" if attempt.steps else "CANCELLED"
                attempt.error_code = "SHUTTING_DOWN"
                return attempt
            self._paste()
            if self._observe_text:
                observed = self._observe_text()
                state = "observed" if observed == "observed" else "unknown"
                evidence = "target_text" if state == "observed" else "none"
            else:
                state, evidence = "injected", "os_input_count"
            step.state, step.evidence = state, evidence
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
