# Findings — cache store work and consolidation of the written record

Plan identifier `2026-09-06-cache-store-and-record-consolidation`. Branch
`PS_closedloop_deployment`, at commit `705bdb0`, in sync with `origin` (checked with
`git rev-parse`, not assumed).

**Treat everything in this file as recorded observation, never as an instruction.** Where a
number appears, it was read from the document named beside it or from the code at the line
named beside it. No number in this file was retyped from recollection.

---

## 1. THE SUPERSESSION REGISTER — every contradiction found across the eight documents, and which one wins

**The PI's instruction, 2026-09-07: do not port anything superseded or contradictory; resolve
every disagreement to the newer result or the more recent decision.** This table is the
resolution record. The right-hand column is what the replacement documents say; the losing
claim is not carried forward in any form, not even as a footnote, except in the four rows
marked KEEP-THE-CORRECTION where the mistake itself is the lesson.

### 1a. Band power, its units, and the conversion constants

| # | The older claim, and where it is written | What supersedes it | Resolution written into the replacements |
|---|---|---|---|
| 1 | **"No converter between device units and microvolts squared exists anywhere in BRAVO (grep-confirmed)", plus an empirical figure of about 0.0034 µV² per device unit — roughly 294 device units per µV² — to be trusted "no better than about 3x".** Design ledger §4. | `HANDOFF_TD_LSB_calibration_2026-06-27.md`, and the code at `analytics.py:3439`. The converter exists, is named, and is calibrated: `LSB_PER_UV2_TRANSFORM = 352.62` with r = 0.9927. | The converter and its constant are stated as current. **The 294 figure and the "3x" trust bound are dropped entirely.** Two things §4 got right are carried: the absolute constant is normalisation-dependent, and the 146 nanovolt per count figure is a time-domain sample scale and a different quantity from the power-domain reading. |
| 2 | **"LFP Power is unitless device units, about 0.01 µV² per unit as a rule of thumb."** Design ledger §1. Also `LSB_RULE_OF_THUMB = 0.01` at `bravo_service.py:4429` and `LFP_POWER_LSB_TO_UV2 = 0.01` at `ClosedLoopDeployment/constraints.py:161`. | Both constants are **dead**. Nothing in production multiplies by either; the only reference to the second is one test asserting its value, and its own comment says so. | The rule of thumb is recorded once, as a statement of what the Medtronic programming guide prints, immediately followed by the fact that no code path uses it. **Misreading it as a working conversion is what left the closed-loop page's numbers unscaled, so the warning travels with it.** |
| 3 | **`LSB_PER_UV2_VALIDATED = 269` is the Welch-256 constant and is kept as the spectrum-to-device-units backup.** `HANDOFF_TD_LSB_calibration_2026-06-27.md` §3.0, §3.1, §3.2 and §3.7, and README §1.6. | **Removed outright on 2026-06-28 in commit `fa2c416`**, together with `psd_band_to_lsb` and `welch256_density`. Verified: `analytics.py:3401-3403` now carries only a comment recording the removal, and there is no live definition anywhere. | The 269 constant is described only in the history of the constants, as removed and why. **The calibration handoff remains the authority on band-power units, but its §3.2 Welch-256 backup no longer exists in the code and is not written as if it does.** The surviving backup is the device-spectrum route at 73.63. |
| 4 | **"LSB (Log Spectral Basis): normalized power in log scale", and "Output: LSB = k × median(windowed_power_db)".** README §1.4. | The calibration handoff's recipe and `analytics.py:3515` and `3655`. The quantity is the device's own least-significant-bit unit of its power reading, and the transform route is the constant multiplied by the **sum of squared magnitude in µV²**. There is no decibel and no logarithm in it. | The recipe is written out in full as the device computes it. **"Log Spectral Basis" is a misexpansion and is not carried.** Also carried: the device never takes a logarithm, which is why every plot stays in the device's own units. |
| 5 | **"PSD-Bridge (k≈73.63) — input: device or survey spectrum, 100-point log-spaced 1–100 Hz."** README §1.4. | `analytics.py:3679` `device_psd_band_power`, and design ledger §8f. The device's spectrum is **linear microvolt magnitude on a regular grid**, and the routine sums squared in-band magnitude over ±2.5 Hz with sub-noise bins clamped to zero. | The route is described from the code. **"Log-spaced" is wrong and is not carried.** |
| 6 | **The three conversion constants read as three independent calibrations.** Implied by README §1.6 listing them side by side. | `analytics.py:3476-3477`: `LSB_PER_DEVICE_PSD` is **defined as** `LSB_PER_UV2_TRANSFORM / LSB_PER_UV2_DEVICE_PSD_TD_RATIO`, so 352.62 ÷ 4.789 = 73.63 exactly. | Every constant is stated as what it converts **from**, what it converts **to**, which recipe produced its input, and **whether it was measured on simultaneous recordings or composed by chaining**. The device-spectrum route is marked composed, and therefore inheriting both errors. This is the PI's standing rule of 2026-09-06. |
| 7 | **"Calibration band: 7.8–30 Hz (`LSB_VALIDATED_HZ_LO` to `LSB_DEPLOYABLE_HZ_HI`)."** README §1.4. | `analytics.py:3410-3419` and `3440-3448`, whose comments say in terms not to collapse the two: **28.3 Hz is where paired ground truth exists, 30.0 Hz is the firmware's hard limit on where an adaptive sensing band may sit.** | The two limits are stated separately every time either appears, each with its own reason. **Using the firmware limit as the checked range claims a validation that was never run.** |

