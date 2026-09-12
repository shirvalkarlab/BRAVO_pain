# Where the brain-signal-to-pain calculation lives, and what moved

RCS08 (uid 2e3c75c00d7f4f37b53a048d195f11da), Medtronic Percept RC.
Starting point: HEAD 6c3c9f2 on branch PS_closedloop_deployment.

## 1. What each side was computing, before anything was changed

The two functions were read line by line before any edit. They were **not computing the same
thing**, and it is worth saying that plainly before saying what was done about it. One of them
fits a straight line to a pain score you can read off a 0-to-10 scale; the other sorts pain into
"high" and "low" and fits a curve to the odds of being in the high group. Their answers are in
different units and cannot be compared as numbers.

| | Closed-loop side: `ClosedLoopDeployment/edges.py -> state_edge` (called E2) | Biomarker page: `Biomarkers/routines/analytics.py -> band_mixedmodel_inference` |
|---|---|---|
| **What is fitted** | a straight line, `pain score = a + b x band power`, fitted by least squares | a logistic curve for the chance that pain is in the high group, `pain_high ~ band_power + (1 \| week)`, fitted in R by lme4 through pymer4 |
| **The number it reports** | `b`: how many pain-scale points the pain score changes per one unit of band power | the odds ratio: how many times more likely high pain becomes per one standard deviation of band power |
| **One row of data** | one spectral sample for one sensing channel and one 5 Hz-wide band, taken from the closed-loop joined table (`adapter.joined_table`), carrying the pain score of the report it was matched to | one rating-matched spectral sample for one channel and band, pulled out of the pooled `td_detail` structure |
| **How a pain report reaches a row** | joined on the **exposure epoch** — the stretch during which the stimulation settings did not change. In the live pipeline the identifier column `report_id` is built as `str(epoch)`, so there is one pain report per exposure epoch | each spectral sample already carries the rating it was matched to |
| **What is grouped so it counts once** | `report_id`, the pain report. If that column is absent the function refuses to estimate | the **elapsed-week index** counted from the first sample of the record, entered as a random intercept |
| **Which power scale** | **linear** band power (`power_linear`). This is the scale the stimulator itself adds up (device rule D11, `ClosedLoopDeployment/constraints.py`), so a slope meant to predict the device is on the device's own scale | **logarithmic**, 10 x log10 of mean band power, then divided by its own standard deviation (ddof=1). The stored spectral matrix holds log power already when `prelog` is set |
| **What happens to the pain score** | used as it stands, continuous | cut into thirds; the top third is "high", the bottom third is "low", the middle third is dropped |
| **How uncertainty is worked out** | grouped (CR0) standard errors when there are at least 40 groups; below that, the wild cluster bootstrap with Rademacher signs drawn once per group, null imposed, whole sign space enumerated at 12 groups or fewer, and the interval obtained by inverting that test | Wald standard error and Wald interval from lme4, exponentiated into odds-ratio space |
| **Window of record used** | the whole record | the first 3 elapsed weeks are dropped, before the thirds are cut and before the standardisation (`VALIDATION_EXCLUDE_FIRST_WEEKS`) |
| **What it needs installed** | numpy, pandas, statsmodels | R with lme4 and pymer4; returns `available: False` without them |
| **What it returns** | an `EdgeEstimate` with `estimate`, `ci`, `p`, `n`, `cluster_unit`, `n_clusters`, `scale`, `note`, and a `resolved` property | a dictionary with `available`, `coef`, `odds_ratio`, `or_lo`, `or_hi`, `z`, `p`, `separation`, `singular` |
| **Special conditions it flags** | few groups; an unbounded interval; a non-connected accepted set | perfect separation (a coefficient above 50 in size); a random-effect variance that has collapsed to nothing |

Other places on the biomarker page that relate band power to pain, none of which is the same
quantity either:

- `spectral_feature_importance` — sweeps every band, reports a cross-validated area under the ROC
  curve plus a logistic p-value with standard errors grouped on the rating.
- `deployment_roc` and `deployment_roc_by_era` — classification accuracy for one chosen band, with
  a moving-block bootstrap interval.
- `power_pain_scatter` — the device's around-the-clock ~10-minute power column against pain, a
  correlation, on a different signal entirely.
- `band_stim_stability` — whether the band's slope is the same under different stimulation states.

**Conclusion of the audit.** Nothing on the biomarker page computed the quantity the closed-loop
module needed: a slope of the continuous pain score on band power, on the linear scale the
stimulator uses, with each pain report counting once. A search of the whole Biomarkers package for
the string `power_linear` returned nothing. So this was not a duplicate calculation that had drifted
— it was a calculation that existed only on the closed-loop side, in the module that is supposed to
be a consumer of the biomarker page rather than a producer.

## 2. Which direction each piece moved, and why

The PI's instruction is that the biomarker page is the home for the brain-signal-to-pain
relationship. That settles the direction: the calculation moves to the biomarker page, and the
closed-loop module asks for it.

