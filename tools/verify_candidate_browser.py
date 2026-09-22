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
<style>body{font:18px sans-serif;margin:35px}textarea, [contenteditable]{border:1px solid #888;width:650px;height:140px;display:block;margin:12px}[contenteditable]{white-space:pre-wrap}</style>
<h1>Disposable native input target</h1>
<div id="composer" role="group" aria-label="Composer"><textarea id="prompt-textarea" aria-label="Message input"></textarea>
<div id="editable" contenteditable="true" role="textbox" aria-label="Chat input"></div>
<div id="attachments"></div><button aria-label="Add photos and files">+</button><button aria-label="Send">Send</button><button id="attachment-action" aria-label="Attachment details">附件详情</button></div><textarea id="other" aria-label="Other input"></textarea>
<script>
window.enterEvents=0;window.submitKeys=[];document.addEventListener('keydown',e=>{if(e.key==='Enter'){window.enterEvents++;window.submitKeys.push({ctrl:e.ctrlKey,target:e.target.id})}});
window.pasteCount=0; window.pasteRecords=[]; window.imageRecords=[]; window.attachDelay=0; window.shiftImageFocus=false;window.hideImageAccessibility=false;window.removeOnly=false;
window.pixelFingerprint=async function(im){const cv=document.createElement('canvas');cv.width=im.naturalWidth;cv.height=im.naturalHeight;cv.getContext('2d').drawImage(im,0,0);const rgba=cv.getContext('2d').getImageData(0,0,cv.width,cv.height).data;const rgb=new Uint8Array(cv.width*cv.height*3);for(let i=0,j=0;i<rgba.length;i+=4){rgb[j++]=rgba[i];rgb[j++]=rgba[i+1];rgb[j++]=rgba[i+2]}const digest=await crypto.subtle.digest('SHA-256',rgb);return {w:cv.width,h:cv.height,sha256:[...new Uint8Array(digest)].map(v=>v.toString(16).padStart(2,'0')).join('')}}; document.addEventListener('paste',e=>{window.pasteCount++;
 window.pasteRecords.push({target:e.target.id, text:e.clipboardData.getData('text/plain')});
 const files=[...e.clipboardData.files];
 if(files.length){e.preventDefault();for(const file of files){const im=new Image();im.alt='Uploading attachment';im.width=48;im.height=48;if(window.hideImageAccessibility||window.removeOnly)im.setAttribute('aria-hidden','true');im.onload=()=>{setTimeout(async()=>{im.alt='Attachment ready';if(window.removeOnly){const b=document.createElement('button');b.setAttribute('aria-label','Remove image attachment');b.textContent='Remove image';document.getElementById('attachments').append(b)}window.imageRecords.push(await window.pixelFingerprint(im));if(window.shiftImageFocus)document.getElementById('attachment-action').focus()},window.attachDelay)};im.src=URL.createObjectURL(file);document.getElementById('attachments').append(im)}}});
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
                    import win32gui, win32con
                    point=((r.left+r.right)//2,(r.top+r.bottom)//2)
                    mouse=Controller();mouse.position=point
                    hit=win32gui.WindowFromPoint(point)
                    root=win32gui.GetAncestor(hit,win32con.GA_ROOT) if hit else 0
                    if root!=hwnd:
                        raise AssertionError(f"native button occluded: {name}; expected={hwnd}, actual={root}")
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


CLIPBOARD_HOLDER = r"""
import json,sys,time,win32clipboard,win32gui
from pathlib import Path
# A message-only window identifies the lease owner; no UI or keyboard hook.
w=win32gui.CreateWindowEx(0,'STATIC','DT Clipboard Lease',0,0,0,0,0,-3,0,0,None)
try:
    for attempt in range(40):
        try:
            win32clipboard.OpenClipboard(w)
            break
        except Exception:
            if attempt==39:raise
            time.sleep(.05)
    note=Path(sys.argv[1]); tmp=note.with_suffix('.tmp')
    tmp.write_text(json.dumps({'pid':__import__('os').getpid(),'hwnd':w}),encoding='utf-8')
    tmp.replace(note)
    sys.stdin.readline()
    if win32clipboard.GetOpenClipboardWindow()!=w:
        raise RuntimeError('clipboard lease lost before explicit release')
    win32clipboard.CloseClipboard()
finally:
    win32gui.DestroyWindow(w)
"""


class ClipboardLease:
    """A separate test-owned PID holds the real clipboard, not the COM test thread."""
    def __init__(self, folder):
        self.path=folder/'clipboard-owner.json'
        self.log=(folder/'clipboard-holder.log').open('wb')
        self.process=subprocess.Popen([sys.executable,'-u','-c',CLIPBOARD_HOLDER,str(self.path)],
            stdin=subprocess.PIPE,stdout=self.log,stderr=subprocess.STDOUT)
        self.owner=None

    async def ready(self):
        import win32clipboard
        await until(lambda:self.path.is_file() or self.process.poll() is not None,
                    message='clipboard holder not ready')
        if self.process.poll() is not None:
            raise RuntimeError('clipboard holder failed before acquiring lease')
        self.owner=json.loads(self.path.read_text(encoding='utf-8'))
        if win32clipboard.GetOpenClipboardWindow()!=self.owner['hwnd']:
            raise RuntimeError('clipboard is not actually held by test child')
        return self.owner

    def release(self):
        if self.process.poll() is None:
            self.process.stdin.write(b'\n');self.process.stdin.flush()
        try:
            code=self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate();self.process.wait(5)
            raise RuntimeError('test clipboard holder did not release normally')
        finally:
            self.log.close()
            if self.process.stdin:self.process.stdin.close()
        if code:
            raise RuntimeError('test clipboard holder failed while holding lease')


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
                    delivered=await target.evaluate('window.pasteRecords.at(-1)')
                    assert delivered=={'target':selector[1:],'text':expected}, {'paste':delivered}
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

                # 按住真实 Shift，让投递停在松键保护阶段；改焦点后必须停止。
                # 桌面插入直接使用已收到的草稿，不依赖手机准备回执。
                result['stage']='target_change_then_recover'
                await target.locator('#prompt-textarea').fill('')
                text='换焦点不得贴错'
                await ready(text)
                from pynput.keyboard import Controller, Key
                keyboard=Controller();keyboard.press(Key.shift)
                try:
                    assert inspector.click(hud(),'插入并复制'),hud_text()
                    await until(lambda:clipboard_text()==text,timeout=1.2,
                                message='delivery did not reach modifier guard')
                    await target.locator('#other').click()
                finally:
                    keyboard.release(Key.shift)
                await until(lambda:'目标变化' in hud_text(),timeout=10,message='target change had no visible result')
                assert await phone.locator('#text').input_value()==text
                assert await target.locator('#other').input_value()==''
                assert await target.locator('#prompt-textarea').input_value()==''
                assert child.poll() is None
                await target.locator('#prompt-textarea').click();hotkey();await completed(text)
                cases.append({'name':'wrong_target_rejected_then_retry_succeeds','passed':True})

                # 关闭手机页面断开真实连接，电脑已收到的文字仍可插入；重连不复活旧稿。
                result['stage']='offline_desktop_insert_then_phone_reconnect'
                await target.locator('#prompt-textarea').fill('')
                text='手机断线后电脑保留的草稿'
                await ready(text)
                await phone.goto('about:blank')
                await until(lambda:'手机离线' in hud_text(),message='disconnect not visible in HUD')
                await target.bring_to_front();await target.locator('#prompt-textarea').click();hotkey()
                await until(lambda:_matches(target,'#prompt-textarea',text),message='offline desktop insert failed')
                await phone.goto(base+'/')
                await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                await completed(text)
                cases.append({'name':'offline_received_draft_insert_and_reconnect_without_resurrection','passed':True})

                result['stage']='clipboard_failure_then_recover'
                await target.locator('#prompt-textarea').fill('')
                text='剪贴板异常后仍可继续'
                await ready(text)
                lease=ClipboardLease(data.parent)
                try:
                    result['clipboard_fixture']=await lease.ready()
                    hotkey()
                    await until(lambda:'保留' in hud_text() and '插入未完成' in hud_text(),timeout=12,
                                message='clipboard failure missing visible recovery')
                    assert await phone.locator('#text').input_value()==text
                    assert await target.locator('#prompt-textarea').input_value()==''
                    assert child.poll() is None
                finally:lease.release()
                await target.locator('#prompt-textarea').click();hotkey();await completed(text)
                cases.append({'name':'real_clipboard_lock_then_retry_succeeds','passed':True})

                result['stage']='phone_button_browser'
                await target.locator('#prompt-textarea').fill('')
                text='手机按钮也必须插入'
                await ready(text)
                await phone.click('#sendBtn')
                await completed(text)
                cases.append({'name':'production_phone_insert_button','passed':True})


                # 正式手机页两张图片 -> 原生HUD按钮 -> 已有附件的真实浏览器Composer。
                # 仅网页延迟显示附件；不替换EXE观察器或投递函数。
                result['stage']='mixed_two_images_then_text'
                await target.locator('#prompt-textarea').fill('')
                await target.evaluate("window.imageRecords=[];window.pasteRecords=[];window.attachDelay=300;window.shiftImageFocus=true")
                from PIL import Image, ImageDraw
                fixtures=[]
                for idx in range(2):
                    path=data.parent/f'mixed-photo-{idx}.png'
                    im=Image.new('RGB',(96,72),(70+idx*60,90,185));ImageDraw.Draw(im).rectangle((8,8,24,24),fill='white');im.save(path)
                    fixtures.append(path)
                async def add_photo(path,caption):
                    await phone.set_input_files('#file',str(path))
                    await phone.wait_for_function("document.querySelector('#editor').classList.contains('show') && document.querySelector('#stage').dataset.ready==='1'")
                    await phone.click('#captionToggle')
                    await phone.fill('#captionInput',caption)
                    # 真正经过Canvas落笔、成品导出、上传，不能只构造asset_refs。
                    box=await phone.locator('#stage').bounding_box()
                    await phone.mouse.move(box['x']+box['width']*.3,box['y']+box['height']*.4)
                    await phone.mouse.down();await phone.mouse.move(box['x']+box['width']*.6,box['y']+box['height']*.5,steps=4);await phone.mouse.up()
                    await phone.click('#done')
                    await phone.wait_for_function("!document.querySelector('#editor').classList.contains('show') && document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                await add_photo(fixtures[0],'第一张标注')
                await add_photo(fixtures[1],'第二张标注')
                text='图片和文字必须一起到达  Image2 / Opus'
                await phone.fill('#text',text)
                await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                expected_text=text+'\n\n图1：第一张标注\n图2：第二张标注'
                await phone.screenshot(path=str(report.with_name(report.stem+'-phone.png')))
                expected_images=await phone.evaluate("""async()=>{const out=[];for(const im of document.querySelectorAll('.attach-card img')){await im.decode();const c=document.createElement('canvas');c.width=im.naturalWidth;c.height=im.naturalHeight;c.getContext('2d').drawImage(im,0,0);const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data,r=new Uint8Array(c.width*c.height*3);for(let i=0,j=0;i<a.length;i+=4){r[j++]=a[i];r[j++]=a[i+1];r[j++]=a[i+2]}const d=await crypto.subtle.digest('SHA-256',r);out.push({w:c.width,h:c.height,sha256:[...new Uint8Array(d)].map(v=>v.toString(16).padStart(2,'0')).join('')})}return out}""")
                await target.bring_to_front();await target.locator('#prompt-textarea').click()
                await until(lambda:'2 张图片已更新' in hud_text(),message='mixed images not visible in native HUD')
                assert inspector.click(hud(),'插入并复制'),hud_text()
                await completed(expected_text)
                assert await target.evaluate('window.imageRecords')==expected_images
                records=await target.evaluate('window.pasteRecords')
                assert len(records)==3 and [v['text'] for v in records]==['','',expected_text],records
                assert [v['target'] for v in records]==['prompt-textarea']*3,records
                assert await phone.locator('.attach-card').count()==0
                cases.append({'name':'two_rendered_images_then_text_after_attachment_focus','passed':True,'image_pixels':expected_images})

                # 用户的真实顺序：相册/截图成品加白板，将白板移到最前，一次点电脑按钮。
                result['stage']='three_reordered_images_one_desktop_click'
                await target.locator('#prompt-textarea').fill('')
                await target.evaluate("window.imageRecords=[];window.pasteRecords=[];document.querySelector('#attachments').replaceChildren()")
                await add_photo(fixtures[0],'相册标注')
                await add_photo(fixtures[1],'截图标注')
                await phone.click('#boardBtn')
                await phone.wait_for_function("document.querySelector('#stage').dataset.ready==='1' && !document.querySelector('#done').disabled")
                box=await phone.locator('#stage').bounding_box()
                await phone.mouse.move(box['x']+box['width']*.25,box['y']+box['height']*.3)
                await phone.mouse.down();await phone.mouse.move(box['x']+box['width']*.65,box['y']+box['height']*.65,steps=8);await phone.mouse.up()
                await phone.click('#captionToggle');await phone.fill('#captionInput','白板先插入')
                await phone.click('#done');await phone.wait_for_selector('#editor.show',state='hidden')
                await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本') && [...document.querySelectorAll('.attach-card label')].every(e=>e.textContent.includes('电脑已收到'))")
                await phone.locator('.attach-card').nth(2).locator('.left').click()
                await phone.locator('.attach-card').nth(1).locator('.left').click()
                assert '白板' in await phone.locator('.attach-card').first.locator('label').inner_text()
                text='一次操作三张图  不漏正文\n完整换行'
                await phone.fill('#text',text)
                await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                expected=text+'\n\n图1：白板先插入\n图2：相册标注\n图3：截图标注'
                expected_three=await phone.evaluate("""async()=>{const out=[];for(const im of document.querySelectorAll('.attach-card img')){await im.decode();const c=document.createElement('canvas');c.width=im.naturalWidth;c.height=im.naturalHeight;c.getContext('2d').drawImage(im,0,0);const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data,r=new Uint8Array(c.width*c.height*3);for(let i=0,j=0;i<a.length;i+=4){r[j++]=a[i];r[j++]=a[i+1];r[j++]=a[i+2]}const d=await crypto.subtle.digest('SHA-256',r);out.push({w:c.width,h:c.height,sha256:[...new Uint8Array(d)].map(v=>v.toString(16).padStart(2,'0')).join('')})}return out}""")
                await target.bring_to_front();await target.locator('#prompt-textarea').click()
                await until(lambda:'3 张图片已更新' in hud_text())
                assert inspector.click(hud(),'插入并复制')
                await completed(expected)
                assert await target.evaluate('window.imageRecords')==expected_three
                records=await target.evaluate('window.pasteRecords')
                assert [x['text'] for x in records]==['','','',expected],records
                assert not own_window(child.pid,'上次结果未知') or not win32gui.IsWindowVisible(own_window(child.pid,'上次结果未知'))
                cases.append({'name':'three_reordered_renders_one_native_click_no_per_image_confirmation','passed':True,'image_pixels':expected_three})

                # 无语义名称的窄 Composer 容器 + 仅移除附件按钮（真实 UIA，不替换观察器）。
                result['stage']='structural_scope_remove_buttons'
                await target.locator('#prompt-textarea').fill('')
                await target.evaluate("window.imageRecords=[];window.pasteRecords=[];document.querySelector('#attachments').replaceChildren();document.querySelector('#composer').removeAttribute('id');document.querySelector('[aria-label=Composer]').removeAttribute('aria-label');document.querySelector('#editable').style.display='none';window.removeOnly=true;window.shiftImageFocus=false")
                await add_photo(fixtures[0],'附件按钮识别')
                text='图片无需逐张确认'
                await phone.fill('#text',text);await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                await target.bring_to_front();await target.locator('#prompt-textarea').click()
                await phone.click('#sendBtn');await completed(text+'\n\n图1：附件按钮识别')
                assert len(await target.evaluate('window.imageRecords'))==1
                assert len(await target.evaluate('window.pasteRecords'))==2
                cases.append({'name':'unnamed_composer_remove_attachment_controls_auto_continue','passed':True})
                await target.evaluate("document.querySelector('[role=group]').id='composer';document.querySelector('#composer').setAttribute('aria-label','Composer');window.removeOnly=false;document.querySelector('#attachments').replaceChildren()")

                # 无附件接收证据时保留正文，不自动弹窗；主动恢复后继续文字不重复贴图。
                result['stage']='unknown_image_explicit_continue_text'
                await target.locator('#prompt-textarea').fill('')
                await target.evaluate("window.imageRecords=[];window.pasteRecords=[];window.shiftImageFocus=false;window.hideImageAccessibility=true")
                await add_photo(fixtures[0],'手动确认图片')
                text='接收未知时文字仍保留'
                await phone.fill('#text',text);await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                await target.bring_to_front();await target.locator('#prompt-textarea').click();hotkey()
                await until(lambda:'恢复' in hud_text(),timeout=15,message='missing explicit recovery action')
                recovery=own_window(child.pid,'上次结果未知')
                assert not recovery or not win32gui.IsWindowVisible(recovery),'recovery must not open unexpectedly'
                assert inspector.click(hud(),'恢复'),hud_text()
                recovery=await until(lambda:own_window(child.pid,'上次结果未知'),message='missing image recovery dialog')
                await until(lambda:win32gui.IsWindowVisible(recovery))
                assert await target.locator('#prompt-textarea').input_value()==''
                assert await phone.locator('#text').input_value()==text
                await until(lambda:not win32gui.IsWindowVisible(hud()), message='HUD covers modal recovery controls')
                assert inspector.click(recovery,'图片已出现，继续文字'),inspector.text(recovery)
                await until(lambda:not win32gui.IsWindowVisible(recovery), message='recovery confirmation click did not close the dialog')
                expected=text+'\n\n图1：手动确认图片'
                await completed(expected)
                assert len(await target.evaluate('window.imageRecords'))==1
                assert len(await target.evaluate('window.pasteRecords'))==2
                cases.append({'name':'unknown_attachment_user_confirms_then_text_only_once','passed':True})
                await target.evaluate('window.hideImageAccessibility=false')

                # 自动定位：当前窗口只有一个明确Composer时，定位后不擅自粘贴。
                result['stage']='locate_composer_from_review'
                await target.locator('#prompt-textarea').fill('')
                await target.evaluate("document.getElementById('editable').style.display='none';document.getElementById('other').focus()")
                await phone.fill('#text','定位但不自动发送')
                await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                await target.bring_to_front();await target.locator('#other').click();hotkey(expand=True)
                review=await until(lambda:own_window(child.pid,'当前图文'));await until(lambda:win32gui.IsWindowVisible(review))
                await until(lambda:not win32gui.IsWindowVisible(hud()),message='HUD covers expanded review controls')
                before_locate=await target.evaluate('window.pasteCount')
                assert inspector.click(review,'定位输入框'),inspector.text(review)
                await until(lambda:target.evaluate("document.activeElement.id==='prompt-textarea'"),message='unique composer was not focused')
                assert await target.evaluate('window.pasteCount')==before_locate,'locating must never paste'
                assert await phone.locator('#text').input_value()=='定位但不自动发送'
                assert await target.locator('#prompt-textarea').input_value()==''
                hotkey();await completed('定位但不自动发送')
                cases.append({'name':'locate_unique_composer_then_explicit_insert','passed':True})

                assert await target.evaluate('window.enterEvents')==0
                assert not errors,errors
                result['insertion_enter_events']=0
                # 确认发送与插入分离。测试设置仅写本脚本创建的隔离目录。
                result['stage']='phone_explicit_send'
                await phone.wait_for_selector('#submitPanel',state='visible')
                before_paste=await target.evaluate('window.pasteCount')
                before_clipboard=clipboard_text()
                await phone.click('#submitMessage');await phone.wait_for_selector('#confirmSend')
                await phone.click('#cancelSend')
                assert await target.evaluate('window.enterEvents')==0
                await phone.click('#submitMessage');await phone.click('#confirmSend')
                await until(lambda:target.evaluate('window.enterEvents===1'),message='confirmed phone Enter missing')
                assert await target.evaluate('window.submitKeys')==[{'ctrl':False,'target':'prompt-textarea'}]
                assert await target.evaluate('window.pasteCount')==before_paste
                assert clipboard_text()==before_clipboard
                await phone.reload();await phone.wait_for_function("document.querySelector('#transferStatus').textContent.includes('电脑已收到当前版本')")
                assert await target.evaluate('window.enterEvents')==1,'reconnect must never repeat sending'
                cases.append({'name':'phone_cancel_then_explicit_enter_once_without_repasting','passed':True})
                settings_path=data/'settings.json';settings=json.loads(settings_path.read_text(encoding='utf-8'))
                settings['phone_send_mode']='ctrl_enter'
                settings_path.write_text(json.dumps(settings),encoding='utf-8')
                await target.locator('#prompt-textarea').fill('')
                text='第二份用Ctrl+Enter发送'
                await ready(text);await phone.click('#sendBtn');await completed(text)
                assert await target.evaluate('window.enterEvents')==1,'insertion must not submit'
                await phone.wait_for_selector('#submitPanel',state='visible')
                before_paste=await target.evaluate('window.pasteCount')
                await phone.click('#submitMessage')
                assert 'Ctrl+Enter' in await phone.locator('#submitShortcut').inner_text()
                await phone.click('#confirmSend')
                await until(lambda:target.evaluate('window.enterEvents===2'),message='confirmed Ctrl+Enter missing')
                assert await target.evaluate('window.submitKeys')==[{'ctrl':False,'target':'prompt-textarea'},{'ctrl':True,'target':'prompt-textarea'}]
                assert await target.evaluate('window.pasteCount')==before_paste
                cases.append({'name':'phone_explicit_ctrl_enter_only_after_second_insertion','passed':True})
                result['explicit_send_enter_events']=2
                result['page_errors']=errors
                result['real_browser']=True
                await target.screenshot(path=str(report.with_suffix('.png')))
            except Exception:
                # 只收集合成测试输入，保留真实DOM/剪贴板事件与可见错误，不重放插入。
                try:
                    result['observed']=await target.evaluate('''() => ({
                        active:document.activeElement?.id,
                        inputs:[...document.querySelectorAll('textarea,[contenteditable]')].map(e=>({
                            id:e.id,value:e.value,text:e.textContent,innerText:e.innerText,html:e.innerHTML})),
                        pastes:window.pasteRecords,enterEvents:window.enterEvents,title:document.title
                    })''')
                    result['phone_text']=await phone.locator('#text').input_value()
                    result['hud_text']=hud_text()
                    rw=own_window(child.pid,'上次结果未知')
                    result['recovery_visible']=bool(rw and win32gui.IsWindowVisible(rw))
                    result['recovery_text']=inspector.text(rw) if rw else ''
                    await target.screenshot(path=str(report.with_suffix('.png')))
                except Exception as evidence_error:
                    result['evidence_error_type']=type(evidence_error).__name__
                raise
            finally:
                await phone_browser.close();await browser.close()
    finally:await runner.cleanup()


async def _matches(page,selector,expected):
    # innerText 是渲染后的文本，会合并普通CSS下的连续空格。
    # 检查DOM实际内容，同时completed另查原始paste事件文本，不放宽空格要求。
    if selector=='#editable':return await page.locator(selector).text_content()==expected
    return await page.locator(selector).input_value()==expected


async def _phone_empty(page):return await page.locator('#text').input_value()==''


def verify(exe,report):
    if sys.platform!='win32' or os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('Only disposable Windows Actions runners are supported')
    exe=exe.resolve(strict=True);report=report.resolve();report.parent.mkdir(parents=True,exist_ok=True)
    result={'passed':False,'test':'frozen-production-phone-browser-stability','cursor_tested':False,
            'android_ime_tested':False,'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='dt-browser-stability-') as temp:
        data=Path(temp)/'data';data.mkdir()
        (data/'settings.json').write_text(json.dumps({'phone_send_enabled':True,'phone_send_mode':'enter'}),encoding='utf-8')
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
            fixture_log=Path(temp)/'clipboard-holder.log'
            if fixture_log.is_file():shutil.copyfile(fixture_log,logs/fixture_log.name)
            report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('exe',type=Path);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();raise SystemExit(verify(a.exe,a.report))
