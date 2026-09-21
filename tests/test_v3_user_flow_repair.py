"""User's real interaction regressions: real Qt / production mobile page.
Native target input and screen pixels are explicitly substituted where noted.
"""
import asyncio
import json
import pytest
from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.test_v3_foreground_surfaces import surfaces
from tests.test_v3_editor_transactions import product, editing, synced, photo
from tests.test_v3_frontend_prod import READ_DRAFT
from doubao_typeless.storage.settings_store import load_settings


def test_settings_drag_expand_return_and_native_close_preserve_draft(surfaces):
    a,c,r=surfaces
    a._remember_external_target=lambda:None
    a.draft.text='visible draft';a._on_activity(a.draft.text,0)
    c.show_window();QTest.qWait(20)
    assert c.widget.isVisible() and a.hud._widget.isVisible()
    a.hud._idle_timeout()
    assert a.hud._widget.isVisible(), 'switching apps and silence do not dismiss draft'
    label=a.hud._status;w=a.hud._widget;before=w.pos()
    local=label.rect().center();start=label.mapToGlobal(local)
    for kind,point,button,buttons in [(QEvent.MouseButtonPress,start,Qt.LeftButton,Qt.LeftButton),
            (QEvent.MouseMove,start+QPoint(-80,-45),Qt.NoButton,Qt.LeftButton),
            (QEvent.MouseButtonRelease,start+QPoint(-80,-45),Qt.LeftButton,Qt.NoButton)]:
        QApplication.sendEvent(label,QMouseEvent(kind,local,point,button,buttons,Qt.NoModifier))
    assert w.pos()!=before
    position=w.pos()
    assert load_settings(a.data_dir)['hud_position']==[position.x(),position.y()]
    a.hud.show_receiving('more words');QTest.qWait(10)
    assert w.pos()==position
    r.show();QTest.qWait(10)
    r.editor.setPlainText('edited in expansion')
    QTest.mouseClick(r.btn_back,Qt.LeftButton);QTest.qWait(20)
    assert not r.widget.isVisible() and w.isVisible()
    assert a.hud._body.toPlainText()=='edited in expansion' and w.pos()==position
    r.show();QTest.qWait(10);r.widget.close();QTest.qWait(20)
    assert w.isVisible() and not r.widget.isVisible()


def test_pair_qr_remains_and_refreshes_after_consumption(surfaces):
    a,c,r=surfaces;c.show_window();QTest.qWait(10)
    old=c.pairing_url();code=a.auth.current_pairing_challenge()
    a.auth.complete_pairing(code)
    c._tick_countdown();QTest.qWait(10)
    assert c.qr.isVisible() and c.pairing_url()!=old
    assert '离线' in c.device_box.text()
    second=a.auth.complete_pairing(a.auth.current_pairing_challenge())
    c._tick_countdown()
    assert second and c.qr.isVisible()


def test_touch_text_can_cancel_save_switch_tools_and_close(tmp_path):
    async def run():
        async with product(tmp_path,touch=True) as (page,app,uploads):
            dialogs=[]
            page.on('dialog',lambda dialog:(dialogs.append(dialog.type),asyncio.create_task(dialog.dismiss())))
            await page.locator('#boardBtn').tap();await editing(page)
            assert await page.locator('[data-tool=pen] svg').count()==1
            await page.locator('#moreBtn').tap();await page.locator('[data-tool=text]').tap()
            box=await page.locator('#stage').bounding_box()
            await page.touchscreen.tap(box['x']+box['width']*.4,box['y']+box['height']*.6)
            await page.wait_for_selector('#canvasTextPanel',state='visible')
            await page.locator('#canvasTextCancel').tap()
            assert await page.locator('#canvasTextPanel').is_hidden()
            await page.locator('#back').tap()
            await page.wait_for_selector('#editor.show',state='hidden')
            assert not uploads and not dialogs
            await page.locator('#boardBtn').tap();await editing(page)
            await page.locator('#moreBtn').tap();await page.locator('[data-tool=text]').tap()
            box=await page.locator('#stage').bounding_box()
            await page.touchscreen.tap(box['x']+box['width']*.4,box['y']+box['height']*.6)
            await page.fill('#canvasTextInput','文字可编辑且能退出')
            # Header Save also commits typed text without forcing an extra tap.
            await page.locator('#done').tap();await page.wait_for_selector('#editor.show',state='hidden');await synced(page)
            saved=await page.evaluate(READ_DRAFT)
            assert '文字可编辑且能退出' in saved['assets'][0]['scene']
            await page.set_input_files('#file',photo());await editing(page)
            await page.locator('#moreBtn').tap();await page.locator('[data-tool=text]').tap()
            # Toolbar/header taps never become canvas text gestures.
            await page.locator('#undoBtn').tap();await page.locator('#back').tap()
            await page.wait_for_selector('#editor.show',state='hidden')
            await synced(page)
            assert len(app.draft.assets)==1 and not dialogs
            # Screenshot acquisition is a labelled synthetic pixel source. UI/auth/upload are real.
            app.capture._grab=lambda scope:photo()['buffer']
            for session in app.auth.sessions.values(): session.allow_capture=True
            await page.locator('#captureBtn').tap();await editing(page)
            await page.locator('#back').tap();await page.wait_for_selector('#editor.show',state='hidden')
            assert not dialogs
    asyncio.run(run())


def test_offline_pc_insert_then_reconnect_clears_only_unchanged_phone(tmp_path):
    from tests.test_v3_assistant_delivery import platform
    async def run():
        async with product(tmp_path) as (page,app,uploads):
            platform(app)
            await page.fill('#text','A offline delivery');await synced(page)
            await page.context.set_offline(True)
            await page.wait_for_function("document.querySelector('#connText').textContent.includes('离线')")
            result=await asyncio.to_thread(lambda:app.request_insert().result(4))
            assert not result.get('error_code') and result['phone_event']['rotated']
            await page.context.set_offline(False)
            await page.wait_for_function("document.querySelector('#text').value===''",timeout=12000)
            await synced(page)
            await page.fill('#text','B received by PC');await synced(page)
            await page.context.set_offline(True)
            await page.wait_for_function("document.querySelector('#connText').textContent.includes('离线')")
            await page.fill('#text','B with new offline changes')
            result=await asyncio.to_thread(lambda:app.request_insert().result(4))
            assert not result.get('error_code')
            await page.context.set_offline(False);await synced(page)
            assert await page.locator('#text').input_value()=='B with new offline changes'
            assert app.draft.text=='B with new offline changes'
    asyncio.run(run())


def test_return_to_hud_copies_visible_pc_edit_instead_of_phone_original(surfaces):
    from tests.test_v3_phone_primary import msg
    a,c,r=surfaces;a._remember_external_target=lambda:None
    copied=[];a._set_text=copied.append
    a.apply_phone_update(msg('phone original'))
    r.show();r.editor.setPlainText('PC edited version')
    QTest.mouseClick(r.btn_back,Qt.LeftButton);QTest.qWait(20)
    assert a.hud._body.toPlainText()=='PC edited version'
    QTest.mouseClick(a.hud._copy,Qt.LeftButton)
    assert copied==['PC edited version'] and a.draft.text=='phone original'
