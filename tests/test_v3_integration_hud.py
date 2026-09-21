import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtGui import QTextCursor
from doubao_typeless.ui.hud import HudController

@pytest.fixture
def hud():
    app = QApplication.instance() or QApplication([])
    h = HudController(); h.start()
    yield h
    h.dismiss(); h._widget.deleteLater(); app.processEvents()

def test_live_tail_manual_scroll_selection_and_drag(hud):
    text = '\n'.join(f'Line {i} sample text' for i in range(80))
    hud.show_receiving(text); QTest.qWait(30)
    bar = hud._body.verticalScrollBar()
    assert bar.maximum() > 0 and bar.value() == bar.maximum()
    bar.setValue(30)
    hud.show_receiving(text + '\nnew line'); QTest.qWait(10)
    assert bar.value() == 30 and hud._latest.isVisible()
    bar.setSliderDown(True)
    before = hud._body.toPlainText()
    hud.show_receiving(text + '\nnew line\nwhile dragging')
    assert hud._body.toPlainText() == before
    bar.setSliderDown(False); QTest.qWait(10)
    assert hud._body.toPlainText().endswith('while dragging')
    c=hud._body.textCursor();c.setPosition(0);c.setPosition(4,QTextCursor.KeepAnchor);hud._body.setTextCursor(c)
    hud.show_receiving('Replacement while selecting')
    assert hud._body.textCursor().selectedText() == 'Line'
    hud._latest.click(); QTest.qWait(20)
    assert hud._body.toPlainText() == 'Replacement while selecting'
    assert not hud._body.textCursor().hasSelection()
    assert bar.value() == bar.maximum()

def test_empty_new_round_clears_old_selection_and_border_is_real(hud):
    hud.show_receiving('old paragraph'); hud._body.selectAll()
    hud.show_receiving(''); hud.show_receiving('next round'); QTest.qWait(20)
    assert hud._body.toPlainText() == 'next round'
    assert not hud._body.textCursor().hasSelection()
    image = hud._widget.grab().toImage()
    assert image.pixelColor(0,0).alpha() == 0
    assert image.pixelColor(image.width()//2,2).alpha() > 0
    button = hud._insert.grab().toImage()
    color = button.pixelColor(button.width()//2, 5)
    assert color.blue() > color.red() + 70  # Primary action must retain Indigo, not inherit transparent background.

def test_transport_typeerror_does_not_retry_or_send_input_field():
    from doubao_typeless.services.byok import ByokService
    calls=[]
    def post(url,payload,headers,timeout):
        calls.append(payload)
        raise TypeError('inside transport')
    svc=ByokService(endpoint='https://example.invalid/v1',api_key='test',post=post)
    out=svc.polish('text',draft_id='d',revision=1,current_draft_id='d',current_revision=1)
    assert out['status']=='error' and len(calls)==1
    assert 'input' not in calls[0] and calls[0]['messages'][-1]['content']=='text'
