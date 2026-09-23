"""实际生产网页的可退出、可撤销与未完成编辑恢复；不模拟真实原生投递。"""
import asyncio
from tests.test_v3_editor_transactions import product, editing, synced, photo
from tests.test_v3_frontend_prod import READ_DRAFT


def test_next_draft_does_not_inherit_previous_insertion_feedback(tmp_path):
    async def run():
        async with product(tmp_path) as (page, app, _uploads):
            from doubao_typeless.core.bundle import freeze_bundle
            await page.fill('#text', '上一段');await synced(page)
            bundle = freeze_bundle(app.draft, bundle_id='feedback-test')
            event = app._phone_rotate_event(bundle, True, 'UNKNOWN')
            event['progress'] = {'message':'文字已发出，接收待确认'}
            await app.bridge.publish_phone_event(event)
            await page.wait_for_function("document.querySelector('#text').value==='' && document.querySelector('#sync').textContent.includes('已开始下一段')")
            await page.fill('#text', '这一段还没有插入');await synced(page)
            assert await page.locator('#deliveryStatus').is_hidden()
            assert '已开始下一段' not in await page.locator('#sync').inner_text()
            # A late duplicate receipt remains explicitly historical and never clears the new text.
            await app.bridge.publish_phone_event(event)
            await page.wait_for_function("document.querySelector('#deliveryStatus').textContent.startsWith('上次插入：')")
            assert await page.locator('#text').input_value() == '这一段还没有插入'
            await page.fill('#text', '继续编辑这一段');await synced(page)
            assert await page.locator('#deliveryStatus').is_hidden()
    asyncio.run(run())


def test_sheets_close_and_settings_describe_current_connection(tmp_path):
    async def run():
        async with product(tmp_path, touch=True) as (page, app, uploads):
            await page.fill('#text', '关闭面板后继续这一段')
            await page.locator('#settingsBtn').tap()
            await page.wait_for_function("document.querySelector('#settingsVersion').textContent.includes('电脑版本')")
            assert '协议' not in await page.locator('#settingsStatus').inner_text()
            assert '未开启' in await page.locator('#settingsGrant').inner_text()
            assert await page.locator('.page').evaluate('(el) => el.inert')
            await page.locator('#closeSheet').tap()
            assert not await page.locator('.page').evaluate('(el) => el.inert')
            assert await page.locator('#text').input_value() == '关闭面板后继续这一段'
            for session in app.auth.sessions.values():
                session.allow_insert = session.allow_capture = True
            await page.locator('#settingsBtn').tap()
            await page.wait_for_function("document.querySelector('#settingsGrant').textContent.includes('手机插入：已允许 · 截电脑：已允许')")
            await page.keyboard.press('Escape')
            assert await page.locator('#sheet').is_hidden()
            await page.locator('#historyBtn').tap()
            await page.keyboard.press('Shift+Tab')
            assert await page.evaluate("document.querySelector('#sheetDialog').contains(document.activeElement)")
            await page.locator('#closeSheet').tap()
            await page.fill('#text', '仍然可以编辑')
            await synced(page)
            assert app.draft.text == '仍然可以编辑'
    asyncio.run(run())


def test_attachment_undo_restores_order_without_hijacking_text_undo(tmp_path):
    async def run():
        async with product(tmp_path, touch=True) as (page, app, uploads):
            for i in range(3):
                await page.set_input_files('#file', {**photo(), 'name':f'{i}.png'})
                await editing(page);await page.locator('#done').tap()
                await page.wait_for_selector('#editor.show', state='hidden');await synced(page)
            original = [x['asset_id'] for x in (await page.evaluate(READ_DRAFT))['assets']]
            await page.get_by_role('button', name='删除第 2 张图片', exact=True).tap()
            await synced(page)
            await page.locator('#text').tap();await page.keyboard.type('undo this typing')
            await page.keyboard.press('Control+z')
            assert await page.locator('.attach-card').count() == 2
            assert await page.locator('#undoRemove').is_visible()
            await page.locator('#undoRemove').tap();await synced(page)
            restored = [x['asset_id'] for x in (await page.evaluate(READ_DRAFT))['assets']]
            assert restored == original
            assert await page.locator('#removeNotice').is_hidden()
            assert await page.get_by_role('button', name='前移第 1 张图片', exact=True).is_disabled()
            assert await page.get_by_role('button', name='后移第 3 张图片', exact=True).is_disabled()
    asyncio.run(run())


def test_closed_settings_response_cannot_replace_new_history_panel(tmp_path):
    async def run():
        async with product(tmp_path, touch=True) as (page, app, uploads):
            started, release = asyncio.Event(), asyncio.Event()
            async def delay(route):
                response = await route.fetch()
                started.set();await release.wait()
                await route.fulfill(response=response)
            await page.route('**/v3/status', delay)
            await page.locator('#settingsBtn').tap();await asyncio.wait_for(started.wait(), 5)
            await page.locator('#closeSheet').tap();await page.locator('#historyBtn').tap()
            async with page.expect_response(lambda r:r.url.endswith('/v3/status')):
                release.set()
            assert await page.locator('#sheetCard h2').inner_text() == '最近图文'
            assert await page.locator('#sheet').is_visible()
            await page.locator('#closeSheet').tap()
    asyncio.run(run())


def test_uncommitted_canvas_text_survives_reload_and_cancel_is_explicit(tmp_path):
    async def run():
        async with product(tmp_path, touch=True) as (page, app, uploads):
            await page.locator('#boardBtn').tap();await editing(page)
            await page.locator('#moreBtn').tap();await page.locator('[data-tool=text]').tap()
            box = await page.locator('#stage').bounding_box()
            await page.touchscreen.tap(box['x']+box['width']*.3, box['y']+box['height']*.6)
            await page.fill('#canvasTextInput', '还没有放入画布的文字')
            await page.locator('#back').tap()
            await page.wait_for_selector('#keepEditing')
            await page.locator('#closeSheet').tap()
            assert await page.locator('#canvasTextInput').input_value() == '还没有放入画布的文字'
            # Explicit page reload represents losing the tab; only this boundary accepts beforeunload.
            page.on('dialog', lambda dialog: asyncio.create_task(dialog.accept()))
            await page.reload();await synced(page)
            await page.locator('.attach-card img').tap();await editing(page)
            assert await page.locator('#canvasTextPanel').is_visible()
            assert await page.locator('#canvasTextInput').input_value() == '还没有放入画布的文字'
            await page.locator('#done').tap()
            await page.wait_for_selector('#editor.show', state='hidden');await synced(page)
            draft = await page.evaluate(READ_DRAFT)
            assert '还没有放入画布的文字' in draft['assets'][0]['scene']
            assert 'edit_text' not in draft['assets'][0]
            assert len(uploads) == 1
    asyncio.run(run())
