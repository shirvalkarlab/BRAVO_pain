# Findings: Closed-Loop grid stability column

Observations only. Nothing here is an instruction. Every code location below was read directly in
this session, not recalled — but every line number will move, so search for the name.

## 1. What is actually built, and what is not

Track D (decision 67) shipped both halves of the stability answer and the switch that would run
them, and nothing turns the switch on.

| Piece | Where | State |
|---|---|---|
| Raw, untranslated answer per (contact, band centre) | `Biomarkers.bravo_service.raw_stability_result_for_point` | built |
| Attaches it to every grid row | `Biomarkers.bravo_service._attach_grid_export_columns` | built, runs only behind the flag |
| The honest four-valued translation | `ClosedLoopDeployment.stability.finding_from_stability_result` | built |
| Reader that applies the translation | `ClosedLoopDeployment.adapter.band_sweep_grid_for_closed_loop` | built |
| The panel that displays it | `ClosedLoopSim/BandSweepGridPanel.js`, `StabilityChip` | built |
| Anything that sets `IncludeCrossSettingStability` | — | **does not exist** |

Confirmed by grep across the repository with the compiled bundle excluded: the string
`IncludeCrossSettingStability` appears in `bravo_service.py` (the one place that reads it), in two
`BandSweepGridPanel.js` lines that are a comment and a tooltip, and in documentation. No client
code sets it in any request body. So `StabilityChip`'s "stability: not yet computed" branch is the
only branch any real page view has ever taken.

## 2. Why it is off, stated as the measurement rather than as a preference

Decision 68 records a full grid build with the flag off at 5.85 s and with it on at 326.7 s, for all
six sensing contact pairs. **That pair is a document number and Phase 1 re-measures it** — CLAUDE.md
§10 rule 3 forbids carrying a timing forward, including this project's own.

The same decision records what turning it on did to the response: 27,865 fields in common, 0
dropped, 10,560 new fields (all under `cross_setting_stability_raw` and `device_rules_status`), and
of the common fields only 22 differed — every one a timing field or the store key, which changes
correctly because the flag is folded into the sweep's own cache key. Zero scientific values moved.
That is the shape Phase 4's own proof should reproduce.

## 3. The import direction is a hard rule, and it has already been broken once

`stability.py`'s docstring makes it explicit: `ClosedLoopDeployment` may import `Biomarkers`, never
the reverse. An earlier Track D draft applied the four-valued translation inside Biomarkers, which
broke that direction and was caught only when the container could not import it.

A second, related finding from decision 67 worth carrying: `stability.py` had imported
`Biomarkers.routines.analytics` with the bare host-only spelling, which the production container
cannot resolve. The consequence was that `adapter.py`'s already-shipped single-candidate
`band_stability` field had likely never returned its real four-valued answer inside the real
gunicorn container since the day it was wired in — only ever "not tested" with a swallowed import
error. It was fixed with the double-import pattern. The lesson for this task: a swallowed import
error in this codebase produces a normal-looking, fast response that is silently missing its
answer, so "it returned without raising" proves nothing.

## 4. The failure mode this column is most likely to hit

`_attach_grid_export_columns` carries its own warning, written after it happened: the first draft
read `center_hz` (a synthetic test's field name) instead of `band_center_hz` (the real row field).
Because a missing key is treated as "skip this row" rather than an error, the bug attached nothing
to any row while still returning a normal-looking, fast response with no exception anywhere. It was
caught only by comparing a flag-on response's own field count against a flag-off one and finding
them equal when they should not have been.

So the check that actually discriminates here is a field COUNT comparison between flag-off and
flag-on, not a shape check and not the absence of an exception.

## 5. What a reader sees today, and why that matters for the options

`BandSweepGridPanel.js`'s `StabilityChip` renders a greyed chip reading "stability: not yet
computed" with a tooltip naming the flag. That is honest — it says the answer was not computed
rather than implying the band is stable — and it matches this project's standing three-state
discipline (decision 9: a gate that goes green on absence of evidence is unsafe). Whatever option
Phase 2 picks, that branch should survive for rows whose answer genuinely has not been computed
yet, rather than being replaced by a blank cell.

## 6. Cost structure, as far as reading goes (to be confirmed by measurement in Phase 1)

`_attach_grid_export_columns` caches per band centre within a channel (`cache = {}` keyed on
`center_hz`), and the correlation and AUC grids share the same 22 centres, so the per-channel call
count is 22 rather than 44. With six real sensing contact pairs on RCS08 that is on the order of
132 calls to `raw_stability_result_for_point`.

Decision 67 recorded two individual live calls at 4.61 s and 2.17 s, the first paying rpy2/R's
one-time initialisation. 132 calls at roughly 2.2 s each is in the region of 290 s, which is
consistent with the 326.7 s full-grid figure. **This is arithmetic over two sampled calls, not a
measurement** — Phase 1 replaces it with a real per-point cost and a real count.

If that structure holds, it is the fact that makes option (b) — compute for the one row a reader
opens — attractive: a single point is a couple of seconds, which is an ordinary click-through cost,
and it is the same shape the grid's existing per-cell drill-down already uses.

## 7. Open item 26 sits on the same grid and is NOT part of this task

Open item 26 (the length-of-signal axis means nothing for a cell served by the device's own
spectrum, and nothing marks which cells those are) is a display and reporting decision on this same
grid, explicitly recorded as the PI's call. It is noted here so it is not rediscovered as new, and
deliberately left out of this plan's scope: it needs its own answer, and bundling a display question
into a cost question would put two decisions behind one go-ahead.
