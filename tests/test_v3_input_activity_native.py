"""Real hooks and harmless F24 events on disposable CI desktops only."""
import os
import sys
import time

import pytest


@pytest.mark.skipif(sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true'
                    or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted',
                    reason='Requires an exclusive disposable Windows runner')
def test_native_hooks_distinguish_own_events_from_external_injection():
    import ctypes
    from doubao_typeless.platform.windows.input_activity import InputActivityMonitor, INJECTION_MARKER
    from doubao_typeless.platform.windows.native_input import INPUT, MOUSEINPUT, _key
    user32=ctypes.WinDLL('user32',use_last_error=True)
    send=user32.SendInput
    send.argtypes=[ctypes.c_uint32,ctypes.POINTER(INPUT),ctypes.c_int]
    send.restype=ctypes.c_uint32
    monitor=InputActivityMonitor().start()
    try:
        baseline=monitor.snapshot()
        assert baseline is not None
        own=(INPUT*2)(_key(0x87),_key(0x87,True))  # F24; no paste or message send.
        assert send(2,own,ctypes.sizeof(INPUT))==2
        assert monitor.snapshot()==baseline
        foreign=(INPUT*2)(_key(0x87),_key(0x87,True))
        for event in foreign:event.data.ki.dwExtraInfo=0
        assert send(2,foreign,ctypes.sizeof(INPUT))==2
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            observed=monitor.snapshot()
            if observed is not None and observed>=baseline+2:break
            time.sleep(.01)
        assert observed is not None and observed>=baseline+2
        after_keyboard=monitor.snapshot()
        def mouse_pair(marker):
            pair=(INPUT*2)()
            for event,dx in zip(pair,(1,-1)):
                event.type=0
                event.data.mi=MOUSEINPUT(dx,0,0,0x2001,0,marker)  # Relative, no coalescing.
            return pair
        assert send(2,mouse_pair(INJECTION_MARKER),ctypes.sizeof(INPUT))==2
        assert monitor.snapshot()==after_keyboard
        assert send(2,mouse_pair(0),ctypes.sizeof(INPUT))==2
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            observed=monitor.snapshot()
            if observed is not None and observed>=after_keyboard+2:break
            time.sleep(.01)
        assert observed is not None and observed>=after_keyboard+2
    finally:
        assert monitor.close()
    assert monitor.snapshot() is None
