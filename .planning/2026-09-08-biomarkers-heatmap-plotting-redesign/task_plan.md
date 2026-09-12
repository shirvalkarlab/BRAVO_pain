# Task plan — Biomarkers heat-map plotting redesign

## Goal

Remove the older scatter-and-violin drill-down panel from the Biomarkers exploration page; enlarge
the calibrated correlation/AUC grids with their own proper axes; and make the hover-preview and
click-through scatter+violin panel load fast.

**CORRECTED (findings.md):** the older panel is fed by `analytics.timedomain.spectral_feature_importance`
(a continuous 5 Hz-step scan, calibrated LSB by DEFAULT since a 2026-06-27 change, self-described
"not a validated biomarker" — still inferior to the calibrated sweep, but not for the "raw
uncalibrated Welch power" reason first stated in this conversation). `streaming_psd.compute_psd_pain_correlation`
(the actual decisions-57-61 routine) turned out to have a live production call path but its result
reaches no frontend field at all — confirmed dead in the served UI, left untouched, out of scope.

**RESOLVED (user, directly):** the two click-behavior sentences describe the SAME two main grids,
said twice — clicking a cell already shows a scatter+violin panel today; the ask was purely to
enlarge the grids and make that click (and the hover preview) fast. No new interaction model.

## Next Step

**Everything asked for is built and proven; hovers now cost 24-53 ms against ~2.9 s before.** Two
things remain outstanding and neither is code: a real logged-in browser check of the finished page
(this session's browser tool could not hold a login — see progress.md), and the PI's own call on
whether the "one big pre-joined matrix" he floated is still wanted now that hovers are at ~30 ms
without it.

## Current Phase

Phase 6 complete (all six phases complete)

## Phases

### Phase 1: Reconnaissance — see and read what exists today
- [x] Get the older scatter-and-violin drill-down panel in front of the user (reconstructed from
      real RCS08 data + the real Plotly spec, no browser needed — see findings.md)
- [x] Read `BiomarkerAnalytics.js` (the older panel) fully; identified its real data source
      (`analytics.timedomain.spectral_feature_importance`, NOT `compute_psd_pain_correlation`)
- [x] Confirmed with the user: KILL the `spectral_feature_importance`-fed scatter+violin panel
      entirely — "an unnecessary duplicated analysis."
- [x] Read `BiomarkerHeatmapGrids.js` in full — finding: the grids and their scatter+violin
      click-through are ALREADY hand-rolled SVG, not Plotly (decision 66, deliberate, for per-cell
      hover/click). No Plotly rendering bottleneck exists anywhere on this page.
- [x] Read the backend hover-preview endpoint (`band_time_sweep_cell_for_participant`) end to end
      and TIMED each step on RCS08: ~2.9s flat per call, every time. `_load_recordings`(TD) 1.27s,
      REDCap fetch 0.65s, `_load_recordings`(PSD) 0.38s, `_event_psd_lsb_blocks` 0.33s. The LSB tile
      cache itself (`_raw_lsb_cache_cached`) was already fast, 0.013s — not the bottleneck.
- **Status:** complete

### Phase 2: Design
- [x] Grid sizing: full-width stacked (was two half-width side-by-side), SVG logical width 900,
      taller rows (30px vs 20px), larger tick font (11px vs 9px), and NEW axis titles ("Band centre
      (Hz)", "Length of signal") — the grids previously had tick numbers only, no axis label.
- [x] Click interaction: RESOLVED by the user as "no change needed" — see Goal correction above.
- [x] Diagnosed the hover slowness with three ranked, TIMED hypotheses (not a guess): (1) redundant
      recordings/PSD-block reload on every hover — CONFIRMED, ~2s of the 2.9s; (2) the LSB tile
      cache itself — RULED OUT, already 13ms; (3) the REDCap pain-report fetch — a real but smaller
      cost (0.65s), and per decision 22 this project explicitly forbids caching it, so it is not a
      candidate to remove.
- [x] No Plotly-specific optimization write-up was needed — there is no Plotly on this page to
      optimize; the fix is backend-side (stop redoing work the parent request already did).
- **Status:** complete

### Phase 3: Implementation
- [x] Removed the older scatter-and-violin drill-down panel. Backend: `spectral_feature_importance`
      dropped from `bravo_service.py`'s `td_tasks` (its `pro_lsb_spectrum_by_channel` parameter also
      removed from `_compute_analytics`, now genuinely dead otherwise); `_live_pro_lsb_spectrum`'s
      call KEPT because `live_match_stats` (a live UI caption) still needs it. Frontend: the
      `<SpectralFeatureImportance>` render and its ~600-line component deleted from
      `BiomarkerAnalytics.js`; the wrapping section's subtitle rewritten (it described the removed
      scan's own methodology) to describe only what remains there, the sliding
      correlation-over-time heatmap. Proven on RCS08: 254,741 fields removed, every one under
      `timedomain.*`, 0 of 7,150,676 common fields changed value. Container suite 593/0.
- [x] Enlarged the calibrated grids with their own axes (`BiomarkerHeatmapGrids.js`'s `Heatmap`):
      see Phase 2's sizing decision. Padding enlarged (46/22/4/4 → 78/46/8/12) to make room for the
      new titles; SVG uses `viewBox` + `width="100%"` so it scales down on a narrow viewport instead
      of overflowing, without changing any cell/label coordinate math.
- [x] Click-on-cell: no change needed (Phase 2).
- [x] Fixed the hover/click-through speed: new `_hover_cell_recordings_setup` in-process memo
      (mirrors the existing `_RAW_LSB_CACHE_MEMO` pattern), holding ONLY recording-derived data
      (td, psd_list, event/montage PSD blocks, chan_order, channels) — per decision 22, recordings
      may be cached with no expiry. The pain-report fetch (`_load_pros`) is deliberately OUTSIDE
      this memo and still runs fresh on every single call, exactly as before, because decision 22
      forbids caching it. Proven on RCS08: cold call 4.28s; three subsequent calls across three
      DIFFERENT contact pairs (the memo is participant-level, not per-channel) each 0.90–1.25s —
      roughly a 3–4x speedup. Equality proof: 1,335 fields compared between a cold and a warm call
      for the identical cell, 0 differences. Container suite re-run clean, 593/0.
- **Status:** complete

### Phase 4: Testing & verification
- [x] Container suite run after every change in this plan: 593/0 throughout (no host-suite
      membership for Biomarkers, so container is the only suite that applies here).
- [x] Field-count/difference-count equality proofs run for both changes that touch a served number
      (the panel removal, the hover-cache memo) — see Phase 3 for both proofs' numbers. Zero
      scientific values moved in either case.
- [x] Frontend rebuilt (exit 0) after each change, including two follow-on compile-error fixes (a
      stale `scan` variable reference left behind by the panel removal). Confirmed the new axis
      title string ("Band centre (Hz)") reached the served chunk (`806.8d4bc2d4.chunk.js`).
- [ ] Real-browser visual check of the finished page: NOT completed. This session's browser tool is
      a fresh, non-persistent sandboxed browser (not the user's own screen), and repeated
      self-registration/login attempts this session did not produce a working authenticated session
      against real RCS08 data. Flagged honestly rather than claimed.
- **Status:** complete (with the one honest exception above)

### Phase 5: Delivery
- [x] Update `DECISIONS_and_open_items.md` with the new decision(s) and proof numbers (decisions 77
      and 78; decision 22 struck through as amended by 78)
- [x] Report to the user with the timings and proof numbers
- **Status:** complete

### Phase 6: The pain-report rule, and the Plotly question
- [x] Answered "would this be faster in Plotly": no. The grids are ~220 SVG rects (sub-millisecond
      to draw) and the measured cost was entirely backend; Plotly would add figure-construction and
      event overhead per interaction, and this project has already paid for Plotly's re-render
      lifecycle once (decision 5, closed-loop figures flashing back to their loading state).
- [x] Established why the "same hash check" cannot skip the fetch: `_pro_table_digest` hashes the
      table AFTER it is fetched. Reported that honestly rather than building something that only
      looked like a freshness check.
- [x] Built the PI's rule instead: hold the report table until the next build. `_PRO_BUILD_CACHE`
      + `_remember_pain_reports` (seeded by every real fetch inside `_load_pros`) +
      `_pain_reports_for_drilldown` (read by the drill-downs only). No clock anywhere in it.
- [x] Shared `_RECORDINGS_SETUP_MEMO` between the grid build and the drill-down, placed after the
      grid's stored-response return so a store-served grid still pays nothing extra.
- [x] Proven on RCS08 by counting real fetches: build = 1, six hovers after = 0 (0.024-0.053 s
      each), Recompute = 1, three hovers after = 0. Equality: held vs fresh hover, 1,335 fields,
      0 differences; grid build fresh-vs-fresh with the store bypassed, 27,865 fields, 19 differing,
      all wall-clock timing fields. Container suite 593/0.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Kill the `spectral_feature_importance`-fed scatter+violin panel entirely, backend and frontend, rather than leave the backend computing it unused. | User, directly: "kill it because its an unnecessary duplicated analysis." The calibrated band-by-length grid already answers the same question with a stronger correction. |
| Keep `_live_pro_lsb_spectrum`'s call in `run_for_participant` even though its first return value (`pro_lsb_spectrum`) is now unused, because its second return value (`live_match_stats`) still feeds a live UI caption. | Untangling the two would mean refactoring `_live_pro_lsb_spectrum` itself — a bigger, unnecessary change for a harmless unused local variable. |
| RESOLVED: the two click-behavior sentences describe the same two main grids, not two different UI elements. No new interaction model built. | User's direct answer to the disambiguating question. |
| Cache the hover-cell endpoint's recordings/PSD-block setup (not the pain-report fetch) in a short, participant-keyed in-process memo, mirroring the existing `_RAW_LSB_CACHE_MEMO` pattern. | Decision 22 explicitly allows caching recordings with no expiry and explicitly forbids caching pain reports; the timed breakdown showed the recordings/block setup was ~2s of the 2.9s cost and the REDCap fetch only 0.65s, so this is the only piece safe and worthwhile to cache. |
| Grids enlarged by stacking full-width (was two half-width columns) rather than just widening the SVG in place. | A wider SVG inside an unchanged half-width column would either overflow or need to shrink back down; stacking gives the intended larger size real room. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| `Edit` tool's exact-string matching repeatedly failed on blocks containing special Unicode characters (em-dash, §, ρ, Δ, µ) copied from `Read` output. | Switched to line-range-targeted `sed`/Python surgery (by line number, not string content) for the two large deletions in `BiomarkerAnalytics.js`. |
| After deleting `SpectralFeatureImportance`, the frontend build failed with `'scan' is not defined` — a wrapping section's subtitle text still referenced the deleted component's own `scan` variable. | Found via the build's own error output (not guessed); rewrote that subtitle to describe only what remains in that section. |
| First timing-attribution probe script imported `from database import models` (wrong path for this repo). | Fixed to `from Server import models`, matching `bravo_service.py`'s own import. |
