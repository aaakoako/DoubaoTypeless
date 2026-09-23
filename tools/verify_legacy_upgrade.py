"""Published 0.4.2 EXE, real confirmation/download/replacement/restart on disposable Windows.
Only the release server is a local TLS fixture; client and updater are not patched.
"""
import argparse, datetime, hashlib, http.server, json, os, shutil, ssl, subprocess, sys, tempfile, threading, time, uuid
from pathlib import Path
from urllib.request import urlopen

class ReleaseProxy:
    def __init__(self, folder, package, version):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Typeless disposable update test')])
        now=datetime.datetime.now(datetime.timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
              .not_valid_after(now+datetime.timedelta(days=1))
              .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
              .add_extension(x509.SubjectAlternativeName([x509.DNSName('api.github.com'),x509.DNSName('github.com')]),critical=False)
              .sign(key,hashes.SHA256()))
        self.cert=folder/'test-ca.pem';self.cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        private=folder/'test-key.pem';private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(self.cert,private)
        payload=package.read_bytes();calls=[]
        release={'tag_name':'v'+version,'assets':[{'name':'DoubaoTypeless.exe',
            'browser_download_url':f'https://github.com/aaakoako/DoubaoTypeless/releases/download/v{version}/DoubaoTypeless.exe',
            'size':len(payload),'digest':'sha256:'+hashlib.sha256(payload).hexdigest()}]}
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_CONNECT(self):
                if self.path not in ('api.github.com:443','github.com:443'):
                    self.send_error(403);return
                self.send_response(200);self.end_headers()
                self.connection=context.wrap_socket(self.connection,server_side=True)
                self.rfile=self.connection.makefile('rb');self.wfile=self.connection.makefile('wb')
                self.close_connection=False;self.handle_one_request();self.close_connection=True
            def do_GET(self):
                calls.append(self.path)
                if self.path.endswith('/releases/latest'):body=json.dumps(release).encode()
                elif self.path.endswith('/DoubaoTypeless.exe'):body=payload
                else:self.send_error(404);return
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
                self.wfile.write(body);self.wfile.flush()
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}';self.calls=calls
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join()


