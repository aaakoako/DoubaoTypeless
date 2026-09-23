"""Native installer rollback with tiny explicit readiness fixtures, not a real-app claim."""
import argparse,json,os,subprocess,tempfile,time,winreg
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
KEY=r'Software\DoubaoTypelessInstallerTest'

def verify(compiler,report):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY):raise RuntimeError('Existing test registration')
    except FileNotFoundError:pass
    report.parent.mkdir(parents=True,exist_ok=True)
    result={'passed':False,'target':'native installer with readiness fixtures'}
    with tempfile.TemporaryDirectory(prefix='upgrade-fail-',dir=report.parent.resolve()) as temp:
        root=Path(temp);payload=root/'payload';payload.mkdir();install=root/'installation';marker=root/'starts.log'
        fixture=root/'fixture.nsi'
        fixture.write_text('''Unicode True
Name "Upgrade fixture"
OutFile "'''+str(payload/'DoubaoTypeless.exe')+'''"
SilentInstall silent
RequestExecutionLevel user
Section
ReadEnvStr $0 DT_TEST_LAUNCH_MARKER
FileOpen $1 $0 a
FileSeek $1 0 END
FileWrite $1 "started$\\r$\\n"
FileClose $1
ReadEnvStr $0 DT_UPDATE_READY_FILE
StrCmp $0 "" done
FileOpen $1 $0 w
FileWrite $1 "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FileClose $1
done:
Sleep 1000
SectionEnd
''',encoding='utf-8')
        def compile_script(script,*defines):
            subprocess.run([str(compiler),'/V2','/INPUTCHARSET','UTF8',*defines,str(script)],check=True,timeout=90)
        compile_script(fixture)
        def installer(name,source):
            output=root/(name+'_Setup.exe')
            compile_script(ROOT/'packaging/windows-installer.nsi','/DVERSION=0.5.1',f'/DBUILD_ID={name}',
                '/DTEST_INSTALL',f'/DSOURCE_SHA={source}',f'/DPAYLOAD={payload}',f'/DOUTPUT={output}')
            return output
        good=installer('good','a'*40);bad=installer('bad','b'*40)
        env={**os.environ,'DT_UPGRADE_TEST_ROOT':str(install),'DT_TEST_LAUNCH_MARKER':str(marker)}
        def run(exe,*args):return subprocess.run([str(exe),*args],env=env,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW).returncode
        try:
            assert run(good,'/UPDATE')==0
            previous=str(install/'versions/good/DoubaoTypeless.exe')
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY) as key:
                assert winreg.QueryValueEx(key,'CurrentExecutable')[0]==previous
            time.sleep(1.2);baseline=marker.read_text().count('started')
            assert run(bad,'/UPDATE','/WAITPID=0')==2
            time.sleep(1.2)
            assert marker.read_text().count('started')==baseline+2,'new failed then previous restarted'
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY) as key:
                assert winreg.QueryValueEx(key,'CurrentExecutable')[0]==previous
            result['startup_failure_restores_previous']=True
            # A filesystem collision prevents extraction before the new app starts.
            blocked=installer('blocked','b'*40)
            (install/'versions/blocked').write_text('owned collision fixture')
            baseline=marker.read_text().count('started')
            assert run(blocked,'/UPDATE','/WAITPID=0')==2
            time.sleep(1.2)
            assert marker.read_text().count('started')==baseline+1
            result['extraction_failure_reopens_previous']=True
            # Native entry forwarding should not overwrite a working runtime.
            forward=root/'DoubaoTypeless.exe';forward.write_bytes(good.read_bytes())
            stamp=Path(previous).stat().st_mtime_ns
            assert run(forward)==0 and Path(previous).stat().st_mtime_ns==stamp
            result['repeat_entry_does_not_reinstall']=True
            portable=root/'portable';portable.mkdir()
            entry=portable/'DoubaoTypeless.exe';entry.write_bytes((payload/'DoubaoTypeless.exe').read_bytes())
            original=entry.read_bytes();(portable/'config.json').write_text('untouched legacy data')
            redirect_env={**env,'DT_UPGRADE_ROOT':str(install),'DT_UPGRADE_PREVIOUS':str(entry),
                          'DT_UPGRADE_PACKAGE':str(good),'DT_UPGRADE_HANDOFF':str(root/'fixture.ready')}
            def retarget():
                return subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                    '-File',str(ROOT/'packaging/upgrade-launch.ps1'),'-Phase','Retarget'],env=redirect_env,
                    creationflags=subprocess.CREATE_NO_WINDOW,timeout=20).returncode
            with entry.open('rb'):
                assert retarget()==2 and entry.read_bytes()==original
            assert retarget()==0 and entry.read_bytes()==good.read_bytes()
            backups=list(portable.glob('*.before-upgrade-*'))
            assert len(backups)==1 and backups[0].read_bytes()==original
            assert (portable/'config.json').read_text()=='untouched legacy data'
            assert run(entry)==0
            result['portable_entry_atomic_replace_and_backup']=True
            result['passed']=True
        finally:
            if (install/'upgrade.log').exists():
                result['log']=(install/'upgrade.log').read_text(encoding='utf-8-sig')
            if marker.exists():result['fixture_starts']=marker.read_text().count('started')
            time.sleep(1.2)
            if (install/'Uninstall.exe').exists():run(install/'Uninstall.exe','/S','_?='+str(install))
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--compiler',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();verify(a.compiler.resolve(),a.report.resolve())
