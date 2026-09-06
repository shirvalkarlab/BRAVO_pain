# BRAVO six-chart release validation — 2026-09-04

## Delivered changes

- Independent first-party Oura tab alongside REDCap Timeline, Stimulation programs, and Medications; Oura–FreeReps remains a separate page.
- Six selected default charts: steps, all available timed HR, all available timed HRV, total calories, longest-episode sleep duration, and total sleep including naps. Forty-four selectable metrics with unavailable measures disabled.
- Full history, custom dates, past 28 Pacific calendar days, applicable study phases, point display, and optional daily-only trailing median.
- Full-width vertically stacked stimulation comparisons, separate OL/CL plots, survey/day counts, and one detailed survey-point tooltip. Compact source-faithful stimulation/sensing settings.
- RCS08-specific L GPe / R MD Thal presentation mapping. Raw identifiers, exports, analysis callbacks, and other participants are preserved.
- Shared primary/secondary outlined-button text colors corrected in both themes. Direct before/after inspection confirmed Oura–FreeReps Refresh view changed from an empty-looking outline to readable blue text. Clicking Refresh view reloaded the recorded data normally.

## Automated validation

- Frontend: 242 tests across 35 suites passed; `/private/tmp/bravo-six-charts-all-tests.log`.
- Oura backend/QC/FreeReps: 29 tests passed; new endpoint/adapter coverage 171 statements and 72 branches, all covered.
- Focused stimulation suite: 35 tests passed, 97.72% branch coverage.
- Target presentation helpers and associated REDCap data tests: 49 tests passed; relevant helpers/data had full coverage.
- Production frontend build passed in Node 22 using cached dependencies without registry access.

## Real data and browser checks

- Full history yielded 426 steps days, 320452 finite HR samples over 445 days, 45618 HRV samples over 429 days, 426 total-calorie days, and 405 days for each sleep duration series.
- HR source coverage includes HeartRate and Sleep. Current stored HRV samples are in Sleep; no additional sleep-only restriction is imposed.
- Total sleep was never less than longest-episode sleep. No incomplete sleep-total days in the current eligible set.
- All six Oura charts rendered at desktop width, and all six fit a 390 px viewport without horizontal overflow (342 px plot containers).
- Past 28 days selected August 8 through September 4, 2026, with only the applicable ongoing Stage 2 context. HR showed 17649 readings over 27 days; HRV 2853 over 26 days.
- Actual OL and CL survey hovers each produced exactly one Plotly hover group. OL showed `n = 9 surveys (7 days)` and compact contacts/settings. CL showed `n = 35 surveys (15 days)`, single-threshold mode, recorded sensing contacts/frequency/thresholds and explicit ganging provenance.
- Four rendered representative OL/CL stimulation plots fit a 390 px viewport: container and SVG width 334 px, document scroll width 390 px. Desktop container widths were 1358 px within a 1728 px viewport.
- Normal viewport was restored after testing.
- After a normal session expiration, the user signed back in. The final deployed build successfully loaded all six charts. Adding Active calories rendered a seventh chart; removing Steps removed its chart; Default Oura metrics restored the six selected defaults in order. Past 28 days again showed August 8 through September 4 with the verified sample counts. Full history was restored afterward. The final page had no alert, all six plot scroll widths equaled their 1358 px container widths, and document scroll width equaled the 1728 px viewport.
- Original user Chrome tab retained as the deliverable at `http://127.0.0.1:8080/reports/redcap-pretrial/81b245ec31594d9894f1dfc9438b6348`, Oura selected, title `UF BRAVO Platform`, Aditya branding. No duplicate verification tab was retained.
- Database also showed the enabled Sync Data from REDCap, Dropbox, and Oura button after sign-in; no sync was triggered.

## Sleep terminology qualification

The user requested a nighttime label. The normalized store omits sleep-type classification, and 12 selected longest episodes occurred during daytime. The provisional accurate display is “Sleep duration (longest episode)” with a definition, versus “Total sleep duration, including naps”. A nighttime window was not invented. The accurate longest-episode label resolves the distinction without falsely classifying daytime sleep as nighttime. The user may still choose a literal nighttime window; no source records or QC rules were changed.

## Local deployment

Only the web-server container was replaced; sync service, database, Redis and data volumes were retained. No sync or analysis jobs were triggered, and no Git commit/push was made.

- Running Aditya image: `sha256:2eca8d588e0c8e116e2a8ad8da05610ab2f525ad225b68ec77a557b0b78cc9d9`.
- Prior build retained as `bravo-local:before-six-charts`.
- Served bundle: `/static/js/main.bdffdbc3.js`.
- Local and served bundle SHA-256 both `8369e685a0e87d2c33c4282601c50d01afb4f24504605f624caa083f72c88063`.
- `scripts/bravo-appliance check` passed after replacement: BRAVO app identity, database, storage, Django checks and localhost binding.
- Chrome showed the Aditya brand and `UF BRAVO Platform` title on Oura–FreeReps and REDCap in the final build before the normal session expired.

