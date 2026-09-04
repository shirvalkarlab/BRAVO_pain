# Biomarkers and Stim Parameter Optimizer: consistency pass

Prepared 2026-09-04 against branch `PS_closedloop_deployment`. Scope was
`Client/src/views/Reports/Biomarkers/` and `Client/src/views/Reports/StimOptimizer/` only. No file
in `Client/src/views/Reports/ClosedLoopSim/` was modified, and no Python was modified. Line numbers
for defects are given against `HEAD` (the state before this pass) so they can be checked against
the original code.

**`Client/src/routes.js` was NOT touched.** No route or sidebar label needed to change: the two
relocated panels are rendered inside the existing Biomarkers view rather than at a new address.

**Build result, verbatim:**

```
Compiled with warnings.
Failed to parse source map from '/Users/pshirvalkar/dev/BRAVO_pain/Client/node_modules/@mediapipe/tasks-vision/vision_bundle_mjs.js.map' file: Error: ENOENT: no such file or directory, open '/Users/pshirvalkar/dev/BRAVO_pain/Client/node_modules/@mediapipe/tasks-vision/vision_bundle_mjs.js.map'
```

**Lint result over the six files touched:** `✖ 11 problems (0 errors, 11 warnings)`. Ten of the
eleven warnings are present at `HEAD` and untouched by this pass. The eleventh is not a new warning
but an existing one that has grown by one identifier: `BiomarkerDataTimeline.js` already carried
`react-hooks/exhaustive-deps` for the omitted `binOf`, and the new `binAssessed` flag, which is
derived from the same `scanModel` the effect already depends on, is now listed alongside it.

---

## 1. Skills loaded, and what each one changed

`ps-scientific-visualization`, `ps-plotly` and `figure-style` were loaded first. Because the brief
explicitly required no new figures, their influence was on encoding discipline rather than on any
chart:

* **Redundant encoding, from `ps-scientific-visualization`.** It is the reason the four-state
  stability answer is a labelled track in which every state is spelled out in words and exactly one
  is filled, rather than a coloured word. Position and text carry the answer, so it survives a
  greyscale print and a colour-vision deficiency; the fill is reinforcement. The same rule is why
  the per-contact direction column keeps its up/down arrow glyph and why the band-commit outcome is
  a coloured swatch beside near-black text rather than coloured text.
