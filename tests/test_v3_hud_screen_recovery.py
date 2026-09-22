from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from doubao_typeless.ui.hud import HudController


def test_saved_removed_screen_position_and_partial_edges_remain_reachable(monkeypatch):
    app=QApplication.instance() or QApplication([])
    class Screen:
        def availableGeometry(self): return QRect(-1280,0,1280,720)
    monkeypatch.setattr(QGuiApplication,'screens',lambda:[Screen()])
    saved=[]
    hud=HudController(position=[2500,900],on_position=saved.append);hud.start()
    try:
        w=hud._widget;hud._place()
        assert Screen().availableGeometry().contains(w.geometry())
        assert saved[-1]==[w.x(),w.y()]
        w.move(-1100,100);hud._place()
        assert (w.x(),w.y())==(-1100,100)
        w.move(-50,680);hud._place()
        assert Screen().availableGeometry().contains(w.geometry())
    finally:
        hud._screen_timer.stop();hud._widget.close();hud._widget.deleteLater();app.processEvents()