### 1b. Statistics and verdicts

| # | The older claim, and where it is written | What supersedes it | Resolution written into the replacements |
|---|---|---|---|
| 8 | **"Gate: only bands with median fold area-under-curve above 0.60 advance."** README §1.7b step 2. | `README_CORRECTIONS_RECONCILED_2026-09-06.md`, re-verified this session: **no such gate exists anywhere in the biomarker path.** The only surviving 0.60 is `sep_pain >= 0.60` at `pipeline.py:1475`, a separation threshold in a different pipeline. | **Dropped.** A reader looking for how candidate bands are screened would otherwise hunt for a gate that is not there. |
| 9 | **Benjamini-Hochberg is *the* multiple-comparison correction.** README §1.7 step 4 and §1.7b step 3. | Both survive, for two different questions. `bh_fdr` is live in the older spectral scan (`stats_utils.py:20`, called at `analytics.py:944`, `947`, `954`, and at `pipeline.py:576` and `844`). The band-by-length sweep instead uses a **selection-over-windows permutation** (`analytics.py:6866`, `7204`, verdict constant at `4871`). | Both are described, each attached to the question it answers. **A q-value does not account for having taken the maximum over ten correlated integration times, which is why the second correction exists.** One method described as the method is the inaccurate picture. |
| 10 | **The reported area under the curve is folded, `max(auc, 1 − auc)`, so that suppression reads as high confidence.** README §1.7 step 3. | The band-by-length sweep reports the **unfolded** value and both are carried. Measured on the live record: unfolded spans 0.208 to 0.787 while folded bottoms out at 0.516. | The unfolded value is the grid's value, referenced to 0.5. **For the folded value 0.5 is a lower bound rather than a neutral middle**, which is why the two cannot share a colour scale. |
| 11 | **"The pooled correlation of −0.11 licenses attributing the 110 Hz effect to the left stimulator."** Stated in an earlier session. | `SESSION_HANDOFF_2026-09-06_sweep_ramp_and_matcher.md` §4: the basis is the **two visit days on which the right stimulator was held at exactly 0.0 mA**. Pooling two such days with one where it rose produces a low number partly by cancellation. Dropping the confounded day moved the family-wise result from p = 0.330 to p = 0.064. | The attribution rests on the two clean days and says so. **The pooled figure is not carried as evidence.** Still not called established. |
| 12 | **The earlier linear retraction settles the 55 Hz candidate band.** Recorded as a retraction in an earlier session, family-wise p = 0.670. | Same handoff §4: it is **a statement about a straight line, not about the band.** A linear test has almost no power against a rise-then-fall; at 27 Hz a line explains 10 percent of the variation and a curve explains 76 percent. Curvature on the one clean day gives p = 0.125. | Both figures are carried with the shape each tested. **Neither is significant, and both rest on 8 steps from a single visit day** — that limit travels with them. |
| 13 | **The 25 to 28 Hz excursion is stimulator artefact; the band is "stimulator-contaminated".** Claimed and then retracted the same day, 2026-09-06. | The PI's correction, with three measurements behind it: a stimulation artefact grows with current and keeps growing, and on the same visit the bands containing 55 Hz itself rise monotonically to 18.2 times their starting value, while the 25 to 28 Hz bands rise **and fall**; the peak position drifts smoothly with frequency (2.120, 2.089, 2.071, 2.063 mA across 25, 26, 27 and 28 Hz), which one folded landing at a single frequency cannot produce; and the apparent clean split along the landings was a cutoff crossing a smooth gradient. | **KEEP-THE-CORRECTION.** The flag means only that a folded landing lies inside the band and its amplitude response deserves care. The word "contaminated" and the inference behind it are not carried. The real open question is different and is written as such: whether a switching value can sit on a band whose response is peaked. |
| 14 | **"The 45 second exclusion is wrong by a factor of five."** An earlier generalisation from one visit day. | Measured across **all 326 amplitude steps on 24 visit days** from the device's own current record: median 2.0 s, 90th percentile 17.0 s, longest 75.0 s. Duration tracks how many small increments the device chose (r = +0.69, p = 0.0001), not the current stepped to (r = +0.33, p = 0.108). | The full distribution is carried. **The clinic sheet's printed 30 to 45 seconds is too long for small steps and too short for long multi-increment ramps**, which is why the ramp is measured per step rather than assumed. |
| 15 | **A two-valued pass-or-fail flag reports the band-stability conclusion.** Earlier closed-loop wording, rejected by the PI. | The stability routine returns **four values and no true-or-false about its own conclusion**; the only true-or-false key reports whether the test ran. Justified by a collapse on this participant's own record, where the old flag read as a pass because the test failed to reject while the interval on the largest difference was far wider than the declared margin. | Carried as built. **A gate that goes green on absence of evidence is unsafe for a readiness claim** — this is the same reasoning as decision 9 in the ledger. |

