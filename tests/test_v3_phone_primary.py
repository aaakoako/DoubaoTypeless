"""正式手机主稿服务回归；平台按键是显式替身，不冒充真机。"""
from __future__ import annotations
import asyncio
import copy
import io
import json
from pathlib import Path
import subprocess
import threading
import pytest
from PIL import Image
from aiohttp import ClientSession, web
from doubao_typeless.app import V3App
from doubao_typeless.core.bundle import Draft, freeze_bundle, source_snapshot
from doubao_typeless.services.phone_primary import apply_phone_snapshot
from doubao_typeless.storage.draft_snapshot import save_draft, load_draft
from doubao_typeless.storage.asset_store import AssetStore

@pytest.fixture
def app(tmp_path):
    a=V3App(data_dir=tmp_path/'isolated',port=0)
    yield a
    a._commands.close(3);a.db.conn.close();a._lock.release()


def msg(text='手机稿',rev=1,**kw):
    return {'authority':'phone','draft_id':'phone-d','epoch':'phone-e','generation':0,
        'revision':rev,'text':text,'asset_refs':[],'asset_documents':[],
        'update_id':f'u{rev}','_source':'remote','_device_id':'device-a',**kw}


def test_phone_claim_and_reconnect_never_adopt_pc_ids(app):
    app.draft.text='old desktop'
    ack=app.apply_phone_update(msg())
    assert ack['durable'] and app.draft.draft_id=='phone-d'
    assert list((app.data_dir/'recovery').glob('*.json'))
    app.apply_phone_update(msg('离线继续修改',9))
    assert app.draft.text=='离线继续修改' and app.draft.revision==9
    with pytest.raises(ValueError,match='STALE_PHONE_REVISION'):app.apply_phone_update(msg('旧消息',2))
    assert app.draft.text=='离线继续修改'


def test_lost_ack_replay_is_durable_but_does_not_wake_hud(app):
    calls=[]
    app.hud.show_receiving=lambda *args,**kw:calls.append(args)
    first=app.apply_phone_update(msg());second=app.apply_phone_update(msg())
    assert first['changed'] and not second['changed'] and second['durable']
    assert first['update_id']==second['update_id'] and len(calls)==1


def test_failed_save_does_not_advance_mirror(tmp_path):
    draft=Draft('d','e',0,'pc','old');before=copy.deepcopy(draft)
    def fail(_):raise OSError('disk')
    with pytest.raises(OSError):apply_phone_snapshot(draft,msg(),AssetStore(tmp_path),fail,lambda _:None)
    assert draft==before


def test_other_phone_cannot_override_owner(app):
    app.apply_phone_update(msg())
    with pytest.raises(ValueError,match='OTHER_PHONE_OWNER'):
        app.apply_phone_update(msg('other',2,_device_id='device-b'))
    assert app.draft.text=='手机稿'


def test_phone_generation_rejects_previous_draft(app):
    app.apply_phone_update(msg())
    app.apply_phone_update(msg('',0,epoch='new-e',generation=1))
    with pytest.raises(ValueError,match='STALE_PHONE_GENERATION'):app.apply_phone_update(msg('delayed',99))
    assert app.draft.text=='' and app.draft.epoch=='new-e'


def test_primary_identity_and_version_survive_restart(app):
    app.apply_phone_update(msg('persistent',12))
    restored,missing=load_draft(app.data_dir,app.store)
    assert not missing and restored.authority=='phone' and restored.generation==0
    assert source_snapshot(restored)==source_snapshot(app.draft)


def test_same_revision_different_material_rejected(app):
    first=msg(asset_documents=[{'id':'x','status':'editing','render_revision':1}])
    app.apply_phone_update(first)
    other=copy.deepcopy(first);other['asset_documents'][0]['render_revision']=2
    with pytest.raises(ValueError,match='PHONE_REVISION_CONFLICT'):app.apply_phone_update(other)
    assert app.draft.assets[0]['render_revision']==1


