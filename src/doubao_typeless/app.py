"""Assemble Pocket Composer v3. Isolated data dir; idle HUD hidden."""
from __future__ import annotations

import asyncio
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


def _log(message: str) -> None:
    print(message, flush=True)


class V3App:
    def __init__(self, *, data_dir: Path | None = None, port: int = 8766):
        self.data_dir = Path(data_dir or v3_data_dir())
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.port = pick_port(port) if port else 0
        self.auth = AuthService()
        self.store = AssetStore(self.data_dir / "assets")
        self.ledger = IntentLedger()
        self.draft = Draft(
            draft_id=str(uuid.uuid4()),
            epoch=str(uuid.uuid4()),
            revision=0,
            editor_device_id="pc",
            text="",
        )
        self.history = HistoryService(self.data_dir / "history.json", persist=True)
        self.byok = ByokService()
        self.hud = HudController(on_insert=self.insert_last)
        self._observer = observer_from_env()
        self._last_attempt: Attempt | None = None
        self.bridge = V3Bridge(
            port=self.port,
            auth=self.auth,
            store=self.store,
            draft=self.draft,
            on_activity=self._on_activity,
            on_intent=self._on_intent,
            on_capture=self._on_capture,
            history_list=self._history_public,
            logger=_log,
        )
        self.capture = CaptureService(grab=self._grab, hide_surfaces=self.hud.hide)
        self.delivery = DeliveryService(
            paste=self._paste,
            set_clipboard_image=self._set_image,
            set_clipboard_text=self._set_text,
            read_focus=self._read_focus,
            observe_image=self._observe_image,
            observe_text=self._observe_text,
        )

    def _on_activity(self, text: str, image_count: int) -> None:
        if text or image_count:
            self.hud.show_receiving(text, image_count)

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

        return grab_primary(scope)

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
        if "V3ComposerTarget" in f"{class_name} {control}":
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
        return payload

    def insert_last(self) -> None:
        bundle = self.bridge.last_bundle
        if bundle is None and (self.draft.text or self.draft.assets):
            bundle = freeze_bundle(self.draft, bundle_id=str(uuid.uuid4()))
            self.bridge.last_bundle = bundle
        if bundle is None:
            return
        sessions = list(self.auth.sessions.values())
        intent = {"intent_id": str(uuid.uuid4()), "trigger": "hotkey"}
        if sessions:
            intent["session_id"] = sessions[-1].session_id
            intent["token"] = sessions[-1].token
            intent["nonce"] = self.auth.issue_nonce(sessions[-1])
        self._on_intent(intent, bundle)

    def recall_last(self) -> None:
        last = self.history.last_bundle()
        if last is None:
            return
        self.hud.show_receiving(last.get("text") or "上次图文", len(last.get("assets") or []))
        self.bridge.last_bundle = last

    async def start(self) -> None:
        await self.bridge.start()
        code = self.auth.new_pairing_challenge()
        url = f"http://{lan_ip()}:{self.port}/"
        pair_note = self.data_dir / "pair.txt"
        pair_note.write_text(f"{url}\n{code}\n", encoding="utf-8")
        _log(f"[v3] 手机打开 {url}")
        _log(f"[v3] 配对码 {code} （2分钟内）")
        _log(f"[v3] 数据目录 {self.data_dir}")
        _log("[v3] 空闲无浮窗；Alt+I 插入，Alt+Shift+I 召回；不发送 Enter")

    def start_background(self, *, start_hud: bool = False):
        if start_hud:
            self.hud.start()
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        asyncio.run_coroutine_threadsafe(self.start(), loop).result(15)
        return loop

    async def stop(self) -> None:
        await self.bridge.stop()


def main() -> None:
    app = V3App()
    app.hud.start()
    try:
        from doubao_typeless.platform.windows.hotkeys import start_hotkeys

        start_hotkeys(on_insert=app.insert_last, on_recall=app.recall_last)
    except Exception as exc:
        _log(f"[v3] 热键未启动: {exc}")

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    asyncio.run_coroutine_threadsafe(app.start(), loop)
    try:
        if app.hud._app is not None:
            app.hud._app.exec()
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        asyncio.run_coroutine_threadsafe(app.stop(), loop).result(5)


if __name__ == "__main__":
    main()