* **Contrast floors, from `figure-style`.** This changed concrete colour choices. Every ratio below
  is a measured WCAG contrast ratio computed with the sRGB relative-luminance formula, checked
  against the black-on-white reference of 21.00:1 and against the palette's own stated
  `onWarn`-on-`#E69F00` figure of 7.73:1, which the same formula reproduces.

  `PAL.pass` (`#009E73`) measures 3.42:1 against white and `PAL.fail` (`#D55E00`) 3.87:1, both below
  the 4.5:1 small-text floor — the same problem `palette.js` already documents for its amber role
  and solves with a separate `warnText` token, but does not solve for pass or fail. So no small text
  on these pages is set in either ink. Where a fill carries a word, the ink is chosen per fill by
  its own measurement, and the measurements do not agree with each other:

  | fill | white ink | `PAL.onWarn` (`#1A1A1A`) | pure black | ink used |
  |---|---|---|---|---|
  | pass `#009E73` | 3.42:1 | **5.09:1** | 6.14:1 | `PAL.onWarn` |
  | fail `#D55E00` | 3.87:1 | 4.50:1 | **5.43:1** | pure black |
  | neutral `#6C757D` | **4.69:1** | 3.71:1 | 4.48:1 | white |
  | warn `#E69F00` | 2.25:1 | **7.73:1** | 9.32:1 | `PAL.onWarn` (palette's own choice) |

  The fail fill is the one case that forced a departure from the palette's `onWarn` token:
  `#1A1A1A` on `#D55E00` measures 4.50:1, which sits exactly on the AA floor with no margin, so any
  future darkening of the fill or lightening of the ink would drop it below. Pure black on the same
  fill measures 5.43:1. The token was specified against the amber fill, where it has ample room, and
  it does not transfer to vermillion — which is a further argument for the `PAL.failText` role
  requested in section 5.
* **`ps-plotly`.** It informed the choice of a third marker symbol (`x-thin`) for the timeline's
  unassessed pain ratings rather than a third colour, and the decision to add the matching legend
  entry conditionally so it appears only when the view is in that state.

---

## 2. Every multi-valued-state collapse found

### Fixed

**(a) `BiomarkerAnalytics.js:179` — the stimulation-stability verdict, rendered as a boolean.**
`{`Stim ${s.stim_stable ? "stable" : "dependent"}`}`, coloured `#0a7f3f` or `#B17500`. This is the
headline instance and the one the brief named. The backend has emitted a three-way
`stability_verdict` since 2026-09-03, and the frontend read only the legacy boolean, so a band whose
equivalence interval was simply too wide to decide anything displayed with the same word, the same
weight and the same green ink as a band whose between-era difference had been shown to be smaller
than the declared margin.

*The four states now distinguished, and how:* **Equivalent** (the interval on the largest
between-era slope difference lies inside the declared margin) fills the green cell; **Differs by
era** (the interaction likelihood-ratio test rejects) fills the vermillion cell; **Not
determinable** (the test did not reject but the interval is wider than the margin) fills a neutral
grey cell; **Not tested** (no result, or a payload predating the equivalence test) fills a second,
separately labelled neutral grey cell. All four cells are drawn on every render, so a reader sees
that four answers exist. The two grey states are separated by their labels and by a sentence naming
why the question could not be answered. Neither grey state ever takes the failure ink, because in
neither case has anything been contradicted.

The readout also now shows the numbers that make the verdict checkable: the largest between-era
difference as a multiplicative factor in odds with its interval, against the declared margin
(`log(2)` in the payload, shown as "a factor of 2.00"), both exponentiated out of the log-odds scale.
A note states plainly that a p-value at or above 0.05 is a failure to reject and not evidence of
equivalence.

**(b) `BiomarkerAnalytics.js:123` — the verdict badge asserts a stability the equivalence test
declined to grant.** The badge string arrives from the backend, where `_band_decide_verdict` prints
`VALIDATED (stim-stable)` whenever `stim_stable` is not explicitly `False` — which includes
`stability_verdict == "inconclusive"`. Since the same response carries the three-way verdict, the
parenthetical is now corrected client-side to `(stim stability not determinable)` or
`(stim stability not tested)`. The correction is confined to the parenthetical; the mixed-effects
half of the verdict is untouched. Badge inks now come from `palette.js`, and a verdict that
establishes nothing takes the neutral grey rather than the failure ink. **This is a workaround for a
backend collapse — see section 6.**

**(c) `BiomarkerAnalytics.js` — a tri-state the backend computes and the interface discarded.**
`band_stim_stability` returns `rate.rate_confounded_with_era` as `True`, `False`, or `None` when
Cramér's V could not be computed at all. Nothing in the frontend read it. It is now one line with
three distinct wordings, because a confounded era result is carrying a stimulation-rate component
rather than a pure amplitude one, an unconfounded one is not, and a null means the association was
not measurable — three different consequences. (`equivalence` and `slope_by_era` were likewise
computed and dropped; the equivalence numbers are now shown, per (a).)

**(d) `BiomarkerAnalytics.js:697` — channels screened and yielding nothing were invisible.**
`.filter((c) => c.selected_band)` dropped every channel whose `selected_band` was `null`. Per
`analytics.py:1876` that is `null` only when not one band in the sweep produced a computable
correlation, which means the channel **was analysed and came back empty** — not that it was skipped.
A reader comparing a four-contact montage against a three-row table had no way to learn which had
happened. Those channels are now real rows in the neutral ink reading "screened, but no band in the
sweep produced a computable correlation".

**(e) `BiomarkerAnalytics.js:726` — the FDR column had three states and showed two.** A `q` that
cleared 0.05, a `q` that did not, and no `q` at all shared the tick glyph's presence or absence,
and the third printed an em-dash in the same grey as a genuine negative. The three now read
`0.031 ✓`, `0.210 (n.s.)`, and `not tested`, with the caption stating that the last is an absence of
evidence and not a negative result. (Note that `analytics.py:1888` coerces `fdr_significant` to a
strict boolean on the fallback branch, so the flag alone cannot express the third state; the display
keys off whether `q` exists.)

**(f) `binarizationModel.js:121` — one empty object for three different situations.** The `empty`
return was reached when the neural-sample index was absent, when the pain series was absent, and
(via a zero-length match) when both were present and the match window was too narrow. The first two
are an absence of inputs and say nothing about the data; the third is a measured, actionable
negative. The return now carries `matchable` and `unmatchableReason`, and `painMatched` is a
length-zero array rather than absent so a consumer cannot index into a stale one. The successful
return is explicitly marked `matchable: true`, so a zero from there is reportable as measured.

**(g) `BinarizationPreview.js:597` — a missing input announced as the reason for a measured
result.** The single fallback sentence "No PSD scan index available — showing the daily PRO
distribution" was printed for all three cases in (f). In the case that matters most it sent the
reader looking for a data problem that did not exist: the truth was that zero of the available
neural samples fell within the match window, which they could fix by widening it. Now three
sentences, one per case, and the window case names the sample count and says explicitly that the
histogram has fallen back to a *different quantity*.

**(h) `BiomarkerDataTimeline.js:217, 885, 895` — a page-wide negative manufactured from an absent
input.** `binMode` tested `!!(scanModel && scanModel.binByKey)`, and the empty model's lookup is an
empty `Map`, which is truthy. So with matching never attempted, `binMode` was true, `painMatched`
was empty, and **every** pain rating rendered as an open circle whose hover read "no neural match",
while every neural mark fell through `binOf(...) || "unmatched"`. Both asserted a check that had not
been run. A `binAssessed` flag now separates the two: unassessed pain ratings get a third symbol
(`x-thin`, neither the closed circle that means matched nor the open one that means matched-nothing)
and the hover reads "match not assessed"; neural marks read "bin: not assessed"; and a legend entry
appears, only in that state, explaining that the crosses mean an unanswered question.

**(i) `Biomarkers/index.js:728` — an unverified promise rendered as a confirmed one.**
`underMemoryPressure()` returns `false` both when the heap is comfortably below the eviction ratio
and when the browser does not expose heap figures at all (`performance.memory` exists on Chromium,
not on Firefox or Safari — `biomarkerStateStore.js:72` documents the choice). The green tick "✓ view
retained — returns instantly from the deployment page" therefore appeared on those browsers as a
confirmed guarantee the guard had declined to measure. The measurement is now read first and its
absence is its own state, worded as a caching decision rather than a guarantee, and all three states
report the heap figures where they exist.

**(j) `StimOptimizer/index.js:374` — the resolution chip, and section 3 below.**

**(k) `StimOptimizer/index.js:183, 145, 256` — section 3 below.**

### Checked and clean, with what was checked

* **`BiomarkerDataTimeline.js`, the four-state bin.** `high` / `low` / `excluded` / `unmatched` are
  each drawn with their own colour **and** their own marker symbol, and the fourth has its own
  legend entry ("not in binarized set (no PRO in window / band-power)") rather than sharing the
  negative's treatment. This is the pattern done correctly and it is the model the fixes above
  follow.
* **`BiomarkerDataTimeline.js:524, 531, 544, 843` — missing sensing-band centre frequencies.**
  A `null` centre is greyed and hovers as `?` or `n/a` rather than being coerced to a number or a
  default band. Correct.
* **`BiomarkerDataTimeline.js:895` — `painMatched` itself.** Once matching has run, this array is a
  genuine per-rating boolean (a rating either claimed a PSD or did not), so the two-symbol rule is
  right in that state; only the unassessed case needed the third symbol.
* **`Biomarkers/index.js` — sensing-band frequency panel.** `anyAboveCap` and `noFreq` are already
  separate branches with separate messages, so "band is above 50 Hz" and "centre frequency not
  available in this device export" do not collapse. Correct.
* **`BinarizationPreview.js:69` — `n0 ? s0 / n0 : c0`.** A zero-count guard against division by
  zero, falling back to the declared cut. Genuinely binary; not a state collapse.
* **`bravo_service.py:3763` — `conservative = (stim_stable is not True)`.** Reading this to check
  whether the backend's ramp guidance collapsed the tri-state: it does not. `None` is treated
  conservatively, which is correct. No change needed and none made.
* **A sweep for `!`, `!!` and `Boolean()` applied to a possibly-null value across all seven files in
  `Biomarkers/` returned no further instances** beyond those listed above. The remaining bare
  truthiness tests in the directory are on view-mode strings (`matchedMode`, `isLsb`, `binMode`),
  loading flags, array lengths, and format-time null guards of the form `x != null ? fmt(x) : "—"`,
  none of which carries a scientific verdict.

---

## 3. The Stim Optimizer page: what was found and changed

**The scientific position was already stated and already enforced, and I did not have to install
it.** The file's header comment sets it out and asks future editors to preserve it, explicitly
warning against adding a recommendation banner that reads the optimum without gating on
`recommendation_supported`; the gate is a strict `=== true` test, so a null does not pass. The
backend is stronger still: `pipeline.StimArm.surface_can_resolve_its_optimum` tests the gain against
the standard deviation of the **difference**, and its docstring records that an earlier version
ignored the incumbent's own posterior standard deviation, that the single arm which passed the old
gate fails the corrected one, and that the corrected variance approximation is deliberately
conservative because it omits a positive covariance term. Nothing on the page presented a point
estimate as a recommendation.

Three things did mislead.

**(a) The comparison the verdict is about was not displayed.** The table printed two posterior
means and two separate standard deviations and then a bare resolved / not-resolved chip, leaving the
reader to combine four numbers in their head to see the difference the verdict was actually about.
The table now carries a **"Gain over in force (±1 SD of the difference)"** column showing the gain
and the interval one standard deviation of the difference wide on each side — the width the
resolution rule itself uses. It is labelled as one standard deviation and not as a 95% interval,
because it is not one. An interval straddling zero is now the visual form of "this arm has not
earned a recommendation". Two notes beneath the table state the sign convention (the objective is a
pain score, so lower is better and a positive gain favours the candidate), give the propagation
formula, and record that the omitted covariance term makes the test conservative rather than
permissive. The header "Best cell" became **"Candidate cell"**, because the cell where the
surrogate's mean is lowest is not a setting the evidence recommends and a column header should not
say "best" about a cell whose advantage may be indistinguishable from zero.

