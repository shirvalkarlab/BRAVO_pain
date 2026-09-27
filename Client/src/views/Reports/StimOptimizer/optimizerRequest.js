/**
 * THE REQUEST THIS VIEW SENDS, WRITTEN OUT IN FULL RATHER THAN LEFT TO THE SERVER'S DEFAULTS.
 *
 * The endpoint takes six optional parameters besides the participant — the pain sites, the
 * hemispheres, the wash-in exclusion window, the figure backend, and the depth and width of the
 * forward simulation the two-stage path's own Stage 1 runs. They are documented on
 * `QueryStimOptimizer` in `BRAVO/Server/APIs/DataAnalysis.py` and applied in
 * `modules/StimOptimizer/bravo_service` `run_for_participant`, and the values below are exactly
 * those documented defaults. The request is therefore unchanged in what it asks the server for.
 *
 * What changes is that it is now written down here, which is what allows the result cache to key
 * on it. A cache key has to name everything that changes the answer; a request that relies on the
 * server's defaults names none of it, so a key derived from such a request would be blind to the
 * very parameters this page is about.
 *
 * Moved here from index.js on 2026-09-26 so the clinic-sheet export sends the SAME request: the
 * export endpoint rebuilds the Stim Optimizer response from its request, and a request missing
 * `Backend: "none"` was a different stored answer (a full recompute on every click, and a third
 * stored response in a kind that keeps two).
 */
export const OPTIMIZER_REQUEST = {
  Sites: ["left_leg", "back"],
  Hemispheres: ["Left", "Right"],
  WashinMin: 1.0,
  Backend: "none",
  NBatches: 3,
  Q: 4,
};
