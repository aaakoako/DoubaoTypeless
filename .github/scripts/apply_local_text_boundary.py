"""Exact two-file startup ordering fix; no workflow writes or force push."""
import hashlib,os,subprocess
from pathlib import Path
BRANCH='v3/assistant-runtime-safety'
BASE='627fe4e767929e55ed4242bf29cb478a05c60b74'
def run(*args,**kw):return subprocess.run(args,check=True,**kw)
def replace(path,sha,edits):
 p=Path(path)
 if hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise RuntimeError('source changed: '+path)
 text=p.read_text(encoding='utf-8')
 for old,new in edits:
  if text.count(old)!=1:raise RuntimeError('unexpected replacement count')
  text=text.replace(old,new)
 p.write_text(text,encoding='utf-8');run('git','add','--',path)
def main():
 if os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:raise RuntimeError('wrong branch')
 if run('git','rev-parse','HEAD^',capture_output=True,text=True).stdout.strip()!=BASE:raise RuntimeError('wrong parent')
 replace('src/doubao_typeless/ui/desktop.py','0b992e96c6e95b49eca15f0d0bd1940aecec74eaabd7f70f75751a896ec0a3d7',[
 ('        app.hud.start()\n        loop = app.start_background(start_hud=False)',
 '''        app.hud.start()
        # Build the native surfaces/control listener before exposing HTTP readiness.
        # Otherwise a second --quit/show can reach a half-started process and time out
        # while expensive first-use font/icon/widget initialization is still running.
        shell = DesktopShell(app)
        if shell._wake is None or not shell._wake.isListening():
            raise RuntimeError("无法建立本机控制入口，已停止启动")
        logger("[v3.lifecycle] native_shell_ready")
        loop = app.start_background(start_hud=False)'''),
 ('        shell = DesktopShell(app)\n        stored = load_settings(app.data_dir)\n',
 '        shell.client.refresh()\n        logger("[v3.lifecycle] desktop_event_loop_ready")\n        stored = load_settings(app.data_dir)\n')])
 replace('tools/verify_candidate_startup.py','754c675d0df7b5b21fe4459eed43749d28adfbff14ee90f18ff27d487c49aaa3',[
 ('("runtime.log", "v3.log")','("runtime.log", "v3.log", "control.log")')])
 run('git','rm','--','.github/scripts/apply_local_text_boundary.py')
 run('git','config','user.name','github-actions[bot]');run('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
 run('git','commit','-m','fix(v3): initialize desktop control before advertising service readiness')
 run('git','push','origin',f'HEAD:refs/heads/{BRANCH}')
if __name__=='__main__':main()
