# Code review, 2026-09-12: the Biomarkers module

**Scope.** `BRAVO/modules/Biomarkers/` (`bravo_service.py` 8,097 lines, `pipeline.py`, `adapter.py`,
`routines/*.py`), plus the `CacheStore` and `DecodeCommon` call sites it makes. Read-only; nothing
outside this file was edited, no test suite was run, nothing went through the container bridge.
Every line number below was read today from the checkout at commit `87db3b1a`; they will move.
The test audit of this morning (`test_audit_2026-09-12_Biomarkers.md`) is not repeated here.

## Summary

- **Findings: 0 Critical, 2 High, 4 Medium, 6 Low.** 10 are CONFIRMED (both sides read), 2 are
  PLAUSIBLE.
- **The most important one (B1):** the power-domain pain detector on the Biomarkers page joins each
  10-minute brain-signal sample to "the same calendar day's" pain ratings using the **UTC** calendar
  date, whose boundary falls at 4-5 pm in California, so every evening rating is filed under the
  next day -- 193 of the 678 ratings in the June snapshot (28.5 %), all of them 4-7 pm local.
- **The second (B2):** if the data-availability timeline's build fails once for any reason, the
  empty answer is memoized and the page says "No Percept recordings decoded" until the next pain
  rating changes the key or the worker restarts.
- The four Mediums are: RCS08's personal outlier ceilings applied by contact NAME to any participant
  (B3); two caches that keep one entry per participant but are written under two different keys by
  two live callers, so they evict each other daily (B4); every new pain rating re-computing the
  spectrum of all 386 voltage-trace recordings and leaving 386 new files behind (B5); two silent
  `except` blocks in the spectrum builder that substitute a different spectrum or drop a recording
  with no log (B6).
- Exception handlers counted: 102 in `bravo_service.py`, 163 across the module. The ones where the
  page cannot tell a failure from a real answer are named in §B and in the closing table.

---

## B1 -- HIGH, CONFIRMED. The "same calendar day" join in the chronic detector uses UTC dates

**Where it lives.** Biomarkers module, `BRAVO/modules/Biomarkers/adapter.py`:

- `align_pros`, lines 143-147:
  ```python
  if "_pro_time_utc" in df.columns:
      df[timestamp_col] = pd.to_datetime(df["_pro_time_utc"], errors="coerce")
  ...
  df["_date"] = df[timestamp_col].dt.date
  ```
  `_pro_time_utc` is the rating's instant converted to UTC (that conversion is correct, decision 2).
  `.dt.date` of a UTC instant is the **UTC** calendar date.
- The chronic path, lines 268-284: `chronic_ts = [_to_datetime(t) for t in time]` (device times,
  UTC, via `utcfromtimestamp`), then `chronic_dates = ... ts.date()` and
  `joined = df.groupby("_date")[present_metrics].mean().reindex(chronic_dates)` -- every chronic
  sample gets the mean of the ratings whose **UTC** date equals the sample's **UTC** date.
- `_threshold_pain_level`, lines 519-521: `day = pd.to_datetime(df["timestamp"]).dt.floor("D")` --
  the "one value per day" series the tertile / median cut is computed on is also UTC-day binned.
- The legacy session path (slider off), lines 226-247, does the same with `df["_date"]`.

**Who calls it.** `bravo_chronic_to_lfp_df` (`adapter.py:609`) -> `pipeline.run_powerdomain_branch`
(`pipeline.py:1351`, and per contact at `:1523`) and the fallback at `bravo_service.py:3315`.

**On which page.** Biomarkers page, every power-domain panel: the chronic pain detector's threshold,
the ROC, the LFP distribution, the sliding-window AUC, the per-contact frequency decode and the
binarization preview (`BiomarkerAnalytics.js:190-191, 304-306, 667, 1007`). On screen today.

