# Biomarkers pipeline literature audit

> Research report
> Researcher: worker-research | Date: 2026-09-22
> Confidence: MIXED — the codebase side is verified against the actual files; several literature
> citations for Percept-specific pain sensing (the "Alamri" line of work) could not be pinned to a
> single confirmed title, and the full Shirvalkar 2023 methods text sat behind a login wall, so
> that comparison rests on the abstract, press coverage and one PubMed record rather than the full
> methods section.

## Summary the PI can read in five minutes

The Biomarkers module (`BRAVO/modules/Biomarkers/`) already does several things that most published
single-patient intracranial pain-biomarker work does not: it corrects for having picked the best
band out of many (a shuffle-based check, not just a false-discovery rate), it corrects a second
time for having also picked the best out of ten signal lengths, it accounts for the fact that
successive pain reports resemble their neighbours (a block-shuffle rather than a plain shuffle), it
reports a plain count of how many surviving pairs of measurements went into each number, and it
publishes the size of its own selection bias (how big a correlation the search alone would produce
with no real effect) rather than only a pass/fail flag. A written record, `RECONCILIATION_F8.md`,
shows the team caught and fixed a subtle version of this same class of error three times running.
That is above the bar set by the two landmark papers this audit compares it to, neither of which
publishes a family-wide shuffle test.

Three gaps matter enough to flag before any biomarker claim is used to program the device.

1. **The main headline finding to date is a true negative, and it should stay one.** The 252-setting
   search reported in decision 229 varied the matching window (2 to 120 minutes), the direction, how
   many neural samples one pain report may claim, and whether clinic-visit ratings are pooled in,
   and found no band that reaches the "established" bar once the within-setting correction is
   applied — except one cell (24.5 Hz, 60 seconds of signal, a 120-minute window before each report)
   whose own correction across the 22 bands does not clear it either (its corrected p-value is 0.23,
   not below the usual 0.05 cut). **No band on this record currently supports a switching value.**
   That is the honest state of the record, not a defect in the search.
2. **Trying 252 settings, even honestly, is itself a form of researcher choice that needs its own
   accounting.** Each setting's internal correction is sound, but nothing corrects across the 252
   settings themselves, so a reader cannot say what the chance of finding at least one "established"
   cell would have been if pain and band power were entirely unrelated. This is the exact problem
   Gelman and Loken call "the garden of forking paths" — a result can be biased by all the choices
   that could have been made, whether or not they were consciously tried (Gelman & Loken, 2013/2019).
3. **When clinic-visit ratings are pooled into the search, nearly every band (11 to 22 of 22, per
   decision 229) comes out negatively associated with pain**, and clinic visits are exactly the
   occasions when the stimulation current is being deliberately stepped up and down. The device's
   own titration data already show band power moves with current directly (`METHODS_measurement_and_findings.md`
   §5, "the bands from 25 to 28 Hz rise with current and then fall"). Nothing in the heat-map search
   path adjusts for stimulation current the way the older streaming-band search does
   (`pipeline.py`'s `partial_corr` step exists only in that other path; a direct search of
   `routines/analytics.py`, which computes the heat-map grid, found no `partial_corr` or
   `stim_amplitude` term at all). A near-universal negative association appearing only when
   visit-time ratings are included is at least as consistent with "current changes both power and,
   through side effects, the rating" as with "power tracks pain."

None of this means the module is doing bad science — if anything it is unusually candid about its
own weaknesses, more so than the two flagship human studies reviewed here. It means the record on
RCS08 has not yet produced a band that should be programmed, and the tooling should keep making
that easy to see rather than easy to search past.

---

## 1. What the pipeline does today

**Signal to band power.** A "band" is a name plus 2.5 Hz on each side (a 5 Hz-wide window): the
column already stored as "12.5 Hz" is the power from 10.0 to 15.0 Hz, and neighbouring columns must
never be added together because they overlap (`METHODS_measurement_and_findings.md` §1;
`availability.py`, `band_half_hz=2.5`). The number itself comes from one of three routes, ranked by
how directly it was measured: the device's own onboard reading (used only after it passes a
per-electrode saturation check, because about 1% of its readings spike to absurd values with no
change in the underlying signal); the 250-samples-per-second voltage trace multiplied by a constant
measured against the device's own readings (345.59, decision 211); or, ranked lowest, the device's
own onboard summary multiplied by a second, composed constant. This routing lives in
`availability.py` (`live_lsb_spectrum_match` and the ceiling check) and `calibration.py`, and the
constant currently in force is drawn on the Biomarkers page's calibration card (`CalibrationInEffectPanel.js`).

**Matching a pain rating to a stretch of signal.** A report is matched to the nearest recording
within a settable time window (60 minutes by default) and a settable direction (before the report,
after it, or nearest either way), with settable limits on how many separate stretches of signal one
report may be matched to (`adapter.py`, `align_pros`; the settings themselves are parsed in
`sweep_settings.py`). At most one stretch of recording is used per report unless the analyst turns
on reuse. This is shown on the Biomarkers page's rating-count panel (`BinarizationPreview.js`,
which reports how many days and how many raw samples were kept, excluded, or fell in the low/high
group) and on the page's acquisition timeline (`BiomarkerDataTimeline.js`, which as of decision 216
draws only the recordings and the device's own settings history, not per-report circles).

