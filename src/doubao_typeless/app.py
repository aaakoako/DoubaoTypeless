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
from doubao_typeless.core.policy import classify_focus, is_own_window
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


def _httpx_json_post(url: str, body: dict, headers: dict, timeout: float = 8.0) -> dict:
    import httpx

    response = httpx.post(url, json=body, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("model response is not an object")
    return data


_log_impl = print


def _log(message: str) -> None:
    _log_impl(str(message))


def set_log(fn) -> None:
    global _log_impl
    _log_impl = fn


def _optional_float(value: object) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


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
        self.byok = ByokService(
            endpoint=stored.get("byok_endpoint") or "",
            api_key=stored.get("byok_api_key") or "",
            model=stored.get("byok_model") or "",
            extra_prompt=str(stored.get("byok_prompt") or ""),
            temperature=_optional_float(stored.get("byok_temperature")),
            post=_httpx_json_post,
        )
        self._last_suggestion = None
        self.hud = HudController(
            on_insert=self.insert_current,
            on_copy=self.copy_text,
            on_expand=lambda: self._notify_ui("expand"),
        )
        self._observer = observer_from_env()
        self._last_attempt: Attempt | None = None
        self._recovery_needed = False
        self._saved_target: tuple[str, str] | None = None
        self._copied_text = ""
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
            on_intent=self.deliver_and_finish,
            on_capture=self._on_capture,
            on_recall=self.recall_last,
            on_phone_draft=self.apply_phone_update,
            is_pc_editing=lambda: self.review_editing,
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

    def _remember_external_target(self) -> None:
        try:
            focus = self._read_focus()
        except Exception:
            return
        if focus and not is_own_window(*focus):
            self._saved_target = focus

    def _restore_external_target(self) -> tuple[str, str]:
        try:
            current = self._read_focus()
        except Exception:
            current = ("", "")
        if is_own_window(*current) and self._saved_target:
            try:
                from doubao_typeless.platform.windows.clipboard import restore_focus

                restore_focus(*self._saved_target)
            except Exception:
                pass
            try:
                current = self._read_focus()
            except Exception:
                current = self._saved_target
        return current

    def apply_phone_update(self, data: dict, *, allow_server_assets: bool = False) -> dict:
        if self.review_editing:
            self.phone_pending = dict(data)
            self._notify_ui("phone_pending")
            return {
                "revision": self.draft.revision,
                "parked": True,
                "durable": False,
                "hash": self.draft.acked_hash,
            }
        if data.get("assets") is not None and not allow_server_assets:
            raise ValueError("client assets rejected")
        if data.get("epoch") and str(data["epoch"]) != self.draft.epoch:
            return {
                "revision": self.draft.revision,
                "parked": False,
                "durable": False,
                "hash": self.draft.acked_hash,
                "error": "stale epoch",
            }
        if data.get("draft_id") and str(data["draft_id"]) != self.draft.draft_id:
            return {
                "revision": self.draft.revision,
                "parked": False,
                "durable": False,
                "hash": self.draft.acked_hash,
                "error": "stale draft",
            }
        from doubao_typeless.core.bundle import apply_draft_update
        from doubao_typeless.services.assets import resolve_asset_refs

        refs = data.get("asset_refs")
        assets = None
        if refs is not None:
            assets = resolve_asset_refs(self.store, refs)
        elif allow_server_assets and data.get("assets") is not None:
            assets = data.get("assets")
        try:
            revision = int(data["revision"])
        except (KeyError, TypeError, ValueError):
            if allow_server_assets:
                revision = self.draft.revision + 1
            else:
                raise ValueError("invalid revision") from None
        before = (self.draft.text, self.draft.revision)
        update = {
            "text": data.get("text", self.draft.text),
            "revision": revision,
            "asset_refs": refs if refs is not None else [a.get("asset_id") for a in self.draft.assets],
        }
        if assets is not None:
            update["assets"] = assets
        apply_draft_update(self.draft, update)
        changed = (self.draft.text, self.draft.revision) != before
        if changed:
            self._save_draft()
            self._on_activity(self.draft.text, len(self.draft.assets))
        return {
            "revision": self.draft.revision,
            "parked": False,
            "durable": changed,
            "hash": self.draft.acked_hash,
        }

    def accept_phone_pending(self) -> None:
        pending = self.phone_pending
        self.review_editing = False
        self.phone_pending = None
        if pending:
            self.apply_phone_update(pending, allow_server_assets=True)

    def keep_pc_edit(self) -> None:
        self.review_editing = True
        self._notify_ui("pc_kept")

    def _on_activity(self, text: str, image_count: int) -> None:
        self._remember_external_target()
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

    def _on_capture(self, scope: str, request_id: str = "", session=None) -> dict:
        if session is None:
            raise ValueError("no session")
        self.hud.hide()
        blob = self.capture.capture(session, scope, request_id=request_id or str(uuid.uuid4()))
        from PIL import Image
        import io

        image = Image.open(io.BytesIO(blob))
        meta = self.store.put_png(blob, width=image.width, height=image.height, role="screenshot")
        self.db.upsert_asset(
            meta["asset_id"],
            meta["sha256"],
            meta["bytes"],
            referenced=True,
            owner_session_id=session.session_id,
        )
        if self.review_editing:
            pending = dict(self.phone_pending or {})
            pending_assets = list(pending.get("assets") or [])
            pending_assets.append(meta)
            pending["assets"] = pending_assets
            pending["text"] = pending.get("text", self.draft.text)
            self.phone_pending = pending
            self._notify_ui("phone_pending")
            return meta
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

    def _session_intent(self, trigger: str) -> dict:
        intent = {"intent_id": str(uuid.uuid4()), "trigger": trigger}
        sessions = list(self.auth.sessions.values())
        if sessions:
            intent["session_id"] = sessions[-1].session_id
            intent["token"] = sessions[-1].token
            intent["nonce"] = self.auth.issue_nonce(sessions[-1])
        return intent

    def _keep_inserted_copy(self, bundle: dict, payload: dict | None = None) -> None:
        if payload and payload.get("error_code") == "CLIPBOARD_INTERFERENCE":
            return
        text = str(bundle.get("text") or "")
        self._copied_text = text
        if not text:
            return
        try:
            self._set_text(text)
        except Exception:
            _log("[v3.copy] 插入后保留剪贴板失败，稿未丢")
            self._notify_ui("copy_failed")

    def _maybe_start_next_draft(self, bundle: dict, payload: dict) -> bool:
        result = payload.get("result")
        steps = payload.get("steps") or []
        text_done = any(
            (step.get("kind") if isinstance(step, dict) else getattr(step, "kind", None)) == "text"
            for step in steps
        )
        images = bundle.get("assets") or []
        if result == "CONFIRMED":
            return False
        if result in {"UNKNOWN", "PARTIAL"} and not images and text_done:
            before = self.draft.epoch
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
            self._save_draft()
            self._notify_ui("new_draft")
            return self.draft.epoch != before
        return False

    def _phone_rotate_event(self, bundle: dict, rotated: bool) -> dict:
        return {
            "type": "draft.rotated",
            "archived": {
                "draft_id": bundle.get("draft_id"),
                "epoch": bundle.get("epoch"),
                "revision": bundle.get("revision"),
                "hash": bundle.get("manifest_hash"),
                "text": bundle.get("text") or "",
                "asset_refs": [a.get("asset_id") for a in (bundle.get("assets") or [])],
            } if rotated else None,
            "draft_id": self.draft.draft_id,
            "epoch": self.draft.epoch,
            "revision": self.draft.revision,
            "text": self.draft.text,
            "asset_refs": [a.get("asset_id") for a in self.draft.assets],
        }

    def _after_insert(self, bundle: dict, payload: dict) -> dict:
        self._keep_inserted_copy(bundle, payload)
        rotated = self._maybe_start_next_draft(bundle, payload)
        event = self._phone_rotate_event(bundle, rotated)
        self.bridge.last_phone_event = event
        payload = dict(payload)
        payload["phone_event"] = event
        self._notify_ui("hide_after_insert")
        return payload

    def deliver_and_finish(self, intent: dict, bundle: dict) -> dict:
        self.hud.hide()
        payload = self._on_intent(intent, bundle)
        return self._after_insert(bundle, payload)

    def _on_intent(self, intent: dict, bundle: dict) -> dict:
        intent_id = str(intent.get("intent_id") or "")
        decision = self.ledger.begin(intent_id)
        if decision == "duplicate":
            return {"result": self.ledger.status(intent_id) or "UNKNOWN", "duplicate": True}
        if decision == "busy":
            return {"result": "BUSY", "error_code": "BUSY"}
        class_name, control = self._restore_external_target()
        if is_own_window(class_name, control):
            self.ledger.finish(intent_id, "NO_STEPS")
            return {"result": "NO_STEPS", "error_code": "OWN_WINDOW"}
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

    def insert_current(self) -> dict | None:
        if not (self.draft.text or self.draft.assets):
            return None
        bundle = freeze_bundle(self.draft, bundle_id=str(uuid.uuid4()))
        self.bridge.last_bundle = bundle
        intent = self._session_intent("insert_current")
        return self.deliver_and_finish(intent, bundle)

    def draft_image_previews(self) -> list[dict]:
        out: list[dict] = []
        for index, asset in enumerate(self.draft.assets):
            asset_id = str(asset.get("asset_id") or "")
            data = b""
            present = False
            if asset_id:
                try:
                    data = self.store.get(asset_id)
                    present = True
                except FileNotFoundError:
                    present = False
            out.append(
                {
                    "order": index + 1,
                    "asset_id": asset_id,
                    "present": present,
                    "bytes": len(data),
                    "data": data,
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                }
            )
        return out

    def suggest_text(self, text: str) -> dict:
        out = self.byok.polish(
            text,
            draft_id=self.draft.draft_id,
            revision=self.draft.revision,
            current_draft_id=self.draft.draft_id,
            current_revision=self.draft.revision,
        )
        suggested = out.get("text") if out.get("status") == "ok" else None
        self._last_suggestion = {
            "original": text,
            "suggested": suggested,
            "draft_id": self.draft.draft_id,
            "epoch": self.draft.epoch,
            "revision": self.draft.revision,
            **out,
        }
        return self._last_suggestion

    def apply_suggestion(self) -> bool:
        last = self._last_suggestion or {}
        if not last.get("suggested"):
            return False
        if last.get("draft_id") != self.draft.draft_id or last.get("epoch") != self.draft.epoch:
            return False
        last["before_apply"] = self.draft.text
        self.draft.text = str(last["suggested"])
        self.draft.revision += 1
        self._save_draft()
        return True

    def reject_suggestion(self) -> None:
        last = self._last_suggestion or {}
        if last.get("before_apply") is not None and last.get("draft_id") == self.draft.draft_id:
            self.draft.text = str(last["before_apply"])
            self.draft.revision += 1
            self._save_draft()
        self._last_suggestion = None

    def copy_text(self) -> str:
        text = self.draft.text or ""
        self._copied_text = text
        try:
            self._set_text(text)
        except Exception:
            _log("[v3.copy] 只复制失败，稿未清")
        return text

    def start_new_draft(self) -> None:
        self.draft.text = ""
        self.draft.assets = []
        self.draft.revision += 1
        self.draft.epoch = str(uuid.uuid4())
        self._save_draft()
        self.hud.hide()
        self._notify_ui("new_draft")

    def restore_history(self, bundle: dict, *, replace: bool = False) -> str:
        if (self.draft.text or self.draft.assets) and not replace:
            return "ask"
        copied = self.history.copy_to_new_draft(bundle)
        self.draft.text = copied.get("text") or ""
        self.draft.assets = list(copied.get("assets") or [])
        self.draft.revision += 1
        self.draft.epoch = str(uuid.uuid4())
        self._save_draft()
        self._notify_ui("activity")
        return "restored"

    def insert_last(self, user_mode: str | None = None) -> dict | None:
        from doubao_typeless.ui.recovery import plan_retry

        bundle = self.bridge.last_bundle
        if bundle is None:
            return None
        intent = self._session_intent("recall_retry")
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
                return None
            if plan["mode"] == "cancel":
                return None
            if plan["mode"] in {"text_only", "remaining_verified", "full"}:
                intent["recovery_mode"] = plan["mode"]
        self._recovery_needed = False
        return self.deliver_and_finish(intent, bundle)

    def confirm_recovery(self, mode: str) -> dict | None:
        return self.insert_last(user_mode=mode)

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
        if plan["mode"] == "ask" or (self._last_attempt and self._last_attempt.result in {"UNKNOWN", "PARTIAL"}):
            self._recovery_needed = True
            self._notify_ui("recovery_ask")
            return
        self.insert_last()

    def capture_region(self) -> None:
        from doubao_typeless.ui.region import select_region

        self.hud.hide()
        box = select_region()
        if box is None:
            _log("[v3.capture] region cancelled; no new image")
            return
        x, y, w, h = box
        granted = [item for item in self.auth.sessions.values() if item.allow_capture]
        if not granted:
            _log("[v3.capture] region needs capture grant")
            return
        session = granted[-1]
        meta = self._on_capture(f"region:{x},{y},{w},{h}", str(uuid.uuid4()), session)
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
        _log("[v3] 空闲无浮窗；Alt+I 插入并复制，Alt+Shift+I 召回；不发送 Enter")

    def start_background(self, *, start_hud: bool = False):
        if start_hud:
            self.hud.start()
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        asyncio.run_coroutine_threadsafe(self.start(), loop).result(15)
        self._loop = loop
        return loop

    def apply_hotkeys(
        self,
        insert: str,
        recall: str,
        *,
        expand: str = "<alt>+<shift>+e",
        capture: str = "<alt>+<shift>+s",
    ) -> list[str]:
        self._stop_hotkeys()
        from doubao_typeless.platform.windows.hotkeys import start_hotkeys

        start = start_hotkeys(
            on_insert=self.insert_current,
            on_recall=self.recall_last,
            on_expand=lambda: self._notify_ui("expand"),
            on_region=self.capture_region,
            insert_combo=insert or "<alt>+i",
            recall_combo=recall or "<alt>+<shift>+i",
            expand_combo=expand or "<alt>+<shift>+e",
            capture_combo=capture or "<alt>+<shift>+s",
        )
        self._hotkeys = start
        return list(start.get("failures") or [])

    def _stop_hotkeys(self) -> None:
        hotkeys = getattr(self, "_hotkeys", None) or {}
        for key in ("listener", "release"):
            obj = hotkeys.get(key)
            if obj is None:
                continue
            try:
                obj.stop()
            except Exception:
                pass
        self._hotkeys = None

    async def stop(self) -> None:
        self._stop_hotkeys()
        await self.bridge.stop()
        try:
            self.db.conn.close()
        except Exception:
            pass
        lock = getattr(self, "_lock", None)
        if lock:
            lock.release()


def main() -> None:
    from doubao_typeless.ui.desktop import run_desktop

    raise SystemExit(run_desktop())


if __name__ == "__main__":
    main()