**What is wrong, concretely.** UTC midnight is 4 pm PST / 5 pm PDT. A rating filed at 6 pm Monday in
California is 01:00 or 02:00 Tuesday UTC, so it is averaged into Tuesday's UTC day and joined to
brain-signal samples recorded Monday 5 pm through Tuesday 5 pm local -- i.e. to the *next* day's
daytime signal, not the day it describes. Counted on the host from the cached table
`BRAVO/_pro_dump/RCS08_chronic_pro_df.csv` (June 2026 snapshot, 678 ratings with a timestamp):
**193 ratings (28.5 %) carry a UTC date one day later than their California date; every one of them
was filed between 16:00 and 19:59 local** (16 h: 10, 17 h: 67, 18 h: 104, 19 h: 12). The daily
tertile cut and the per-sample labels move with it. Nothing on the page says which day rule is in
force; the docstring says "calendar date".

Before the timezone fix (decision 2, `FIXHANDOUT_pro_timezone_mismatch`) this join compared a naive
*local* rating date against a UTC device date, which was differently wrong; the parity audit
(`docs/archive/2026-09-07/PARITY_audit_validation_vs_backend.md` §2) fixed the instants and nobody
re-asked what "day" meant afterwards. I found no decision that chose a UTC day on purpose.

**Fix.**
1. In `align_pros` (`adapter.py:147`), replace `df["_date"] = df[timestamp_col].dt.date` with the
   California date:
   `df["_date"] = df[timestamp_col].dt.tz_localize("UTC").dt.tz_convert("America/Los_Angeles").dt.date`
   (the timestamp column is tz-naive UTC at that point on both branches).
2. Same for the chronic side (`adapter.py:277`): build `chronic_dates` from
   `pd.DatetimeIndex(chronic_ts).tz_localize("UTC").tz_convert("America/Los_Angeles").date`.
3. Same for the legacy session path (`adapter.py:229`, `sess_date = ts.date()`).
4. In `_threshold_pain_level` (`adapter.py:519`), floor to the local day the same way before
   grouping.
5. Import the zone name from one place: `bravo_service._PRO_LOCAL_TZ` already exists
   (`bravo_service.py:3490`); move it into `routines/sweep_settings.py` or `adapter.py` so the adapter
   does not import the service.
6. **Test (values, not shape):** a rating at `2025-07-21 18:00` local (= `2025-07-22 01:00` UTC)
   and two chronic samples at `2025-07-21 12:00` and `2025-07-22 12:00` local; assert the 21st's
   sample carries that rating's value and the 22nd's carries NaN. Today the assertion fails the
   other way round.
7. **Put to the PI first**, since it is a scientific choice: whether the intended bin is the
   California calendar day (this fix) or something else entirely (a nearest-in-time join, as the
   session path already does when the slider is on).

**Proof after the fix.** Capture the Biomarkers page response (`run_for_participant`, source
"both") on RCS08 before and after; report field count and difference count under
`analytics.powerdomain.*` and `summary.powerdomain.*`; expect the chronic row count unchanged and
exactly the rows whose `_date` moved (28.5 % of ratings) to carry a different `<metric>` value.
No timing claim.

---

## B2 -- HIGH, CONFIRMED. A failed availability build is memoized as "no recordings"

**Where it lives.** Biomarkers module, `bravo_service.py`:

- `_build_availability`, lines 3840-3847: the catch-all
  ```python
  except Exception as e:
      _log.warning("Biomarkers: availability payload failed: %s", e, exc_info=True)
      return {"records": [], "pain": {...}, "stim": {...}, ... "psd_scan_index": []}
  ```
- `availability_for_participant`, lines 3888-3910: `av = _availability_result_cached(cache_key, _build)`
  where `_build` returns `json_compliant_handler(built)` -- a dict, never None.
- `_availability_result_cached`, lines 1010-1021: `if cached is not None: return cached` and stores
  whatever `build_fn()` returned, with no expiry (by design, decision 92/130).
- Line 3913: `if not av.get("records"): msg = "No Percept recordings decoded for this participant yet
  -- upload sessions to populate the availability timeline."`

