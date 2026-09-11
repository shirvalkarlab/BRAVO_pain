/**
 * The cache slots the Closed-Loop Deployment page occupies, and the two family-wide operations it
 * needs.
 *
 * WHY THIS FILE EXISTS. `database/resultCache` stores one entry per `${moduleKey}::${participant}`
 * pair, so a module owns exactly one result. That is the right shape for the Biomarkers and Stim
 * Parameter Optimizer views, which each assemble a whole page from a single response. It is not the
 * shape of the Closed-Loop Deployment page, which fetches from five endpoints on its own route and
 * lends two more panels to the Biomarkers route. Those answers are separate questions with separate
 * inputs — the receiver-operating-characteristic curve does not change when the threshold mode is
 * switched, and the deployment report does not change when the operating point moves — so they
 * cannot share a single entry without one of them silently overwriting another.
 *
 * The keys below therefore extend the module identifier with a panel name. The store treats each as
 * a distinct module, because `moduleKey` is only ever used to build the slot string. A forward
 * slash separates the two parts rather than the store's own double colon, so that a slot string
 * read in a debugger still shows unambiguously where the module name ends.
 *
 * THIS IS A WORKAROUND. It used to also carry a limit worth stating here — a flat entry-count cap
 * was the wrong unit when one entry is nineteen megabytes and another is twenty kilobytes, so
 * visiting all three views (nine slots total: five on the deployment route, three on the
 * biomarker route, one for the optimizer) could evict a fresh result to make room for a small one.
 * `resultCache` now bounds itself by a byte budget and by how many different participants are
 * resident, not by a slot count (PI, 2026-09-08), so one participant's own nine slots are never
 * limited on their own — see that file for the current bounds. This file's own reason for
 * existing, giving the deployment page's five endpoints and two lent panels each their own slot
 * rather than fighting over one, is unrelated to that and still stands.
 */
import {
  MODULES, invalidate, markUpstreamChanged, getResult, putResult, settingsKey,
} from "database/resultCache";
import { refreshServerIdentity } from "database/useCachedResult";

/**
 * One key per question the deployment family asks.
 *
 * `report` is deliberately the bare `MODULES.closedLoop` rather than a suffixed key. It is the slot
 * another module reaches for when it declares that the deployment view is out of date, so it has to
 * be the name that module already knows.
 */
export const CL = {
  report: MODULES.closedLoop,
  // The calibrated grid is fetched from the SAME endpoint as the report, with an empty candidate
  // list. It needs its own slot: the cache keeps one answer per slot per participant and hands a
  // request with different settings the held answer marked stale rather than fetching. Sharing
  // `report` meant the grid's empty-candidate reply filled the slot first, and the report for a
  // chosen band was then shown that reply -- "no candidate configuration was supplied" on the
  // evidence panel with a band plainly chosen above it. Watched live on RCS08, 2026-09-10.
  grid: `${MODULES.closedLoop}/grid`,
  summary: `${MODULES.closedLoop}/summary`,
  roc: `${MODULES.closedLoop}/roc`,
  era: `${MODULES.closedLoop}/era`,
  lsbPower: `${MODULES.closedLoop}/lsbPower`,
  psdLsb: `${MODULES.closedLoop}/psdLsb`,
  conversionModel: `${MODULES.closedLoop}/conversionModel`,
  // The pooled three-source view (every visit's points, by side), fetched AFTER the report has
  // arrived so the first figures are never behind it (the PI, 2026-09-11: "prefetch the data
  // after the first figures load"). Its own slot for the same reason the grid has one.
  pooled: `${MODULES.closedLoop}/pooled`,
  // the stored closed-loop simulation, fetched after the report the same way (Phase 8)
  simulation: `${MODULES.closedLoop}/simulation`,
};

/** Every slot in the family, in no meaningful order. */
export const CLOSED_LOOP_SLOTS = Object.keys(CL).map((k) => CL[k]);

