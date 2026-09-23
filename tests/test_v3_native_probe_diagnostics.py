"""Actual headless browser event arguments must not break native diagnostics."""
import asyncio
import sys
from types import SimpleNamespace
import pytest
from playwright.async_api import async_playwright
from tools import verify_candidate_browser as probe
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


class FakeCOMError(Exception):
    def __init__(self, hresult=-2147220991):
        self.hresult = hresult


def inspector():
    item = probe.NativeInspector.__new__(probe.NativeInspector)
    item.com_error = FakeCOMError
    item.transient_reads = {}
    return item


def test_transient_read_reacquires_elements_on_next_poll():
    item = inspector()
    frames = iter([None, [SimpleNamespace(CurrentName='ready')]])
    def controls(_):
        frame = next(frames)
        if frame is None:
            raise FakeCOMError()
        return frame
    item.controls = controls
    assert item.text(1) == ''
    assert item.text(1) == 'ready'
    assert item.transient_reads == {'text': 1}


def test_persistent_transient_read_still_expires_original_deadline():
    item = inspector()
    item.controls = lambda _: (_ for _ in ()).throw(FakeCOMError())
    with pytest.raises(AssertionError, match='original deadline'):
        asyncio.run(probe.until(lambda: item.text(1) == 'ready', timeout=.01, message='original deadline'))
    assert item.transient_reads['text'] >= 1


def test_other_com_error_is_not_hidden():
    item = inspector()
    item.controls = lambda _: (_ for _ in ()).throw(FakeCOMError(-2147024891))
    with pytest.raises(FakeCOMError):
        item.text(1)
    assert item.transient_reads == {}


def test_geometry_read_retry_never_repeats_the_click(monkeypatch):
    item = inspector()
    calls = []
    element = SimpleNamespace(CurrentName='Insert', CurrentControlType=50000, CurrentIsEnabled=True,
        CurrentBoundingRectangle=SimpleNamespace(left=0, top=0, right=20, bottom=20))
    frames = iter([None, [element], [element]])
    def controls(_):
        value = next(frames)
        if value is None:
            raise FakeCOMError()
        return value
    item.controls = controls
    mouse = SimpleNamespace(position=None, click=lambda button: calls.append(button))
    monkeypatch.setitem(sys.modules, 'pynput.mouse', SimpleNamespace(Controller=lambda: mouse,
        Button=SimpleNamespace(left='left')))
    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(
        WindowFromPoint=lambda _: 1, GetAncestor=lambda *_: 1))
    monkeypatch.setitem(sys.modules, 'win32con', SimpleNamespace(GA_ROOT=2))
    assert item.click(1, 'Insert')
    assert calls == ['left'] and item.transient_reads == {'click_geometry': 1}