**The per-cell statistic.** For the page's headline chart — the heat map of 22 named bands (8.5 to
29.5 Hz) against ten candidate lengths of signal (1 to 60 seconds) — each cell is a Pearson
correlation between that band's power and the chosen pain score, plus a version that splits pain
into a high third and low third and reports how well the band separates them (an area-under-the-curve
number). Both come with a resampling interval built from moving blocks of data rather than single
points, so that neighbouring, non-independent measurements do not make the interval falsely narrow
(`routines/analytics.py`, the block in the 5600-5900 line range; `stats_utils.block_bootstrap_picks`).
This is the grid drawn on `BiomarkerHeatmapGrids.js`. A second, older per-session search (used by the
ROC and "honest performance" cards, `BiomarkerAnalytics.js`) picks one winning sensing contact and
frequency out of a wider search (`pipeline.py`, `select_biomarker_band`).

**The correction for having searched.** Two corrections apply on top of each other for the heat map.
First, because the best of ten lengths of signal is reported, a shuffled version of the same
best-of-ten choice is run 1,000 times on scrambled pain scores (keeping their day-to-day resemblance
intact via a moving-block shuffle) to get a fair comparison level, not just the level a single length
would need to clear (`analytics._best_of_windows_null_correlation`,
`_best_of_windows_null_auc`). Second, because 22 bands were searched at once, the standard
false-discovery correction (Benjamini-Hochberg) is applied across those 22 p-values on top of the
first correction (`_apply_family_wise_correction`, decision 63). The older per-session search has its
own, independently-documented version of this same idea, and a written record
(`RECONCILIATION_F8.md`) walks through a case where the shuffle test and the search that chose the
band were quietly running on two different samples of data, so the shuffle test was not actually
testing the number the search had picked — caught, explained and fixed, with the fix proven by
re-measuring the discrepancy at machine precision (`RECONCILIATION_F8.md` §4).

**The verdict words.** A cell is only labelled `established` when both checks pass: its resampling
interval sits entirely off the "no relationship" value, and its value beats the shuffled level
(`analytics.py`, the constants `BAND_PAIN_ESTABLISHED` / `BAND_PAIN_NOT_RESOLVED` near line 3462).
"Not resolved" is not the same as "the band is useless" — it means the question was not settled
either way, and the code comments say so explicitly. These words are what a clinician reads on each
cell of `BiomarkerHeatmapGrids.js`, and the same card's "How to read this" panel currently states,
in RCS08's own numbers, that no band clears this bar under 5,544 searched combinations with
clinic-visit ratings left out (decision 229).

---

## 2. Point-by-point audit

