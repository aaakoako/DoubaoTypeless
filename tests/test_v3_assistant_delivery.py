"""用户流程级服务回归：真实草稿/队列/存储/WS，平台接口是显式替身。

不作为 Windows EXE、真机输入法或实际第三方 Composer 的通过证据。
"""
from __future__ import annotations
import asyncio
import copy
import io
import json
import shutil
import threading
from pathlib import Path
import pytest
from PIL import Image
from doubao_typeless.app import V3App
from doubao_typeless.core.bundle import freeze_bundle
from doubao_typeless.services.command_queue import CommandQueue
from doubao_typeless.storage.draft_snapshot import load_draft


@pytest.fixture
def app(tmp_path):
    a = V3App(data_dir=tmp_path/'isolated', port=0)
    yield a
    a._commands.close(3)
    a.db.conn.close()
    a._lock.release()


def platform(a, *, paste=None):
    a._read_focus = lambda: ('DT-S2-PasteTarget', 'chatinput', 11)
    a.delivery._read_focus = a._read_focus
    a._saved_target = a._read_focus()
    a.delivery._wait_modifiers = lambda: True
    a.delivery._is_locked = lambda: False
    a.delivery._is_elevated = lambda: False
    a.delivery._read_clipboard_text = None
    a.delivery._prepare_image = lambda: None
    a.delivery._observe_text = lambda: 'unknown'
    a.delivery._observe_image = lambda: 'observed'
    written=[]
    a.delivery._set_text = lambda text: written.append(text)
    a._set_text = lambda text: None
    a.delivery._set_image = lambda data: None
    a.delivery._paste = paste or (lambda: None)
    return written


def prepare(a, text='A'):
    a.update_pc_text(text)
    return freeze_bundle(a.draft, bundle_id='bundle-case')


def test_queue_rejects_overlap_without_delayed_replay():
    started, release = threading.Event(), threading.Event()
    q = CommandQueue()
    calls=[]
    def work():
        calls.append('first'); started.set(); assert release.wait(2)
        return 123
    first=q.submit(work)
    assert started.wait(2)
    second=q.submit(lambda:calls.append('second'))
    assert second.result()['error_code']=='BUSY'
    assert q.close(0) is False
    assert q.submit(lambda:None).result()['error_code']=='SHUTTING_DOWN'
    release.set()
    assert first.result(2)==123
    assert q.close(2)
    assert calls==['first']


def test_queue_exception_does_not_disable_next_command():
    seen=[]
    q=CommandQueue(on_error=lambda exc:seen.append(type(exc).__name__))
    try:
        assert q.submit(lambda:1/0).result(2)['result']=='UNKNOWN'
        assert q.submit(lambda:'next').result(2)=='next'
        assert seen==['ZeroDivisionError']
    finally:q.close()


def test_missing_file_releases_busy_and_can_insert_next(app):
    platform(app)
    bundle=prepare(app)
    bundle['assets']=[{'asset_id':'missing-image'}]
    result=app.deliver_and_finish({'intent_id':'missing'},bundle)
    assert result['error_code']=='ASSET_MISSING'
    assert app.ledger.busy is False
    assert app.draft.text=='A'
    assert app.history.last_bundle()['bundle_id']=='bundle-case'
    assert app.insert_current()['result']=='UNKNOWN'
    assert app.draft.text==''


def test_platform_error_retains_draft_and_evidence(app):
    def fail():raise OSError('simulated clipboard write race')
    platform(app,paste=fail)
    prepare(app)
    result=app.request_insert().result(3)
    assert result['result']=='UNKNOWN'
    assert result['error_code']=='DELIVERY_FAILED'
    assert len(result['steps'])==1 # 发键可能部分发生，不能伪报零步骤。
    assert app.ledger.busy is False
    assert app.draft.text=='A'
    app.delivery._paste=lambda:None
    assert app.request_insert().result(3)['result']=='UNKNOWN'
    assert app.draft.text==''


def test_recovery_snapshot_exists_before_first_platform_action(app):
    platform(app)
    prepare(app,'先存副本再操作')
    def paste():
        saved=app.db.last_bundle()
        assert saved['source_text']=='先存副本再操作'
        assert saved['source_snapshot']['epoch']==app.draft.epoch
    app.delivery._paste=paste
    result=app.insert_current()
    assert result['result']=='UNKNOWN'


def test_no_paste_when_recovery_storage_fails(app,monkeypatch):
    calls=[]
    platform(app,paste=lambda:calls.append('paste'))
    prepare(app)
    def fail(*a,**kw):raise OSError('storage unavailable')
    monkeypatch.setattr(app.history,'record',fail)
    result=app.insert_current()
    assert result['result']=='UNKNOWN' and result['steps']==[]
    assert calls==[] and app.draft.text=='A' and not app.ledger.busy


def test_new_text_during_delivery_is_not_rotated(app):
    started,release=threading.Event(),threading.Event()
    def paste(): started.set(); assert release.wait(3)
    platform(app,paste=paste)
    prepare(app,'旧稿A')
    future=app.request_insert()
    assert started.wait(3)
    app.update_pc_text('新稿B')
    release.set()
    result=future.result(3)
    assert result['phone_event']['rotated'] is False
    assert app.draft.text=='新稿B'
    assert app.history.last_bundle()['text']=='旧稿A'


def test_duplicate_intent_does_not_overwrite_clipboard(app):
    calls=[]
    platform(app,paste=lambda:calls.append('paste'))
    bundle=prepare(app)
    app.deliver_and_finish({'intent_id':'one'},bundle)
    app._set_text=lambda text:calls.append('unwanted-copy')
    result=app.deliver_and_finish({'intent_id':'one'},bundle)
    assert result['duplicate']
    assert calls==['paste']


