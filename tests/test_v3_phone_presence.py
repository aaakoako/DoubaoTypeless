"""A hidden settings window must not freeze the visible HUD's connection status."""
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from doubao_typeless.app import V3App
from doubao_typeless.ui.desktop import ClientWindow


def test_background_presence_updates_without_reopening_hidden_surfaces(tmp_path, monkeypatch):
    qt = QApplication.instance() or QApplication([])
    app = V3App(data_dir=tmp_path, port=0)
    online = {"phone"}
    monkeypatch.setattr(app.bridge, "online_device_ids", lambda: set(online))
    app.draft.editor_device_id = "phone"
    app.hud.start()
    win = ClientWindow(app)
    try:
        win.widget.hide()
        app.hud.show_receiving("电脑保留这一段", [], revision=1, phone_primary=True)
        assert app.hud._widget.isVisible()
        online.clear()
        QTest.qWait(1200)
        assert "手机离线" in app.hud._status.text()
        assert not win.widget.isVisible()
        app.hud._apply_hide()
        online.add("phone")
        QTest.qWait(1200)
        assert app.hud.phone_online
        assert not app.hud._widget.isVisible()
        assert not win.widget.isVisible()
    finally:
        win.timer.stop()
        win.widget.deleteLater()
        app.hud._screen_timer.stop()
        app.hud._widget.close()
        app.hud._widget.deleteLater()
        qt.processEvents()
