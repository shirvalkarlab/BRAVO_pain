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
Phases A, B, C, C.1-C.5 are all done and verified live. Only Phase D remains:
condense the "how to read this" drawer text (confirmed, live, to be exactly as verbose as the spec
described — a full screen of bullet points) by roughly half, reorder by priority, and enlarge the
font, following this project's `HOUSE_RULES_writing_and_claims.md` and the `ps-scientific-writing`
skill's §6a conciseness conventions loaded this session.

## Current Phase
Phase D — pending

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

### Phase C: Redesign "How well each band tracks pain" with Plotly — COMPLETE
- [x] Fix the Y-axis: `Heatmap`'s `seconds` reads `integration_seconds_delivered` first. Verified
      live: rows now read 3s/6s/9s/15s/21s/24s/30s/45s/1m/5m (was 1s/5s/10s/15s/20s/25s/30s/45s/
      1m/5m), matching `analytics.integration_time_tile_count`'s documented rounding exactly.
- [x] Replaced the hand-rolled SVG `Heatmap` with a Plotly heatmap trace via this project's own
      `PlotlyRenderManager` (`graphing-utility/Plotly`), sized to 600×(rows*20+60) — roughly 2/3 of
      the previous 900-wide, rows*30+80 footprint. Y-axis is categorical (string labels) so every
      row keeps equal visual height regardless of how irregular the underlying seconds values are,
      matching the original SVG's layout exactly. One real bug found and fixed before this worked
      at all: `setXlabel`/`setYlabel` need `fig.subplots(1, 1)` called first to populate
      `this.layout.xaxis`/`yaxis` (every other consumer of this class in the codebase does this;
      skipping it crashed the whole page with "Cannot set properties of undefined").
- [x] Added persistent right-side panels, hand-rolled SVG (kept, not Plotly — these are single,
      non-gridded plots with no per-cell hit-testing problem, so the reason for choosing Plotly
      over SVG for the heatmaps does not apply here): `ScatterFitPanel` (Pearson r + its own
      parametric two-tailed p-value, computed from the cell's own fetched points — implemented via
      a standard regularized-incomplete-beta Student's-t p-value, verified against known reference
      values before use: t=2.228,df=10→p=0.0500; r=0.5,n=30→p=0.0049, both matched) next to the
      correlation grid; `ViolinPanel` (Welch's two-sample t-test between the high/low groups, same
      p-value machinery) next to the AUC grid. Both titled with channel, band centre and length of
      signal (using the DELIVERED seconds label, matching the axis — the REQUESTED value is still
      what's sent to the cell drill-down endpoint, which keys its own lookup on it; these were kept
      as two separate fields, `seconds`/`secondsDisplay`, after finding they'd shown different
      numbers for the same row in an early live check). Both statistics are explicitly labelled in
      the UI and in the "how to read this" drawer as plain, single-cell, uncorrected numbers —
      never conflated with the grid's own permutation- and bootstrap-corrected headline statistics.
      Driven by CLICK only (persistent) — hover no longer fetches or shows a preview, per a
      deliberate reading of the spec ("persist when clicked"); it only moves the cross-highlight.
- [x] Cross-highlighting: hover and pinned state are now ONE shared `{row, col}` per interaction
      (not two separate per-grid states as before), read by both `PlotlyHeatmap` instances — a
      click on EITHER grid populates BOTH panels and highlights that cell on BOTH grids at once
      (drawn as a small square-outline marker at the cell's own data coordinates, not a raw
      shape indexed by row/col, which is unreliable on a categorical axis).
- [x] Every electrode/channel label on this section (`ContactStrip`, the panel titles) now uses
      Phase B's backend `display_short`/`display_region` fields, matching "Recorded power
      channels" exactly.
- [x] Built clean (zero warnings for this file, including the pre-existing `totalW` one, gone now
      that the old `CellFigure` it lived in was replaced). Verified live on RCS08: hovering shows
      the cross-highlight and a native Plotly tooltip with no fetch; clicking either grid populates
      both panels with real numbers and titles (e.g. "R 0⁻3⁺ (Right VIM) · 20.5 Hz · 30s of signal",
      "Pearson r = -0.120, p = 0.0470 (n = 276)", "Welch t(200.7) = -0.17, p = 0.8672 (high n=100,
      low n=176)") and highlights the same cell on the other grid; no console errors across
      multiple hover/click cycles on both grids.
  - **Status:** complete

