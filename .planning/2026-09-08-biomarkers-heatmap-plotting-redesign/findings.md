# Findings & Decisions

## Requirements
-

## Research Findings

### CORRECTION: the "older scatter-and-violin drill-down" is NOT `compute_psd_pain_correlation`

Traced the actual render path instead of relying on the framing carried over from earlier in the
conversation. `Client/src/views/Reports/Biomarkers/BiomarkerAnalytics.js` builds the scatter (left)
+ violin (right) panel (lines ~778-899) from `scan = td.spectral_feature_importance`, where
`td = analytics.timedomain` — i.e. the response field `analytics.timedomain.spectral_feature_importance`,
NOT anything named after `compute_psd_pain_correlation`.

`analytics.spectral_feature_importance` (routines/analytics.py:1259) is a 5 Hz sliding-band scan,
0-100 Hz, that by **default already uses calibrated device LSB** (`feature="lsb"`, its own docstring:
"CALIBRATED device LSB from the SHARED per-pair CS-1...CS-4 cache" -- the same calibration machinery
as the main grids, fed through `_live_pro_lsb_spectrum` -> `availability.live_lsb_spectrum_match`,
the same matcher confirmed as the main grids' data source two turns ago). "The old Welch-density x
k=269 / device-FFT rescale path is REMOVED (PI 2026-06-27)" -- so the uncalibrated-Welch framing is
stale; that path doesn't exist in this function any more. What IS still true and load-bearing: its
own docstring says outright "NOTHING here is a validated biomarker -- discovery," it runs a
continuous 5 Hz-step scan rather than the calibrated sweep's 22 fixed centers x 10 window lengths,
and it uses a much weaker correction (a single FDR pass, no permutation/bootstrap) -- so it is still
scientifically inferior to the calibrated grids for the reason the user cares about, just not for
the reason ("raw, uncalibrated Welch power") stated earlier in this conversation.

`streaming_psd.compute_psd_pain_correlation` (decisions 57-61, the genuinely raw/uncalibrated,
per-session, FDR+cluster-robust routine) has exactly one production caller,
`pipeline.run_timedomain_branch` (pipeline.py:622), which IS reached from the live request path
(`bravo_service.py` calls `pipeline.run_biomarker` at lines 3051 and 3960). But no field name
matching it (`psd_pain_correlation`, `pain_correlation`) is consumed anywhere in
`Client/src/views/Reports/Biomarkers/`. **Not yet confirmed**: whether its result surfaces under a
differently-named field that some other part of the page reads, or whether it is computed on every
request and never actually displayed. This needs one more read (`pipeline.run_timedomain_branch`'s
return dict shape, and what `bravo_service.py` does with it) before the plan can say for certain
whether removing/disabling `compute_psd_pain_correlation` is in scope at all.

Rendered the real panel directly from live data to answer the user's sanity-check request without
a browser: pulled `analytics.timedomain.spectral_feature_importance` for RCS08 via the bridge
(`_agent_bridge/_scatter_violin_probe.py` -> `_scatter_violin_probe.json`), then reconstructed the
exact trace/layout spec from `BiomarkerAnalytics.js` in Python (`plotly.graph_objects`, matching
colors/violin config/hovertemplate) and rendered it with kaleido (installed in a throwaway venv at
`/tmp/plotly_venv`, not in the container or the project's own environment) to
`/tmp/scatter_violin_reconstruction.png`, sent to the user. Real result on the left 1-3 contact at
2.5 Hz: n=153 (76 TD, 77 PSD), Spearman rho = -0.52, p = 2.7e-98, Cohen's d = -0.37.

### RESOLVED: `compute_psd_pain_correlation`'s output is effectively dead in the live UI

Traced `pipeline.run_timedomain_branch` (its one production caller): it runs
`compute_psd_pain_correlation` over the FULL per-channel/per-frequency grid, then immediately
collapses that down to ONE FDR-selected band (`select_biomarker_band`) and writes only that single
band's value onto the timeline as `td_biomarker_value`/`_channel`/`_freq_hz`/`_r`/`_p`, plus a
`summary` dict. The only frontend consumer of `td_biomarker_value` is
`BiomarkerTimeline.js:166/178` -- the drawn as a "PSD biomarker" trace -- and `BiomarkerTimeline.js`
is the LEGACY timeline component `index.js` only falls back to when the modern availability payload
is unavailable (`timelineData.availability.records.length > 0` is false). In today's normal
operation the modern timeline always has availability data, so this fallback essentially never
renders. **Conclusion: `compute_psd_pain_correlation`'s full per-band grid is computed on every
request and thrown away except for one collapsed value that reaches a dead code path.** It is not
what the user means by "the older scatter and violin drill-down" (that's confirmed as
`spectral_feature_importance` -> `BiomarkerAnalytics.js`, above) and is out of this plan's scope --
flagged as a separate, unrelated finding (wasted compute on every request) worth its own decision
later, not something to fix as part of this plotting redesign.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-