/**
 * Rebuild a set of cached answers, with exactly one request per answer.
 *
 * WHY THIS EXISTS RATHER THAN A CALL TO THE HOOK'S OWN `recompute()`. `recompute()` discards the
 * entry, then waits for the server-identity request to come back, and only then starts the fetch.
 * Discarding an entry publishes a store event; the hook re-reads on every store event; and on that
 * re-read there is no longer anything cached, so the hook's ordinary "nothing is cached, fetch it"
 * path starts a request of its own — while the deliberate one is still waiting behind the identity
 * check. Both then run. On this page that means two concurrent calls to an endpoint that fits
 * mixed-effects models through a single-threaded embedded R, which is the specific thing the
 * existing comments in `useDeploymentReport` warn against.
 *
 * So the request is left to the one path that is already correct. The server identity is refreshed
 * first, because a press of Recompute is the natural moment to notice that the server has
 * restarted, and it is best-effort exactly as it is on mount; then the entries are discarded, and
 * each hook issues the single request it would have issued for a page it had never seen.
 *
 * This is a workaround for a defect in `database/useCachedResult`, which its owner will fix; the
 * accompanying report states it precisely. When `recompute()` no longer double-fetches, every
 * caller of this function can be replaced by the `recompute` the hook already returns.
 */
export function recomputeSlots(uid, keys) {
  refreshServerIdentity();
  (keys || []).forEach((k) => invalidate(k, uid));
}

/** Every deployment slot for one participant, which is what the page's Recompute control rebuilds. */
export function recomputeClosedLoop(uid) {
  recomputeSlots(uid, CLOSED_LOOP_SLOTS);
}

/**
 * Declare that every deployment answer for one participant now rests on a changed input, without
 * discarding any of them.
 *
 * The case this exists for is a band candidate being committed on the Biomarkers page. The whole
 * family is marked rather than only the report, because each panel is about the committed band too:
 * the conversion panel fits that band, the per-era panel refits it, and a reader who has just
 * committed a different band should not see any of them presented as current.
 */
export function markClosedLoopFamilyStale(uid, reason) {
  CLOSED_LOOP_SLOTS.forEach((k) => markUpstreamChanged(k, uid, reason));
}

/**
 * The Biomarkers calibrated heat-map grid's cache slots, one PER PAIN-SCORE METRIC.
 *
 * WHY A SLOT PER METRIC, NOT ONE SLOT FOR THE WHOLE GRID. `resultCache` holds exactly one entry
 * per slot; a settings change does not add a second entry, it marks the existing one stale. A
 * single shared slot could therefore only ever hold the MOST RECENTLY viewed metric's grid — the
 * exact problem this exists to fix, since switching to any other metric would find the slot
 * "stale" (its key no longer matches) and have to recompute, even a metric already viewed once in
 * this same session. Giving each metric its own slot means each one keeps its own independent
 * cached-or-stale status, and switching between metrics already computed is a plain cache read.
 */
export function biomarkerHeatmapSlot(metricKey) {
  return `${MODULES.biomarkers}/heatmapGrid/${String(metricKey)}`;
}

/**
 * Warm one metric's grid in the background if it is not already fresh, without touching any
 * component's React state.
 *
 * This is deliberately NOT `useCachedResult` a second time: that hook is built to drive one
 * visible fetch with its own loading/error UI, and mounting one instance per background metric
 * would show loading/error state nobody asked to see for a metric the reader has not selected. A
 * failed background prefetch resolves to `null` rather than rejecting, for the same reason a
 * prefetch has no visible loading state — the reader never asked for this metric, so a transport
 * failure here must stay invisible; the ordinary on-demand fetch (via `useCachedResult`, when the
 * reader actually switches to this metric) is the real fallback and will report its own error if
 * the same request fails again.
 */
export function prefetchBiomarkerHeatmapMetric(uid, metricKey, settingsForMetric, fetchFn) {
  const key = settingsKey(settingsForMetric);
  const existing = getResult(biomarkerHeatmapSlot(metricKey), uid, key);
  if (existing && !existing.stale) return Promise.resolve(existing.bundle);
  return Promise.resolve()
    .then(fetchFn)
    .then((bundle) => {
      putResult(biomarkerHeatmapSlot(metricKey), uid, key, bundle, { why: "background prefetch" });
      return bundle;
    })
    .catch(() => null);
}