**(b) The resolution chip collapsed a three-valued answer (line 374).**
`a.optimum_resolved ? "resolved" : "not resolved"`. The served boolean reports `False` both for an
arm whose difference was measured and found too small to call **and** for an arm whose difference
could not be formed at all — `surface_can_resolve_its_optimum` returns `False` when the propagated
standard deviation is non-finite or zero. These call for different responses: collect more exposure
versus fix the fit. Both posterior means and both standard deviations are in the payload, so the
difference and its uncertainty are recomputed on the page and the third state is recovered:
**resolved**, **not resolved**, **not determinable**, each with a tooltip stating which it is and
why. "Not determinable" is an outlined neutral chip, not a variant of the negative, and neither
non-positive state uses the failure ink, because neither says a setting is worse.

**(c) The verdict banner made a positive claim about arms it had not measured (line 145).** When a
recommendation was withheld the banner read "For every arm, the predicted gain over the setting
currently in force is smaller than the uncertainty of that difference" — true only of the arms whose
difference could be formed. The banner now counts the two populations and reports each, so an arm
that could not be compared is not spoken for.

**(d) The closed-loop readiness badge worded two states identically (line 183).** `ready === false`
printed "no deployable control signal" whether cells had been screened and none qualified or nothing
had been screened at all. The served payload carries `n_cells_screened`, so the second case now
reads "no cells screened — deployability not yet assessed" and takes a disabled-grey rather than the
caution fill. Relatedly, the per-cell deployable column (line 256) used `color="error"` for "no": a
cell outside what the device can actuate on has not failed in the sense the error ink means, and the
reason is spelled out in the adjacent column, so it now reads in the neutral register.