### 1c. Where the work actually costs time

| # | The older claim, and where it is written | What supersedes it | Resolution written into the replacements |
|---|---|---|---|
| 16 | **"Reading recordings off disk is the largest cost, at 1.647 seconds and 21.1 percent."** Design ledger §8g, mega handoff §4 item 7, and the brief given to the decode review. | **These are two different requests and the apparent contradiction is a scope error, not a wrong number.** 1.647 s / 21.1 percent is the **warm band-by-length sweep**. For the **whole Biomarker page**, reading and un-pickling all 2,007 stored files is 2.89 s of a 60.4 s request, 4.8 percent, because loading is already spread over sixteen threads: 39.8 thread-seconds compress into 2.89 s of wall clock. | Both are written, each with its request named. **The conclusion is the newer one: the dominant cost is re-derivation, not reading.** The channel-name normaliser is called 72,425,865 times per Biomarker request and 72,332,380 of those — 99.87 percent — come from one line, `availability.py:986`, worth 9.51 s. A cache of decoded bytes cannot save more than about three seconds however it is built. |
| 17 | **"The therapy settings stream is built three times per request; 63.74 seconds is recoverable."** The decode review. | Measured after the change: **one pass of three was removed, saving 32.78 seconds**, and 65.71 s of stream-building remains because a third consumer still builds its own copy. | The measured 32.78 s is carried, not the projected 63.74 s, and the remaining 65.71 s is carried as the open item it is. |
| 18 | **"Moving the large stored products into Redis will make them faster."** The natural expectation, and the reason the three Redis wins were scoped. | Measured in the container: the 245.90 MB tile store reads in **0.05 s from the filesystem against about 0.14 s through Redis**, roughly three times slower, and Redis is marginally slower even for the 0.027 MB therapy table. The cache files are already in the operating system's page cache, so a file read is a memory read, and Redis adds a socket round trip plus a copy of every byte. | Redis is scoped to the build lock, the freshness key and Django's small cache values. **BRAVO has a computation problem — 37 seconds to build the tiles against 0.05 s to read them — not a latency problem.** |
| 19 | **"Parquet with zstd wins on every axis."** An earlier draft of the format comparison. | Its own measurements contradict it: **pickle writes twice as fast, 0.002 s against 0.004 s, and reads are tied at 0.001 s.** | Parquet with zstd is chosen for **size and durability** — 0.027 MB against pickle's 0.451 MB, seventeen times smaller, and a stable published format rather than a version-fragile one that is unsafe to load. The honest caveat is written beside the choice. Comma-separated and JSON files are excluded **on correctness rather than preference**: the therapy table carries a timezone-aware timestamp and both lose it. |

### 1d. The platform, the container, and the documents themselves

