"""Disposable Windows only. Record injection metadata, never key values/positions."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


def main(source, report):
    if (sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
        raise RuntimeError('Requires a disposable GitHub-hosted Windows runner')
    sys.path.insert(0, str(source / 'src'))
    from doubao_typeless.platform.windows.input_activity import InputActivityMonitor
    from doubao_typeless.platform.windows.native_input import INPUT, KEYBDINPUT, MOUSEINPUT, _key

    class Recorder(InputActivityMonitor):
        def __init__(self):
            super().__init__(); self.records = []; self.records_lock = threading.Lock()

        def _observe(self, extra, injected):
            with self.records_lock:
                self.records.append({'extra_info':extra, 'extra_info_hex':hex(extra), 'injected':injected})
            super()._observe(extra, injected)

        def take(self):
            with self.records_lock:
                rows, self.records = self.records, []
                return rows

    api = ctypes.WinDLL('user32', use_last_error=True)
    send = api.SendInput
    send.argtypes = [ctypes.c_uint32, ctypes.POINTER(INPUT), ctypes.c_int]
    send.restype = ctypes.c_uint32
    from ctypes import wintypes
    original_pointer=wintypes.POINT()
    api.GetCursorPos.argtypes=[ctypes.POINTER(wintypes.POINT)]
    api.SetCursorPos.argtypes=[ctypes.c_int,ctypes.c_int]
    if not api.GetCursorPos(ctypes.byref(original_pointer)):
        raise ctypes.WinError(ctypes.get_last_error())
    output = {'passed':False, 'production_sha':subprocess.check_output(
        ['git','rev-parse','HEAD'], cwd=source, text=True).strip(),
        'pointer_bytes':ctypes.sizeof(ctypes.c_void_p),
        'abi':{'INPUT':ctypes.sizeof(INPUT),'KEYBDINPUT':ctypes.sizeof(KEYBDINPUT),
               'MOUSEINPUT':ctypes.sizeof(MOUSEINPUT),
               'keyboard_extra_offset':KEYBDINPUT.dwExtraInfo.offset,
               'mouse_extra_offset':MOUSEINPUT.dwExtraInfo.offset}, 'cases':[]}
    report.parent.mkdir(parents=True, exist_ok=True)
    monitor = Recorder().start()
    try:
        assert monitor.snapshot() is not None, 'Hook monitor unavailable'
        assert ctypes.sizeof(ctypes.c_void_p)==8, '64-bit interpreter required'
        for kind in ('keyboard','mouse'):
            for label, marker in (('wide64',0x4F12345676543210),('nonzero31',0x76543210),('zero_control',0)):
                assert monitor.snapshot() is not None
                unrelated = monitor.take()
                if kind == 'keyboard':
                    events = (INPUT*2)(_key(0x87), _key(0x87, True))
                    for event in events:event.data.ki.dwExtraInfo=marker
                else:
                    events = (INPUT*2)()
                    for event, direction in zip(events,(1,-1)):
                        event.type=0
                        event.data.mi=MOUSEINPUT(direction,0,0,0x2001,0,marker)
                case={'kind':kind,'marker_type':label,'expected_extra':marker,
                      'expected_hex':hex(marker),'before_case_metadata':unrelated}
                output['cases'].append(case)
                case['accepted']=int(send(2,events,ctypes.sizeof(INPUT)))
                observed=[]; deadline=time.monotonic()+2
                # The barrier alone may precede OS dispatch. Await callbacks too.
                while time.monotonic()<deadline:
                    assert monitor.snapshot() is not None, 'Hook observation became unavailable'
                    observed.extend(monitor.take())
                    if len(observed)>=2:break
                    time.sleep(.01)
                case['received']=observed
                case['exact_marker_count']=sum(r['injected'] and r['extra_info']==marker for r in observed)
                case['low32_marker_count']=sum(r['injected'] and r['extra_info']==(marker & 0xffffffff) for r in observed)
                # Marker mismatch is the measurement, not a reason to skip later cases.
                assert case['accepted']==2 and len(observed)>=2, 'Injection or observation incomplete'
                time.sleep(.1)
        output['passed']=True
    except BaseException as exc:
        output['error']={'type':type(exc).__name__,'message':str(exc)}
        raise
    finally:
        output['monitor_closed']=monitor.close()
        # Release the harmless test key even if SendInput accepted only key-down.
        release=(INPUT*1)(_key(0x87,True))
        send(1,release,ctypes.sizeof(INPUT))
        output['pointer_restored']=bool(api.SetCursorPos(original_pointer.x,original_pointer.y))
        if not output['monitor_closed']:output['passed']=False
        report.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    assert output['monitor_closed'], 'Hook cleanup failed'


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    main(args.source.resolve(),args.report.resolve())
