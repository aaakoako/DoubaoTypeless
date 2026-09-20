"""真实发送服务/HTTP授权回归。平台按键明确使用替身；原生包另有独立测试。"""
import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace
import pytest
from aiohttp import web, ClientSession
from doubao_typeless.services.phone_send import PhoneSendService
from doubao_typeless.storage.credentials import AuthService
from doubao_typeless.core.bundle import Draft, freeze_bundle
from doubao_typeless.platform.windows.focus import FocusSnapshot
from doubao_typeless.platform.windows.native_input import inject_submit, InputInjectionError


@pytest.fixture
def ctx(tmp_path):
    auth=AuthService(); session=auth.complete_pairing(auth.new_pairing_challenge(), allow_insert=True)
    d=Draft('draft','epoch',3,session.device_id,'原始文本',authority='phone',generation=2)
    target=[FocusSnapshot('Chrome_WidgetWin_1','Chat',10,20,0,(40,50),'composer')]
    settings={'phone_send_enabled':True,'phone_send_mode':'enter'}
    keys=[];now=[0.0]
    service=PhoneSendService(data_dir=tmp_path,options=lambda:settings,read_focus=lambda:target[0],
       wait_modifiers=lambda:True,emit=keys.append,authorize=auth.authorize,current_draft=lambda:d,clock=lambda:now[0])
    b=freeze_bundle(d,bundle_id='bundle')
    result={'result':'UNKNOWN','steps':[{'kind':'text','state':'injected','evidence':'os_input_count'}]}
    service.record_delivery(b,result,target[0])
    return SimpleNamespace(service=service,auth=auth,session=session,draft=d,keys=keys,settings=settings,
                          target=target,now=now,bundle=b,result=result,path=tmp_path)


def ticket(c):
    x=c.service.prepare(c.session); assert not x.get('error_code'),x
    return {'ticket':x['ticket'],'delivery_id':x['delivery_id'],'confirmed':True}


def test_insert_and_status_do_not_send(ctx):
    assert ctx.service.status(ctx.session)['available'];ticket(ctx)
    assert ctx.keys==[]


def test_explicit_confirm_sends_once_and_journal_has_no_content(ctx):
    body=ticket(ctx);x=ctx.service.commit(ctx.session,body)
    assert x['result']=='KEYS_SENT' and not x['message_confirmed']
    assert ctx.service.commit(ctx.session,body)['duplicate']
    assert ctx.keys==['enter']
    raw=next((ctx.path/'send-actions').glob('*.json')).read_text()
    assert '原始文本' not in raw and body['ticket'] not in raw


@pytest.mark.parametrize('confirmed',[False,None,'true',1])
def test_confirmation_must_be_boolean_true(ctx,confirmed):
    b=ticket(ctx);b['confirmed']=confirmed
    assert ctx.service.commit(ctx.session,b)['error_code']=='SEND_CONFIRMATION_REQUIRED'
    assert not ctx.keys


def test_cancel_then_open_invalidates_old_token(ctx):
    old=ticket(ctx);new=ticket(ctx)
    assert ctx.service.commit(ctx.session,old)['error_code']=='SEND_CONFIRMATION_REQUIRED'
    assert ctx.service.commit(ctx.session,new)['sent'];assert ctx.keys==['enter']


def test_sender_off_by_default_and_disable_after_prepare(ctx):
    b=ticket(ctx);ctx.settings['phone_send_enabled']=False
    assert ctx.service.commit(ctx.session,b)['error_code']=='PHONE_SEND_DISABLED';assert not ctx.keys


def test_source_new_content_refuses_old_send(ctx):
    b=ticket(ctx);ctx.draft.revision+=1;ctx.draft.text='下一段'
    assert ctx.service.commit(ctx.session,b)['error_code']=='SEND_DRAFT_CHANGED';assert not ctx.keys


def test_next_empty_generation_allows_reviewing_previous_on_pc(ctx):
    ctx.draft.generation+=1;ctx.draft.epoch='next';ctx.draft.revision=0;ctx.draft.text=''
    assert ctx.service.commit(ctx.session,ticket(ctx))['sent']


def test_later_empty_generation_is_not_the_same_previous_message(ctx):
    ctx.draft.generation+=2;ctx.draft.epoch='later';ctx.draft.text=''
    assert not ctx.service.status(ctx.session)['available']


def test_expired_and_restart_tickets_do_not_replay(ctx):
    b=ticket(ctx);ctx.now[0]=121
    assert ctx.service.commit(ctx.session,b)['error_code']=='SEND_EXPIRED';assert not ctx.keys
    ctx.service._pending.clear();assert not ctx.service.status(ctx.session)['available']


def test_target_changed_during_modifier_wait_stops(ctx):
    b=ticket(ctx)
    def wait():ctx.target[0]=ctx.target[0]._replace(runtime_id=(100,));return True
    ctx.service.wait_modifiers=wait
    assert ctx.service.commit(ctx.session,b)['error_code']=='TARGET_CHANGED';assert not ctx.keys


def test_permission_revocation_is_rechecked_after_wait(ctx):
    b=ticket(ctx)
    def wait():ctx.auth.revoke(ctx.session.session_id);return True
    ctx.service.wait_modifiers=wait
    with pytest.raises(ValueError):ctx.service.commit(ctx.session,b)
    assert not ctx.keys


