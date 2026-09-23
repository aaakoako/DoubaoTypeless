"""Offline HTML prototype behavior checks; never native input or real networking.
Requires playwright and an installed Chromium. Set CHROMIUM_PATH as needed.
This script loads trusted local HTML using page.set_content (no server required).
"""
from __future__ import annotations
import os, json, base64, io
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'prototype/index.html').read_text(encoding='utf-8')
results=[]

def record(name, fn):
    try: fn(); results.append({'name':name,'status':'PASS'})
    except Exception as e: results.append({'name':name,'status':'FAIL','detail':str(e)[:1200]})

def ok(v,message='assertion failed'):
    if not v: raise AssertionError(message)

def main():
 with sync_playwright() as w:
    browser=w.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
    p=browser.new_page(viewport={'width':1440,'height':1150})
    p.set_default_timeout(2500)
    errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
    p.set_content(HTML,wait_until='load')
    def scene(s):p.evaluate('(s)=>demo.scene(s)',s);p.wait_for_timeout(100)
    def ev(s):return p.evaluate(s)
    def checks(*args):
        for item in args:ok(item)
    def stroke(tool='pen'):
        p.evaluate('(x)=>demo.setTool(x)',tool)
        box=p.locator('#canvas').bounding_box();x=box['x']+box['width']*.30;y=box['y']+box['height']*.45
        p.mouse.move(x,y);p.mouse.down();p.mouse.move(x+80,y+55,steps=8);p.mouse.up()
    def done():p.click('#doneBtn');p.wait_for_timeout(50)
    def withscene(name,fn):scene(name);fn()
    record('idle has no popup and no insertion',lambda:checks(not ev("document.getElementById('hud').classList.contains('show')"),p.locator('#sendBtn').is_disabled(),ev('demo.state.attempts.length')==0))
    record('text input is mirrored; popup does not move DOM focus',lambda: (p.locator('#textInput').fill('  Opus 和 Image2\n'),checks(ev('demo.state.text')=='  Opus 和 Image2\n',ev("document.activeElement.id")=='textInput',ev("document.getElementById('hud').classList.contains('show')"))))
    record('idle timer hides popup without clearing draft',lambda:(p.wait_for_timeout(6200),checks(not ev("document.getElementById('hud').classList.contains('show')"),ev('demo.state.text')=='  Opus 和 Image2\n')))
    record('text-only insert preserves whitespace and never sends',lambda:(ev('demo.insert()'),checks(ev('demo.getTarget().text')=='  Opus 和 Image2\n',ev('demo.state.lastResult')=='confirmed',ev('demo.state.attempts[0].steps')==['text_sent','text_observed'])))
    record('success popup disappears, immutable last text remains',lambda:(p.wait_for_timeout(1000),checks(not ev("document.getElementById('hud').classList.contains('show')"),ev('demo.state.last.text')=='  Opus 和 Image2\n')))
    record('screenshot sample opens shared editor and compact HUD',lambda:withscene('markup',lambda:checks(p.locator('#editor').is_visible(),ev("document.getElementById('hud').classList.contains('compact')"),ev('demo.state.editor.ops.length')==3)))
    record('pointer stroke creates one object',lambda:(stroke(),ok(ev('demo.state.editor.ops.length')==4)))
    record('undo and redo restore stroke',lambda:(p.click('#undoBtn'),ok(ev('demo.state.editor.ops.length')==3),p.click('#redoBtn'),ok(ev('demo.state.editor.ops.length')==4)))
    record('crop changes actual PNG dimensions and undo restores bounds',lambda:crop_case(p,stroke))
    record('caption sheet keeps text without leaving editor',lambda:(p.click('#captionBtn'),p.locator('#captionInput').fill('图1①缩短，图2是草图'),p.click('#saveCaption'),checks(ev('demo.state.text')=='图1①缩短，图2是草图',p.locator('#editor').is_visible())))
    record('cannot insert unfinished editor',lambda:(ev('demo.insert()'),ok(ev('demo.state.attempts.length')==0)))
    record('done returns image and text to single composer',lambda:(done(),checks(p.locator('#composer').is_visible(),ev('demo.state.assets.length')==1,ev('demo.state.text')=='图1①缩短，图2是草图',not ev("document.getElementById('hud').classList.contains('compact')"))))
    record('wrong target creates zero paste steps and preserves bundle',lambda:(p.select_option('#targetMode','wrong'),ev('demo.insert()'),checks(ev('demo.getTarget().images')==0,ev('demo.state.lastResult')=='no_steps',ev('demo.state.last.assets.length')==1,ev('demo.state.attempts[0].steps.length')==0)))
    record('opening history never retries implicitly',lambda:(p.click('#historyBtn'),checks(p.locator('#shade').is_visible(),ev('demo.state.attempts.length')==1),p.click('#cancelRetry')))
    record('refocus and hotkey-style recall reuses exact images plus text',lambda:(p.select_option('#targetMode','good'),ev('demo.recall()'),p.wait_for_timeout(600),checks(ev('demo.getTarget().images')==1,ev('demo.getTarget().text')=='图1①缩短，图2是草图',ev('demo.state.attempts[1].steps')==['image_1_sent','image_1_observed','text_sent','text_observed'])))
    record('partial image success stops before text',lambda:(scene('markup'),done(),p.select_option('#targetMode','partial'),ev('demo.insert()'),checks(ev('demo.getTarget().images')==1,ev('demo.getTarget().text')=='',ev('demo.state.lastResult')=='partial')))
    record('text-only retry does not duplicate image',lambda:(p.select_option('#targetMode','good'),ev('demo.recall()'),p.click('#retryText'),p.wait_for_timeout(400),checks(ev('demo.getTarget().images')==1,ev('demo.getTarget().text')!='')))
    record('unknown image receipt never advances text',lambda:(scene('markup'),done(),p.select_option('#targetMode','unknown'),ev('demo.insert()'),checks(ev('demo.state.lastResult')=='unknown',ev('demo.getTarget().text')=='',ev('demo.state.attempts[0].steps')==['image_1_sent'])))
    record('offline click and reconnect never replay insertion',lambda:(scene('text'),p.click('#disconnect'),ev('demo.insert()'),checks(ev('demo.state.attempts.length')==0,ev('demo.state.text')!=''),p.click('#disconnect'),ok(ev('demo.state.attempts.length')==0)))
    record('changing text mid-attempt preserves new draft',lambda:concurrent_case(p))
    record('focus loss during text delay cancels injection',lambda:focus_case(p))
    record('whiteboard has editable primitives, no screenshot source',lambda:withscene('whiteboard',lambda:checks(ev('demo.state.editor.source') is None,ev('demo.state.editor.ops.length')>4)))
    record('whiteboard zoom and fit keep object coordinates',lambda:(ev("window.beforeOps=JSON.stringify(demo.state.editor.ops)"),p.click('#zoomIn'),ok(ev('demo.state.zoom')>1),p.click('#fitCanvas'),checks(ev('demo.state.zoom')==1,ev('JSON.stringify(demo.state.editor.ops)===window.beforeOps'))))
    record('whiteboard wireframe button is drawable objects',lambda:(p.click('#moreTools'),ev('window.beforeCount=demo.state.editor.ops.length'),p.click('#addWireframe'),ok(ev('demo.state.editor.ops.length===window.beforeCount+2'))))
    record('solid mask export has opaque replacement pixels',lambda:mask_case(p))
    record('empty whiteboard cannot become output',lambda:(scene('idle'),p.click('#boardBtn'),p.click('#doneBtn'),checks(p.locator('#editor').is_visible(),ev('demo.state.attempts.length')==0)))
    record('local PNG upload decodes and enters editor',lambda:(scene('idle'),p.locator('#fileInput').set_input_files(str(ROOT/'fixtures/sample.png')),p.wait_for_timeout(150),checks(ev('demo.state.assets.length')==1,ev('demo.state.editor.w')==2,p.locator('#editor').is_visible())))
    record('image count capped at six in prototype',lambda:(scene('idle'),ev("for(let i=0;i<7;i++)addAsset(createAsset('图片',blankImage(2,2),2,2))"),ok(ev('demo.state.assets.length')==6)))
    record('settings are on-demand and do not insert',lambda:(scene('idle'),p.click('#settingsBtn'),checks(p.locator('#shade').is_visible(),ev('demo.state.attempts.length')==0,not ev("document.getElementById('hud').classList.contains('show')")),ev('closeSheet()')))
    record('dark theme toggles without draft change',lambda:(scene('text'),ev('window.before=demo.state.text'),p.click('#themeToggle'),checks(ev("document.body.classList.contains('dark')"),ev('window.before===demo.state.text'))))
    for width in (360,390,430):
        def responsive(width=width):
            p.set_viewport_size({'width':width,'height':850});scene('text')
            ok(ev('document.documentElement.scrollWidth')<=width,'horizontal overflow')
            rect=p.locator('#phone').bounding_box();ok(rect['width']<=width)
            scene('markup');ok(p.locator('#canvas').bounding_box()['height']>180)
        record(f'responsive layout {width}px (not real IME)',responsive)
    p.set_viewport_size({'width':1440,'height':1150})
    record('no runtime JavaScript exceptions',lambda:ok(not errors,str(errors)))
    browser.close()
 report={'kind':'offline_browser_prototype_checks','environment':{'browser':'Chromium / local set_content','native_windows':False,'real_phone':False,'network':False},'passed':sum(x['status']=='PASS' for x in results),'total':len(results),'results':results,'product_acceptance':'96 cases NOT_RUN'}
 (ROOT/'evidence/prototype-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(f"Prototype checks: {report['passed']}/{report['total']}")
 for r in results:
    if r['status']=='FAIL':print(r['name'],r['detail'])
 if report['passed']!=report['total']:raise SystemExit(1)

def crop_case(p,stroke):
    stroke('crop');p.click('#cropApply')
    crop=p.evaluate('demo.state.editor.crop');ok(crop['w']<1000 and crop['h']<640)
    data=p.evaluate('demo.rendered(demo.state.editor)');im=Image.open(io.BytesIO(base64.b64decode(data.split(',')[1])))
    ok(im.width==round(crop['w']) and im.height==round(crop['h']))
    p.click('#undoBtn');ok(p.evaluate('demo.state.editor.crop.w')==1000)

def concurrent_case(p):
    p.evaluate("demo.scene('text');window.oldText=demo.state.text;demo.insert();demo.state.text='下一轮文字';demo.state.revision++;demo.update();")
    p.wait_for_timeout(350)
    ok(p.evaluate('demo.state.text')=='下一轮文字')
    ok(p.evaluate('demo.getTarget().text===window.oldText'))

def focus_case(p):
    p.evaluate("demo.scene('text');demo.insert();document.getElementById('targetMode').value='wrong';")
    p.wait_for_timeout(350)
    ok(p.evaluate('demo.getTarget().text')=='')
    ok(p.evaluate('demo.state.lastResult')=='no_steps')

def mask_case(p):
    p.evaluate("demo.state.editor.ops=[{type:'mask',x:0,y:0,x2:100,y2:100}];demo.state.editor.crop={x:0,y:0,w:1600,h:1000}")
    raw=p.evaluate('demo.rendered(demo.state.editor)');im=Image.open(io.BytesIO(base64.b64decode(raw.split(',')[1])))
    ok(im.convert('RGBA').getpixel((40,40))==(20,20,20,255))

if __name__=='__main__':main()
