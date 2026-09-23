import asyncio
from tests.test_v3_editor_transactions import product,synced


def test_phone_input_motion_stops_and_can_be_disabled(tmp_path):
    async def run():
        async with product(tmp_path,touch=True) as (page,app,_):
            await page.emulate_media(reduced_motion='no-preference')
            await page.fill('#text','正在说话，文字同步中')
            assert await page.locator('#inputActivity').is_visible()
            assert await page.locator('#text').evaluate("el=>el.getAnimations().some(a=>a.playState==='running')")
            await page.wait_for_selector('#inputActivity',state='hidden')
            await synced(page);assert app.draft.text=='正在说话，文字同步中'
            await page.click('#settingsBtn');await page.click('#motionToggle')
            assert await page.locator('#motionToggle').get_attribute('aria-pressed')=='false'
            await page.reload();await synced(page)
            await page.fill('#text','关闭动画后仍可输入')
            assert not await page.locator('#inputActivity').is_visible()
            await synced(page);assert app.draft.text=='关闭动画后仍可输入'
            await page.click('#settingsBtn');await page.click('#motionToggle')
            await page.reload();await synced(page)
            await page.emulate_media(reduced_motion='reduce')
            await page.fill('#text','系统减少动态效果')
            assert await page.locator('#inputActivity').is_visible()
            assert await page.locator('#text').evaluate("el=>el.getAnimations().some(a=>a.playState==='running')")
            await synced(page);assert app.draft.text=='系统减少动态效果'
    asyncio.run(run())
