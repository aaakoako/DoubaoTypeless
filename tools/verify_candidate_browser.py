"""仅GitHub托管Windows：正式EXE + 正式手机页面 + 真实Chromium输入框。

使用合成文本，真实鼠标/热键/剪贴板；对照网页不是ChatGPT/Cursor验收。
没有修改EXE的投递函数。仅清理本脚本创建的进程与浏览器。
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import io
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

TARGET_HTML = '''<!doctype html><meta charset="utf-8"><title>DT Browser Contract</title>
<style>body{font:18px sans-serif;margin:35px}textarea, [contenteditable]{border:1px solid #888;width:650px;height:140px;display:block;margin:12px}</style>
<h1>Disposable native input target</h1>
<div id="composer"><textarea id="prompt-textarea" aria-label="Message input"></textarea>
<div id="editable" contenteditable="true" role="textbox" aria-label="Chat input"></div>
<div id="attachments"></div></div><textarea id="other" aria-label="Other input"></textarea>
<script>
window.enterEvents=0;document.addEventListener('keydown',e=>{if(e.key==='Enter')window.enterEvents++});
window.pasteCount=0; document.addEventListener('paste',e=>{window.pasteCount++;
 const files=[...e.clipboardData.files];
 if(files.length){e.preventDefault();for(const file of files){const im=new Image();im.alt='Attachment '+(document.images.length+1);im.width=48;im.height=48;im.src=URL.createObjectURL(file);document.getElementById('attachments').append(im)}}});
window.dynamicTitle=null;
</script>'''


async def until(check, *, timeout=12, message='condition not met'):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        result=check()
        if hasattr(result,'__await__'):result=await result
        if result:return result
        await asyncio.sleep(.07)
    raise AssertionError(message)


def own_window(pid, title):
    import win32gui,win32process
    found=[]
    def each(hwnd,_):
        if win32process.GetWindowThreadProcessId(hwnd)[1]==pid and win32gui.GetWindowText(hwnd)==title:
            found.append(hwnd)
    win32gui.EnumWindows(each,None)
    return found[0] if found else 0


class NativeInspector:
    def __init__(self):
        sys.coinit_flags=0
        import comtypes.client
        self.module=comtypes.client.GetModule('UIAutomationCore.dll')
        self.uia=comtypes.client.CreateObject('{FF48DBA4-60EF-4201-AA87-54103EEF594E}',interface=self.module.IUIAutomation)

    def controls(self, hwnd):
        if not hwnd:return []
        root=self.uia.ElementFromHandle(hwnd)
        items=root.FindAll(4,self.uia.CreateTrueCondition())
        return [items.GetElement(i) for i in range(min(600,items.Length))]

    def text(self, hwnd):
        return '\n'.join(str(e.CurrentName or '') for e in self.controls(hwnd))

    def click(self, hwnd, name):
        from pynput.mouse import Controller, Button
        for element in self.controls(hwnd):
            if element.CurrentName==name and element.CurrentControlType==50000 and element.CurrentIsEnabled:
                r=element.CurrentBoundingRectangle
                if r.right>r.left and r.bottom>r.top:
                    mouse=Controller();mouse.position=((r.left+r.right)//2,(r.top+r.bottom)//2)
                    mouse.click(Button.left)
                    return True
        return False


def hotkey(expand=False):
    from pynput.keyboard import Controller, Key, KeyCode
    k=Controller()
    if expand:
        k.press(Key.alt_l);k.press(Key.shift);k.press(KeyCode.from_vk(0x45))
        time.sleep(.07);k.release(KeyCode.from_vk(0x45));k.release(Key.shift);k.release(Key.alt_l)
    else:
        k.press(Key.alt_l);k.press(KeyCode.from_vk(0x49));time.sleep(.07)
        k.release(KeyCode.from_vk(0x49));k.release(Key.alt_l)


def clipboard_text():
    import win32clipboard,win32con
    for _ in range(20):
        try:
            win32clipboard.OpenClipboard()
            try:return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            finally:win32clipboard.CloseClipboard()
        except Exception:time.sleep(.02)
    raise RuntimeError('cannot read clipboard')


async def exercise(child,data,result,report):
    from aiohttp import ClientSession,web
    from playwright.async_api import async_playwright
    import win32gui,win32clipboard
    note=data/'pair.txt'
    await until(lambda:note.is_file() or child.poll() is not None,message='startup note missing')
    if child.poll() is not None:raise RuntimeError('candidate exited during startup')
    addr,code=note.read_text(encoding='utf-8').splitlines()[:2]
    base='http://127.0.0.1:'+str(urlparse(addr).port)
    server=web.Application();server.router.add_get('/',lambda _:web.Response(text=TARGET_HTML,content_type='text/html'))
    runner=web.AppRunner(server);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    target_url='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])+'/'
    result['cases']=[]
    cases=result['cases']; inspector=NativeInspector()
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=False,args=['--force-renderer-accessibility'])
            phone_browser=await pw.chromium.launch()
            try:
                target=await browser.new_page(viewport={'width':1100,'height':850})
                await target.goto(target_url)
                phone=await phone_browser.new_page(viewport={'width':430,'height':850})
                # 测试网络延迟只延迟原页面生成的准备回执，不补造协议字段。
                await phone.add_init_script('''window.prepareDelay=0;
const raw=WebSocket.prototype.send;WebSocket.prototype.send=function(data){
 let value;try{value=JSON.parse(data)}catch{}
 if(value?.type==='draft.prepared'&&window.prepareDelay){setTimeout(()=>{if(this.readyState===1)raw.call(this,data)},window.prepareDelay)}
 else raw.call(this,data);
};''')
                errors=[];phone.on('pageerror',lambda e:errors.append(str(e)))
                await phone.goto(base+'/?pair='+code)
                await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                async with ClientSession() as http:
                    sessions=await (await http.get(base+'/v3/sessions')).json()
                    for entry in sessions['items']:
                        response=await http.post(base+'/v3/grants',json={'session_id':entry['session_id'],'allow_insert':True,'allow_capture':True},headers={'Origin':base})
                        assert response.status==200

                def hud():return own_window(child.pid,'DT-V3-HUD')
                def hud_text():return inspector.text(hud())
                async def ready(text):
                    await phone.fill('#text',text)
                    await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                    await target.bring_to_front();await target.locator('#prompt-textarea').click()
                    await until(lambda:hud() and win32gui.IsWindowVisible(hud()),message='native HUD not visible')
                async def completed(expected,selector='#prompt-textarea'):
                    await until(lambda: _matches(target,selector,expected), message='external browser exact text mismatch')
                    await until(lambda:_phone_empty(phone),message='real phone did not rotate to empty')
                    assert clipboard_text()==expected
                    assert child.poll() is None

                text='HUD按钮第一段  Image2 / Opus\n保留换行'
                result['stage']='hud_button_browser'
                await ready(text)
                assert inspector.click(hud(),'插入并复制'),hud_text()
                await completed(text)
                await until(lambda:not win32gui.IsWindowVisible(hud()),message='successful HUD did not hide')
                cases.append({'name':'native_HUD_button_browser','passed':True})

                # 原生详情按钮不能把文字送回本工具自身，也不能丢掉目标控件。
                result['stage']='review_button_browser'
                await target.locator('#prompt-textarea').fill('')
                text='详情按钮第二段'
                await ready(text);hotkey(expand=True)
                review=await until(lambda:own_window(child.pid,'当前图文'))
                await until(lambda:win32gui.IsWindowVisible(review))
                assert inspector.click(review,'插入并复制'),inspector.text(review)
                await completed(text)
                cases.append({'name':'native_review_button_browser','passed':True})

                result['stage']='contenteditable_and_dynamic_title'
                text='网页可编辑区域  第三段'
                await phone.fill('#text',text)
                await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                await target.locator('#editable').click()
                await target.evaluate("window.dynamicTitle=setInterval(()=>document.title='Working '+Date.now(),80)")
                hotkey();await completed(text,'#editable')
                await target.evaluate('clearInterval(window.dynamicTitle)')
                cases.append({'name':'contenteditable_dynamic_title_hotkey','passed':True})

                # 回执等待中换到同窗口的另一输入控件，必须停止，不得贴错位置。
                result['stage']='target_change_then_recover'
                await target.locator('#prompt-textarea').fill('')
                text='换焦点不得贴错'
                await ready(text);await phone.evaluate('window.prepareDelay=1400');hotkey()
                await until(lambda:'确认手机' in hud_text())
                await target.locator('#other').click()
                await until(lambda:'目标变化' in hud_text(),timeout=10,message='target change had no visible result')
                assert await phone.locator('#text').input_value()==text
                assert await target.locator('#other').input_value()==''
                assert await target.locator('#prompt-textarea').input_value()==''
                assert child.poll() is None
                await phone.evaluate('window.prepareDelay=0')
                await target.locator('#prompt-textarea').click();hotkey();await completed(text)
                cases.append({'name':'wrong_target_rejected_then_retry_succeeds','passed':True})

                result['stage']='clipboard_failure_then_recover'
                await target.locator('#prompt-textarea').fill('')
                text='剪贴板异常后仍可继续'
                await ready(text)
                win32clipboard.OpenClipboard()
                try:
                    hotkey()
                    await until(lambda:'保留' in hud_text() and '插入未完成' in hud_text(),timeout=12,
                                message='clipboard failure missing visible recovery')
                    assert await phone.locator('#text').input_value()==text
                    assert await target.locator('#prompt-textarea').input_value()==''
                    assert child.poll() is None
                finally:win32clipboard.CloseClipboard()
                await target.locator('#prompt-textarea').click();hotkey();await completed(text)
                cases.append({'name':'real_clipboard_lock_then_retry_succeeds','passed':True})

                result['stage']='phone_button_browser'
                await target.locator('#prompt-textarea').fill('')
                text='手机按钮也必须插入'
                await ready(text)
                await phone.click('#sendBtn')
                await completed(text)
                cases.append({'name':'production_phone_insert_button','passed':True})

                assert await target.evaluate('window.enterEvents')==0
                assert not errors,errors
                result['enter_events']=0
                result['page_errors']=errors
                result['real_browser']=True
                await target.screenshot(path=str(report.with_suffix('.png')))
            finally:
                await phone_browser.close();await browser.close()
    finally:await runner.cleanup()


async def _matches(page,selector,expected):
    if selector=='#editable':return await page.locator(selector).inner_text()==expected
    return await page.locator(selector).input_value()==expected


async def _phone_empty(page):return await page.locator('#text').input_value()==''


def verify(exe,report):
    if sys.platform!='win32' or os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('Only disposable Windows Actions runners are supported')
    exe=exe.resolve(strict=True);report=report.resolve();report.parent.mkdir(parents=True,exist_ok=True)
    result={'passed':False,'test':'frozen-production-phone-browser-stability','cursor_tested':False,
            'android_ime_tested':False,'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='dt-browser-stability-') as temp:
        data=Path(temp)/'data'
        env={**os.environ,'DT_V3_DATA_DIR':str(data),'DT_V3_PIPE':'DT-stable-'+uuid.uuid4().hex,'PYTHONUTF8':'1'}
        env.pop('QT_QPA_PLATFORM',None)
        child=subprocess.Popen([str(exe),'--minimized'],env=env)
        result['pid']=child.pid
        try:
            asyncio.run(exercise(child,data,result,report))
            result['stage']='normal_exit'
            quitproc=subprocess.run([str(exe),'--quit'],env=env,timeout=15)
            assert quitproc.returncode==0
            result['exit_code']=child.wait(15)
            assert result['exit_code']==0
            result['passed']=True;result['stage']='complete'
        except Exception as exc:
            result.update(error_type=type(exc).__name__,error=str(exc),process_exit_before_cleanup=child.poll())
        finally:
            if child.poll() is None:
                subprocess.run([str(exe),'--quit'],env=env,timeout=15)
                try:child.wait(15)
                except subprocess.TimeoutExpired:
                    child.terminate();child.wait(5);result['test_owned_forced_cleanup']=True
            logs=report.parent/(report.stem+'-logs');logs.mkdir(exist_ok=True)
            for p in (data/'logs').glob('*.log'):shutil.copyfile(p,logs/p.name)
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('exe',type=Path);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();raise SystemExit(verify(a.exe,a.report))
