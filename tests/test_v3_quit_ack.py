"""Qt quit acknowledgement must survive immediate server shutdown (real processes)."""
import os,subprocess,sys,time,uuid
from pathlib import Path
import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from doubao_typeless.ui.single_instance import request_command
QT=None
SERVER = '''
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QTimer
from doubao_typeless.ui.single_instance import listen_for_commands
qt=QCoreApplication([])
received=[]
def command(value):
    received.append(value)
    if value=='quit':qt.quit()
server=listen_for_commands(command)
if server is None:raise SystemExit(3)
Path(sys.argv[1]).write_text('listening',encoding='utf-8')
QTimer.singleShot(8000,qt.quit)
qt.exec()
raise SystemExit(0 if received==['quit'] else 4)
'''


def test_quit_reply_drains_before_server_event_loop_stops(tmp_path, monkeypatch):
    """A real second process must receive its positive ACK before immediate quit."""
    global QT
    QT=QApplication.instance() or QApplication([])
    monkeypatch.setenv('DT_V3_PIPE','DT-test-exit-ack-'+uuid.uuid4().hex)
    monkeypatch.setenv('DT_V3_DATA_DIR',str(tmp_path/'isolated'))
    marker=tmp_path/'listening'
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    server=subprocess.Popen([sys.executable,'-c',SERVER,str(marker)],env=env,
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+8
        while not marker.exists() and server.poll() is None and time.monotonic()<deadline:
            QTest.qWait(10)
        assert marker.exists(),'test-owned server failed before listen'
        assert request_command('quit',1500),'positive quit acknowledgment lost'
        out,err=server.communicate(timeout=3)
        assert server.returncode==0,(out,err)
    finally:
        if server.poll() is None:server.terminate();server.wait(3)