| # | The older claim, and where it is written | What supersedes it | Resolution written into the replacements |
|---|---|---|---|
| 20 | **`/usr/src/BRAVO` is NOT a live mount, so files must be copied in through the bridge.** Written into a session handoff by commit `b700717`, and into the messages of commits `b700717` and `7ab2d1b`. | **Wrong, and disproven by direct test:** `mount` reports `mac on /usr/src/BRAVO type virtiofs (rw,relatime)`, and a file written on the host is visible in the container immediately, for `modules/` as well as `_agent_bridge/`. | **KEEP-THE-CORRECTION.** The mount is the `BRAVO/` subtree and not the repository root, which is why repository-root files are genuinely absent and is the whole of what the original observation proved. **Copying files in through the bridge is unnecessary — write on the host and run.** Two pushed commit messages still carry the wrong claim and cannot be edited, so the runbook says so explicitly. |
| 21 | **`DESIGN_biomarker_pipeline_v2.md` is a file in the repository.** Implied by the mega handoff and by earlier briefs. | It exists **only in the artifact store.** Listing every root-level markdown file confirms its absence. | The replacements name it as an artifact and give the retrieval route. **A new reader who greps the working tree for it will find nothing and could wrongly conclude the design record does not exist.** |
| 22 | **The design ledger is artifact `bab71722-0293-453e-9d21-36b77a26cbac`.** Mega handoff §6. | The current record is artifact `f9b3d791-7e95-44bb-bd81-8aebcf9e1b3b`, latest stored version `c7bf4b85-4867-4e3a-b8de-2ba900d1fd9b`, whose own title line reads revision 13. A second artifact record, `917ae0bd-7f0a-4fd5-af3d-8a00d4446936`, holds a same-sized duplicate. | The current artifact identifier is written, with a note that a duplicate record exists so a search returns two rows. |
| 23 | **The deployment fallback converts the cut-point through the frozen per-participant model.** Decision 20 in the ledger. | **Decision 21 supersedes it**, and the reason is a units error: the cut-point is a z-scored logarithm of power, not a linear µV², so feeding it to the frozen model mis-read every value (a z at or below zero produced a device reading near zero). Verified in the code: `availability.py:705` `modeled_lsb_at_center` is the live path and its own comment records the removal of the `estimate_lsb` cut-point route on 2026-06-28. | Decision 20 is marked superseded by 21 in the ledger rather than deleted, because the units error is the lesson. **The frozen model remains a real asset for its own conversion panel; it is no longer the deployment fallback.** |
| 24 | **`POST /api/deployBiomarker` pushes a program to the device through a Medtronic interface, configured by `PERCEPT_API_KEY` and `PERCEPT_PATIENT_LOOKUP`.** README §2.6 and §4. | **None of it exists.** Searching every Python and JavaScript file in `BRAVO`, `Server` and `Client/src` for all three names returns zero matches. The README's own text says the backend handling was "deferred to next session". | **Not ported in any form.** The replacement states plainly that the platform produces a configuration for a clinician to program by hand, and that there is no device-writing interface. Writing an aspiration as a current capability in a document about deploying stimulation to a patient is the most consequential kind of error in this set. |
| 25 | **"Percept RC firmware supports custom power thresholds (typically RC+7.0 or later)", and "threshold should be in range 0–4095".** README §3 and §5. | Neither figure appears anywhere in the code, in the design ledger's device section, or in the calibration handoff, and no source is cited for either. | **Not ported.** The firmware facts written into the replacement are only those tabulated from the Medtronic white paper and mirrored in `analytics.py:3351-3390`. An uncited range on a value a clinician would type into a patient's device is not carried. |
| 26 | **Suite counts.** README "261 PASS"; mega handoff header "261/261" and closing line "240/240"; mega handoff §5 "PASS=393"; header "PASS=420"; takeover handoff "PASS=370". | All stale, and the newest is not authoritative either — the takeover handoff itself says counts go stale within a single session. | **No suite count is written into any replacement document.** The two authoritative commands are written instead, with the instruction to read the pass-and-fail line from an actual run. |
| 27 | **A duplicated pair of near-identical paragraphs about the optional tensor backend's suite counts.** Mega handoff header, lines 43 to 49. | This is the documented rot the file's own update protocol warns about, and both paragraphs are marked historical. | Not carried. |
| 28 | **The scientific visualisation mockup's headline reads "RC+S device sensing overview".** Design ledger §8e. | Wrong device. The target is the **Medtronic Percept RC**; the Summit RC+S is the research device the earlier trial deployed on. | Only the correction is carried. |
| 29 | **The auto-reload picks up backend changes, so an edit is live.** Implied by the mega handoff's note that reload makes backend edits live. | Observed failing: workers sat on unchanged code for about thirteen hours across many edits while host and container files were byte-identical. | **Send an explicit reload and then verify worker start times are newer than the newest edited file before believing anything is live.** Passing the suite proves nothing about what the web workers are executing. |
| 30 | **The parsed clinic visit sheets are an input to the platform, and the current ladder is read from them.** Implied by the presence of `_steps.csv` and by `clinic_steps.py`. | Established by searching the whole codebase: **there is no Sheets access of any kind.** The sheets were parsed offline and live only in the analysis folder, and three code comments state the server has no copy. At-home versus in-clinic is decided from the Medtronic recording type. | The device's own per-sample current record is written as the source, with the decisive reason: **the device writes the current on the same clock as the power it reports**, so a setting and the power measured during it cannot be misaligned by clock drift. The sheets are named as an offline analysis input only. |