def png():
    output=io.BytesIO(); Image.new('RGB',(70,70),(40,180,20)).save(output,'PNG'); return output.getvalue()


def test_capture_resource_does_not_mutate_active_draft(app):
    session=app.auth.complete_pairing(app.auth.new_pairing_challenge())
    app.auth.set_grants(session.session_id,allow_capture=True)
    app.capture._grab=lambda scope:png()
    before=copy.deepcopy(app.draft.__dict__)
    meta=app._on_capture('primary','source-request',session)
    assert meta['role']=='source' and meta['status']=='editing'
    assert app.draft.__dict__==before
    assert app.store.get(meta['asset_id'])==png()


def test_unfinished_mobile_document_reaches_desktop_and_blocks(app):
    result=app.apply_phone_update({'draft_id':app.draft.draft_id,'epoch':app.draft.epoch,
        'revision':1,'text':'正在画图','asset_refs':[],
        'asset_documents':[{'id':'local-a','asset_id':'','status':'editing','render_revision':1}]})
    assert result['durable']
    assert app.request_insert().result()['error_code']=='IMAGE_EDITING'
    restored,missing=load_draft(app.data_dir,app.store)
    assert restored.assets[0]['status']=='failed' # 未上传像素不能在重启后假装存在。


def test_existing_lock_can_be_passed_to_real_app(tmp_path):
    from doubao_typeless.runtime_lock import InstanceLock
    path=tmp_path/'isolated'
    lock=InstanceLock(path/'instance.lock'); assert lock.acquire()
    a=V3App(data_dir=path,port=0,instance_lock=lock)
    try: assert a._lock is lock
    finally:
        a.db.conn.close(); lock.release()


@pytest.mark.skipif(shutil.which('node') is None, reason='Node runtime required')
def test_phone_protocol_to_real_service_three_rounds(app):
    async def run():
        written=platform(app)
        session=app.auth.complete_pairing(app.auth.new_pairing_challenge())
        app.auth.set_grants(session.session_id,allow_insert=True)
        app._loop=asyncio.get_running_loop()
        await app.bridge.start()
        base=f'http://127.0.0.1:{app.bridge.port}'
        conf={'base':base,'session':{'session_id':session.session_id,'token':session.token},
              'headers':{'X-DT-Session':session.session_id,'X-DT-Token':session.token}}
        child=await asyncio.create_subprocess_exec('node',str(Path(__file__).parent/'fixtures/phone_service_driver.mjs'),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            out,err=await asyncio.wait_for(child.communicate(json.dumps(conf).encode()),15)
            assert child.returncode==0,err.decode()
            assert json.loads(out)['rounds']==3
            assert len(written)==3 and written[0]=='第一段：原文  不改空格\n'
            assert app.draft.text=='有图的下一段'
            assert app.draft.assets[0]['status']=='editing'
            assert app.draft.assets[0]['local_id']=='local-new'
        finally:
            await app.bridge.stop()
            app._loop=None
    asyncio.run(run())


@pytest.mark.skipif(shutil.which('node') is None, reason='Node runtime required')
def test_source_receipt_regressions():
    import subprocess
    script=Path(__file__).with_name('test_v3_assistant_receipts.mjs')
    result=subprocess.run(['node',str(script)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['passed']==12


def test_history_full_metadata_and_delete_survive_restart(app):
    from doubao_typeless.services.history import HistoryService
    bundle=prepare(app,'历史有原稿')
    bundle['assets']=[{'asset_id':'a','local_id':'L','render_revision':4,'caption':'说明','status':'ready','role':'markup'}]
    app.history.record(bundle,attempt_result='UNKNOWN')
    restored=HistoryService(app.data_dir/'history.json',db=app.db)
    assert restored.last_bundle()['source_snapshot']==bundle['source_snapshot']
    assert restored.last_bundle()['assets'][0]['render_revision']==4
    restored.delete(bundle['bundle_id'])
    assert HistoryService(app.data_dir/'history.json',db=app.db).last_bundle() is None
    assert not (app.data_dir/'history.json').exists()


def test_complete_candidate_manifest_detects_dll_change(tmp_path):
    from tools.manifest_candidate import make_manifest
    root=tmp_path/'candidate';root.mkdir()
    (root/'app.exe').write_bytes(b'fixture exe')
    (root/'runtime.dll').write_bytes(b'A')
    first=make_manifest(root,'a'*40,tmp_path/'files.json')
    (root/'runtime.dll').write_bytes(b'B')
    second=make_manifest(root,'a'*40,tmp_path/'files2.json')
    assert first['files'][0]['sha256']==second['files'][0]['sha256']
    assert first['files'][1]['sha256']!=second['files'][1]['sha256']
    assert second['release_ready'] is False


def test_custom_hotkey_releases_its_actual_keys(monkeypatch):
    import sys,types
    instances=[]
    class Global:
        def __init__(self,mapping):self.mapping=mapping;instances.append(self)
        def start(self):pass
        def canonical(self,key):return key.lower()
    class Listener:
        def __init__(self,on_release):self.on_release=on_release
        def start(self):pass
    module=types.ModuleType('pynput.keyboard')
    module.GlobalHotKeys=Global;module.Listener=Listener
    module.HotKey=types.SimpleNamespace(parse=lambda combo:combo.lower().split('+'))
    monkeypatch.setitem(sys.modules,'pynput.keyboard',module)
    from doubao_typeless.platform.windows.hotkeys import start_hotkeys
    calls=[]
    out=start_hotkeys(on_insert=lambda:calls.append('insert'),on_recall=lambda:None,insert_combo='<ctrl>+q')
    invoke=instances[0].mapping['<ctrl>+q']
    invoke();invoke();assert calls==['insert']
    out['release'].on_release('Q')
    invoke();assert calls==['insert','insert']