### Phase C.1: Live-feedback refinements to the Plotly redesign — COMPLETE
Requested directly after Phase C shipped, from watching it live: (1) remove the heatmap's axis
GRIDLINES specifically (the faint reference lines through every tick), keeping the tick labels
themselves; (2) the heatmap size "was a little better before" — increase by 25% from the first
Plotly pass; (3) the axes originally asked for belonged on the side panels (scatter, violin), not
the heatmaps — those panels had only a bare text label, no real axis; (4) the panel title is
identical on both panels (pure duplication) — keep it once, above the scatter panel, at double the
font size.
- [x] Heatmap: `xaxis`/`yaxis` layout now sets `showgrid: false, zeroline: false` on both axes
      (cell borders via `xgap`/`ygap` already separate the cells; the added gridlines were on top
      of those and just added noise). Tick labels are untouched.
- [x] Heatmap size: default `width` 600 → 750; `height` formula `rows*20+60` (min 180) →
      `rows*25+75` (min 225) — a 25% increase on both dimensions.
- [x] Added `niceTicks()` (the standard 1/2/5×10^n round-number tick algorithm) and a shared
      `PanelAxes` component (axis lines + tick marks + numeric labels) to both `ScatterFitPanel`
      (x = band power, y = pain) and `ViolinPanel` (y = band power only — x is the two categorical
      groups, already labelled "High pain"/"Low pain" under each violin, so no numeric x-axis
      applies there).
- [x] `PanelTitle` now renders ONLY inside `ScatterFitPanel`; removed from both of `ViolinPanel`'s
      branches. Font size doubled, 11.5px → 23px, now that it is the one copy carrying this
      information for both panels. Height budgets adjusted (`ScatterFitPanel`'s reserved space
      64px, up from 46px, to fit the larger title without crowding the plot).
- [x] Built clean; verified live on RCS08: heatmap cells read as clean solid blocks with tick
      labels but no grid lines, are visibly larger, and clicking a cell shows one large title only
      above the scatter panel ("R 0⁻3⁺ (Right VIM) · 17.5 Hz · 15s of signal") with both the
      scatter panel (Band power 100–500, Pain 20–80, both with axis lines and tick marks) and the
      violin panel (Band power axis only, ticked and labelled) rendering real axes for the first
      time. No console errors.
  - **Status:** complete

### Phase C.2: Second round of live-feedback refinements — COMPLETE
Requested directly, in three follow-up messages while C.1 was still building: (1) remove the
heatmap's axis LINES and TICK MARKS too (not just gridlines), and label the x-axis with the actual
band-centre value every 3rd cell instead of Plotly's own auto-picked round numbers; (2) the
scatter/violin panels didn't actually end up matching the heat maps' new, larger height (a real
miss — `panelHeight` in the main component still used the OLD pre-25%-increase formula), make them
square with more margin so the violins don't run close to the edges, and double the tick-label
font; (3) also scale up the axis TITLE captions (not just tick labels), make the y-axis title
vertical (it had stayed horizontal, unlike every other axis title on this page), and name the
actual units (band power is always device LSB on this page; pain names whichever score is
selected, since the same axis serves NRS/VAS/MPQ/etc.); (4) remove the modebar (zoom/pan/download
toolbar) that Plotly shows on hover over the heat maps.
- [x] Heatmap axes: added `showline: false, ticks: ""` to both `xaxis` and `yaxis` (removes the
      axis line and tick marks; tick labels, controlled separately, are untouched). X-axis now
      uses `tickmode: "array"` with explicit `tickvals`/`ticktext` built from `centers.filter((c,i)
      => i % 3 === 0)` — exactly the "every 3rd band centre" rule the original SVG grid used —
      instead of Plotly's own automatic tick choice.
  - **Status:** complete
- [x] Extracted one shared `heatmapHeight(rows)` function, called by both `PlotlyHeatmap` (for its
      own `height`) and the main component (for `panelHeight`, passed to both side panels) — the
      two cannot drift out of sync again the way they just did.
  - **Status:** complete
