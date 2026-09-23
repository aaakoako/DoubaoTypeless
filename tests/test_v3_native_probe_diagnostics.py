"""Actual headless browser event arguments must not break native diagnostics."""
import asyncio
from playwright.async_api import async_playwright
from tools.verify_candidate_browser import phone_diagnostics


def test_phone_lifecycle_callbacks_accept_page_and_preserve_navigation():
    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.route('http://probe.test/**', lambda route:
                    route.fulfill(status=200, content_type='text/html', body='<p>ready</p>'))
                pending, failures, lifecycle = phone_diagnostics(page)
                await page.goto('http://probe.test/one?pair=synthetic')
                await page.reload()
                assert await page.locator('p').inner_text() == 'ready'
                assert lifecycle == {'domcontentloaded': 2, 'load': 2}
                assert not pending and not failures
            finally:
                await browser.close()
    asyncio.run(run())
