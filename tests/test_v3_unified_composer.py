"""统一UI与完整图文回归。Windows COM/按键依赖在组件测试中为显式替身。"""
from __future__ import annotations
import copy,io,json,subprocess,sys
from pathlib import Path
import pytest
from PIL import Image
from tests.test_v3_assistant_delivery import app,platform,prepare
from doubao_typeless.core.bundle import freeze_bundle
from doubao_typeless.core.attempt import Attempt
from doubao_typeless.services.delivery import DeliveryService
from doubao_typeless.adapters import cursor_windows as adapter
from doubao_typeless.platform.windows.focus import FocusSnapshot

ROOT=Path(__file__).resolve().parents[1]
FOCUS=FocusSnapshot('Chrome_WidgetWin_1','Chat',10,20,30,(40,50),'composer')

def image_asset(app,n=0):
    f=io.BytesIO();Image.new('RGB',(20,20),(90+n,70,190)).save(f,'PNG')
    a=app.store.put_png(f.getvalue(),width=20,height=20,role='markup')
    return {**a,'status':'ready','local_id':f'local-{n}','render_revision':2,'caption':f'标注{n}'}

def mixed(app,n=1):
    prepare(app,'正文  保留空格\n')
    app.draft.assets=[image_asset(app,i) for i in range(n)]
    return freeze_bundle(app.draft,bundle_id='mixed-case')

def test_mixed_all_images_observed_then_text_attempt_is_complete_not_claimed_confirmed(app):
    calls=[];platform(app,paste=lambda:calls.append('paste'))
    app.delivery._set_image=lambda _:calls.append('image')
    app.delivery._set_text=lambda t:calls.append(('text',t))
    b=mixed(app,2);result=app.deliver_and_finish({'intent_id':'mixed'},b)
    assert result['result']=='UNKNOWN' and not result.get('error_code')
    assert [s['kind'] for s in result['steps']]==['image','image','text']
    assert result['steps'][-1]['state']=='injected'
    assert result['phone_event']['rotated'] is True
    assert app.draft.text=='' and app.draft.assets==[]
    assert app.history.last_bundle()['text']==b['text']
    assert calls==['image','paste','image','paste',('text',b['text']),'paste']

def test_unobservable_image_still_pastes_text_and_preserves_history(app):
    calls=[];platform(app,paste=lambda:calls.append('paste'))
    app.delivery._observe_image=lambda:'unknown';app.delivery._set_text=lambda _:calls.append('text')
    b=mixed(app);result=app.deliver_and_finish({'intent_id':'unknown'},b)
    assert calls==['paste','text','paste'] and result['phone_event']['rotated']
    assert result['progress']['text_state']=='attempted_unconfirmed'
    assert app.draft.text=='' and app.history.last_bundle()['text']==b['text']

def test_manual_confirm_continues_without_repeating_image(app):
    calls=[];platform(app,paste=lambda:calls.append('paste'))
    app.delivery._observe_image=lambda:'unknown';b=mixed(app)
    # Recover a persisted pre-fix attempt whose image receipt was unknown.
    app.delivery._resume_input=lambda _:None
    app.deliver_and_finish({'intent_id':'first'},b)
    app._last_attempt.steps[-1].state='unknown';app._last_attempt.error_code=None
    app.delivery._resume_input=None
    result=app.confirm_recovery('confirm_continue')
    assert calls==['paste','paste']
    assert result['steps'][0]['evidence']=='user_confirmed'
    assert result['steps'][-1]['kind']=='text'
    assert result['phone_event']['rotated']

def test_text_only_recovery_keeps_unconfirmed_images(app):
    platform(app);app.delivery._observe_image=lambda:'unknown';b=mixed(app)
    app.delivery._resume_input=lambda _:None
    app.deliver_and_finish({'intent_id':'first'},b)
    app.delivery._resume_input=None
    result=app.confirm_recovery('text_only')
    assert result['text_only'] and not result['phone_event']['rotated']
    assert app.draft.assets and app.draft.text==b['source_text']

def test_new_text_during_mixed_delivery_never_rotates(app):
    platform(app);b=mixed(app)
    def on_text(_):app.update_pc_text('下一段新内容')
    app.delivery._set_text=on_text
    app.delivery._read_clipboard_text=None
    result=app.deliver_and_finish({'intent_id':'changed'},b)
    assert not result['phone_event']['rotated'] and app.draft.text=='下一段新内容'

