/**
 * One in-memory result cache shared by the Biomarkers, Stim Parameter Optimizer and Closed-Loop
 * Deployment views.
 *
 * THE PROBLEM THIS SOLVES. All three are ROUTE-level components, so React Router unmounts them on
 * navigation and destroys every piece of `useState` they hold. Clicking from Biomarkers to
 * Closed-Loop Deployment and back therefore threw away a completed analysis and started again from
 * the loading screen — and on this participant the closed-loop report alone takes about seventy
 * seconds to assemble. A clinician comparing two modules paid that cost on every switch, and there
 * was no way to hide a plot and bring it back without recomputing the whole view behind it.
 *
 * THE RULE THE CACHE FOLLOWS. A result is reused unless something that could change it has
 * changed. Three things can:
 *
 *   1. The SETTINGS that produced it. Every entry is stored under a key derived from the request
 *      the view would send, so a changed metric, threshold, window or candidate band is a
 *      different key and misses the cache rather than returning the wrong answer.
 *   2. The SERVER. The cache lives in the tab and outlives a server restart, so a clinician could
 *      restart the server, return to a tab left open, and be shown results computed by code that
 *      is no longer running. Every entry records the server's boot token and is treated as stale
 *      when the current token differs. See `/api/queryServerIdentity`.
 *   3. An UPSTREAM COMMIT. Committing a new band candidate on the Biomarkers page changes what the
 *      deployment view is about, so a module can declare its results stale for the other modules
 *      through `markUpstreamChanged`.
 *
 * Nothing else invalidates. In particular, navigating, unmounting, remounting, collapsing a panel
 * and reopening it do not, because none of them changes the answer.
 *
 * WHY THE STALENESS IS SURFACED RATHER THAN ACTED ON. When an entry is stale this module does NOT
 * silently discard it and recompute. It returns the old result together with the reason it is
 * stale, so the view can show the last completed analysis — which is what the reader asked to
 * see — while marking the Recompute control to say that it no longer reflects the current
 * settings. Silently recomputing would reintroduce exactly the seventy-second wait the cache
 * exists to remove, and silently showing a stale number with no indication would be worse than
 * either.
 *
 * MEMORY. The heavy results are large: the biomarker bundle is around nineteen megabytes and the
 * deployment payload around one hundred and forty kilobytes. The cache is bounded by entry count
 * AND by live heap pressure where the browser reports it, and under pressure it declines to store
 * a new result rather than risking the tab. Declining is safe because the caller's fallback is to
 * recompute, which is slow but correct. This mirrors the guard already proven in
 * `views/Reports/Biomarkers/biomarkerStateStore.js`, which this module generalises; that file's
 * per-view behaviour is unchanged and it remains the owner of the biomarker CONTROLS layer.
 */

/** Module identifiers. Strings rather than an enum so a stored entry stays readable in a debugger. */
export const MODULES = {
  biomarkers: "biomarkers",
  stimOptimizer: "stimOptimizer",
  closedLoop: "closedLoop",
};

// ---- the store -------------------------------------------------------------------------------
// A module-level Map, which is what makes this survive an unmount: module scope is per page load,
// not per component. A hard reload clears it, which is correct — a reload is the user asking for a
// clean slate, and it is also when a new server build would arrive.
const STORE = new Map();          // `${module}::${uid}` -> entry
// RAISED FROM 6 TO 24 after the views were wired, because the original figure was set against an
// assumption that did not survive contact with the closed-loop page: it has SEVEN separate
// requests, not one, so a single participant occupies nine slots across the three modules rather
// than three. At six the store silently evicted entries that were still being displayed.
//
// The count is also the wrong unit on its own, and this cap is not what keeps the tab safe. The
// entries differ by three orders of magnitude — the biomarker bundle is around nineteen megabytes
// and a panel payload around twenty kilobytes — so twenty-four small entries and twenty-four large
// ones are not comparable amounts of memory. The real bound is the heap-pressure guard in
// `putResult`, which reclaims other participants first and then declines to store at all. This cap
// exists only to stop unbounded growth across many participants in one session.
const MAX_ENTRIES = 24;
const PRESSURE_RATIO = 0.85;

let SERVER_TOKEN = null;          // last token seen from /api/queryServerIdentity
const UPSTREAM = new Map();       // `${module}::${uid}` -> { at, reason }
const LISTENERS = new Set();

