"""Slow receipt persistence must not advertise a retry before it can run."""
import threading

from tests.test_v3_phone_primary import app, msg
from tests.test_v3_assistant_delivery import platform


def test_failure_feedback_waits_for_receipt_and_accepts_immediate_retry(app):
    platform(app)
    app.apply_phone_update(msg('保留并重试'))
    writing, release = threading.Event(), threading.Event()
    notices, retries, attempts = [], [], []
    publish = app._publish_phone_event

    def slow_publish(event):
        if not event['rotated']:
            writing.set()
            assert release.wait(3)
        publish(event)

    def deliver(intent, bundle):
        attempts.append(1)
        if len(attempts) == 1:
            return {'result': 'NO_STEPS', 'error_code': 'TARGET_CHANGED', 'steps': []}
        return {'result': 'UNKNOWN', 'steps': [
            {'kind': 'text', 'state': 'injected', 'evidence': 'os_input_count'}]}

    def notice(event, **payload):
        notices.append((event, payload))
        if event == 'delivery_failed':
            retries.append(app.request_insert())

    app._publish_phone_event = slow_publish
    app._on_intent = deliver
    app.ui_hook = notice
    first = app.request_insert()
    try:
        assert writing.wait(3)
        assert not any(event == 'delivery_failed' for event, _ in notices)
        assert not first.done()
    finally:
        release.set()
    assert first.result(3)['error_code'] == 'TARGET_CHANGED'
    assert len(retries) == 1
    assert retries[0].result(3).get('error_code') is None
    assert len(attempts) == 2
    failures = [data for event, data in notices if event == 'delivery_failed']
    assert len(failures) == 1 and failures[0]['copied'] == '文字'


def test_busy_local_insert_is_visible_and_never_replayed(app):
    platform(app)
    app.apply_phone_update(msg())
    started, release = threading.Event(), threading.Event()
    notices = []
    app.ui_hook = lambda event, **kw: notices.append((event, kw))

    def occupied():
        started.set()
        assert release.wait(3)

    task = app._commands.submit(occupied)
    try:
        assert started.wait(3)
        rejected = app.request_insert().result(1)
        assert rejected['error_code'] == 'BUSY'
        assert ('command_rejected', {'error_code': 'BUSY'}) in notices
        assert app.hud._mode == 'busy'
    finally:
        release.set()
    task.result(3)
    assert not any(event == 'delivery_start' for event, _ in notices)
