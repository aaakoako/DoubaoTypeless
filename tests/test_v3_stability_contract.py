"""稳定性契约；进程测试是真实spawn，平台故障是显式替身，不代替用户事故复现。"""
import json
import os
import time
from pathlib import Path
import pytest
from doubao_typeless.platform.windows.automation_host import AutomationHost, TargetProbeError
from doubao_typeless.platform.windows.focus import FocusSnapshot, same_target
from doubao_typeless.platform.windows.integrity import target_above_ours
from doubao_typeless.platform.windows.native_input import InputInjectionError
from doubao_typeless.services.delivery import DeliveryService
from doubao_typeless.core.attempt import Attempt
from tests.test_v3_assistant_delivery import app, platform, prepare


def echo_worker(pipe):
    while True:
        request = json.loads(pipe.recv_bytes())
        if request['op'] == 'close':
            pipe.close(); return
        pipe.send_bytes(json.dumps({'ok': True, 'value': {'pid': os.getpid()}}).encode())


def crash_worker(pipe):
    pipe.recv_bytes()
    os._exit(23)  # 仅退出测试自己创建的辅助PID。


def slow_worker(pipe):
    pipe.recv_bytes()
    time.sleep(10)


def test_real_auxiliary_process_reused_and_gracefully_closed():
    h = AutomationHost(worker=echo_worker)
    try:
        first = h.call('ping')
        assert first['pid'] != os.getpid()
        assert h.call('ping') == first
    finally:
        h.close()
    assert h.pid is None
    with pytest.raises(TargetProbeError, match='CLOSED'): h.call('ping')


def test_auxiliary_crash_does_not_kill_parent_or_replay_request():
    h = AutomationHost(worker=crash_worker)
    with pytest.raises(TargetProbeError, match='FAILED'): h.call('ping')
    assert h.pid is None
    h._worker = echo_worker
    assert h.call('ping')['pid'] != os.getpid()
    h.close()


def test_auxiliary_timeout_is_bounded_and_next_request_can_recover():
    h = AutomationHost(worker=slow_worker)
    before = time.monotonic()
    with pytest.raises(TargetProbeError, match='TIMEOUT'): h.call('ping', timeout=.15)
    assert time.monotonic() - before < 4
    assert h.pid is None
    h._worker = echo_worker
    assert h.call('ping')['pid'] != os.getpid()
    h.close()


def test_foreground_title_is_not_control_identity():
    a = FocusSnapshot('Chrome_WidgetWin_1','Loading',44,66,77,(1,2),'composer')
    assert same_target(a, a._replace(title='Streaming…'))
    assert not same_target(a,a._replace(runtime_id=(1,3)))
    assert not same_target(a,a._replace(pid=67))
    assert not same_target(a,a._replace(kind='password'))


def test_dynamic_title_does_not_break_text_delivery():
    count=[0];paste=[]
    def read():
        count[0]+=1
        return FocusSnapshot('Chrome_WidgetWin_1',f'Title {count[0]}',44,66,77,(1,2),'composer')
    d=DeliveryService(paste=lambda:paste.append(1),set_clipboard_text=lambda _:None,
        set_clipboard_image=lambda _:None,read_focus=read)
    result=d.run(Attempt('a','i','b','generic'),{'text':'原文','assets':[]})
    assert paste==[1] and not result.error_code


def test_inspection_failure_never_becomes_an_empty_allowed_target(app):
    calls=[]
    platform(app,paste=lambda:calls.append('paste'));prepare(app,'不应该发出')
    app._read_focus=lambda:(_ for _ in ()).throw(TargetProbeError('TARGET_INSPECTION_TIMEOUT'))
    result=app.request_insert().result(5)
    assert result['result']=='UNKNOWN' and result['steps']==[]
    assert calls==[] and app.draft.text=='不应该发出'
    assert not app.ledger.busy
    assert app.hud._mode=='result' and result.get('copied')=='文字'
    assert '超时' in app.hud._operation_message


