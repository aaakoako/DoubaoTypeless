"""Native installer rollback with tiny explicit readiness fixtures, not a real-app claim."""
import argparse,json,os,subprocess,tempfile,time,winreg,threading,ctypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
KEY=r'Software\DoubaoTypelessInstallerTest'


class ProcessTree:
    """Keep handles, not just PIDs: cleanup cannot kill a subsequently reused PID."""
    def __init__(self, child):
        from ctypes import wintypes as w
        self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        self.k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];self.k.OpenProcess.restype=w.HANDLE
        self.k.CloseHandle.argtypes=[w.HANDLE]
        self.k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
        self.k.TerminateProcess.argtypes=[w.HANDLE,w.UINT]
        self.k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];self.k.CreateToolhelp32Snapshot.restype=w.HANDLE
        class Entry(ctypes.Structure):
            _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',ctypes.c_size_t),
                      ('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),
                      ('flags',w.DWORD),('name',w.WCHAR*260)]
        self.Entry=Entry
        for name in ('Process32FirstW','Process32NextW'):
            fn=getattr(self.k,name);fn.argtypes=[w.HANDLE,ctypes.POINTER(Entry)];fn.restype=w.BOOL
        handle=self.k.OpenProcess(0x1000|0x100000|1,False,child.pid)
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        self.rows={child.pid:{'pid':child.pid,'parent':os.getpid(),'name':Path(child.args[0]).name,'handle':handle}}
        self.stop=threading.Event();self.errors=[]
        self.thread=threading.Thread(target=self.watch,daemon=True);self.thread.start()

    def scan(self):
        snap=self.k.CreateToolhelp32Snapshot(2,0)
        if snap==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        rows=[]
        try:
            entry=self.Entry();entry.size=ctypes.sizeof(entry)
            ok=self.k.Process32FirstW(snap,ctypes.byref(entry))
            while ok:
                rows.append((entry.pid,entry.parent,entry.name));ok=self.k.Process32NextW(snap,ctypes.byref(entry))
            # An exited parent's PID must never authorize a newly unrelated process.
            pending=True
            while pending:
                pending=False
                for pid,parent,name in rows:
                    if pid in self.rows or parent not in self.rows:continue
                    if self.k.WaitForSingleObject(self.rows[parent]['handle'],0)!=258:continue
                    handle=self.k.OpenProcess(0x1000|0x100000|1,False,pid)
                    if handle:
                        self.rows[pid]={'pid':pid,'parent':parent,'name':name,'handle':handle};pending=True
        finally:self.k.CloseHandle(snap)

    def watch(self):
        while not self.stop.is_set():
            try:self.scan()
            except Exception as exc:self.errors.append(type(exc).__name__)
            self.stop.wait(.05)

    def freeze(self):
        self.stop.set();self.thread.join()
        try:self.scan()
        except Exception as exc:self.errors.append(type(exc).__name__)
        return [{**{k:v for k,v in row.items() if k!='handle'},
                 'alive':self.k.WaitForSingleObject(row['handle'],0)==258} for row in self.rows.values()]

    def cleanup(self):
        outcomes=[]
        for row in reversed(list(self.rows.values())):
            if self.k.WaitForSingleObject(row['handle'],0)==258:
                ok=bool(self.k.TerminateProcess(row['handle'],1))
                outcomes.append({'pid':row['pid'],'terminated':ok,'error':0 if ok else ctypes.get_last_error()})
                if ok:self.k.WaitForSingleObject(row['handle'],5000)
        return outcomes

    def close(self):
        self.stop.set();self.thread.join()
        for row in self.rows.values():self.k.CloseHandle(row['handle'])


def window_evidence(pids):
    from ctypes import wintypes as w
    api=ctypes.WinDLL('user32',use_last_error=True)
    callback=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    api.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    api.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    api.IsWindowVisible.argtypes=[w.HWND]
    api.SendMessageTimeoutW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM,w.UINT,w.UINT,ctypes.POINTER(ctypes.c_size_t)]
    api.SendMessageTimeoutW.restype=ctypes.c_ssize_t
    api.EnumWindows.argtypes=[callback,w.LPARAM];api.EnumChildWindows.argtypes=[w.HWND,callback,w.LPARAM]
    rows=[]
    def record(hwnd,parent=None):
        pid=w.DWORD();api.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value not in pids or len(rows)>=120:return
        name=ctypes.create_unicode_buffer(256);api.GetClassNameW(hwnd,name,256)
        title=ctypes.create_unicode_buffer(1024);count=ctypes.c_size_t()
        api.SendMessageTimeoutW(hwnd,13,1024,ctypes.addressof(title),2,100,ctypes.byref(count))
        rows.append({'hwnd':int(hwnd),'pid':pid.value,'parent_window':parent,'class':name.value,
                     'title':title.value,'visible':bool(api.IsWindowVisible(hwnd))})
    @callback
    def top(hwnd,_):
        pid=w.DWORD();api.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value in pids:
            record(hwnd)
            @callback
            def descendant(inner,_):record(inner,int(hwnd));return True
            api.EnumChildWindows(hwnd,descendant,0)
        return True
    api.EnumWindows(top,0)
    return rows

