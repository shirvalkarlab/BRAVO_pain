# Findings & Decisions

## Requirements
Open item 7's display cleanup, specified by the user in full detail across six parts: merge the
two pain-score dropdowns, remove the duplicate, confirm prefetching is unchanged, and redesign the
"How well each band tracks pain" section (Plotly, resized grids, side panels with real statistics,
cross-highlighting, Medtronic-style electrode labels everywhere, condensed "how to read this" text).

## Research Findings
- `BiomarkerHeatmapGrids.js` (704 lines, read in full) has its OWN internal `metric`/`setMetric`
  state and `<select>` (the "second dropdown," positioned at the top of "How well each band tracks
  pain"), synced from the page-level `pageMetric` prop only via a one-way effect — so it can
  diverge from the page-level dropdown. That page-level dropdown lives in `index.js` directly below
  `BiomarkerDataTimeline` (the "first dropdown").
- Y-axis root cause confirmed by reading `analytics.integration_time_tile_count` and
  `BAND_TIME_SWEEP_SECONDS` in `BRAVO/modules/Biomarkers/routines/analytics.py`: `Heatmap`'s
  `seconds` array prefers `integration_seconds_requested` over `_delivered`, showing the length
  ASKED FOR rather than the length the 3-second tile cache actually DELIVERS. The rounding rule
  (`round(requested / 3) * 3`, minimum one tile) reproduces the user's own three example mappings
  exactly.
- No per-arbitrary-cell p-value exists anywhere in the stored/served grid — only per-CENTRE "best
  of ten lengths" rows (`best_correlation_rows`/`best_auc_rows`) carry a rigorous (permutation- and
  bootstrap-corrected) p-value. `band_time_sweep_from_power`'s full return dict was read in full to
  confirm this (`BRAVO/modules/Biomarkers/routines/analytics.py` ~5896-6070).
- The already-correct Medtronic-style electrode label ("L 0⁻3⁺ (Left GPi) @ 22.5 Hz") is built by
  `index.js`'s own `fmt()` helper (~line 1068) from `data.recorded_powers`, itself built server-side
  by `bravo_service._recorded_powers` using `analytics.format_channel` (a real, existing, reusable
  formatter — NOT something to write from scratch) and `bravo_service._region_map` (real
  per-participant device metadata, `Electrode.custom_name`/`.target` — explains why the region
  string is already "Left GPi" rather than a bare "GPi"). The calibrated grid's own channel display
  (`ContactStrip`, the pinned-cell header) currently shows the RAW enum-style channel key instead
  (`ch.replace(/_/g, " ")`, e.g. "ZERO TWO LEFT") — `_band_time_sweep_channels` does not attach a
  formatted label to each channel's sweep object today.
- Plotly's click/hover event handling is already used elsewhere in this codebase's own render
  manager (`Client/src/graphing-utility/Plotly/index.js`, `click:`/`plotly_relayout` handlers), so
  decision 66's original reason for choosing hand-rolled SVG over Plotly (no hover/click support at
  the time) no longer rules Plotly out.
- No "/ps-scientific-writing" skill exists anywhere on this machine (checked `.claude/skills/` and
  a filesystem-wide search) — the condensed doc text will follow this project's own
  `HOUSE_RULES_writing_and_claims.md` instead.

## Technical Decisions
See task_plan.md's Decisions Made table.

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- `DECISIONS_and_open_items.md` decisions 62 (search-first minimal chrome), 63 (BH correction), 66
  (Track A build, the SVG choice being reversed here), open item 7 (this task's own origin).
