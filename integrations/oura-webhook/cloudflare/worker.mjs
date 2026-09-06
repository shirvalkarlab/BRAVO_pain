import {DurableObject} from 'cloudflare:workers';

const ENCODER = new TextEncoder();
const TYPES = new Set(['tag','enhanced_tag','workout','session','sleep','daily_sleep','daily_readiness',
  'daily_activity','daily_spo2','sleep_time','rest_mode_period','ring_configuration','daily_stress',
  'daily_cardiovascular_age','daily_resilience','vo2_max','meal']);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const iso = seconds => new Date(seconds * 1000).toISOString();
const reply = (status, body) => Response.json(body, {status, headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});

async function key(secret) {
  return crypto.subtle.importKey('raw', ENCODER.encode(secret), {name:'HMAC',hash:'SHA-256'}, false, ['sign','verify']);
}
async function digest(secret, value) {
  return new Uint8Array(await crypto.subtle.sign('HMAC', await key(secret), ENCODER.encode(value)));
}
async function equalSecret(expected, provided) {
  // Authenticate tokens through WebCrypto verification, not string equality.
  return crypto.subtle.verify('HMAC', await key(expected), await digest(expected, expected), ENCODER.encode(provided));
}
const hex = bytes => Array.from(bytes, value=>value.toString(16).padStart(2,'0')).join('');

function configured(env) {
  const values = [env.OURA_CLIENT_SECRET,env.OURA_VERIFICATION_TOKEN,env.OURA_READ_TOKEN];
  return env.ACTIVATION_APPROVED === 'true' && typeof env.OURA_USER_ID === 'string' && UUID.test(env.OURA_USER_ID)
    && values.every(value=>typeof value === 'string' && value.length >= 32) && new Set(values).size === 3;
}

async function boundedBody(request) {
  const reader = request.body?.getReader();
  if (!reader) throw new Error('Empty body');
  const chunks = []; let length = 0;
  try {
    while (true) {
      const {done,value} = await reader.read();
      if (done) break;
      length += value.length;
      if (length > 4096) throw new Error('Body too large');
      chunks.push(value);
    }
  } finally { await reader.cancel(); }
  if (!length) throw new Error('Empty body');
  const raw = new Uint8Array(length); let offset=0;
  for (const value of chunks) {raw.set(value,offset);offset+=value.length;}
  return raw;
}

