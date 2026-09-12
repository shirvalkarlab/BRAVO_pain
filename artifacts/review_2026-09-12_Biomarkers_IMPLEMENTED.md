# Biomarkers review of 2026-09-12: what was built, and what it changed

**Implements** `artifacts/review_2026-09-12_Biomarkers.md`. Written 2026-09-12 on branch
`PS_closedloop_deployment`, uncommitted (the orchestrator commits). Every number below was measured
today on the live server for RCS08 through the bridge, never carried forward from a document. The
capture files are `BRAVO/_agent_bridge/_probe_tl/bm_review_{before,after_b1,after}.pkl` and the
scripts beside them (`probe_bm_review_capture.py`, `probe_bm_review_compare.py`,
`probe_matrix_order_insensitive.py`, `probe_b7_alternating.py`).

**Files changed** (all under `BRAVO/modules/Biomarkers/` unless said otherwise): `adapter.py`,
`pipeline.py`, `bravo_service.py`, `routines/analytics.py`, new `routines/local_time.py`; four
existing test files updated and eight new ones; `CacheStore/store.py` (one entry in a table) and
`CacheStore/tests/test_keep_newest.py` (one test). Nothing under `ClosedLoopDeployment/`,
`StimOptimizer/` or `Client/` was touched by this work.

**Both test suites, re-run after the last edit** (routine run, then the live run):

```
host:      1106 passed, 43 skipped, 0 failed, 0 errors
container: PASS=630 FAIL=0 LIVE_SKIPPED=6
host (live only):      1149 deselected in 0.42s
container (live only): PASS=6 FAIL=0 (live tests only)
```

The baseline before this work was host 1073 / 42 / 0 and container 598 + 6 live. The container
gained exactly the 32 tests this work adds (598 + 32 = 630); the host gained my one CacheStore test
plus the other builders' tests landing at the same time. One earlier routine run in the middle of
this work reported one host failure; its log was overwritten within seconds by another builder's run
and the failure did not reproduce on the two runs after it, so I cannot name it, and I say so
rather than guess.

---

## FOR THE PI: B1 moved the chronic pain detector's numbers, and here is how much

**Where this is on screen.** Biomarkers page, every panel that reads the power-domain (10-minute
band-power trend) detector: the chronic pain detector's threshold, the ROC, the LFP distribution,
the sliding-window AUC, the per-contact frequency decode, and the binarization preview. All on
screen today.

**What changed.** The detector joins each 10-minute brain-signal sample to "the same calendar
day's" pain ratings, and computes the pain cut on one value per day. "Day" used to be the UTC
date, whose boundary is 4 pm (winter) or 5 pm (summer) in California, so every evening rating
was averaged into the NEXT day. It is now the California calendar day, in every place the page
derives a day from an instant: the chronic join, the legacy same-day session join (slider off),
the daily series behind the pain cut, the per-day binarization preview rows and day counts, and
the timeline's date column. One rule, one function (`routines/local_time.py`,
`local_calendar_day`), so **reversing it is a change to that one function.**

**How many ratings moved day.** Of RCS08's 766 ratings with a time, **201 (26.2 %) carried a UTC
date one day later than their California date** -- every one filed between 16:00 and 19:59 local
(16 h: 10, 17 h: 70, 18 h: 108, 19 h: 13). The review counted 193 of 678 on the June snapshot;
this is the live record today.

**The page before and after, field for field, this change alone** (the capture `after_b1` was
taken with only B1 applied):

| Block of the response | Fields before | Fields after | In common | Differing | Only before | Only after |
|---|---|---|---|---|---|---|
| whole page | 1,020,742 | 1,033,080 | 1,018,762 | 96,252 | 1,980 | 14,318 |
| `analytics.powerdomain.*` | 76,705 | 89,043 | 74,725 | 57,670 | 1,980 | 14,318 |
| `summary.powerdomain.*` | 241 | 241 | 241 | 225 | 0 | 0 |
| `analytics.timedomain.*` | 40,227 | 40,227 | 40,227 | **0** | 0 | 0 |
| `summary.timedomain.*` | 1,060 | 1,060 | 1,060 | **0** | 0 | 0 |
| `availability.*` (the timeline) | 607,381 | 607,381 | 607,381 | **0** | 0 | 0 |
| `timeline` (5,944 chronic rows) | 136,714 | 136,714 | 136,714 | 11,653 | 0 | 0 |

The fields present on one side only are the sliding-window entries: the number of windows went
from 77 to 90 because the day boundaries moved. The voltage-trace side of the page and the
timeline did not move at all.

