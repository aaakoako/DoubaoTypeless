"""Assemble Pocket Composer v3. Isolated data dir; idle HUD hidden."""
from __future__ import annotations

import asyncio
import os
import threading
import time
import uuid
from pathlib import Path

from doubao_typeless.core.attempt import Attempt
from doubao_typeless.core.bundle import Draft, archive_if_match, freeze_bundle
from doubao_typeless.core.intent import IntentLedger
from doubao_typeless.runtime import lan_ip, pick_port, v3_data_dir
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.services.byok import ByokService
from doubao_typeless.services.capture import CaptureService
from doubao_typeless.services.delivery import DeliveryService
from doubao_typeless.services.history import HistoryService
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService
from doubao_typeless.adapters.observable_target import from_env as observer_from_env
from doubao_typeless.ui.hud import HudController


_log_impl = print


def _log(message: str) -> None:
    _log_impl(str(message))


def set_log(fn) -> None:
    global _log_impl
    _log_impl = fn


class V3App:
    def __init__(self, *, data_dir: Path | None = None, port: int = 8766):
        self.data_dir = Path(data_dir or v3_data_dir())
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.port = pick_port(port) if port else 0
        self.auth = AuthService()
        self.store = AssetStore(self.data_dir / "assets")
        from doubao_typeless.storage.db import V3DB
        from doubao_typeless.services.assets import CHUNK, UploadService

        self.db = V3DB(self.data_dir / "v3.sqlite")
        raw_chunk = os.environ.get("DT_V3_CHUNK_SIZE", "").strip()
        chunk = int(raw_chunk) if raw_chunk.isdigit() and int(raw_chunk) >= 1024 else CHUNK
        self.uploads = UploadService(self.store, self.db, chunk_size=chunk)
        self.ledger = IntentLedger()
        self.draft = Draft(
            draft_id=str(uuid.uuid4()),
            epoch=str(uuid.uuid4()),
            revision=0,
            editor_device_id="pc",
            text="",
        )
        self.history = HistoryService(self.data_dir / "history.json", persist=True, db=self.db)
        from doubao_typeless.storage.settings_store import load_settings

        stored = load_settings(self.data_dir)
        self.byok = ByokService(endpoint=stored.get("byok_endpoint") or "", api_key=stored.get("byok_api_key") or "")
        self.hud = HudController(on_insert=self.insert_last, on_expand=lambda: self._notify_ui("expand"))
        self._observer = observer_from_env()
        self._last_attempt: Attempt | None = None
        self._recovery_needed = False
        self.review_editing = False
        self.phone_pending = None
        self.ui_hook = None
        from doubao_typeless.storage.draft_snapshot import load_draft, save_draft

        restored, missing = load_draft(self.data_dir, self.store)
        if restored is not None:
            self.draft = restored
            if missing:
                _log(f"[v3.draft] 快照缺图 {len(missing)}，不造假像素")
        self._save_draft = lambda: save_draft(self.data_dir, self.draft)
        self.bridge = V3Bridge(
            port=self.port,
            auth=self.auth,
            store=self.store,
            draft=self.draft,
            on_activity=self._on_activity,
            on_intent=self._on_intent,
            on_capture=self._on_capture,
            on_recall=self.recall_last,
            history_list=self._history_public,
            uploads=self.uploads,
            logger=_log,
            byok=self.byok,
            data_dir=self.data_dir,
        )
        self.capture = CaptureService(grab=self._grab, hide_surfaces=self.hud.hide)
        self.delivery = DeliveryService(
            paste=self._paste,
            set_clipboard_image=self._set_image,
            set_clipboard_text=self._set_text,
            read_focus=self._read_focus,
            observe_image=self._observe_image,
            observe_text=self._observe_text,
            wait_modifiers=self._wait_modifiers,
            is_locked=self._session_locked,
            is_elevated=self._target_elevated,
            read_clipboard_text=self._read_clipboard_text,
        )

    def _notify_ui(self, event: str, **kwargs) -> None:
        hook = getattr(self, "ui_hook", None)
        if hook:
            hook(event, **kwargs)

    def _on_activity(self, text: str, image_count: int) -> None:
        if self.review_editing:
            self.phone_pending = {"text": text, "image_count": image_count}
            self._notify_ui("phone_pending")
            return
        self._save_draft()
        if text or image_count:
            self.hud.show_receiving(text, image_count)
        self._notify_ui("activity")

    def _history_public(self) -> list:
        return [
            {
                "bundle_id": item["bundle"]["bundle_id"],
                "revision": item["bundle"].get("revision"),
                "asset_count": len(item["bundle"].get("assets") or []),
                "text_chars": len(item["bundle"].get("text") or ""),
                "attempt_result": item.get("attempt_result"),
            }
            for item in self.history.items
        ]

    def _grab(self, scope: str) -> bytes:
        from doubao_typeless.platform.windows.capture import grab_primary

        return grab_primary(scope, hide=self.hud.hide)

    def _on_capture(self, scope: str, request_id: str = "") -> dict:
        sessions = list(self.auth.sessions.values())
        if not sessions:
            raise ValueError("no session")
        self.hud.hide()
        blob = self.capture.capture(sessions[-1], scope, request_id=request_id or str(uuid.uuid4()))
        from PIL import Image
        import io

        image = Image.open(io.BytesIO(blob))
        meta = self.store.put_png(blob, width=image.width, height=image.height, role="screenshot")
        self.draft.assets.append(meta)
        self.draft.revision += 1
        self._on_activity(self.draft.text, len(self.draft.assets))
        return meta

    def _wait_modifiers(self) -> bool:
        from doubao_typeless.platform.windows.guards import wait_modifiers_up

        return wait_modifiers_up()

    def _session_locked(self) -> bool:
        from doubao_typeless.platform.windows.guards import session_locked

        return session_locked()

    def _target_elevated(self) -> bool:
        return False

    def _read_clipboard_text(self) -> str | None:
        try:
            from doubao_typeless.platform.windows.clipboard import read_clipboard_text

            return read_clipboard_text()
        except Exception:
            return None

    def _read_focus(self):
        from doubao_typeless.platform.windows.clipboard import read_focus

        return read_focus()

    def _paste(self) -> None:
        from doubao_typeless.platform.windows.clipboard import send_paste

        send_paste()

    def _set_image(self, data: bytes) -> None:
        from doubao_typeless.platform.windows.clipboard import set_clipboard_png

        if not data:
            return
        set_clipboard_png(data)

    def _set_text(self, text: str) -> None:
        from doubao_typeless.platform.windows.clipboard import set_clipboard_text

        set_clipboard_text(text)

    def _observe_image(self) -> str:
        if self._observer is not None:
            return self._observer.observe_image()
        from doubao_typeless.adapters.cursor_windows import observe_image

        return observe_image()

    def _observe_text(self) -> str:
        if self._observer is not None:
            return self._observer.observe_text()
        from doubao_typeless.adapters.generic_text import observe_text

        return observe_text()

    def _hydrate_bundle(self, bundle: dict) -> dict:
        hydrated = dict(bundle)
        assets = []
        for asset in hydrated.get("assets") or []:
            item = dict(asset)
            if "bytes_data" not in item:
                item["bytes_data"] = self.store.get(item["asset_id"])
            assets.append(item)
        hydrated["assets"] = assets
        return hydrated

    def _on_intent(self, intent: dict, bundle: dict) -> dict:
        intent_id = str(intent.get("intent_id") or "")
        decision = self.ledger.begin(intent_id)
        if decision == "duplicate":
            return {"result": self.ledger.status(intent_id) or "UNKNOWN", "duplicate": True}
        if decision == "busy":
            return {"result": "BUSY", "error_code": "BUSY"}
        class_name, control = self._read_focus()
        from doubao_typeless.core.policy import classify_focus

        kind = classify_focus(class_name, control)
        if kind == "paste":
            adapter_id = "s2_paste_target"
        elif "V3ComposerTarget" in f"{class_name} {control}":
            adapter_id = "product_target"
        else:
            from doubao_typeless.adapters.cursor_windows import identify

            adapter_id = identify(class_name, control)
        attempt = Attempt(
            attempt_id=str(uuid.uuid4()),
            intent_id=intent_id,
            bundle_id=bundle["bundle_id"],
            adapter_id=adapter_id,
        )
        hydrated = self._hydrate_bundle(bundle)
        frozen_text = hydrated.get("text")
        mode = str(intent.get("recovery_mode") or "full")
        skip = set(intent.get("skip_asset_ids") or [])
        try:
            result = self.delivery.run(attempt, hydrated, mode=mode, skip_asset_ids=skip)
        except Exception:
            self.ledger.finish(intent_id, "UNKNOWN")
            raise
        self.ledger.finish(intent_id, result.result)
        self._last_attempt = result
        self.history.record(bundle, attempt_result=result.result)
        if result.result == "CONFIRMED":
            archive_if_match(
                self.draft,
                {
                    "draft_id": bundle.get("draft_id"),
                    "epoch": bundle.get("epoch"),
                    "revision": bundle.get("revision"),
                    "manifest_hash": bundle.get("manifest_hash"),
                },
                current_hash=bundle.get("manifest_hash") or "",
            )
        _log(f"[v3.delivery] {result.result} enter={self.delivery.enter_count} text_frozen={frozen_text == bundle.get('text')}")
        payload = result.to_dict()
        payload["result"] = result.result
        self._save_draft()
        return payload

    def insert_last(self, user_mode: str | None = None) -> None:
        from doubao_typeless.ui.recovery import plan_retry

        bundle = self.bridge.last_bundle
        if bundle is None and (self.draft.text or self.draft.assets):
            bundle = freeze_bundle(self.draft, bundle_id=str(uuid.uuid4()))
            self.bridge.last_bundle = bundle
        if bundle is None:
            return
        sessions = list(self.auth.sessions.values())
        intent = {"intent_id": str(uuid.uuid4()), "trigger": "hotkey"}
        if self._last_attempt is not None:
            images_total = len(bundle.get("assets") or [])
            images_obs = sum(1 for s in self._last_attempt.steps if s.kind == "image" and s.state == "observed")
            text_sent = any(s.kind == "text" for s in self._last_attempt.steps)
            plan = plan_retry(
                previous_result=self._last_attempt.result,
                same_target=True,
                images_observed=images_obs,
                images_total=images_total,
                text_sent=text_sent,
                user_mode=user_mode,
            )
            if plan["mode"] == "ask":
                self._recovery_needed = True
                self.hud.show_receiving("上次结果未知，请选择恢复方式", len(bundle.get("assets") or []))
                _log("[v3.recovery] ask; 不自动重放、不Ctrl+A")
                self._notify_ui("recovery_ask")
                return
            if plan["mode"] == "cancel":
                return
            if plan["mode"] in {"text_only", "remaining_verified", "full"}:
                intent["recovery_mode"] = plan["mode"]
        self._recovery_needed = False
        if sessions:
            intent["session_id"] = sessions[-1].session_id
            intent["token"] = sessions[-1].token
            intent["nonce"] = self.auth.issue_nonce(sessions[-1])
        self._on_intent(intent, bundle)

    def confirm_recovery(self, mode: str) -> None:
        self.insert_last(user_mode=mode)

    def recall_last(self) -> None:
        from doubao_typeless.ui.recovery import plan_retry

        last = self.history.last_bundle()
        if last is None:
            return
        kept_text = self.draft.text
        kept_assets = [a.get("asset_id") for a in self.draft.assets]
        plan = plan_retry(
            previous_result=(self._last_attempt.result if self._last_attempt else "UNKNOWN"),
            same_target=False,
            images_observed=0,
            images_total=len(last.get("assets") or []),
            text_sent=False,
        )
        _log(
            f"[v3.recall] mode={plan['mode']} auto_replay={plan['auto_replay']} "
            f"ctrl_a_delete={plan['ctrl_a_delete']} current_kept={self.draft.text == kept_text}"
        )
        self.hud.show_receiving(last.get("text") or "上次图文", len(last.get("assets") or []))
        self.bridge.last_bundle = last
        if self.draft.text != kept_text or [a.get("asset_id") for a in self.draft.assets] != kept_assets:
            raise RuntimeError("recall must not swallow current draft")
        self._save_draft()

    def capture_region(self) -> None:
        from doubao_typeless.ui.region import select_region

        self.hud.hide()
        box = select_region()
        if box is None:
            _log("[v3.capture] region cancelled; no new image")
            return
        x, y, w, h = box
        sessions = list(self.auth.sessions.values())
        if not sessions or not sessions[-1].allow_capture:
            _log("[v3.capture] region needs capture grant")
            return
        meta = self._on_capture(f"region:{x},{y},{w},{h}", str(uuid.uuid4()))
        _log(f"[v3.capture] region {meta.get('width')}x{meta.get('height')}")

    def _acquire_instance_lock(self) -> None:
        from doubao_typeless.runtime_lock import InstanceLock

        lock = getattr(self, "_lock", None)
        if lock is not None and getattr(lock, "owned", False):
            return
        self._lock = InstanceLock(self.data_dir / "instance.lock")
        if not self._lock.acquire():
            _log("[v3] 另一个预览实例已在运行，不强杀、不抢锁")
            raise RuntimeError("instance lock held")

    async def start(self) -> None:
        self._acquire_instance_lock()
        await self.bridge.start()
        self.port = self.bridge.port
        code = self.auth.new_pairing_challenge()
        url = f"http://{lan_ip()}:{self.port}/"
        pair_note = self.data_dir / "pair.txt"
        pair_note.write_text(f"{url}\n{code}\n", encoding="utf-8")
        _log(f"[v3] 手机打开 {url}")
        _log(f"[v3] 配对码 {code} （2分钟内）")
        _log(f"[v3] 数据目录 {self.data_dir}")
        from doubao_typeless.platform.windows.hotkeys import probe_hotkey_conflicts

        probe = probe_hotkey_conflicts()
        _log(f"[v3] 热键探测 {probe}；冲突时改键，语法合法不等于注册成功")
        _log("[v3] 空闲无浮窗；Alt+I 插入，Alt+Shift+I 召回；不发送 Enter")

    def start_background(self, *, start_hud: bool = False):
        if start_hud:
            self.hud.start()
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        asyncio.run_coroutine_threadsafe(self.start(), loop).result(15)
        self._loop = loop
        return loop

    async def stop(self) -> None:
        await self.bridge.stop()
        lock = getattr(self, "_lock", None)
        if lock:
            lock.release()


def main() -> None:
    from doubao_typeless.ui.desktop import run_desktop

    raise SystemExit(run_desktop())


if __name__ == "__main__":
    main()
