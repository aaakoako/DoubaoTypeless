"""Real Qt surface ownership; no native target compatibility claim."""
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from doubao_typeless.app import V3App
from doubao_typeless.ui.desktop import ClientWindow,ReviewPanel
QT=None

@pytest.fixture
def surfaces(tmp_path):
    global QT
    QT=QApplication.instance() or QApplication([])
    a=V3App(data_dir=tmp_path/'isolated',port=0);a.hud.start()
    client=ClientWindow(a);review=ReviewPanel(a)
    yield a,client,review
    client.widget.hide();review.widget.hide();a.hud.dismiss()
    client.widget.deleteLater();review.widget.deleteLater();a.hud._widget.deleteLater()
    a._commands.close(2);a.db.conn.close();a._lock.release();QTest.qWait(10)

@pytest.mark.parametrize('name',['review'])
def test_visible_surface_excludes_hud_even_when_phone_updates(surfaces,name):
    a,c,r=surfaces
    a._remember_external_target=lambda:None
    a.hud.show_receiving('原稿');QTest.qWait(20)
    assert a.hud._widget.isVisible()
    w=c if name=='client' else r
    c.show_window() if name=='client' else r.show()
    QTest.qWait(20)
    assert w.widget.isVisible() and not a.hud._widget.isVisible()
    a.hud.show_receiving('手机继续更新');QTest.qWait(20)
    assert a.hud.text=='手机继续更新' and not a.hud._widget.isVisible()
    w.widget.hide();QTest.qWait(10)
    assert not a.hud._widget.isVisible()
    a.hud.show_receiving('下一次输入');QTest.qWait(20)
    assert a.hud._widget.isVisible()

def test_locate_button_does_not_call_insert_or_clear_phone(surfaces):
    a,c,r=surfaces;actions=[];a.update_pc_text('定位不插入')
    a._remember_external_target=lambda:None
    a.request_locate_composer=lambda:actions.append('locate')
    a.request_review_insert=lambda:actions.append('insert')
    a.hud.show_receiving(a.draft.text);r.show();QTest.qWait(20)
    button=next(b for b in r.widget.findChildren(QPushButton) if b.text()=='定位输入框')
    assert not a.hud._widget.isVisible()
    QTest.mouseClick(button,Qt.LeftButton);QTest.qWait(10)
    assert actions==['locate'] and a.draft.text=='定位不插入'

def test_multiple_surfaces_release_independently(surfaces):
    a,c,r=surfaces;a._remember_external_target=lambda:None
    c.show_window();r.show();QTest.qWait(10)
    r.widget.hide();a.hud.show_receiving('settings coexists');QTest.qWait(10)
    assert a.hud._widget.isVisible() and c.widget.isVisible()
    c.widget.hide();a.hud.show_receiving('show now');QTest.qWait(10)
    assert a.hud._widget.isVisible()