| Piece | Where it went | Why |
|---|---|---|
| The estimate itself | **moved** into `Biomarkers/routines/analytics.py` as `band_pain_tracking` | it answers the biomarker page's own question, so the page should own it. `state_edge` now calls it and packs the answer into the `EdgeEstimate` shape the closed-loop module reads |
| Grouped (CR0) standard errors, the wild cluster bootstrap, the interval obtained by inverting that test, the switch between the two and the `estimator_for` explanation of the switch | **moved** into `analytics.py`; `edges.py` imports the names back out unchanged | this is the "extra and genuinely useful" capability the brief anticipated. It had to move rather than be reached for, because the biomarker page may not import the closed-loop module (see below), so an estimator living on the biomarker page cannot borrow standard errors from the closed-loop one |
| A reader for the biomarker page's own spectra | **added** on the biomarker side as `band_pain_tracking_from_detail` | the page keeps its spectra in the pooled `td_detail` structure rather than in a joined table, so without this the page could not call its own new function. It also lets the page ask for the slope on the stimulator's linear scale, which is what makes a biomarker-page number comparable with a closed-loop one |
| Three separate answers, kept as words | **added** on the biomarker side as `PAIN_TRACKING_TRACKS`, `PAIN_TRACKING_NOT_RESOLVED`, `PAIN_TRACKING_NOT_ASSESSED` | see section 5 |
| The logistic mixed model, the thirds cut, the 3-week exclusion | **stayed** on the biomarker page, untouched | a different quantity, with its own audience and its own published numbers. Merging it with the slope would have been the papering-over the brief warned against |

Nothing was left behind as a second copy. A test reads the source of `state_edge` and fails if a
regression or a bootstrap call reappears inside it.

## 3. The import direction, checked in a fresh interpreter

`ClosedLoopDeployment` may import `Biomarkers`. `Biomarkers` may not import
`ClosedLoopDeployment`. The precedent was already in the repository:
`ClosedLoopDeployment/clinic_steps.py` imports `harmonic_landings_hz` from the biomarker page.

The check runs `python -B -c "from Biomarkers.routines import analytics; print(...)"` as a
**separate process** and requires the printed list of loaded closed-loop modules to be empty. Doing
this in the test's own interpreter would prove nothing, because that process imports the closed-loop
module at the top of the file, so the name would be present either way. Test:
`test_the_biomarker_module_still_does_not_import_the_closed_loop_module`. It passes.

## 4. Before and after, on the live participant

The container and the checkout turned out to be the same filesystem, so editing the files and
re-running would have compared the changed code with itself. Instead the pre-change `edges.py` was
frozen as a standalone copy (`_agent_bridge/_sync_paintracking/_paintracking_edges_before.py`, the
only edits being two relative imports made absolute), and **both versions were run on the same live
table in one pass**. The data cannot have moved between the two readings.

Every band cell on the record with at least two pain reports was compared: 6 sensing channels x 18
band centres = **108 cells**, 112,068 rows in the joined table.

- **Cells whose numbers are identical before and after: 108 of 108.** Exact equality, not a
  tolerance, on the slope, the interval, the p-value, the sample count, the group count, the sign
  and the resolved flag.
- **Cells whose numbers moved: 0.**
- **Cells whose explanatory note text is unchanged: 108 of 108.**
- Estimable cells: 108 of 108. Of those, 22 have an interval that excludes zero.

The number the deployment panel publishes, for the candidate with the most pain reports behind it
(sensing contacts 0 and 3 on the RIGHT electrode, band centred at 10.5 Hz):

| | before | after |
|---|---|---|
| slope (pain points per unit of linear band power) | -0.33835757860447285 | -0.33835757860447285 |
| 95% interval | -0.7443335807037885 to 0.06761842349484276 | identical |
| p | 0.1023540178175916 | identical |
| spectral samples | 3067 | 3067 |
| pain reports behind them | 68 | 68 |
| grouped on | `report_id` | `report_id` |
| power scale | linear | linear |
| answer | interval spans zero: **no direction established** | identical |

So the answer to "did the number move" is that it did not, and it could not have: the same
arithmetic is now reached through one function instead of two. The separate question — whether the
closed-loop slope and the biomarker page's odds ratio agree — cannot be answered by comparing the
two numbers, because they are in different units, on different power scales, with pain treated
differently in each. That comparison is now at least *possible*, because
`band_pain_tracking_from_detail(..., power_scale="device_linear")` will produce a slope from the
biomarker page's own spectra on the stimulator's scale. It has not been run here and no claim about
its value is made.

**One prose change, declared rather than hidden.** Two refusal messages were reworded when the code
moved, because they used the phrase "rating-level cluster", which the house language rule does not
allow, and because they did not name the column that was missing:

- old: `no report_id column: the rating-level cluster is unavailable, and estimating this edge
  without it would reproduce the pseudoreplication the audit flagged`
- new: `no report_id column: the grouping that makes each pain report count once is unavailable,
  and estimating this slope without it would treat every spectral sample as an independent
  observation, which is the pseudoreplication the audit flagged`

and, for the case of a single group, "fewer than two rating clusters" became "fewer than two
report_id groups; a slope needs at least two groups to be identifiable once each group counts once".
Neither sentence appears anywhere on the live record: all 108 live cells reach the estimator, so all
108 notes are byte-identical before and after. The test that asserted the old phrase was updated,
and it now also requires the message to name the missing column.

