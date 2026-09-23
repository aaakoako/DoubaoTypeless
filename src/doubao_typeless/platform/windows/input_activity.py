"""Transaction-scoped input activity; never stores keys, coordinates or text.

The owner must start before injection and close in finally. A missing snapshot
means unsafe to restore focus. This is an input-origin guard, not authentication.
"""
from __future__ import annotations

import ctypes
import secrets
import sys
import threading

# Windows mouse injection can truncate extraInfo to 32 bits even in a 64-bit
# process (native diagnostic 35908543979). Use a nonzero shared-width tag; do
# not mask arbitrary external tags during comparison.
INJECTION_MARKER = secrets.randbits(31) or 1


def is_external_input(extra_info: int, injected: bool) -> bool:
    # Other automation, including injected input, must still cancel recovery.
    return not (injected and extra_info == INJECTION_MARKER)


class _WindowsHooks:
    def __init__(self):
        if sys.platform != 'win32':
            raise OSError('WINDOWS_INPUT_OBSERVER_UNAVAILABLE')
        from ctypes import wintypes as w
        self.w = w
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, w.WPARAM, w.LPARAM)
        self.api.SetWindowsHookExW.argtypes = [ctypes.c_int, self.callback_type, w.HINSTANCE, w.DWORD]
        self.api.SetWindowsHookExW.restype = w.HANDLE
        self.api.UnhookWindowsHookEx.argtypes = [w.HANDLE]
        self.api.UnhookWindowsHookEx.restype = w.BOOL
        self.api.CallNextHookEx.argtypes = [w.HANDLE, ctypes.c_int, w.WPARAM, w.LPARAM]
        self.api.CallNextHookEx.restype = ctypes.c_ssize_t
        self.api.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
        self.api.GetMessageW.restype = ctypes.c_int
        self.api.PeekMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
        self.api.PostThreadMessageW.argtypes = [w.DWORD, w.UINT, w.WPARAM, w.LPARAM]
        self.api.PostThreadMessageW.restype = w.BOOL
        self.kernel.GetCurrentThreadId.restype = w.DWORD
        self.kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
        self.kernel.GetModuleHandleW.restype = w.HMODULE
        self.hooks = []; self.callbacks = []; self.thread_id = 0
        self._barrier_lock = threading.Lock(); self._barriers = {}; self._next_barrier = 0

    def install(self, observe, failed):
        w = self.w
        class Keyboard(ctypes.Structure):
            _fields_ = [('vk', w.DWORD), ('scan', w.DWORD), ('flags', w.DWORD),
                        ('time', w.DWORD), ('extra', ctypes.c_size_t)]
        class Mouse(ctypes.Structure):
            _fields_ = [('point', w.POINT), ('data', w.DWORD), ('flags', w.DWORD),
                        ('time', w.DWORD), ('extra', ctypes.c_size_t)]
        self.thread_id = self.kernel.GetCurrentThreadId()
        self.msg = w.MSG()
        self.api.PeekMessageW(ctypes.byref(self.msg), None, 0, 0, 0)
        for kind, structure, mask in ((13, Keyboard, 0x10), (14, Mouse, 0x01)):
            def receive(code, wp, lp, structure=structure, mask=mask):
                if code >= 0:
                    try:
                        item = ctypes.cast(lp, ctypes.POINTER(structure)).contents
                        observe(int(item.extra), bool(item.flags & mask))
                    except BaseException:
                        failed()
                # Never swallow any event, including those we injected ourselves.
                return self.api.CallNextHookEx(None, code, wp, lp)
            callback = self.callback_type(receive)
            self.callbacks.append(callback)  # Keep callback alive until thread exits.
            handle = self.api.SetWindowsHookExW(kind, callback, self.kernel.GetModuleHandleW(None), 0)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            self.hooks.append(handle)

    def receive(self):
        result = self.api.GetMessageW(ctypes.byref(self.msg), None, 0, 0)
        if result < 0:
            raise ctypes.WinError(ctypes.get_last_error())
        if result and self.msg.message == 0x8000 + 73:
            with self._barrier_lock:event = self._barriers.get(int(self.msg.wParam))
            if event is not None:event.set()
        return result != 0

    def synchronize(self, timeout):
        # GetMessage delivers pending low-level hook calls on this thread before
        # returning the posted barrier. It is not a guarantee against future input.
        event = threading.Event()
        with self._barrier_lock:
            self._next_barrier += 1; token = self._next_barrier
            self._barriers[token] = event
        try:
            return bool(self.api.PostThreadMessageW(self.thread_id, 0x8000 + 73, token, 0) and event.wait(timeout))
        finally:
            with self._barrier_lock:self._barriers.pop(token, None)

    def wake(self):
        return bool(self.thread_id and self.api.PostThreadMessageW(self.thread_id, 0x12, 0, 0))

    def uninstall(self):
        ok = True
        for handle in reversed(self.hooks):
            if not self.api.UnhookWindowsHookEx(handle):ok = False
        self.hooks.clear()
        return ok


