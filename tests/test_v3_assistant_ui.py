"""真实Qt组件事件循环/几何检查，不声明Windows系统焦点或托盘实机通过。"""
from __future__ import annotations
import os
import threading
from pathlib import Path
import pytest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from doubao_typeless.app import V3App
from doubao_typeless.ui.hud import HudController
from doubao_typeless.ui.desktop import ReviewPanel,ClientWindow,apply_ui_font

QT_APP=None
@pytest.fixture(scope='module',autouse=True)
def qt_app():
    global QT_APP
    QT_APP=QApplication.instance() or QApplication([])
    apply_ui_font(QT_APP)
    yield QT_APP

@pytest.fixture
def hud():
    h=HudController();h.start()
    yield h
    h.hide(); h._widget.deleteLater();QTest.qWait(1)


def test_network_thread_really_shows_widget_on_gui_loop(hud):
    t=threading.Thread(target=lambda:hud.show_receiving('网络线程文字'*120))
    t.start();t.join()
    QTest.qWait(30)
    assert hud._widget.isVisible()
    assert hud._body.toPlainText()=='网络线程文字'*120
    assert hud._widget.width()==400
    assert hud._widget.height()<=300
    assert hud._body.verticalScrollBar().maximum()>0
    # 初次长文自动追尾；按2026-09-22用户反馈，未完成稿不自动隐藏。
    assert hud._body.verticalScrollBar().value()==hud._body.verticalScrollBar().maximum()
    assert not hud._timer.isActive()


def test_reading_selection_survives_append_and_pauses_idle(hud):
    text='第%02d行：长文内容\n'
    content=''.join(text%i for i in range(50))
    hud.show_receiving(content);QTest.qWait(20)
    cursor=hud._body.textCursor();cursor.setPosition(5);cursor.setPosition(12,QTextCursor.KeepAnchor)
    hud._body.setTextCursor(cursor)
    hud._body.verticalScrollBar().setValue(0)
    selected=hud._body.textCursor().selectedText()
    assert not hud._timer.isActive()
    hud.show_receiving(content+'追加一行')
    QTest.qWait(20)
    assert hud._body.textCursor().selectedText()==selected
    assert hud._body.verticalScrollBar().value()==0
    assert not hud._timer.isActive()


def test_first_show_completes_tail_before_deferred_timers(hud):
    hud.show_receiving('网络线程文字'*120)
    bar=hud._body.verticalScrollBar()
    assert bar.maximum()>0 and bar.value()==bar.maximum()


def test_late_document_layout_follows_tail_but_keeps_manual_reading(hud):
    hud.show_receiving('长文内容\n' * 80);QTest.qWait(30)
    bar = hud._body.verticalScrollBar()
    hud._body.document().setDocumentMargin(22);QTest.qWait(20)
    assert bar.value() == bar.maximum()
    bar.setValue(20)
    hud._body.document().setDocumentMargin(30);QTest.qWait(20)
    assert bar.value() == 20


def test_cursor_visibility_after_range_change_does_not_leave_tail_margin(hud):
    hud.show_receiving('长文内容\n'*80);QTest.qWait(30)
    bar=hud._body.verticalScrollBar()
    hud._body.document().setDocumentMargin(22)
    # Windows QTextEdit may scroll to the final cursor before its bottom margin
    # after notifying rangeChanged. Model that ordering, not a longer deadline.
    bar.setValue(bar.maximum()-4);QTest.qWait(20)
    assert bar.value()==bar.maximum()
    hud._body.document().setDocumentMargin(30)
    bar.setValue(20);QTest.qWait(20)
    assert bar.value()==20, 'queued tail correction interrupted manual reading'


def test_hud_shrinks_for_next_short_draft(hud):
    hud.show_receiving('long line '*400);QTest.qWait(20)
    old=hud._widget.height()
    hud.hide();hud.show_receiving('新段落');QTest.qWait(20)
    assert hud._widget.height()<old
    assert not hud._timer.isActive()


def test_review_commits_edit_before_queued_insert(tmp_path):
    app=V3App(data_dir=tmp_path,port=0)
    panel=ReviewPanel(app)
    seen=[]
    app.request_insert=lambda:seen.append(app.draft.text)
    try:
        panel.show();QTest.qWait(10)
        panel.editor.setPlainText('电脑改过的新文字')
        assert app.draft.text=='电脑改过的新文字'
        panel.insert()
        assert seen==['电脑改过的新文字']
        assert not panel.widget.isVisible()
    finally:
        panel.widget.deleteLater();QTest.qWait(1)
        app._commands.close();app.db.conn.close();app._lock.release()


def test_accept_phone_conflict_preserves_old_pc_draft(tmp_path):
    app=V3App(data_dir=tmp_path,port=0)
    try:
        app.update_pc_text('电脑稿')
        app.update_pc_text('电脑已再次修改')
        app.review_editing=True
        app.apply_phone_update({'draft_id':app.draft.draft_id,'epoch':app.draft.epoch,'revision':1,'text':'手机冲突稿'})
        assert app.draft.text=='电脑已再次修改'
        app.accept_phone_pending()
        assert app.draft.text=='手机冲突稿'
        import json
        backups=[json.loads(p.read_text(encoding='utf-8')) for p in (tmp_path/'recovery').glob('*.json')]
        assert any(b['text']=='电脑已再次修改' for b in backups)
    finally:
        app._commands.close();app.db.conn.close();app._lock.release()


def test_connection_window_no_secret_in_readable_url_and_optional_practice(tmp_path,monkeypatch):
    import doubao_typeless.ui.desktop as ui
    monkeypatch.setattr(ui,'lan_ip',lambda:'192.168.1.100')
    app=V3App(data_dir=tmp_path,port=0)
    win=ClientWindow(app)
    try:
        win.widget.show();QTest.qWait(20)
        assert win.widget.size().width()==560 and win.widget.size().height()==600
        assert '?pair=' not in win.url_label.text()
        assert '?pair=' in win.pairing_url()
        assert not win.practice.isVisible()
        win.practice_toggle.setChecked(True)
        assert win.practice.isVisible()
    finally:
        win.widget.hide();win.widget.deleteLater();QTest.qWait(1)
        app._commands.close();app.db.conn.close();app._lock.release()
