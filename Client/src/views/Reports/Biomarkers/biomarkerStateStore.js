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

import {
  MATCHING_DEFAULTS, MATCHING_DEFAULTS_VERSION, REPLACED_DEFAULTS, CONTROL_REQUEST_KEYS,
} from "./matchingDefaults";

const CONTROLS_PREFIX = "bravo.biomarkerControls.";

// ---- controls (localStorage, per participant) ------------------------------------------------
function _ckey(uid) { return CONTROLS_PREFIX + String(uid || "unknown"); }

const _same = (a, b) => (typeof a === "number" || typeof b === "number"
  ? Number(a) === Number(b) : a === b);

/**
 * A saved setting from before a change of defaults, moved to today's defaults ONCE (decision 331).
 *
 * A value equal to a default an intervening version replaced (`REPLACED_DEFAULTS`) becomes today's
 * default; anything else the viewer chose is kept. The same move is made inside the saved request
 * (`requestParams`, by its request keys) and the saved last run (`matchingRun.settings`), so the page
 * and the Closed-Loop page, which inherits the last run, agree. The result carries today's version,
 * so once the page saves it again a viewer who then picks 5 minutes keeps 5 minutes.
 */
export function migrateControls(saved) {
  if (!saved || typeof saved !== "object") return saved;
  const from = Number(saved.defaults_version) || 1;
  if (from >= MATCHING_DEFAULTS_VERSION) return saved;
  const out = { ...saved };
  const rp = out.requestParams ? { ...out.requestParams } : null;
  const run = out.matchingRun && out.matchingRun.settings
    ? { ...out.matchingRun, settings: { ...out.matchingRun.settings } } : null;
  for (let v = from + 1; v <= MATCHING_DEFAULTS_VERSION; v += 1) {
    const replaced = REPLACED_DEFAULTS[v] || {};
    Object.keys(replaced).forEach((field) => {
      const olds = replaced[field];
      const now = MATCHING_DEFAULTS[field];
      const key = CONTROL_REQUEST_KEYS[field];
      if (field in out && olds.some((o) => _same(out[field], o))) out[field] = now;
      if (rp && key && key in rp && olds.some((o) => _same(rp[key], o))) rp[key] = now;
      if (run && key && key in run.settings && olds.some((o) => _same(run.settings[key], o))) {
        run.settings[key] = now;
      }
    });
  }
  if (rp) out.requestParams = rp;
  if (run) out.matchingRun = run;
  out.defaults_version = MATCHING_DEFAULTS_VERSION;
  out.migrated_from_version = from;
  return out;
}

/** Persist the lightweight control panel + last-computed requestParams for a participant. */
export function saveControls(uid, controls) {
  try {
    window.localStorage.setItem(_ckey(uid), JSON.stringify({
      schema: "biomarker_controls_v1", saved_at: Date.now(), ...controls,
      defaults_version: MATCHING_DEFAULTS_VERSION,
    }));
  } catch (e) {
    // Quota or private browsing. The shared result cache still holds this session's analysis, so
    // navigating away and back still works; what is lost is only persistence across a reload.
    // eslint-disable-next-line no-console
    console.warn("saveControls: localStorage write failed", e);
  }
}

/** Read persisted controls for a participant, moved to today's defaults where they predate them
 *  (`migrateControls`), or null. */
export function loadControls(uid) {
  try {
    const raw = window.localStorage.getItem(_ckey(uid));
    return raw ? migrateControls(JSON.parse(raw)) : null;
  } catch (e) { return null; }
}

/** Today's defaults as the request keys the pages send (the pain score as `LabelMetric`). */
export function defaultMatchingSettings() {
  const out = { LabelMetric: MATCHING_DEFAULTS.metric };
  Object.keys(CONTROL_REQUEST_KEYS).forEach((field) => {
    out[CONTROL_REQUEST_KEYS[field]] = MATCHING_DEFAULTS[field];
  });
  return out;
}

/**
 * THE MATCHING SETTINGS THE BIOMARKERS PAGE MOST RECENTLY RAN (decision 331), for the Closed-Loop
 * page to inherit: `{settings, ranAt, source}`, `settings` in request keys (the pain score as
 * `LabelMetric`).
 *
 * `source` says where they came from: "run" (the page recorded a run: a Recompute, or a heat-map
 * grid it built and showed as current), "computed" (a page saved before decision 331 recorded only
 * its last Compute request, which carries no clinic-sheet switch; the switch is then the page's own
 * control), or "defaults" (the page has never been opened for this participant in this browser).
 */
export function loadMatchingRun(uid) {
  const P = (uid && loadControls(uid)) || null;
  const base = defaultMatchingSettings();
  if (P && P.matchingRun && P.matchingRun.settings) {
    return { settings: { ...base, ...P.matchingRun.settings }, ranAt: P.matchingRun.ranAt || null,
      source: "run" };
  }
  if (P && P.requestParams) {
    const rp = P.requestParams;
    const settings = { ...base };
    Object.values(CONTROL_REQUEST_KEYS).concat(["LabelMetric"]).forEach((k) => {
      if (rp[k] !== undefined && rp[k] !== null) settings[k] = rp[k];
    });
    if (P.metric) settings.LabelMetric = P.metric;
    if (typeof P.includeClinicSheetRatings === "boolean") {
      settings.IncludeClinicSheetRatings = P.includeClinicSheetRatings;
    }
    return { settings, ranAt: P.saved_at || null, source: "computed" };
  }
  return { settings: base, ranAt: null, source: "defaults" };
}

/** Clear persisted controls for a participant. */
export function clearControls(uid) {
  try { window.localStorage.removeItem(_ckey(uid)); } catch (e) { /* no-op */ }
}