**A separate observation, not acted on.** The centre frequencies in
`_agent_bridge/validated_band_candidates_v2.csv` (83.5, 38.5, 45.5, 34.5, 32.5 Hz) mostly do not
land on the closed-loop module's band grid, so asking the closed-loop report for those candidates
returns "too few usable samples" with 0 rows, which reads like missing data rather than a grid
mismatch. That is in `adapter.py`, which belongs to another lane this session, so it was left alone
and is recorded here.

## 5. The three answers are words, and they stay three

`band_pain_tracking` returns a `verdict` that is one of three strings, never True or False:

- `"tracks"` — the interval lies wholly on one side of zero, so a direction is established.
- `"not_resolved"` — the slope was estimated and the interval spans zero (or no interval could be
  formed at all). This is a result. The slope is still reported.
- `"not_assessed"` — never estimated: a column was missing, fewer than six usable samples, or fewer
  than two groups. No slope is reported.

They are strings because a True/False value has no room for the third one, so "not assessed" gets
stored as False and then read as a negative finding, and a band that was never measured appears in a
report as a band that failed. That has happened three times in this project.

`state_edge` carries the same three states in the fields of an `EdgeEstimate`, which is what
downstream code already reads: "not assessed" arrives with no slope at all (`estimate` is None),
while "not resolved" arrives with a slope and an interval spanning zero (`resolved` is False). The
mapping drops the slope exactly when the verdict is "not assessed", so a never-assessed band can
never arrive with a number attached and be misread as a measured absence.

Three tests hold this open:
`test_band_pain_tracking_says_not_resolved_not_not_assessed_on_noise`,
`test_the_three_verdicts_are_words_that_cannot_be_read_as_true_or_false` (which asserts all three
are truthy, so a truth test cannot sort them), and
`test_state_edge_keeps_never_assessed_apart_from_no_direction_established`.

## 6. Tests and suite counts

New on the biomarker side (`Biomarkers/tests/test_analytics.py`), all 10 passing:

1. `test_band_pain_tracking_recovers_a_planted_slope_and_says_it_tracks` — a slope of 1.5 pain
   points per unit of power is planted and recovered to within 0.15, with the planted value inside
   the interval; 60 groups, 480 rows.
2. `test_band_pain_tracking_counts_each_pain_report_once_not_each_sample` — every row is copied
   five times. The slope does not move, the grouped interval width changes by under 2 per cent, and
   an ordinary least-squares interval on the same copied data is computed alongside it and shrinks
   to under 55 per cent of its original width. This measures what the grouping is protecting
   against rather than only asserting that nothing happened.
3. `test_band_pain_tracking_refuses_rather_than_treating_every_sample_as_independent`
4. `test_band_pain_tracking_says_not_resolved_not_not_assessed_on_noise`
5. `test_the_three_verdicts_are_words_that_cannot_be_read_as_true_or_false`
6. `test_band_pain_tracking_switches_to_the_bootstrap_when_there_are_few_pain_reports`
7. `test_band_pain_tracking_names_the_power_scale_it_used_and_the_scale_changes_the_slope`
8. `test_band_pain_tracking_from_detail_groups_on_the_rating_not_on_the_sample` — the expected row
   and group counts are computed from the same feature extractor rather than written in, because
   some synthetic band powers are not positive and have no logarithm.
9. `test_band_pain_tracking_from_detail_says_not_assessed_for_a_channel_that_is_not_there`
10. `test_band_pain_tracking_from_detail_rejects_a_scale_it_does_not_have`

New on the closed-loop side (`ClosedLoopDeployment/tests/test_core.py`), all 5 passing:

1. `test_state_edge_returns_exactly_what_the_biomarker_page_computes` — every field compared for
   exact equality against `band_pain_tracking` on the same table. Equality and not a tolerance, so
   a second implementation cannot creep back in.
2. `test_state_edge_does_not_do_the_arithmetic_itself_any_more` — reads the source and fails if a
   regression or a bootstrap call reappears.
3. `test_state_edge_keeps_never_assessed_apart_from_no_direction_established`
4. `test_the_biomarker_module_still_does_not_import_the_closed_loop_module` — fresh interpreter.
5. `test_the_closed_loop_module_reaches_the_biomarker_page_for_this_and_re_exports_the_toolkit`

One existing test updated: `test_state_edge_refuses_when_the_rating_cluster_is_absent` now checks
the reworded refusal quoted in section 4.

### Suite counts

| Suite | How it was run | Result |
|---|---|---|
| ClosedLoopDeployment | `PYTHONPATH=. python -B -m pytest ClosedLoopDeployment/tests -q` | **221 passed, 0 failed, 0 skipped** (216 before this work, +5 new) |
| Biomarkers | `_agent_bridge/run_tests.py` inside the container, through the bridge | **PASS=336 FAIL=0** (326 before this work, +10 new) |

The Biomarkers suite runs against the live checkout, which two other agents were editing at the
same time, so its count is not attributable to this lane alone.