def verify(compiler,report):
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise RuntimeError('Installer diagnostics require a disposable GitHub-hosted runner')
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
        def run(exe,*args,timeout=60,environment=None,phase=None):
            command=[str(exe),*args]
            stage={'index':len(result.setdefault('runs',[]))+1,'command':command,'phase':phase or Path(exe).name,
                   'timeout_seconds':timeout,'started':time.time()}
            result['runs'].append(stage)
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            child=subprocess.Popen(command,env=environment or env,creationflags=subprocess.CREATE_NO_WINDOW)
            tree=None
            try:
                tree=ProcessTree(child)
                code=child.wait(timeout=timeout)
                stage['returncode']=code
                return code
            except subprocess.TimeoutExpired:
                stage['timed_out']=True
                try:
                    stage['processes']=tree.freeze()
                    stage['process_scan_errors']=tree.errors
                    stage['windows']=window_evidence({r['pid'] for r in stage['processes'] if r['alive']})
                except Exception as exc:stage['process_evidence_error']=type(exc).__name__
                try:
                    stage['installation']={'exists':install.exists(),
                        'marker':(install/'.typeless-install').exists(),
                        'uninstaller':(install/'Uninstall.exe').exists(),
                        'fixture_marker':marker.read_text() if marker.exists() else None,
                        'entries':[str(p.relative_to(install)) for p in install.rglob('*')][:300] if install.exists() else []}
                    if (install/'upgrade.log').exists():stage['upgrade_log']=(install/'upgrade.log').read_text(encoding='utf-8-sig')
                    from PIL import ImageGrab
                    screenshot=report.with_name(report.stem+f'-timeout-{stage["index"]}.png')
                    ImageGrab.grab(all_screens=True).save(screenshot)
                    stage['screenshot']=screenshot.name
                except Exception as exc:stage['filesystem_or_screenshot_error']=type(exc).__name__
                finally:
                    try:
                        if tree:stage['cleanup']=tree.cleanup()
                        elif child.poll() is None:child.kill()
                    except Exception as exc:stage['cleanup_error']=type(exc).__name__
                raise
            finally:
                if tree:tree.close()
                stage['ended']=time.time()
                report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
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
            foreign=root/'occupied';foreign.mkdir();(foreign/'user.txt').write_text('keep')
            baseline=marker.read_text().count('started')
            env['DT_UPGRADE_TEST_ROOT']=str(foreign)
            try:assert run(bad,'/UPDATE','/WAITPID=0')==2
            finally:env['DT_UPGRADE_TEST_ROOT']=str(install)
            time.sleep(1.2)
            assert marker.read_text().count('started')==baseline+1
            assert list(foreign.iterdir())==[foreign/'user.txt'] and (foreign/'user.txt').read_text()=='keep'
            result['foreign_directory_refusal_reopens_previous_without_writes']=True
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
            def retarget(phase):
                return run('powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                    '-File',str(ROOT/'packaging/upgrade-launch.ps1'),'-Phase','Retarget',
                    environment=redirect_env,timeout=20,phase=phase)
            with entry.open('rb'):
                assert retarget('retarget_locked_entry')==2 and entry.read_bytes()==original
            assert retarget('retarget_unlocked_entry')==0 and entry.read_bytes()==good.read_bytes()
            backups=list(portable.glob('*.before-upgrade-*'))
            assert len(backups)==1 and backups[0].read_bytes()==original
            assert (portable/'config.json').read_text()=='untouched legacy data'
            assert run(entry)==0
            result['portable_entry_atomic_replace_and_backup']=True
            result['passed']=True
        except BaseException as exc:
            result['error']={'type':type(exc).__name__,'message':str(exc)}
            raise
        finally:
            if (install/'upgrade.log').exists():
                result['log']=(install/'upgrade.log').read_text(encoding='utf-8-sig')
            if marker.exists():result['fixture_starts']=marker.read_text().count('started')
            time.sleep(1.2)
            try:
                if (install/'Uninstall.exe').exists():
                    code=run(install/'Uninstall.exe','/S','_?='+str(install))
                    result['cleanup_exit_code']=code
            except Exception as exc:
                result['cleanup_error']={'type':type(exc).__name__,'message':str(exc)}
                if 'error' not in result:raise
            finally:report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--compiler',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();verify(a.compiler.resolve(),a.report.resolve())
