import json
import threading
import time
import pytest
from doubao_typeless.services.input_check import InputCheck, make_request, parse_response, evaluate, presentation, VOICE_NOTE
from doubao_typeless.storage.settings_store import save_settings, load_settings
from tests.test_v3_assistant_delivery import app, platform, prepare

OPTIONS = {'jev_enabled': True, 'jev_api_key': 'test-key', 'jev_emotion': True, 'jev_voice_note': True}
READY = {'status': 'ready', 'issues': [{'kind': 'transcription', 'label': '疑似转写错误', 'text': '测试原稿'}],
         'suspected_transcription': True, 'tone': '急切'}


def response(request, choice='transcription', confidence=.95):
    answers = {}
    for name, question in request['questions'].items():
        selected = 'urgent' if name == 'tone' else choice
        probabilities = {k: 0. for k in question['criteria']}; probabilities[selected] = 1.
        answers[name] = {'type': 'choice', 'choice': selected, 'probabilities': probabilities, 'confidence': confidence}
    return {'model': 'jev-1.13.0', 'answers': answers}


def wait_for(check):
    deadline = time.monotonic()+2
    while time.monotonic()<deadline:
        if check():return
        time.sleep(.005)
    raise AssertionError('worker did not finish')


def test_request_and_response_keep_typed_decisions_and_no_confirmation_instruction():
    req, spans = make_request('请插入扣得克斯。然后保留图片。')
    result = parse_response(response(req), req, spans)
    assert len(result['issues']) == 2 and result['tone'] == '急切'
    assert result['suspected_transcription'] and req['model'] == 'jev-1.13.0'
    assert '确认' not in VOICE_NOTE and '原文' not in req['state']
    assert not any('image' in k for k in req['state'])
    req, _ = make_request('内容', False)
    assert 'tone' not in req['questions']


@pytest.mark.parametrize('bad', ['missing', 'nan', 'choice', 'probability'])
def test_malformed_output_never_enables_a_note(bad):
    def post(req):
        body = response(req); a = body['answers']['part_0']
        if bad == 'missing':body['answers'].pop('part_0')
        elif bad == 'nan':a['confidence'] = float('nan')
        elif bad == 'choice':a['choice'] = 'fabricated'
        else:a['probabilities']['clean'] = 1.
        return body
    result = evaluate('测试', 'secret', post=post)
    assert result['status']=='error' and not result.get('suspected_transcription')


def test_uncertainty_not_reported_as_clean():
    req, spans = make_request('不确定内容')
    result = parse_response(response(req, confidence=.2), req, spans)
    assert result['inconclusive'] and not result['suspected_transcription']
    assert '暂无法判断' in presentation(result)[0]


def test_disabled_missing_key_and_long_text_never_call_transport():
    for options in ({**OPTIONS, 'jev_enabled': False}, {**OPTIONS, 'jev_api_key': ''}):
        service = InputCheck(options, evaluate_fn=lambda *a: pytest.fail('unexpected call'), now=lambda:100.)
        service.observe(('d', 'e', 1, '稿'), '稿'); service.observe(('d', 'e', 1, '稿'), '稿')
        assert service.result['status'] in {'disabled','no_key'}
    assert evaluate('字'*12001, 'secret', post=lambda r:pytest.fail('large request'))['status']=='error'


def test_stale_response_discarded_and_same_draft_note_suppression_survives_edits():
    entered, release = threading.Event(), threading.Event(); now=[0.]
    def run(*args): entered.set(); release.wait(2); return READY.copy()
    service=InputCheck(OPTIONS,evaluate_fn=run,now=lambda:now[0])
    old=('d','e',1,'旧稿'); new=('d','e',2,'新稿')
    service.observe(old,'旧稿'); service.toggle_note(old)
    now[0]=1; service.observe(old,'旧稿'); assert entered.wait(1)
    service.observe(new,'新稿'); release.set(); wait_for(lambda:not service._busy)
    assert service.view(new)['status']=='waiting' and service._suppressed
    now[0]=2; service.observe(new,'新稿'); wait_for(lambda:not service._busy)
    assert not service.view(new)['note'] and service.view(new)['suppressed']
    service.observe(('d','next',3,'下一段'),'下一段'); assert not service._suppressed


def test_disable_and_shutdown_discard_active_response():
    for stop in ('disable','close'):
        entered, release=threading.Event(),threading.Event(); now=[0.]
        def run(*args):entered.set();release.wait(2);return READY.copy()
        service=InputCheck(OPTIONS,evaluate_fn=run,now=lambda:now[0]);identity=('d','e',1,'稿')
        service.observe(identity,'稿');now[0]=1;service.observe(identity,'稿');assert entered.wait(1)
        if stop=='disable':service.configure({**OPTIONS,'jev_enabled':False})
        else:service.close()
        release.set();wait_for(lambda:not service._busy)
        assert service.result['status']=='disabled' and not service.view(identity).get('note')


