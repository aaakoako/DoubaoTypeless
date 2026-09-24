import hashlib
from pathlib import Path
import pytest
import httpx
from doubao_typeless.services.v3_update import release_package, download_upgrade, acknowledge_update_launch

BASE='https://github.com/aaakoako/Pocket-Composer/releases/download/v0.5.2/'
EXE=b'MZ'+b'full native package fixture'*10

def release(digest=True):
    assets=[{'name':'DoubaoTypeless.exe','browser_download_url':BASE+'DoubaoTypeless.exe','size':len(EXE)},
            {'name':'SHA256SUMS.txt','browser_download_url':BASE+'SHA256SUMS.txt'}]
    if digest:assets[0]['digest']='sha256:'+hashlib.sha256(EXE).hexdigest()
    return {'tag_name':'v0.5.2','assets':assets}

@pytest.mark.parametrize('change',[{'draft':True},{'prerelease':True},{'tag_name':'latest'}, {'assets':[]}])
def test_only_explicit_official_complete_release_is_upgradable(change):
    assert release_package({**release(),**change}) is None

def test_untrusted_asset_origin_is_rejected():
    body=release();body['assets'][0]['browser_download_url']='https://elsewhere.invalid/app.exe'
    assert release_package(body) is None

@pytest.mark.parametrize('digest',[True,False])
def test_download_verifies_full_native_package_before_handoff(tmp_path,digest):
    def serve(req):
        if req.url.path.endswith('SHA256SUMS.txt'):
            return httpx.Response(200,text=hashlib.sha256(EXE).hexdigest()+'  DoubaoTypeless.exe\n')
        return httpx.Response(200,content=EXE)
    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        result=download_upgrade(release_package(release(digest)),tmp_path,client=client)
    assert result.read_bytes()==EXE and result.name=='DoubaoTypeless.exe'
    assert not list(tmp_path.rglob('*.part'))

@pytest.mark.parametrize('body',[EXE[:-1],b'MZ'+b'corrupt'*80])
def test_corrupt_download_leaves_no_executable(tmp_path,body):
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=body))) as client:
        with pytest.raises(ValueError):download_upgrade(release_package(release()),tmp_path,client=client)
    assert not list(tmp_path.rglob('*.exe')) and not list(tmp_path.rglob('*.part'))

def test_cancel_keeps_running_version_and_no_partial_package(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=EXE))) as client:
        with pytest.raises(RuntimeError,match='取消'):
            download_upgrade(release_package(release()),tmp_path,client=client,cancelled=lambda:True)
    assert not list(tmp_path.rglob('*.exe'))

def test_startup_receipt_is_one_use_and_does_not_overwrite_other_files(tmp_path,monkeypatch):
    from doubao_typeless import build_info
    monkeypatch.setattr(build_info,'build_info',lambda:{'source_sha':'a'*40})
    note=tmp_path/('.update-ready-'+'b'*32)
    monkeypatch.setenv('DT_UPDATE_READY_FILE',str(note));acknowledge_update_launch()
    assert note.read_text()=='a'*40
    another=tmp_path/'config.json';another.write_text('keep')
    monkeypatch.setenv('DT_UPDATE_READY_FILE',str(another));acknowledge_update_launch()
    assert another.read_text()=='keep'


def test_handoff_does_not_authorize_install_until_ui_accepts(tmp_path,monkeypatch):
    import types
    from doubao_typeless.services import v3_update as update
    package=tmp_path/'DoubaoTypeless.exe';package.write_bytes(EXE)
    captured=[]
    monkeypatch.setattr(update,'sys',types.SimpleNamespace(platform='win32',frozen=True,executable=str(tmp_path/'old.exe')))
    monkeypatch.setattr(update.subprocess,'CREATE_NO_WINDOW',0,raising=False)
    monkeypatch.setattr(update.subprocess,'CREATE_NEW_PROCESS_GROUP',0,raising=False)
    def spawn(*args,**kwargs):
        captured.append(kwargs['env'])
        Path(kwargs['env']['DT_UPGRADE_HANDOFF']).write_text(str(update.os.getpid()))
        return types.SimpleNamespace(poll=lambda:None)
    monkeypatch.setattr(update.subprocess,'Popen',spawn)
    accept=update.start_upgrade(package,tmp_path,pipe='isolated-test')
    assert accept.suffix=='.accept' and not accept.exists()
    assert captured[0]['DT_UPGRADE_PREVIOUS']==str(tmp_path/'old.exe')


def test_handoff_timeout_revokes_this_attempt(tmp_path,monkeypatch):
    import types
    from doubao_typeless.services import v3_update as update
    package=tmp_path/'DoubaoTypeless.exe';package.write_bytes(EXE)
    captured=[];ticks=iter([0,0,16])
    monkeypatch.setattr(update,'sys',types.SimpleNamespace(platform='win32',frozen=True,executable=str(tmp_path/'old.exe')))
    monkeypatch.setattr(update.subprocess,'CREATE_NO_WINDOW',0,raising=False)
    monkeypatch.setattr(update.subprocess,'CREATE_NEW_PROCESS_GROUP',0,raising=False)
    monkeypatch.setattr(update,'time',types.SimpleNamespace(monotonic=lambda:next(ticks),sleep=lambda _:None))
    def spawn(*args,**kwargs):
        captured.append(kwargs['env']);return types.SimpleNamespace(poll=lambda:None)
    monkeypatch.setattr(update.subprocess,'Popen',spawn)
    with pytest.raises(RuntimeError,match='撤销'):update.start_upgrade(package,tmp_path,pipe='isolated-test')
    handoff=Path(captured[0]['DT_UPGRADE_HANDOFF'])
    assert handoff.with_suffix('.cancel').exists() and not handoff.with_suffix('.accept').exists()
