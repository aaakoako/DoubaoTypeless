"""Assemble Pocket Composer v3. Isolated data dir; idle HUD hidden."""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from pathlib import Path

from doubao_typeless.core.attempt import Attempt
from doubao_typeless.core.bundle import Draft, archive_if_match, freeze_bundle
from doubao_typeless.runtime import lan_ip, v3_data_dir
from doubao_typeless.services.bridge_v3 import V3Bridge
from doubao_typeless.services.byok import ByokService
from doubao_typeless.services.capture import CaptureService
from doubao_typeless.services.delivery import DeliveryService
from doubao_typeless.services.history import HistoryService
from doubao_typeless.storage.asset_store import AssetStore
from doubao_typeless.storage.credentials import AuthService
from doubao_typeless.ui.hud import HudController


def _log(message: str) -> None:
    print(message, flush=True)


class V3App:
    def __init__(self, *, data_dir: Path | None = None, port: int = 8766):
        self.data_dir = Path(data_dir or v3_data_dir())
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.port = port
        self.auth = AuthService()
        self.store = AssetStore(self.data_dir / "assets")
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
        self._last_attempt: Attempt | None = None
        self.bridge = V3Bridge(
            port=port,
            auth=self.auth,
            store=self.store,
            draft=self.draft,
            on_activity=self._on_activity,
            on_intent=self._on_intent,
            on_capture=self._on_capture,
            history_list=self._history_public,
            logger=_log,
        )
        self.capture = CaptureService(grab=self._grab)
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

    def _on_capture(self, scope: str) -> dict:
        sessions = list(self.auth.sessions.values())
        if not sessions:
            raise ValueError("no session")
        blob = self.capture.capture(sessions[-1], scope)
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
        from doubao_typeless.adapters.cursor_windows import observe_image

        return observe_image()

    def _observe_text(self) -> str:
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

    def _on_intent(self, intent: dict, bundle: dict) -> None:
        attempt = Attempt(
            attempt_id=str(uuid.uuid4()),
            intent_id=str(intent.get("intent_id") or uuid.uuid4()),
            bundle_id=bundle["bundle_id"],
            adapter_id="cursor_windows",
        )
        hydrated = self._hydrate_bundle(bundle)
        frozen_text = hydrated.get("text")
        result = self.delivery.run(attempt, hydrated)
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
