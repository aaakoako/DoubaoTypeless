"""Real production phone page: clear is durable, recoverable and rejects stale work."""
import asyncio
from tests.test_v3_editor_transactions import product, photo, editing, synced
from tests.test_v3_frontend_prod import READ_DRAFT


def test_clear_mixed_draft_and_restore_from_recent(tmp_path):
    async def run():
        async with product(tmp_path,touch=True) as (page,app,_):
            await page.fill('#text','清空前的正文')
            for _ in range(2):
                await page.set_input_files('#file',photo());await editing(page)
                await page.click('#done');await page.wait_for_selector('#editor.show',state='hidden');await synced(page)
            before=await page.evaluate(READ_DRAFT)
            await page.click('#clearDraft');await page.wait_for_function("document.querySelector('#text').value==='' && !document.querySelector('.page').inert")
            await synced(page)
            after=await page.evaluate(READ_DRAFT)
            assert after['text']=='' and after['assets']==[] and after['epoch']!=before['epoch']
            assert after['generation']==before['generation']+1
            assert app.draft.text=='' and app.draft.assets==[]
            await page.reload();await synced(page)
            assert await page.locator('#text').input_value()==''
            await page.click('#historyBtn');await page.get_by_role('button',name='恢复手机上次图文（可离线）').click()
            await page.get_by_role('button',name='保留当前，恢复图文').click()
            await page.wait_for_function("document.querySelector('#text').value==='清空前的正文'");await synced(page)
            assert await page.locator('#text').input_value()=='清空前的正文'
            assert await page.locator('.attach-card').count()==2
    asyncio.run(run())


def test_clear_offline_reconnect_does_not_resurrect_old_draft(tmp_path):
    async def run():
        async with product(tmp_path) as (page,app,_):
            await page.fill('#text','旧稿');await synced(page)
            await page.context.set_offline(True)
            await page.wait_for_function("!document.querySelector('#clearDraft').disabled")
            await page.click('#clearDraft');await page.wait_for_function("document.querySelector('#text').value===''")
            await page.fill('#text','断线期间的新稿')
            await page.context.set_offline(False);await synced(page)
            assert app.draft.text=='断线期间的新稿'
            await page.reload();await synced(page)
            assert await page.locator('#text').input_value()=='断线期间的新稿'
    asyncio.run(run())


def test_clear_storage_failure_preserves_original_and_allows_retry(tmp_path):
    async def run():
        async with product(tmp_path) as (page,app,_):
            await page.fill('#text','不能丢');await synced(page)
            await page.evaluate("() => {window.realPut=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(){throw new DOMException('quota','QuotaExceededError')};}")
            await page.click('#clearDraft')
            await page.wait_for_function("!document.querySelector('.page').inert")
            assert await page.locator('#text').input_value()=='不能丢'
            assert (await page.evaluate(READ_DRAFT))['text']=='不能丢'
            await page.evaluate('() => {IDBObjectStore.prototype.put=window.realPut;}')
            await page.click('#clearDraft');await page.wait_for_function("document.querySelector('#text').value===''");await synced(page)
            assert app.draft.text==''
    asyncio.run(run())


def test_clear_invalidates_delayed_photo_decode(tmp_path):
    async def run():
        async with product(tmp_path) as (page,app,_):
            await page.fill('#text','等待图片');await synced(page)
            await page.evaluate("() => {window.realDecode=HTMLImageElement.prototype.decode;HTMLImageElement.prototype.decode=function(){window.decoding=true;return new Promise(r=>window.releaseDecode=()=>window.realDecode.call(this).then(r))};}")
            await page.set_input_files('#file',photo());await page.wait_for_function('window.decoding')
            await page.click('#clearDraft');await page.wait_for_function("document.querySelector('#text').value===''")
            await page.evaluate('window.releaseDecode()');await synced(page)
            await page.fill('#text','下一段');await synced(page)
            assert await page.locator('.attach-card').count()==0 and app.draft.assets==[]
            assert await page.locator('#editor').is_hidden()
    asyncio.run(run())


def test_clear_cancels_pending_insert_nonce_without_dispatch(tmp_path):
    async def run():
        async with product(tmp_path) as (page,app,_):
            started=asyncio.Event();release=asyncio.Event();intents=[]
            page.on('websocket',lambda ws:ws.on('framesent',lambda payload:intents.append(payload)))
            await page.reload();await synced(page)
            async def nonce(route):
                started.set();await release.wait();await route.continue_()
            await page.route('**/v3/nonce',nonce)
            await page.fill('#text','不能在清空后发出');await synced(page)
            await page.click('#sendBtn');await asyncio.wait_for(started.wait(),5)
            await page.click('#clearDraft');await page.wait_for_function("document.querySelector('#text').value===''")
            release.set();await page.fill('#text','现在的新稿');await synced(page)
            assert app.draft.text=='现在的新稿'
            assert not any('insert.intent' in p for p in intents)
            assert not await page.locator('#sendBtn').is_disabled()
    asyncio.run(run())


