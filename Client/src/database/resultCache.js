/** Completed analyses only, in this page's memory. Never persisted to browser storage. */
import { SessionController } from "database/session-control";

export const MODULES = { biomarkers: "biomarkers", stimOptimizer: "stimOptimizer", closedLoop: "closedLoop" };
const STORE = new Map();
const UPSTREAM = new Map();
const TOKENS = new Map();
const VERSIONS = new Map();
const LISTENERS = new Set();
const USERS = new WeakMap();
const MAX_ENTRIES = 24;
let nextUser = 0;
let principal = null;
let epoch = 0;

export function settingsKey(settings) {
  const norm = (v) => {
    if (v == null) return null;
    if (Array.isArray(v)) return v.map(norm);
    if (typeof v === "object") return Object.fromEntries(Object.keys(v).sort()
      .filter((k) => v[k] !== undefined).map((k) => [k, norm(v[k])]));
    if (typeof v === "number") return Number.isFinite(v) ? v : null;
    return v;
  };
  try { return JSON.stringify(norm(settings)); }
  catch (_) { return `unserialisable:${Date.now()}:${Math.random()}`; }
}

/** Account replacement (including signing back in as the same user) starts a new cache session. */
export function cacheScope(identity = null) {
  const user = SessionController.getUser();
  const session = SessionController.getSession();
  if (!user || !Object.keys(user).length) {
    if (principal !== null) { STORE.clear(); UPSTREAM.clear(); TOKENS.clear(); epoch += 1; }
    principal = null;
    return null;
  }
  if (!USERS.has(user)) USERS.set(user, ++nextUser);
  const study = Object.fromEntries(Object.entries(session || {}).filter(([key]) => /study|permission|access/i.test(key)));
  const next = settingsKey({ account: user, generation: USERS.get(user), study, server: SessionController.getServer() });
  if (principal !== next) {
    STORE.clear(); UPSTREAM.clear(); TOKENS.clear(); VERSIONS.clear(); epoch += 1;
    principal = next;
  }
  return settingsKey({ principal, identity });
}

const family = (moduleKey, uid) => settingsKey([moduleKey, uid]);
const slot = (moduleKey, uid, scope) => settingsKey([scope, moduleKey, uid]);
export function cacheVersion(moduleKey, uid) { return `${epoch}:${VERSIONS.get(family(moduleKey, uid)) || 0}`; }
export function subscribe(fn) { LISTENERS.add(fn); return () => LISTENERS.delete(fn); }
function notify(event) { LISTENERS.forEach((fn) => { try { fn(event); } catch (_) { /* isolate listeners */ } }); }

export function memoryInfo() {
  const m = typeof performance !== "undefined" && performance.memory;
  return m && m.jsHeapSizeLimit ? { usedMB: m.usedJSHeapSize / 1048576,
    limitMB: m.jsHeapSizeLimit / 1048576, ratio: m.usedJSHeapSize / m.jsHeapSizeLimit } : null;
}
export function underMemoryPressure() { const info = memoryInfo(); return !!info && info.ratio >= 0.85; }

/** Identity tokens are participant-specific and include server input/QC/access revisions. */
export function serverToken(uid = "*") { cacheScope(); return TOKENS.get(String(uid)) || null; }
export function setServerToken(token, uid = "*") {
  cacheScope();
  const previous = TOKENS.get(String(uid));
  const next = token == null ? null : String(token);
  const changed = previous != null && previous !== next;
  if (next === null) TOKENS.delete(String(uid)); else TOKENS.set(String(uid), next);
  if (changed) invalidateParticipant(uid, "data, quality control, access or analysis version changed");
  return changed;
}
export function invalidateParticipant(uid, reason) {
  for (const [key, entry] of STORE) if (entry.uid === uid) STORE.delete(key);
  for (const [key, entry] of UPSTREAM) if (entry.uid === uid) UPSTREAM.delete(key);
  epoch += 1;
  notify({ type: "participantInvalidated", uid, reason });
}

export function markUpstreamChanged(moduleKey, uid, reason) {
  cacheScope();
  UPSTREAM.set(family(moduleKey, uid), { uid, reason: String(reason || "an input changed") });
  notify({ type: "upstreamChanged", module: moduleKey, uid });
}
export function clearUpstreamChanged(moduleKey, uid) { UPSTREAM.delete(family(moduleKey, uid)); }

/** Defense in depth; callers must use the canonical polling client, not raw 202 responses. */
export function isCompletedResult(bundle) {
  if (bundle == null) return false;
  if (bundle.status === 202 || ["pending", "queued", "running", "processing"].includes(bundle.status)) return false;
  return !(bundle.data && (bundle.data.status === 202 ||
    ["pending", "queued", "running", "processing"].includes(bundle.data.status)));
}

export function putResult(moduleKey, uid, key, bundle, meta = null, identity = null) {
  const scope = cacheScope(identity);
  if (!moduleKey || !uid || !scope) return { stored: false, reason: "no authenticated cache scope" };
  if (!isCompletedResult(bundle)) return { stored: false, reason: "analysis has not completed" };
  const s = slot(moduleKey, uid, scope);
  if (underMemoryPressure()) STORE.clear();
  if (underMemoryPressure()) return { stored: false, reason: "browser memory is near its limit" };
  const now = Date.now();
  STORE.set(s, { bundle, moduleKey, uid, key, savedAt: now, lastReadAt: now,
    serverToken: serverToken(uid), meta });
  while (STORE.size > MAX_ENTRIES) {
    const candidates = [...STORE.entries()].filter(([k]) => k !== s);
    candidates.sort((a, b) => Number(a[1].uid === uid) - Number(b[1].uid === uid) || a[1].lastReadAt - b[1].lastReadAt);
    STORE.delete(candidates[0][0]);
  }
  clearUpstreamChanged(moduleKey, uid);
  notify({ type: "stored", module: moduleKey, uid });
  return { stored: true, reason: null };
}

export function getResult(moduleKey, uid, currentKey, identity = null) {
  const scope = cacheScope(identity);
  if (!scope) return null;
  const e = STORE.get(slot(moduleKey, uid, scope));
  if (!e) return null;
  // An input/access identity mismatch is a hard miss, never an old result shown as merely stale.
  if (e.serverToken !== serverToken(uid)) return null;
  e.lastReadAt = Date.now();
  const reasons = [];
  if (currentKey !== e.key) reasons.push("the settings on this page have changed since this result was computed");
  const upstream = UPSTREAM.get(family(moduleKey, uid));
  if (upstream) reasons.push(upstream.reason);
  return { bundle: e.bundle, key: e.key, savedAt: e.savedAt, computedAt: e.savedAt,
    meta: e.meta, stale: reasons.length > 0, staleReasons: reasons };
}

export function invalidate(moduleKey, uid) {
  cacheScope();
  for (const [key, entry] of STORE) if (entry.moduleKey === moduleKey && entry.uid === uid) STORE.delete(key);
  clearUpstreamChanged(moduleKey, uid);
  const key = family(moduleKey, uid);
  VERSIONS.set(key, (VERSIONS.get(key) || 0) + 1);
  notify({ type: "invalidated", module: moduleKey, uid });
}
export function invalidateAll(reason) {
  STORE.clear(); UPSTREAM.clear(); VERSIONS.clear(); epoch += 1;
  notify({ type: "invalidatedAll", reason });
}
export function cacheStats() {
  cacheScope();
  const memory = memoryInfo();
  // Do not expose account identifiers, participant identifiers, request settings or payloads.
  return { count: STORE.size, maxEntries: MAX_ENTRIES, memory, memoryMeasurable: memory !== null };
}