function slot(moduleKey, uid) { return `${String(moduleKey)}::${String(uid || "unknown")}`; }

/**
 * A stable string for a settings object.
 *
 * Keys are sorted at every level, because two objects that differ only in key order describe the
 * same request and must not miss the cache. `undefined` is dropped rather than serialised, so a
 * control that is absent and one that is explicitly unset agree.
 */
export function settingsKey(settings) {
  const norm = (v) => {
    if (v === null || v === undefined) return null;
    if (Array.isArray(v)) return v.map(norm);
    if (typeof v === "object") {
      const out = {};
      Object.keys(v).sort().forEach((k) => {
        if (v[k] !== undefined) out[k] = norm(v[k]);
      });
      return out;
    }
    if (typeof v === "number") return Number.isFinite(v) ? v : null;
    return v;
  };
  try {
    return JSON.stringify(norm(settings === undefined ? null : settings));
  } catch (e) {
    // A settings object that cannot be serialised (a cycle, a DOM node) must not silently collapse
    // every request onto one key, so it is given a key that can never match a stored one.
    return `unserialisable:${Date.now()}:${Math.random()}`;
  }
}

// ---- memory guard ----------------------------------------------------------------------------
export function memoryInfo() {
  const m = (typeof performance !== "undefined") && performance.memory;
  if (!m || !m.jsHeapSizeLimit) return null;
  return {
    usedMB: m.usedJSHeapSize / 1048576,
    limitMB: m.jsHeapSizeLimit / 1048576,
    ratio: m.usedJSHeapSize / m.jsHeapSizeLimit,
  };
}

/**
 * True when the heap is close to its ceiling.
 *
 * Returns false when the browser does not report heap figures at all, which is Firefox and Safari.
 * That is a deliberate choice and it is NOT the same as "there is room": it means the guard cannot
 * measure, so it does not block. Callers that report a caching decision to the user must say which
 * of the two situations they are in rather than presenting an unmeasured case as a confirmed one.
 */
export function underMemoryPressure() {
  const mi = memoryInfo();
  return mi ? mi.ratio >= PRESSURE_RATIO : false;
}

/**
 * Evict one entry, preferring another participant's over the one being read.
 *
 * Least-recently-read alone is not good enough here. Every slot is touched on read, so within one
 * participant the entries that fall out are whichever panels the reader last looked at — which is
 * an accident of their click order rather than a decision about what is worth keeping. Worse, a
 * participant being actively worked on can evict their OWN panels while another participant's
 * abandoned nineteen-megabyte bundle stays resident.
 *
 * So the search runs in two passes: other participants first, oldest of those, and only if none
 * exist does it fall back to the least-recently-read entry of the current participant.
 */
function evictOldest(exceptSlot) {
  const currentUid = String(exceptSlot || "").split("::")[1] || null;
  const pick = (predicate) => {
    let chosen = null;
    let chosenAt = Infinity;
    STORE.forEach((v, k) => {
      if (k === exceptSlot || !predicate(k)) return;
      if (v.savedAt < chosenAt) { chosenAt = v.savedAt; chosen = k; }
    });
    return chosen;
  };
  const other = currentUid
    ? pick((k) => (String(k).split("::")[1] || null) !== currentUid)
    : null;
  const victim = other !== null ? other : pick(() => true);
  if (victim !== null) STORE.delete(victim);
}

// ---- server identity -------------------------------------------------------------------------
/** Record the token from /api/queryServerIdentity. Returns true when it CHANGED. */
export function setServerToken(token) {
  const next = token == null ? null : String(token);
  const changed = SERVER_TOKEN !== null && next !== null && SERVER_TOKEN !== next;
  SERVER_TOKEN = next;
  if (changed) notify({ type: "serverChanged", token: next });
  return changed;
}

export function serverToken() { return SERVER_TOKEN; }

// ---- upstream invalidation -------------------------------------------------------------------
/**
 * Declare that something a module DEPENDS ON has changed, without discarding its result.
 *
 * The case this exists for: committing a new band candidate on the Biomarkers page changes which
 * configuration the deployment view is about. The deployment result already on screen was computed
 * for the previous band and is not wrong about that band, so it is kept and marked rather than
 * thrown away — the reader can still see what the previous candidate looked like while the
 * Recompute control tells them the page is now behind.
 */
