import {registerHooks} from 'node:module';
import {DatabaseSync} from 'node:sqlite';
import {test,beforeEach,afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';

// Only the Cloudflare base class is stubbed. Crypto, HTTP and SQLite are real.
registerHooks({resolve(specifier,context,next) {
  if(specifier==='cloudflare:workers')return {url:'data:text/javascript,export class DurableObject {}',shortCircuit:true};
  return next(specifier,context);
}});
const {route,NotificationStore,default:worker}=await import('./worker.mjs');
const user='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222';
const NOW=1788627870,iso=seconds=>new Date(seconds*1000).toISOString();
let env,db,store;
beforeEach(()=>{
  env={ACTIVATION_APPROVED:'true',OURA_USER_ID:user,OURA_CLIENT_SECRET:'s'.repeat(32),OURA_VERIFICATION_TOKEN:'v'.repeat(32),OURA_READ_TOKEN:'r'.repeat(32)};
  db=new DatabaseSync(':memory:');
  const sql={exec(query,...params) {
    const statement=db.prepare(query);
    if(query.startsWith('SELECT'))return {toArray:()=>statement.all(...params)};
    const result=statement.run(...params);return {rowsWritten:Number(result.changes)};
  }};
  store=new NotificationStore({storage:{sql}},env);
});
afterEach(()=>db.close());
function event(changes={}) {return {user_id:user,event_type:'update',data_type:'sleep',object_id:'synthetic-id',event_time:iso(NOW-30),...changes};}
function request({method='POST',path='/oura-webhook',body=JSON.stringify(event()),timestamp=NOW,headers={}}={}) {
  const signature=createHmac('sha256',env.OURA_CLIENT_SECRET).update(String(timestamp)).update(body).digest('hex').toUpperCase();
  return new Request('https://review.invalid'+path,{method,...(method==='POST'?{body}:{}),
    headers:{'Content-Type':'application/json','x-oura-timestamp':String(timestamp),'x-oura-signature':signature,...headers}});
}
async function call(options={},now=NOW) {const response=await route(request(options),env,store,now);assert.equal(response.headers.get('Cache-Control'),'no-store');return {code:response.status,body:await response.json()};}
async function status() {return call({method:'GET',path:'/status',headers:{Authorization:'Bearer '+env.OURA_READ_TOKEN}});}

test('disabled/missing configuration fails closed without accessing storage',async()=>{
  env.ACTIVATION_APPROVED='false';assert.equal((await call()).code,503);
  env.ACTIVATION_APPROVED='true';env.OURA_USER_ID='invalid';assert.equal((await call()).code,503);
  env.OURA_USER_ID=user;env.OURA_READ_TOKEN=env.OURA_VERIFICATION_TOKEN;assert.equal((await call()).code,503);
  env.OURA_READ_TOKEN='short';assert.equal((await call()).code,503);
});
test('empty status is protected, does not prove no sync',async()=>{
  assert.equal((await status()).body.latest_notification,null);
  assert.equal((await call({method:'GET',path:'/status'})).code,401);
  assert.equal((await call({method:'GET',path:'/'})).code,404);
});
test('challenge requires exact token and single challenge, writes no state',async()=>{
  const path='/oura-webhook?verification_token='+env.OURA_VERIFICATION_TOKEN+'&challenge=abc';
  assert.deepEqual((await call({method:'GET',path})).body,{challenge:'abc'});
  for(const suffix of ['&challenge=duplicate','&extra=value'])assert.equal((await call({method:'GET',path:path+suffix})).code,401);
  assert.equal((await call({method:'GET',path:'/oura-webhook?verification_token=bad&challenge=a'})).code,401);
  assert.equal((await status()).body.latest_notification,null);
});
test('exact raw bytes signed correctly, changed whitespace fails',async()=>{
  const body=JSON.stringify(event(),null,2);assert.equal((await call({body})).code,200);
  const wrong=createHmac('sha256',env.OURA_CLIENT_SECRET).update(String(NOW)+JSON.stringify(event())).digest('hex');
  assert.equal((await call({body,headers:{'x-oura-signature':wrong}})).code,401);
  const result=(await status()).body;
  assert.equal(result.latest_notification.event_time,iso(NOW-30));assert.equal(result.latest_notification.received_at,iso(NOW));
});
test('dedupe survives object reconstruction, resending does not advance receipt',async()=>{
  assert.equal((await call()).body.duplicate,false);
  store=new NotificationStore({storage:{sql:store.sql}},env);
  assert.equal((await call({timestamp:NOW+120},NOW+120)).body.duplicate,true);
  assert.equal((await status()).body.last_received_at,iso(NOW));
});
test('out of order timestamps and delete notifications remain correctly labeled',async()=>{
  await call();await call({body:JSON.stringify(event({event_time:iso(NOW-600),object_id:'older'})),timestamp:NOW+10},NOW+10);
  assert.equal((await status()).body.latest_notification.event_time,iso(NOW-30));
  assert.equal((await status()).body.last_received_at,iso(NOW+10));
  await call({body:JSON.stringify(event({event_type:'delete',event_time:iso(NOW)}))});
  assert.equal((await status()).body.latest_notification.event_type,'delete');
});
test('expired/future/tampered signing metadata and invalid content types are rejected',async()=>{
  for(const timestamp of [NOW-3901,NOW+61,'bad',NOW*1000])assert.equal((await call({timestamp})).code,401);
  for(const signature of ['','f'.repeat(64),'g'.repeat(64)])assert.equal((await call({headers:{'x-oura-signature':signature}})).code,401);
  assert.equal((await call({headers:{'Content-Type':'text/plain'}})).code,415);
});
test('invalid JSON/schema, duplicate keys, future and impossible dates fail closed',async()=>{
  const bodies=['{bad}', '[]', '{}','null',JSON.stringify(event()).replace('"user_id":','"user_id":"duplicate","user_id":'),
    ...[{event_time:iso(NOW+61)},{event_time:'2026-02-30T00:00:00Z'},{event_time:'2026-09-05T00:00:00'},
       {event_time:iso(-1)},{event_type:'unknown'},{data_type:'other'},{object_id:'x y'},{object_id:1},{user_id:'invalid'},{health_value:123}].map(x=>JSON.stringify(event(x)))];
  for(const body of bodies)assert.equal((await call({body})).code,400,body);
  assert.equal((await call({body:JSON.stringify(event({user_id:other}))})).code,403);
  assert.equal((await status()).body.latest_notification,null);
});
test('streamed body limit rejects empty or oversized body without trusting Content-Length',async()=>{
  assert.equal((await call({body:''})).code,413);
  assert.equal((await call({body:' '.repeat(4097)})).code,413);
});
test('stored records omit raw object identifiers, secrets and body',async()=>{
  await call();const rows=db.prepare('SELECT * FROM notifications').all();
  assert.equal(rows.length,1);assert.equal(JSON.stringify(rows).includes('synthetic-id'),false);
  assert.equal(JSON.stringify(rows).includes(env.OURA_CLIENT_SECRET),false);
  assert.throws(()=>store.record({user_id:other}),/User mismatch/);
});
test('storage failure returns 503 without internal details',async()=>{
  store.record=()=>{throw Error('private storage detail');};
  assert.deepEqual(await call(),{code:503,body:{error:'Receiver unavailable'}});
});
test('Worker binding routes authenticated status and avoids DO calls for rejected requests',async()=>{
  let calls=0;env.NOTIFICATIONS={idFromName:name=>{assert.equal(name,user);return name;},get:()=>{calls++;return store;}};
  assert.equal((await worker.fetch(request({method:'GET',path:'/status'}),env)).status,401);assert.equal(calls,0);
  assert.equal((await worker.fetch(request({method:'GET',path:'/status',headers:{Authorization:'Bearer '+env.OURA_READ_TOKEN}}),env)).status,200);
  assert.equal(calls,1);
});
