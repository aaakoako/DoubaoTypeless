"""真实模块回归；UIA/平台是显式替身，不等于第三方 Agent 原生验收。"""
from __future__ import annotations
import pytest
from doubao_typeless.services.delivery_progress import summarize_delivery
from doubao_typeless.platform.windows.composer_locator import composer_candidate, choose_candidate
from doubao_typeless.core.attempt import Attempt
from doubao_typeless.services.delivery import DeliveryService
from tests.test_v3_assistant_delivery import app, platform, prepare

BUNDLE = {"text": "这段文字不能无声遗漏", "assets": [{"asset_id": "image-a"}]}

def image_step(state="unknown"):
    return {"kind": "image", "asset_id": "image-a", "state": state, "evidence": "none"}

def descriptor(**kwargs):
    return {"control_type": 50004, "enabled": True, "offscreen": False,
            "readonly": False, "password": False, "automation_id": "prompt-textarea",
            "class_name": "", "name": "", **kwargs}

def candidate(n=1):
    return {"hwnd": 100, "pid": 77, "control_hwnd": 0, "runtime_id": [42,n],
            "kind": "composer", "class_name": "Chrome_WidgetWin_1", "title": "chat", "label": "对话输入框"}

def test_unknown_image_explicitly_says_text_not_attempted():
    result=summarize_delivery(BUNDLE,{"result":"UNKNOWN","steps":[image_step()]})
    assert result["awaiting_image_confirmation"]
    assert result["text_state"] == "not_attempted"
    assert "文字尚未插入" in result["message"]
    assert result["images_observed"] == 0

def test_only_image_has_no_false_missing_text():
    result=summarize_delivery({**BUNDLE,"text":""},{"result":"UNKNOWN","steps":[image_step()]})
    assert result["text_state"] == "not_needed"
    assert "文字" not in result["message"]

def test_error_does_not_offer_manual_image_receipt():
    result=summarize_delivery(BUNDLE,{"result":"UNKNOWN","error_code":"INPUT_PARTIAL","steps":[image_step()]})
    assert result["awaiting_image_confirmation"] is False

def test_text_injected_not_observed_is_never_confirmed():
    result=summarize_delivery(BUNDLE,{"result":"UNKNOWN","steps":[image_step("observed"),{"kind":"text","state":"injected"}]})
    assert result["text_state"] == "attempted_unconfirmed"
    assert "接收待确认" in result["message"]

def test_unknown_image_continues_text_using_production_delivery():
    actions=[]
    d=DeliveryService(paste=lambda:actions.append('paste'),set_clipboard_image=lambda _:actions.append('image'),
                      set_clipboard_text=lambda _:actions.append('text'),read_focus=lambda:('Composer','chatinput',1),
                      observe_image=lambda:'unknown')
    a=d.run(Attempt('a','i','b','test'),BUNDLE)
    assert actions == ['image','paste','text','paste']
    assert a.result=='UNKNOWN'
    assert summarize_delivery(BUNDLE,a.to_dict())["text_state"]=='attempted_unconfirmed'

def test_ui_command_receives_actual_mixed_paste_progress(app):
    platform(app)
    app.delivery._observe_image=lambda:'unknown'
    # 素材注入仅替代文件系统，投递/收尾/事件均为生产方法。
    app._hydrate_bundle=lambda value:value
    bundle=prepare(app,'尚未发出的正文');bundle['assets']=[{'asset_id':'image-a'}]
    events=[];app.ui_hook=lambda name,**kw:events.append((name,kw))
    output=app.deliver_and_finish({'intent_id':'image-pause'},bundle)
    assert output['progress']['text_state']=='attempted_unconfirmed'
    assert app.history.last_bundle()['text']=='尚未发出的正文'
    complete=next(kw for name,kw in events if name=='delivery_complete')
    assert not complete['progress']['awaiting_image_confirmation']
    assert not any(name=='recovery_available' for name,_ in events)
    assert not any(name=='recovery_ask' for name,_ in events)

@pytest.mark.parametrize('changes',[
    {'password':True},{'readonly':True},{'enabled':False},{'offscreen':True},
    {'name':'Search messages'},{'class_name':'monaco-editor'},
    {'control_type':50000},{'automation_id':'search-prompt-textarea'},
    {'automation_id':'','name':'Message history'},
    {'automation_id':'','name':'Prompt library search'},
])
def test_reject_unsafe_noninput_candidates(changes):
    assert not composer_candidate([descriptor(**changes)])

@pytest.mark.parametrize('changes',[
    {},{'automation_id':'chat-input'},
    {'automation_id':'','name':'Ask anything'},
    {'automation_id':'','name':'输入消息'},
    {'control_type':50030,'keyboard_focusable':True},
])
def test_accept_explicit_editable_composer(changes):
    assert composer_candidate([descriptor(**changes)])

def test_ancestor_text_does_not_manufacture_composer():
    assert not composer_candidate([descriptor(automation_id='',name='普通输入'),{'name':'Ask anything'}])