def set_ready(a):
    a.input_check.configure(OPTIONS)
    a.input_check.observe(a.input_check_identity(),a.review_text())
    a.input_check.result=READY.copy()


def test_copy_insert_history_and_new_draft_preserve_original(app):
    written=platform(app); bundle=prepare(app,'原始正文');set_ready(app)
    assert app.copy_text()==VOICE_NOTE+'\n原始正文' and app.draft.text=='原始正文'
    result=app.deliver_and_finish({'intent_id':'jev-note'},bundle)
    assert written==[VOICE_NOTE+'\n原始正文'] and result['phone_event']['rotated']
    last=app.history.last_bundle()
    assert last['source_text']=='原始正文' and last['text'].count(VOICE_NOTE)==1
    assert app.history.copy_to_new_draft(last)['text']=='原始正文'
    assert app._with_input_note(last)['text'].count(VOICE_NOTE)==1
    assert app.copy_text('下一段')=='下一段'


def test_fallback_and_cancel_use_same_frozen_note(app):
    platform(app);bundle=prepare(app,'原始正文');set_ready(app);copies=[];app._set_text=copies.append
    frozen=app._with_input_note(bundle)
    app.toggle_input_note()
    app._copy_fallback(frozen,{'error_code':'COMPOSER_NOT_FOUND','steps':[]})
    assert copies==[VOICE_NOTE+'\n原始正文']
    assert app.copy_text()=='原始正文'
    assert app._with_input_note(bundle)['text']=='原始正文'


def test_annotation_decision_frozen_before_late_response(app):
    bundle=prepare(app,'原始正文');app.input_check.configure(OPTIONS)
    frozen=app._with_input_note(bundle)
    set_ready(app)
    assert app._with_input_note(frozen)['text']=='原始正文'
    app.update_pc_text('新稿')
    assert app.copy_text()=='新稿' and app._with_input_note(bundle)['text']=='原始正文'


def test_annotation_off_when_submitted_remains_off_after_enabling(app):
    bundle=prepare(app,'原始正文')
    frozen=app._with_input_note(bundle)
    set_ready(app)
    assert app._with_input_note(frozen)['text']=='原始正文'


def test_retry_after_failure_preserves_note_preference():
    now=[0.]; calls=[]
    def run(*args):
        calls.append(args)
        return {'status':'error','message':'超时'} if len(calls)==1 else READY.copy()
    service=InputCheck(OPTIONS,evaluate_fn=run,now=lambda:now[0])
    identity=('d','e',1,'稿')
    service.observe(identity,'稿');service.toggle_note(identity)
    now[0]=1;service.observe(identity,'稿');wait_for(lambda:not service._busy)
    assert service.view(identity)['status']=='error'
    service.retry(identity);now[0]=2;service.observe(identity,'稿');wait_for(lambda:not service._busy)
    assert len(calls)==2 and service.view(identity)['suppressed']


@pytest.mark.parametrize('pc_edit',[False,True])
def test_phone_primary_note_keeps_original_receipt_and_recovery(app,pc_edit):
    from tests.test_v3_phone_primary import msg
    from doubao_typeless.core.bundle import canonical_manifest_hash,source_snapshot
    written=platform(app);app.apply_phone_update(msg('手机原稿'))
    original=source_snapshot(app.draft)
    if pc_edit:
        app.review_editing=True;app.update_pc_text('电脑修正')
    set_ready(app)
    result=app.request_insert().result(3)
    assert written==[VOICE_NOTE+'\n'+('电脑修正' if pc_edit else '手机原稿')]
    assert result['phone_event']['rotated']
    assert result['phone_event']['archived']['source_text']=='手机原稿'
    assert source_snapshot(app.draft)==original
    last=app.history.last_bundle()
    assert canonical_manifest_hash(last)==last['manifest_hash']
    assert last['source_snapshot']==original and app.history.copy_to_new_draft(last)['text']=='手机原稿'


def test_jev_key_separate_from_byok_and_redacted_on_disk(app,monkeypatch):
    monkeypatch.setenv('DT_V3_SECRET_FILE','1')
    save_settings(app.data_dir,{**OPTIONS,'byok_api_key':'other-key'})
    raw=(app.data_dir/'settings.json').read_text()
    assert 'test-key' not in raw and 'other-key' not in raw
    assert load_settings(app.data_dir)['jev_api_key']=='test-key'
    save_settings(app.data_dir,{'jev_api_key':''})
    settings=load_settings(app.data_dir)
    assert settings['jev_api_key']=='' and settings['byok_api_key']=='other-key'
    from doubao_typeless.services.v3_diagnostics import snapshot
    assert 'test-key' not in json.dumps(snapshot(app))