export function markUpstreamChanged(moduleKey, uid, reason) {
  UPSTREAM.set(slot(moduleKey, uid), { at: Date.now(), reason: String(reason || "an input changed") });
  notify({ type: "upstreamChanged", module: moduleKey, uid, reason });
}

export function clearUpstreamChanged(moduleKey, uid) { UPSTREAM.delete(slot(moduleKey, uid)); }

// ---- subscription ----------------------------------------------------------------------------
/** Subscribe to cache events, so a Recompute control can turn red without polling. */
export function subscribe(fn) {
  LISTENERS.add(fn);
  return () => LISTENERS.delete(fn);
}

function notify(ev) {
  LISTENERS.forEach((fn) => {
    try { fn(ev); } catch (e) { /* a bad listener must not break the store */ }
  });
}

// ---- read and write --------------------------------------------------------------------------
/**
 * Store a completed result.
 *
 * Returns a small record saying whether it was stored and, when it was not, why — so a view can
 * tell a reader "this will recompute when you come back" instead of promising persistence it did
 * not achieve.
 */
export function putResult(moduleKey, uid, key, bundle, meta) {
  if (!moduleKey || !uid) return { stored: false, reason: "no module or participant given" };
  const s = slot(moduleKey, uid);

  if (underMemoryPressure()) {
    // Reclaim everything else first: another participant's nineteen-megabyte bundle is a better
    // thing to lose than the result the reader is looking at right now.
    Array.from(STORE.keys()).forEach((k) => { if (k !== s) STORE.delete(k); });
  }
  if (underMemoryPressure()) {
    STORE.delete(s);
    return {
      stored: false,
      reason: "the browser heap is close to its limit, so this result was not kept; returning to "
              + "this view will recompute it",
    };
  }

  STORE.set(s, {
    bundle,
    key: key == null ? null : String(key),
    savedAt: Date.now(),
    serverToken: SERVER_TOKEN,
    meta: meta || null,
  });
  while (STORE.size > MAX_ENTRIES) evictOldest(s);
  UPSTREAM.delete(s);
  notify({ type: "stored", module: moduleKey, uid });
  return { stored: true, reason: null };
}

/**
 * Read a stored result and say whether it is still current.
 *
 * Returns null only when there is nothing stored. When there IS something, it always comes back —
 * with `stale` and `staleReasons` describing why it may no longer be right. The caller decides
 * what to do, and the intended behaviour is to display it and mark the Recompute control rather
 * than to discard it.
 */
export function getResult(moduleKey, uid, currentKey) {
  const s = slot(moduleKey, uid);
  const e = STORE.get(s);
  if (!e) return null;
  e.savedAt = Date.now();                       // least-recently-used touch

  const reasons = [];
  if (currentKey != null && e.key != null && String(currentKey) !== e.key) {
    reasons.push("the settings on this page have changed since this result was computed");
  }
  if (SERVER_TOKEN != null && e.serverToken != null && SERVER_TOKEN !== e.serverToken) {
    reasons.push("the server has restarted or its analysis code has reloaded since this result "
                 + "was computed");
  }
  const up = UPSTREAM.get(s);
  if (up) reasons.push(up.reason);

  return {
    bundle: e.bundle,
    key: e.key,
    savedAt: e.savedAt,
    computedAt: e.savedAt,
    meta: e.meta,
    stale: reasons.length > 0,
    staleReasons: reasons,
  };
}

/** Drop one module's result for one participant. This is what Recompute calls before refetching. */
export function invalidate(moduleKey, uid) {
  const s = slot(moduleKey, uid);
  STORE.delete(s);
  UPSTREAM.delete(s);
  notify({ type: "invalidated", module: moduleKey, uid });
}

/** Drop everything. Used when the server token changes, since no entry can be trusted. */
export function invalidateAll(reason) {
  STORE.clear();
  UPSTREAM.clear();
  notify({ type: "invalidatedAll", reason: reason || null });
}

/** What is resident, for a diagnostics line. Never returns the bundles themselves. */
export function cacheStats() {
  const rows = [];
  STORE.forEach((v, k) => {
    rows.push({ slot: k, savedAt: v.savedAt, key: v.key, serverToken: v.serverToken });
  });
  return {
    entries: rows,
    count: STORE.size,
    maxEntries: MAX_ENTRIES,
    serverToken: SERVER_TOKEN,
    memory: memoryInfo(),
    memoryMeasurable: memoryInfo() !== null,
  };
}