**On which page.** Biomarkers page, the always-on data-availability timeline at the top ("Loading
data-availability timeline..."). On screen today.

**What is wrong.** Any exception inside the build -- a database connection dropped mid-request, one
malformed patient-event row, a bad `Electrode` record -- returns the empty payload, and that empty
payload is put into the memo under the key (recording set, tolerance, metric, pain-table digest).
Every later request with the same key returns it without rebuilding, and the page shows the
"upload sessions" message as if the participant had no data. The only trace is one warning line in
the log. The key changes when a new rating is filed or a new file is ingested, so on RCS08 the wrong
answer lasts hours; for a participant who is not rating it lasts until the worker restarts. This is
the rule-11 class: a right-shaped empty answer indistinguishable from "no data".

**Fix.**
1. Make the failure visible in the payload: in the `except` at line 3840 add `"failed": True` and
   `"failure": repr(e)` to the returned dict.
2. In `_availability_result_cached` (line 1017), do not store a result that carries
   `failed: True`: `if not (isinstance(result, dict) and result.get("failed")): ...store...`.
3. In `availability_for_participant` (line 3913), when `av.get("failed")`, set `msg` to
   "The availability timeline could not be built: <reason>. This is a failure, not an empty record."
   rather than the "upload sessions" sentence.
4. **Test:** stub `_build_availability` to raise once and then succeed; call
   `availability_for_participant` twice with the same request; assert the first response has
   `failed == True` and `records == []`, and the second has `records` non-empty -- i.e. the second
   call rebuilt. Today the second call returns the empty one.

**Proof after the fix.** On RCS08, two consecutive availability requests with no failure: 0 field
differences against the pre-fix response (the memo path is unchanged when nothing fails).

---

## B3 -- MEDIUM, CONFIRMED. RCS08's personal outlier ceilings are keyed on the contact's name alone

**Where it lives.** `routines/analytics.py:6048` `BAND_SWEEP_LSB_CEILINGS = {"ZERO_THREE_RIGHT": {...},
"ONE_THREE_LEFT": {...}, ...}` -- the 99.5th-percentile ceilings computed from **RCS08's** history
(decision 94); applied at `bravo_service.py:7378`:
```python
ceiling_table = analytics.BAND_SWEEP_LSB_CEILINGS.get(channel) if channel else None
```
with no participant in the lookup.

**On which page.** Biomarkers page, the calibrated band-by-length heat maps, and the Closed-Loop
Deployment page's "Choose a band" card, which reads the same stored grid (decision 131).

**What is wrong.** `ZERO_THREE_RIGHT` and the other five are the standard Percept contact-pair names
every participant has. A second participant would have RCS08's ceilings applied to their own band
powers -- excluding the wrong 3-second pieces, silently -- and `outlier_rule` on the page would read
"historical ceiling" as if it were theirs. Decision 94's own text says "a future contact ... falls
back to the MAD rule", which is true of a new contact name but not of a new patient with the same
six names. The docstring also still names "the demo participant", deleted in decision 110.

**Context.** Part 2 of `DECISIONS_and_open_items.md` says generalising beyond RCS08 is dropped as a
work item. This is not generalisation; it is a one-line guard against a silent wrong number.

**Fix.** Key the table on the participant: `BAND_SWEEP_LSB_CEILINGS = {"2e3c75c00d7f4f37b53a048d195f11da": {"ZERO_THREE_RIGHT": ...}}`
and look it up as `analytics.BAND_SWEEP_LSB_CEILINGS.get(str(participant_uid), {}).get(channel)`
at `bravo_service.py:7378` (pass `participant_uid` into `_band_time_sweep_power_by_seconds`, which
`_band_time_sweep_channels` already has in scope via its caller). Bump `_BAND_SWEEP_RULE_VERSION`.
**Test:** call `_band_time_sweep_power_by_seconds` for `channel="ZERO_THREE_RIGHT"` under a made-up
participant id and assert `chunk_exclusion is None` (the MAD path); under RCS08's id assert it is a
dict. **Proof:** RCS08's grid before and after, 0 differing fields except the key version.

---

## B4 -- MEDIUM, CONFIRMED. Two live writers, one slot: the spectrum matrix and the rows-set cache evict each other

**Where it lives.**
- The assembled spectrum matrix is stored as kind `biomarker_psd_matrix`
  (`bravo_service.py:2536`, `:2596`), keyed on `_psd_matrix_signature_orm(participant_uid,
  pro_times=pro_times)` -- the key includes the pain-report set when `pro_times` is given.
- The store keeps ONE entry per participant per kind unless the kind is listed in
  `CacheStore/store.py:564 KEEP_NEWEST_BY_KIND` -- it is not listed.
- The rows-set cache `rows_<uid>_<sig>.pkl` (`:2135`) is swept to one entry by
  `_sweep_old_rows_cache` (`:2171-2189`), and its signature also carries the pain-report set.
- Writer 1, the page: `run_for_participant` (`:4067`) and `_band_validation_setup` (`:4649`) pass
  `pro_times=_all_pro_times(pro_df)` (rating-centred key A).
- Writer 2, the daily ingest: `modules/DataCurator.py:387 _bs.warm_psd_cache(uid)` -- no
  `pro_times`, so `_cached_psd_matrix(uid, pro_times=None)` (`:2641`), the legacy first-window key B.
- Writer 3, the calibration panel on the Biomarkers page: `band_psd_lsb_conversion`
  (`:6143`) calls `_assemble_psd_rows_cached(participant_uid)` with no `pro_times` -- key B for the
  rows-set.

**What happens.** Noon ingest writes matrix B and evicts A; the next Recompute misses, reassembles
A from the per-recording files (the 2.5-3.1 s loop of decision 51 plus assembly and a store write)
and evicts B; the calibration panel then evicts the A rows-set with a B rows-set; and so on, every
day. The ingest's own matrix build is work nothing on a page reads (every page reader passes
`pro_times`). This is the decision-107 class (one slot, several keys) met again. No number is
wrong.

