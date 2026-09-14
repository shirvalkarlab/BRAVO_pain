/**
 * The two-stage plan -- open loop first, then the check that decides whether closed loop may
 * start, then closed loop -- fetched as a SECOND request to the Stim Optimizer endpoint.
 *
 * FETCHED AFTER THE PAGE'S OWN RESPONSE, NOT WITH IT. The page's first paint waits on the
 * open-loop surfaces; the plan is a further ten seconds or so of server work on top of that
 * (`two_stage.seconds` on RCS08, 2026-09-12: 10.3 s inside a 61.5 s request) and it is not what
 * the reader came for first. So this request is enabled only once the page's own `data` has
 * arrived, and it sends the page's request unchanged plus `TwoStage: true`. The server keys its
 * stored response on that flag (`_response_signature` in `StimOptimizer/bravo_service.py`), so a
 * request without the flag is never handed the copy that carries the plan and one with it is
 * never handed the copy without.
 *
 * ITS OWN CACHE SLOT (`STIM.twoStage`). The cache keeps one answer per slot per participant and
 * hands a request whose settings differ the held answer marked stale rather than fetching, so if
 * this shared the page's slot, whichever of the two requests answered second would be shown as
 * the answer to the first. The Closed-Loop page's grid met exactly that (decision 113).
 *
 * THE OVERRIDE KEYS ARE REQUEST-ONLY. `TwoStageOverrideReason` / `TwoStageOverrideBy` (and the
 * explore-outside-the-adaptive-range pair being added on the server) are accepted by the endpoint
 * but no control on the page sends them yet; the card says so in one line.
 */
import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { STIM } from "views/Reports/moduleCacheKeys";

export default function useTwoStagePlan({ participantUid, baseRequest, afterMain, enabled = true }) {
  const settings = { ...(baseRequest || {}), TwoStage: true };
  const body = { ParticipantId: participantUid, ...settings };
  const cached = useCachedResult({
    moduleKey: STIM.twoStage,
    uid: participantUid,
    // The participant is the other half of the slot, so it is left out of the key (the same rule
    // the page's own request follows).
    settings,
    // `afterMain` is the page's own `data`; null until the surfaces have their answer.
    enabled: enabled !== false && !!participantUid && !!afterMain,
    fetcher: () => SessionController.query("/api/queryStimOptimizer", body)
      .then((response) => (response && response.data) || null),
  });
  const raw = cached.data;
  // The block lives under `two_stage` on the same response the page reads. A response that
  // arrived without it (an older server, or the flag dropped on the way) is reported as such
  // rather than shown as an empty plan.
  const block = raw && raw.two_stage ? raw.two_stage : null;
  let err = cached.err || null;
  if (!err && raw && raw.available === false) err = raw.reason || "the optimizer response was unavailable";
  if (!err && raw && !block) err = "the response carried no two-stage block";
  if (!err && block && block.available === false) err = block.reason || "the two-stage plan was unavailable";
  return {
    data: block && block.available !== false ? block : null,
    loading: cached.loading,
    err,
    stale: cached.stale,
    recompute: cached.recompute,
    requestBody: body,
  };
}
