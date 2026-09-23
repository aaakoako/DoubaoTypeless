"""Run test-namespace NSIS install, upgrade, frozen startup and uninstall.

The older installer is a layout fixture, not a claim of legacy 0.4.2 migration.
Never touches the production uninstall, shortcut or startup registry entries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import winreg
import sys
from smoke_v3_candidate import run as smoke

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
TEST_KEY=r'Software\DoubaoTypelessInstallerTest'

def verify(directory, payload, compiler, report):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,TEST_KEY):
            raise RuntimeError('Existing installer test registration; refusing to overwrite')
    except FileNotFoundError: pass
    installers=list(directory.glob('*-installer-test_Setup.exe'))
    if len(installers)!=1:raise ValueError('Expected exactly one test installer')
    report.parent.mkdir(parents=True,exist_ok=True)
    result={'passed':False,'real_codex_cursor_tested':False,'legacy_migration_tested':False}
    with tempfile.TemporaryDirectory(prefix='installer-',dir=report.parent.resolve()) as temp:
        root=Path(temp).resolve(); install=root/'application'; data=root/'user-data';data.mkdir()
        from doubao_typeless.core.bundle import Draft
        from doubao_typeless.storage.draft_snapshot import save_draft, load_draft
        from doubao_typeless.storage.asset_store import AssetStore
        from PIL import Image
        import io
        pixels=io.BytesIO();Image.new('RGB',(24,24),(20,50,120)).save(pixels,format='PNG')
        store=AssetStore(data/'assets')
        asset=store.put_png(pixels.getvalue(),width=24,height=24,role='photo')
        save_draft(data,Draft('upgrade-draft','upgrade-epoch',2,'pc','升级后还在',[asset]))
        settings={name:'<smoke-disabled>' for name in ('hotkey_insert','hotkey_recall','hotkey_expand','hotkey_capture')}
        settings['byok_model']='upgrade-kept-model'
        (data/'settings.json').write_text(json.dumps(settings),encoding='utf-8')
        before={str(p.relative_to(data)):hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob('*') if p.is_file()}
        # This fixture exercises ordinary setup, not the renamed legacy updater
        # entry; the latter now intentionally triggers automatic launch.
        previous=root/'previous-test_Setup.exe'
        subprocess.run([str(compiler.resolve()),'/INPUTCHARSET','UTF8','/DVERSION=0.4.9',
            f'/DPAYLOAD={payload.resolve()}',f'/DOUTPUT={previous}','/DTEST_INSTALL',
            str(ROOT/'packaging/windows-installer.nsi')],check=True,stdout=subprocess.DEVNULL)
        def execute(exe,*args):
            subprocess.run([str(exe),*args],check=True,timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            execute(previous,'/S',f'/D={install}')
            assert (install/'versions/0.4.9/DoubaoTypeless.exe').is_file()
            execute(installers[0].resolve(),'/S',f'/D={install}')
            info=json.loads((payload/'_internal/build-info.json').read_text())
            exe=install/'versions'/(info['version']+'-'+info['source_sha'][:8])/'DoubaoTypeless.exe'
            assert exe.is_file() and (install/'versions/0.4.9/DoubaoTypeless.exe').is_file()
            result['previous_program_retained']=True
            result['installed_runtime']=smoke(exe,data,existing_data=True)
            assert result['installed_runtime']['passed']
            restored,missing=load_draft(data,store)
            assert restored.text=='升级后还在' and not missing and restored.assets[0]['asset_id']==asset['asset_id']
            assert json.loads((data/'settings.json').read_text())['byok_model']=='upgrade-kept-model'
            # Installing elsewhere must not allow the old uninstaller to remove
            # the current install registration or its program files.
            newer=root/'relocated-application'
            execute(installers[0].resolve(),'/S',f'/D={newer}')
            execute(install/'Uninstall.exe','/S',f'_?={install}')
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,TEST_KEY) as key:
                assert winreg.QueryValueEx(key,'InstallDir')[0]==str(newer)
            newer_exe=newer/'versions'/(info['version']+'-'+info['source_sha'][:8])/'DoubaoTypeless.exe'
            assert newer_exe.is_file()
            with newer_exe.open('rb'):
                locked=subprocess.run([str(newer/'Uninstall.exe'),'/S',f'_?={newer}'],timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
                assert locked.returncode==2
                assert (newer/'.typeless-install').exists() and (newer/'Uninstall.exe').exists()
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,TEST_KEY):pass
            execute(newer/'Uninstall.exe','/S',f'_?={newer}')
            assert not (newer/'versions').exists()
            result.update(relocated_install_protected=True,locked_uninstall_retry=True)
            deadline=time.monotonic()+15
            while (install/'versions').exists() and time.monotonic()<deadline:time.sleep(.1)
            assert not (install/'versions').exists()
            assert {name:hashlib.sha256((data/name).read_bytes()).hexdigest() for name in before}==before
            backup=list((data/'upgrade-backups').glob('*/backup-complete.json'))
            assert len(backup)==1
            assert (backup[0].parent/'draft.json').read_bytes()==(data/'draft.json').read_bytes()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software') as key:
                try:winreg.OpenKey(key,'DoubaoTypelessInstallerTest')
                except FileNotFoundError:pass
                else:raise AssertionError('Uninstall left its registration')
            result.update(passed=True,install=True,upgrade=True,uninstall=True,user_data_unchanged=True)
        finally:
            for owned in (install,root/'relocated-application'):
                if (owned/'Uninstall.exe').exists() and (owned/'versions').exists():
                    execute(owned/'Uninstall.exe','/S',f'_?={owned}')
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path)
    p.add_argument('--payload',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();print(verify(a.directory,a.payload,a.compiler,a.report))