def test_failure_after_image_does_not_lose_copy_or_steps(app):
    platform(app);b=mixed(app)
    def fail(_):raise OSError('clipboard busy')
    app.delivery._set_text=fail
    result=app.deliver_and_finish({'intent_id':'fail'},b)
    assert result['error_code'] and not result['phone_event']['rotated']
    assert [s['kind'] for s in result['steps']]==['image']
    assert not app.ledger.busy and app.history.last_bundle()['text']==b['text']

def test_scope_recovery_refusal_prevents_text():
    calls=[]
    service=DeliveryService(read_focus=lambda:FOCUS,paste=lambda:calls.append('paste'),
        set_clipboard_image=lambda _:None,set_clipboard_text=lambda _:calls.append('text'),
        observe_image=lambda:'observed',resume_input=lambda _:None)
    a=service.run(Attempt('a','i','b','x'),{'assets':[{'asset_id':'a'}],'text':'never'})
    assert a.result=='PARTIAL' and a.error_code=='TARGET_CHANGED' and calls==['paste']

def test_progress_reports_image_then_wait_then_text():
    events=[]
    d=DeliveryService(read_focus=lambda:FOCUS,paste=lambda:None,set_clipboard_image=lambda _:None,
        set_clipboard_text=lambda _:None,observe_image=lambda:'observed',progress=events.append)
    d.run(Attempt('a','i','b','x'),{'assets':[{'asset_id':'a'}],'text':'text'})
    assert [e['stage'] for e in events]==['image','image_wait','text']

def baseline():
    return {'window':10,'focus':{'pid':20,'runtime_id':[40,50]},'composer_control':{'pid':20,'runtime_id':[40,50]},
        'scope':{'pid':20,'runtime_id':[90]},'scope_safe':True,'image_children':[]}

@pytest.mark.parametrize('change',[{'window':11},{'scope':{'pid':21,'runtime_id':[90]}},{'scope_safe':False},
                                   {'composer_control':{'pid':20,'runtime_id':[41]}}])
def test_observer_rejects_different_context(change):
    b=baseline();assert not adapter.same_composer_scope(b,{**b,**change})

def test_observer_accepts_attachment_focus_inside_bound_composer(monkeypatch):
    b=baseline();record={**b,'focus':{'pid':20,'runtime_id':[55]},
                      'image_children':[{'runtime_id':[101],'control_type':'50006','pending':False}]}
    seen=[]
    def probe(anchor=None):seen.append(anchor);return copy.deepcopy(record)
    monkeypatch.setattr(adapter,'capture_image_baseline',probe)
    assert adapter.observe_image(b,timeout_s=.4)=='observed' and seen==[b,b]

@pytest.mark.parametrize('node',[{'runtime_id':[1],'control_type':'50006','pending':False},
                                 {'runtime_id':[2],'control_type':'50006','pending':True},
                                 {'runtime_id':[],'control_type':'50006','pending':False},
                                 {'runtime_id':[2],'control_type':'50000','pending':False}])
def test_observer_never_confirms_old_pending_unidentified_or_button(monkeypatch,node):
    b=baseline();b['image_children']=[{'runtime_id':[1]}]
    monkeypatch.setattr(adapter,'capture_image_baseline',lambda _=None:{**b,'image_children':[node]})
    assert adapter.observe_image(b,timeout_s=0)=='unknown'

def test_cancelled_observer_does_not_wait_or_probe(monkeypatch):
    monkeypatch.setattr(adapter,'capture_image_baseline',lambda _:pytest.fail('cancelled query'))
    assert adapter.observe_image(baseline(),cancelled=lambda:True)=='unknown'

def test_new_image_disappearing_is_not_stable_receipt(monkeypatch):
    b=baseline();seq=iter([{**b,'image_children':[{'runtime_id':[2],'control_type':'50006'}]},b,b])
    monkeypatch.setattr(adapter,'capture_image_baseline',lambda _=None:next(seq,b))
    assert adapter.observe_image(b,timeout_s=.12)=='unknown'