**Of the 5,944 chronic rows** (row count unchanged): 3,839 carry a different joined rating value
(`powerdomain_nrs`), 1,554 a different high/low label, 25 a different prediction; the threshold is
one number broadcast to every row (93.61 -> 94.48). More rows move than ratings moved (26 %),
because a day's mean changes whenever any one of its ratings enters or leaves it.

**The headline numbers the page shows, before -> after:**

| Value (`summary.powerdomain`) | Before (UTC day) | After (California day) |
|---|---|---|
| area under the curve, pooled detector | 0.5906 | 0.5713 |
| its shuffle p-value (1,000 shuffles) | **0.035** | **0.102** |
| best threshold (device units) | 93.61 | 94.48 |
| number of validation windows | 77 | 90 |
| sensitivity / specificity | 0.976 / 0.017 | 0.968 / 0.020 |
| prevalence of high-pain samples | 0.139 | 0.174 |
| samples labelled high / low | 49,710 / 308,244 | 49,972 / 236,432 |
| samples in the excluded middle third | 40,255 | 111,805 |
| Spearman, band power vs continuous pain | 0.140 | 0.132 |

**So under the California day, the pooled chronic detector's shuffle test is no longer below
0.05.** The review's own reading was that the UTC day was never chosen on purpose (decision 2
made the rating timestamps California local, and nobody re-asked what "day" meant afterwards),
and that is why this was implemented without waiting; but whether the intended bin is the
California calendar day or something else (a nearest-in-time join, as the session path already
does when the slider is on) is a scientific choice and is yours. The old numbers are in
`bm_review_before.pkl`.

**No stored product carries this join**, so no rule-version constant needed a bump for it: the
power-domain detector's output goes into the page response and is not written to the cache store
(checked against every `store`/`store_if_absent` call in `bravo_service.py`: the spectrum matrix,
the REDCap snapshot, the stability grid and the band-sweep tables, none of which reads the day
join). The in-process recording memos hold recordings only.

