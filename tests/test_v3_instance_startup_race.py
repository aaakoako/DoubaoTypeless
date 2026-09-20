"""Real Qt local-socket startup race; all pipes belong to the test process."""
import threading,time,uuid
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from doubao_typeless.ui.single_instance import request_command,listen_for_commands
QT=None

@pytest.mark.parametrize('command',['show','quit'])
def test_command_waits_for_delayed_listener_once(monkeypatch,command):
    global QT
    QT=QApplication.instance() or QApplication([])
    monkeypatch.setenv('DT_V3_PIPE','DT-test-delayed-'+uuid.uuid4().hex)
    received=[];servers=[];out=[]
    def start():
        servers.append(listen_for_commands(received.append))
    QTimer.singleShot(100,start)
    worker=threading.Thread(target=lambda:out.append(request_command(command,1000)))
    worker.start()
    try:
        end=time.monotonic()+2
        while (worker.is_alive() or not received) and time.monotonic()<end:QTest.qWait(10)
        worker.join(.2)
        assert out==[True] and received==[command]
        assert len(servers)==1 and servers[0] is not None
    finally:
        worker.join(2)
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