Broader earlier layout coverage and the verified Sync Data button location are recorded in [the UI spacing audit](ui-spacing-audit.md). These results cover tested surfaces and representative data states, not every possible future data combination.


## Follow-up: REDCap-style Oura context and three toggles

User correction: the first release copied study phases but omitted detailed stimulation context and used a seven-day smoother. The follow-up now exposes exactly three switches, in this order: **5-point rolling median**, **Past 28 days**, **Stimulation context**. The median and context initially appear; point display and phase context remain part of the standard view.

- Five-point smoothing reuses REDCap's centered observed-point median helper, before date filtering. It excludes nulls, uses fewer available observations at global ends, and can span phase/missing-period boundaries. Daily values use five observed daily values; HR/HRV use five recorded readings. Raw traces and missing gaps remain present.
- Oura receives the same reviewed home transitions and unknown intervals as REDCap. The shared settings selector/panel supplies complete stimulation/sensing details, clickable date-filtered markers, prior-window record provenance, and the existing readable cap of 12 transition labels. Sample tooltips resolve home settings at each timestamp, preserving uncertainty and explicit missing-evidence intervals. Daily totals do not claim a single program.
- Frontend regression suite: **245 tests / 35 suites passed** (`/private/tmp/bravo-oura-context-all-tests.log`). Includes centered median values and gaps, unchanged raw HR/HRV, timed unknown settings, three-toggle behavior, dense transition limits, and annotation selection/cleanup.
- Build succeeded; running image `sha256:c215bd4b82376df4f18ee36f090de2cb7a153727632546d790dd80d8faea956c`. Backend/data/QC are the same prior image; only client assets and generated HTML changed. Prior image retained as `bravo-local:before-oura-context`.
- `bravo-appliance check` passed. Served `/static/js/main.805c9d37.js` matches local SHA-256 `a71c8cfb528b1a08d9c233c1003bf6cbe724be2cc4a16d387ed634cd74132ce8`.
- Authenticated Chrome: exactly three switches in the requested order; all six plots show a five-point median legend and the selected transition annotation; raw HR/HRV counts remain 320452/45618. Expanded settings show L GPe / R MD Thal, dual-threshold mode, 23.44 Hz sensing, and recorded 166/167 LSB thresholds. Turning context off removes the panel and all six annotations; turning it back on restores them. Desktop plots fit 1358 px containers without horizontal overflow.
- Narrow final check: at a 390 px viewport, all six plot containers/SVGs were 342 px, no document or plot horizontal overflow, and every legend/transition text element stayed inside its chart. Normal viewport restored and original Chrome Oura tab retained.


## Follow-up: trial phases beside every longitudinal chart

The user requested phase names without scrolling to the page header. Clinical Timeline (11 default graphs), Oura (six default graphs and any additional selected metrics), and the medication time axis now have chart-local wrapping phase legends with visible date spans and exact source-boundary hover descriptions. Matching faint phase shading occupies each chart interval below data. REDCap point hovers include the recorded phase name. Categorical stimulation/medication comparisons do not receive a misleading temporal phase axis.

Phase intervals are clipped to the selected Pacific date window without changing recorded boundaries. A phase active before the left edge remains labeled; nonintersecting prior/future phases disappear. The medication window correctly includes Stage 1/2 only. Full-history Oura shows all five trial portions, with five rendered shaded bands and one local legend per chart; Past 28 days shows only ongoing Stage 2 on all six charts.

Validation: 248 frontend tests / 36 suites passed (`/private/tmp/bravo-phase-label-tests.log`). New checks cover phase clipping, ordering, pre-window context, intraday transitions, unknown/invalid ranges, full untruncated legend text, hover descriptions, and source immutability. Production build passed.

Release image: `sha256:758e5d993288922b7a3681080c72fc7fb1a6ea7ac40d49c44a3e400cf6963431`; previous image retained as `bravo-local:before-phase-labels`. Only frontend/generated HTML changed. Post-replacement appliance checks passed, including application identity and health. Local/served `/static/js/main.a2ba86fd.js` match SHA-256 `ff13113cbf6b0c5129b10c7836f2ce881b7322e59acf184e4e3959711eea06de`.

Narrow browser check: all six full-history Oura charts retained five local phase labels at 390 px. Legend widths/scroll widths both 326 px, no label escaped its legend, plot widths/scroll widths both 342 px, document width 390 px. Normal viewport restored and original authenticated Chrome report retained.