def test_settings_shortcut_change_invalidates_open_confirmation(ctx):
    b=ticket(ctx);ctx.settings['phone_send_mode']='ctrl_enter'
    assert ctx.service.commit(ctx.session,b)['error_code']=='SEND_SETTINGS_CHANGED';assert not ctx.keys
    assert ctx.service.commit(ctx.session,ticket(ctx))['sent'];assert ctx.keys==['ctrl_enter']


def test_journal_failure_never_calls_platform(ctx,monkeypatch):
    def fail(*_):raise OSError('disk')
    monkeypatch.setattr('doubao_typeless.services.phone_send.write_json_atomic',fail)
    b=ticket(ctx);assert ctx.service.commit(ctx.session,b)['error_code']=='SEND_JOURNAL_FAILED'
    assert ctx.service.commit(ctx.session,b)['duplicate'];assert not ctx.keys


def test_partial_platform_send_is_consumed_never_retried(ctx):
    calls=[]
    def fail(_):calls.append(1);raise InputInjectionError(1,2)
    ctx.service.emit=fail;b=ticket(ctx)
    assert ctx.service.commit(ctx.session,b)['result']=='UNKNOWN'
    assert ctx.service.commit(ctx.session,b)['duplicate'];assert calls==[1]


def test_new_delivery_invalidates_old_confirmation(ctx):
    old=ticket(ctx);ctx.service.record_delivery(ctx.bundle,ctx.result,ctx.target[0])
    assert ctx.service.commit(ctx.session,old)['error_code']=='SEND_CONFIRMATION_REQUIRED';assert not ctx.keys


def test_unknown_image_is_not_sendable(ctx):
    b=copy.deepcopy(ctx.bundle);b['assets']=[{'asset_id':'photo'}]
    result=copy.deepcopy(ctx.result);result['steps'].insert(0,{'kind':'image','asset_id':'photo','state':'unknown'})
    ctx.service.record_delivery(b,result,ctx.target[0])
    assert not ctx.service.status(ctx.session)['available']


@pytest.mark.parametrize('kind',['code','terminal','unknown','password','readonly'])
def test_unsafe_target_never_gets_send_capability(ctx,kind):
    target=ctx.target[0]._replace(kind=kind)
    ctx.service.record_delivery(ctx.bundle,ctx.result,target)
    assert not ctx.service.status(ctx.session)['available']


@pytest.mark.parametrize('mode,expected',[('enter',[(13,0),(13,2)]),('ctrl_enter',[(17,0),(13,0),(13,2),(17,2)])])
def test_native_submit_emits_only_configured_whitelist(mode,expected):
    calls=[]
    def send(n,events,_):calls.extend((events[i].data.ki.wVk,events[i].data.ki.dwFlags)for i in range(n));return n
    assert inject_submit(mode,send)==len(expected);assert calls==expected


def test_submit_partial_only_releases_never_repeats_enter():
    calls=[]
    def send(n,events,_):calls.append([(events[i].data.ki.wVk,events[i].data.ki.dwFlags)for i in range(n)]);return 1
    with pytest.raises(InputInjectionError):inject_submit('enter',send)
    assert calls==[[(13,0),(13,2)],[(13,2)]]


def test_real_http_enforces_pairing_confirmation_and_replay(ctx):
    from doubao_typeless.services.bridge_v3 import V3Bridge
    from doubao_typeless.storage.asset_store import AssetStore
    async def run():
        bridge=V3Bridge(port=0,auth=ctx.auth,store=AssetStore(ctx.path/'assets'),draft=ctx.draft,
           phone_send=ctx.service,on_send=ctx.service.commit)
        runner=web.AppRunner(bridge.make_app());await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
        base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);h={'X-DT-Session':ctx.session.session_id,'X-DT-Token':ctx.session.token,'Origin':base}
        try:
            async with ClientSession() as client:
                assert (await client.post(base+'/v3/send/prepare',headers={'Origin':base})).status==401
                prepared=await(await client.post(base+'/v3/send/prepare',headers=h)).json()
                body={'ticket':prepared['ticket'],'delivery_id':prepared['delivery_id'],'confirmed':True}
                assert (await client.post(base+'/v3/send/commit',headers=h,json={**body,'keys':['ENTER']})).status==400
                assert not ctx.keys
                assert (await(await client.post(base+'/v3/send/commit',headers=h,json=body)).json())['sent']
                assert (await(await client.post(base+'/v3/send/commit',headers=h,json=body)).json())['duplicate']
                assert ctx.keys==['enter']
        finally:await runner.cleanup()
    asyncio.run(run())


def test_target_changed_while_journal_writes_never_emits(ctx,monkeypatch):
    import doubao_typeless.services.phone_send as module
    original=module.write_json_atomic
    def save(path,value):
        original(path,value)
        ctx.target[0]=ctx.target[0]._replace(runtime_id=(99,))
    monkeypatch.setattr(module,'write_json_atomic',save)
    body=ticket(ctx)
    assert ctx.service.commit(ctx.session,body)['error_code']=='SEND_PRECONDITION_CHANGED'
    assert not ctx.keys
    ctx.target[0]=ctx.target[0]._replace(runtime_id=(40,50))
    assert ctx.service.commit(ctx.session,body)['duplicate'] and not ctx.keys