---

## 4. Which relocated panels were placed, and where

Both were imported from their existing location — `views/Reports/ClosedLoopSim/PsdLsbPanel` and
`views/Reports/ClosedLoopSim/ConversionModelPanel` — so there remains one implementation of each and
a fix applied there is a fix here. Neither file was edited.

They sit in a new **"Device-scale calibration"** section at the foot of the Biomarkers page, below
the analytics section, because the section copy refers to the exploratory scan above it. The section
has a short heading explaining what the pair is for, and each panel has its own question as a
heading: *"Does the committed band convert to device units, and is the conversion linear?"* for
`PsdLsbPanel`, and *"What conversion is assumed for a band the device never sensed?"* for
`ConversionModelPanel`. They are placed side by side at `lg={6}` so the observed and modelled
answers to the same question are read together.

**Props.** `ConversionModelPanel` needs only `participantUid`, which the page has.
`PsdLsbPanel` additionally needs a `bandCandidate` carrying the contact, centre frequency and
bandwidth. **The Biomarkers page did not hold one**, and this is worth stating rather than papering
over: the candidate is written to `localStorage` by the commit button inside `BiomarkerAnalytics`,
via `ClosedLoopSim/bandCandidateStore`, and localStorage is not observable from React. Rather than
pass `undefined`, the page now reads the committed envelope with `loadBandCandidate` on mount and on
participant change, and a commit callback (`onBandCommitted`) is threaded from the page down through
`BiomarkerAnalytics` → `SpectralFeatureImportance` → `ValidationReadout` and fired after a
successful commit — the browser's `storage` event fires only for *other* tabs, so without the
callback a reader who committed a band would see the panel keep its empty state until a reload and
would reasonably conclude the conversion could not be computed. When no band has been committed the
panel renders its own empty state, and the caption beneath says what to click to populate it.