function parseEvent(text, user, now, signedAt) {
  const event = JSON.parse(text);
  const fields = ['data_type','event_time','event_type','object_id','user_id'];
  if (!event || typeof event !== 'object' || Array.isArray(event) || Object.keys(event).sort().join() !== fields.join()
      || !Object.values(event).every(value=>typeof value === 'string')) throw new Error('Schema');
  // JSON.parse alone silently accepts duplicate keys. At this point all values
  // are strings, so count the lexical key tokens as well as the parsed keys.
  if ([...text.matchAll(/"(?:[^"\\]|\\.)*"\s*:/g)].length !== fields.length) throw new Error('Duplicate keys');
  if (!['create','update','delete'].includes(event.event_type) || !TYPES.has(event.data_type)
      || !/^[A-Za-z0-9_-]{1,128}$/.test(event.object_id) || !UUID.test(event.user_id)) throw new Error('Type');
  if (event.user_id.toLowerCase() !== user) return null;
  const format = /^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
  const match = event.event_time.match(format), stamp = Date.parse(event.event_time)/1000;
  if (!match || !Number.isFinite(stamp) || new Date(`${match[1]}T00:00:00Z`).toISOString().slice(0,10) !== match[1]
      || stamp < 0 || stamp > Math.min(now,signedAt)+60) throw new Error('Time');
  return {...event,event_time:stamp,user_id:user};
}

export async function route(request, env, store, now=Date.now()/1000) {
  try {
    if (!configured(env)) return reply(503,{error:'Receiver not activated'});
    const url = new URL(request.url), user = env.OURA_USER_ID.toLowerCase();
    if (request.method === 'GET' && url.pathname === '/status') {
      if (!await equalSecret(`Bearer ${env.OURA_READ_TOKEN}`,request.headers.get('Authorization') || '')) return reply(401,{error:'Unauthorized'});
      return reply(200,await store.status(now));
    }
    if (request.method === 'GET' && url.pathname === '/oura-webhook') {
      const params=url.searchParams, keys=[...params.keys()];
      if (keys.length !== 2 || params.getAll('verification_token').length !== 1 || params.getAll('challenge').length !== 1
          || !params.get('challenge') || params.get('challenge').length > 1024
          || !await equalSecret(env.OURA_VERIFICATION_TOKEN,params.get('verification_token'))) return reply(401,{error:'Invalid verification'});
      return reply(200,{challenge:params.get('challenge')});
    }
    if (request.method !== 'POST' || url.pathname !== '/oura-webhook') return reply(404,{error:'Not found'});
    const timestamp=request.headers.get('x-oura-timestamp') || '', signature=request.headers.get('x-oura-signature') || '';
    if (!/^\d{10}$/.test(timestamp) || !/^[a-f0-9]{64}$/i.test(signature)
        || Number(timestamp)<now-3900 || Number(timestamp)>now+60) return reply(401,{error:'Invalid authentication'});
    if (request.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase() !== 'application/json') return reply(415,{error:'JSON required'});
    let raw;
    try {raw=await boundedBody(request);} catch {return reply(413,{error:'Invalid body length'});}
    const prefix=ENCODER.encode(timestamp), signed=new Uint8Array(prefix.length+raw.length);
    signed.set(prefix);signed.set(raw,prefix.length);
    const signatureBytes=Uint8Array.from(signature.match(/../g),part=>parseInt(part,16));
    if (!await crypto.subtle.verify('HMAC',await key(env.OURA_CLIENT_SECRET),signatureBytes,signed)) return reply(401,{error:'Invalid authentication'});
    let event;
    try {event=parseEvent(new TextDecoder('utf-8',{fatal:true}).decode(raw),user,now,Number(timestamp));}
    catch {return reply(400,{error:'Invalid event metadata'});}
    if (!event) return reply(403,{error:'Unbound user'});
    const identity=JSON.stringify([user,event.event_type,event.data_type,event.object_id,event.event_time]);
    const fingerprint=hex(await digest(env.OURA_CLIENT_SECRET,identity));
    return reply(200,await store.record({user_id:user,fingerprint,event_time:event.event_time,received_at:now,
      event_type:event.event_type,data_type:event.data_type}));
  } catch {return reply(503,{error:'Receiver unavailable'});}
}

export class NotificationStore extends DurableObject {
  constructor(ctx,env) {
    super(ctx,env);
    this.sql=ctx.storage.sql;this.user=env.OURA_USER_ID.toLowerCase();
    this.sql.exec('CREATE TABLE IF NOT EXISTS notifications (user_id TEXT NOT NULL,fingerprint TEXT NOT NULL,event_time REAL NOT NULL,received_at REAL NOT NULL,event_type TEXT NOT NULL,data_type TEXT NOT NULL,PRIMARY KEY(user_id,fingerprint))');
    this.sql.exec('CREATE INDEX IF NOT EXISTS notification_order ON notifications(user_id,event_time DESC,received_at DESC)');
    this.sql.exec('CREATE INDEX IF NOT EXISTS notification_receipt ON notifications(user_id,received_at DESC)');
  }
  record(event) {
    if (event.user_id!==this.user) throw new Error('User mismatch');
    const cursor=this.sql.exec('INSERT OR IGNORE INTO notifications VALUES (?,?,?,?,?,?)',event.user_id,event.fingerprint,event.event_time,event.received_at,event.event_type,event.data_type);
    return {accepted:true,duplicate:cursor.rowsWritten===0};
  }
  status(now) {
    const row=this.sql.exec('SELECT event_time,received_at,event_type,data_type FROM notifications WHERE user_id=? ORDER BY event_time DESC,received_at DESC LIMIT 1',this.user).toArray()[0];
    const receipt=this.sql.exec('SELECT MAX(received_at) AS receipt FROM notifications WHERE user_id=?',this.user).toArray()[0].receipt;
    return {schema_version:1,source:'oura_webhook',user_id:this.user,as_of:iso(now),
      latest_notification:row?{...row,event_time:iso(row.event_time),received_at:iso(row.received_at)}:null,
      last_received_at:receipt===null?null:iso(receipt),
      meaning:'Authenticated Oura data-change notification; not app-open time or LastAppSync.'};
  }
}

export default {
  async fetch(request,env) {
    // Defer Durable Object allocation until an authenticated operation needs it.
    const object=()=>env.NOTIFICATIONS.get(env.NOTIFICATIONS.idFromName(env.OURA_USER_ID.toLowerCase()));
    return route(request,env,{status:now=>object().status(now),record:event=>object().record(event)});
  }
};
