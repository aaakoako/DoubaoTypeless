"""CI专用：实际无控制台EXE连续三次Alt+I，真实剪贴板/键盘/外部输入框。

不使用PasteTarget/平台替身，不代表Cursor/手机输入法通过。
只在临时GitHub Windows runner执行，只管理本脚本创建的两个PID。
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
import uuid

TARGET = r'''
import json, sys, tkinter as tk
from pathlib import Path
p=Path(sys.argv[1]); title=sys.argv[2]
w=tk.Tk();w.title(title);w.geometry('500x220')
e=tk.Text(w);e.pack(fill='both',expand=True);e.focus_force()
w.after(200,lambda:(w.lift(),e.focus_force()))
def tick():
    q=p.with_suffix('.tmp')
    q.write_text(json.dumps({'text':e.get('1.0','end-1c')}),encoding='utf-8')
    q.replace(p);w.after(50,tick)
w.after(50,tick);w.mainloop()
'''

async def message(ws, kind: str, timeout: float=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        msg=await ws.receive_json(timeout=max(.05,deadline-time.monotonic()))
        if msg.get('type')=='error':
            raise RuntimeError('bridge rejected test request: '+str(msg.get('error')))
        if msg.get('type')==kind:return msg
    raise TimeoutError(kind)

async def exercise(exe: Path, data: Path, env: dict, child, target, textfile: Path, title: str):
    from aiohttp import ClientSession
    import win32gui, win32con, win32process, win32clipboard
    from pynput.keyboard import Controller, Key
    note=data/'pair.txt'
    for _ in range(300):
        if child.poll() is not None: raise RuntimeError('candidate exited during startup')
        if note.is_file():break
        await asyncio.sleep(.1)
    else:raise TimeoutError('pair note not ready')
    address,code=note.read_text(encoding='utf-8').splitlines()[:2]
    base='http://127.0.0.1:'+str(urlparse(address).port)
    async with ClientSession() as http:
        async with http.post(base+'/v3/pair',json={'code':code},headers={'Origin':base}) as r:
            if r.status!=200:raise RuntimeError('test pairing rejected')
            creds=await r.json()
        async with http.ws_connect(base+'/ws') as ws:
            await ws.send_json({'type':'session.hello','session_id':creds['session_id'],'token':creds['token']})
            state=await message(ws,'session.ready')
            key=Controller(); aggregate='';rounds=[]
            for text in ['第一段  保留空格\n','第二段 Image2 / Opus\n','第三段连续输入完成']:
                hwnd=win32gui.FindWindow(None,title)
                if not hwnd or win32process.GetWindowThreadProcessId(hwnd)[1]!=target.pid:
                    raise RuntimeError('test-owned input window not found')
                win32gui.SetForegroundWindow(hwnd)
                for _ in range(30):
                    if win32gui.GetForegroundWindow()==hwnd:break
                    await asyncio.sleep(.05)
                else:raise RuntimeError('test target cannot receive focus')
                await ws.send_json({'protocol':3,'type':'draft.update','draft_id':state['draft_id'],
                    'epoch':state['epoch'],'revision':state['revision']+1,'text':text,
                    'asset_refs':[],'asset_documents':[]})
                ack=await message(ws,'draft.ack')
                if not ack.get('durable'):raise RuntimeError('draft not durable')
                # 实际进入全局热键监听器，再由EXE自己的队列/平台代码执行Ctrl+V。
                key.press(Key.alt_l); key.press('i'); key.release('i'); key.release(Key.alt_l)
                rotated=await message(ws,'draft.rotated',15)
                if not rotated.get('rotated'):raise RuntimeError('text draft not rotated')
                archived=rotated.get('archived') or {}
                if archived.get('source_text',archived.get('text'))!=text:raise RuntimeError('wrong archived text')
                aggregate+=text
                for _ in range(80):
                    if child.poll() is not None:raise RuntimeError('candidate exited after insert')
                    try:received=json.loads(textfile.read_text(encoding='utf-8')).get('text')
                    except (OSError,ValueError):received=None
                    if received==aggregate:break
                    await asyncio.sleep(.05)
                else:raise RuntimeError('external target text mismatch')
                copied=None
                for _ in range(20):
                    try:
                        win32clipboard.OpenClipboard()
                        try:copied=win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                        finally:win32clipboard.CloseClipboard()
                        break
                    except Exception:await asyncio.sleep(.025)
                if copied!=text:raise RuntimeError('insert-and-copy clipboard mismatch')
                rounds.append({'round':len(rounds)+1,'exact_text':True,'clipboard':True,
                    'rotated':True,'process_alive':child.poll() is None})
                state=rotated
            return rounds

def verify(exe: Path, report: Path) -> int:
    if sys.platform!='win32' or os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('Restricted to disposable Windows GitHub Actions runner')
    exe=exe.resolve(strict=True)
    result={'test':'frozen-three-text-inserts','passed':False,'cursor_tested':False,
            'phone_ime_tested':False,'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='dt-native-text-') as temp:
        root=Path(temp);data=root/'data';state=root/'target.json';script=root/'target.py'
        script.write_text(TARGET,encoding='utf-8');title='DT-Native-Input-'+uuid.uuid4().hex[:8]
        env={**os.environ,'DT_V3_DATA_DIR':str(data),'DT_V3_PIPE':'DT-smoke-'+uuid.uuid4().hex}
        env.pop('QT_QPA_PLATFORM',None) # 真正桌面，不用离屏替代系统焦点。
        child=subprocess.Popen([str(exe),'--minimized'],env=env)
        target=subprocess.Popen([sys.executable,str(script),str(state),title],env=env)
        result.update(pid=child.pid,target_pid=target.pid)
        try:
            result['rounds']=asyncio.run(exercise(exe,data,env,child,target,state,title))
            quitproc=subprocess.run([str(exe),'--quit'],env=env,timeout=15)
            result['quit_command_exit']=quitproc.returncode
            result['process_exit']=child.wait(timeout=15)
            if quitproc.returncode or result['process_exit']:raise RuntimeError('not graceful exit')
            result['passed']=True
        except Exception as exc:
            result.update(error_type=type(exc).__name__,error=str(exc),passed=False)
        finally:
            import win32gui,win32con,win32process
            hwnd=win32gui.FindWindow(None,title)
            if hwnd and win32process.GetWindowThreadProcessId(hwnd)[1]==target.pid:
                win32gui.PostMessage(hwnd,win32con.WM_CLOSE,0,0)
                try:target.wait(timeout=5)
                except subprocess.TimeoutExpired:pass
            for process in (child,target):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                    result['test_owned_cleanup']=True
            report.parent.mkdir(parents=True,exist_ok=True)
            logs=report.parent/(report.stem+'-logs');logs.mkdir(exist_ok=True)
            for path in (data/'logs').glob('*.log'):
                # 只有临时CI配对凭据和固定测试文本；仍不包含pair.txt/真实用户数据。
                shutil.copyfile(path,logs/path.name)
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('exe',type=Path);p.add_argument('--report',required=True,type=Path)
    args=p.parse_args();raise SystemExit(verify(args.exe,args.report))
