"""真实Qt控件的共用样式与操作层级；截图只作为对应环境证据。"""
import os
from pathlib import Path
import pytest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtTest import QTest
from doubao_typeless.app import V3App
from doubao_typeless.ui.desktop import ClientWindow,ReviewPanel,RecoveryDialog,ComposerPicker
from doubao_typeless.ui.theme import QSS
from doubao_typeless.ui.hud import HudController
QT=None
@pytest.fixture
def pair(tmp_path):
    global QT
    QT=QApplication.instance() or QApplication([])
    a=V3App(data_dir=tmp_path/'isolated',port=0)
    w=ClientWindow(a);review=ReviewPanel(a)
    yield a,w,review
    w.widget.hide();review.widget.hide();w.widget.deleteLater();review.widget.deleteLater()
    a._commands.close(2);a.db.conn.close();a._lock.release();QTest.qWait(10)

def test_all_surfaces_share_styles_and_single_primary(pair):
    a,w,r=pair
    recovery=RecoveryDialog(w.widget,confirm_image=True,progress={'images_attempted':1,'images_total':1,'text_state':'not_attempted','message':'文字尚未插入'})
    picker=ComposerPicker(w.widget,[])
    for widget in [w.widget,r.widget,recovery._dlg,picker.widget]:assert widget.styleSheet()==QSS
    buttons=recovery._dlg.findChildren(QPushButton)
    assert len([b for b in buttons if b.objectName()=='primary'])==1
    assert any(b.text()=='图片已出现，继续文字' for b in buttons)
    recovery._dlg.deleteLater();picker.widget.deleteLater()

def test_current_review_does_not_show_conflict_controls_when_none(pair):
    a,w,r=pair;r.show();QTest.qWait(20)
    assert r.btn_use_phone.isHidden() and r.btn_keep.isHidden()
    assert r.btn_apply.isHidden() and r.btn_reject.isHidden()
    assert any(b.text()=='定位输入框' and b.isVisible() for b in r.widget.findChildren(QPushButton))

def test_hud_uses_shared_primary_role_and_status_remains_visible(pair):
    a,w,r=pair;h=HudController();h.start()
    try:
        h.show_receiving('长文体验 '*100,1,assets=[{'status':'queued'}]);QTest.qWait(20)
        assert h._widget.styleSheet()==QSS and h._insert.property('role')=='primary'
        h.operation_event('delivery_progress',stage='image_wait',index=1,total=2)
        assert h._mode=='busy' and not h._timer.isActive() and '1/2' in h._status.text()
        assert h._widget.height()<=300
    finally:h.dismiss();h._widget.deleteLater()

def test_screenshots_of_production_widgets_when_requested(pair):
    folder=os.environ.get('DT_UI_EVIDENCE_DIR')
    if not folder:return
    a,w,r=pair;dest=Path(folder);dest.mkdir(parents=True,exist_ok=True)
    w.show_window();QTest.qWait(60)
    w.widget.grab().save(str(dest/'connection.png'))
    from PySide6.QtWidgets import QTabWidget
    tabs=w.widget.findChild(QTabWidget)
    for n,name in [(1,'settings'),(2,'recent')]:
        tabs.setCurrentIndex(n);QTest.qWait(30);w.widget.grab().save(str(dest/(name+'.png')))
    a.update_pc_text('统一的图文审阅：保留手机主稿，也能在电脑改字。');r.show();QTest.qWait(30)
    r.widget.grab().save(str(dest/'review.png'))
