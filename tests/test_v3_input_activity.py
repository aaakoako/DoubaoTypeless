"""No native hooks or synthesized OS input: exercise classification and lifetime."""
import queue
import threading
import pytest

from doubao_typeless.platform.windows.input_activity import InputActivity, InputActivityMonitor, INJECTION_MARKER, is_external_input
from doubao_typeless.platform.windows.native_input import inject_paste, inject_submit, InputInjectionError


class Backend:
    def __init__(self, *, fail_install=False, fail_close=False):
        self.messages = queue.Queue(); self.fail_install = fail_install; self.fail_close = fail_close
        self.installed = False; self.uninstalled = False; self.owner = None; self.cleaned_on = None

    def install(self, observe, failed):
        self.owner = threading.get_ident(); self.observe = observe; self.failed = failed
        self.installed = True
        if self.fail_install:raise OSError('partial hook installation')

    def receive(self):
        message = self.messages.get()
        if message is None:return False
        if isinstance(message, threading.Event):message.set(); return True
        extra, injected, done = message
        self.observe(extra, injected); done.set()
        return True

    def emit(self, extra, injected):
        done = threading.Event(); self.messages.put((extra, injected, done))
        assert done.wait(1)

    def wake(self):self.messages.put(None); return True

    def synchronize(self, timeout):
        event=threading.Event();self.messages.put(event);return event.wait(timeout)

    def uninstall(self):
        self.uninstalled = True; self.cleaned_on = threading.get_ident()
        return not self.fail_close


@pytest.mark.parametrize('extra,injected,external', [
    (INJECTION_MARKER, True, False), (INJECTION_MARKER, False, True),
    (0, False, True), (0, True, True), (INJECTION_MARKER ^ 1, True, True),
])
def test_only_our_marked_injection_is_exempt(extra, injected, external):
    assert is_external_input(extra, injected) is external


def test_count_covers_early_input_and_external_automation_without_key_storage():
    backend = Backend()
    observer = InputActivity(backend_factory=lambda:backend)
    assert observer.snapshot() is None and not observer.available
    assert observer.start()
    try:
        assert observer.snapshot() == 0
        backend.emit(INJECTION_MARKER, True)
        assert observer.snapshot() == 0
        backend.emit(0, False); backend.emit(INJECTION_MARKER ^ 1, True)
        assert observer.snapshot() == 2
        assert backend.owner != threading.get_ident()
    finally:assert observer.close()
    assert observer.snapshot() is None and not observer.available
    assert backend.uninstalled and backend.cleaned_on == backend.owner
    assert observer.close() and not observer.start()


def test_partial_install_failure_releases_backend_and_cannot_report_safe():
    backend = Backend(fail_install=True); observer = InputActivity(backend_factory=lambda:backend)
    assert not observer.start()
    assert backend.uninstalled and observer.snapshot() is None
    assert not observer.close()


def test_unhook_failure_is_fail_closed():
    observer = InputActivity(backend_factory=lambda:Backend(fail_close=True))
    assert observer.start()
    assert not observer.close()
    assert not observer.available and observer.count is None


def test_observation_failure_invalidates_snapshot_before_shutdown():
    backend = Backend(); observer = InputActivity(backend_factory=lambda:backend)
    assert observer.start()
    backend.failed()
    assert observer.snapshot() is None
    assert not observer.close()


def test_start_timeout_never_later_becomes_available():
    entered, release = threading.Event(), threading.Event()
    class Slow(Backend):
        def install(self, observe, failed):
            entered.set(); release.wait(2); super().install(observe, failed)
    backend = Slow(); observer = InputActivity(backend_factory=lambda:backend)
    try:
        assert not observer.start(timeout=.01)
        assert entered.is_set() and observer.snapshot() is None
    finally:
        release.set(); observer.close(timeout=1)
    assert backend.uninstalled and observer.snapshot() is None


def test_close_timeout_never_reports_safe_and_can_finish_cleanup():
    release = threading.Event(); entered = threading.Event()
    class Stuck(Backend):
        def receive(self):entered.set(); release.wait(2); return False
        def wake(self):return False
    backend = Stuck(); observer = InputActivity(backend_factory=lambda:backend)
    assert observer.start() and entered.wait(1)
    try:
        assert not observer.close(timeout=.01)
        assert observer.snapshot() is None
    finally:release.set(); observer.close(timeout=1)
    assert backend.uninstalled


def test_marked_paste_and_submit_preserve_keys_counts_and_zero_timestamps():
    batches = []
    def send(count, events, size):
        batches.append([(e.data.ki.wVk, e.data.ki.dwFlags, e.data.ki.time, e.data.ki.dwExtraInfo) for e in events])
        return count
    assert inject_paste(send) == 4
    assert inject_submit('enter', send) == 2
    assert inject_submit('ctrl_enter', send) == 4
    assert [[(vk, flags) for vk, flags, _, _ in batch] for batch in batches] == [
        [(17,0),(86,0),(86,2),(17,2)], [(13,0),(13,2)], [(17,0),(13,0),(13,2),(17,2)]]
    assert all(t == 0 and marker == INJECTION_MARKER for batch in batches for _,_,t,marker in batch)


def test_partial_injection_cleanup_is_also_marked_without_repasting():
    batches=[]
    def send(count, events, size):
        batches.append([(e.data.ki.wVk,e.data.ki.dwFlags,e.data.ki.dwExtraInfo) for e in events])
        return 2 if len(batches)==1 else count
    with pytest.raises(InputInjectionError):inject_paste(send)
    assert batches[1] == [(86,2,INJECTION_MARKER),(17,2,INJECTION_MARKER)]


def test_monitor_start_returns_self_and_failed_start_does_not_raise():
    backend=Backend(fail_install=True);monitor=InputActivityMonitor(backend_factory=lambda:backend)
    assert monitor.start() is monitor
    assert monitor.snapshot() is None
    monitor.close()


def test_snapshot_drains_pending_external_input_before_returning():
    backend=Backend();monitor=InputActivityMonitor(backend_factory=lambda:backend).start()
    try:
        assert monitor.snapshot()==0
        backend.messages.put((0,False,threading.Event()))
        assert monitor.snapshot()==1
    finally:monitor.close()


def test_snapshot_barrier_failure_is_permanently_fail_closed():
    backend=Backend();monitor=InputActivityMonitor(backend_factory=lambda:backend).start()
    try:
        backend.synchronize=lambda timeout:False
        assert monitor.snapshot() is None and not monitor.available
    finally:monitor.close()


def test_thread_creation_failure_is_unavailable_not_a_paste_exception(monkeypatch):
    def fail(_):raise RuntimeError('thread unavailable')
    monkeypatch.setattr(threading.Thread,'start',fail)
    monitor=InputActivityMonitor(backend_factory=lambda:pytest.fail('must not install'))
    assert monitor.start() is monitor and monitor.snapshot() is None
    monitor.close()
