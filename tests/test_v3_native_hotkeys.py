"""System registration lifecycle with explicit backend; Windows EXE smoke tests real API."""
from __future__ import annotations
import queue
import threading
import time
import pytest
from doubao_typeless.platform.windows.native_hotkeys import Combination, NativeHotkeys, parse_combination

@pytest.mark.parametrize('combo,mods,vk', [('<alt>+i',1,73),('<ctrl>+<alt>+q',3,81),
 ('<shift>+<ctrl>+<f4>',6,0x73),('<cmd>+<space>',8,32),('<ALT_L>+I',1,73)])
def test_parse_existing_settings(combo,mods,vk):
    assert parse_combination(combo)==Combination(mods,vk)

@pytest.mark.parametrize('combo',['i','<alt>','<alt>+i+q','<ctrl>+<f12>','<alt>+<esc>','<ctrl>++'])
def test_unsupported_binding_is_explicit(combo):
    with pytest.raises(ValueError):parse_combination(combo)

class FakeAPI:
    def __init__(self,fail=()):
        self.messages=queue.Queue();self.calls=[];self.fail=fail
    def open(self):self.owner=threading.get_ident();return self.owner
    def register(self,ident,combo):
        self.calls.append(('register',ident,threading.get_ident()))
        return 1409 if ident in self.fail else 0
    def unregister(self,ident):self.calls.append(('unregister',ident,threading.get_ident()))
    def receive(self):return self.messages.get(timeout=2)
    def wake_stop(self,tid):
        assert tid==self.owner
        self.messages.put(None)

def wait_for(check):
    deadline=time.monotonic()+1
    while time.monotonic()<deadline:
        if check():return
        time.sleep(.005)
    assert check()

def test_real_registration_result_not_only_probe():
    api=FakeAPI(fail={0x5100})
    s=NativeHotkeys([('<alt>+i',lambda:None),('<alt>+q',lambda:None)],backend_factory=lambda:api).start()
    try:
        assert s.registered==['<alt>+q'] and '1409' in s.failures[0]
    finally:s.stop()
    assert [v[1] for v in api.calls if v[0]=='unregister']==[0x5101]

def test_dispatch_and_unregister_use_owner_thread():
    api=FakeAPI();called=[]
    s=NativeHotkeys([('<alt>+i',lambda:called.append(threading.get_ident()))],backend_factory=lambda:api).start()
    api.messages.put(0x5100);wait_for(lambda:bool(called));s.stop()
    assert called==[api.owner]
    assert all(call[2]==api.owner for call in api.calls)
    assert not s._thread.is_alive()

def test_callback_error_does_not_kill_registration(monkeypatch):
    errors=[];count=[]
    import doubao_typeless.runtime_diagnostics as diag
    monkeypatch.setattr(diag,'record_runtime_exception',lambda *args:errors.append(args))
    def call():
        count.append(1)
        if len(count)==1:raise RuntimeError('test only')
    api=FakeAPI();s=NativeHotkeys([('<alt>+i',call)],backend_factory=lambda:api).start()
    try:
        api.messages.put(0x5100);api.messages.put(0x5100)
        wait_for(lambda:len(count)==2)
        assert len(errors)==1 and s._thread.is_alive()
    finally:s.stop()

def test_stop_is_idempotent_and_unrecognized_message_cannot_invoke():
    api=FakeAPI();called=[]
    s=NativeHotkeys([('<alt>+i',lambda:called.append(1))],backend_factory=lambda:api).start()
    api.messages.put(999);s.stop();s.stop()
    assert called==[]
    assert len([v for v in api.calls if v[0]=='unregister'])==1

def test_duplicate_shortcut_is_not_silently_overwritten():
    api=FakeAPI()
    s=NativeHotkeys([('<alt>+i',lambda:None),('<ALT_L>+I',lambda:None)],backend_factory=lambda:api).start()
    try:
        assert len(s.registered)==1 and len(s.failures)==1
    finally:s.stop()

def test_windows_dispatch_selects_native_backend(monkeypatch):
    import doubao_typeless.platform.windows.hotkeys as hotkeys
    import doubao_typeless.platform.windows.native_hotkeys as native
    calls=[]
    monkeypatch.setattr(hotkeys.sys,'platform','win32')
    monkeypatch.setattr(native,'start_native_hotkeys',lambda **kw:calls.append(kw) or {'backend':'native'})
    cb=lambda:None
    assert hotkeys.start_hotkeys(on_insert=cb,on_recall=cb)['backend']=='native'
    assert calls[0]['on_insert'] is cb