---

## 5. Consistency with the rebuilt deployment page

* **`palette.js` is imported, not duplicated,** in `Biomarkers/index.js`,
  `Biomarkers/BiomarkerAnalytics.js` and `StimOptimizer/index.js`. Local hexes removed:
  `#0a7f3f`, `#B17500`, `#9A3324`, `#6c757d`, `#8A6100`, `#D55E00`, `#0072B2`, `#9AA0A6`. Two of
  those (`#0a7f3f`, `#B17500`) do not appear in the palette at all, so a reader moving between the
  pages had to re-learn the colour code.
* **Dashed frame for modelled, solid for observed,** applied to the relocated pair. `PsdLsbPanel`
  fits from the participant's own time-matched recordings, so it sits in a solid `PAL.accentBorder`
  frame; `ConversionModelPanel` serves a frozen model whose gain at any particular band is
  interpolated from a fitted trend across frequency, so it sits in a dashed `PAL.neutralBorder`
  frame. Each carries a caption saying which it is and why.
* **Neutral grey for "not established", never the failure ink.** Applied throughout: the two grey
  stability states, the barren-channel rows, the "not tested" FDR cell, the "not determinable"
  resolution chip, the unscreened readiness badge, and the non-deployable cell column.
* **The hatch texture was not used.** `PAL.hatch` is reserved for the caveat channel on the
  deployment page and nothing on these two pages needed that channel, so introducing it here would
  have diluted it.
