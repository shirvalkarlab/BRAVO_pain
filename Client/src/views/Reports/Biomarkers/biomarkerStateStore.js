/**
 * The Biomarkers view's CONTROLS layer, and nothing else.
 *
 * The Biomarkers view is a ROUTE-level component (/reports/biomarkers/:uid). React Router UNMOUNTS
 * it on navigation, destroying every useState — so without help, returning to it shows the original
 * loading view. Restoring it takes two quite different things, and this file now owns exactly one
 * of them.
 *
 * WHAT THIS FILE OWNS: the controls. A few hundred bytes per participant — the metric, the
 * binarization strategy and its percentile cuts, the matching parameters, the timeline colour mode,
 * and the request that was last computed — written to localStorage. That storage is the point: it
 * survives a hard reload and a closed tab, so the panel comes back configured the way it was left
 * even after the browser has been restarted, and the view knows which request its displayed result
 * belongs to.
 *
 * WHAT THIS FILE NO LONGER OWNS: the heavy result. The nineteen-megabyte analysis bundle used to
 * live in a second, in-memory layer here — a module-level map with its own eviction rule and its own
 * heap-pressure guard. `database/resultCache` was generalised FROM that layer and now serves all
 * three analysis views, so keeping this copy would have left the application with two heavy caches
 * holding the same class of object under two independent eviction policies, and a result evicted
 * from one but not the other would have been genuinely ambiguous — present according to one store
 * and absent according to the other. The heavy layer is therefore gone rather than deprecated, and
 * `views/Reports/Biomarkers/index.js` reads and writes the bundle through
 * `database/useCachedResult` like the other two views. Its heap-pressure guard went with it: the
 * shared store carries the same guard, and the view now reports on the shared one.
 */

const CONTROLS_PREFIX = "bravo.biomarkerControls.";

// ---- controls (localStorage, per participant) ------------------------------------------------
function _ckey(uid) { return CONTROLS_PREFIX + String(uid || "unknown"); }

/** Persist the lightweight control panel + last-computed requestParams for a participant. */
export function saveControls(uid, controls) {
  try {
    window.localStorage.setItem(_ckey(uid), JSON.stringify({
      schema: "biomarker_controls_v1", saved_at: Date.now(), ...controls,
    }));
  } catch (e) {
    // Quota or private browsing. The shared result cache still holds this session's analysis, so
    // navigating away and back still works; what is lost is only persistence across a reload.
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