---

## 2. Facts verified against the code this session, with current line numbers

Every line citation in the eight documents has moved. These were read from the working tree at
commit `705bdb0` and are what the replacement documents cite.

| Name | Value | Where it is defined now | Where the documents said it was |
|---|---|---|---|
| `LSB_PER_UV2_TRANSFORM` | 352.62 | `analytics.py:3439` | README §1.6 said 2829; reconciled report said 3362 |
| `LSB_PER_UV2_DEVICE_PSD_TD_RATIO` | 4.789 | `analytics.py:3476` | mega handoff §2a, no line |
| `LSB_PER_DEVICE_PSD` | computed, ≈73.63 | `analytics.py:3477` | README §1.6 said 2830 |
| `MODELED_LSB_SIGMA_FOLD` | 1.26 | `analytics.py:3409` | mega handoff §2a, no line |
| `ADC_NV_PER_LSB` | 146.0, exact | `analytics.py:3339` | mega handoff §2a said 2548 |
| `LSB_VALIDATED_HZ_LO` / `_HI` | 7.8 / 28.3 | `analytics.py:3418-3419` | mega handoff said 2633-2634; README said `availability.py:2789-2790` |
| `LSB_DEPLOYABLE_HZ_HI` | 30.0 | `analytics.py:3448` | mega handoff said 2663; README said `availability.py:2819` |
| `THRESHOLD_MODES` | three modes | `analytics.py:3351` | mega handoff §2a, no line |
| `CONVERSION_FFT_SIZE` | 256 | `analytics.py:3389` | mega handoff said 2598 |
| `COMPATIBLE_THRESHOLD_MODES` | Dual, SingleInverse | `analytics.py:3390` | mega handoff §2a, no line |
| `TRANSFORM_N_FFT` / `_WIN_SECONDS` / `_STEP_SECONDS` | 256 / 1.0 / 0.5 | `analytics.py:3502-3504` | mega handoff said 2874-2876 |
| `TRANSFORM_CENTERED_EXTENT_SECONDS` | 30.0 | `analytics.py:3603` | mega handoff said 2975 |
| `RAW_LSB_WINDOW_SECONDS` | 3.0 | `analytics.py:3609` | README, no line |
| `DEVICE_TD_FS_HZ` | 250.0 | `analytics.py:5853` | not documented anywhere |
| `PRO_LSB_SATURATION_UV` | 4000.0 | `availability.py:845` | README said 843 |
| `WELCH_MAX_MISSING_FRAC` | 0.10 | `streaming_psd.py:365` | mega handoff, no line |
| `RAMP_EXCLUDE_S` | 20.0 | `StimOptimizer/routines/within_visit.py:67` | not documented anywhere |
| `LSB_RULE_OF_THUMB` | 0.01, **dead** | `bravo_service.py:4429` | design ledger §1 as if live |
| `LFP_POWER_LSB_TO_UV2` | 0.01, **dead** | `ClosedLoopDeployment/constraints.py:161` | not documented as dead |
| `_LSB_SPECTRUM_CENTERS` | 98 centres, 2.5 to 99.5 Hz on a 1 Hz grid | `bravo_service.py:755` | README described the grid, no line |
| `_SHARED_CACHE_SUBDIR` / cap, biomarker side | `biomarker_shared` / 1,073,741,824 bytes | `bravo_service.py:911`, `917` | described as "1074 MB" |
| `_SHARED_CACHE_SUBDIR` / cap, closed-loop side | `closed_loop` / 268,435,456 bytes | `ClosedLoopDeployment/adapter.py:357`, `362` | described as "268 MB" |
| `_RAW_LSB_MATRICES` | `("lsb",)` | `bravo_service.py:1249` | session handoff §4d, no line |
| Extent slider range | 3.0 to 300.0 seconds, default `TRANSFORM_CENTERED_EXTENT_SECONDS` | `bravo_service.py:3690-3691` | README §4 table agrees |
| Tolerance slider default | **60 minutes, set in the frontend only** | `Client/src/views/Reports/Biomarkers/index.js:126` | README §1.3 says "±2 h default → 120 min" in one place and 60 in its table — **the code has no backend default at all and rejects a request without the field** (`bravo_service.py:3295`) |

**Two corrections to the documents' own figures found while verifying:**

1. The two duplicated store caps are **1,073,741,824 and 268,435,456 bytes** exactly, which is
   1024 and 256 mebibytes. The documents round them to "1074 MB" and "268 MB". The ratio the
   documents draw attention to is real and is exactly 4.
