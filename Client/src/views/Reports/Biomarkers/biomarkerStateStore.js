/**
 * Biomarker view state persistence — survives navigating away to the Closed-Loop deployment view
 * and back without resetting to the loading screen.
 *
 * The Biomarkers view is a ROUTE-level component (/reports/biomarkers/:uid). React Router UNMOUNTS
 * it on navigation, destroying every useState — so on return `data` is false and you get the
 * original loading view. This store restores it through TWO layers, by design:
 *
 *   1. CONTROLS (tiny, ~hundreds of bytes) -> localStorage, per participant. The exact panel config
 *      (metric, strategy, percentile cuts, match params, color mode) and the last-computed
 *      requestParams. Survives a full page reload and tab close. On return we restore the controls
 *      instantly and, if a compute had been run, re-issue it (the backend caches the PSD inputs, so
 *      the ~19 MB analysis recomputes quickly) — the view looks identical within ~1 s.
 *
 *   2. HEAVY RESULT (~19 MB: analytics + availability + timeline + power) -> an in-memory, module-
 *      level LRU cache. Modules persist across route unmount/mount (only a hard page reload clears
 *      them), so when you come straight back the byte-identical result is restored with ZERO
 *      recompute — instant, same pixels. localStorage CANNOT hold this (5-10 MB quota, synchronous
 *      write would freeze the tab), which is why the heavy layer is memory-only.
 *
 * MEMORY GUARD ("memory tackle"): the heap cache is bounded by entry count AND by live heap
 * pressure (performance.memory where the browser exposes it, i.e. Chromium). Under pressure it
 * evicts older participants and, if still tight, declines to cache the new result at all — the
 * controls-layer recompute path is the graceful fallback, so we never OOM the tab to keep a cache.
 */

const CONTROLS_PREFIX = "bravo.biomarkerControls.";

// ---- Layer 1: controls (localStorage, per participant) ---------------------------------------
function _ckey(uid) { return CONTROLS_PREFIX + String(uid || "unknown"); }

/** Persist the lightweight control panel + last-computed requestParams for a participant. */
export function saveControls(uid, controls) {
  try {
    window.localStorage.setItem(_ckey(uid), JSON.stringify({
      schema: "biomarker_controls_v1", saved_at: Date.now(), ...controls,
    }));
  } catch (e) {
    // Quota/private-mode: the in-memory layer still works this session; just no reload persistence.
    // eslint-disable-next-line no-console
    console.warn("saveControls: localStorage write failed", e);
  }
}

/** Read persisted controls for a participant, or null. */
export function loadControls(uid) {
  try {
    const raw = window.localStorage.getItem(_ckey(uid));
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

/** Clear persisted controls for a participant. */
export function clearControls(uid) {
  try { window.localStorage.removeItem(_ckey(uid)); } catch (e) { /* no-op */ }
}

// ---- Layer 2: heavy result (in-memory LRU + memory guard) ------------------------------------
const HEAP = new Map();            // uid -> { bundle, saved_at, request_key }
const MAX_ENTRIES = 2;             // keep at most 2 participants' heavy results resident
const PRESSURE_RATIO = 0.85;       // evict/decline above this fraction of the JS heap limit

/** Live heap usage where the browser exposes it (Chromium). Returns null on Firefox/Safari. */
export function memoryInfo() {
  const m = (typeof performance !== "undefined") && performance.memory;
  if (!m || !m.jsHeapSizeLimit) return null;
  return { usedMB: m.usedJSHeapSize / 1048576, limitMB: m.jsHeapSizeLimit / 1048576,
    ratio: m.usedJSHeapSize / m.jsHeapSizeLimit };
}

/** True when we're close to the heap ceiling. Unknown (no performance.memory) -> false (don't block). */
export function underMemoryPressure() {
  const mi = memoryInfo();
  return mi ? mi.ratio >= PRESSURE_RATIO : false;
}

function _evictOldest() {
  let oldestKey = null, oldestAt = Infinity;
  for (const [k, v] of HEAP) { if (v.saved_at < oldestAt) { oldestAt = v.saved_at; oldestKey = k; } }
  if (oldestKey != null) HEAP.delete(oldestKey);
}

/**
 * Cache the heavy result for a participant. `requestKey` is the JSON of the computed requestParams,
 * so a stale cache (controls changed since) can be detected on read. Returns true if cached.
 * Memory-guarded: under pressure it evicts others and, if still tight, declines (returns false) so
 * the caller falls back to recompute-on-return rather than risking an OOM.
 */
export function putHeavy(uid, bundle, requestKey) {
  if (!uid) return false;
  // If we're under pressure, first reclaim everything else.
  if (underMemoryPressure()) {
    for (const k of Array.from(HEAP.keys())) if (k !== String(uid)) HEAP.delete(k);
  }
  // Still under pressure after reclaiming? Decline to cache; recompute path will cover the return.
  if (underMemoryPressure()) { HEAP.delete(String(uid)); return false; }
  HEAP.set(String(uid), { bundle, saved_at: Date.now(), request_key: requestKey || null });
  while (HEAP.size > MAX_ENTRIES) _evictOldest();
  return true;
}

/** Read the cached heavy result for a participant, or null. Does not validate freshness. */
export function getHeavy(uid) {
  const e = HEAP.get(String(uid));
  if (!e) return null;
  e.saved_at = Date.now();   // LRU touch
  return e;
}

/** Drop a participant's heavy cache entry (e.g. on explicit recompute). */
export function dropHeavy(uid) { HEAP.delete(String(uid)); }