def test_native_recovery_is_forbidden_after_new_user_input(app,monkeypatch):
    import types
    app._read_focus=lambda:FOCUS._replace(runtime_id=(99,))
    app._injected_input_stamp=1;app._input_stamp=lambda:2;app._image_baseline=baseline()
    app._delivery_input_activity=types.SimpleNamespace(snapshot=lambda:1)
    app._delivery_input_baseline=0
    assert app._resume_after_image(FOCUS) is None


def test_own_injected_timestamp_change_does_not_reject_scoped_recovery(app,monkeypatch):
    import types
    from doubao_typeless.platform.windows import automation_host
    sequence=iter([FOCUS._replace(runtime_id=(99,)),FOCUS])
    app._read_focus=lambda:next(sequence)
    app._injected_input_stamp=1;app._input_stamp=lambda:2
    app._image_baseline=baseline()
    app._delivery_input_activity=types.SimpleNamespace(snapshot=lambda:0)
    app._delivery_input_baseline=0
    calls=[]
    def restore(op,args):
        calls.append(op)
        assert args['input_stamp']==2 and args['expected']==list(FOCUS)
        return list(FOCUS)
    monkeypatch.setattr(automation_host,'host',lambda:types.SimpleNamespace(call=restore))
    assert app._resume_after_image(FOCUS)==FOCUS
    assert calls==['resume_composer']


def test_delayed_attachment_refocus_retries_only_focus_and_is_bounded(app,monkeypatch):
    import types
    from doubao_typeless.platform.windows import automation_host
    app._read_focus=lambda:FOCUS._replace(runtime_id=(99,))
    app._input_stamp=lambda:2;app._image_baseline=baseline()
    app._delivery_input_activity=types.SimpleNamespace(snapshot=lambda:0)
    app._delivery_input_baseline=0
    calls=[]
    monkeypatch.setattr(automation_host,'host',lambda:types.SimpleNamespace(
        call=lambda *args:(calls.append(args[0]) or list(FOCUS))))
    app._paste=lambda:pytest.fail('focus recovery must not replay paste')
    assert app._resume_after_image(FOCUS) is None
    assert calls==['resume_composer']*3


def test_external_input_during_restore_stops_without_another_focus_attempt(app,monkeypatch):
    import types
    from doubao_typeless.platform.windows import automation_host
    app._read_focus=lambda:FOCUS._replace(runtime_id=(99,))
    app._input_stamp=lambda:2;app._image_baseline=baseline()
    changes=iter([0,1])
    app._delivery_input_activity=types.SimpleNamespace(snapshot=lambda:next(changes))
    app._delivery_input_baseline=0
    calls=[]
    monkeypatch.setattr(automation_host,'host',lambda:types.SimpleNamespace(
        call=lambda *args:(calls.append(args[0]) or list(FOCUS))))
    assert app._resume_after_image(FOCUS) is None
    assert len(calls)==1


def test_mixed_delivery_closes_activity_observer_even_when_paste_fails(app,monkeypatch):
    from doubao_typeless.platform import desktop as input_activity
    calls=[]
    class Monitor:
        def start(self):calls.append('start');return self
        def snapshot(self):return 0
        def close(self):calls.append('close')
    monkeypatch.setattr(input_activity,'start_input_activity',lambda:Monitor().start())
    platform(app)
    bundle=mixed(app)
    def fail(*args,**kw):raise OSError('synthetic')
    app.delivery.run=fail
    result=app.deliver_and_finish({'intent_id':'observer-cleanup'},bundle)
    assert result['error_code']=='DELIVERY_FAILED'
    assert calls==['start','close']
    assert app._delivery_input_activity is None and app._delivery_input_baseline is None


def test_user_input_during_timestamp_read_never_reaches_focus_helper(app,monkeypatch):
    import types
    from doubao_typeless.platform.windows import automation_host
    activity={'count':0}
    app._read_focus=lambda:FOCUS._replace(runtime_id=(99,))
    def timestamp():
        activity['count']+=1  # A user click while the timestamp is being read.
        return 2
    app._input_stamp=timestamp;app._image_baseline=baseline()
    app._delivery_input_activity=types.SimpleNamespace(snapshot=lambda:activity['count'])
    app._delivery_input_baseline=0
    monkeypatch.setattr(automation_host,'host',lambda:pytest.fail('must not steal focus'))
    assert app._resume_after_image(FOCUS) is None