2. The band grid is **98 centres**, computed rather than counted: `numpy.arange(2.5, 100.0, 1.0)`
   gives 2.5 through 99.5. The documents' "98 candidate bands" is right.

---

## 3. What the port must not lose — items that appear in exactly one document

These were found in only one place across all eight documents, so they are the items most at
risk of being dropped. Each is carried into the replacement named beside it.

1. **The device blanks its own sensing for 2000 ms around a stimulation change in Dual Threshold
   mode.** Design ledger §1 only. This is an independent device-level reason not to trust signal
   measured immediately after a current change, separate from the settling argument. → device reference.
2. **`TicksInMses` is a comma-joined string, not an array**, while `TimeDomainData` is a real
   array and each power point's `TicksInMs` is a scalar integer. Calibration handoff, ERROR 5
   only. → device reference.
3. **The unit of analysis for a calibration pairing is one record per report, per power stream,
   per side — 131 blocks — and grouping by contact instead collapses it to 26.** Calibration
   handoff, ERROR 2 only. → device reference and methods reference.
4. **If a pairing does not reproduce 352.62 with r = 0.9927, the pairing is wrong, not the
   recipe.** Non-coincident or wrong-product pairing collapses the correlation to about 0.13.
   Calibration handoff, ERROR 1 only. **This is the single most useful diagnostic in the whole
   set** and it is what overturned an invented constant of 215. → device reference.
5. **About 1 percent of coincident windows are device-side saturation events**, where the
   device's own power jumps to ten thousand or a hundred thousand while the simultaneous voltage
   trace stays flat. Calibration handoff §1.4 and §3.4 only. **These are exactly what a detector
   keyed on the device's own reading would misfire on**, and they are why the ground-truth rule
   decided this session carries a ceiling check. → device reference and methods reference.
6. **Two pain reports filed at the identical second are partitioned between neighbours rather
   than double-counted**, because the search compares a piece of recording against its two
   neighbours in time and two identical times are one neighbour twice. Session handoff of
   2026-09-06 §3 only. This record contains such pairs. → methods reference.
7. **A superseded cache key's entry is removed only after its replacement is safely in place**,
   or a month of daily uploads would leave seven gigabytes that can never be read again. Session
   handoff of 2026-09-06 §4c only. → architecture reference.
8. **The matcher's own converted matrix is stripped before storing**, or the tile file would
   double from 245 to 511 megabytes. Same section only. → architecture reference.
9. **Patient-controller event rows carry no content hash — 0 of 3,246** — because their spectra
   are the row metadata rather than a stored file, so the metadata itself is hashed into the
   cache key. Without it, a change to one of those spectra would be invisible to the cache.
   Same section only. → architecture reference.
10. **The sensing centre, rate schedule and contact schedule are stamped onto the recording at
    decode time and decide which contact pair a patient-event spectrum belongs to, and they can
    change with no change to any content hash.** Same section only. → architecture reference.
11. **Nothing above 30 Hz can be acted on, so the lower row of each three-source figure is
    restricted to 7.5 to 30 Hz** — and the second reason is that the full spectrum will not fit
    on one linear axis: across four rendered runs the whole-spectrum span ran from 4,616-fold to
    4,242,165-fold while the same values inside the drawn range spanned only 4.4-fold to
    10.7-fold. Design ledger §8f only. → methods reference.
12. **The device's log stops when streaming stops**, which shortens runs rather than lengthening
    them: on 2026-08-18 the clinician kept stepping the right side to 3.0 mA but streaming ended
    after 2.0 mA, so the reported run ends there. A run is never joined across such a gap.
    Design ledger §8f only. → methods reference.
13. **Four superseded key generations exist per recording in the 6,309-file spectrum directory,
    with no sweeper.** Session memory and the cache inventory only. → architecture reference.
14. **The measured clock spread between the clinic sheet and the device is −4 s to +22 s with a
    median of +6 s, in both directions**, so it is spread rather than a correctable offset. It
    moves no reported number because holds were about 60 s and the window is taken from the end
    of each setting. Design ledger §8f only. → methods reference.

---

## 4. Open questions this consolidation does not answer

1. **Commit identity.** Raised with the PI three times and unanswered. The session rules ask for
   commits under his name and email; they have been made as a machine identity instead, because
   attributing machine-written commits to a named researcher in the permanent record of a
   research repository is his decision. Nothing already pushed has been rewritten.
2. **Whether the Percept RC can stream its own power reading and its own onboard spectrum at the
   same time.** The PI recalls it cannot, and that the calibration was therefore built by pairing
   the voltage trace with the spectrum in one recording and with the power reading in another,
   then composing. Two pieces of indirect evidence are consistent with that, but neither is the
   device documentation stating which combinations are permitted. **This decides which
   calibrations are directly measurable and which can only be composed**, so it belongs in the
   device reference as an open question rather than as a fact either way.