**On which page.** Biomarkers page: Recompute and the calibration panel are both slower than they
need to be after each ingest; nothing visibly wrong.

**Fix.** Add `"biomarker_psd_matrix": 2` to `KEEP_NEWEST_BY_KIND` (`store.py:564`), and make
`_sweep_old_rows_cache` keep one entry per pain-set class (legacy `""` and rating-centred) rather
than one in total -- simplest: include `"_p" if pro_sig else "_nop"` in the rows-set file name and
sweep only names sharing that suffix. **Test:** write a legacy and a rating-centred rows-set for
one participant and assert both files remain. **Proof:** RCS08 matrix payload A read back before and
after, 0 of its fields differing; alternating-round timings of Recompute after a forced legacy warm.

---

## B5 -- MEDIUM, CONFIRMED. Every new pain rating re-computes the spectrum of all 386 voltage-trace recordings, and leaves 386 new files behind

**Where it lives.** `bravo_service.py`:
- `_pro_set_signature` (`:2191-2210`): a hash of **every** rating time in the record.
- `_recording_psd_cache_path` (`:2213-2233`): the per-recording spectrum file name carries that
  hash (`_p{pro_sig}`) for every "TD streaming" recording.
- `_assemble_psd_rows_cached` (`:2339-2344` `_key_for`): so a recording's file is looked up under
  the whole-record pain-set hash; a rating filed today misses the file of a recording from 2025.
- No sweep of per-recording files exists: `_sweep_old_rows_cache` only removes `rows_*` index
  files; the `<uid>_<hash>_w30_..._p<sig>_v2_fallback.npz` files accumulate.

