"""Primary-phone local text must retain the legacy manual insertion contract.

The phone prepare coroutine and native focus/clipboard in these service tests are
explicit fakes. Frozen Windows tests independently exercise the real interfaces.
"""
from __future__ import annotations
import asyncio
import threading
import pytest
from tests.test_v3_phone_primary import app, msg
from tests.test_v3_assistant_delivery import platform
from doubao_typeless.platform.windows.focus import FocusSnapshot
from doubao_typeless.core.bundle import source_snapshot


@pytest.fixture
def primary(app):
    written = platform(app)
    app.apply_phone_update(msg('手机主稿  保留空格\n'))
    loop = asyncio.new_event_loop()
    started = threading.Event()
    def run():
        asyncio.set_event_loop(loop)
        loop.call_soon(started.set)
        loop.run_forever()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert started.wait(2)
    app._loop = loop
    prepared = []
    async def prepare(device_id):
        prepared.append(device_id)
        return {'revision': app.draft.revision}
    app.bridge.prepare_phone = prepare
    try:
        yield app, written, prepared
    finally:
        app._commands.close(3)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(3)
        loop.close()
        app._loop = None


def focus(app, kind):
    value = FocusSnapshot('TkTopLevel', 'Notes', 22, 33, 0, (), kind)
    app._read_focus = lambda: value
    app.delivery._read_focus = app._read_focus
    app._saved_target = value


@pytest.mark.parametrize('kind', ['unknown', 'edit', 'composer'])
def test_explicit_local_text_does_not_require_composer(primary, kind):
    app, written, prepared = primary
    focus(app, kind)
    calls = []
    def locate():
        calls.append(True)
        return {'status': 'not_found'}
    app._locate_composer = locate
    result = app.request_insert().result(3)
    assert calls == [], 'plain-text manual insertion must not depend on Composer discovery'
    assert prepared == ['device-a']
    assert not result.get('error_code'), result
    assert [step['kind'] for step in result['steps']] == ['text']
    assert written == ['手机主稿  保留空格\n']
    assert result['phone_event']['rotated'] is True
    assert app.draft.authority == 'phone'


def test_unknown_target_with_images_still_requires_discovery(primary):
    app, written, prepared = primary
    focus(app, 'unknown')
    app.draft.assets = [{'local_id':'draft-photo', 'status':'editing', 'render_revision':1}]
    calls=[]
    app._locate_composer=lambda:(calls.append(True) or {'status':'not_found'})
    before=source_snapshot(app.draft)
    result=app.request_insert().result(3)
    assert calls == [True] and not prepared and not written
    assert result['error_code']=='COMPOSER_NOT_FOUND' and result['steps']==[]
    assert source_snapshot(app.draft)==before


@pytest.mark.parametrize('kind', ['code', 'terminal', 'password', 'readonly'])
def test_local_plain_text_still_rejects_unsafe_targets(primary, kind):
    app, written, prepared = primary
    focus(app, kind)
    before = source_snapshot(app.draft)
    result = app.request_insert().result(3)
    assert not written
    assert result['error_code']=='NEEDS_TARGET' and result['steps']==[]
    assert source_snapshot(app.draft)==before and not result['phone_event']['rotated']