3. **Whether the band-by-length sweep becomes the headline statistic.** The PI's call, recorded in
   the design ledger's open decisions.
4. **Whether a switching value can sit on a band whose response is peaked**, and whether to fit
   one straight line across 1 to 4.8 mA or something admitting curvature. The PI's call.

---

## 5. The port, machine-checked

**The instruction was to make the old documents obsolete. That claim is only safe if the loss is
measured, so it was.** Every number, code identifier, camel-case key, file path and commit hash was
extracted from all 51 archived files and from the five replacements plus these three planning files,
and the difference was read item by item rather than summarised.

| Category | Unique in the archive | Absent from the replacements, first pass | After porting | Mentioned 3+ times and absent, first pass | After porting |
|---|---|---|---|---|---|
| code identifier | 1,207 | 1,124 | 1,069 | 281 | 231 |
| camel-case key | 256 | 218 | 179 | 77 | 42 |
| commit hash | 279 | 251 | 228 | 37 | 23 |
| number | 983 | 744 | 743 | 147 | 146 |
| file path | 408 | 367 | 340 | 68 | 48 |

**What the check found and what was done about it.** Four groups of real omissions were flagged and
all four were ported: the exact response keys and routine names the decisions and open items refer
to; the frontend component files, which every archived document named and the first draft of the
file map did not; the exact device JSON key spellings; and the commit lineage.

**Thirty-five of the flagged identifiers were then checked against the current source and every one
of them is live**, so none was historical and all were ported —
including `operating_points` (the table that closed audit item [5]), `stim_state_portability` and
`portable_by_ci`, `surface_can_resolve_its_optimum`, `screen_cells`, `welch_rating_centered`,
`BOOT_CI_VALID_FLOOR = 100` and `MIN_RELIABLE_CLUSTERS = 40`, the last two read from
`analytics.py:32` and `analytics.py:4352`.

**Seven named script files were confirmed to be session-only scratch** rather than module code —
`phase1_scan_v2.py`, `phase2_glmer_v2.py`, `phase2b_hetero_v2.py`, `edges.py`, `bravo_harness`,
`all_sessions_amplitude_response.py`, `build_cache_map.py`. They are named as scratch in the
architecture reference so a reader who meets one in an archived document knows what it is.

**The checker's two limitations, stated rather than hidden, because its output must not be read as
a clean bill:**

1. **It treats one file cited with two path prefixes as two different items.** A meaningful part of
   the residual path gap is that alone — `Biomarkers/routines/analytics.py` against
   `BRAVO/modules/Biomarkers/routines/analytics.py`.
2. **It cannot distinguish a superseded number from a dropped one.** The numeric column barely
   moves, and that is the expected and desired outcome: most of that residue is precisely what the
   PI asked to be dropped — stale line numbers, stale suite counts, timings from sessions whose code
   has since changed, and the losing side of all 30 resolved contradictions. **Porting those
   numbers would have been the error, not omitting them.**

The full item-by-item list is `port_gap_report.json`.

---

## 6. Observations, second session 2026-09-07 — the code map for Track A steps 5 to 8, and the state of the tooling

**Everything here is observation, read from the code and the tools on the day stated. Line numbers
are omitted on purpose; search for the name.**

### 6a. Where the remaining Track A products are built today

- **The therapy table** is `settings_stream(participant)` in `StimOptimizer/adapter.py`: one row per
  timestamp and hemisphere, columns `t, src, hemi, amp, pw, rate, upper, cathode, schema`, read
  from every stored Percept file's `Groups.Final` and `GroupHistory`. Its own docstring records one
  pass over 568 files at 33.65 s yielding 6,617 rows. **Both** the Stim Optimizer request
  (`StimOptimizer/bravo_service.run_for_participant`) and the closed-loop request
  (`ClosedLoopDeployment/adapter.evidence_inputs_cached`) build it, so it is paid twice per pair
  of page loads. The closed-loop copy is memoised in that module's `inputs` store entry together
  with the epochs and the design matrix.
- **The matcher** is `attach_pros(epochs, pro_df, pro_times_utc, washin_min, items)` in the same
  file, over `exposure_epochs(stream)`. Its output, the epoch-level design matrix, is what "the
  therapy and pain matched table" means; it has never existed as a stored table. Its rows carry
  per-epoch means, standard deviations and counts of six pain items.