def test_image_only_update_wakes_and_passes_version_to_hud(app):
    calls=[];app.hud.show_receiving=lambda *args,**kw:calls.append(kw)
    raw=io.BytesIO();Image.new('RGB',(20,20),(30,120,80)).save(raw,format='PNG')
    meta=app.store.put_png(raw.getvalue(),width=20,height=20,role='markup')
    a=msg('',1,asset_refs=[meta['asset_id']],asset_documents=[{'id':'photo','asset_id':meta['asset_id'],'status':'ready','render_revision':1}])
    app.apply_phone_update(a)
    a['revision']=2;a['update_id']='second';a['asset_documents'][0]['render_revision']=2
    app.apply_phone_update(a)
    assert len(calls)==2 and calls[-1]['assets'][0]['render_revision']==2
    assert Path(calls[-1]['assets'][0]['path']).read_bytes()==raw.getvalue()


def test_pc_edits_are_saved_separately_and_phone_keeps_authority(app):
    app.apply_phone_update(msg())
    base=source_snapshot(app.draft);app.review_editing=True;app.update_pc_text('电脑修正')
    assert source_snapshot(app.draft)==base and app.review_text()=='电脑修正'
    assert (app.data_dir/'desktop-edit.json').is_file()
    app.apply_phone_update(msg('手机继续输入',2))
    assert app.draft.text=='手机继续输入' and app.review_text()=='电脑修正'
    assert app.phone_pending is not None
    app.accept_phone_pending()
    assert app.review_text()=='手机继续输入'


def test_offline_hotkey_never_falls_back_to_mirrored_text(app):
    app.apply_phone_update(msg())
    app._read_focus=lambda:('Edit','Notes',22)
    pasted=[];app.delivery._paste=lambda:pasted.append(True)
    result=app.request_insert().result(2)
    assert result['result']=='NO_STEPS' and result['error_code']=='PHONE_OFFLINE'
    assert pasted==[] and app.draft.text=='手机稿'


def test_completion_in_primary_mode_does_not_name_next_phone_draft(app):
    app.apply_phone_update(msg());bundle=freeze_bundle(app.draft,bundle_id='b');before=source_snapshot(app.draft)
    result=app._after_insert(bundle,{'result':'CONFIRMED','steps':[]})
    assert result['phone_event']['phone_primary'] and result['phone_event']['rotated']
    assert source_snapshot(app.draft)==before  # 仅手机自行保全、清稿并创建下一epoch。


def test_legacy_local_insert_remains_available(app):
    from tests.test_v3_assistant_delivery import platform
    out=platform(app);app.update_pc_text('旧版的复制/插入功能')
    assert app.request_insert().result(2)['result']=='UNKNOWN'
    assert out==['旧版的复制/插入功能'] and app.draft.text==''


def test_real_service_primary_protocol_duplicate_and_prepare(app):
    async def run():
        runner=web.AppRunner(app.bridge.make_app());await runner.setup()
        site=web.TCPSite(runner,'127.0.0.1',0);await site.start();port=site._server.sockets[0].getsockname()[1]
        session=app.auth.complete_pairing(app.auth.new_pairing_challenge(),allow_insert=False,allow_capture=False)
        try:
            async with ClientSession() as http:
                async with http.ws_connect(f'http://127.0.0.1:{port}/ws') as ws:
                    await ws.send_json({'type':'session.hello','session_id':session.session_id,'token':session.token})
                    ready=await ws.receive_json();assert 'phone-primary-v1' in ready['capabilities']
                    data=msg();data.pop('_source');data.pop('_device_id');data['type']='draft.update'
                    await ws.send_json(data);ack=await ws.receive_json();assert ack['durable']
                    assert app.draft.editor_device_id==session.device_id
                    await ws.send_json(data);again=await ws.receive_json();assert again['durable'] and not again['changed']
                    task=asyncio.create_task(app.bridge.prepare_phone(session.device_id))
                    prepare=await ws.receive_json();assert prepare['type']=='draft.prepare'
                    await ws.send_json({**data,'type':'draft.prepared','request_id':prepare['request_id']})
                    assert (await task)['revision']==1
                    assert not app.history.items  # 只确认当前稿，无投递副作用。
        finally:await runner.cleanup()
    asyncio.run(run())


