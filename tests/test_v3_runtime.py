"""V3 runtime: history, BYOK, capture, HUD idle, composer page, recovery."""
from __future__ import annotations

from pathlib import Path

import pytest

from doubao_typeless.app import V3App
from doubao_typeless.core.attempt import Attempt
from doubao_typeless.core.bundle import Draft, freeze_bundle
from doubao_typeless.runtime import PREVIEW_NAME, v3_data_dir
from doubao_typeless.services.byok import ByokService
from doubao_typeless.services.capture import CaptureService
from doubao_typeless.services.delivery import DeliveryService, VK_RETURN
from doubao_typeless.services.history import HistoryService
from doubao_typeless.services.terms import apply_permanent, hints
from doubao_typeless.storage.credentials import AuthService, Session
from doubao_typeless.ui.hud import HudController

COMPOSER = Path(__file__).resolve().parents[1] / "src/doubao_typeless/static/composer.html"


def test_v3_data_dir_is_isolated_from_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("DT_V3_DATA_DIR", str(tmp_path / "preview"))
    path = v3_data_dir()
    repo = Path(__file__).resolve().parents[1]
    assert path != repo
    assert "config.json" not in str(path)
    monkeypatch.delenv("DT_V3_DATA_DIR")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert v3_data_dir().name == PREVIEW_NAME
    assert (tmp_path / "local" / "DoubaoTypeless" / PREVIEW_NAME) == v3_data_dir()


def test_hud_idle_is_hidden():
    hud = HudController()
    assert hud.visible is False
    hud.show_receiving("hello", 0)
    assert hud.visible is True
    hud.hide()
    assert hud.visible is False


def test_history_last_is_not_current_draft(tmp_path):
    hist = HistoryService(tmp_path / "history.json")
    bundle_a = {
        "bundle_id": "a",
        "draft_id": "d1",
        "epoch": "e1",
        "revision": 1,
        "manifest_hash": "h1",
        "text": "bundle A",
        "assets": [],
    }
    hist.record(bundle_a, attempt_result="UNKNOWN")
    current = Draft("d2", "e2", 1, "phone", "bundle B")
    last = hist.last_bundle()
    assert last["text"] == "bundle A"
    assert current.text == "bundle B"
    copied = hist.copy_to_new_draft(last)
    assert copied["action"] == "copy_to_new_draft"
    assert copied["source_bundle_id"] == "a"
    replay = hist.replay_bundle(last)
    assert replay["action"] == "replay_bundle"
    assert replay["bundle_id"] == "a"


def test_history_gc_keeps_protected_and_caps(tmp_path):
    hist = HistoryService(tmp_path / "history.json")
    for i in range(25):
        hist.record(
            {
                "bundle_id": str(i),
                "text": "x",
                "assets": [{"bytes": 10}],
            },
            attempt_result="UNKNOWN",
        )
        hist.items[-1]["recorded_at"] = 1
    hist.gc(now=10**10, protected_ids={"24"})
    ids = [i["bundle"]["bundle_id"] for i in hist.items]
    assert "24" in ids
    assert len(hist.items) <= 21
    diag = hist.diagnostics()
    assert "text" not in diag
    assert "token" not in diag


def test_byok_skips_without_key_and_rejects_images():
    svc = ByokService()
    out = svc.polish("hello", draft_id="d", revision=1, current_draft_id="d", current_revision=1)
    assert out["status"] == "skipped"
    assert out["text"] == "hello"
    with pytest.raises(ValueError, match="images"):
        svc.polish("hello", draft_id="d", revision=1, current_draft_id="d", current_revision=1, images=["nope"])


def test_byok_stale_revision_does_not_overwrite():
    def post(url, body, headers):
        assert "image" not in body
        assert "Bearer secret" in headers["Authorization"]
        return {"text": "rewritten"}

    svc = ByokService(endpoint="https://example.invalid/v1", api_key="secret", post=post)
    stale = svc.polish(
        "old",
        draft_id="d1",
        revision=1,
        current_draft_id="d1",
        current_revision=2,
    )
    assert stale["status"] == "stale"
    assert stale["text"] is None


def test_terms_hint_never_auto_replaces():
    notes = hints("试试 Midjourney 和 Opus")
    assert notes
    with pytest.raises(RuntimeError):
        apply_permanent("Opus")


def test_capture_requires_grant():
    session = Session("d", "s", "h", 9e12, allow_capture=False)
    svc = CaptureService(grab=lambda _s: b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError, match="not granted"):
        svc.capture(session, "primary")
    session.allow_capture = True
    with pytest.raises(ValueError, match="unknown capture scope"):
        svc.capture(session, "hwnd:1234")
    assert svc.capture(session, "primary").startswith(b"\x89PNG")


def test_delivery_stops_remaining_when_target_changes():
    pasted = []
    foci = iter(
        [
            ("ComposerPane", "chatinput"),
            ("ComposerPane", "chatinput"),
            ("Scintilla", "code"),
        ]
    )
    svc = DeliveryService(
        paste=lambda: pasted.append("paste"),
        set_clipboard_image=lambda _b: pasted.append("image"),
        set_clipboard_text=lambda _t: pasted.append("text"),
        read_focus=lambda: next(foci),
        observe_image=lambda: "observed",
        observe_text=lambda: "observed",
    )
    attempt = Attempt("a", "i", "b", "cursor_windows")
    bundle = {
        "text": "later",
        "assets": [
            {"asset_id": "img-1", "bytes_data": b"\x89PNG\r\n\x1a\n"},
            {"asset_id": "img-2", "bytes_data": b"\x89PNG\r\n\x1a\n"},
        ],
    }
    out = svc.run(attempt, bundle)
    assert out.result == "PARTIAL"
    assert "text" not in pasted
    assert pasted.count("image") == 1


def test_frozen_bundle_ignores_later_draft_edits():
    draft = Draft("d", "e", 1, "phone", "first", assets=[])
    bundle = freeze_bundle(draft, bundle_id="b1")
    draft.text = "second"
    assert bundle["text"] == "first"


def test_composer_is_single_page_shared_editor():
    html = COMPOSER.read_text(encoding="utf-8")
    assert "白板" in html
    assert html.count("<canvas") == 1
    assert "auto_send" not in html
    assert "插入电脑" in html
    assert "VK_RETURN" not in html
    assert "keybd_event" not in html
    assert "min-height:44px" in html
    assert "图片标注" in html and "快速白板" in html


def test_v3_app_uses_isolated_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DT_V3_DATA_DIR", str(tmp_path / "iso"))
    app = V3App(data_dir=tmp_path / "iso", port=0)
    assert app.data_dir == tmp_path / "iso"
    assert app.hud.visible is False
    assert app.delivery.enter_count == 0
    assert VK_RETURN != 0


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="native Qt HUD")
def test_hud_applies_show_from_worker_thread():
    import threading

    hud = HudController()
    hud.start()
    if hud._widget is None:
        pytest.skip("PySide6 HUD widget missing")
    from PySide6.QtWidgets import QApplication

    def worker():
        hud.show_receiving("from-worker", 0)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(2)
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    assert hud.visible is True
    assert hud._widget.isVisible() is True
    hud.hide()