class InputActivity:
    """One-shot observer. start/close return bool; snapshot() returns int or None.

    None is fail-closed: never infer 'no user input' from unavailable monitoring.
    Context management raises on startup failure; always inspect close's result
    when shutdown success matters. No hooks are installed by construction.
    """
    def __init__(self, *, backend_factory=_WindowsHooks):
        self._factory = backend_factory; self._backend = None
        self._lock = threading.Lock(); self._ready = threading.Event(); self._stop = threading.Event()
        self._thread = None; self._available = False; self._failed = False; self._closed = False
        self._count = 0; self._cleaned = False

    @property
    def available(self):
        with self._lock:return self._available and not self._failed and not self._closed

    @property
    def count(self):
        return self.snapshot()

    def snapshot(self):
        if not self.available:return None
        if threading.current_thread() is self._thread:
            self._failure(); return None
        try:
            if not self._backend.synchronize(.5):
                self._failure(); return None
        except BaseException:
            self._failure(); return None
        with self._lock:
            return self._count if self._available and not self._failed and not self._closed else None

    def _failure(self):
        with self._lock:self._failed = True; self._available = False

    def _observe(self, extra, injected):
        if is_external_input(extra, injected):
            with self._lock:self._count += 1

    def start(self, timeout=2.0):
        with self._lock:
            if self._closed or self._thread is not None:return False
            self._thread = threading.Thread(target=self._work, name='DT-input-activity', daemon=True)
            try:self._thread.start()
            except Exception:
                self._thread = None; self._failed = True; self._closed = True
                return False
        if not self._ready.wait(timeout):
            self._failure(); self.close(timeout=timeout); return False
        return self.available

    def _work(self):
        try:
            self._backend = self._factory()
            self._backend.install(self._observe, self._failure)
            with self._lock:
                self._available = not self._failed and not self._closed
            self._ready.set()
            while not self._stop.is_set():
                if not self._backend.receive():
                    if not self._stop.is_set():self._failure()
                    break
        except BaseException:
            self._failure()
        finally:
            try:
                self._cleaned = self._backend is None or self._backend.uninstall()
                if not self._cleaned:self._failure()
            except BaseException:
                self._failure()
            with self._lock:self._available = False
            self._ready.set()

    def close(self, timeout=2.0):
        with self._lock:self._closed = True; self._available = False
        self._stop.set()
        thread = self._thread
        if thread is None:return True
        if thread.is_alive() and self._backend is not None:
            try:
                if not self._backend.wake():self._failure()
            except BaseException:self._failure()
        if thread is threading.current_thread():self._failure(); return False
        thread.join(timeout)
        if thread.is_alive():self._failure(); return False
        return bool(self._cleaned and not self._failed)

    def __enter__(self):
        if not self.start():
            self.close(); raise OSError('INPUT_OBSERVER_UNAVAILABLE')
        return self

    def __exit__(self, *_):
        self.close()


class InputActivityMonitor(InputActivity):
    """Application API: failed start is observable as snapshot() is None.

    Ordinary paste can continue without a monitor; automatic focus recovery
    must require a non-None baseline and an equal, non-None current snapshot.
    """
    def start(self, timeout=2.0):
        super().start(timeout=timeout)
        return self

    def __enter__(self):
        return self.start()
