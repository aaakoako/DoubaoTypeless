"""冻结体验版后的单一稳定性修复。FakeAPI不是真实 Windows 接收证据。"""
from __future__ import annotations
import ctypes
import pytest
from doubao_typeless.platform.windows.native_input import INPUT, InputInjectionError, inject_paste
from tests.test_v3_assistant_delivery import app, platform, prepare


class Sender:
    def __init__(self, accepted=4):
        self.accepted=accepted;self.calls=[]
    def __call__(self, count, array, size):
        self.calls.append([(i.data.ki.wVk, i.data.ki.dwFlags) for i in array])
        assert size==ctypes.sizeof(INPUT)
        return self.accepted if len(self.calls)==1 else count


def test_sendinput_layout_matches_windows_abi():
    assert ctypes.sizeof(INPUT)==(40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)


def test_only_one_ctrl_v_chord_no_enter():
    sender=Sender()
    assert inject_paste(sender)==4
    assert sender.calls==[[(0x11,0),(0x56,0),(0x56,2),(0x11,2)]]


def test_zero_injected_is_not_a_success_and_does_not_retry():
    sender=Sender(0)
    with pytest.raises(InputInjectionError) as e:inject_paste(sender,lambda:5)
    assert e.value.error_code=='INPUT_REJECTED' and e.value.winerror==5
    assert len(sender.calls)==1


@pytest.mark.parametrize('accepted,keys',[(1,[(0x11,2)]),(2,[(0x56,2),(0x11,2)]),(3,[(0x11,2)])])
def test_partial_only_releases_owned_keys_never_repastes(accepted,keys):
    sender=Sender(accepted)
    with pytest.raises(InputInjectionError) as e:inject_paste(sender)
    assert e.value.error_code=='INPUT_PARTIAL'
    assert sender.calls[1]==keys and len(sender.calls)==2


def test_cleanup_error_does_not_mask_original_partial():
    calls=[]
    def sender(*args):
        calls.append(1)
        if len(calls)==1:return 2
        raise OSError('cleanup blocked')
    with pytest.raises(InputInjectionError) as e:inject_paste(sender)
    assert e.value.accepted==2 and len(calls)==2


def test_input_rejected_keeps_draft_and_next_operation_works(app):
    events=[];app.ui_hook=lambda kind,**data:events.append((kind,data))
    sender=Sender(0)
    platform(app,paste=lambda:inject_paste(sender));prepare(app,'不要误清的原文')
    result=app.request_insert().result(2)
    assert result['error_code']=='DELIVERY_FAILED' and result['result']=='UNKNOWN'
    assert app.draft.text=='不要误清的原文' and not app.ledger.busy
    assert not result['phone_event']['rotated']
    assert any(kind=='delivery_failed' and data.get('error_code')=='DELIVERY_FAILED' for kind,data in events)
    recorded=(app.data_dir/'logs'/'runtime.log').read_text(encoding='utf-8')
    assert 'InputInjectionError' in recorded and '不要误清的原文' not in recorded
    app.delivery._paste=lambda:None
    assert app.request_insert().result(2)['result']=='UNKNOWN'
    assert app.draft.text==''


def test_real_clipboard_entry_delegates_to_checked_api(monkeypatch):
    from doubao_typeless.platform.windows import clipboard, native_input
    calls=[]
    def rejected():
        calls.append(1)
        raise InputInjectionError(0,4,5)
    monkeypatch.setattr(native_input,'send_paste',rejected)
    with pytest.raises(InputInjectionError):clipboard.send_paste()
    assert calls==[1]


def test_partial_injection_keeps_recovery_and_does_not_retry(app):
    sender=Sender(2)
    platform(app,paste=lambda:inject_paste(sender));prepare(app,'保留原稿')
    out=app.request_insert().result(2)
    assert out['result']=='UNKNOWN' and out['error_code']=='DELIVERY_FAILED'
    assert not out['phone_event']['rotated'] and app.draft.text=='保留原稿'
    assert len(sender.calls)==2  # 一次尝试、一次只释放按键，没有再贴一次。
    assert app.history.last_bundle()['source_text']=='保留原稿'
