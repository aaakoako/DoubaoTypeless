"""Real PowerShell helper lifecycle; only test-owned sleeper processes, no desktop input."""
import os, subprocess, sys, time
from pathlib import Path
import pytest
SCRIPT=Path(__file__).resolve().parents[1]/'packaging/upgrade-launch.ps1'
pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Windows helper')

def wait_file(path,worker):
    end=time.monotonic()+8
    while time.monotonic()<end:
        if path.exists():return
        assert worker.poll() is None
        time.sleep(.05)
    raise AssertionError('missing handoff')

@pytest.mark.parametrize('approve',[False,True])
def test_wait_requires_ack_and_cancel_prevents_late_install(tmp_path,approve):
    old=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],creationflags=subprocess.CREATE_NO_WINDOW)
    note=tmp_path/'handoff.ready'
    env={**os.environ,'DT_UPGRADE_ROOT':str(tmp_path),'DT_UPGRADE_WAIT_PID':str(old.pid),'DT_UPGRADE_HANDOFF':str(note)}
    worker=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(SCRIPT),'-Phase','Wait'],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        wait_file(note,worker)
        assert note.read_text()==str(old.pid)
        if approve:
            note.with_suffix('.accept').write_text(str(old.pid));time.sleep(.25)
        assert worker.poll() is None
        note.with_suffix('.cancel').write_text('cancel')
        assert worker.wait(8)==4
        assert old.poll() is None,'helper must not terminate the current application'
    finally:
        if worker.poll() is None:worker.terminate();worker.wait(5)
        old.terminate();old.wait(5)


def test_acknowledged_handoff_continues_only_after_old_process_exits(tmp_path):
    old=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],creationflags=subprocess.CREATE_NO_WINDOW)
    note=tmp_path/'handoff.ready'
    env={**os.environ,'DT_UPGRADE_ROOT':str(tmp_path),'DT_UPGRADE_WAIT_PID':str(old.pid),'DT_UPGRADE_HANDOFF':str(note)}
    worker=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(SCRIPT),'-Phase','Wait'],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        wait_file(note,worker);note.with_suffix('.accept').write_text(str(old.pid))
        # Accept and immediately exit before the helper's next polling interval.
        assert worker.poll() is None
        old.terminate();old.wait(5)
        assert worker.wait(8)==0
    finally:
        if worker.poll() is None:worker.terminate();worker.wait(5)
        if old.poll() is None:old.terminate();old.wait(5)