* **Every state track draws all its states.** The stability track renders four labelled cells and
  fills one, so the arity of the answer is visible in the markup rather than implied by whichever
  value happened to arrive.

**One deliberate divergence, and one new semantic role needed.**

The stability track is implemented **locally inside `BiomarkerAnalytics.js` rather than importing a
shared `StateTrack` component from `ClosedLoopSim/`.** That directory was being rebuilt in parallel
while this pass ran, and importing a file that may not yet exist on disk would break the build for
both of us. It should be replaced by the shared component once that rebuild lands; the local version
is small and self-contained to make the swap easy.

**Requested new role: `PAL.passText` and `PAL.failText`.** The palette documents that `#E69F00` is
too low-contrast for text and supplies `warnText`; the same is true of `pass` (about 3.4:1 against
white) and `fail` (about 3.9:1), and there is no equivalent token for either. I worked around it by
keeping small text near-black and moving the semantic colour onto a swatch or a fill, but the two
pages should agree on darkened variants rather than each inventing a workaround. `PAL.failFill` and
`PAL.failBorder`, added to the palette during this pass by the parallel rebuild, cover the fill side.

---

## 6. Backend changes required — described, not made

I own no Python here. Five changes, in descending order of how much display honesty currently
depends on a frontend workaround.

1. **`modules/Biomarkers/bravo_service.py:3490-3509`, `_band_decide_verdict`.** It decides the badge
   parenthetical from `h.get("stim_stable") is False`, so it prints `VALIDATED (stim-stable)` for a
   band whose `stability_verdict` is `"inconclusive"`. It should read `stability_verdict` and emit a
   third label, for example `VALIDATED (stim stability not determinable)`. Until it does, the
   frontend rewrites the parenthetical, which works but means two places encode the same rule.
   `modules/Biomarkers/tests/test_band_candidate.py:73-76` pins the current two-label behaviour and
   would need updating with it.
2. **`modules/StimOptimizer/bravo_service.py:184`.** `"optimum_resolved": bool(arm.surface_can_resolve_its_optimum())`
   destroys a `None`. `stage1_openloop.SliceResult.resolves_its_optimum` returns `bool | None` and its
   docstring calls the `None` case "the single most important correction in this module" — a
   pulse-width stratum that never delivered the incumbent's rate has no data near that cell, and on
   the RCS08 matrix the 140 µs stratum reported a definitional zero as 1.66 points worse than it is
   and passed the resolution criterion on that fiction. That state cannot currently reach the page.
   Use `_jsonable(...)` and let `None` through.
3. **`modules/StimOptimizer/pipeline.py`, `StimArm.surface_can_resolve_its_optimum`.** It returns
   `False` when the propagated standard deviation is non-finite or non-positive, which is the same
   value it returns for a genuine negative. It should return `None` there, matching the slice-level
   method. The frontend currently recovers this state by recomputing the difference itself.
4. **Serialise the comparison rather than making the frontend redo it.** The arms payload should
   carry `gain`, `sd_of_difference` and the resolution multiple `k` alongside `optimum_resolved`.
   The page now duplicates `sqrt(sd_star² + sd_inc²)` and hardcodes `RESOLUTION_K = 1.0` mirroring
   `stage1_openloop.RESOLUTION_K`; if that constant changes, the display silently disagrees with the
   verdict beside it. This is the change I would make first.
5. **`modules/StimOptimizer/bravo_service.py:289`, `_blockers`.** `not any(a.get("optimum_resolved") for a in arms.values())`
   treats `None` as falsy, so once (2) and (3) land, an arm that cannot be assessed would still count
   towards "no arm resolved". It should count the three states separately, as the banner now does.
