# Task Plan: Biomarkers page — pain-score dropdown consolidation and heat-map display redesign (open item 7)

## Goal
Six-part display cleanup on the Biomarkers exploration page, per the user's own detailed spec:
1. Merge the two pain-score dropdowns into one, moved to a new full-width, red-outlined bar below
   the binarization box.
2. Remove the second (duplicate) dropdown inside the calibrated-grid section; wire that section to
   the single consolidated dropdown instead.
3. Confirm prefetching of all pain-score metrics stays as-is (already built, decision 82).
4. Redesign "How well each band tracks pain" using Plotly instead of hand-rolled SVG: fix the
   Y-axis mislabeling, shrink the grids to ~2/3 size, add persistent right-side scatter/violin
   panels with real statistics, cross-highlight the same cell on both grids, reformat every
   electrode label on the page to the Medtronic convention, and condense + enlarge the
   "how to read this" text.

## Next Step
Phase A done and verified live. Continue to Phase B (backend electrode-label enrichment for the
calibrated grid's channel display), then Phase C (the Plotly rewrite of the two heat maps with side
panels and cross-highlighting), then Phase D (condensed "how to read this" text). Paused here to
give the user a progress checkpoint before the much larger Phase C rewrite.

## Current Phase
Phase B — pending

## Phases

### Phase A: Consolidate the two pain-score dropdowns into one — COMPLETE
- [x] Removed the internal `metric`/`setMetric` state and `<select>` from `BiomarkerHeatmapGrids.js`;
      `metric` is now a plain `const metric = pageMetric || "nrs";` read from the single page-level
      dropdown. `metricLabel` (previously an unused prop) is now displayed as plain text where the
      dropdown used to be.
