"""真实Chromium的IndexedDB持久化/失败事务；不是Android真机声明。"""
from pathlib import Path
import functools
import http.server
import subprocess
import threading
import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope="module")
def storage_site(tmp_path_factory):
    root=tmp_path_factory.mktemp("idb-site")
    (root/"index.html").write_text("<!doctype html><title>storage-test</title>")
    out=root/"storage.js"
    code="import {buildSync} from 'esbuild';buildSync({entryPoints:['src/storage/drafts.ts'],bundle:true,format:'iife',globalName:'DTStore',outfile:process.argv[1]})"
    subprocess.run(["node","--input-type=module","-e",code,str(out)],cwd=ROOT/"web",check=True)
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),functools.partial(Handler,directory=str(root)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown();server.server_close();thread.join()

@pytest.fixture
def storage_page(storage_site):
    playwright=pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context();page=context.new_page()
        page.goto(storage_site)
        page.add_script_tag(url=storage_site+"/storage.js")
        page.evaluate('window.events=[];window.repo=new DTStore.DraftRepository(s=>events.push(s))')
        yield page,context,storage_site
        browser.close()


def test_large_draft_survives_new_page(storage_page):
    page,context,url=storage_page
    page.evaluate('''async()=>{repo.save({schema:1,text:"phone draft",revision:4,draft_id:"d",epoch:"e",saved_at:1,
      assets:[{id:"a",source:"data:image/png;base64,"+"A".repeat(7*1024*1024),scene:"{saved}"}]});await repo.flush()}''')
    page.close();next_page=context.new_page();next_page.goto(url);next_page.add_script_tag(url=url+"/storage.js")
    result=next_page.evaluate('''async()=>{let d=await new DTStore.DraftRepository().load();return {text:d.text,size:d.assets[0].source.length,scene:d.assets[0].scene}}''')
    assert result=={"text":"phone draft","size":7*1024*1024+22,"scene":"{saved}"}


def test_queued_writes_keep_latest_revision(storage_page):
    page,_,_=storage_page
    result=page.evaluate('''async()=>{for(let i=1;i<=12;i++)repo.save({schema:1,text:"draft"+i,revision:i,draft_id:"d",epoch:"e",assets:[],saved_at:i});await repo.flush();return {saved:await repo.load(),events}}''')
    assert result["saved"]["revision"]==12 and result["events"][-1]=="saved"


def test_storage_failure_keeps_last_committed_draft(storage_page):
    page,_,_=storage_page
    result=page.evaluate('''async()=>{let d={schema:1,text:"old",revision:1,draft_id:"d",epoch:"e",assets:[],saved_at:1};
      repo.save(d);await repo.flush();let old=IDBObjectStore.prototype.put;
      IDBObjectStore.prototype.put=function(){throw new DOMException("quota","QuotaExceededError")};
      repo.save({...d,text:"new",revision:2});let failed=false;try{await repo.flush()}catch{failed=true}
      IDBObjectStore.prototype.put=old;return {failed,still:(await repo.load()).text,events}}''')
    assert result["failed"] and result["still"]=="old" and result["events"][-1]=="unavailable"
