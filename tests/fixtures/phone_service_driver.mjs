// 正式手机消息/回执模块 + 真实本地 HTTP/WS。没有浏览器、输入法或系统按键。
import assert from 'node:assert/strict';

import {applyReady, applyRotated, buildDraftUpdate} from '../../web/src/sync.js';
let input=''; for await (const chunk of process.stdin) input += chunk;
const cfg=JSON.parse(input);
const state = {text:'', assets:[], revision:0, draft_id:'', epoch:'', conflict:null};
const ws = new WebSocket(cfg.base.replace('http:', 'ws:') + '/ws');
const messages = [], waiting = [];
ws.addEventListener('message', ev => {
  const msg = JSON.parse(ev.data);
  const ix = waiting.findIndex(w => w.test(msg));
  if (ix >= 0) waiting.splice(ix,1)[0].resolve(msg); else messages.push(msg);
});
function receive(test) {
  const index = messages.findIndex(test);
  if (index >= 0) return Promise.resolve(messages.splice(index,1)[0]);
  return new Promise((resolve,reject) => {
    const timer = setTimeout(() => reject(new Error('message timeout')), 4000);
    waiting.push({test, resolve:msg => {clearTimeout(timer); resolve(msg);}});
  });
}
await new Promise((resolve,reject) => {ws.addEventListener('open',resolve,{once:true}); ws.addEventListener('error',reject,{once:true});});
ws.send(JSON.stringify({type:'session.hello', ...cfg.session}));
assert.equal(applyReady(state, await receive(m => m.type === 'session.ready')), 'adopt');
const epochs = [];
for (const text of ['第一段：原文  不改空格\n', '第二段 Opus / Image2', '第三段：可以连续输入']) {
  state.text = text;
  const message = buildDraftUpdate(state);
  ws.send(JSON.stringify(message));
  const ack = await receive(m => m.type === 'draft.ack' && m.revision === state.revision);
  assert.equal(ack.durable,true);
  const response = await fetch(cfg.base + '/v3/nonce', {
    method:'POST', headers:{...cfg.headers, Origin:cfg.base, 'Content-Type':'application/json'}, body:JSON.stringify(cfg.session)
  });
  assert.equal(response.status,200);
  const {nonce} = await response.json();
  ws.send(JSON.stringify({...message, ...cfg.session, type:'insert.intent', nonce,
    intent_id:crypto.randomUUID(), trigger:'insert_current'}));
  const result = await receive(m => m.type === 'attempt.status');
  assert.equal(result.result, 'UNKNOWN'); // 真实外部接收未验证，不能写CONFIRMED。
  assert.equal(applyRotated(state, await receive(m => m.type === 'draft.rotated')), 'cleared');
  assert.equal(state.text,'');
  epochs.push(state.epoch);
}
assert.equal(new Set(epochs).size,3);
state.text='有图的下一段';
state.assets=[{id:'local-new',status:'editing',render_revision:1,caption:'待上传'}];
ws.send(JSON.stringify(buildDraftUpdate(state)));
const pending = await receive(m => m.type === 'draft.ack' && m.revision === state.revision);
assert.equal(pending.durable,true);
ws.close();
console.log(JSON.stringify({rounds:3, uniqueEpochs:epochs.length, pendingVersion:state.revision}));
