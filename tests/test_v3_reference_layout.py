"""Regression boundaries for independent references and responsive product surfaces."""
import asyncio
import os
from pathlib import Path
import pytest
from doubao_typeless.services.input_check import make_request, parse_response, REFERENCE_DIMENSIONS
from tests.test_v3_input_check import response
from tests.test_v3_unified_ui import pair


def test_reference_uncertainty_does_not_change_emotion_or_enable_voice_note():
    request, spans = make_request('请继续处理。')
    body = response(request, choice='clean')
    for name in REFERENCE_DIMENSIONS:
        answer = body['answers']['reference_' + name]
        answer['confidence'] = .2
    result = parse_response(body, request, spans)
    assert len(result['references']) == 4
    assert all(row['state'] == 'unknown' for row in result['references'])
    assert result['tone'] == '急切' and not result['issues']
    assert not result['suspected_transcription']
    assert result['reference_scope'] == 'current_text'


@pytest.mark.parametrize('font_size', [13, 18, 24])
def test_hud_full_feedback_keeps_action_text_and_rows_separate(pair, font_size):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton
    from doubao_typeless.ui.theme import QSS
    a, _, _ = pair
    from PySide6.QtGui import QFontDatabase
    from doubao_typeless.ui.desktop import apply_ui_font
    if not QFontDatabase.families() and os.name == 'nt':
        QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR']) / 'Fonts' / 'msyh.ttc'))
    apply_ui_font()
    h = a.hud
    h.start()
    try:
        h._widget.setStyleSheet(QSS.replace('font-size:13px', f'font-size:{font_size}px'))
        h.show_receiving('这是一段较长的文字。' * 35)
        request, spans = make_request('测试')
        result = parse_response(response(request), request, spans)
        h.set_input_check({**result, 'tone':'彻底怒了', 'tone_kind':'furious', 'note':True})
        QTest.qWait(80)
        for container in (h._check_row, h._bar):
            buttons = [b for b in container.findChildren(QPushButton) if b.isVisible()]
            for button in buttons:
                assert button.width() >= button.sizeHint().width(), (font_size, button.text(), button.size())
                assert container.rect().contains(button.geometry()), (font_size, button.text(), container.size(), button.geometry())
            for i, button in enumerate(buttons):
                assert all(not button.geometry().intersects(other.geometry()) for other in buttons[i+1:])
        assert h._feedback is not None and h._tone_badge.label.text() == '彻底怒了'
        assert h._body.height() >= 40
        folder = os.environ.get('DT_REDESIGN_EVIDENCE')
        if folder:
            Path(folder).mkdir(parents=True, exist_ok=True)
            h._widget.grab().save(str(Path(folder) / f'hud-{font_size}.png'))
    finally:
        h.dismiss();h._widget.deleteLater()


@pytest.mark.parametrize('width,height', [(320,360), (360,640), (430,932)])
def test_mobile_editor_tools_remain_scroll_reachable(tmp_path, width, height):
    from tests.test_v3_editor_transactions import product, editing
    async def run():
        async with product(tmp_path, touch=True) as (page, app, uploads):
            await page.set_viewport_size({'width':width, 'height':height})
            await page.click('#boardBtn');await editing(page)
            await page.click('#moreBtn')
            await page.click('#captionToggle')
            await page.locator('#captionInput').fill('低高度时仍能编辑图注')
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.locator('#captionInput').scroll_into_view_if_needed()
            box = await page.locator('#captionInput').bounding_box()
            assert box['y'] >= 0 and box['y'] + box['height'] <= height + 1
            await page.locator('#back').click(trial=True)
            await page.locator('#done').click(trial=True)
            folder = os.environ.get('DT_REDESIGN_EVIDENCE')
            if folder:
                await page.screenshot(path=str(Path(folder) / f'phone-editor-{width}-{height}.png'))
    asyncio.run(run())


def test_surface_animation_follows_resize_without_covering_old_content(pair):
    from PySide6.QtTest import QTest
    from doubao_typeless.ui.motion import SurfacePulse
    _, window, _ = pair
    target = window.widget
    target.show()
    pulse = SurfacePulse(target)
    target.resize(680, 700)
    QTest.qWait(10)
    assert pulse.geometry() == target.rect()
    pulse.finish()


def test_review_large_text_actions_stay_reachable_in_small_window(pair):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton, QScrollArea
    from doubao_typeless.ui.theme import QSS
    a, _, review = pair
    a.update_pc_text('保留原稿，分别观察参考维度。' * 50)
    review.widget.setStyleSheet(QSS.replace('font-size:13px', 'font-size:24px'))
    review.show();review.widget.resize(360, 320)
    QTest.qWait(30)
    assert review.widget.width() <= 360
    for label in ('返回浮窗','复制','插入并复制'):
        button = next(b for b in review.widget.findChildren(QPushButton) if b.text() == label)
        assert button.isVisible() and review.widget.rect().contains(button.geometry())
        assert button.width() >= button.sizeHint().width()
    scroll = review.widget.findChild(QScrollArea)
    assert scroll.verticalScrollBar().maximum() > 0


def test_mobile_composer_and_settings_at_large_text(tmp_path):
    from tests.test_v3_editor_transactions import product
    async def run():
        async with product(tmp_path, touch=True) as (page, app, uploads):
            await page.set_viewport_size({'width':320,'height':640})
            await page.add_style_tag(content='html,body,#app{font-size:22px}button{font-size:22px}')
            await page.fill('#text','这一段需要保留完整，按钮仍能操作。')
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.locator('#clearDraft').click(trial=True)
            await page.locator('#sendBtn').click(trial=True)
            await page.locator('#settingsBtn').click()
            await page.locator('#closeSheet').click(trial=True)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.locator('#closeSheet').click()
            folder = os.environ.get('DT_REDESIGN_EVIDENCE')
            if folder:
                await page.set_viewport_size({'width':390,'height':844})
                await page.reload()
                await page.locator('#text').fill('图文一起表达，电脑接着做。')
                await page.screenshot(path=str(Path(folder) / 'phone-composer.png'), full_page=True)
    asyncio.run(run())