def test_old_receipt_cannot_clear_new_text_after_manual_clear(tmp_path):
    async def run():
        async with product(tmp_path) as (page,app,_):
            from doubao_typeless.core.bundle import freeze_bundle
            await page.fill('#text','旧稿');await synced(page)
            event=app._phone_rotate_event(freeze_bundle(app.draft,bundle_id='old'),True,'UNKNOWN')
            event['progress']={'message':'旧操作的文字粘贴已发出'}
            await page.click('#clearDraft');await page.wait_for_function("document.querySelector('#text').value===''")
            await page.fill('#text','清空后新写的');await synced(page)
            await app.bridge.publish_phone_event(event)
            await page.wait_for_function("document.querySelector('#deliveryStatus').textContent.startsWith('上次插入：')")
            assert await page.locator('#text').input_value()=='清空后新写的'
    asyncio.run(run())


def test_clear_remains_reachable_in_keyboard_sized_viewport(tmp_path):
    async def run():
        async with product(tmp_path,touch=True) as (page,app,_):
            await page.set_viewport_size({'width':390,'height':430})
            await page.fill('#text','键盘展开时清空');await synced(page)
            await page.locator('#clearDraft').tap()
            await page.wait_for_function("document.querySelector('#text').value===''")
            await page.fill('#text','下一段');await synced(page)
            await page.locator('#sendBtn').scroll_into_view_if_needed()
            box=await page.locator('#sendBtn').bounding_box()
            assert box['y']>=0 and box['y']+box['height']<=430
    asyncio.run(run())


def test_clear_failure_during_capture_unlocks_retry_and_ignores_late_result(tmp_path):
    async def run():
        import json
        async with product(tmp_path) as (page,app,_):
            replies=[];capture_requests=[]
            def proxy(route):
                server=route.connect_to_server()
                def inbound(raw):
                    msg=json.loads(raw)
                    if msg.get('type')=='capture.result':replies.append((route,raw))
                    else:route.send(raw)
                def outbound(raw):
                    msg=json.loads(raw)
                    if msg.get('type')=='capture.request':capture_requests.append(msg)
                    server.send(raw)
                server.on_message(inbound);route.on_message(outbound)
            await page.route_web_socket('**/ws',proxy)
            await page.reload();await synced(page)
            await page.fill('#text','存储失败仍保留');await synced(page)
            await page.click('#captureBtn')
            for _ in range(100):
                if replies:break
                await asyncio.sleep(.01)
            assert replies and await page.locator('#captureBtn').is_disabled()
            await page.evaluate("() => {window.realPut=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(){throw new DOMException('quota','QuotaExceededError')};}")
            await page.click('#clearDraft');await page.wait_for_function("!document.querySelector('.page').inert")
            assert await page.locator('#text').input_value()=='存储失败仍保留'
            assert not await page.locator('#captureBtn').is_disabled()
            route,raw=replies[0];route.send(raw)
            await page.evaluate('() => {IDBObjectStore.prototype.put=window.realPut;}')
            await page.click('#captureBtn')
            for _ in range(100):
                if len(capture_requests)==2:break
                await asyncio.sleep(.01)
            assert len(capture_requests)==2
    asyncio.run(run())


def test_clear_aborts_upload_queue_and_reload_stays_empty(tmp_path):
    async def run():
        async with product(tmp_path) as (page,app,_):
            release=asyncio.Event();started=asyncio.Event();requests=[]
            async def upload(route):
                requests.append(route.request.url);started.set()
                await release.wait()
                try:await route.abort()
                except Exception:pass
            await page.context.set_offline(True)
            for _ in range(2):
                await page.set_input_files('#file',photo());await editing(page)
                await page.click('#done');await page.wait_for_selector('#editor.show',state='hidden')
            await page.route('**/v3/assets/init',upload)
            await page.context.set_offline(False)
            try:
                await asyncio.wait_for(started.wait(),5)
                await page.click('#clearDraft');await page.wait_for_function("document.querySelector('#text').value==='' && document.querySelectorAll('.attach-card').length===0 && !document.querySelector('.page').inert")
                await synced(page)
            finally:release.set()
            assert len(requests)==1,'clearing must not start the next upload'
            await page.reload();await synced(page)
            saved=await page.evaluate(READ_DRAFT)
            assert saved['assets']==[] and saved['text']==''
            await page.click('#historyBtn')
            await page.wait_for_function("document.querySelector('#sheetCard').textContent.includes('手机上次 · 2 图')")
    asyncio.run(run())
