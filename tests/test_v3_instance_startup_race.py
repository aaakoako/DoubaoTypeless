"""Real separate-process Qt commands, matching two compiled desktop instances.

A blocking Qt socket client in a Python thread shares the server's GIL and is not
representative of --quit from a second EXE. Keep command-count/deadline assertions,
but use a genuine child process and a readiness marker before delaying the listener.
"""
import json,os,subprocess,sys,time,uuid
from pathlib import Path
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from doubao_typeless.ui.single_instance import request_command,listen_for_commands
QT=None
CLIENT='''
import json,sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from doubao_typeless.ui.single_instance import request_command
app=QCoreApplication([])
Path(sys.argv[2]).write_text('connecting',encoding='utf-8')
result=request_command(sys.argv[1],1500)
print(json.dumps({'accepted':result}),flush=True)
raise SystemExit(0 if result else 2)
'''

@pytest.mark.parametrize('command',['show','quit'])
def test_command_waits_for_delayed_listener_once(monkeypatch,tmp_path,command):
    global QT
    QT=QApplication.instance() or QApplication([])
    monkeypatch.setenv('DT_V3_PIPE','DT-test-delayed-'+uuid.uuid4().hex)
    marker=tmp_path/'started'
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    child=subprocess.Popen([sys.executable,'-c',CLIENT,command,str(marker)],env=env,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
    received=[];servers=[]
    def start():servers.append(listen_for_commands(received.append))
    try:
        end=time.monotonic()+8
        while not marker.exists() and child.poll() is None and time.monotonic()<end:QTest.qWait(10)
        assert marker.exists(),'client failed before attempting connection'
        assert not servers
        QTimer.singleShot(100,start)
        while (child.poll() is None or not received) and time.monotonic()<end:QTest.qWait(10)
        out,err=child.communicate(timeout=2)
        assert child.returncode==0,(out,err)
        assert json.loads(out)=={'accepted':True}
        assert received==[command]
        assert len(servers)==1 and servers[0] is not None
    finally:
        if child.poll() is None:
            child.terminate();child.wait(3)  # Only this test's child.
        for server in servers:
            if server is not None:server.close();server.deleteLater()
        QTest.qWait(10)


def test_missing_listener_is_bounded_and_has_no_side_effect(monkeypatch):
    global QT
    QT=QApplication.instance() or QApplication([])
    monkeypatch.setenv('DT_V3_PIPE','DT-test-absent-'+uuid.uuid4().hex)
    start=time.monotonic()
    assert request_command('quit',120) is False
    assert time.monotonic()-start<.8
    assert request_command('paste',1000) is False
