# Progress Log

## Session: 2026-09-08

### Current Status
- **Phase:** 1 - Reconnaissance
- **Started:** 2026-09-08

### Actions Taken
- New, independent plan directory created (`2026-09-08-biomarkers-heatmap-plotting-redesign`) per
  CLAUDE.md decision 36, rather than adding this to the cache-store plan.
- Wrote task_plan.md's 5 phases: reconnaissance, design (with an explicit go-ahead gate before
  code), implementation, testing/verification, delivery.
- Browser login attempts failed repeatedly (this session's browser tool is a fresh, non-persistent
  sandboxed browser — not the user's own screen, no shared cookies); pivoted to rendering the real
  panel from real backend data with real plotting code instead of a screenshot. Traced the panel's
  true data source to `analytics.timedomain.spectral_feature_importance` (corrected an earlier,
  wrong claim in this conversation that it was `compute_psd_pain_correlation`). Pulled live RCS08
  data via the bridge, reconstructed the exact Plotly spec from `BiomarkerAnalytics.js` in Python,
  rendered with kaleido (throwaway venv at `/tmp/plotly_venv`), sent to the user.
- User confirmed: kill the panel, it's "an unnecessary duplicated analysis."
- Removed it end to end: backend (`spectral_feature_importance` task + its now-dead
  `pro_lsb_spectrum_by_channel` parameter), frontend (`SpectralFeatureImportance` component, ~600
  lines, plus the stale subtitle text describing its removed methodology). Proven on RCS08:
  254,741 fields removed (all under `timedomain.*`), 0 of 7,150,676 common fields changed.
  Container suite 593/0. Frontend rebuilt clean after fixing two compile errors from a leftover
  `scan` reference.
- Timed the slow hover-preview's real backend endpoint (`band_time_sweep_cell_for_participant`) on
  RCS08, per-step: ~2.9s flat every call, dominated by redundant `_load_recordings`/REDCap-fetch/
  event-block work the parent grid request already did once. The LSB tile cache itself is fast
  (13ms) — not the bottleneck. No Plotly rendering bottleneck exists anywhere in this page's grids
  (they're hand-rolled SVG, not Plotly, by deliberate prior design choice).
- Next: asked the user to disambiguate their two click-behavior sentences (small-multiples strip
  vs. the two main grids) before implementing grid enlargement / click interaction / hover-speed fix.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|

### Errors
| Error | Resolution |
|-------|------------|

## Session 2026-09-08 (continued) — the pain-report rule and the Plotly question

- Loaded the BRAVO session-rules and Plotly skills as asked. Answered the Plotly question with
  reasoning rather than repetition: no, it would not be faster. The grids are ~220 plain SVG rects
  (sub-millisecond); the measured cost was entirely backend. Plotly adds per-interaction figure and
  event overhead, and this project has already paid for its re-render lifecycle once (decision 5).
- Investigated the PI's "same hash check" premise against the code and found it cannot hold:
  `_pro_table_digest` hashes the table AFTER the fetch, so it dedups a write but can never save a
  fetch, and there is no metadata-only REDCap call here to ask instead. Said so plainly rather than
  building something that merely looked like a freshness check.
- Built his rule instead, with no clock in it: `_PRO_BUILD_CACHE` holds the table the most recent
  REAL fetch produced; every building endpoint still fetches fresh and thereby re-seeds it; only the
  read-only drill-downs read it back. First implemented as a 60 s TTL, then replaced when he
  specified "until Recompute or a new load" — the TTL is gone entirely.
- Shared `_RECORDINGS_SETUP_MEMO` between the grid build and the drill-down, and passed the grid's
  already-loaded `td` in so nothing is read twice. Placed AFTER the grid's stored-response return,
  deliberately: an earlier draft put it before and would have slowed the store-served path that
  decision 38 engineered — caught by reading that path rather than by a test.
- Proof by counting real fetches (wrapping `_load_pros_raw`): build 1, six hovers 0, Recompute 1,
  three more hovers 0. Hover times 0.024-0.053 s against ~2.9 s at the start of this work.
  Equality: held-vs-fresh hover 1,335 fields 0 differences; grid build fresh-vs-fresh (store
  bypassed both sides) 27,865 fields, 19 differing, all wall-clock `*_seconds`. Container 593/0.
- Recommended AGAINST building the "one big pre-joined matrix" for now: with hovers at ~30 ms the
  join it would eliminate is no longer measurable, so it would add a new cache shape and its own
  invalidation surface for no observable gain. Left as the PI's call.