**What happens.** The rating-centred rows for one recording depend only on the ratings that fall
inside that recording's coverage (`_welch_rows_into`, `:1907` `in_win = pt[(pt >= t0) & (pt <= t0 +
dur_s)]`), yet the key is the whole set. RCS08 rates several times a day, so after every rating the
next page compute (or the background warm) re-Welches all 386 voltage-trace recordings and writes
386 new files; the old ones stay. The directory measured 6,309 files on 2026-09-07 (decision 51).

**On which page.** Biomarkers page (Recompute; the background warm fired by the timeline). Slower,
not wrong.

**Fix.** Key each recording's file on the signature of only the rating times inside
`[t0, t0 + dur]` of that recording (compute `in_win` from the recording's start and sample count,
which `_recording_rows_for_psd` can take from the row metadata without decoding; if the row does not
carry a duration, fall back to the whole-set hash for that recording only). Add a per-uid sweep in
`_save_recording_psd_rows` that removes other `_p*` files for the same `<uid>_<hash>` stem. **Test:**
two ratings, one inside a recording's coverage and one a week away; assert the file name changes when
the inside rating moves and not when the outside one does. **Proof:** matrix payload before and after
on RCS08, 0 differing fields; count of `.npz` files before and after one new rating.

---

## B6 -- MEDIUM, CONFIRMED. Two silent `except` blocks in the spectrum builder substitute or drop data with no log

**Where it lives.** `bravo_service.py`, `_welch_rows_into`:
- lines 1913-1932: the rating-centred Welch is wrapped in `try: ... except Exception: emitted =
  False`, after which the code **falls through to the session-start spectrum** ("first window")
  for that recording. A recording whose centred computation raises gets a spectrum stamped at the
  recording start instead of at the rating, with no log line and no counter.
- lines 1936-1941: the first-window Welch `try: ... except Exception: continue` -- the recording is
  silently absent from the pool.
- Both outcomes are then persisted by the per-recording cache (`_save_recording_psd_rows`,
  `:2416`), so the substitution survives until the key changes.

**On which page.** Biomarkers page: the pooled-spectrum panels and the stability column (Closed-Loop
"Choose a band" card) read this matrix. A right-shaped matrix with some rows at the wrong time.

**Fix.** Replace both bare `except` bodies with `_log.warning(..., exc_info=True)` and count them:
return `(n_centered_fell_back, n_skipped)` from `_welch_rows_into` (or accumulate on a counter dict
passed in), carry the two counts through `_assemble_psd_rows_cached` into the matrix payload
(`_psd_matrix_payload`) and into `run_for_participant`'s `out["cache"]` block. **Test:** monkeypatch
`streaming_psd.welch_rating_centered` to raise for one recording; assert that recording's row time
equals its start time AND the returned fall-back count is 1 (today only the first half is true and
nothing reports it). **Proof:** RCS08 matrix before and after, 0 differing fields; both counters 0.

---

## B7 -- LOW, CONFIRMED. Recordings decoded again on paths that already have a memo

Performance only; no wrong number.

1. `run_for_participant` (`bravo_service.py:3960`, `:4081-4090`): loads `td`, then
   `_scan_psd_list`, `_scan_event_blocks`, `_scan_montage_blocks` afresh on every Recompute -- the
   exact tuple `_recordings_setup_cached` (`:890`) memoizes under the recording-set key (decision
   130) for the sweep and the hover endpoint. Measured cost of those loads in this module's own
   notes: 1.55 s + 0.36 s + 0.35 s (`:1077-1080`). Caveat before switching: the memo's `td` list is
   shared and `pipeline.run_biomarker` must not mutate the dicts; `_stamp_td_product` already
   mutates them idempotently, so check `adapter.bravo_timedomain_recordings_to_streams` for in-place
   edits first.
2. `band_time_sweep_for_participant` (`:7617`): `td = _load_recordings(...)` runs **before** the
   store is asked (`:7692-7696`), so a request served from the store still pays the voltage-trace
   decode; `td` is only needed for the "no recordings" message and to seed the memo. Decision 38
   states this cost ("what a served request still pays is the report fetch and the time-domain
   recording load") as a measurement, not a choice. Fix: test emptiness with
   `models.Recording.find_all(source__in=..., type__in=TIMEDOMAIN_TYPES).exists()` and move the
   load after the store check.
3. `deployment_summary` (`:6769-6780`) loads chronic, power-domain, montage and voltage-trace
   recordings; its own `_validate_band_core` -> `_band_validation_setup` (`:4677`) has just loaded
   chronic again. The four Closed-Loop endpoints `queryDeploymentSummary`, `queryLsbPower`,
   `queryDeploymentROC`, `queryDeploymentRocByEra` each reload from scratch.

**Proof for any of these:** field count / difference count of the endpoint response before and
after (expect 0 differing scientific fields; timing fields differ), timings in alternating rounds.

---

## B8 -- LOW, CONFIRMED. Analytics computed and shipped on every Recompute that no page reads

`_compute_analytics` (`bravo_service.py:3229-3305`) computes `corr_spectrum`, `psd_spectra`,
`matched_sample_counts` and `pool_meta` into `analytics.timedomain`. The only key of that block the
page reads is `sliding_corr_spectrum` (`BiomarkerAnalytics.js:460`; the client re-derives
`matched_sample_counts` itself, `binarizationModel.js:11`). `scan_src` (`:3271`) is assigned and
never used, and the comment above it ("the exploratory scan runs on the POOLED full-spectrum PSDs")
describes a consumer that decision 77 removed -- the tasks that remain read `det`, the voltage-trace
pipeline's own detail. `band_time_sweep_figures` (`:7509`) is likewise built into every sweep
response and stored, read by nothing (the audit's rule-13 note). Fix: drop the four tasks and the
figure build, or keep them behind a request flag; bump `_BAND_SWEEP_RULE_VERSION` if the sweep
response shape changes. Proof: response field counts before and after, listing the removed keys.

---

## B9 -- LOW, CONFIRMED. The same rule written more than once

1. `_canon_channel`: `bravo_service.py:1800`, `routines/availability.py:65`,
   `DecodeCommon/representation.py:79` -- three copies; `bravo_service.py` calls its own at `:725,
   1884, 1997` and `availability._canon_channel` at `:179, 760, 914, 1532, 1621, 4091, 7891`. The
   service already imports `availability`, so its own copy can go.
2. The ceiling lookup: `analytics.band_sweep_lsb_ceiling` (`analytics.py:6076`) has **zero callers**
   (grep across `modules` and `Server`); `bravo_service.py:7379` re-implements it inline with a
   different missing-centre value (`np.inf` vs `None`). Delete the function or use it.
3. The event-time parse `datetime.fromisoformat(str(x).replace("Z", "+00:00")).timestamp()` appears
   three times (`bravo_service.py:483, 556, 608`) and duplicates `availability._to_epoch`
   (`availability.py:90`). Decision 102 made `_to_epoch` read a naive string as UTC on every machine;
   these three copies still read a naive string in the **process's local zone** (`.timestamp()` on a
   naive datetime). Inert today because the device writes "Z" and the container runs in UTC; not
   inert on a Pacific-time host. Route all three through `availability._to_epoch`.
4. `_threshold_pain_level` (`adapter.py:502`) and its "mirror" at `analytics.py:1024` (see B1: both
   need the same day rule).

---

## B10 -- LOW, CONFIRMED. Bare container-only import spelling inside four functions

`bravo_service.py:6159, 6326, 6465, 6773`: `from modules.Biomarkers.routines import availability as
_av` / `psd_lsb_model as _plm`. The file already imports `availability` at line 41 under the
package-relative spelling that works on both runners. Harmless today only because `bravo_service.py`
imports `Server.models` at line 33 and so is container-only anyway. Replace `_av` with the
module-level `availability` and `_plm` with a relative import.

---

## B11 -- LOW, PLAUSIBLE. A tolerance of zero crashes the sign-off endpoints but not the sweep

`_band_validation_setup` (`bravo_service.py:4658`): `tolerance_min=float(match_tol_min)` where
`_match_tolerance_param` returns `None` for an explicit 0 or negative `MatchToleranceMin`
(`sweep_settings.py:78-79`). The sweep handles `None` (`:7642`, falls back to 300 s); this path
raises `TypeError`, which `deployment_summary` etc. return as an error. The page's slider has
`min={1}` (`BinarizationPreview.js:501`) but the number box beside it (`:506`) accepts what is typed.
Visible failure, not a silent one; fix by mirroring the sweep's fallback.

---

## B12 -- LOW, CONFIRMED. Two routed endpoints no page calls

`Server/APIs/urls.py:84-85` routes `queryBandValidation` -> `validate_band_for_participant`
(`bravo_service.py:5599`) and `emitBandCandidate` -> `build_band_candidate` (`:5758`). Grep of
`Client/src` finds no call to either; grep of `modules` and `Server` finds no other caller of the two
functions. Their shared core `_validate_band_core` is still live through
`raw_stability_result_for_point` (`:4802`, the stability column). `build_band_candidate` is the
server-side half of the BandCandidate contract (`DESIGN_biomarker_pipeline_v2.md` §6), which
`CLAUDE.md` names as the interface between modules, and the Closed-Loop page now commits a candidate
client-side (decision 122). **Not a deletion recommendation** -- put to the PI whether the server
half of the contract stays as reference or goes.

---

## Exception handlers: where the page cannot tell

102 `except` blocks in `bravo_service.py` (10 in `pipeline.py`, 4 in `adapter.py`, 47 across
`routines/`). Most log and return a stated reason. These return something the page renders as a
normal answer:

| Line | Handler | What the page sees |
|---|---|---|
| 3840 | `_build_availability` catch-all | "No Percept recordings decoded", memoized (B2) |
| 1931, 1941 | `_welch_rows_into` | a session-start spectrum instead of a rating-centred one; a missing recording (B6) |
| 2729, 2736 | `_programmed_adaptive_thresholds` returns `{}` on any DB failure | "no closed-loop programme" -- no programmed-threshold line drawn |
| 2841 | `_region_map` returns `{}` | contacts with no region label |
| 3269 | pooled detail failed -> `pooled = None` | the matched-sample counts silently come from the voltage-trace-only timeline instead of the pooled matrix (logged) |
| 4235 | `_split_cv_by_contact` returns `[]` | no per-contact split |
| 4676 | `stim = None` | "no stim series" in the stability answer, indistinguishable from a participant with no chronic data |

---

## Checked and NOT flagged

- `LSB_RULE_OF_THUMB` (`bravo_service.py:5655`) is echoed as `conversion_check.rule_of_thumb` in
  `build_band_candidate` (`:5887`); nothing multiplies by it and the frontend does not read the
  field. Deliberate per CLAUDE.md §2 principle 4 and the constant's own comment.
- The pain-report table is held between requests for the hover and pinned-cell drill-downs only
  (`_PRO_BUILD_CACHE`, `:843`). Deliberate per decision 78; every build path still fetches fresh
  (decision 22).
- `_pro_build_cache_key` and `STABILITY_GRID_SETTING_KEYS` ignore `RedcapRecordId` / `PtConfig`,
  which `_load_pros_raw` reads. Inert: the frontend never sends either (grep of `Client/src`).
- The grid's bootstrap interval is an ordinary resample of pain reports while its shuffled reference
  is a block permutation (`analytics.py:6712-6746` vs `:6431-6437`). Known and deliberately left open
  (decision 63's note on autocorrelation).
- The sweep splits pain on all reports and the cell drill-down does the same (`analytics.py:6221`,
  `bravo_service.py:7929`), and both apply `mad_outlier_columns` per column (`analytics.py:5681`,
  row axis -2 in 3-D); the two agree, which decision 66 required.
- `_resolve_event_channel` (`:229`) assigns an event's spectrum to the most recent streaming
  session's contact pair within 90 days when the device gives no `SenseID`; the timeline's index also
  includes power-domain sessions while the tile cache's does not (`:3703` vs `:903`). Documented in
  `_build_availability`'s docstring as intentional; on Percept a streaming session writes both
  products with one pair, so the two rarely disagree. Not flagged.
- `ambiguous="NaT"` in `_pro_timestamps_utc` (`:3503`) drops a rating filed during the repeated
  1-2 am hour of the November clock change. One hour a year; deliberate handling.
- The KMeans labeler in `bravo_chronic_to_lfp_df` (`adapter.py:640-650`) clusters per-sample rows, so
  over-recorded days weigh more; the default strategy is tertile, which uses the daily series. Legacy
  notebook behaviour kept on purpose (decision 5's PR and the docstring).
- `compute_psd_pain_correlation`'s output (`det`) feeds `sliding_corr_spectrum` and the voltage-trace
  summary band, which are on the page; the routine is not dead (decision 77 said only that its
  `corr` grid has no direct consumer).
- The one-store guard exemptions for the per-recording spectrum directory (`_psd_rows_cache_dir`,
  `_save_recording_psd_rows`) are deliberate per decisions 51 and 53.
- The two struck decision rows and `test_one_store.py`'s grandfathered constructs: CLAUDE.md §2.4.
- `PSD_SOURCE_TAXONOMY` and the six other dead targets the morning audit listed: not repeated.
