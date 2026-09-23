"""真实Qt事件循环检查；未装Qt的本机不冒充这组通过，CI必须执行。"""
import os
import threading
import pytest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from doubao_typeless.ui.hud import HudController

QT_APP=None
@pytest.fixture
def hud():
    global QT_APP
    QT_APP=QApplication.instance() or QApplication([])
    h=HudController();h.start();h.show_receiving('本次正文')
    yield h
    h.dismiss();h._widget.deleteLater();QTest.qWait(10)


def test_waiting_survives_idle_timeout_and_empty_ack(hud):
    t=threading.Thread(target=lambda:hud.operation_event('sync_wait'))
    t.start();t.join();QTest.qWait(30)
    assert hud._mode=='busy' and hud._widget.isVisible()
    assert not hud._timer.isActive() and not hud._insert.isEnabled()
    hud._idle_timeout();hud.hide();QTest.qWait(10)
    assert hud._widget.isVisible() and '确认手机' in hud._status.text()


def test_failure_is_visible_copy_remains_and_success_can_hide(hud):
    hud.operation_event('sync_wait')
    hud.operation_event('delivery_failed',error_code='PHONE_OFFLINE')
    QTest.qWait(20)
    assert hud._widget.isVisible() and hud._insert.isEnabled()
    assert hud._copy.isEnabled() and '离线' in hud._status.text()
    assert not hud._timer.isActive()
    hud.operation_event('delivery_start')
    hud.operation_event('delivery_complete',result='UNKNOWN',rotated=True,text_sent=True)
    assert hud._timer.interval()==900
    hud._idle_timeout()
    assert not hud._widget.isVisible()


def test_worker_show_hide_failure_events_are_ordered_without_timer_thread_errors(hud):
    def work():
        hud.operation_event('sync_wait')
        hud.show_receiving('同步刚完成',revision=2)
        hud.operation_event('delivery_start')
        hud.operation_event('delivery_failed',error_code='TARGET_CHANGED')
    t=threading.Thread(target=work);t.start();t.join()
    QTest.qWait(40)
    assert hud._mode=='failed'
    assert hud._body.toPlainText()=='同步刚完成'
    assert '目标变化' in hud._status.text() and hud._widget.isVisible()


def test_new_content_during_operation_is_not_hidden_by_previous_receipt(hud):
    hud.operation_event('delivery_start')
    hud.show_receiving('下一段',revision=3)
    hud.operation_event('delivery_complete',result='UNKNOWN',rotated=False,text_sent=True)
    assert hud._mode=='receiving' and hud._body.toPlainText()=='下一段'
    assert not hud._timer.isActive()


def test_image_updates_do_not_remove_waiting_feedback(hud):
    hud.operation_event('sync_wait')
    hud.show_receiving('原文',1,assets=[{'id':'new','status':'queued'}],revision=4,phone_primary=True)
    assert hud._mode=='busy' and not hud._timer.isActive()
    assert '确认手机' in hud._status.text()
    assert not hud._insert.isEnabled()


def test_success_hides_even_when_pointer_still_over_clicked_button(hud):
    QTest.mouseMove(hud._insert, hud._insert.rect().center())
    hud.operation_event('delivery_start')
    hud.operation_event('delivery_complete',result='UNKNOWN',rotated=True,text_sent=True)
    hud._idle_timeout()
    assert not hud._widget.isVisible()


def test_new_edit_clears_old_failure_without_clearing_text(hud):
    hud.operation_event('delivery_failed',error_code='PHONE_OFFLINE')
    hud.show_receiving('新的输入', revision=8)
    assert hud._mode=='receiving'
    assert hud._body.toPlainText()=='新的输入'
    assert '离线' not in hud._status.text()


def test_result_timer_does_not_stop_for_old_selected_text(hud):
    hud._body.selectAll()
    hud.operation_event('delivery_start')
    hud.operation_event('delivery_complete',result='UNKNOWN',rotated=True,text_sent=True)
    assert hud._timer.isActive() and hud._timer.interval()==900


def test_copy_during_pending_insert_is_disabled_to_avoid_manual_double_paste(hud):
    hud.operation_event('sync_wait')
    assert not hud._copy.isEnabled()
    hud.operation_event('delivery_failed',error_code='PHONE_OFFLINE')
    assert hud._copy.isEnabled()


@pytest.mark.parametrize('reading', ['selection', 'slider'])
def test_hidden_reading_hud_returns_after_location_without_losing_reading(hud,reading):
    hud.show_receiving('需要保留阅读位置的正文\n'*80)
    QTest.qWait(20)
    bar=hud._body.verticalScrollBar()
    bar.setValue(bar.maximum()//2)
    if reading=='selection':hud._body.selectAll()
    else:bar.setSliderDown(True)
    before=(hud._body.toPlainText(),hud._body.textCursor().selectedText(),bar.value())
    hud.dismiss()
    assert not hud._widget.isVisible()
    hud.operation_event('composer_located')
    assert hud._widget.isVisible() and '已定位输入框' in hud._status.text()
    assert (hud._body.toPlainText(),hud._body.textCursor().selectedText(),bar.value())==before
    assert not hud._follow_tail
    bar.setSliderDown(False)


def test_location_failure_returns_visible_feedback_from_covered_review(hud):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QWidget, QLabel
    from doubao_typeless.ui.desktop import DesktopShell
    host, review = QWidget(), QWidget()
    hud.bind_foreground_surface(review)
    review.show()
    QTest.qWait(10)
    assert not hud._widget.isVisible()
    shell = SimpleNamespace(app=SimpleNamespace(hud=hud),
        client=SimpleNamespace(widget=host, delivery_status=QLabel(host)),
        review=SimpleNamespace(widget=review, banner=QLabel(review)))
    payload = {'error_code': 'NEEDS_TARGET', 'operation': 'locate'}
    hud.operation_event('delivery_failed', **payload)
    thread = threading.Thread(target=lambda: DesktopShell._from_service(shell, 'delivery_failed', **payload))
    thread.start(); thread.join()
    QTest.qWait(30)
    assert hud._widget.isVisible() and not review.isVisible()
    assert hud._body.toPlainText() == '本次正文' and hud._copy.isEnabled()
    assert '输入框' in hud._status.text()
    review.deleteLater(); host.deleteLater(); QTest.qWait(10)
