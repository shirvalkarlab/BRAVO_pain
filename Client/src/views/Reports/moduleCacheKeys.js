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

/** Validate access and source revisions before invalidating mounted result hooks. */
export async function recomputeSlots(uid, keys) {
  await refreshServerIdentity(uid);
  (keys || []).forEach((key) => invalidate(key, uid));
}

/** Every deployment slot for one participant, which is what the page's Recompute control rebuilds. */
export function recomputeClosedLoop(uid) {
  return recomputeSlots(uid, CLOSED_LOOP_SLOTS);
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