| Choice | What the literature does | What this pipeline does | At least as rigorous? | Severity if not |
|---|---|---|---|---|
| Per-patient vs. pooled model | Shirvalkar et al. (2023, *Nat. Neurosci.*) explicitly fit a **separate** model per patient and report that the winning brain region and signal differed across their four patients — they do not claim one band generalises across people (PMID 37217725). | This pipeline is single-patient by construction (RCS08 only); every band, correlation and verdict is per-participant, per-contact, per-side. | Yes — matches the field's own practice. | Cosmetic (already correct) |
| Multiple-comparison correction across bands | Neither Shirvalkar et al. (2023) nor the aDBS biomarker papers (Little 2013; Swann 2018; Gilron 2021) report a Benjamini-Hochberg or family-wise correction across the frequency bands searched; the aDBS trials pick one pre-specified band (beta) rather than searching a grid. | This pipeline runs Benjamini-Hochberg across 22 band centres on top of a permutation correction for having also picked the best of ten signal lengths (`analytics.py`, decision 63; `pipeline.select_biomarker_band`). | **Yes, more rigorous than the cited literature** on this one axis. | — |
| Correction across analysis *settings* (window length, direction, cap, clinic-sheet inclusion) | Gelman & Loken's "garden of forking paths" argument is the standard citation for why this matters even when no single analysis is "p-hacked": the number of paths that *could* have been taken inflates the false-positive rate of the one path that was (Gelman & Loken, 2013, updated 2019, Columbia Statistics working paper). | The 252-setting search (decision 229) applies the two corrections above *within* each setting, but nothing corrects *across* the 252 settings. The one near-hit (24.5 Hz, q = 0.23) is reported honestly as not clearing the bar, but the framework that would say "how surprising is it that 1 of 5,544 tests nearly cleared 0.05" does not exist. | **No** — this is the field's own unsolved problem, not unique to this codebase, but the codebase has the machinery to close it (a single further permutation over the whole search) and has not. | Weakens a claim (there is currently no positive claim resting on this, so it blocks nothing today, but would block one tomorrow) |
| Serial correlation in the outcome (day-to-day pain repeats) | Politis & Romano's circular block bootstrap (1992) is the standard method for resampling dependent time series without breaking short-range structure; it is standard in econometrics and increasingly in neuroscience but not universal in the DBS-biomarker papers reviewed (none of the four aDBS papers above report a block-adjusted interval). | Used throughout: `stats_utils.circular_block_perm_matrix`, `block_bootstrap_picks`, `effective_n` (a Bartlett/Bretherton adjustment to the sample size itself). Block length is *measured* from the data's own autocorrelation rather than fixed (`stats_utils.block_length_for`), with an unusually candid docstring admitting the block-length rule is not the only defensible one and that it was tested and reverted once. | **Yes, more rigorous than the cited literature.** | — |
| Handling of the permutation test's own resolution limit | Standard permutation methodology (e.g., Anderson & Robinson's work on permutation p-values) notes that a rotation-style null with only *n* distinct outcomes has a hard floor on the smallest p-value it can report, and that this floor should be stated rather than silently rounded. | The code computes and reports this floor explicitly (`stats_utils.permutation_null_resolution`, `perm_p_floor` / `perm_p_step` fields) and warns when a reported p sits close to a conventional cut-off relative to that floor (at 72 ratings, the floor is about 0.014). | **Yes**, and unusually transparent about it. | — |
| Artefact contamination from the stimulator itself | Hammer et al. (2022, *Stereotact. Funct. Neurosurg.*) found the Percept device produces **no** sub-100 Hz subharmonic artefacts (unlike earlier bidirectional DBS devices), but does show electrocardiogram contamination in essentially all recordings taken with stimulation on, plus ramping-related artefacts when the current itself is changing. Neumann et al. and related work report the same ECG finding and give a prevalence figure (65.2% of one cohort's recordings showing an identifiable cardiac artefact on one implant side). | The Biomarkers module marks, but does not remove, harmonic landings of the *stimulation rate itself* (55 Hz lands at 5, 25 and 30 Hz; 145 Hz lands at 15 and 25 Hz — `DEVICE_percept_rc.md` §9, `analytics.harmonic_landings_hz`). No code in `BRAVO/modules/Biomarkers/` was found that identifies or removes an electrocardiogram artefact, and no test file name (52 files under `tests/`) mentions ECG or cardiac contamination. | **No** on the cardiac-artefact axis specifically. The harmonic-marking is a documented, deliberate choice (a warning, never a refusal — decision 220), which matches the "characterise, don't blindly remove" stance Hammer et al. take toward some artefacts, but cardiac contamination is a different, well-characterised artefact this platform does not appear to check for at all. | Weakens a claim on any band below roughly 2 Hz-equivalent harmonics of a typical adult heart rate (order 1-1.5 Hz and its harmonics up through the low band range); most immediately relevant to the lowest analysed centres (8.5-11.5 Hz region, where a heart-rate harmonic could in principle land depending on rate) |
| Cross-validation / out-of-sample checking | Bergmeir & Hyndman's methodological work establishes that naive k-fold cross-validation on serially dependent data leaks information across folds, and recommends forward-chaining (train on the past, test on the future) instead. | The project's own decision log records this exact fix once already (decision 12: "Forward-chaining out-of-sample validation; in-sample hid reversals 0.55→0.24"), and the module's own README states plainly that the chronic-trend detector's in-sample AUC (≈0.69) does **not** reproduce out-of-fold (CV balanced accuracy ≈0.51, chance) — and reports the honest number rather than the flattering one (`README.md`, "Statistical rigor"). | **Yes** — matches best practice, and is unusually willing to report a negative validation result rather than lead with the in-sample number. | — |
| Pain-rating reliability / minimal meaningful change | The published minimal clinically important difference (MCID) for an 11-point numeric or visual pain scale in chronic pain populations is commonly cited as roughly 1 to 2.5 points (with wide study-to-study variation; a systematic review reports the median absolute MCID at about 2.3 points on a 0-10 scale and notes it depends heavily on baseline pain and the method used to compute it — Olsen et al., *J. Clin. Epidemiol.*, 2018). Test-retest reliability of the numeric rating scale is generally reported as good among literate respondents (r around 0.94) but markedly lower among those who cannot read the scale unaided (around 0.71). | The project has its own, measured "reliable change" statistic (short-gap pairwise scatter per score, decision 104/111/112) rather than importing a literature MCID, and treats it as a warning, never a blocker. No code in `Biomarkers/` was found that compares a correlation's effect size against the rating scale's own minimal meaningful change — i.e., a correlation could be statistically "established" while resting on pain differences smaller than what a patient would notice. | Partial — the project measures its own version of test-retest noise (arguably better, since it is participant-specific rather than borrowed from a different population), but does not connect that number to whether the *pain difference driving a correlation* is clinically meaningful. | Weakens a claim |
| Ecological-momentary-assessment sampling density | The chronic-pain EMA methodology literature recommends 3-5 prompts per day as the practical range balancing data density against participant burden, and reports typical study designs averaging about 5 prompts/day (a 2018 systematic review, *J. Pain*). Shirvalkar et al. (2023) report a mean of about 3.2 ratings per day for their example participant. | RCS08's rating density was not independently re-measured in this audit (out of scope; the symptom-time-series worker owns this), but the matching-window analysis already in this codebase (60-minute default tolerance, up to 120 minutes in the 252-setting search) implies ratings are considerably sparser than every-few-hours EMA density, since a 120-minute window is being used to find *any* usable neighbour at all. | Cannot fully assess without the density number (see Gaps). | Weakens a claim (if density is much lower than the EMA literature's working range, every interval and effective-sample-size correction in this module is doing more work than it looks like) |
| Stationarity / drift over months | Long-term Percept recordings show a measured diurnal (time-of-day) component to band power in Parkinson's patients — time of day explained 41% ± 9% of beta-power variance in one chronic-recording study — and separately warn that movement artefacts can produce apparent slow drifts that are not physiological (a 2022 chronic-recording study, published in *npj Parkinson's Disease*). | This project's explicit standing rule is that **time is modelled nowhere**, and drift is treated only as a consequence of the stimulation current itself changing over the trial, not of the calendar (decisions 193-196). | **No** — this is a known, published confound (time-of-day effects on band power) that the current design does not check for, by policy rather than oversight. See recommendation 3 below on whether that policy should be revisited only for a diagnostic check, not for reversal. | Weakens a claim |
| Confounding by stimulation amplitude in the band-power/pain correlation | Any correlational analysis pairing a neural signal to a symptom while amplitude is being adjusted needs some accounting for amplitude as a shared cause of both the signal (directly, since higher current changes band power — see the E1 dose-response finding, decision 126/197/213) and, through side effects, the rating. Provenza et al.'s and Scangos et al.'s closed-loop biomarker-discovery methodology (pairing resting-state neural activity with symptom ratings) is explicit that biomarker discovery sessions were run at a *fixed*, stable therapy setting for this reason. | The older per-session search does adjust for this (`pipeline._band_inference`'s `stats_utils.partial_corr` against stimulation amplitude). A direct search of `routines/analytics.py` — the module that computes the heat-map grid used for the 252-setting search — found no `partial_corr` or `stim_amplitude` term at all. Decision 229's finding that 11-22 of 22 bands come out **negatively** associated with pain once clinic-visit ratings are pooled in is exactly the pattern a shared amplitude effect would produce, and clinic visits are stated elsewhere in the record to be occasions when current is deliberately stepped (`sweep_settings.include_clinic_sheet_ratings_param`'s own docstring: "the sheet steps were taken while current was being stepped on purpose"). | **No**, on the heat-map path specifically. | **Blocks a claim** — any positive or negative finding from a clinic-sheet-inclusive sweep should not be read as a pain relationship until amplitude is accounted for |

---

## 3. Robustness gaps

**Autocorrelation handling.** Handled well and is a strength, not a gap: block bootstrap intervals,
a block-permutation null whose block length is measured from the data rather than assumed, and an
effective-sample-size correction (Bartlett/Bretherton) applied to every reported p-value and interval
(`stats_utils.py`; confidence: HIGH, verified by reading the functions and their test file,
`test_stats_utils.py`). One caveat the code itself states and this audit confirms by reading it: the
block-length estimator assumes the dependence decays geometrically (an AR(1) shape), measured the
actual decay on RCS08 and found it does **not** decay that way for one of the two outcome metrics
(`nrs`), so the "block length 1" the estimator returns there happens to be the right answer for the
wrong reason — a full circular rotation rather than a genuinely short block
(`stats_utils.block_length_for`'s own docstring, lines ~157-180). Confidence: HIGH that this is
stated accurately in the code; MEDIUM on whether it generalises to a different outcome metric or a
future participant, because the docstring itself calls this an "open design question, deliberately
not resolved."

**Multiplicity across lengths × bands × windows × scores × directions.** The two corrections inside
one setting (best-of-ten-lengths permutation, then Benjamini-Hochberg across 22 bands) are sound and
independently documented (`DESIGN_biomarker_pipeline_v2.md` §8g; confidence: HIGH). The 252-setting
search that produced decision 229's headline numbers is a different kind of multiplicity — trying
many *matching rules*, not many *bands* — and nothing in the pipeline corrects across that axis. This
is precisely Gelman and Loken's point: the researcher does not need to have "fished" through all 252
combinations by hand for the result to be biased by the fact that 252 combinations *existed* to
choose among (Gelman & Loken, 2013/2019). The current write-up of decision 229 is honest about this
(it reports the full 5,544-row denominator and states plainly that 0 rows clear 0.05, and separately
flags the near-hit's own corrected q as 0.23), so no false claim is being made today — but if a future
setting *does* clear a corrected p by chance, there is currently no machinery to say how likely that
was to happen anyway by trying enough settings. Confidence: HIGH that no cross-setting correction
exists (verified by reading the sweep and grid code end to end); MEDIUM on how large the resulting
bias would be in practice, since it depends on how correlated the 252 settings are with each other
(a 120-minute window and a 119-minute window are not 252 independent draws).

**Stationarity and drift.** The project's decision to model no calendar-time effect and attribute
drift entirely to changes in stimulation current (decisions 193-196) is a considered position, not
an oversight, and it is defensible given the DBS pain literature's own emphasis on stimulation as the
dominant lever. But the published aDBS literature on chronic Percept recordings independently in
Parkinson's disease found a real, sizeable time-of-day effect on band power unrelated to stimulation
(41% ± 9% of beta-power variance explained by time of day in one chronic-recording cohort; a
2022 npj Parkinson's Disease study). Confidence: MEDIUM that the same effect exists on RCS08's chronic
pain record, because it was measured in a different disease and target and has not been tested here;
this audit did not re-run that check, and it is explicitly one this pipeline's design choice would
currently prevent from surfacing even if present, since no time-of-day term is fit anywhere.

**Artefact contamination in the analysed range.** The device's own harmonic-landing table
(`DEVICE_percept_rc.md` §9) is measured and specific: at the current rates in force, 55 Hz lands at 5,
25 and 30 Hz, and 145 Hz lands at 15 and 25 Hz, contaminating 33 of the platform's 98 stored bands
including eight of the 22 heat-map centres (22.5-29.5 Hz). This is marked on every affected row as a
warning (decision 220) rather than silently hidden, which matches how Hammer et al. (2022) recommend
treating a *characterised* artefact — flag rather than blindly subtract. But the same paper and the
related literature on Percept artefacts (electrocardiogram contamination, essentially universal with
stimulation on) describe a second artefact source this audit found no matching check for anywhere in
`BRAVO/modules/Biomarkers/`: no function name, docstring or test file (of 52 test files) mentions ECG,
cardiac, or heartbeat contamination. Confidence: HIGH that the harmonic-landing check exists and is
well-documented; HIGH that no cardiac-artefact check exists in this module (a targeted search found
none); MEDIUM on how much this matters for RCS08 specifically, since a cardiac artefact's exact
frequency and harmonics depend on that participant's own heart rate at the time of recording, which
this audit did not have access to measure.

**Rating reliability.** The project's own "reliable change" statistic is participant-specific and
arguably better-grounded than an imported literature MCID, but confidence: MEDIUM that it is
connected anywhere to whether a correlation's effect size clears that bar — this audit found the
statistic computed (decisions 104/111/112) but did not find it referenced inside the heat-map grid's
own verdict logic (`analytics.py`'s established/not-resolved constants make no reference to a
reliable-change value). A correlation could in principle be "established" by the grid's own
definition while resting on pain differences below what this participant's own ratings can reliably
distinguish.

**Clinic-sheet ratings merged with home ratings.** Decision 186 already treats this as
consequential enough to be off by default, and decision 228 records a real bug once found in how
the drill-down view merged the two sources. The remaining gap, not yet closed as of this audit, is
the confound described in the point-by-point table above: clinic visits are the occasions the
stimulation current is deliberately changed, and the near-universal negative association seen only
when clinic-sheet ratings are pooled in (decision 229) is exactly the signature a shared-current
effect would leave. Confidence: HIGH that no amplitude adjustment exists on this analysis path
(verified by grep); MEDIUM on whether amplitude is in fact the explanation, since this audit did not
re-run the correlation with amplitude partialled out.

**Single-participant inference.** Handled correctly by not overclaiming: every verdict, decision
row and heat-map cell is scoped to RCS08 by name, and the frontend's own headline text says so
explicitly ("for RCS08 only," `BiomarkerHeatmapGrids.js` line 120). This matches Shirvalkar et al.'s
(2023) own practice of not pooling across their four patients. Confidence: HIGH.

**Effect-size reporting.** A genuine strength: the module reports both the "unfolded" area under the
curve (which can fall below 0.5, and does — 0.208 to 0.787 on the live record,
`METHODS_measurement_and_findings.md` §3) and the direction-folded version separately, with 0.5 as
the explicit no-relationship reference rather than zero, and states this cannot be conflated in one
colour scale. It also reports, for the selected band in the older per-session search, the size of the
correlation the search alone would produce with no real effect (the "winner's curse" summary,
`pipeline._band_inference`, fields `perm_null_max_mean` / `perm_obs_exceeds_null_p95`). This is a
level of honesty about effect-size inflation that this audit did not find matched in any of the
reviewed published DBS-biomarker papers. Confidence: HIGH.

---

## 4. Ranked recommendations

Ordered by how much a missed claim would cost, not by how easy the fix is. Each names whether it
reverses a standing decision (none of the ten do), an estimate of the work, and the evidence behind
it.

1. **Must fix before any positive claim: adjust the heat-map correlation for stimulation amplitude,
   or explicitly restrict the search to fixed-amplitude windows.** Evidence: a direct search of
   `routines/analytics.py` found no `partial_corr` or `stim_amplitude` term anywhere in the grid the
   heat map and the 252-setting search read; the near-universal negative association seen only when
   clinic-visit ratings (taken during deliberate current changes) are pooled in is the textbook
   signature of a shared cause. Cost: low — the adjustment (`stats_utils.partial_corr`) already
   exists and is wired into the *other* search path (`pipeline._band_inference`); porting it means
   adding one term per cell and reporting the adjusted value alongside the raw one, the same pattern
   already used elsewhere on this page. Does not reverse a decision — decision 186 already treats
   clinic-sheet inclusion as something to look at deliberately, not by default; this makes that look
   honest rather than confounded.

2. **Must fix before any positive claim: report a correction across the 252-setting search itself, not
   only within each of its 220-cell grids.** Evidence: Gelman & Loken's garden-of-forking-paths
   argument, and the fact that decision 229's own near-hit (q = 0.23 within its own 22-band family)
   has no stated probability of arising anyway from trying 252 related searches. Cost: medium — the
   cheapest version is a second-level permutation: shuffle the pain series once, rerun the same
   252-setting sweep on the shuffled series, and report what fraction of shuffles produce at least one
   "established" cell; repeating that a few hundred times gives an honest family-wide reference level.
   This reuses machinery that already exists (`circular_block_perm_matrix`) at the cost of running the
   already-built sweep many more times, which is why it is medium rather than low. Does not reverse a
   decision.

3. **Would strengthen: check for a time-of-day or day-of-week component in band power, as a
   diagnostic, without changing the standing rule that time is not modelled in the switching-value
   design.** Evidence: an independently published chronic-Percept-recording study found time of day
   explained 41% of beta-power variance in a different disease and target; this project has not
   checked whether an analogous effect exists on RCS08's record. Cost: low — a single correlation of
   band power against hour-of-day or day-of-week, reported once, not wired into any verdict. This
   would explicitly be a diagnostic that could inform whether decision 193-196 ("time is modelled
   nowhere") should stay as is; it does not itself reverse that decision, and any change to the
   decision would need the PI's sign-off per house rule 8.

4. **Would strengthen: add a cardiac-artefact check.** Evidence: the Percept-artefact literature
   (Hammer et al. 2022; related ECG-artefact papers) reports electrocardiogram contamination in
   essentially all recordings taken with stimulation on; no function, docstring or test in this module
   checks for it, while the harmonic-landing check for the stimulator's own rate is already built and
   well-tested. Cost: medium — needs either an estimate of the participant's heart rate at each
   recording (from the recording metadata, if timestamped closely enough to a clinical heart-rate
   reading) or a spectral peak-finding pass on the raw voltage trace to flag a likely cardiac line
   the way `harmonic_landings_hz` already flags the stimulator's line. Does not reverse a decision.

5. **Would strengthen: connect the reliable-change statistic to the heat-map's verdict wording.**
   Evidence: the project already computes a participant-specific reliable-change number
   (decisions 104/111/112); the house-rules-mandated distinction between "established" and
   "clinically meaningful" is not currently made anywhere in the grid's own text. Cost: low — one
   additional sentence per established cell, comparing its effect size (in raw pain-scale units, not
   only in a correlation) against the participant's own measured reliable-change value. Does not
   reverse a decision.

6. **Would strengthen: publish, once, how many ratings per day RCS08 actually provides, and compare it
   explicitly against the density the matching-window settings imply.** Evidence: the chronic-pain
   ecological-momentary-assessment literature recommends 3-5 ratings per day; Shirvalkar et al. (2023)
   report about 3.2/day for their comparable participant; this project's own 60-to-120-minute matching
   windows suggest RCS08's density may be considerably lower, but this audit could not verify the
   actual number (it is the symptom-time-series worker's territory and was out of scope here). Cost:
   low, if the number already exists elsewhere in the platform; otherwise a one-off count. Does not
   reverse a decision.

7. **Would strengthen: state, once per report, the effective (not raw) number of independent pain
   reports behind the headline number the clinician actually reads.** Evidence: `effective_n` is
   already computed per cell internally, but the plain "how many measurements" language a clinician
   sees on the page-level summary (as opposed to the underlying JSON) was not verified in this audit
   to always be the effective count rather than the raw one. Cost: low if it is already wired through
   consistently; this audit flags it as a point to double-check rather than a confirmed defect (see
   Gaps). Does not reverse a decision.

8. **Would strengthen: extend the F8-style reconciliation check (verifying, cell for cell, that a
   permutation family is built from exactly the rows and masks the selection grid used) to the
   heat-map's own permutation path, not only the older per-session search.** Evidence: `RECONCILIATION_F8.md`
   documents this defect occurring, and being caught, three separate times in the older path; the
   newer heat-map sweep (`analytics.py`) was not verified in this audit to carry the same
   cell-for-cell reconciliation check the older path now has (`perm_family_reconciled`,
   `perm_family_max_abs_dev_from_corr`). Cost: medium — requires adding the equivalent published
   fields to the sweep's own null-building functions and one live-data proof, following the pattern
   `ARCHITECTURE_cache_store.md` §5 already requires for any change to how a number is produced. Does
   not reverse a decision; extends an existing, PI-endorsed pattern.

9. **Would strengthen: log, once, whether the exploratory search's 252 settings were in fact drawn
   from a pre-specified list or built up interactively while looking at intermediate results.**
   Evidence: Wicherts et al.'s pre-registration checklist (cited via Gelman & Loken) asks researchers
   to either fix a choice in advance or disclose that it was not fixed; the audit could not determine
   from the code alone which of the 252 settings were chosen before seeing any result and which were
   added afterward. Cost: very low — a one-paragraph note in the decision log or the search's own
   output recording how the setting list was built. Does not reverse a decision; it is a
   documentation gap, not a code gap.

10. **Cosmetic but worth doing: state, on the heat-map card itself, the same "established requires
    surviving a search across many settings" caveat that decision 229's write-up already states in the
    decision log, so a reader of the page alone (not the decision log) sees it.** Evidence: house rule
    12 requires that an explanation stand on its own without having read the code or, by extension,
    a separate document; the current "How to read this" text on `BiomarkerHeatmapGrids.js` (lines
    120-131) already carries the RCS08-specific headline numbers, so this is a small addition, not a
    new feature. Cost: very low. Does not reverse a decision.

---

## 5. Gaps and what I could not verify

- **The full methods section of Shirvalkar et al. (2023, *Nat. Neurosci.*)** sat behind a login
  redirect during this research session; the comparison above rests on the abstract, a PubMed record,
  press coverage (UCSF, NIH, an Issues.org interview) and search-engine-surfaced excerpts rather than
  a direct read of the paper's statistics section. In particular, I could not confirm from a primary
  source exactly how that paper corrected (if at all) for searching across candidate frequency bands
  within each patient's per-patient model, which is the single most load-bearing comparison in this
  audit's table. Confidence in that specific row: MEDIUM, not HIGH.
- **"Alamri" on Percept-based chronic-pain sensing.** The assignment named this as a source to check;
  repeated searches surfaced DBS-for-chronic-pain review articles that cite "Alamri and Pereira" as
  authors of a related review, but I could not confirm a specific title, year, journal or DOI for a
  paper matching the assignment's description well enough to cite it directly. This citation is
  flagged as unverified rather than included as fact.
- **RCS08's actual ratings-per-day density** was not measured in this session (explicitly the
  symptom-time-series worker's scope per the task boundary); the ecological-momentary-assessment
  comparison in §3 is therefore a comparison against a *literature range*, not against a *measured*
  RCS08 number, and recommendation 6 exists specifically to close that gap.
- **Whether the page-level (as opposed to JSON-level) clinician-facing text always states the
  effective rather than the raw sample count** was not fully traced through every card; this audit
  read the backend fields (`n_effective` is present and distinct from `n`) but did not exhaustively
  check every frontend card that might print `n` instead of `n_effective`. Recommendation 7 reflects
  this as an open question rather than a confirmed defect.
- **Whether the heat-map sweep's own permutation path (as opposed to the older per-session search)
  already carries the F8-style cell-for-cell reconciliation check** was not fully confirmed; this audit
  read the sweep's null-building functions (`_best_of_windows_null_correlation`,
  `_best_of_windows_null_auc`) and found no `perm_family_reconciled`-style published field there, but
  did not read every line of `routines/analytics.py` (a roughly 400 KB file, far larger than could be
  read in full in this session) end to end, so a reconciliation check elsewhere in that file cannot be
  fully ruled out. Recommendation 8 is written to hold regardless of which is true.
- **Whether a cardiac artefact is in fact present and consequential on RCS08's specific recordings**
  was not measured; this audit confirmed only that no code checks for one, not that one is present.
- **The exact citation for "Sani" and "Ramirez-Zamora"** on Percept-based pain sensing, as named in
  the assignment, was not independently confirmed to a specific paper within the search budget of this
  session; general DBS-for-chronic-pain review literature references overlapping author groups, but no
  single title could be pinned down with confidence high enough to cite directly.

---

## 6. Source index

**Codebase (read directly this session).**
- `BRAVO/modules/Biomarkers/pipeline.py` — `select_biomarker_band`, `_autocorr_adjusted_pgrid`,
  `_band_inference`, `_block_perm_maxcorr_pvalue`, `run_timedomain_branch`, `run_powerdomain_branch`.
- `BRAVO/modules/Biomarkers/routines/stats_utils.py` — `bh_fdr`, `effective_n`, `partial_corr`,
  `block_length_for`, `circular_block_perm_matrix`, `block_bootstrap_picks`,
  `permutation_null_resolution`, `mad_outlier_flags`.
- `BRAVO/modules/Biomarkers/routines/analytics.py` — the band-by-length sweep (lines ~5660-5920),
  `_best_of_windows_null_correlation`, `_best_of_windows_null_auc`, `_apply_family_wise_correction`,
  the `BAND_PAIN_ESTABLISHED` / `BAND_PAIN_NOT_RESOLVED` constants (~3462-3465).
- `BRAVO/modules/Biomarkers/routines/sweep_settings.py` — the matching and split settings a stored
  grid is built under, `sweep_settings_tag`.
- `BRAVO/modules/Biomarkers/adapter.py` — `align_pros`, `mad_outlier_mask`.
- `BRAVO/modules/Biomarkers/README.md`, `RECONCILIATION_F8.md`.
- `Client/src/views/Reports/Biomarkers/BiomarkerHeatmapGrids.js` (the "How to read this" drawer,
  lines ~120-131, carrying decision 229's headline numbers).
- `METHODS_measurement_and_findings.md`, `DESIGN_biomarker_pipeline_v2.md`, `DEVICE_percept_rc.md`
  (§9, the harmonic-landing table), `DECISIONS_and_open_items.md` (decisions 63, 104, 111, 112, 126,
  186, 193-199, 202-211, 216, 220, 228, 229).

**Literature.**
1. Shirvalkar P, et al. "First-in-human prediction of chronic pain state using intracranial neural
   biomarkers." *Nature Neuroscience*, 2023. PMID 37217725.
   https://pubmed.ncbi.nlm.nih.gov/37217725/ — accessed via PubMed record, abstract and secondary
   coverage only (see Gaps).
2. Little S, et al. "Adaptive deep brain stimulation in advanced Parkinson disease."
   *Annals of Neurology*, 2013;74(3):449-457. doi:10.1002/ana.23951.
   https://onlinelibrary.wiley.com/doi/abs/10.1002/ana.23951
3. Swann NC, et al. "Adaptive deep brain stimulation for Parkinson's disease using motor cortex
   sensing." *Journal of Neural Engineering*, 2018;15(4):046006.
4. Gilron R, et al. "Long-term wireless streaming of neural recordings for circuit discovery and
   adaptive stimulation in individuals with Parkinson's disease." *Nature Biotechnology*, 2021.
   PMID 33941932. https://www.nature.com/articles/s41587-021-00897-5
5. Oehrn CR, et al. "Chronic adaptive deep brain stimulation versus conventional stimulation in
   Parkinson's disease: a blinded randomized feasibility trial." *Nature Medicine*, 2024.
   PMID 39160351. https://www.nature.com/articles/s41591-024-03196-z
6. Scangos KW, et al. "Closed-loop neuromodulation in an individual with treatment-resistant
   depression." *Nature Medicine*, 2021;27(10):1696-1700. doi:10.1038/s41591-021-01480-w.
   https://www.nature.com/articles/s41591-021-01480-w — cited for its biomarker-discovery
   methodology (pairing resting-state neural activity with symptom ratings at a fixed therapy
   setting); the exact "Provenza 2021" citation named in the assignment could not be independently
   pinned to a distinct title (see Gaps).
7. Hammer LH, Kochanski RB, Starr PA, Little S. "Artifact characterization and a multipurpose
   template-based offline removal solution for a sensing-enabled deep brain stimulation device."
   *Stereotactic and Functional Neurosurgery*, 2022;100(3):168-183.
   https://pmc.ncbi.nlm.nih.gov/articles/PMC9064887/
8. Diurnal modulation of subthalamic beta oscillatory power in Parkinson's disease patients during
   deep brain stimulation. *npj Parkinson's Disease*, 2022. https://www.nature.com/articles/s41531-022-00350-7
9. Gelman A, Loken E. "The garden of forking paths: Why multiple comparisons can be a problem, even
   when there is no 'fishing expedition' or 'p-hacking' and the research hypothesis was posited
   ahead of time." Columbia University working paper, 2013 (revised 2019).
   https://sites.stat.columbia.edu/gelman/research/unpublished/p_hacking.pdf
10. Politis DN, Romano JP. "A circular block-resampling procedure for stationary data." In
    *Exploring the Limits of Bootstrap*, 1992 (standard citation for the circular block bootstrap
    used throughout `stats_utils.py`).
11. Bergmeir C, Benítez JM. "On the use of cross-validation for time series predictor evaluation."
    *Information Sciences*, 2012. https://www.sciencedirect.com/science/article/abs/pii/S0020025511006773
    (forward-chaining / rolling-origin evaluation, the method decision 12 independently adopted.)
12. Olsen MF, et al. "Minimum clinically important differences in chronic pain vary considerably by
    baseline pain and methodological factors: systematic review of empirical studies."
    *Journal of Clinical Epidemiology*, 2018. https://www.jclinepi.com/article/S0895-4356(18)30124-0/abstract
13. Ecological Momentary Assessment Methodology in Chronic Pain Research: A Systematic Review.
    *The Journal of Pain*, 2018. https://www.jpain.org/article/S1526-5900(18)30030-0/fulltext
14. Numeric Pain Rating Scale test-retest reliability summary. RehabMeasures Database.
    https://www.sralab.org/rehabilitation-measures/numeric-pain-rating-scale

**Not independently confirmed (named in the assignment, not cited above as fact).** A specific,
citable "Alamri" paper on Percept-based chronic-pain sensing; a specific "Sani" or "Ramirez-Zamora"
paper on the same topic; a specific "Provenza 2021" depression paper distinct from Scangos et al.
2021 (see note on source 6). These are flagged in §5 rather than fabricated.
