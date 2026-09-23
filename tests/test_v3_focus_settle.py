"""Deterministic delayed UIA focus acknowledgement; no native input."""
from contextlib import nullcontext
from types import SimpleNamespace
import sys
import pytest
from doubao_typeless.platform.windows import focus


TARGET = focus.FocusSnapshot('Chrome', 'synthetic', 10, 20, 0, (42, 7), 'composer')


class Clock:
    value = 0.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def verify(read, unchanged=lambda: True):
    clock = Clock()
    events = []
    result = focus._verify_restored_target(TARGET, read, unchanged, timeout=.05,
        clock=clock.now, sleep=clock.sleep, trace=lambda *a, **kw: events.append((a, kw)))
    return result, clock.value, events


def test_delayed_exact_identity_is_observed_without_more_actions():
    frames = iter([TARGET._replace(runtime_id=(42, 6)), TARGET])
    passed, elapsed, _ = verify(lambda: next(frames))
    assert passed and elapsed == .025


@pytest.mark.parametrize('change', [
    {'hwnd': 11}, {'pid': 21}, {'control_hwnd': 123},
    {'runtime_id': (42, 8)}, {'kind': 'edit'},
])
def test_wrong_identity_or_kind_never_passes(change):
    passed, elapsed, events = verify(lambda: TARGET._replace(**change))
    assert not passed and elapsed == .05
    assert events[-1][0] == ('verification_timeout',)


def test_external_input_before_read_cancels():
    def unexpected():
        raise AssertionError('must not read after input change')
    assert not verify(unexpected, lambda: False)[0]


def test_external_input_during_read_cancels_even_exact_match():
    states = iter([True, False])
    assert not verify(lambda: TARGET, lambda: next(states))[0]


def test_restore_focuses_once_even_when_provider_acknowledges_late(monkeypatch):
    calls = []
    element = SimpleNamespace(SetFocus=lambda: calls.append('focus'))
    uia = SimpleNamespace(ElementFromHandle=lambda _: element)
    monkeypatch.setattr(focus, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(
        IsWindow=lambda _: True, SetForegroundWindow=lambda _: calls.append('activate')))
    monkeypatch.setitem(sys.modules, 'win32process', SimpleNamespace(
        GetWindowThreadProcessId=lambda _: (30, 20)))
    monkeypatch.setitem(sys.modules, 'win32api', SimpleNamespace(GetLastInputInfo=lambda: 123))
    monkeypatch.setattr(focus, 'automation', lambda: nullcontext(uia))
    monkeypatch.setattr(focus, 'runtime_id', lambda _: TARGET.runtime_id)
    monkeypatch.setattr(focus, '_focus_trace', lambda *a, **kw: None)
    frames = iter([TARGET._replace(kind='unknown'), TARGET])
    monkeypatch.setattr(focus, '_read_target_direct', lambda: next(frames))
    original = focus._verify_restored_target
    clock = Clock()
    monkeypatch.setattr(focus, '_verify_restored_target', lambda saved, read, unchanged:
        original(saved, read, unchanged, clock=clock.now, sleep=clock.sleep, trace=lambda *a, **kw: None))
    assert focus._restore_target_direct(TARGET)
    assert calls == ['activate', 'focus']