def test_zero_candidate_does_not_guess():
    assert choose_candidate([],complete=True)['status']=='not_found'

def test_two_candidates_never_choose_first():
    assert choose_candidate([candidate(1),candidate(2)],complete=True)['status']=='ambiguous'

def test_incomplete_search_does_not_call_one_result_unique():
    assert choose_candidate([candidate()],complete=False)['status']=='incomplete'

def test_single_strong_candidate_allowed_after_complete_scan():
    assert choose_candidate([candidate()],complete=True)['reason']=='unique_in_window'

def test_exact_remembered_candidate_beats_ambiguous_window():
    saved=('class','old title',100,77,0,(42,2),'composer')
    result=choose_candidate([candidate(1),candidate(2)],complete=True,remembered=saved)
    assert result['reason']=='remembered_exact'
    assert result['candidate']['runtime_id']==[42,2]

def test_same_runtime_other_process_is_not_remembered():
    saved=('class','title',100,999,0,(42,2),'composer')
    assert choose_candidate([candidate(1),candidate(2)],complete=True,remembered=saved)['status']=='ambiguous'

def test_locate_ambiguous_does_not_focus_or_paste(app,monkeypatch):
    from doubao_typeless.platform import desktop as composer_locator, desktop as focus
    platform(app)
    calls=[]
    monkeypatch.setattr(composer_locator,'locate_current',lambda _: {'status':'ambiguous','candidates':[candidate(1),candidate(2)]})
    monkeypatch.setattr(focus,'restore_target',lambda _:calls.append('focus'))
    app.delivery._paste=lambda:calls.append('paste')
    assert app.request_locate_composer().result(2)['status']=='ambiguous'
    assert calls==[]

def test_locate_unique_restores_without_inserting_or_clearing(app,monkeypatch):
    from doubao_typeless.platform import desktop as composer_locator, desktop as focus
    monkeypatch.setattr(composer_locator,'locate_current',lambda _: {'status':'found','candidate':candidate(),'reason':'unique_in_window'})
    calls=[]
    monkeypatch.setattr(focus,'restore_target',lambda _:calls.append('focus') or True)
    app._read_focus=lambda:('Chrome_WidgetWin_1','chat',100,77,0,(42,1),'composer')
    app.delivery._paste=lambda:calls.append('paste')
    app.update_pc_text('保留此稿')
    assert app.request_locate_composer().result(2)['status']=='located'
    assert calls==['focus'] and app.draft.text=='保留此稿'


def test_locate_while_busy_explains_rejection_without_queuing(app):
    import threading
    entered, release = threading.Event(), threading.Event()
    def hold():
        entered.set()
        release.wait(2)
    future = app._commands.submit(hold)
    assert entered.wait(1)
    try:
        result = app.request_locate_composer().result(1)
        assert result['result'] == 'BUSY'
        assert app._last_delivery_status == {'event': 'command_rejected', 'error_code': 'BUSY'}
    finally:
        release.set()
        future.result(2)

def test_locate_does_not_steal_after_user_changes_application(app,monkeypatch):
    from doubao_typeless.platform import desktop as composer_locator, desktop as focus
    monkeypatch.setattr(composer_locator,'locate_current',lambda _: {'status':'found','candidate':candidate(),'reason':'unique_in_window'})
    calls=[]
    monkeypatch.setattr(focus,'restore_target',lambda _:calls.append('focus') or True)
    app._read_focus=lambda:('Notepad','my work',101,78,0,(42,1),'edit')
    assert app.request_locate_composer().result(2)['status']=='changed'
    assert calls==[]

def test_locate_aborts_if_user_changes_control_in_same_window(app,monkeypatch):
    from doubao_typeless.platform import desktop as composer_locator, desktop as focus
    monkeypatch.setattr(composer_locator,'locate_current',lambda _: {'status':'found','candidate':candidate(),'reason':'unique_in_window'})
    calls=[]
    monkeypatch.setattr(focus,'restore_target',lambda _:calls.append('focus') or True)
    frames=iter([('Chrome_WidgetWin_1','chat',100,77,0,(42,1),'composer'),
                 ('Chrome_WidgetWin_1','chat',100,77,0,(42,9),'edit')])
    app._read_focus=lambda:next(frames)
    assert app.request_locate_composer().result(2)['status']=='changed'
    assert calls==[]

def test_rich_composer_uses_same_editability_policy_as_locator():
    from doubao_typeless.platform.windows.focus import classify_element
    d=descriptor(control_type=50030,keyboard_focusable=True)
    assert composer_candidate([d]) and classify_element([d])=='composer'
    assert not composer_candidate([{**d,'readonly':None}])

def test_error_keeps_explicit_image_text_progress():
    from doubao_typeless.ui.insert_status import error_message
    text=error_message({'error_code':'TARGET_CHANGED','progress':{'images_attempted':1,'text_state':'not_attempted'}})
    assert '目标变化' in text and '文字尚未插入' in text