def test_owned_restore_failure_is_no_steps(app,monkeypatch):
    platform(app); prepare(app)
    app._read_focus=lambda:FocusSnapshot('QtQWindowIcon','当前图文',123,os.getpid())
    import doubao_typeless.platform.desktop as f
    monkeypatch.setattr(f,'restore_target',lambda _:False)
    assert app.request_insert().result(3)['error_code']=='OWN_WINDOW'
    assert app.draft.text=='A'


def test_native_error_detail_and_windows_error_code_are_kept(app):
    error=InputInjectionError(0,4,5)
    assert error.winerror==5
    platform(app,paste=lambda:(_ for _ in ()).throw(error));prepare(app)
    out=app.request_insert().result(3)
    assert out['detail_code']=='INPUT_REJECTED'
    assert 'Windows未接受' in app.hud._operation_message
    assert not out['phone_event']['rotated'] and app.draft.text=='A'


def test_failure_feedback_and_successful_retry_share_a_single_queue(app):
    platform(app,paste=lambda:(_ for _ in ()).throw(OSError('fixture')));prepare(app)
    out=app.request_insert().result(3)
    assert out['error_code']=='DELIVERY_FAILED' and app.hud._mode=='failed'
    assert app.hud.visible
    app.delivery._paste=lambda:None
    assert app.request_insert().result(3)['phone_event']['rotated']
    assert app.hud._mode=='result' and app.draft.text==''


def test_ctrl_is_also_waited_for_before_paste():
    from doubao_typeless.platform.windows.guards import wait_modifiers_up
    assert not wait_modifiers_up(timeout_s=.04,get_async=lambda vk:0x8000 if vk==0x11 else 0)


def test_integrity_comparison_does_not_elevate():
    current=os.getpid()
    assert target_above_ours(get_pid=lambda:current+1,read_rid=lambda pid:0x2000 if pid==current else 0x3000)
    assert not target_above_ours(get_pid=lambda:current+1,read_rid=lambda pid:0x2000)


def test_unreadable_integrity_is_an_error_not_false():
    def unavailable(_):raise OSError('no token')
    with pytest.raises(OSError): target_above_ours(get_pid=lambda:os.getpid()+1,read_rid=unavailable)


def test_empty_insert_has_visible_feedback(app):
    result=app.request_insert().result(2)
    assert result['error_code']=='EMPTY_DRAFT'
    assert app.hud._mode=='failed' and '没有' in app.hud._operation_message


def test_phone_disconnected_allows_local_mirror_without_waiting(app):
    platform(app)
    app.draft.authority='phone'; app.draft.text='留在手机'
    out=app.request_insert().result(3)
    assert not out.get('error_code') and out['steps']
    assert app.hud._mode=='result' and app.draft.text=='留在手机'


def test_runtime_entry_dispatches_frozen_process_before_loading_application():
    source=(Path(__file__).resolve().parents[1]/'tools/run_v3.py').read_text(encoding='utf-8')
    assert source.index('multiprocessing.freeze_support()') < source.rindex('    main()')


def test_repeated_intent_never_leaves_a_permanent_waiting_hud(app):
    calls=[]
    platform(app,paste=lambda:calls.append('paste'))
    bundle=prepare(app,'同一次操作')
    app.deliver_and_finish({'intent_id':'repeat-id'},bundle)
    second=app.deliver_and_finish({'intent_id':'repeat-id'},bundle)
    assert second['duplicate'] and calls==['paste']
    assert app.hud._mode!='busy'


def test_copy_failure_preserves_current_draft_and_has_visible_feedback(app):
    platform(app);prepare(app,'复制失败保留')
    app._set_text=lambda _:(_ for _ in ()).throw(OSError('clipboard unavailable'))
    app.copy_text()
    assert app.draft.text=='复制失败保留' and app.hud._mode=='failed'
    assert '未复制' in app.hud._operation_message