def test_target_change_during_initial_input_barrier_prevents_any_paste(app,monkeypatch):
    from doubao_typeless.platform import desktop as input_activity
    written=platform(app)
    target={'focus':FOCUS}
    app._read_focus=lambda:target['focus']
    app.delivery._read_focus=app._read_focus
    app._restore_external_target=lambda:FOCUS[:2]
    class Monitor:
        def start(self):return self
        def snapshot(self):target['focus']=FOCUS._replace(runtime_id=(99,));return 0
        def close(self):pass
    monkeypatch.setattr(input_activity,'start_input_activity',lambda:Monitor().start())
    app.delivery._paste=lambda:pytest.fail('must recheck target after barrier')
    result=app.deliver_and_finish({'intent_id':'barrier-target-change'},mixed(app))
    assert result['error_code']=='TARGET_CHANGED' and not result['steps'] and not written

def test_theme_generated_outputs_match_single_source():
    subprocess.run([sys.executable,str(ROOT/'tools/export_ui_theme.py'),'--check'],check=True)
    theme=json.loads((ROOT/'assets/ui-theme.json').read_text(encoding='utf-8'))
    from doubao_typeless.ui.theme_generated import COLORS
    assert COLORS==theme['colors']
    assert COLORS['accent']=='#5B5CE2'

def test_native_and_mobile_share_primary_and_control_rules():
    from doubao_typeless.ui.theme import QSS
    css=(ROOT/'web/src/styles.css').read_text(encoding='utf-8')
    assert 'theme.generated.css' in css and 'prefers-color-scheme:dark' not in css
    assert 'box-shadow' not in css and 'QPushButton:focus' in QSS
    assert 'QTabBar::tab:selected' in QSS and 'border-bottom: 2px' in QSS
    assert 'min-height:44px' in css and 'focus-visible' in css

def test_icon_uses_same_accent():
    from tools.export_v3_icon import export
    export()
    assert '#5B5CE2' in (ROOT/'assets/icon.svg').read_text(encoding='utf-8')


def test_production_paste_records_stamp_only_after_one_native_call(monkeypatch):
    # Exercise the production wrapper itself; platform fixture otherwise replaces it.
    from doubao_typeless.app import V3App
    from doubao_typeless.platform import desktop as clipboard
    import types
    calls=[]
    monkeypatch.setattr(clipboard,'send_paste',lambda:calls.append('paste'))
    stub=types.SimpleNamespace(_input_stamp=lambda:77)
    V3App._paste(stub)
    assert calls==['paste'] and stub._injected_input_stamp==77


def test_production_input_stamp_without_windows_does_not_raise(monkeypatch):
    from doubao_typeless.app import V3App
    monkeypatch.setattr(sys,'platform','linux')
    assert V3App._input_stamp() is None


def test_production_input_stamp_uses_windows_state(monkeypatch):
    from doubao_typeless.app import V3App
    import types
    monkeypatch.setitem(sys.modules,'win32api',types.SimpleNamespace(GetLastInputInfo=lambda:1234))
    monkeypatch.setattr(sys,'platform','win32')
    assert V3App._input_stamp()==1234


def test_uploading_attachment_does_not_claim_completed_receipt(monkeypatch):
    b=baseline()
    monkeypatch.setattr(adapter,'capture_image_baseline',lambda _=None:{**b,
        'image_children':[{'runtime_id':[200],'control_type':'50006','pending':True}]})
    assert adapter.observe_image(b,timeout_s=.2)=='unknown'


@pytest.mark.parametrize('receipt',['unknown','absent'])
def test_three_images_then_text_no_receipt_does_not_short_circuit(receipt):
    calls=[]
    d=DeliveryService(read_focus=lambda:FOCUS,paste=lambda:calls.append('paste'),
        set_clipboard_image=lambda b:calls.append(b),set_clipboard_text=lambda t:calls.append(t),
        observe_image=lambda:receipt)
    bundle={'assets':[{'asset_id':str(n),'bytes_data':bytes([n])} for n in range(3)],'text':'正文'}
    result=d.run(Attempt('a','i','b','test'),bundle)
    assert calls==[bytes([0]),'paste',bytes([1]),'paste',bytes([2]),'paste','正文','paste']
    assert result.result=='UNKNOWN' and d.enter_count==0
    assert all(s.evidence=='os_input_count' for s in result.steps)