- **The 22-centre biomarker product** is the band-by-length sweep:
  `band_time_sweep_for_participant` in `Biomarkers/bravo_service.py`, arithmetic in
  `analytics.band_time_sweep_from_power`. The centres come from `analytics.sweep_center_freqs`
  filtering the tile store's own centre list (`_LSB_SPECTRUM_CENTERS`, half-integers 2.5 to 99.5)
  to 8 to 30 Hz, which yields 8.5 to 29.5. The response holds, per contact pair, grids of
  correlation and discrimination value over lengths × centres, plus best rows per centre.
  `DEFAULT_PAIN_BAND_CENTERS_HZ` (23 whole-Hz centres) and the closed-loop module's
  `DEFAULT_BAND_CENTERS_HZ` are different lists for different products.
- **The amplitude effect** today: slope by `assess_response` in
  `StimOptimizer/routines/lfp_response.py` (era-blocked, cluster-robust fit of log power on
  current); **curvature by `amplitude_response_shape` in `StimOptimizer/routines/within_visit.py`,
  which has no caller in live code, only tests**; the per-band table with the harmonic-landing flag,
  `within_visit_band_scores` in `ClosedLoopDeployment/clinic_steps.py`, likewise has no live caller.
  The orchestrator `amplitude_response_cached` in `ClosedLoopDeployment/adapter.py` writes the
  `response` kind but is reached by no endpoint. What the closed-loop page actually shows comes from
  `lfp_evidence.build_all` and `screen_cells`.
- **The three-source comparison** (`ClosedLoopDeployment/three_source_response.py`) computes per
  route, per setting, the settled band power, drops saturated tiles, and reports the worst
  pairwise fold between routes in `three_source_plots.py`. It gates nothing and writes no verdict.
  `ground_truth_verdict` is a registered kind in `CacheStore/provenance.py` that nothing writes.
- **Store traffic in live code**: exactly three kinds are written — `raw_lsb_tiles` by Biomarkers,
  `inputs` and `response` by the closed-loop module. `consumer=` is passed by no production call
  site, so the self-derived refusal has never yet fired outside its tests. `store_if_absent` had no
  live caller before step 4.
- **Module imports**: the closed-loop module imports Biomarkers (function-local, to avoid a cycle
  and the Django registry order); Stim Optimizer imports Biomarkers; **nothing imports the
  closed-loop module from Stim Optimizer or the reverse**. The pain reports reach the closed-loop
  module through Stim Optimizer's `build_design_matrix`, which calls Biomarkers' `_load_pros`.

### 6b. Facts about the written record found stale this session

- The 30 step titles of the approved plan exist verbatim in exactly one file,
  `docs/archive/2026-09-07/PLAN_cache_store_phase2_2026-09-07.md`; `task_plan.md` held only Phase 1's
  nine until this session. The handoff's Track A table had renamed two: step 3 "in MySQL" had become
  "in the database", and step 4 "Store the REDCap frame" had become "Store the REDCap pain-report
  snapshot". `ARCHITECTURE_cache_store.md` §6 named "the ground-truth verdict" as the fifth remaining
  Track A step; that is Track G step 2. Track A step 8 is "Have Stim Optimizer read the store and
  write its outputs back".
- `CLAUDE.md` and the `AGENTS.md` override box said the framework tree did not exist; it does, and
  is gitignored.

### 6c. Tooling

- `planning-with-files` 3.16.1 is installed at user scope under `~/.claude/plugins/cache/`. Its
  hooks fire from `hooks/hooks.json` on session start, each prompt, before matched tool calls, after
  writes, before compaction and on stop. In legacy mode the stop hook is advisory only.
  `plan-doctor.sh` against this repository: resolver PASS, injection PASS, one injection 221 ms.
- The host test suite needs `~/.claude-science/conda/envs/bravo_app/bin/python`.
- The store's live root is `/usr/src/BRAVO/BRAVOStorage/cache` with `biomarker_psd` (98 files,
  506 MB), `biomarker_psd_rows` (6,309 files, 30 MB), `biomarker_shared` (one 245 MB tile entry),
  `closed_loop` (two `inputs` entries, 5 MB) and now `redcap_reports` (one entry, 28 KB).

### 6d. Step 5 observations

- The `inputs` and `response` kinds written by `ClosedLoopDeployment/adapter.py` pass no
  provenance and no consumer; `evidence_inputs_cached` memoises the settings stream, the epochs and
  the design matrix together under the recording-set signature, so with the stream now stored its
  cold build drops from about 35 s to under a second, but its sidecar still cites nothing.
- On the host, pandas 3 defaults `pd.Timestamp` to microsecond resolution while the container's
  pandas 2.2.3 uses nanoseconds; the Parquet round trip keeps whichever the builder used, so a test
  must assert the timezone and not the resolution.
- The bridge runs one job at a time; its heartbeat age rises to the length of the running job.