**Test.** `tests/test_local_calendar_day.py`, seven tests: the review's own case (a rating at
18:00 local on the 21st = 01:00 UTC on the 22nd, chronic samples at local noon on the 21st and
22nd: the 21st's sample carries 7.0, the 22nd's is empty -- the UTC rule gave the opposite); the
same for the slider-off session join; the daily series behind the cut (three samples whose median
lands differently under the two rules, pinned on the labels [1, 0, 1]); the preview's daily rows
and day counts; the day turning over at 07:00 UTC in summer and 08:00 UTC in winter; and that the
service binds the same zone object. One existing fixture (`test_adapter.py`'s chronic-trend days)
built its days on UTC midnight and is now anchored on California midnight; no assertion in it was
weakened.

---

## B2 (High): a failed timeline build is no longer remembered as "no recordings"

**On screen.** Biomarkers page, the data-availability timeline at the top.

**What changed** (`bravo_service.py`): the catch-all in `_build_availability` marks its empty
payload with `failed: True` and the reason (`failure`); the memo (`_availability_result_cached`)
returns such a payload but never stores it; the page message becomes "The availability timeline
could not be built: <reason>. This is a failure, not an empty record -- the next request will try
the build again" instead of "upload sessions".

**Test.** `tests/test_availability_failure_not_memoized.py`, four tests. The endpoint is called
for real with everything below it stubbed; the build raises once (through the real catch-all) and
then succeeds: the first response carries `failed == True` and no records, the second carries the
records, the third performs no build. The genuinely-empty case still says "upload sessions" and is
still memoized.

**Live.** Two consecutive availability requests for RCS08 with no failure: 607,395 fields each, 0
differing; and before against after this change, 607,395 fields, 0 differing.

---

## B3 (Medium): RCS08's outlier ceilings apply to RCS08 only

**On screen.** Biomarkers page, the calibrated band-by-length heat maps; Closed-Loop Deployment
page, the "Choose a band" card (which reads the same stored grid).

**What changed.** `routines/analytics.py`: `BAND_SWEEP_LSB_CEILINGS` is keyed on the participant
uid first, then the contact; one lookup, `band_sweep_ceiling_table(participant_uid, channel)`,
and `band_sweep_lsb_ceiling` now takes the participant too. `bravo_service.py`:
`_band_time_sweep_power_by_seconds` and `_band_time_sweep_channels` take `participant_uid` and
read the table through that one lookup (this also closes review B9.2, the zero-caller duplicate).
`_BAND_SWEEP_RULE_VERSION` is `v10_ceilings_keyed_on_participant`, so no grid stored under the old
rule is served as if built under this one.

**Test.** `tests/test_ceilings_keyed_on_participant.py`, four tests: `ZERO_THREE_RIGHT` under a
made-up participant takes the MAD rule (`chunk_exclusion` is None), under RCS08's uid it takes
the ceilings (a dict), the 24.5 Hz ceiling on R 0-3 reads back as 498.6, and the service reads
the table only through the one lookup.

**Live.** The band sweep before and after, per contact pair: 6,077 fields (6,076 on the two right
contacts), 0 differing apart from one wall-clock timing field per contact; at the top level the
store key and `served_from_store` (True -> False, because the version bump makes the first request
a fresh build: 2.78 s served before, 8.69 s built after).

---

## B6 (Medium): the spectrum builder's two silent failures are logged and counted

**On screen.** Biomarkers page, the pooled full-spectrum panels; Closed-Loop "Choose a band" card's
stability column. The new counts are in the page response under `cache.spectrum_builder`.

**What changed** (`bravo_service.py`). `_welch_rows_into` logs both failures with the traceback and
returns `(n_centered_fell_back, n_skipped)`, adding them into a `counts` dict when given. The two
counts are stored beside the rows in each recording's own spectrum file and in the rows-set
cache, summed by `_assemble_psd_rows_cached` (which now returns a fourth value, the quality
summary), written into the matrix payload as one-element integer arrays, and read back into
`run_for_participant`'s `cache.spectrum_builder` block. A file written before the counters
existed reads as "not recorded" (`n_recordings_without_counts`), never as zero.

**Test.** `tests/test_spectrum_builder_counts.py`, four tests: a centred spectrum that raises for
one recording gives that recording a row at its START time and a count of 1 (the review's test);
a first-window failure counts as skipped; the counts survive both cache layers and a legacy file
reads as unknown; the matrix payload carries them and the page reads them back.

**Live.** The matrix reassembled from the per-recording files against the stored one: 630,442
power values and 6,242 durations, 0 differing (see B5 for the row-order note). Counters on the
live record: 0 fell back, 0 skipped, 832 recordings without counts (every file pre-dates the
counters), 0 keyed on the whole set.

---

## B4 (Medium): the two matrix writers stop evicting each other

**On screen.** Biomarkers page: nothing visible; Recompute and the calibration panel no longer
pay a reassembly after each noon ingest.

**What changed.** `CacheStore/store.py`: `KEEP_NEWEST_BY_KIND["biomarker_psd_matrix"] = 2`.
`bravo_service.py`: the rows-set file name carries its pain-set class (`_p` rating-centred,
`_nop` legacy first-window) and `_sweep_old_rows_cache` removes only the same class.

**Tests.** `CacheStore/tests/test_keep_newest.py` +1: the page's key and the ingest's key written
in turn both read back, a third key evicts the oldest. `tests/test_rows_set_cache_by_pain_set_class.py`,
three tests: a legacy and a rating-centred rows-set both remain on disk and both stay hits; a new
report set evicts only its own class; a file from before the suffix is swept.

**Live.** The stored matrix before against after, 655,511 fields, 0 differing; the store held one
matrix entry before and holds one now (the ingest has not run since). The review also asked for
alternating-round timings of Recompute after a forced legacy warm; I did not force a legacy warm
on the live server (it would write a second production matrix entry for a measurement), so no
timing is claimed for B4.

---

## B5 (Medium): a rating no longer re-computes the spectrum of every voltage-trace recording

**On screen.** Biomarkers page (Recompute; the background warm the timeline fires). Speed, not a
number.

**What was checked first.** All 386 of RCS08's voltage-trace recording rows carry `Duration` in
their metadata, decode to exactly one recording each, and the row's `date` and `Duration` equal
the decoded start time and length to the digit (`probe_b5_row_coverage.py`). So the coverage can
be read off the row with no decode, and **0 recordings took the whole-set fallback**.

**What changed** (`bravo_service.py`). `_recording_rows_for_psd` carries each row's start and
duration; `_recording_pro_signature` keys a voltage-trace recording's spectrum file on the ratings
inside `[start - 60 s, start + duration + 60 s]` (the margin guards a future ingest whose row
metadata is slightly off; it costs only that a rating within a minute of an edge invalidates that
one file); a row with no duration keeps the whole-set key and is counted
(`n_recordings_keyed_on_whole_set`). `_sweep_recording_psd_siblings` removes a recording's older
rating-centred files after the new one lands and prunes the manifest. `_migrate_whole_set_file`
moves a file built under the old whole-set key for the CURRENT report set onto the new key through
the one grandfathered per-recording writer, once, instead of re-Welching the whole record (about
190 s): the same rows, since the builder only ever used the in-coverage ratings.

**Test.** `tests/test_recording_spectrum_key_is_its_own_ratings.py`, five tests: the review's
(moving the inside rating changes the file name, moving or adding a rating a week away does not);
the 60 s margin; the fallback for a row with no duration; the assembly writes one file per
recording, re-Welches only the recording whose inside rating moved, sweeps its old file and prunes
the manifest; the migration serves the old file's rows with no decode and removes it.

**Live.** Reassembling the matrix from the per-recording files (`ForceRefresh='matrix'`) took
1.03 s and migrated the files in place: 1,604 `.npz` files before, 1,604 after. Against the stored
matrix: 232,597 of 655,511 fields differ in place, and that is row ORDER -- the property decision
53 found and measured -- because once both are sorted by time, contact and source the row identities
match row for row and **630,442 power values and 6,242 durations differ in 0** (2,222 rows sit at
a different position). Then one new rating 30 days after the last (far from every recording):
**0 recordings re-Welched, 1,604 files before and 1,604 after**, assembly 0.39 s. Under the old
key that rating re-Welched all 386 and left 386 new files.

---

## B7 (Low): recordings decoded once, not on every request

**What changed** (`bravo_service.py`). (1) `run_for_participant` reads the voltage-trace
recordings, the montage spectra and the two event-block sets from the memo the sweep and the hover
already share (`_recordings_setup_cached`). (2) The band sweep asks the store BEFORE decoding the
voltage trace; the "no recordings" answer is still reached, after the store, since a participant
with no recordings has no store key. (3) The two sign-off endpoints (`deployment_summary`,
`band_lsb_and_power`) and `_band_validation_setup` take their four recording lists from the two
memos (`_sign_off_recordings`, `_chronic_list_for`). A module switch, `RUN_REUSES_RECORDING_MEMO`,
keeps the old loads reachable for the alternating-round measurement (the decision-43 pattern).

**Live, alternating rounds old / memo / old / memo, field for field:**

| Request | old | memo | old | memo | fields | differing (every pair) |
|---|---|---|---|---|---|---|
| Biomarkers page (`run_for_participant`, both sources) | 39.62 s | 39.03 s | 39.49 s | 37.21 s | 1,033,084 | 0 |
| `deployment_summary` (L 1-3, 20.5 Hz) | 8.53 s | 3.88 s | 6.43 s | 3.82 s | 363 | 0 |
| `band_lsb_and_power` (same band) | 11.66 s | 9.24 s | 12.01 s | 9.88 s | 193 | 0 |

The page barely moves (its 39 s is elsewhere); the sign-off summary roughly halves. The sweep's own
saving (a store-served request no longer decodes the voltage trace) was not timed separately: the
version bump of B3 made today's first sweep request a fresh build.

---

## B9, B10, B11 (Low)

- **B9.1** `bravo_service._canon_channel` is now a binding of `availability._canon_channel` (the
  two were identical line for line); `test_channel_canon.py` +1 asserts they are one object.
- **B9.2** the ceiling lookup: one function, used by the service (done under B3).
- **B9.3** the three copies of the event-time parse (`datetime.fromisoformat(...).timestamp()`,
  which read a naive string in the process's own zone) now call `availability._to_epoch`, which
  reads it as UTC on every machine (decision 102). Three now-unused local `datetime` imports
  removed.
- **B9.4** `analytics._binarize_labels` mirrors `_threshold_pain_level` on a flat array and has no
  day in it, so there was nothing to change there.
- **B10** the four function-local `from modules.Biomarkers.routines import ...` (container-only
  spelling) are gone: `availability` is the module-level import, `psd_lsb_model` is imported
  package-relative. `tests/test_import_spelling.py` reads the source and fails on the next copy.
  (`bravo_service` still imports `Server.models` at module level, so it is container-only anyway;
  the guard is about the habit.)
- **B11** `_validation_tolerance_min`: a typed match tolerance of 0 or a negative value
  (`_match_tolerance_param` gives None) now falls back to the sweep's own fallback, the longest
  length of signal as minutes (5.0), instead of `float(None)` crashing the four Closed-Loop
  endpoints. `tests/test_validation_tolerance_zero.py`, two tests, on the value and on the call
  site.

---

## Not done, and why

- **B8** (analytics computed and shipped that no page reads): not touched. Deleting a
  computed-but-unread block is the PI's call (CLAUDE.md §2 principle 4); left for him.
- **B12** (two routed endpoints no page calls): flagged in the review, not for deletion; left for
  him.
- **B4's timing** after a forced legacy warm: not measured, for the reason in B4.
- **The rows-set cache and the per-recording files were not cleared or rebuilt by hand**: the
  migration in B5 handled the voltage-trace files in 1.03 s on the first reassembly, and the
  ingest's legacy files keep their names.

## Where the numbers will show next

The page's `cache.spectrum_builder` block (B6) reads 0 / 0 / 832 / 0 today: the 832 is every
recording whose file pre-dates the counters. It will fall as recordings are re-Welched for a real
reason (a moved in-coverage rating, a new upload); it is not an error.
