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
 * THIS IS A WORKAROUND, AND IT HAS A LIMIT THAT IS WORTH STATING RATHER THAN REDISCOVERING.
 * `resultCache` bounds itself at six entries, and the three views between them now want nine slots
 * for one participant: five on the deployment route, three on the biomarker route, one for the
 * optimizer. Visiting all three therefore evicts. Eviction takes the least recently read entry and
 * the store touches an entry on every read, so what falls out in practice is the small panel
 * payload of whichever page was left first rather than the nineteen-megabyte biomarker bundle —
 * but that is a property of the access pattern rather than a guarantee, and a count is the wrong
 * unit for a cap when one entry is nineteen megabytes and another is twenty kilobytes. The report
 * accompanying this change asks for a larger bound, or for the store to gain a sub-key of its own
 * so that a module can hold several results and be invalidated as a unit.
 */
import { MODULES, invalidate, markUpstreamChanged } from "database/resultCache";
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
  summary: `${MODULES.closedLoop}/summary`,
  roc: `${MODULES.closedLoop}/roc`,
  era: `${MODULES.closedLoop}/era`,
  lsbPower: `${MODULES.closedLoop}/lsbPower`,
  psdLsb: `${MODULES.closedLoop}/psdLsb`,
  conversionModel: `${MODULES.closedLoop}/conversionModel`,
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
