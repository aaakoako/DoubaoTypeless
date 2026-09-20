"""真实Chromium画布像素/指针组件测试；仅本地内联脚本，不访问网络页面。

这不是 Android 输入法、触控手感或手机→Composer 端到端验收。
"""
from __future__ import annotations
import io
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def canvas_bundle(tmp_path_factory):
    if not shutil.which('node') or not (ROOT/'web/node_modules/esbuild').exists():
        pytest.skip('canvas test needs npm ci and Node')
    out=tmp_path_factory.mktemp('canvas')/'canvas.js'
    code='''import {buildSync} from 'esbuild'; buildSync({entryPoints:['src/editor/canvas.ts'],bundle:true,format:'iife',globalName:'DTCanvas',outfile:process.argv[1]});'''
    subprocess.run(['node','--input-type=module','-e',code,str(out)],cwd=ROOT/'web',check=True,capture_output=True)
    return out.read_text()

@pytest.fixture
def canvas_page(canvas_bundle):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':430,'height':500},has_touch=True)
        page=context.new_page()
        page.set_content('<style>body{margin:0}#stage{width:400px;height:400px;touch-action:none}</style><div id="stage"></div>')
        page.add_script_tag(content=canvas_bundle)
        page.evaluate("window.editor = new DTCanvas.SharedEditor(document.querySelector('#stage'),128,128);editor.addBlankBoard(128,128)")
        yield page
        context.close();browser.close()


def pixels(page):
    raw=page.evaluate('async()=>Array.from(new Uint8Array(await (await editor.exportBlob()).arrayBuffer()))')
    return Image.open(io.BytesIO(bytes(raw))).convert('RGBA')


def test_real_pointer_first_stroke_undo_redo(canvas_page):
    page=canvas_page
    # source(128) centered at (136,136), transform is production fit().
    page.mouse.move(165,180);page.mouse.down();page.mouse.move(240,180,steps=8);page.mouse.up()
    assert page.evaluate('editor.layer.getChildren().length')==1
    drawn=pixels(page)
    page.evaluate('editor.undo()')
    assert page.evaluate('editor.layer.getChildren().length')==0
    assert pixels(page).tobytes()!=drawn.tobytes()
    page.evaluate('editor.redo()')
    assert pixels(page).tobytes()==drawn.tobytes()


def test_photo_reopen_requires_source_pixels_and_preserves_crop_mask(canvas_page):
    page=canvas_page
    page.evaluate('''async()=>{
      const c=document.createElement('canvas');c.width=128;c.height=128;
      const g=c.getContext('2d');g.fillStyle='#cc3311';g.fillRect(0,0,128,128);
      g.fillStyle='#1188bb';g.fillRect(64,0,64,128);window.source=c.toDataURL();
      await editor.loadImage(source,128,128);editor.addMask(20,20,32,32);
      editor.applyCrop({x:16,y:16,w:96,h:96});window.scene=editor.exportScene();
    }''')
    before=pixels(page)
    assert before.size==(96,96)
    assert before.getpixel((20,20))[:3]==(17,17,17)
    page.evaluate('''()=>{editor.destroy();document.querySelector('#stage').replaceChildren();
      window.editor=new DTCanvas.SharedEditor(document.querySelector('#stage'));
      editor.importScene(scene);
    }''')
    assert page.evaluate('async()=>{try{await editor.exportBlob();return false}catch{return true}}')
    page.evaluate('async()=>await editor.rebindSource(source)')
    assert pixels(page).tobytes()==before.tobytes()


def test_crop_is_clipped_to_real_source(canvas_page):
    page=canvas_page
    assert page.evaluate('editor.applyCrop({x:-100,y:-100,w:210,h:210})')
    assert page.evaluate('editor.crop')=={'x':0,'y':0,'w':110,'h':110}
    assert not page.evaluate('editor.applyCrop({x:120,y:120,w:90,h:90})')
    assert pixels(page).size==(110,110)


def test_two_finger_pan_and_zoom_do_not_add_stroke(canvas_page):
    page=canvas_page
    cdp=page.context.new_cdp_session(page)
    before=page.evaluate('({x:editor.stage.x(),y:editor.stage.y(),s:editor.stage.scaleX()})')
    cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':150,'y':200,'id':1},{'x':250,'y':200,'id':2}]})
    cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':170,'y':230,'id':1},{'x':270,'y':230,'id':2}]})
    cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    after=page.evaluate('({x:editor.stage.x(),y:editor.stage.y(),s:editor.stage.scaleX()})')
    assert after['x']==pytest.approx(before['x']+20)
    assert after['y']==pytest.approx(before['y']+30)
    assert after['s']==pytest.approx(before['s'])
    assert page.evaluate('editor.layer.getChildren().length')==0
    assert page.evaluate('editor.undoDepth')==0


def test_destroy_detaches_editor_and_disallows_export(canvas_page):
    page=canvas_page
    page.evaluate('editor.destroy();editor.destroy()')
    assert page.evaluate("!document.querySelector('#stage').__dtEditor")
    assert page.evaluate('async()=>{try{await editor.exportBlob();return false}catch{return true}}')