- [x] `ScatterFitPanel`/`ViolinPanel`: canvas is now square (`w = h`, both derived from the shared
      `panelHeight` minus each panel's own header reservation), `pad` widened 34→62 to fit the
      larger tick labels and the rotated axis title, violin centre fractions tightened
      (0.28/0.72→0.3/0.7, half-width 0.2→0.17×w) so neither violin's tails approach the edge at the
      new, much larger size. `PanelAxes` tick-label font doubled, 8px→16px.
  - **Status:** complete
- [x] Axis title captions enlarged 9px→13px; the y-axis title on both panels is now rotated -90°
      (matching the heat maps' own "Length of signal" convention) instead of sitting horizontally
      at the top-left; both now name real units — "Band power (LSB)" (this page's own established
      abbreviation for the device's least-significant-bit units, used throughout, e.g. "Recorded
      power channels") and "Pain (`${metricLabel}`)" (the actual selected score — NRS/VAS/MPQ/etc.
      — threaded down from the main component's own `metricLabel` prop, since the same axis serves
      whichever pain metric is currently selected).
  - **Status:** complete
- [x] Modebar removed from both heat maps specifically (not from `PlotlyRenderManager` itself,
      which is shared by 10+ other pages and has no config-override mechanism to change safely):
      imported `Plotly` directly (same `plotly.js-dist` package the render manager itself imports)
      and called `Plotly.react(divId, fig.traces, fig.layout, { displayModeBar: false, responsive:
      true })` immediately after `fig.render()`, re-applying the identical data/layout with the
      modebar switched off, scoped only to these two divs.
  - **Status:** complete
- [x] Built clean; verified live on RCS08: heatmap cells show floating tick labels with no axis
      line, no tick marks, and the x-axis reads real band centres (9,12,15,18,21,24,27,30) every
      3rd column; the scatter and violin panels are visibly close in height to the heat maps now
      (both driven by the one shared formula); violins render with clear margin on both sides; both
      panels show a vertical, unit-labelled axis title ("Pain (Overall VAS)", "Band power (LSB)")
      at a larger font; hovering a heat map shows its cross-highlight tooltip with no modebar
      appearing anywhere on the chart. No console errors.
  - **Status:** complete

### Phase C.3: Fix the panel-sizing regression from C.2 — COMPLETE
C.2's "match the heat map height" fix was structurally wrong: it treated the panel's own title and
statistics text as space to CARVE OUT of a fixed total height shared with the heat map, so the
actual plot inside kept shrinking every time the title got bigger — the opposite of matching. The
heat map's own section heading ("Correlation with pain...") sits ABOVE its box, outside the height
budget entirely; the panels' title was incorrectly being counted INSIDE theirs. Called "terrible"
and "badly positioned" directly, correctly.
- [x] `ScatterFitPanel`/`ViolinPanel`: the plot is now a full-size square literally equal to
      `heatmapHeight(rows)` (`h = height; w = h;`, no subtraction), with the title/statistics text
      rendered as ordinary content ABOVE it — exactly parallel to how the heat map's own heading
      sits above its own box. The outer `MDBox`'s fixed `sx={{height}}` constraint is removed on
      the rendered branch (kept only on the loading placeholder, for visual stability while
      waiting) so the natural content flow no longer needs to fit inside a budget smaller than the
      plot itself.
- [x] `pad` reworked from a height-fraction formula to a fixed value (50px) sized to the actual
      room the enlarged tick numbers and the rotated axis title need without colliding, since the
      panel's true size is effectively constant (10 length-of-signal rows, always) rather than
      genuinely variable — a fraction was solving a problem that doesn't exist and made the true
      constraint (legibility) harder to reason about.
- [x] Stats-line text enlarged 11px→15px on both panels (direct feedback: "all the stats text is
      too small").
- [x] Violin panel's "High pain"/"Low pain" category labels enlarged 9px→16px, matching the
      tick-label size used everywhere else on both panels (direct feedback: should "match the
      other plots' size").
- [x] Rotated y-axis title's `x` position tightened 16→12 on both panels to keep clear of the
      tick-label text now that `pad` shrank from C.2's 62 to 50.
  - **Status:** complete
- [x] Built clean; verified live on RCS08: the scatter and violin plots are now visibly close in
      size to their heat maps (previously dramatically smaller and oddly offset); axes fill most of
      each panel with comfortable margins; "High pain"/"Low pain" and the statistics line are
      clearly larger; violins show no clipping. No console errors. A stray blue "highlighted text"
      appearance on some tick labels in one screenshot was confirmed to be an ordinary text-
      selection artifact from a prior click, not a rendering bug -- gone on the next click.
  - **Status:** complete

### Phase C.4: Move the pinned-cell title and stats out of the panel boxes; fix panel fill and axis-label collision; order the thumbnail strip; remove the irrelevant binarization warning — COMPLETE
Four rounds of direct live feedback on the C.3 layout, addressed in sequence.
- [x] The big pinned-cell title (`PanelTitle`) moved out of the scatter panel entirely into its own
      Grid row shared with `ContactStrip`, bottom-aligned (`alignItems="flex-end"`) so the title's
      floor lines up with the thumbnail strip's floor. The scatter panel's stats line
      (`ScatterStatsLine`, split out of the old combined `ScatterFitPanel`) moved into a second,
      separate, top-aligned Grid row alongside the "Correlation with pain — depends only on
      matching" heading. `ScatterPlotSvg` (also split out) now renders alone, sized to literally
      equal `heatmapHeight(rows)`, with nothing subtracted for title or stats since both moved
      elsewhere. The AUC/violin section (`ViolinPanel`) is unchanged, per explicit instruction
      ("the bottom violin plot looks better aligned, so you can leave it as is").
- [x] Fixed with live measurement, not guesswork: the scatter/violin SVGs were hard-coded
      `width = height` (a literal square), so on a wide `md=5` Grid column (measured live at 570px
      while the square was only 325px) roughly 245px of the panel's own width went unused — this
      was the "not filling the panel" complaint. New `useMeasuredWidth()` hook (`ResizeObserver` on
      a wrapping div) reports the column's real rendered width; both panels now use that as their
      SVG width, with height still pinned to `heatmapHeight(rows)`. Measured live: the y-axis
      title/tick-label collision was real too — ticks sit at `pad - 6` right-aligned, and a 3-digit
      value ("150") right-aligned against that point ran left past the title's old `x=12`; `pad`
      widened 50→60 and the title's `x` moved 12→16 (violin's mismatched `x=12`/rotate-anchor `x=16`
      also unified to 16) on both panels.
- [x] `ContactStrip`'s thumbnail order was raw JSON key-insertion order (whatever the backend
      response happened to return); added `contactSortKey()` (hemisphere first — Left before Right,
      falling back to the raw channel key's own LEFT/RIGHT token when `display_hemisphere` is
      absent — then ascending by the two contact digits, read from `display_contacts` with a
      fallback to parsing `ZERO`/`ONE`/`TWO`/`THREE` tokens out of the raw key) so the strip always
      reads left-side contacts in numeric order followed by right-side contacts in numeric order.
- [x] Removed the "⚠ Power-domain biomarker pools ... interpret per target rather than as a single
      combined biomarker" warning from the binarization panel (`index.js`) — a pure display removal,
      the backend field (`data.powerdomain_pooled_warning`) is untouched and still computed, just
      never rendered.
- [x] Built clean both times (title/stats/fill/order in one build, the warning removal in a second).
      Verified live on RCS08 after each build: the title/ContactStrip row and the heading/stats row
      both align correctly; the AUC/violin section renders unchanged; the thumbnail strip reads L
      0⁻2⁺, L 0⁻3⁺, L 1⁻3⁺, R 0⁻2⁺, R 0⁻3⁺, R 1⁻3⁺ in that order; a pinned cell's scatter and violin
      panels now visibly fill their full column width with no wasted margin and no tick/title
      overlap (zoomed screenshot confirmed clear whitespace between the rotated title and the tick
      numbers); the warning text is absent from the served bundle's rendered page
      (`document.body.innerText` checked directly). No console errors at any step.
  - **Status:** complete

### Phase C.5: Scatter and violin panels rebuilt as native Plotly figures; click-reliability fixes; AUC annotation — COMPLETE
Requested directly: "make the scatter[/violin] plot using a Plotly command so that it auto-resizes
to fill the panel," then "make the actual panel size square," then three rounds of direct feedback
on the violin's jittered-point styling, then a report that single click needed two tries and that a
native double-click crashed the whole page, then a final request to annotate the AUC above the
violin.
- [x] `PlotlyViolin` and a new `PlotlyScatter` component replace the hand-rolled SVG versions,
      both native `type: "violin"`/`type: "scatter"` Plotly traces via `PlotlyRenderManager` (the
      same wrapper the two calibrated heat maps already use), with `responsive: true` so Plotly's
      own resize handling fills the panel rather than a hand-measured `ResizeObserver`. Both
      panels are now a genuine square (`aspect-ratio: 1/1`, capped at the heat map's own height).
      `useMeasuredWidth`, `PanelAxes` and `niceTicks` (the SVG-era axis-drawing helpers) are deleted
      as dead code now that nothing calls them.
- [x] Violin marker styling, iterated live to its final form: solid, same-hue-as-its-own-violin
      points (not a shared neutral dark colour), no marker outline, with the violin's own fill
      lightened to 0.4 alpha specifically so the fully-opaque points read as visibly darker against
      it -- confirmed with a zoomed screenshot.
- [x] The violin panel's stats line now leads with `AUC = ${aucSw.auc_grid[row][col]}` -- the
      grid's own already-computed value for the pinned cell, read directly, never recomputed
      client-side -- before the existing Welch t-test text. Verified live against the grid's own
      hover tooltip for the identical cell: both read 0.535.
- [x] Fixed: single click intermittently needing two tries. Root cause -- the heat map's shared
      cross-highlight marker was rebuilt inside the SAME effect that (re)builds the whole figure
      and attaches the `plotly_click` listener, keyed on `hoveredCell`/`pinnedCell`; a real mouse
      gliding across cells before landing on one to click fired hover events that tore down and
      reattached the listener, and a click landing in that window found nothing listening. Split
      into two effects: one draws the heatmap/best-cell traces and owns the listeners, keyed only
      on the underlying grid data; a second updates ONLY a fixed-index highlight trace via
      `Plotly.restyle`, keyed on hover/pinned state, never touching the listeners.
- [x] Fixed: a genuine native double-click crashed the whole page to a blank white screen.
      Reproduced directly (two separate single clicks were harmless; one real double-click was
      not) and root-caused via the console: `Error: No DOM element with id '...' exists on the
      page` thrown from `.purge()` in all four panels' cleanup effects at once -- Plotly's own
      built-in double-click "reset axes" handling was tearing the chart divs down in a way React's
      unmount bookkeeping did not expect, and the resulting uncaught exception (no error boundary
      exists anywhere in this app) crashed the whole render tree. Fixed with `doubleClick: false`
      on all three `Plotly.react` calls (none of these panels have zoom/pan to reset) and by
      guarding every purge cleanup with a `document.getElementById(divId)` check plus a try/catch
      around the new restyle call. Re-reproduced after each fix: still crashed with `doubleClick:
      false` alone; no longer crashed once the purge guards were added, across three separate
      double-clicks on three different cells/grids, no console errors either time.
- [x] Built clean throughout (multiple rounds). Verified live on RCS08 after every round: panels
      fill their square correctly and auto-resize; violin points read clearly against the lighter
      fill; the AUC annotation matches the grid's own tooltip; single click pins instantly and
      reliably; double-click no longer crashes.
  - **Status:** complete

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
| ~~No "/ps-scientific-writing" skill exists...~~ **SUPERSEDED**: the user subsequently loaded `ps-plotly`, `ps-scientific-writing` and `ps-scientific-visualization` mid-session. | Phase D's condensing work will follow §6a of the now-loaded `ps-scientific-writing` skill (compress tokens not sentences, one idea per clause, count the actual word-reduction) together with this project's own `HOUSE_RULES_writing_and_claims.md`, not `HOUSE_RULES` alone as first planned. |
| Plain JavaScript object notation throughout for Plotly, never the Python API the `ps-plotly` skill documents — confirmed directly with the user before writing any Plotly code. | This codebase uses `plotly.js` (`package.json` pins `^2.14.0`) directly in the browser via this project's own `PlotlyRenderManager` wrapper (`graphing-utility/Plotly`) — plain `{type, x, y, z, ...}` trace/layout objects passed to `Plotly.newPlot`/`.react`, not `plotly.express`/`plotly.graph_objects`. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Live gunicorn workers did not pick up the Phase B backend edit on their own (`--reload --reload-engine poll`), serving a stale, unlabeled response ~5 min after the edit and after a page Recompute | Sent `SIGHUP` to the gunicorn master (its own documented graceful-reload signal); new worker PIDs appeared and the new fields were present afterward |
| `PlotlyHeatmap` crashed the whole page on first use: `TypeError: Cannot set properties of undefined (setting 'title')` inside `setXlabel` | `fig.subplots(1, 1)` was never called, so `this.layout.xaxis`/`yaxis` did not exist yet — every other consumer of `PlotlyRenderManager` in this codebase calls `subplots()` before `setXlabel`/`setYlabel`; added the same call |
| Panel title showed "20 s of signal" (the REQUESTED value sent to the cell drill-down endpoint) while the axis/tooltip for the same row showed "21s" (DELIVERED) — same cell, two different numbers | Added a separate `secondsDisplay` (delivered) field on `pinnedCell` used only for display; `seconds` (requested) is still what's sent to the server, since `band_time_sweep_cell_for_participant` keys its own lookup on that exact value |
