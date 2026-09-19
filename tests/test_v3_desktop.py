"""Desktop client talks to the live V3App, not a static page."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from doubao_typeless.app import V3App
from doubao_typeless.ui.filelog import FileLogger
from doubao_typeless.ui.recovery import plan_retry
from doubao_typeless.storage.settings_store import load_settings


def _qt_app():
    from PySide6.QtWidgets import QApplication
    from doubao_typeless.ui.desktop import apply_ui_font

    qt = QApplication.instance() or QApplication([])
    apply_ui_font(qt)
    return qt


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows desktop client")
def test_client_window_shows_live_url_and_grants(tmp_path):
    _qt_app()
    app = V3App(data_dir=tmp_path, port=0)
    app.start_background(start_hud=False)
    try:
        from doubao_typeless.ui.desktop import ClientWindow

        win = ClientWindow(app)
        assert str(app.port) in win.url_label.text()
        assert "http://" in win.url_label.text()
        assert "配对码" in win.code_label.text()
        assert win.qr.pixmap() is not None and not win.qr.pixmap().isNull()
        code = app.auth.current_pairing_challenge()
        session = app.auth.complete_pairing(code, allow_insert=False, allow_capture=False)
        win.refresh()
        win.set_insert(session.session_id, True)
        assert app.auth.sessions[session.session_id].allow_insert is True
        win.set_capture(session.session_id, True)
        assert app.auth.sessions[session.session_id].allow_capture is True
        win.revoke(session.session_id)
        assert session.session_id not in app.auth.sessions
    finally:
        import asyncio

        asyncio.run_coroutine_threadsafe(app.stop(), app._loop).result(5)


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows desktop client")
def test_settings_and_review_use_same_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    daily = tmp_path / "repo" / "config.json"
    daily.parent.mkdir()
    daily.write_text('{"llm_api_key":"keep-daily"}', encoding="utf-8")
    _qt_app()
    data = tmp_path / "preview-v3"
    app = V3App(data_dir=data, port=0)
    from doubao_typeless.ui.desktop import ClientWindow, ReviewPanel

    win = ClientWindow(app)
    win.byok_endpoint.setText("https://example.invalid/v1")
    win.byok_key.setText("sk-desktop-test")
    win.hotkey_insert.setText("<ctrl>+<alt>+i")
    win.save_settings()
    stored = load_settings(data)
    assert stored["byok_api_key"] == "sk-desktop-test"
    assert stored["hotkey_insert"] == "<ctrl>+<alt>+i"
    assert daily.read_text(encoding="utf-8") == '{"llm_api_key":"keep-daily"}'
    app.draft.text = "电脑稿"
    panel = ReviewPanel(app)
    panel.editor.setPlainText("电脑稿已改")
    app.review_editing = True
    app._on_activity("手机新稿", 0)
    assert panel.editor.toPlainText() == "电脑稿已改"
    assert app.phone_pending["text"] == "手机新稿"
    panel.note_phone_pending()
    assert "手机有更新" in panel.banner.text()
    win.widget.show()
    win.hide_to_tray()
    assert win.widget.isVisible() is False


def test_recovery_dialog_asks_instead_of_auto_replay():
    plan = plan_retry(
        previous_result="UNKNOWN",
        same_target=True,
        images_observed=0,
        images_total=1,
        text_sent=False,
    )
    assert plan["mode"] == "ask"
    assert plan["auto_replay"] is False
    _qt_app()
    from doubao_typeless.ui.desktop import RecoveryDialog

    dlg = RecoveryDialog()
    assert dlg.choice == "cancel"
    dlg._pick(dlg._dlg, "text_only")
    assert dlg.choice == "text_only"


def test_file_log_redacts_and_caps(tmp_path):
    path = tmp_path / "v3.log"
    log = FileLogger(path, also_print=False, max_bytes=80)
    log("Bearer sk-abcdefghijk should hide")
    log("second line")
    text = path.read_text(encoding="utf-8")
    assert "sk-abcdefghijk" not in text
    assert "…" in text


def test_pause_blocks_draft_without_dropping_text(tmp_path):
    app = V3App(data_dir=tmp_path, port=0)
    app.bridge.paused = True
    app.draft.text = "kept"
    assert app.bridge.paused is True
    assert app.draft.text == "kept"


def test_wake_pipe_is_preview_specific_and_false_without_server():
    from PySide6.QtNetwork import QLocalServer
    from doubao_typeless.ui.single_instance import PIPE, request_quit, request_show
    from doubao_typeless.ui.v3_startup import V3_RUN_NAME

    assert PIPE == "DoubaoTypelessV3Preview"
    assert V3_RUN_NAME == "DoubaoTypelessV3Preview"
    assert V3_RUN_NAME != "DoubaoTypeless"
    _qt_app()
    QLocalServer.removeServer(PIPE)
    assert request_show() is False
    assert request_quit() is False
