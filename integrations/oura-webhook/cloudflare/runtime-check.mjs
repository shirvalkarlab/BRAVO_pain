// Local workerd/SQLite acceptance using synthetic values only. No remote access.
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';

const base=process.env.LOCAL_WORKER_URL || 'http://127.0.0.1:8789';
const url=new URL(base);
if(url.hostname!=='127.0.0.1' || url.protocol!=='http:')throw Error('This test is restricted to local loopback HTTP.');
const user='11111111-1111-4111-8111-111111111111',secret='s'.repeat(32),read='r'.repeat(32),verify='v'.repeat(32);
const now=Math.floor(Date.now()/1000), iso=seconds=>new Date(seconds*1000).toISOString();
async function call(path,options={}) {
  const response=await fetch(base+path,options);
  assert.equal(response.headers.get('Cache-Control'),'no-store');
  return {status:response.status,body:await response.json()};
}
const status=()=>call('/status',{headers:{Authorization:'Bearer '+read}});
const event=(changes={})=>({user_id:user,event_type:'update',data_type:'sleep',object_id:'synthetic-id',event_time:iso(now-30),...changes});
async function post(changes={},timestamp=now,tamper=false) {
  const body=JSON.stringify(event(changes));
  const signature=createHmac('sha256',secret).update(String(timestamp)+body).digest('hex').toUpperCase();
  return call('/oura-webhook',{method:'POST',body:tamper?body+' ':body,
    headers:{'Content-Type':'application/json','x-oura-timestamp':String(timestamp),'x-oura-signature':signature}});
}
{
  assert.equal((await call('/status')).status,401);
  assert.equal((await status()).body.latest_notification,null);
  assert.deepEqual((await call('/oura-webhook?verification_token='+verify+'&challenge=local-only')).body,{challenge:'local-only'});
  assert.equal((await post({},now,true)).status,401);
  assert.equal((await post({user_id:'22222222-2222-4222-8222-222222222222'})).status,403);
  assert.equal((await post({},now-3901)).status,401);
  assert.deepEqual((await post()).body,{accepted:true,duplicate:false});
  const first=(await status()).body;
  assert.equal(first.latest_notification.event_time,iso(now-30));
  assert.equal(first.source,'oura_webhook');assert.equal(first.user_id,user);
  assert.deepEqual((await post({},now+1)).body,{accepted:true,duplicate:true});
  assert.equal((await status()).body.last_received_at,first.last_received_at);
  assert.equal((await post({object_id:'older',event_time:iso(now-600)})).status,200);
  assert.equal((await status()).body.latest_notification.event_time,iso(now-30));
  assert.equal((await post({event_type:'delete',event_time:iso(now-1)})).status,200);
  assert.equal((await status()).body.latest_notification.event_type,'delete');
  assert.equal((await post({event_time:iso(now+120)})).status,400);
  console.log('PASS: real local workerd + SQLite Durable Object: challenge/auth, exact-body HMAC, user binding, replay/future rejection, signed notification/status, deduplication, ordering and delete semantics. No remote service contacted.');
}
