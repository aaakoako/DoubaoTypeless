"""Recovery is a visible, exclusive action, not a hidden/dropped callback."""
import threading
import pytest
from tests.test_v3_assistant_delivery import app
QT=None


def test_early_recovery_refusal_is_visible_and_preserves_current_draft(app):
    app.draft.text='新稿不能因恢复失败而清空'
    notices=[]; notified=threading.Event()
    def notice(event,**kw):
        notices.append((event,kw));notified.set()
    app.ui_hook=notice
    result=app.request_recovery('confirm_continue').result(2)
    assert result['error_code']=='NO_IMAGE_TO_CONFIRM'
    assert notified.wait(1), 'recovery rejection notification never arrived'
    assert app.draft.text=='新稿不能因恢复失败而清空'
    assert any(name=='delivery_failed' and kw.get('error_code')=='NO_IMAGE_TO_CONFIRM' for name,kw in notices)


def test_busy_recovery_is_reported_and_not_silently_queued(app):
    started=threading.Event();release=threading.Event();actions=[];notices=[]
    app.ui_hook=lambda event,**kw:notices.append((event,kw))
    def block():started.set();release.wait(2);return {}
    first=app._commands.submit(block)
    try:
        assert started.wait(1)
        app.confirm_recovery=lambda mode:actions.append(mode)
        result=app.request_recovery('confirm_continue').result(1)
        assert result['error_code']=='BUSY'
        assert any(name=='delivery_failed' and kw.get('error_code')=='BUSY' for name,kw in notices)
    finally:release.set();first.result(2)
    assert not actions


def test_real_hud_does_not_cover_modal_or_lose_incoming_phone_text():
    global QT
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from doubao_typeless.ui.hud import HudController
    QT=QApplication.instance() or QApplication([])
    hud=HudController();hud.start()
    try:
        hud.show_receiving('保留旧文字');QTest.qWait(20)
        assert hud._widget.isVisible()
        with hud.modal_pause():
            assert not hud._widget.isVisible()
            hud.show_receiving('手机又更新了');QTest.qWait(20)
            assert hud.text=='手机又更新了' and not hud._widget.isVisible()
            with hud.modal_pause():
                hud.operation_event('delivery_failed',error_code='BUSY');QTest.qWait(20)
                assert not hud._widget.isVisible()
            assert not hud._widget.isVisible()
        assert not hud._widget.isVisible() and hud.text=='手机又更新了'
        hud.operation_event('delivery_start');QTest.qWait(20)
        assert hud._widget.isVisible() and not hud._timer.isActive()
    finally:hud.dismiss();hud._widget.deleteLater();QTest.qWait(10)
