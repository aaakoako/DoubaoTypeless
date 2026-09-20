"""用户在手机确认后的独立发送动作。插入/重连/重试永远不调用此动作。

只对最近一次完整投递、来源设备、具体目标签发短期一次性票据。发送前先
原子保存已消耗记录；失去回执/平台部分执行均不重发。不是消息发送成功证明。
"""
from __future__ import annotations

import copy
import hashlib
import secrets
import threading
import time
from pathlib import Path

from doubao_typeless.core.bundle import source_snapshot
from doubao_typeless.platform.windows.focus import same_target
from doubao_typeless.storage.draft_snapshot import write_json_atomic

MODES = {"enter": "Enter", "ctrl_enter": "Ctrl+Enter"}


class PhoneSendService:
    TTL = 120.0

    def __init__(self, *, data_dir: Path, options, read_focus, wait_modifiers,
                 emit, authorize, current_draft, is_locked=lambda: False,
                 is_elevated=lambda: False, clock=time.monotonic):
        self.data_dir = Path(data_dir)
        self.options, self.read_focus, self.wait_modifiers = options, read_focus, wait_modifiers
        self.emit, self.authorize, self.current_draft = emit, authorize, current_draft
        self.is_locked, self.is_elevated, self.clock = is_locked, is_elevated, clock
        self._lock = threading.RLock()
        self._pending: dict[str, dict] = {}

    def record_delivery(self, bundle: dict, payload: dict, target) -> None:
        device = str(bundle.get("device_id") or "")
        if not device or device == "pc":
            return
        with self._lock:
            self._pending.pop(device, None)  # 一次新投递总会使上一份发送票据失效。
            if payload.get("error_code") or payload.get("duplicate") or payload.get("text_only"):
                return
            if payload.get("result") not in {"CONFIRMED", "UNKNOWN", "PARTIAL"}:
                return
            if not target or len(target) < 7 or target[6] not in {"composer", "edit"} or not target[5]:
                return
            planned = [a.get("asset_id") for a in bundle.get("assets") or []]
            steps = payload.get("steps") or []
            observed = [s.get("asset_id") for s in steps if s.get("kind") == "image" and s.get("state") == "observed"]
            text = str(bundle.get("text") or "")
            text_ok = not text or any(s.get("kind") == "text" and s.get("state") in {"observed", "injected"}
                                     and s.get("evidence") in {"target_text", "os_input_count"} for s in steps)
            if observed != planned or not text_ok or not (planned or text):
                return
            # 只保留内容身份，不把用户正文或图片复制进发送日志。
            self._pending[device] = {
                "delivery_id": secrets.token_hex(16), "target": copy.deepcopy(tuple(target)),
                "source": copy.deepcopy(bundle.get("source_snapshot")),
                "generation": int(bundle.get("generation") or 0),
                "expires": self.clock() + self.TTL, "token": None, "mode": None,
                "claimed": False, "result": None,
            }
            if len(self._pending) > 32:
                oldest = min(self._pending, key=lambda k: self._pending[k]["expires"])
                del self._pending[oldest]

    def _guard(self, device: str, item: dict | None) -> str:
        settings = self.options()
        if settings.get("phone_send_enabled") is not True:
            return "PHONE_SEND_DISABLED"
        if settings.get("phone_send_mode", "enter") not in MODES:
            return "INVALID_SEND_MODE"
        if not item or self.clock() > item["expires"]:
            return "SEND_EXPIRED"
        draft = self.current_draft()
        # 手机尚未收到轮换回执可仍是原稿，或已换成下一段空稿；新内容不能被旧发送操作跨越。
        if draft.editor_device_id != device:
            return "SEND_DRAFT_CHANGED"
        same = item["source"] is not None and source_snapshot(draft) == item["source"]
        next_empty = (draft.authority == "phone" and draft.generation == item["generation"] + 1
                      and not draft.text and not draft.assets)
        if not same and not next_empty:
            return "SEND_DRAFT_CHANGED"
        return ""

    def status(self, session) -> dict:
        with self._lock:
            self.authorize(session.session_id, session.token, "insert")
            item = self._pending.get(session.device_id)
            error = self._guard(session.device_id, item)
            return {"available": not error and bool(item and not item["claimed"]),
                    "error_code": error or ("SEND_ALREADY_USED" if item and item["claimed"] else ""),
                    "mode": self.options().get("phone_send_mode", "enter"),
                    "delivery_id": item["delivery_id"] if item and not error else None}

    def prepare(self, session) -> dict:
        with self._lock:
            self.authorize(session.session_id, session.token, "insert")
            item = self._pending.get(session.device_id)
            error = self._guard(session.device_id, item)
            if error:
                return {"error_code": error}
            if item["claimed"]:
                return {"error_code": "SEND_ALREADY_USED"}
            if not same_target(self.read_focus(), item["target"]):
                return {"error_code": "TARGET_CHANGED"}
            mode = self.options().get("phone_send_mode", "enter")
            # 每次打开确认框换新票据。旧框/旧请求不能重复发送。
            item["token"] = secrets.token_urlsafe(32)
            item["mode"] = mode
            return {"ticket": item["token"], "delivery_id": item["delivery_id"],
                    "shortcut": MODES[mode], "expires_in": max(0, int(item["expires"] - self.clock()))}

    def commit(self, session, body: dict) -> dict:
        with self._lock:
            self.authorize(session.session_id, session.token, "insert")
            item = self._pending.get(session.device_id)
            error = self._guard(session.device_id, item)
            if error:
                return {"error_code": error, "sent": False}
            ticket = body.get("ticket")
            if (body.get("confirmed") is not True or not isinstance(ticket, str) or len(ticket) > 128
                    or not item["token"] or not secrets.compare_digest(ticket, item["token"])
                    or body.get("delivery_id") != item["delivery_id"]):
                return {"error_code": "SEND_CONFIRMATION_REQUIRED", "sent": False}
            if item["claimed"]:
                return {**(item["result"] or {"result": "UNKNOWN", "sent": False}), "duplicate": True}
            if self.options().get("phone_send_mode", "enter") != item["mode"]:
                return {"error_code": "SEND_SETTINGS_CHANGED", "sent": False}
            if self.is_locked() or self.is_elevated():
                return {"error_code": "SEND_TARGET_UNAVAILABLE", "sent": False}
            if not same_target(self.read_focus(), item["target"]):
                return {"error_code": "TARGET_CHANGED", "sent": False}
            if not self.wait_modifiers():
                return {"error_code": "MODIFIERS_HELD", "sent": False}
            # 等待时可能撤权、换目标、编辑新稿或改设置，发键前全部再校验。
            self.authorize(session.session_id, session.token, "insert")
            error = self._guard(session.device_id, item)
            if error or not same_target(self.read_focus(), item["target"]):
                return {"error_code": error or "TARGET_CHANGED", "sent": False}
            if self.options().get("phone_send_mode", "enter") != item["mode"]:
                return {"error_code": "SEND_SETTINGS_CHANGED", "sent": False}
            item["claimed"] = True
            path = self.data_dir / "send-actions" / (item["delivery_id"] + ".json")
            journal = {"schema": 1, "delivery_id": item["delivery_id"], "mode": item["mode"],
                       "device_hash": hashlib.sha256(session.device_id.encode()).hexdigest(),
                       "state": "CLAIMED", "message_confirmed": False}
            try:
                write_json_atomic(path, journal)
            except Exception:
                item["result"] = {"sent": False, "error_code": "SEND_JOURNAL_FAILED", "result": "NO_STEPS"}
                return item["result"]
            try:
                # Durable IO may take time; authority and focus are rechecked after it.
                self.authorize(session.session_id, session.token, "insert")
                error = self._guard(session.device_id, item)
                if error or self.is_locked() or self.is_elevated():
                    raise ValueError(error or "SEND_TARGET_UNAVAILABLE")
                if self.options().get("phone_send_mode", "enter") != item["mode"]:
                    raise ValueError("SEND_SETTINGS_CHANGED")
                if not same_target(self.read_focus(), item["target"]):
                    raise ValueError("TARGET_CHANGED")
            except Exception:
                item["result"] = {"result":"NO_STEPS", "sent":False, "error_code":"SEND_PRECONDITION_CHANGED"}
                return item["result"]
            try:
                self.emit(item["mode"])
                result = {"result": "KEYS_SENT", "sent": True, "message_confirmed": False}
            except Exception:
                # 平台可能部分执行，消费掉票据，绝不重新发送按键。
                result = {"result": "UNKNOWN", "sent": False, "error_code": "SEND_RESULT_UNKNOWN"}
            item["result"] = result
            try:
                write_json_atomic(path, {**journal, "state": result["result"]})
            except Exception:
                pass  # CLAIMED仍阻止重放；进程重启不恢复发送票据。
            return result
