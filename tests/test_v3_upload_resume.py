"""实际客户端上传函数对真实HTTP服务断点续传；不模拟成手机触控或系统投递。"""
from __future__ import annotations
import asyncio, io, json, os, subprocess, random
from pathlib import Path
from PIL import Image
from aiohttp import web
from doubao_typeless.app import V3App

ROOT = Path(__file__).resolve().parents[1]


def test_actual_upload_resumes_only_missing_chunks_after_disconnect(tmp_path):
    module = tmp_path/'upload.mjs'
    code = "import{buildSync}from'esbuild';buildSync({entryPoints:['src/transport/upload.ts'],bundle:true,format:'esm',platform:'node',outfile:process.argv[1]});"
    subprocess.run(['node','--input-type=module','-e',code,str(module)],cwd=ROOT/'web',check=True,capture_output=True)
    rng = random.Random(42)
    image=Image.frombytes('RGB',(64,64),rng.randbytes(64*64*3));out=io.BytesIO();image.save(out,format='PNG')
    payload=tmp_path/'source.png';payload.write_bytes(out.getvalue())
    driver=tmp_path/'resume.mjs'
    driver.write_text('''import {uploadPng} from './upload.mjs';
import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';
const cfg=JSON.parse(process.argv[2]), blob=new Blob([readFileSync(cfg.file)],{type:'image/png'});
const original=globalThis.fetch;const controller=new AbortController();let ticket;let mode='first';
let initCount=0,chunkZero=0,temporaryFailure=false;const progress=[];
globalThis.fetch=async (url,options)=>{
 const full=new URL(url,cfg.base), path=full.pathname;
 if(path.endsWith('/init'))initCount++;
 if(path.endsWith('/chunks/0'))chunkZero++;
 if(mode==='first'&&path.endsWith('/chunks/1')){controller.abort();throw new DOMException('interrupted','AbortError');}
 if(mode==='resume'&&path.endsWith('/chunks/1')&&!temporaryFailure){temporaryFailure=true;throw new TypeError('temporary network');}
 return original(full,options);
};
const opts={signal:controller.signal,checkpoint:t=>{ticket=t},progress:(sent,total)=>progress.push([sent,total])};
await assert.rejects(uploadPng(blob,cfg.headers,64,64,'markup',opts));
assert.ok(ticket);assert.equal(initCount,1);assert.equal(chunkZero,1);
mode='resume';const meta=await uploadPng(blob,cfg.headers,64,64,'markup',{ticket,progress:(sent,total)=>progress.push([sent,total])});
assert.equal(initCount,1);assert.equal(chunkZero,1);assert.ok(temporaryFailure);
assert.equal(meta.bytes,blob.size);assert.equal(progress.at(-1)[0],blob.size);
console.log(JSON.stringify({asset_id:meta.asset_id,hash:meta.sha256,initCount,chunkZero,temporaryFailure}));
''',encoding='utf-8')
    async def exercise():
        app=V3App(data_dir=tmp_path/'pc',port=0);app.uploads.chunk_size=1024
        session=app.auth.complete_pairing(app.auth.new_pairing_challenge(),allow_insert=False,allow_capture=False)
        runner=web.AppRunner(app.bridge.make_app());await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
        base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
        try:
            child=await asyncio.create_subprocess_exec('node',str(driver),json.dumps({'base':base,'file':str(payload),
                'headers':{'X-DT-Session':session.session_id,'X-DT-Token':session.token}}),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            output,error=await asyncio.wait_for(child.communicate(),15)
            assert child.returncode==0,error.decode()
            result=json.loads(output);assert app.store.get(result['asset_id'])==payload.read_bytes()
            assert app.store.meta(result['asset_id'])['role']=='markup'
        finally:
            await runner.cleanup();await app.stop()
    asyncio.run(exercise())