def test_source_bytes_completed_as_render_are_not_reused_as_source(app):
    import hashlib
    raw=io.BytesIO();Image.new('RGB',(16,16),(10,40,70)).save(raw,format='PNG');data=raw.getvalue()
    source=app.store.put_png(data,width=16,height=16,role='screenshot')
    app.db.upsert_asset(source['asset_id'],source['sha256'],len(data),owner_session_id='device:device-a')
    ticket=app.uploads.init(mime='image/png',total_bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
        width=16,height=16,owner_session_id='device:device-a',role='markup')
    app.uploads.put_chunk(ticket['upload_id'],0,data,owner_session_id='device:device-a')
    rendered=app.uploads.complete(ticket['upload_id'],owner_session_id='device:device-a')
    assert rendered['asset_id']!=source['asset_id']
    assert app.store.meta(rendered['asset_id'])['role']=='markup'


def test_primary_ai_changes_only_explicit_pc_edit(app):
    app.apply_phone_update(msg('手机 Opus'))
    app.review_editing=True;app.update_pc_text('电脑 Opus')
    app._last_suggestion={'draft_id':app.draft.draft_id,'epoch':app.draft.epoch,'revision':app.draft.revision,
                          'original':'电脑 Opus','suggested':'电脑修正 Opus'}
    assert app.apply_suggestion()
    assert app.review_text()=='电脑修正 Opus' and app.draft.text=='手机 Opus'
    app.reject_suggestion()
    assert app.review_text()=='电脑 Opus' and app.draft.text=='手机 Opus'


def test_primary_image_hud_updates_pixels_and_blocks_unfinished(app):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from doubao_typeless.ui.hud import HudController
    qt=QApplication.instance() or QApplication([])
    h=HudController();h.start()
    try:
        raw=io.BytesIO();Image.new('RGB',(20,20),(220,30,40)).save(raw,format='PNG')
        meta=app.store.put_png(raw.getvalue(),width=20,height=20,role='markup')
        path=str(app.store.root/(meta['asset_id']+'.bin'))
        h.show_receiving('',1,assets=[{'id':'x','status':'editing','render_revision':1}],revision=1,phone_primary=True)
        qt.processEvents();assert h._widget.isVisible() and not h._insert.isEnabled()
        h.hide();qt.processEvents();assert not h._widget.isVisible()
        h.show_receiving('',1,assets=[{'id':'x','status':'ready','render_revision':2,'path':path}],revision=2,phone_primary=True)
        qt.processEvents();assert h._widget.isVisible() and h._insert.isEnabled()
        thumb=h._thumb_row.itemAt(0).widget()
        assert not thumb.pixmap().isNull()
        assert thumb.pixmap().toImage().pixelColor(1,1).red()==220
        assert '已更新' in h._status.text() and h._widget.height()<=300
    finally:h.hide();h._widget.deleteLater();qt.processEvents()


def test_primary_outbox_runs_actual_js():
    root=Path(__file__).resolve().parents[1]
    completed=subprocess.run(['node','tests/test_v3_primary_outbox.mjs'],cwd=root,capture_output=True,text=True,timeout=15)
    assert completed.returncode==0,completed.stdout+completed.stderr


def test_explicit_takeover_requires_exact_mirror_and_preserves_previous(app):
    app.apply_phone_update(msg('前一台'))
    before=source_snapshot(app.draft)
    request=msg('当前手机',generation=1,epoch='new-epoch',_device_id='other',
        takeover={'draft_id':app.draft.draft_id,'epoch':app.draft.epoch,'revision':app.draft.revision,'owner_device_id':app.draft.editor_device_id})
    bad=copy.deepcopy(request);bad['takeover']['revision']=100
    with pytest.raises(ValueError,match='OTHER_PHONE_OWNER'):app.apply_phone_update(bad)
    app.apply_phone_update(request)
    assert app.draft.text=='当前手机' and app.draft.editor_device_id=='other'
    assert any(json.loads(p.read_text())['text']=='前一台' for p in (app.data_dir/'recovery').glob('*.json'))


def test_same_owner_explicit_new_generation_recovers_without_automatic_rebase(app):
    app.apply_phone_update(msg('电脑镜像'))
    request=msg('明确选择的手机稿',epoch='chosen',generation=1,revision=1,
        takeover={'draft_id':app.draft.draft_id,'epoch':app.draft.epoch,'revision':app.draft.revision,'owner_device_id':app.draft.editor_device_id})
    app.apply_phone_update(request)
    assert app.draft.text=='明确选择的手机稿' and app.draft.epoch=='chosen'