- [x] In `index.js`, moved the "Pain metric (drives live timeline + exploratory analysis)" `Select`
      block out of its position directly under the Biomarker Data Timeline, into a new standalone
      full-width `Grid item` directly below the black-bordered binarization/matching Card, with a
      red (#D32F2F) outline. Label text, options list and the `Select` component itself unchanged.
- [x] Built clean (one pre-existing, unrelated warning: `totalW` unused in `CellFigure`, deferred to
      Phase C since that function is rewritten there anyway). Verified live on RCS08: exactly one
      dropdown renders, in the new position below the binarization card; the timeline pain row, the
      binarization preview, and "How well each band tracks pain" (now showing "Pain score: Left Leg
      VAS" as plain text, no second dropdown) all still track it correctly.

### Phase B: Give every channel on the calibrated grid a Medtronic-style label — COMPLETE
- [x] `_band_time_sweep_channels` (`bravo_service.py`) now takes a `region_map` parameter and
      attaches `display_short`/`display_region`/`display_hemisphere`/`display_contacts` to every
      channel's sweep dict, via `analytics.format_channel` — the SAME formatter
      `_recorded_powers` already uses for "Recorded power channels" — rather than a second,
      re-derived formatter. The raw channel key stays the dict key and the value sent in every
      request field; only display fields are added. `band_time_sweep_for_participant` passes
      `_region_map(Participant, chan_order)` (also already-existing, real per-participant device
      metadata, not a static map). Deliberately did NOT attach a "@ X.X Hz" sensing frequency here
      (unlike "Recorded power channels"): this section sweeps 22 different band centres per
      channel, so no single frequency describes the channel the way it legitimately does for a
      fixed power-domain sensing band — appending one would misleadingly imply otherwise.
      `_BAND_SWEEP_RULE_VERSION` bumped (`v3_...` -> `v4_sweep_display_labels`) so a cache entry
      built before this change is never served as if it already carried the new fields.
      `ContactStrip` and the pinned-cell header in `BiomarkerHeatmapGrids.js` now read
      `display_short`/`display_region` (falling back to the old raw-key rendering only if an
      unlabeled response is ever served).
- [x] Verified live on RCS08 via a direct probe (`_agent_bridge/_probe_sweep_labels.py`, disposable
      scratch, not committed): all 6 real channels resolve correctly — e.g. `ZERO_TWO_LEFT` -> "L
      0⁻2⁺" / "Left GPi", `ZERO_THREE_RIGHT` -> "R 0⁻3⁺" / "Right VIM" — matching the existing
      "Recorded power channels" convention exactly, including which channels get which region.
      **Operational finding, disclosed rather than hidden**: the live container's gunicorn workers
      (`--reload --reload-engine poll`) did NOT pick up this edit on their own even ~5 minutes
      after the file changed and after an explicit page Recompute — the server kept serving a
      response built under the OLD cache-key version from before the edit. Diagnosed by fetching
      the live endpoint directly from the browser console and finding `display_short` genuinely
      absent from the JSON (not a frontend bug). Fixed by sending `SIGHUP` to the gunicorn master
      (its own documented graceful-reload signal — spawns new workers, drains old ones), confirmed
      by re-fetching and seeing new worker PIDs plus the new fields present. No proof was made that
      THIS SPECIFIC restart requirement is new — the poll-reloader working intermittently on a
      bind-mounted file is a plausible, previously-undocumented gap in this project's own
      operational notes; flagged here rather than assumed away.
  - **Status:** complete

### Phase C: Redesign "How well each band tracks pain" with Plotly
- [x] Fix the Y-axis: `Heatmap`'s `seconds` reads `integration_seconds_delivered` first. Verified
      live: rows now read 3s/6s/9s/15s/21s/24s/30s/45s/1m/5m (was 1s/5s/10s/15s/20s/25s/30s/45s/
      1m/5m), matching `analytics.integration_time_tile_count`'s documented rounding exactly.
- [ ] Replace the hand-rolled SVG `Heatmap` with a Plotly heatmap trace (via this project's own
      Plotly render manager), sized to ~2/3 of the current footprint.
- [ ] Add persistent right-side panels: a scatter+fitted-line panel (Pearson r + p, computed from
      the cell's own fetched points) next to the correlation grid; a violin panel (two-sample t-test
      + p, from the same points' `high`/`low` labels) next to the AUC grid — both showing channel,
      centre frequency and signal length in their titles, and both driven by click (persistent),
      not just hover.
- [ ] Cross-highlight: hovering/clicking a cell in one grid highlights the same (row, column) in the
      other.
- [ ] Reformat every electrode/channel label on this section (`ContactStrip`, the pinned-cell
      header) using Phase B's new backend fields, matching the "Recorded power channels" convention
      exactly.
- [ ] Build; verify live: labels, resize, Y-axis values, both panels' statistics, cross-highlight.
  - **Status:** pending

### Phase D: Condense the "how to read this" text
- [ ] Rewrite the four bullet notes plus the two dynamic `notes` arrays' presentation: reorder by
      priority (correlation/AUC interpretation, the circle marker, the multiple-comparison
      correction, then everything else), cut total length by roughly half, and increase the font
      size by roughly 1.5x. Follow `HOUSE_RULES_writing_and_claims.md` (this project's own
      available writing standard) and the `ps-scientific-writing` skill's §6a conciseness
      conventions loaded this session (compress tokens not sentences, one idea per clause, count
      the actual word-count reduction rather than assume it).
  - **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The Y-axis "Length of signal" mislabeling is real and already root-caused: `Heatmap`'s `seconds` array reads `sw.integration_seconds_requested \|\| sw.integration_seconds_delivered`, i.e. it prefers the REQUESTED length (1, 5, 10, 15, 20, 25, 30, 45, 60, 300 s) over the DELIVERED one. `analytics.integration_time_tile_count` (already documented, already tested) rounds every request to the nearest 3-second tile: 1s→3s, 5s→6s, 10s→9s, 15s→15s, 20s→21s, 25s→24s, 30s→30s, 45s→45s, 60s→60s, 300s→300s. The user's own three example mappings (1s→3s, "2 chunks"→6s, 10s→9s) match this exactly — confirmed correct rather than guessed. Fix: swap the preference to `integration_seconds_delivered \|\| integration_seconds_requested`. |
| Per-cell statistics for the new side panels (Pearson r + p for the scatter, a comparison stat + p for the violin) are computed CLIENT-SIDE from the (power, pain) pairs `fetchCell` already returns, not added as new backend permutation/bootstrap machinery. | The stored response only carries a per-CENTRE "best of ten lengths" row (`best_correlation_rows`/`best_auc_rows`, permutation- and bootstrap-corrected) — there is no per-arbitrary-cell p-value anywhere in the stored grid. The user's own spec says "t-test if no other exists," which reads as authorizing a plain, standard single-cell statistic (Pearson r's own parametric p-value; an unpaired two-sample t-test between the high/low groups already labeled in the fetched points) as the honest, disclosed answer for an arbitrary cell — explicitly NOT claimed to carry the same rigor (permutation, FDR) as the grid's own headline "best row" statistics, and labeled as such in the UI. |
| "Should also all be precomputed/prefetched and cached" (for the panel statistics) is read as: compute the stats once when a cell's points are fetched and store them in the SAME per-cell cache (`cellCacheRef`) already used for the raw points, not as a new instruction to eagerly fetch all ~220 cells × 6 channels before any interaction. | The existing hover/click design (decision 62, "search-first, minimal chrome") deliberately fetches a cell's data only on demand; mass-prefetching every cell would be a ~1,300-request burst against a single-threaded backend resource, contradicting this project's own established performance discipline. Flagged here as an interpretation, not a certainty, so it can be corrected if wrong. |
| Electrode labels everywhere on this page are reformatted to match the ALREADY-EXISTING, backend-built "Recorded power channels" convention (`index.js` line ~1068's `fmt()`: `"{label} ({region}) @ {center_hz} Hz"`, where `label` and `region` come from `analytics.format_channel` + `_region_map`, real per-participant device metadata — not a static demo map). | This is the one place on the page that already produces the exact Medtronic-style string the user quoted verbatim as their reference example (confirmed the quoted frequencies — 22.5/7.8/9.8 Hz left, 8.8/23.4/8.8 Hz right — match RCS08's real recorded values). Reusing it rather than inventing a second formatter keeps one source of truth, per this project's own DRY principle and its prior history of exactly this kind of drift (the cache-store consolidation, decision 30). |
| Plotly replaces the hand-rolled SVG for the two big heat maps, reversing decision 66's explicit choice, on the user's own direct instruction. | Decision 66 chose SVG specifically because "the existing figures were never built to carry per-cell hover and click" at the time — but this project's own Plotly render-manager (`Client/src/graphing-utility/Plotly/index.js`) already wires `plotly_click`/`plotly_relayout` handlers elsewhere, so the original constraint no longer rules Plotly out. Recorded here as a reversal, not silently overwritten, per CLAUDE.md's own rule that a superseding decision must say so. |
| No "/ps-scientific-writing" skill exists in this repository's `.claude/skills/` or anywhere else searched on this machine. | The condensed "how to read this" text will instead follow this project's own, already-available `HOUSE_RULES_writing_and_claims.md` (plain language, defined terms, no banned jargon/constructions) — the applicable written standard for this repository. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