def verify(package, report):
    if sys.platform!='win32' or os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise RuntimeError('Published legacy GUI test requires disposable GitHub-hosted Windows; never occupy the user desktop')
    import win32gui,win32process,win32api,win32con,winreg
    from pynput.mouse import Controller,Button
    from PIL import ImageGrab
    key=r'Software\DoubaoTypelessInstallerTest'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key):raise RuntimeError('Existing test registration')
    except FileNotFoundError:pass
    report.parent.mkdir(parents=True,exist_ok=True)
    result={'passed':False,'published_legacy_version':'0.4.2','target_application_tested':False,
            'server':'local TLS release fixture; trust configured only in child environment','legacy_data_migration':False}
    with tempfile.TemporaryDirectory(prefix='legacy-upgrade-',dir=report.parent.resolve()) as temp:
        root=Path(temp);old=root/'old app';old.mkdir();install=root/'installed';data=root/'new-data';data.mkdir()
        original=old/'DoubaoTypeless.exe'
        with urlopen('https://github.com/aaakoako/DoubaoTypeless/releases/download/v0.4.2/DoubaoTypeless.exe',timeout=60) as response:
            original.write_bytes(response.read())
        result['published_exe_sha256']=hashlib.sha256(original.read_bytes()).hexdigest()
        config={'llm_enabled':False,'learn_enabled':False,'start_with_windows':False,'bridge_port':0,
                'hotkey_insert':'','hotkey_toggle_review':''}
        (old/'config.json').write_text(json.dumps(config),encoding='utf-8');(old/'data').mkdir()
        dictionary=old/'data/dictionary.txt';dictionary.write_text('legacy fixture -> kept\n',encoding='utf-8')
        (data/'settings.json').write_text(json.dumps({k:'<smoke-disabled>' for k in ('hotkey_insert','hotkey_recall','hotkey_expand','hotkey_capture')}),encoding='utf-8')
        # The test installer name carries the target version; the runtime report verifies source identity.
        version=package.name.split('_')[1]
        proxy=ReleaseProxy(root,package,version)
        env={**os.environ,'HTTPS_PROXY':proxy.url,'HTTP_PROXY':proxy.url,'NO_PROXY':'127.0.0.1,localhost',
             'SSL_CERT_FILE':str(proxy.cert),'DT_GITHUB_MIRROR':'0','DT_V3_DATA_DIR':str(data),
             'DT_V3_PIPE':'DT-LegacyUpgrade-'+uuid.uuid4().hex,'DT_UPGRADE_TEST_ROOT':str(install)}
        env.pop('DT_SKIP_AUTO_UPDATE_CHECK',None);env.pop('QT_QPA_PLATFORM',None)
        child=subprocess.Popen([str(original)],cwd=old,env=env)
        new_exe=None
        try:
            deadline=time.monotonic()+60;dialog=0
            while time.monotonic()<deadline and not dialog:
                def match(hwnd,_):
                    nonlocal dialog
                    if win32gui.GetWindowText(hwnd)!='发现新版本':return
                    pid=win32process.GetWindowThreadProcessId(hwnd)[1]
                    handle=win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION|win32con.PROCESS_VM_READ,False,pid)
                    try:path=win32process.GetModuleFileNameEx(handle,0)
                    finally:handle.Close()
                    if Path(path).resolve()==original.resolve():dialog=hwnd
                win32gui.EnumWindows(match,None);time.sleep(.1)
            assert dialog,'Published 0.4.2 did not offer the fixture release'
            before_config=(old/'config.json').read_bytes();before_dictionary=dictionary.read_bytes()
            button=win32gui.GetDlgItem(dialog,6);assert button,'Missing native Yes button'
            rect=win32gui.GetWindowRect(button);point=((rect[0]+rect[2])//2,(rect[1]+rect[3])//2)
            win32gui.SetForegroundWindow(dialog);mouse=Controller();mouse.position=point;mouse.click(Button.left)
            result['native_update_confirmation_clicked']=True
            child.wait(timeout=50);result['old_process_exited']=True
            deadline=time.monotonic()+100
            while time.monotonic()<deadline:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as registration:
                        candidate=Path(winreg.QueryValueEx(registration,'CurrentExecutable')[0])
                        source=winreg.QueryValueEx(registration,'CurrentSource')[0]
                    if (install/'upgrade.log').is_file() and 'upgrade succeeded' in (install/'upgrade.log').read_text(encoding='utf-8-sig'):
                        new_exe=candidate;break
                except FileNotFoundError:pass
                time.sleep(.2)
            assert new_exe and new_exe.is_file(),'Complete package did not restart'
            assert hashlib.sha256(original.read_bytes()).digest()==hashlib.sha256(package.read_bytes()).digest()
            assert (old/'config.json').read_bytes()==before_config and dictionary.read_bytes()==before_dictionary
            result.update(source_sha=source,legacy_data_unchanged=True,complete_entry_replaced=True,proxy_requests=proxy.calls)
            # Reopening the replaced old shortcut must forward without reinstalling.
            stamp=new_exe.stat().st_mtime_ns
            forwarded=subprocess.run([str(original)],cwd=old,env=env,timeout=60)
            assert forwarded.returncode==0 and new_exe.stat().st_mtime_ns==stamp
            result['repeated_old_entry_forwards']=True
            ImageGrab.grab().save(report.parent/'legacy-upgrade-complete.png')
            result['passed']=True
        finally:
            proxy.close()
            for name in ('update.log','debug.log'):
                if (old/name).exists():shutil.copy2(old/name,report.parent/('legacy-'+name))
            if (install/'upgrade.log').exists():shutil.copy2(install/'upgrade.log',report.parent/'legacy-native-upgrade.log')
            if new_exe:
                subprocess.run([str(new_exe),'--quit'],env=env,timeout=20)
                time.sleep(2)
            if child.poll() is None:child.terminate();child.wait(10)
            if (install/'Uninstall.exe').exists():
                subprocess.run([str(install/'Uninstall.exe'),'/S','_?='+str(install)],timeout=60)
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);p.add_argument('--report',type=Path,required=True)
    args=p.parse_args();verify(args.package.resolve(),args.report.resolve())
