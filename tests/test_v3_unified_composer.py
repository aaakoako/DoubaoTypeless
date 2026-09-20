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

def test_one_unknown_image_preserves_text_and_never_pastes_it_early(app):
    calls=[];platform(app,paste=lambda:calls.append('paste'))
    app.delivery._observe_image=lambda:'unknown';app.delivery._set_text=lambda _:calls.append('text')
    b=mixed(app);result=app.deliver_and_finish({'intent_id':'unknown'},b)
    assert calls==['paste'] and not result['phone_event']['rotated']
    assert result['progress']['text_state']=='not_attempted'
    assert app.draft.text==b['source_text']

def test_manual_confirm_continues_without_repeating_image(app):
    calls=[];platform(app,paste=lambda:calls.append('paste'))
    app.delivery._observe_image=lambda:'unknown';b=mixed(app)
    app.deliver_and_finish({'intent_id':'first'},b)
    result=app.confirm_recovery('confirm_continue')
    assert calls==['paste','paste']
    assert result['steps'][0]['evidence']=='user_confirmed'
    assert result['steps'][-1]['kind']=='text'
    assert result['phone_event']['rotated']

def test_text_only_recovery_keeps_unconfirmed_images(app):
    platform(app);app.delivery._observe_image=lambda:'unknown';b=mixed(app)
    app.deliver_and_finish({'intent_id':'first'},b)
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
    app._read_focus=lambda:FOCUS._replace(runtime_id=(99,))
    app._injected_input_stamp=1;app._input_stamp=lambda:2;app._image_baseline=baseline()
    assert app._resume_after_image(FOCUS) is None

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
