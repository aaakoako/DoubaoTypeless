import asyncio
from tests.test_v3_editor_transactions import product, editing, stroke


def test_compact_composer_keeps_insert_action_in_visible_area(tmp_path):
    async def run():
        async with product(tmp_path,touch=True) as (page,app,uploads):
            await page.fill('#text','手机键盘弹出之后，仍然能点击插入。')
            await page.set_viewport_size({'width':390,'height':390})
            await page.wait_for_function("document.querySelector('#app').classList.contains('compact-keyboard')")
            box=await page.locator('#sendBtn').bounding_box()
            assert box and 0<=box['y'] and box['y']+box['height']<=390
            await page.locator('#sendBtn').click(trial=True)
            assert await page.locator('#text').input_value()=='手机键盘弹出之后，仍然能点击插入。'
            await page.set_viewport_size({'width':390,'height':844})
            assert await page.locator('#text').input_value()=='手机键盘弹出之后，仍然能点击插入。'
    asyncio.run(run())


def test_browser_back_closes_sheet_then_confirms_dirty_editor_without_leaving(tmp_path):
    async def run():
        async with product(tmp_path,touch=True) as (page,app,uploads):
            original=page.url
            await page.click('#boardBtn'); await stroke(page)
            await page.go_back()
            await page.wait_for_selector('#discardEditing')
            assert page.url==original
            await page.go_back()
            await page.wait_for_selector('#sheet.show',state='hidden')
            assert await page.locator('#editor').is_visible()
            await page.go_back(); await page.click('#discardEditing')
            await page.wait_for_selector('#editor.show',state='hidden')
            assert page.url==original and uploads==[]
            await page.click('#boardBtn'); await editing(page); await page.go_back()
            await page.wait_for_selector('#editor.show',state='hidden')
            assert page.url==original
    asyncio.run(run())


def test_small_keyboard_viewport_keeps_text_commit_and_cancel_reachable(tmp_path):
    async def run():
        async with product(tmp_path,touch=True) as (page,app,uploads):
            await page.click('#boardBtn'); await editing(page)
            await page.click('#moreBtn')
            await page.locator('[data-tool="text"]').click()
            await page.locator('#stage').click(position={'x':80,'y':70})
            await page.fill('#canvasTextInput','键盘打开时也能完成标注')
            await page.set_viewport_size({'width':390,'height':390})
            for selector in ('#back','#canvasTextAdd','#canvasTextCancel'):
                box=await page.locator(selector).bounding_box()
                assert box and box['y']>=0 and box['y']+box['height']<=390
            await page.click('#canvasTextAdd')
            await page.set_viewport_size({'width':390,'height':844})
            await page.click('#done'); await page.wait_for_selector('#editor.show',state='hidden')
            assert await page.locator('.attach-card').count()==1
    asyncio.run(run())
