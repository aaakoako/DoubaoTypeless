"""Production Qt update button; transport/installer are explicit controlled substitutes."""
import os
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from tests.test_v3_unified_ui import pair
from doubao_typeless.services import v3_update


def until(check):
    for _ in range(100):
        if check():return
        QTest.qWait(20)
    raise AssertionError('Qt update callback timed out')

@pytest.mark.parametrize('fails',[False,True])
def test_explicit_update_button_quits_only_after_valid_handoff(pair,tmp_path,monkeypatch,fails):
    app,window,_=pair
    accepted=tmp_path/'handoff.accept';seen=[]
    window._update_package={'version':'0.5.2'}
    window.on_update_ready=lambda:seen.append(accepted.read_text())
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Yes)
    def download(*args,**kwargs):
        if fails:raise ValueError('校验失败，当前版本未改变')
        return tmp_path/'package.exe'
    monkeypatch.setattr(v3_update,'download_upgrade',download)
    monkeypatch.setattr(v3_update,'start_upgrade',lambda *a,**k:accepted)
    window.update_install.click()
    if fails:
        until(lambda:'校验失败' in window.update_status.text())
        assert window.update_install.isEnabled() and window.update_button.isEnabled()
        assert not seen and not accepted.exists()
    else:
        until(lambda:bool(seen))
        assert seen==[str(os.getpid())]
        assert '新版将自动打开' in window.update_status.text()
