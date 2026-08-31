# BRAVO_pain — Mega Handoff (consolidated)

> **HOW TO UPDATE THIS DOC (read before editing).** This is the single durable handoff; keep it
> that way. At the end of a session that changed the codebase:
> 1. **Read the whole doc first.** Don't append at the top while the bottom goes stale — that is
>    exactly how this file rotted before (duplicate headers, contradictory HEAD/suite lines).
> 2. **Update the state line below** (branch, HEAD short-SHA, suite count) to the real `git`/test
>    state — verify, don't copy from memory.
> 3. **Add a §0 entry** (newest first) summarizing what changed and why. Fold related fixes into
>    one entry; don't accumulate near-duplicate bullets.
> 4. **Update the affected reference**, not just §0: constants in §2, decisions in §3, open items
>    in §4, gotchas in §7, file map in §8. If a constant/function was removed, delete its row —
>    don't leave it described as current.
> 5. **Remove outdated comments/claims.** When a later fact supersedes an earlier one, drop the
>    earlier one rather than stacking a contradiction. §2b frozen-model numbers are SACRED — keep
>    verbatim.
> 6. Keep it durable: constants, decisions, gotchas, file map — not the blow-by-blow (that lives
>    in the per-session `SESSION_HANDOFF_*.md` / `HANDOFF_*.md`).
>
> **Purpose.** Single authoritative reference for the BRAVO_pain closed-loop DBS platform.
> Read this to be current. Where sources conflicted, the chronologically later one won and the
> stale claim was dropped. **State as of this revision:** branch `PS_closedloop_deployment`,
> **MERGED to `v3.1.0`** (2026-06-29, PR #9 → merge commit `39dfb2f`): the entire
> `PS_closedloop_deployment` line (61 commits — two-window matching, R1/R2/R11/R12 accuracy
> remediation, montage device-PSD coverage, binarization fixes) is now in the default branch. Code
> review: mergeable_state `clean`, container suite 261/261, no CI configured on the repo. Branch is
> retained (not deleted). Continue feature work on `PS_closedloop_deployment`; it is now 1 merge behind
> `v3.1.0` only by the merge commit.
>
> **Documentation:** Comprehensive README created (`README_BIOMARKERS_AND_DEPLOYMENT.md`, 759 lines)
> covering full v3.1.0 architecture: data sources, two-window matching semantics, LSB computation
> (TD-transform k=352.62 + PSD-bridge), cache/matching flow, spectral feature importance, binarization
> (unique-PRO tertiles), per-channel count semantics, deployment checklist, ClosedLoopSim UI/workflow,
> configuration, testing, troubleshooting, and development guidelines.
>
> **Branch HEAD `b239e57`** (hotfix: guard the offset-range string against null `scanModel.counts` — the
> hoisted `rangeTxt`/`offsetSummary` in BinarizationPreview.js read `counts.min_abs_offset_min` before
> the preview model loaded, throwing `Cannot read properties of null` and blanking the Biomarkers module.
> Added `counts &&` guards; rebuilt chunk `434.861dc283`, main `8fa51c07`). Below = the two-window change
> it patches.
>
> **`b06b0e2`** (biomarker matching: TWO-WINDOW MODALITY SPLIT + cache-only path). The two match
> windows now have distinct jobs: the **main MatchToleranceMin slider = eligibility radius for BOTH TD
> and PSD** (PSD bridge no longer hard-locked to ±120 s); the **extent slider is repurposed into a
> TD-signal QUANTITY knob** = how many of the nearest 3 s TD tiles to median per rating (nearest
> round(q/3), |Δt|-ranked). The cache-based `live_lsb_spectrum_match` is now the ONLY scan path (legacy
> real-time `per_pro_lsb_spectrum` recompute retired in the scan; still used by the timeline modeled
> markers). Per-channel `n_high/n_low/n_excluded` now count DISTINCT PROs carrying a resolved LSB, so
> `n_high+n_low+n_excluded == n_td+n_psd_bridge == n_channel` (fixes the per-channel/pooled mismatch AND
> the per-channel dash bug). Frontend: Legacy/Live toggle removed (cache always on), extent slider
> relabeled + max raised to 300 s, two-window caption, pooled line sums per-channel counts, match-offset
> range added to the pro-report summary line. **Full in-container suite: PASS=261 FAIL=0.** Frontend
> rebuilt (chunk `434.9f4cba51`, main `87e35786`). Live verify on 2e3c75c0: widening the main slider
> 2→120 min grows matched PROs 258→927; the TD-quantity slider scales only n_td_used (×4 from 30→120 s),
> PSD untouched. Prior `7ce588d` (R1/R2/R11/R12 accuracy remediation — signed AUC, per-contact best-band,
> unique-PRO binarization cut, derivable montage whitelist; suite 260), `edfd0b5`, `d2f0d8a` are live.
> No-agent-commits rule RETIRED — agent now commits + pushes (bravo-session-rules Rule 4).
>
> **Per-session detail** lives in the `SESSION_HANDOFF_*.md` / `HANDOFF_*.md` files this doc
> synthesizes (the most recent narrative is `SESSION_HANDOFF_2026-06-28_biomarker_count_ux.md`; the
> TD→LSB calibration write-up is `HANDOFF_TD_LSB_calibration_2026-06-27.md`). This doc keeps the
> durable facts — constants, frozen model, decisions, gotchas, file map — not the blow-by-blow.

---

## 0. Recent work (newest first)

What changed and why, most recent first. The durable decisions are tabulated in §3; this section
keeps the operational specifics. Per-commit detail: the dated session handoffs.

**RESOLVED (2026-08-30, later): the July/August exports were re-synced into `RCS008 jsons/Stage 1`
and are now ingested. BRAVO holds data to 2026-08-28.** The earlier provenance conflict was a
Dropbox sync state, not a mystery: the folder now carries **577 JSONs (was 520) and 571 PDFs (was
512)**, including **57 JSONs stamped 2026-07-02 through 2026-08-28** that were absent when the folder
was first searched. Those are exactly the files the earlier stim census had read, which is why it
contained records to 2026-08-28 while the folder appeared to stop at 24 June. Lesson for next time:
a Dropbox CloudStorage path can legitimately lack files that existed earlier and will exist again —
re-check the folder before concluding data is lost, and check the embedded filename stamp rather than
mtime (every one of the 57 new files has a June-or-later stamp but was written to disk later still).

`ingest_percept_folder` handled all 57: content-hash dedup classified **57 of 57 as new** (contrast
the first run, where 15 of 20 filename-novel files were byte-identical re-exports), and all 57
ingested with **zero failures in 210 s**. The database went **502 → 559 SourceFiles** and
**5366 → 6095 Recordings** (+729), with newest SourceFile and newest Recording both now
**2026-08-28**. Orphan count did not move (still 9), i.e. every new file produced recordings. The
Biomarkers timeline can now advance past June; the assembled-matrix cache keys on the recording set
so the first view load after this ingest is the slow one that rebuilds it.

**"Biomarker plot is not updating with the new data" — the cache is EXONERATED; the platform simply
had no data past June (2026-08-30).** The plot is correct for the data BRAVO holds. Note the limit
of this finding: it is established that BRAVO's newest data is 2026-06-24 and that no ingest has
occurred since 2026-06-25. It is NOT established where the reportedly-new device files are — they
were searched for and not found (see the outstanding item at the end of this entry). Do not read
this entry as "the new files are sitting in a folder"; that was looked for and did not hold.

Evidence, all from the live container:

- `/usr/src/BRAVO/BRAVOStorage/` holds 508 entries, every one last written **2026-06-25**. Nothing
  has been uploaded since June.
- The database's newest `SourceFile` was **2026-06-24** and its newest `Recording` **2026-06-29**.
- `BRAVOStorage/cache/biomarker_psd` was touched the morning of 2026-08-30 — the view was running
  and re-rendering happily, off June data.

**The trap is structural, not a bug: copying exports into a folder does not put them in BRAVO.**
Until now the only ingest path was the browser upload view (`Server/APIs/DataHandler`
`DataUploadHandler`); there was no management command and no folder watcher. A folder of new
exports therefore produces exactly this signature — a "frozen" plot with no error anywhere,
because every view is faithfully drawing the last ingested state.

The caching was investigated first and **exonerated**. `_assembled_signature` in
`modules/Biomarkers/bravo_service.py` folds in each recording's (source, uid, hash), the Welch
window, the channel-canonicalisation version, the TD-missing version, the PRO-set signature, and
the patient-event recordings separately. It invalidates correctly; the in-container ingest log
shows the matrix reassembling on its own immediately after new rows landed. The container had also
been restarted, which clears the two in-process memos regardless.

**New: `Server/management/commands/ingest_percept_folder.py`.** Batch-ingests a folder of Percept
session-report JSONs for one participant, reusing the upload view's exact chain in the same order
(`DataCurator.saveCacheFile` → `DataCurator.MedtronicPerceptJSONDecoder`) so a batch-ingested file
is indistinguishable from a browser-uploaded one. Dedup is the identical HMAC over raw bytes
(`unique_hashed`) scoped to institute, so re-running over an already-loaded folder is a safe no-op.
Supports `--dry-run` (genuinely read-only; classifies new vs held and exits), `--limit`, and
`--continue-on-error`. The orbstack container cannot see host paths, but `BRAVO/_agent_bridge/` is
shared, so the working route is to drop exports into `_agent_bridge/incoming/` and point the
command at `/usr/src/BRAVO/_agent_bridge/incoming`.

First real run: of 520 host JSONs, 20 had filenames absent from the database, and content-hash
dedup showed only **5** were genuinely new — the other 15 were re-exports under different filename
prefixes with byte-identical payloads. Ingesting the 5 took the database from 497 to **502**
SourceFiles and 5322 to **5366** Recordings.

**"Orphan" SourceFiles are benign — do not chase them.** 9 of 502 SourceFiles carry zero Recording
rows, and this is correct behaviour in every case examined. Two classes: (a) near-empty session
reports (`Impedance` length 0, `PatientEvents` length 2, no neural blocks); (b) **re-exports of a
session already held**. Class (b) looked alarming — 2.6 MB files carrying `LFPMontage` ×6,
`LfpMontageTimeDomain` ×6 and a survey, yielding no rows — but `DataCurator` line ~307 dedups at the
RECORDING level on a content fingerprint scoped to the participant. All three such files carry
`SessionDate=2025-07-29T22:21:20Z` and that session's montages and surveys are already in BRAVO from
`Report_Json_Session_Report_20250730T140701.json` and two 20250730T1220xx files. Nothing is dropped.
Note also that one of them is *named* `...20250814T145112.json` while its SessionDate is 2025-07-29 —
export filename stamps and session dates disagree, which is the same naming quirk documented above.

**STILL OUTSTANDING — the July/August 2026 device data is not on this machine.** The reconstructed
stim timeline used in the StimOptimizer work runs to 2026-08-28 with epochs at 2026-07-07, 07-22,
08-06 and 08-12, so those exports existed when that census was built. They are now absent from every
granted host path (searched all roots for `*_202607*T*` / `*_202608*T*`, JSON and PDF: zero hits),
from the `RCS008 jsons` folder (newest file 2026-06-24 by both name stamp and mtime), and from
container storage. **They must be re-provided before the Biomarkers timeline can advance past June.**
Once they are, the fix is one command — drop them in `_agent_bridge/incoming/` and run
`ingest_percept_folder`, `--dry-run` first.

**The ingest surfaced a real latent crash in `deployment_summary` — fixed (2026-08-30).** After the
5 new files landed, the container suite went 261/261 → **259 pass / 2 fail**, both in
`deployment_summary` with `TypeError: unsupported operand type(s) for -: 'NoneType' and 'int'` at
`bravo_service.py` line 4935.

Cause: `power.get('n_ratings_needed', 0) - power.get('n_ratings_current', 0)`. **`dict.get(key,
default)` does NOT return the default when the key is PRESENT with value `None`** — the default only
fires on absence. The live payload was `{available: True, more_data_needed: True,
n_ratings_needed: None, n_ratings_current: 43}`: the power calculation legitimately flags
underpowering while being unable to SOLVE for the required N, because an effect at or near chance
has no finite sample size that reaches 80%. So the subtraction hit `None - 43` and took down the
whole deployment-summary export for that participant — not just the caveat.

Fixed to report the honest state instead of inventing a shortfall. It now reads: "Underpowered:
more independent pain ratings are needed for 80% power, and the required number could not be
estimated — at the observed effect size there is no finite sample size that reaches 80%. Treat this
as 'not estimable', not as a small shortfall. Currently 43 ratings." The sibling hazard one line up
(`power.get("power_current", 0) * 100`, same present-but-null pattern; note line ~4865 already
treated `n_ratings_needed_hi` as nullable with an `∞` fallback) was hardened the same way, and the
two gate-detail f-strings now render `not estimable` / `∞` rather than `None%`.

Worth reading for the science, not just the crash: the gate detail for RCS08 ZERO_TWO_LEFT at
20 Hz now prints **"power 5%, need ∞ ratings"** on 43 ratings. That was previously invisible behind
an exception.

**Then the power analysis itself was fixed, not just the crash it caused (2026-08-30).** Probing the
real inputs showed the first diagnosis was incomplete. There are TWO degenerate regimes, not one:

- `auc = 0.5` exactly → the early-return branch, `n_ratings_needed = None`. Correct: no finite N
  reaches target power. `power_current = alpha` is also correct — rejecting AUC=0.5 when it is true
  happens at the Type I rate.
- `auc` just ABOVE 0.5 → the main path, returning a **finite but absurd** requirement. The live call
  (ZERO_TWO_LEFT, 20 Hz, 5 Hz wide, nrs/tertile) gives `auc = 0.5036`, `n_ratings_current = 48`,
  `design_effect = 1.28`, and **`n_ratings_needed = 270,660`**. Required n scales as
  1/(AUC−0.5)², so a near-chance AUC yields a number no study can meet — ~5,400 years at this
  participant's ~50 independent ratings/year. The old caveat rendered that as "~270,612 more ratings
  needed", which reads as a data-collection plan when it is really a restatement of "this band does
  not discriminate".

Three defects fixed in `routines/analytics.py auc_power`:

1. **Return shape was not invariant.** The unavailable and at-chance paths returned a SHORTER dict
   than the main path (missing `auc_lo`, `n_pos`, `n_neg`, `power_current_lo`, `n_ratings_needed_hi`,
   `n_ratings_effective`, `small_sample`, `small_sample_floor`), so a consumer reading
   `power["power_current_lo"]` raised KeyError on exactly the degenerate inputs where it most needed
   a value. All paths now fill one canonical template via `_power_result_blank()`.
2. **No way to tell "undefined" from "broken" from "huge".** Added `status` ∈
   {`powered`, `more_data_feasible`, `requirement_infeasible`, `at_or_below_chance`} plus
   `requirement_feasible` and `feasible_n_max`, so callers branch on a value instead of re-deriving
   the logic from floats. Feasibility is decided on the CONSERVATIVE requirement when a CI lower
   bound supplied one, consistent with the existing fail-closed gate.
3. **The power-vs-N curve was unreadable.** `n_top` was `max(N0, n_need) * 1.35`, so the at-chance
   case built a 40-point grid running to ~365,000 ratings on which the clinician's real 48 sit
   invisibly at the origin and the curve reads as a flat line at alpha. Now capped at the feasibility
   ceiling with `curve_truncated` flagged rather than silently clipped.

`FEASIBLE_N_RATINGS_MAX = 500` is the ceiling, chosen in this study's own units and documented at the
constant: ~50 independent ratings/year for one participant makes 500 a deliberately generous ~10-year
horizon, and it is a keyword argument so a pooled multi-site analysis can raise it. The raw
requirement is always reported alongside, so the threshold hides nothing.

Consumer side, `deployment_summary` now branches on `status`. The live readout reads: *"Underpowered
and NOT rescuable by more data: 80% power would require 270,660 independent ratings, beyond the 500
ceiling for a realistic single-participant study. Because required n scales as 1/(AUC-0.5)^2, this is
a restatement of 'indistinguishable from chance', not a collection target. Currently 48 ratings."*
The gate detail changed from `power 3%, need 270660 ratings` to `power 3%; target power NOT achievable
by collecting more data (AUC indistinguishable from chance)`.

Five tests added covering shape invariance across all four paths, the status vocabulary in each
regime, at-chance giving an undefined rather than large requirement, curve capping, and the ceiling
being configurable. Container suite **267/267**.

`test_deployment_summary_survives_unestimable_power_requirement` added to
`modules/Biomarkers/tests/test_analytics.py`. It is deliberately non-vacuous — verified that on the
live participant the call returns `available: True` with exactly one `Underpowered:` caveat — and it
asserts no caveat or gate detail leaks a literal `None`/`None%` into user-facing text. Container
suite now **262/262**.

**Outlier exclusion added to the full-spectrum exploration scan (2026-08-30, PI request).**

Rule: a sample is dropped when `|x - median| >= N_MAD * MAD` with `MAD = median(|x - median|)` and
**no consistency rescaling**, i.e. the literal reading of "five MAD or greater from the median".
Defaults live in `analytics.OUTLIER_N_MAD = 5.0` and `analytics.OUTLIER_SCALE = "log"`. Request
overrides: `OutlierNMad` (0 disables, reproducing the pre-change numbers) and `OutlierScale`
(`log`/`raw`). Note this is NOT the Iglewicz-Hoaglin modified z-score (0.6745/MAD, 3.5 cut); 5 raw
MAD is about 3.37 sigma on Gaussian data.

**Two decisions that are NOT cosmetic, both measured rather than assumed:**

1. **Applied on the LOG scale, not raw.** The LSB band-power feature is multiplicative and spans
   roughly 0.1 to 15000, so a symmetric raw-scale window is proportionally far tighter above the
   median than below: it deletes the upper tail almost exclusively. Measured on the real RCS08 scan,
   the raw-scale rule removed **17,930 samples (3.71%)** and the log-scale rule **29,938 (6.19%)** —
   and the raw rule's removals were one-sided. Worse, the *selected biomarker changed*: strongest AUC
   was 0.9040 at 64.5 Hz under the log rule but 0.9192 at 10.5 Hz under the raw rule. A test
   (`test_log_scale_rule_is_two_sided_where_raw_is_not`) pins the one-sidedness.
2. **Per (channel, band), not pooled.** Band-power distributions differ by orders of magnitude across
   channels and frequencies, so a pooled threshold would be set by whichever channel has the largest
   units. This was the open question from the PI's dictated request and is still worth confirming.

**READ THIS BEFORE QUOTING THE REMOVAL COUNT: 6.19% is far more than the ~0.1% a well-behaved
unimodal distribution yields at 5 MAD.** That is evidence the feature is a MIXTURE across recording
sessions, not a clean distribution with a few artefacts, so some of what the rule removes is likely
real physiology rather than noise. The panel text says so explicitly (it triggers above 2% removal).
This is a caveat on the rule, not a reason to skip it.

**One shared exclusion set reaches every statistic.** Implemented by blanking excluded samples to
NaN in BOTH the display feature and the fit feature at the single point they are computed, so every
downstream consumer that already masks on `isfinite` drops the same samples without needing its own
filter and without disturbing row alignment against the label and cluster vectors. Verified by
differencing the real scan with the rule off vs on: the correlation changed in **410 of 576 bands**
and the cross-validated AUC in **290**, with `n` and `n_r` moving in step. Cohen's d, the median
delta and the rating-clustered logistic p are code-path verified rather than differenced, because
they are not emitted as per-band curves in this payload — the effect size reads
`band_power_by_center` (the blanked array, via `bp_list` at the scatter block) and the clustered p is
computed inside `_band_cv_stats(bp_log)` alongside the AUC from the same blanked fit array. The
scatter's reported `n` already follows the exclusion because its mask is
`np.isfinite(bp_log) & label_fin`.

Guards, each with a test: fewer than 4 finite samples, fewer than 4 strictly-positive samples for
the log rule, and a **zero-MAD guard** — when a majority of samples share one value the MAD is 0 and
a naive rule would flag everything that merely differs from the median, deleting all remaining
variation; the rule declines and says so in `skipped`. Non-finite entries are never counted as
removals, so the reported number means genuine exclusions.

Reported in `spectral_feature_importance()["outliers"]` (rule string, n_mad, scale, n_removed,
n_samples_considered, pct_removed, n_bands_evaluated, n_bands_with_removal,
n_bands_skipped_zero_mad, applies_to, detected_on) and echoed at the response top level as
`outlier_n_mad` / `outlier_scale`. The UI states the rule, the count and the mixture caveat in the
subtitle beneath **Full-spectrum exploration**. Container suite **273/273**.

**CRITICAL FIX (2026-08-31): `rating_group` on the time-domain path was built from the pain SCORE,
not the identity of the matched report — so the plate's "rigorous" clustered statistics were
clustered on the outcome itself.** This is audit item F9/C3, and it is the most consequential of the
inference defects because it corrupted the statistic the panel presents as the trustworthy one.

`pipeline.run_timedomain_branch` reconstructed the grouping by searching `pro_df` for a report whose
VALUE equalled the session's label and taking the first hit
(`np.where(np.abs(pro_vals - lbl) < 1e-6)[0][0]`). On an integer scale that collapses every session
sharing a score into ONE "rating", so the number of groups equalled the number of distinct pain
VALUES. Measured on live RCS08:

| metric | groups BEFORE (= distinct values) | groups AFTER (= matched reports) |
|---|---|---|
| `nrs` | **7** | **72** |
| `left_leg_vas` | 37 | 46 |

Severity is metric-dependent, which is why it survived: on a 0-100 VAS the collapse is a 24%
undercount, but on integer NRS it is a **10x** undercount. Two consequences, both on the rigorous
statistics:

- `_cluster_robust_logit_p` clustered on 7 clusters instead of 72. Sandwich variance on that few
  clusters is unreliable, and this is the p-value the plate presents as the pseudoreplication-corrected
  headline (the ringed survivors).
- `_cv_logistic_auc`'s `StratifiedGroupKFold` grouped on those same collapsed groups, i.e. **the CV
  folds were defined by the outcome being predicted** — whole pain levels were held out together.
  That is not a defensible fold structure under any reading.

Fixed at the source rather than patched: `adapter.align_pros` now records `matched_pro_time`, the
IDENTITY of the report each session matched (its timestamp under time-window matching; the calendar
date under legacy same-day aggregation, where the day's aggregate genuinely IS one shared rating, NaT
when unmatched). `pipeline` factorizes that identity — distinct report gives a distinct group,
unmatched gives -1. `labels` is `session_df[label_col]`, so epoch *i* is session row *i* one-for-one
and the identity carries straight across. The value-matching fallback is **deleted, not kept**: if
the alignment assumption ever fails the code logs and leaves the grouping unset rather than silently
reverting to a grouping that clusters on the outcome. **Three** tests pin it, in
`tests/test_adapter.py` (the container suite moved 277 -> 280, i.e. +3):
`test_align_pros_records_the_matched_report_identity_not_just_its_value` (two sessions matched to
DIFFERENT reports that share a score land in different groups),
`test_align_pros_unmatched_session_has_no_identity` (NaT factorizes to -1 rather than joining
whichever group sorts first) and `test_align_pros_same_day_branch_groups_by_date`. The commit message
on `cf7c429` says "four tests" — that count is wrong; there are three, and they are named here.

Not pinned by a test, and worth adding: the `pipeline` side of the fix. The three tests all exercise
`align_pros`; the factorize-and-clamp step in `run_timedomain_branch` and its no-fallback warning
path are currently covered only by the live measurement (nrs 7 -> 72 groups), not by an assertion.

Note `pipeline.py` had no logging at all — a first draft of that warning would have raised
`NameError` on `_log`. A module logger was added.

**THE RESULT THIS EXPOSED, and it matters scientifically: under correct rating-level clustering, NOT
ONE of 576 candidate bands survives FDR for the left leg — the PI's designated primary site.**
Verified as a real null rather than missing values (a clustered p is computed for all 576 cells):

| metric | naive FDR survivors | rigorous FDR survivors | min clustered p | min q | strongest AUC |
|---|---|---|---|---|---|
| `nrs` | 454 of 576 | **156** | 3.98e-06 | 0.0012 | 0.859 |
| `left_leg_vas` | 444 of 576 | **0** | 0.00149 | **0.128** | 0.904 |

So for the primary site the naive analysis would pass 444 of 576 bands and the honest one passes
none, while the strongest AUC on display is 0.904. That combination — a high AUC with no band
surviving clustered multiplicity correction — is exactly what this plate exists to catch, and it
should be read as "no validated biomarker for the left leg on this data", not as a 0.904 result.
Do not quote the naive count. (The earlier audit recorded 471 naive / 74 rigorous under the OLD
grouping, but its naive count differs from any configuration measured here, so treat that pair as a
different configuration rather than a clean before/after.)

Container suite **280/280**.

**CRITICAL FIX (2026-08-30): the conservative "powered" gate in `auc_power` was defeated by a fold,
and could report a FALSE PASS on a device-facing readout.** Found by a delegated inference audit,
confirmed independently against live RCS08 data before changing anything.

`analytics.py` computed `a_lo = max(auc_lo, 1 - auc_lo)`, commented "fold defensively". That mirrors
a sub-chance CI lower bound up above 0.5 — destroying exactly the information the caller's DE-FOLDED
bootstrap CI exists to carry (that de-fold is deliberate and was separately audited as correct).
Two distinct failures resulted:

1. **Silently inert.** With the real RCS08 bound `auc_lo = 0.3484` and `auc = 0.5036`, the fold gave
   0.6516, which fails `a_lo <= auc` AND fails `a_lo <= 0.5`. Neither branch ran, so `auc_lo`,
   `power_current_lo` and `n_ratings_needed_hi` all returned `None`. The fail-closed branch — the
   entire point of a conservative gate — was **unreachable for precisely the bands it was written
   for.** Verified across eight different lower bounds: all `None`.
2. **False pass.** At `auc = 0.85` with `auc_lo = 0.20`, the fold returned 0.80, which satisfies
   `a_lo <= auc`. Power was then computed at a fabricated "conservative" bound of 0.80 and the status
   came back **`powered`** — a band whose interval badly crosses chance reading as deployable. That is
   the gate being *more* permissive than the point estimate.

Fixed by keeping the SIGNED bound: clamp a bound above the point estimate down to it (that means the
caller passed the wrong end), but never mirror across 0.5. New payload field `ci_crosses_chance`,
present on every return path so the shape stays invariant. Measured after the fix:

| case | before | after |
|---|---|---|
| auc 0.85, auc_lo 0.20 | `status=powered`, bound 0.80 | `auc_lo=0.20`, `power_lo=0.05`, `crosses=True`, not powered |
| RCS08: auc 0.5036, auc_lo 0.3484 | all `None` | `auc_lo=0.3484`, `power_lo=0.05`, `status=requirement_infeasible`, `crosses=True` |
| genuinely powered: auc 0.85, auc_lo 0.72 | `powered` | `powered`, `power_lo=0.994` — no false negative introduced |

Three tests pin it, including shape invariance across all four return paths.

**The rest of that audit is a 13-item specification, NOT yet implemented** — see the artifact
`CI_SPEC_biomarker_plate.md` and its three supporting tables. The highest-severity outstanding items:
the correlation-spectrum p is a naive t on EPOCHS (at the selected cell 9.24e-10 naive versus 1.56e-04
cluster-robust on ratings, an SE inflation of 1.65x, taking BH survivors from 20 cells to 4); the
selection-corrected `perm_p` permutes epoch labels rather than ratings (0.0729 versus 0.233 under a
rating-level null); a time-ordered holdout shows the winning band's correlation **reverses sign**
out of sample (r_train +0.552, r_holdout -0.413); the bootstrap block length of 12 gives simulated
coverage 0.850 against 0.945 at length 1; and `rating_group` on the time-domain path is built by
value-matching pain scores, collapsing 72 true matched ratings into 7 groups. The audit also found
several things sound and says so explicitly — do not "fix" the cluster resampling, the BCa
acceleration, the de-fold, or the deployment MAD policy.

**"Original bug" closed out: the Biomarkers API now has a cache force-refresh (2026-08-30).** There
was previously no bypass at all, so if the assembled-matrix cache ever DID go stale there was no way
to rebuild from the UI — which is why the original "plot not updating" report had no diagnostic path,
even though the actual cause turned out to be device files that had never been ingested. Two
granularities, because they differ in cost by two orders of magnitude:

- `ForceRefresh: "matrix"` (also `true`/`1`/`yes`) — ignore the assembled-matrix npz, reassemble from
  the per-recording spectra. Seconds. Measured: 27.5 s, rebuilt from 809 cached spectra with **0**
  recordings re-Welch'd.
- `ForceRefresh: "all"` (also `full`/`hard`) — additionally ignore the per-recording spectra, forcing
  a decode + Welch of every recording. Minutes.
- Absent/`false`/`0`/unrecognised → normal cached read. An unrecognised value maps to "no refresh"
  rather than raising, so a typo can never trigger the expensive path or 500 a working panel.

A refresh still WRITES the rebuilt caches, so the next request is fast again. Verified that a refresh
reproduces the SAME answer rather than a different one: strongest AUC 0.904032 at 64.5 Hz both ways.
The response now carries a `cache` block (`force_refresh`, `meaning`, `how_to_refresh`) so a future
"it is not updating" report is answerable from the payload alone — and that text points the reader at
the newest SourceFile date FIRST, because that, not the cache, was the real cause last time.

Container suite **277/277**.

**RESOLVED (2026-08-30, PI decision): ONE outlier filter for the whole biomarker plate, 5 MAD,
applied uniformly to FEATURE, LABEL and the chronic LFP-power column.** The three separate
implementations described below have been consolidated into a single canonical rule in
`routines/stats_utils.py`:

| symbol | meaning |
|---|---|
| `stats_utils.MAD_N_DEFAULT = 5.0` | the ONE threshold; change it here to move the whole plate |
| `stats_utils.mad_outlier_flags(x, n_mad, scale)` | True == outlier (drop) |
| `stats_utils.mad_keep_mask(x, n_mad, scale)` | True == keep; exact complement, for keep-polarity callers |

`analytics` imports the threshold and the flag function (no local copy remains).
`streaming_psd._mad_keep` and `adapter.mad_outlier_mask` now DELEGATE, keeping their names and
keep-polarity for existing callers but losing their private 3 MAD defaults. Verified at runtime that
all three agree on identical data: the two keep-masks are exact complements of the canonical drop
mask, boundary included (the canonical rule uses strict `>` so it matches `_mad_keep`'s `<=` keep).

**THE MEASUREMENT THAT SETTLES 3 vs 5 — 3 MAD would have discarded nearly a quarter of the data.**
Run on the real RCS08 scan, same code path, threshold varied:

| threshold | samples removed | of total | bands affected | label outliers |
|---|---|---|---|---|
| 3 MAD | 110,355 | **22.82%** | 576 of 576 | 99 |
| 5 MAD | 29,938 | **6.19%** | 410 of 576 | **0** |

At 3 MAD every single band loses samples and 22.8% of the matched data goes, which is not a
defensible artefact filter on a feature that is a session mixture. 5 MAD is the standing decision.

**Note the label column: at 5 MAD there are ZERO label outliers.** So including the pain label in the
exclusion is currently a NO-OP on this dataset — it is the right uniform policy and it is wired, but
it is not moving any number today. At 3 MAD it would have dropped 99 ratings.

**Scale is per-quantity, and this is not a violation of "one rule" — it is what keeps the one rule
two-sided.** The rule is evaluated in log space for MULTIPLICATIVE quantities (raw linear LSB in the
exploration scan, the chronic LFP-power column) and on the raw scale for quantities that are already
additive (dB/z features in `streaming_psd` and the deployment family, and the bounded ordinal pain
label). A symmetric window on a linear power axis deletes the upper tail almost exclusively; measured
earlier, the raw-scale rule removed 3.71% one-sidedly against 6.19% two-sidedly, and the SELECTED
BAND changed as a result.

**API CHANGE, worth knowing before reading old code: `mad_k=None` / `k=None` now means USE THE
CANONICAL THRESHOLD, not "disabled".** Explicit disable is `0` (or `False`). This bit twice during
implementation and both traps are now fixed with comments in place: `adapter._concat_chronic` and
`streaming_psd.pearson_corr_psd_label` both guarded their filter with a plain truthiness test
(`if mad_k`), so the new `None` default would have SILENTLY SWITCHED OUTLIER REJECTION OFF for every
default call — in the correlation spectrum's case, for the whole panel. No production caller passed
`None` expecting the old meaning (all use the default); two tests did and were updated to `0`.

Two adapter tests failed on the threshold change and were corrected rather than relaxed: they now
read `stats_utils.MAD_N_DEFAULT` instead of hardcoding a multiplier, so they track the canonical rule
and cannot silently drift from it again. Container suite **274/274**.

**Superseded, kept for orientation — the audit that led to the decision above:**

**PIPELINE-WIDE OUTLIER AUDIT (2026-08-30) — the headline is that THREE MAD RULES ALREADY EXISTED
and they disagree with each other and with the new one.** This is the finding that matters most.

| helper | polarity | default | applied to | drives |
|---|---|---|---|---|
| `analytics.mad_outlier_flags(x, n_mad, scale)` (NEW) | True = **DROP** | **5 MAD**, log scale | feature only | exploration scan |
| `adapter.mad_outlier_mask(x, k)` | True = **KEEP** | **3 MAD** | chronic LFP power col | `_concat_chronic`, `pipeline.py:462` (on LABELS) |
| `streaming_psd._mad_keep(x, k)` | True = **KEEP** | **3 MAD** | feature **AND label** | `pearson_corr_psd_label` -> the whole correlation spectrum |

Three consequences, the first already fixed:

1. **FIXED — name/polarity trap.** The new helper was originally called `mad_outlier_mask`, the same
   name as adapter's, but returns the **inverse** mask (adapter: True = keep; new: True = drop) with a
   different parameter name (`k` vs `n_mad`) and a different default (3 vs 5). Two same-named
   functions whose masks are complements means copying a call site between modules silently keeps
   ONLY the outliers. Renamed to `mad_outlier_flags`, with a docstring saying not to rename it back
   and a test (`test_the_two_mad_helpers_have_opposite_polarity_and_must_not_be_confused`) asserting
   the two masks are exact complements at a matched threshold and that `analytics` does not export
   the old name.
2. **PI DECISION NEEDED — 3 MAD or 5?** The correlation spectrum has been rejecting at **3 MAD**
   all along, which is STRICTER than the 5 MAD just requested. Unifying at 5 would LOOSEN an
   existing filter and change correlation-spectrum numbers that may already have been reported.
   Not changed unilaterally.
3. **PI DECISION NEEDED — filter the pain label or not?** `_mad_keep` is applied to the LABEL as
   well as the feature, so extreme pain ratings are currently dropped from the correlation spectrum.
   The new rule deliberately leaves the label intact, on the reasoning that a bounded ordinal pain
   scale has extreme values that are signal rather than contamination. These two positions are
   contradictory and one of them should win.

**Deployment and threshold-detector family: REPORTED, NOT REMOVED.** A deliberate policy split, not
an oversight. These functions return two kinds of number: an AUC (associational, where trimming a
tail is defensible) and a cut-point threshold with its sensitivity/specificity (an OPERATING POINT
the device runs against, where the device meets the full distribution). A threshold fitted on a
trimmed sample would not deliver the sensitivity printed beside it. So `outlier_report_for_feature()`
evaluates and reports the rule without removing anything, and `deployment_roc` additionally returns a
clearly-labelled `sensitivity_analysis` with the AUC recomputed excluding the flagged samples.
Wired into `deployment_roc`, `deployment_roc_by_era`, `threshold_drift_by_week` and
`deployment_forward_chaining`. Note the scale subtlety: those features are ALREADY log/dB, so the
rule is applied with `scale="raw"` — passing `scale="log"` would take log10 of a dB value and
silently skip the negative ones.

**Measured on live RCS08, and it changes the picture: the deployment feature has essentially no
outliers.** `band_deployment_roc` on ZERO_TWO_LEFT @ 20 Hz flags **0 of 82** samples (MAD 0.431);
`band_deployment_roc_by_era` flags **6 of 409 (1.47%)**. So the 6.19% seen in the exploration scan is
a property of the RAW LSB feature and its heavy multiplicative tail, NOT a pipeline-wide problem. The
committed band's AUC is not being driven by tail samples.

**Also worth knowing: the exploration scan's correlation is Spearman, which is rank-invariant and
already robust to outliers** — so the removal moves it only modestly. The statistic that genuinely
needed protection is the **Pearson** correlation spectrum, and that one already had a 3 MAD filter.

**STILL TO DO after this audit.** Not wired and not audited in depth: `psd_spectra` (not referenced
by the frontend), `cluster_scatter` (not referenced), and the chronic cv_df statistics
(`sliding_window_analytics`, `roc_analysis`, `lfp_distribution`, `power_pain_scatter`,
`pain_binarization`) which read `LFP_smoothed` from the chronic frame rather than the per-rating band
feature — a different data path whose outlier handling comes from `adapter._concat_chronic` at
3 MAD. `psd_lsb_conversion` and `deployment_summary` are also not yet covered.

**Superseded note (kept for orientation) — the earlier to-do list below predates the audit above.** The exclusion currently reaches the
exploration SCAN only. Not yet audited or wired: `corr_spectrum`, `psd_spectra`, the chronic cv_df
statistics (`sliding_window_analytics`, `roc_analysis`, `lfp_distribution`, `power_pain_scatter`,
`cluster_scatter`, `pain_binarization`), the threshold detector (`_otsu_threshold`,
`threshold_drift_by_week`) and the deployment family (`deployment_roc`, `deployment_roc_by_era`,
`deployment_forward_chaining`, `psd_lsb_conversion`, `deployment_summary`). The deployment/threshold
group shares ONE feature source, `_band_feature_from_detail` (callers at lines 2194, 2501, 2680,
2799), which is the single insertion point for all four.

**Open judgement call for the PI, do not silently resolve:** blanket exclusion is defensible for
ASSOCIATIONAL statistics (correlation, AUC, effect size) but questionable for anything that sets an
OPERATING POINT the device will run against — the detector threshold and the LSB conversion
constant. A threshold estimated on a trimmed distribution while the device encounters the full one
means the reported sensitivity and specificity are not what the device will achieve. Recommended
resolution: compute the operating point on the full distribution, report the outlier count beside
it, and present the outlier-excluded AUC as a labelled sensitivity analysis rather than as the
headline.

**StimOptimizer is now reachable from the sidebar (2026-08-30).** Five registrations, mirroring the
Biomarkers precedent:

| layer | file |
|---|---|
| DB -> design matrix | `BRAVO/modules/StimOptimizer/adapter.py` (new) |
| service | `BRAVO/modules/StimOptimizer/bravo_service.py` (new) |
| API view | `BRAVO/Server/APIs/DataAnalysis.py` -> `QueryStimOptimizer` |
| route | `BRAVO/Server/APIs/urls.py` -> `path('queryStimOptimizer', ...)` |
| React view | `Client/src/views/Reports/StimOptimizer/index.js` (new) |
| sidebar | `Client/src/routes.js` -> key `stimOptimizer`, `/reports/stim-optimizer/:participant_uid` |

Sidebar label is **"Stim Parameter Optimizer"**, directly under Biomarker Exploration. Frontend
rebuilt (`main.8caba91d.js`), and the dev override bind-mounts `./Client/build` to
`/usr/share/nginx/html`, so the host build is served with no image rebuild — confirmed the served
bundle contains the new view. `/api/queryStimOptimizer` resolves (verified by
`django.urls.resolve` -> `QueryStimOptimizer`, and by an unauthenticated POST returning 403 where an
unregistered path returns 405).

**Two SEPARATE test suites — do not quote one as covering the other.** The container suite
(`_agent_bridge/run_tests.py`, **267/267**) covers Biomarkers and does NOT include StimOptimizer:
the container has no `pytest` installed, so an attempt to run the module tests there fails with
`No module named pytest`. The StimOptimizer suite (**59 passed**) runs on the HOST in conda env
`bravo_app`, from `BRAVO/modules` with `PYTHONPATH=.`. Both numbers are current as of 2026-08-30;
quote them separately.

**Why `adapter.py` reads stored JSON rather than the Therapy tables — do not "simplify" this.**
BRAVO normalizes settings into `Therapy` -> `ElectricalTherapy` -> `ElectricalStimulation`, which are
dated and carry amplitude, pulse width, frequency and a bare `contact` index list — **but not the
hemisphere**. Recovering it means mapping contact indices through the device's lead
`Target`/`CustomName` definitions, and at one timestamp several rows differ by GROUP rather than by
side (verified: two rows at 2026-08-28 18:25, `GROUP_A` contacts [1..6] at 3.0 mA/150 us and
`GROUP_B` contacts [4,5,6] at 3.5 mA/100 us). Getting that wrong silently SWAPS hemispheres, which is
a wrong-science failure with no crash. The adapter instead loads each `SourceFile` through
`DataCurator.loadCacheFile` and reuses the validated dual-schema parser, where the device states the
hemisphere explicitly. **Validation:** on the 1,239 shared (timestamp, hemisphere) keys against the
file-based census, amplitude, pulse width, rate, cathode label and schema tag are **identical at
100%**. Session rows do not share keys because the census used the FILENAME stamp (local clock) while
the adapter uses `SessionDate` (UTC); measured on twelve August files these differ by a median of
**1.4 minutes** (max 65.1, on 2026-08-06). With a 1-minute wash-in that can move a report across the
boundary, so it is a real if small difference.

**The honesty gate was wrong and is fixed — this is the most consequential change here.**
`ArmResult.surface_can_resolve_its_optimum` tested `mu_star + k*sd_star < incumbent_mu`, which
rearranges to `gain > k*sd_star`: it cleared the CANDIDATE's SD but ignored the incumbent's own
posterior SD. Worked example from this run, arm `left_leg__Right`: incumbent mu +0.4285, candidate mu
-0.6881, so gain 1.117; candidate SD 0.989, incumbent SD 0.923. The old form passed
(1.117 > 0.989) and that single arm is why the module reported "recommendation supported" at all.
Propagating both SDs gives sd_diff = sqrt(0.989^2 + 0.923^2) = 1.353, and 1.117 < 1.353, so the
difference is **not** resolved. All four arms are now unresolved and `recommendation_supported` is
False, which is the truthful reading. `incumbent_sd` was added to the figure metadata to make this
computable. The joint GP covariance between the two cells is NOT carried, so `var1 + var2` is used;
because nearby cells are positively correlated this OVERSTATES the variance and the gate is therefore
strictly conservative — it can withhold a recommendation it might have supported but cannot
manufacture one. Tightening it needs `return_cov=True` on a joint prediction and is a documented next
step, not a silent approximation. **Five** tests pin this in `StimOptimizer/tests/test_pipeline.py`
(`test_gate_propagates_the_incumbent_sd_not_just_the_candidate`,
`test_gate_is_conservative_relative_to_ignoring_the_incumbent_sd`,
`test_gate_returns_false_when_the_candidate_is_worse`,
`test_gate_missing_incumbent_sd_degrades_to_the_candidate_only`,
`test_gate_rejects_a_degenerate_zero_variance`) — an earlier version of this line said six.

**Two blockers were dead code and now fire.** `safe_contiguous` was computed as
`safe_contiguous_ceiling is not None`, but that field is always a float (NaN when there is no
ceiling), so the expression was constant True and the non-contiguous-safe-set blocker could never
appear. It now reads the canonical `safe_is_contiguous`, and all four arms correctly report a
non-contiguous safe set. That exposed a further clinically relevant fact worth acting on: the
contiguous safe ceiling is **1.9-2.2 mA** while every proposed optimum sits at **4.0-4.9 mA**, i.e.
inside the safe set but in a **disconnected island**. A monotone amplitude ramp from the setting in
force toward that cell would cross amplitudes the safety model rejects. That is a consequence of the
two-anchor safety seed having no prospective side-effect data to shape it, and it now emits its own
blocker.

**Four audit fixes on top of the above (2026-08-30), one of them the same class of bug as the
original complaint:**

1. **The adapter silently dropped pain reports after the last settings observation.** The final
   epoch is open-ended — its `t_end` is only the last device export, not the moment the setting
   stopped being in force — so `_t < t_end` discarded every report collected since that export.
   Measured: 1 of 753 reports today (2026-08-29), but the mechanism means EVERY future report is
   dropped until new settings arrive, which is exactly the silent truncation that made the timeline
   look frozen. Open epochs now extend to +inf; `open_ended` still marks them so anything weighting
   by exposure knows `dur_h` is a lower bound. Design matrix went 751 -> 752 reports.
2. **The service understated its own data horizon.** It stamped figures with the last epoch's START
   (2026-08-12) while settings ran to 08-28 and reports to 08-29. It now reports the span, epoch
   count and report count.
3. **The power gate's conservative branch had no status guard.** The fix for "do not print a
   six-figure requirement as if it were a target" was applied to only one of the two branches, so a
   near-chance band that also had a CI lower bound still printed its requirement.
4. **The infeasible caveat quoted the point requirement while the status is decided on the
   conservative one.** It now quotes the deciding requirement and says which it is ("at the point
   AUC" / "at the CI lower bound"), so the number in the sentence is the number that produced the
   verdict.

`pipeline.run(outdir=None)` is new and means in-memory only — fit every arm, write nothing. The
service uses it so no CSVs or PNGs accumulate in the container, and figures are returned as Plotly
JSON for the browser (never rendered server-side; no kaleido).

**Housekeeping:** `BRAVO/_agent_bridge/incoming/` holds ~450 MB of session JSONs copied there to
feed the ingest run (20 files; 5 were new, 15 were duplicates). They are staging copies, safe to
delete once you are satisfied with the ingest. Left in place rather than removed, since deleting
inside the repo is the user's call. `_agent_bridge/_*.py` is already gitignored, so the probe
scripts written during this investigation (`_ingest_census.py`, `_storage_probe.py`,
`_orphan_probe.py`, `_orphan_dedup_check.py`, `_power_probe.py`, `_tb_probe.py`,
`_caveat_probe*.py`, `_dump_sf_names.py`) are untracked and equally disposable.

**Known gap, not fixed:** the Biomarkers API exposes no cache-bypass or force-refresh parameter, so
if the assembled-matrix cache ever DID go stale there is no way to force a rebuild from the UI. The
signature is sound so this is a robustness gap rather than an active fault; worth adding.

**`StimOptimizer` gains a callable entry point and runs per hemisphere (2026-08-30, untracked).**
Previously `routines/` was importable library code with no runner, so nothing in the module was
reachable from BRAVO the application. `StimOptimizer/pipeline.py` now provides `run(design_matrix,
sites=..., hemispheres=..., ...) -> RunReport`, mirroring `modules/Biomarkers/pipeline.py`; still
library mode with no Django endpoint or React view.

The unit of work is an **arm**: one pain site crossed with one hemisphere's amplitude. Arms are
fitted independently and never blended. The two sides are usable on different epoch subsets and the
LEFT is the sparser one — in the 86-epoch RCS08 warm start both amplitudes are recorded on every
epoch, but the left is above 0 mA on 59 and the right on 71 (21 epochs run the left off with the
right active, against 9 the other way), giving 54 fitted epochs on the left arm and 63 on the right.
`routines/plots.py` `build_context` takes `hemisphere=` and `primary_item=`, derives the amplitude
column from it, refuses a missing column rather than substituting, and stamps hemisphere and outcome
onto every figure's provenance line. Four arms (left_leg / back × Left / Right) produce 20 figures.

**Four stale or inconsistent constants in `plots.py` were poisoning every output, now removed.**
`INCUMBENT_EPOCH` and `INCUMBENT_XY` were independent module constants that had drifted apart *and*
gone stale: the epoch pointed at 50 (2025-11-01, 110 Hz / 1.2 mA) while the coordinates named
55 Hz / 1.6 mA, belonging to neither that epoch nor the setting actually in force (epoch 102,
2026-08-12, 55 Hz, 3.5/3.0 mA). Every J was therefore referenced to the wrong incumbent. Both are
now `None` by default and **derived from the design matrix** (most recent `t0`), which makes the pair
self-consistent and staleness impossible; they remain as explicit overrides only. Three figure
annotations additionally hardcoded the `55 Hz / 1.6 mA` label text while their markers used the
derived value — all three now read the derived coordinates.

`AMP_GRID` ran 0.8–4.0 mA and so **could not represent the July–August 2026 escalation**, which
delivered up to 4.8 mA: the highest settings actually delivered fell outside the search space, where
the surrogate could neither score nor propose them. Now 0.0–5.0 mA (0.0 because a hemisphere
genuinely runs at 0 mA in this record). `WASHIN_MIN` was 5.0 and is now 1.0 (the PI-declared 60 s
window); `DATA_HORIZON` now defaults to a string containing `UNDECLARED` so a stale horizon can
never be silently stamped onto a figure — the caller must pass the true one.

Also fixed: panel c of fig3 used a fixed y-floor of −1.35, which clipped the running-best trace off
the bottom of the axis on arms whose best J goes lower (54 of 132 points on left_leg__Left, whose J
spans −1.96 to +3.84). Limits are now data-driven with headroom added above for the legend only.

`StimOptimizer/tests/test_pipeline.py` is new (8 tests) covering incumbent derivation, per-hemisphere
column selection, refusal of an unknown or missing hemisphere, grid coverage of the delivered range,
labelled provenance defaults, and that an unfittable arm is recorded in `manifest["skipped"]` rather
than silently dropped. 54 tests pass **on a local run** (`PYTHONPATH=. python -B -m pytest
StimOptimizer/tests`), not through the bridge suite.

**Standing caveat unchanged:** no arm's optimum is resolved at one posterior SD
(`optimum_resolved` False for all four; signal-to-uncertainty 1.43–3.70) and the safe set is
non-contiguous in amplitude on every arm. Every selected cell is exploration-led (fraction above
0.5 throughout), but the magnitude is NOT uniform across arms and must not be quoted as a single
number: left_leg__Left 0.959–0.994, back__Left 0.938–0.999, back__Right 0.939–0.979, but
**left_leg__Right 0.565–0.833** — the right-hemisphere left-leg arm carries appreciably more
exploitable signal than the other three. Read the per-arm `stimopt_batch_<arm>.csv`, not a summary
figure. These figures are built to show that a recommendation is not supported, not to produce one.
The randomised within-visit ordering change remains the prerequisite.

On fig1's headline: a grid minimum below zero IS predicted better than the incumbent in the mean,
so the old hardcoded title "Nothing on the grid is predicted better than the incumbent" was false
on three of four arms. `_incumbent_verdict()` now derives the wording — it reports "predicted better
but NOT resolved: gain X < posterior SD Y" when the gain is smaller than the optimum's own posterior
SD (true for left_leg__Left 0.46 < 1.01, left_leg__Right 0.25 < 1.07, back__Left 0.37 < 0.64), and
only claims nothing is better when the minimum is genuinely non-negative (back__Right, +0.749).
`_amp_label()` likewise derives the y-axis label from `ctx.meta["hemisphere"]`; it had been
hardcoded to "Left-hemisphere amplitude" in five places, so every right-arm figure contradicted its
own provenance stamp and its own incumbent marker.

**New module: `BRAVO/modules/StimOptimizer/` — Bayesian optimization of stimulation parameters
(2026-08-29, untracked).** Library mode, no Django endpoint or React view, mirroring the staging the
Biomarkers module used. Searches (frequency, left amplitude) on a discrete grid with a Matern-3/2 ARD
GP over a composite pain objective, under a separately modelled safety GP, with a parallel
pairwise-probit preference GP. `OBJECTIVE_SPEC.md` is a pre-registration and carries a dated amendment
log — read it before changing any threshold. No torch: the grid is a few hundred cells so the
acquisition is evaluated exhaustively and scikit-learn's `GaussianProcessRegressor` supplies the
kernel with per-observation noise. 35 tests pass (verified against fresh bytecode with `-B`, after a
docstring-splitting SyntaxError meant an earlier "passing" run had used a stale `.pyc`).

**GOTCHA, high impact: the Percept JSON carries stimulation amplitude in TWO different places, and a
parser that reads only one of them silently returns an incomplete record.** This is a schema issue, not
a missing-data issue: the JSONs contain the full amplitude history and are the canonical source.

- **Legacy schema.** `Groups.{Initial,Final}[].ProgramSettings.{LeftHemisphere,RightHemisphere}
  .Programs[]`, with the delivered amplitude in `AmplitudeInMilliAmps`, pulse width in
  `PulseWidthInMicroSecond`, and rate at the group level in `ProgramSettings.RateInHertz`.
- **BrainSense schema.** When a group is configured for sensing, there are **no hemisphere keys at
  all**. The per-hemisphere program moves to `ProgramSettings.SensingChannel[]`, one entry per
  hemisphere identified by `HemisphereLocation`. The delivered amplitude is
  **`SuspendAmplitudeInMilliAmps`**; `PulseWidthInMicroSecond` and `RateInHertz` sit on the channel
  (not the group); per-contact amplitudes are in `ElectrodeState[].ElectrodeAmplitudeInMilliAmps`;
  `UpperLimitInMilliAmps`/`LowerLimitInMilliAmps` are the programmed bounds; and
  `Upper/LowerCaptureAmplitudeInMilliAmps` plus `AdaptiveTherapy` carry the closed-loop configuration.

Both schemas appear throughout the record and the split is **not** a date cutoff — of 1088
active-group hemisphere records from `Groups.Final`, 681 use the sensing schema and 407 the legacy one.
It is also **not** a home-versus-clinic distinction: both schemas occur in both session types. What
happened for RCS08 is simply that by July 2026 every active group was sensing-configured, which is
expected once closed-loop deployment is under way. Read both schemas (see
`StimOptimizer.routines`-adjacent `group_settings()` pattern) and prefer `GroupHistory` alongside
`Groups.Final`, because the dated `GroupHistory` snapshots capture between-visit changes that the
per-session records miss — including them raises the epoch count from 73 to 102.

An earlier revision of this entry claimed the JSONs truncate amplitude and directed readers to the
PDF session reports instead. **That was wrong and is retracted.** It came from a parser that read only
the hemisphere keys, so sensing-configured groups looked empty. The PDFs are a valid cross-check: on
439 sessions where both sources describe the same group and hemisphere, amplitude agrees in 98.4% of
cases, pulse width and rate in 99.5%. The apparent "extra" 5.0 mA level in the PDFs was an artifact of
comparing active-group-only JSON records against all-group PDF records — the 5.0 mA belonged to Group
B on 24 sessions in July-August 2025, and Group B was not the active group in any of them.

Two real traps if you do use the PDFs: the filename stamp is LOCAL clock while the JSON `SessionDate`
field is UTC (a seven-hour offset that reduces a naive join to 9 of 1177 rows), and the PDF text must
be parsed line-by-line — a `(?:.*?\n){0,4}?` construct under `re.S` backtracks catastrophically and
hangs for over ten minutes.

**Programmed limits ARE usable as safety anchors.** `UpperLimitInMilliAmps` exceeds the delivered
amplitude in 96.5% of legacy-schema records (median headroom 0.60 mA) and 58.3% of sensing-schema
records (median 0.30 mA), so it is a genuine clinician ceiling rather than a copy of the current
amplitude. A single June record where the two were equal had earlier been over-generalised.

**Pulse width is asymmetric between hemispheres** in about 90% of timestamps — left 60 µs with right
160 µs is the most common pairing (619 timestamps). Any instruction to "pin pulse width" must name a
value per hemisphere.

**RCS08 warm start and the corrected scientific reading.** From the canonical dual-schema JSON parse
including `GroupHistory`: **102 setting-change epochs, 86 with data, 56 with n >= 3, 746 usable
reports** at the 5-minute wash-in. (A single-schema parse gave 60/45/33/678 and a PDF-based
reconstruction gave 73/67/51/747; both are superseded.) Effective sample size for a
settings-level model is the **epoch**, not the report: ICC 0.286, design effect 5.02. Wash-in
exclusion is **5 minutes**, not 24 h — PI reports a demonstrated sub-5-minute response, which recovers
81 reports and 10 epochs. The previously missing June-August window was an **amplitude escalation, not
a plateau**: 55 Hz throughout with left/right 2.0/1.6 -> 3.5/3.5 -> 4.0/4.0 -> 4.5/4.5 -> 4.0/3.0 ->
3.5/3.0, pulse width 60 -> 100 us, cathode ring 1 -> ring 2. The five best epochs with n >= 5 are all
from that period. **Current incumbent is epoch 73: 55 Hz, 3.5 mA left / 3.0 mA right, 100 us, ring 2,
n = 18, NRS 6.56** — not the 55 Hz / 1.6 mA setting the truncated record implied. The surrogate finds a
real amplitude dose-response (length scale 3.81; posterior mean at 55 Hz falls from +0.803 at 0.8 mA
to +0.034 at 4.5 mA, then flattens, matching the clinical back-off from 4.5), and the highest-EI cells
are 55 Hz at 4.4-5.0 mA. An earlier "flat in amplitude, go to 40 Hz" reading was an artifact of the
truncated data. Amplitude is confounded with time in the *opposite* direction to what the JSONs
implied: days versus left amplitude +0.39 (p = 0.001), days versus NRS -0.61 (p < 0.0001).

**PRO refresh path.** `scripts/dump_chronic_pros.py` is not mounted into the container; stage it into
`BRAVO/_agent_bridge/` (which is live-mounted) and run via the bridge with `DUMP_OUT` set to a fresh
directory so the prior dump is not clobbered. The refreshed dump ships a `_pro_time_utc` column —
use it rather than re-deriving the California-to-UTC conversion (verified identical to a manual
PDT/PST conversion across 694 overlapping rows).

**Documentation: v3.1.0 README fully corrected (2026-06-29, `621bc35`).** Six critical fixes applied to
`README_BIOMARKERS_AND_DEPLOYMENT.md` in response to user feedback: (1) Added `MedtronicIndefiniteStream`
to data-sources table (line 57) — the indefinite-duration TD recording type was core but missing from docs.
(2) Rewrote TD-transform extent description (line 168) — changed from "fixed ±30 s centered" to "selectable
via MatchExtentSec slider (default 30 s; range 3–300 s) controlling TD signal quantity per pain report."
(3) Corrected PSD-bridge band integration (line 179) — was "linear interpolation to point sample," now
"integrates power across ±2.5 Hz band (5 Hz total width)" per `device_psd_band_power` code at line 3186.
(4) Added "Pain Metric Configuration" subsection (new §1.5a, line ~149) documenting support for VAS/NRS/NPQ
/composite scales, configurable per site via `_resolve_biomarker_metric` in `bravo_service.py`. (5) Created
new "Mixed-Model & Forward-Windows Workflow" subsection (§1.7b, line 287) describing temporal validation,
fold-based CV, and per-contact ranking that precedes final deployment selection. (6) Added "Biomarker
Discovery Workflow (Visualization)" diagram (§1.3b, line 99) showing the 5-phase pipeline from ingestion
through deployment ranking — parallel structure to the existing Deployment module diagram (§2.3). README
expanded 759 → 896 lines; all 6 items now grounded in code with line-number citations. Committed and pushed
to `PS_closedloop_deployment` branch. No code changes; documentation only.

**Matching two-window modality split + cache-only scan path (2026-06-28, `b06b0e2`).** The PI flagged
that two time windows in the UI governed two DIFFERENT matched sets that did not cascade: the main
`MatchToleranceMin` slider drove the pooled-PSD binarization population (up to 2 h), while ρ/AUC/scatter
were computed on a separate LSB-spectrum window hard-locked to ±30 s (TD) / ±120 s (PSD) — so widening
the slider grew the binarization histogram but had ZERO effect on the biomarker statistics. Resolution
(Option B, split by modality): in `availability.live_lsb_spectrum_match`, **`tol_s` (the main slider) is
now the eligibility radius for BOTH TD and PSD**; **`td_quantity_s` (the repurposed extent slider) is a
QUANTITY-OF-SIGNAL knob** — after TD eligibility is decided by `tol_s`, each PRO keeps only the
`round(td_quantity_s/3)` NEAREST 3 s tiles (|Δt|-ranked, before/after agnostic) and medians them; PSD has
no quantity cap (median over every event within `tol_s`). The raw 3 s-tile cache is non-overlapping
(`availability.py` ~line 83 tiles by raw sample index), so 30 s ⇒ nearest 10 tiles exactly. Back-compat
shim maps the legacy `extent_s`/`psd_tol_s` kwargs. `bravo_service`: the cache matcher is now the ONLY
scan path (legacy real-time `per_pro_lsb_spectrum` recompute retired in the scan; still feeds the timeline
modeled markers — a separate viz, intentionally left). It passes `tol_s=match_tol_min*60`,
`td_quantity_s=match_extent_s`. New data auto-extends the cache (signature already keys on recording
StartTime/channels/sample-count). **Count consistency:** per-channel `n_high/n_low/n_excluded` were
counted over pooled-PSD epoch rows (`chan_fin` from `psd[:,ci,:]`) while `n_td/n_psd_bridge` counted the
LSB subset — diverging badly after the change (1190 vs 419). Now `chan_fin`/the split are counted over
DISTINCT PROs carrying a resolved LSB tier, so `n_high+n_low+n_excluded == n_td+n_psd_bridge == n_channel`
(also fixes the long-standing per-channel dash bug — those fields now reach the response). Frontend:
removed the Legacy/Live toggle (cache always on, `useLiveMatching` pinned true), extent slider relabeled
"Time-domain signal per rating (N s ≈ nearest N/3 tiles)" with max raised 120→300 s, two-window caption,
pooled line now SUMS the per-channel distinct-LSB counts (was `sfi.binarization`, a different unit), and
the match-offset full range "(range lo to hi min)" appended to the "X of Y pain reports … median match
offset" line only. Live verify on 2e3c75c0: main slider 2→120 min grows matched PROs 258→927; TD-quantity
30→120 s scales `n_td_used` ×4 with PSD untouched. New tests `test_live_match_td_quantity_caps_nearest_n_tiles`
+ rewritten reuse test; **container suite 261/261**. Frontend chunk `434.9f4cba51`, main `87e35786`.
*Hotfix `b239e57`:* the offset-range edit blanked the Biomarkers module — the hoisted `rangeTxt`/
`offsetSummary` read `counts.min_abs_offset_min` while `scanModel.counts` is still null on first paint;
added `counts &&` guards, rebuilt (chunk `434.861dc283`, main `8fa51c07`). PI confirmed it works.

**Biomarker accuracy remediation — high-priority audit fixes (2026-06-28, `7ce588d`).** Four of the
high-severity items from the stress-test audit (`remediation_action_plan.md`, artifact `488a4d02`).
**R1/A1 signed AUC:** `_cv_logistic_auc` keeps its notebook-parity fold (`max(auc,1-auc)`, always ≥0.5),
but `spectral_feature_importance` now also emits per-band `auc_signed` — the same CV-AUC oriented by the
band's correlation sign, so a null band reads ~0.5 and a beta-SUPPRESSION band reads <0.5. The scan figure
plots `auc_signed` on y2 over `[0,1]` with a dashed 0.5 chance line (was folded `auc` over `[0.4,1]`).
**R11/A7 binarization bias:** `_binarize_labels` gained a `rating_group` arg so the tertile cut is computed
on the UNIQUE-PRO distribution, not the pseudoreplicated per-sample vector (a rating matched by k windows
was pulling the cut toward recording-dense pain states; max_reuse=18 here). **R2/A2 per-contact biomarker:**
each channel now carries `selected_band` {center_hz, rho, auc_signed, q, sign, direction, fdr_significant} —
best FDR-significant band else max-|ρ| — and the frontend renders a per-contact best-band table (band AND
direction are contact-specific: RCS08 R 1⁻3⁺ VIM beta ELEVATES, GPi contacts SUPPRESS). **R12/F5 montage
generalization:** `_MAIN_BIPOLAR` is now derived by `_build_main_bipolar()` from `_DEFAULT_BIPOLAR_PAIRS ×
_HEMISPHERES` with a `BRAVO_MAIN_BIPOLAR` env override; default reproduces the original six pairs. New tests:
`test_auc_signed_reflects_correlation_direction`, `test_binarize_cut_invariant_to_sample_multiplicity`,
`test_selected_band_is_per_contact_and_signed`. **Frontend eslint gotcha (reconfirmed):** a component-body
`const … = arr.map((c) => {…})` retroactively trips `react-hooks/rules-of-hooks` (flags earlier hooks as
conditional) even though Babel parses it — the per-contact table had to be built as a self-contained JSX
IIFE, and the signed-AUC y-array inlined (no `const` in the trace callback). R3 (FDR rigorous-count headline)
was found already satisfied in code+test. **R5/R6/R7/R8/R9/R10/R13/R14 remain** (coverage doc, tolerance-regime
label, bridge single-process probe, band-grid params, min_per_group guard, magic-constant config, calibrated-band
gate, per-participant k). NOTE: bridge watcher down → container suite NOT run; HUP workers next session.

**Binarization-hover zero-TD-count fix + reuse-modeled preview (2026-06-28, `edfd0b5`).** Two
frontend bugs in the binarization-preview histogram. (1) ZERO TD COUNTS: the hover's per-source line
("X TD · Y montage · Z event") always showed `0 TD`. Root cause: `binarizationModel.srcBucket`
classified a sample's source by the literal substring `"td"`, but the backend `_psd_sample_index`
(bravo_service.py:1272) stamps time-domain samples `"BrainSense streaming"` / `"Indefinite stream"` —
neither contains "td" — so all 950 TD samples (624 indefinite + 326 streaming for 2e3c75c0) fell into
the montage bucket and `by_source.*.td` stayed 0. FIX: `srcBucket` now maps `td`/`stream`/`indefinite`
→ td (montage/event unchanged). (2) REUSE TOGGLE INERT ON PREVIEW: the preview is a CLIENT-SIDE replica
(`computeMatchedScanModel` over `availability.psd_scan_index`) with no reuse concept, so `AllowWindowReuse`
moved only the backend scatter, never the preview histogram. FIX: added an `allowWindowReuse` branch that
matches each sample to EVERY rating within tolerance (K-closest per rating per channel; `prior` stays
one-directional), preserving uncovered samples as unmatched; `pct_psd_used` uses DISTINCT matched samples
under reuse so it stays ≤100%. Verified by Node unit test (strict TD=2 not 0; reuse lifts n_matched and TD
count; pct≤100). Frontend-only — no worker reload, just a browser refresh. GOTCHA: the preview matcher is a
deliberate replica of the backend pooled match; if backend match semantics change, this must change in
lockstep or preview vs committed counts diverge.

**Montage device-PSD coverage + window-reuse toggle (2026-06-28).** The raw LSB cache routed
montage/survey recordings only through the TD-transform path (×352.62) and treated them as having "no
PSD to bridge" — but every `MedtronicBrainSenseSurvey`/Montage carries a full device PSD in
`Descriptor.MedtronicPSD[]` (`LFPFrequency`/`LFPMagnitude`, 100-pt, per contact; the "PSD snapshot from
montage" the timeline hover shows). That spectrum was ignored by the LSB cache. FIX: new
`bravo_service._montage_psd_lsb_blocks()` extracts each `MedtronicPSD` entry → `{channel,t,freq,power,
source="Montage PSD"}` (channel via `SensingElectrodes`+`Hemisphere` → `_EVENT_SENSE_CONTACT`/
`_canon_channel`); `availability.raw_lsb_spectrum_cache(montage_psd_recordings=…)` folds them into the
PSD family via `device_psd_band_power × LSB_PER_DEVICE_PSD≈73.63`. CALIBRATION VALIDATED: paired
same-recording device-PSD LSB / TD-transform LSB = median 0.993, IQR [0.966,1.020] in 8–30 Hz (n=204) —
LFPMagnitude is the same linear-µV onboard-FFT unit as patient-event FFTBinData, so the bridge constant
is correct (an earlier unpaired 1.5× gap was time-coverage mismatch, not calibration). RESULT
(2e3c75c0): `ZERO_THREE_LEFT` PSD windows 15→232 (+217); live API `n_pro_psd` 86→110 (+24 PROs reach the
bridge tier that previously had no LSB), `n_pro_td=123` unchanged (TD still preferred). New
**`AllowWindowReuse`** request param (default OFF): when ON, `live_lsb_spectrum_match` matches each
window to EVERY PRO whose extent covers it (vectorized `_windows_in_extent`) instead of nearest-only —
trades the no-reuse independence guarantee for sample size; default preserves strict one-window-one-PRO.
Per-modality non-reuse (a montage's TD tile and its device-PSD window can serve two different PROs) holds
in BOTH modes because TD/PSD match in separate passes. 4 regression tests added
(`test_per_pro_lsb.py`), suite 257/257. Backend committed `b6f660f`; frontend `AllowWindowReuse`
toggle (No-reuse/Allow-reuse, near the LSB-matching control) committed `d2f0d8a`; both pushed. Workers
HUP-reloaded so the montage coverage fix is live. NOTE: the live-matching caption is built as a plain
string variable, NOT a JSX-embedded nested-ternary template literal — the latter makes the react-hooks
eslint pass mis-scope every later hook as conditional and fails `npm run build`.

**Binarization cut control: in-plot drag → two-handle range slider (2026-06-28).** The percentile
cuts were set by dragging dashed lines INSIDE the histogram (`BinarizationPreview.js`), via Plotly
`edits.shapePosition`. That boolean has no per-axis constraint, so a line drag moved in x AND y and
could resize/tilt the line — the cut lines were draggable/resizable in all directions. REPLACED with a
single MUI range slider (two handles, low + high) ABOVE the histogram; the in-plot lines are now
DISPLAY-ONLY dashed notches that track the slider (shapePosition:false, relayout drag handler removed,
dead `valueToPercentile`/`cutShapeIdx`/`draggableCuts` deleted). Slider drives the same
`percentileLow/High` state and promotes a tertile preset to "percentile" on first move (disableSwap +
≥1-pct gap so cuts never cross; handles colored LO/HI by data-index). Parent (`index.js`) chips +
help text updated from "drag the dashed lines" to "range slider above the histogram". Frontend rebuilt
(main.8cf360ff.js). NOTE: this supersedes the earlier-this-session "draggable cut-lines in Plotly"
deliverable — direct in-plot dragging was the thing being removed.

**`vas_min` KeyError regression FIXED (2026-06-28).** Any non-default `LabelMetric` (vas, mpq_sum,
etc.) crashed `run_for_participant` with `Biomarker computation error: 'vas_min'` (the card rendered
the "upload a Percept session / configure REDCap" fallback). ROOT: the scatter-dedup `rating_group`
injection added in 2daf80e (`pipeline.run_timedomain_branch`) read `pro_df[label_col]` where
`label_col = f"{label_metric}_{label_reduce}"` (= "vas_min") — but `pro_df` is the RAW REDCap frame
whose columns are bare metric names (`vas`/`nrs`/`mpq_sum`); the `_min`/`_mean` suffixes exist only on
`session_df` (adapter.align_pros), so ANY metric (including default `nrs`→"nrs_min") would hit this
read. (Why the default path didn't crash for every user was NOT traced — possibly the dedup block was
skipped or `pro_df` carried suffixed columns in some entry paths; unverified.) FIX: map session labels
back to PRO rows via the bare `pro_df[label_metric]` column (pd.to_numeric-coerced), guarded with
`if label_metric in pro_df.columns` (else rating_group stays -1 → no dedup, no crash); invariant lookup
hoisted out of the per-epoch loop. Verified through the bridge on RCS08 with `LabelMetric=vas`: the
request that previously errored now returns message='', 6 channels (the "after" half; the pre-fix
KeyError is established by code inspection, not re-run). Suite 253/253.

**Phase 1 + 3 + 4a + scatter dedup bug fix (2026-06-28, COMMITTED 2daf80e).**
- **Scatter dedup bug FIXED.** TD-only channels (e.g., L 0⁻2⁺) were not deduplicated because `rating_group` was missing from the TD detail dict. User reported n=90 in title but only ~14 visible points. Root: `compute_psd_pain_correlation()` returns no `rating_group`; only `build_pooled_detail_from_matrix()` (PSD path) had it. FIX: inject `rating_group` in `pipeline.py run_timedomain_branch()` by mapping each session's matched PRO to its index in pro_df. Dedup now works for both TD and pooled paths.
- **Live matching wired in (Phase 4a).** `live_lsb_spectrum_match()` assigns each raw 3 s window to NEAREST PRO (TD ±30 s, PSD ±120 s, no-reuse by construction). Toggle `UseLiveMatching` (default OFF for A/B), param `MatchExtentSec` (3–300 s). FDR naive 401 vs legacy 428 — no-reuse doesn't collapse over-reporting (root: MaxPerRating on separate PSD match). AUC unchanged.
- **Phase-1 frontend: toggle + draggable histogram + hover.** Toggle (Legacy/Live-cache) + extent Slider + stats readout. Draggable cut-lines in Plotly (replace disconnected sliders with chips). Histogram hover: day-count pinned top, then TD/PSD source splits.
- **Indefinite-stream mislabel (Phase 3).** 103 IndefiniteStream recs mislabeled BrainSense — decoded payloads carry no type field. FIX: stamp `RecordingType` from DB onto dict in `_decode`; discriminators now key off `RecordingType=='MedtronicIndefiniteStream'`. Index: `{BS 326, Indef 624, Montage 1174, Event 3119}`.
- **Text revision (Phase 3).** log10→raw + Pearson→Spearman ρ (rank-invariant); AUC fit stays log10 internally. Slider relabel: "Max LSB samples per Pain rating". FDR annotation reworded (MaxPerRating, not LSB reuse). Power-domain section removed. Feature-importance height +25 %; super-title spacing fixed.

---

- **Scatter/violin overplot fixed (root cause).** In LSB mode the click-scatter plots `x=log10(modeled
  LSB)` (modeled PER RATING) vs `y=PRO rating`, so every matched PSD sharing a rating collapses onto
  the same (x,y) — overplotting, not dropped points — while the title summed `n_grp` over ALL matched
  rows (inflated headline; `len_x` could even exceed `n_channel`). `spectral_feature_importance` now
  DE-DUPLICATES the scatter to one observation per distinct `rating_group` (`dedup_by_rating`,
  first-wins); `n_grp` derives from the de-duped index so `nlo+nhi+nmid == n_obs == len(x)` (rendered
  dots == headline n). `n_obs` is taken AFTER the `max_scatter` cap (cap-parity edge fixed). New
  scatter payload: `n_obs/n_distinct/n_rows/dedup_by_rating` + per-band `n_td/n_psd`; new per-channel
  `n_high/n_low/n_excluded/n_td/n_psd_bridge`. Bridge-verified at 25.5 Hz on all 6 channels.
- **Hover-N audit (all traces).** 8 count sites; 3 misreported (spectrum curve legend+hover ~L303,
  scatter title ~L556, violin caption ~L584), all printing `n_channel` (matched PSD ROWS) where the
  count of independent rendered LSB vectors belonged — inflating 130–925 (R 0⁻3⁺ claimed n=1026 vs
  ~101 vectors). The cited "AUC N=98 == Pearson N=98" is ONE `n_channel` echoed onto both the r and
  AUC traces via `<extra>%{fullData.name}</extra>`; `ch.n_r` is rendered nowhere. New label spec (PI):
  report only TWO values everywhere in the spectral panel — `(<n_td> TD · <n_psd> PSD)`.
- **UI text.** `index.js`: legacy Time-/Power-domain `summaryLine()` prose (and orphaned `fmt`/`fmtP`)
  replaced by a concise per-channel high/low/excluded + TD/PSD summary. `BiomarkerAnalytics.js`: Full
  Spectrum caption 6 paragraphs → 2 lines; mixed-effects `ValidationReadout` enlarged+bolded (verdict
  badge 14px, 16px OR/CI/p headline, bold stim verdict + LRT p). `BiomarkerDataTimeline.js`: stale
  green (`LSB_GREEN #2CA02C`) glyphs removed from the legend — no rendered trace is ever green (real
  LSB colored by sensing Hz / steel-blue); recolored to `LANE_NEUTRAL` (DIM_GREY), 9→7 legend rows.
- **Raw match-agnostic LSB cache (decouple, half 1 of 2).** New `availability.raw_lsb_spectrum_cache()`
  tiles the WHOLE recording into 3 s non-overlapping windows (`RAW_LSB_WINDOW_SECONDS=3.0`), full
  0–100 Hz, `[W×C]` per channel + per-window timestamps, **NO PRO coupling** (cache key = channel +
  recordings + centers). TD tiles by wall-clock sample index (gap-correct) → validated 1 s-Hann/256-FFT
  median ×352.62; PSD-bridge one window/event ×73.63, calibrated mask gated [7.8,30]. Each window
  source-tagged (Montage/Indefinite/BrainSense for TD; Patient event for PSD) via `TD_PRODUCT_SOURCE_
  LABEL` for the future hover breakdown. LSB-source provenance chip added to the spectral panel.
  Bridge-verified on RCS08 (60 528 TD + 445 PSD windows on ZERO_THREE_RIGHT; saturation/missing
  rejection unit-tested). **DEFERRED to a focused follow-up (PI: "cache layer first, matching next
  session"):** wiring the cache into `bravo_service`, LIVE matching (median over a configurable ~30 s
  rating-centered extent, TD preferred within window), the no-LSB-reuse-across->1-PRO rule (cuts
  today's ~79.7 % pseudoreplication — report r/AUC before/after), and the binarization-histogram hover
  source breakdown. The old `per_pro_lsb_spectrum` PRO-coupled path stays live until then.
- Per-session detail: `SESSION_HANDOFF_2026-06-28_biomarker_count_ux.md`.

**Audit [5] (server-side cut-point) + [42] (LSB op-point chip) + Bug 1–4 committed (2026-06-28). Suite 253/253.**
- **Bug 1–4 landed:** the prior event-PSD-resolver + frontend tier/title changeset was committed
  (`f6849c4`) and pushed to origin. The PI reversed the no-agent-commits rule; the `bravo-session-rules`
  skill now carries **Rule 4 (commit + push after a verified changeset)** instead. Git identity
  `Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>` passed via `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env
  vars (sandbox `.git/config` is write-protected, so `git config user.*` fails).
- **[5] — full-array cut-point.** `deployment_roc` downsampled `fpr/tpr/thr` to `max_points`, and the
  ROC panel re-solved the operating point in-browser on those downsampled arrays — so the displayed
  cut-point (incl. the Youden default lifted to Phases C–E) could drift from the backend's exact
  optimum. New `analytics._solve_roc_operating_point(...)` solves youden/f1/cost on the FULL arrays;
  `deployment_roc` ships `operating_points={youden,f1,cost:[{log_cost,cost_ratio,...}]}` (cost grid =
  the UI slider's −3..3 step-0.25 = 25 pts). Frontend `pickServerCutpoint()` snaps to it, falling back
  to the live `solveCutpoint()` only for older payloads. Legacy `operating_point` unchanged and now
  provably == `operating_points['youden']`. +4 tests.
- **[42] — op-point chip + histogram LSB.** `LsbPowerPanel` renders an operating-point chip (rule +
  sens/spec + oriented-log-power cut + `→ ≥/≈ X LSB`) and lifts the resolved device LSB to the parent
  (`index.js` `lsbThreshold` state); `DeploymentRocPanel`'s feature-histogram cut line now annotates
  the resulting `≥/≈ X LSB` beneath the log-power cut. Closes the "two numbers connected only by
  prose" gap. UI-only (LSB value already came from `/queryLsbPower`). Frontend rebuilt.
- Per-session detail: `SESSION_HANDOFF_2026-06-28_audit_5_42.md`.

**Bug 1: Event-PSD channel resolver + Bug 2: Modeled-LSB symbol fix (2026-06-28, UNCOMMITTED). Suite 249/249.**

*Bug 1 root cause:* `_event_block_channel` guessed Right→`ZERO_THREE` / Left→`ONE_THREE` statically for blocks lacking a `SenseID`. On RCS08 84% of the 3,119 event PSD blocks (2,635/3,119) had no `SenseID`, and 86% of all blocks are Right-hemisphere, so ~86% of all event PSDs were dumped onto **R 0-3** — contaminating that channel's binarization scan pool and starving others. This is a biomarker-accuracy bug, not just display.

*Fix:* Replaced the static guess with an **active-sensing resolver**:
- `_build_sensing_config_index(decoded_recs)` — builds a per-hemisphere sorted `[(epoch_s, channel)]` list from `BrainSenseTimeDomain` + `BrainSensePowerDomain` records (single-channel sessions only; IndefiniteStream and montage sweeps — which sense all pairs simultaneously — are excluded by a `len(chans)==1` guard).
- `_build_sensing_config_index_from_rows(psd_rows)` — companion builder for the cached-assembly path where decoded dicts aren't available (builds from flat Welch rows, TD-streaming source only).
- `_resolve_event_channel(hemi_key, sense_id, t_event, sensing_index)` — priority 1: SenseID (authoritative); 2: most-recent prior config in 90-day window; 3: nearest-after config; 4: None (skip, never guess).
- `_EVENT_HEMI_DEFAULT_CONTACT` fully removed from all production paths. `_event_block_channel` reduced to a SenseID-only shim for backward compat.
- Wired into all 5 call sites: `_event_psd_rows`, `_event_psd_index`, `_event_psd_lsb_blocks` → availability timeline tick path, binarization scan pool (both `_assemble_psd_rows_cached` and the warm-cache path), and the deployment scan path.
- Sensing index sources: streaming TD only for `_assemble_psd_rows*`; TD + PowerDomain for the availability payload where `powerdomain_list` is in scope.
- Architecture: channel assignment stays at **analysis time** (not ingestion) — new JSONs automatically benefit; richer index as sessions accumulate.

*Live RCS08 validation:* Before → 484/3119 (16%) routed via SenseID; After → **3119/3119 (100%)** routed. L 1-3 went from 34 → 407 events. 421 bilateral events (both L+R) resolved to correct independent contacts (R=0-3 + L=1-3 dominant; R=0-3 + L=0-3 in 14 events when Left was sensing 0-3 that session). 0 unresolved.

*Bug 2 root cause:* The lane-level modeled tier used `symbol: "diamond-open"` for ALL methods. The per-rating tier already distinguished `td_transform→circle-open` / `psd_bridge→diamond-open` via `TIER_SYMBOL` but the lane tier did not, so TD-modeled points were invisible behind PSD-bridge diamonds.

*Fix (BiomarkerDataTimeline.js):* Lane-level modeled tier now partitions each frequency group by method and pushes two traces: `circle-open` for `td_transform`, `diamond-open` for `event_psd_bridge`. Non-binMode legend split into two entries (one per symbol). Redundant `matched ≥1 PSD` / `no neural match` pain-rating swatches removed from binMode glyph key (binarization mode already communicates this via color encoding). `nLegRows`: binMode 7→5, non-binMode 8→9.

*Bug 3 (BinarizationPreview.js line 346):* `scanModel` was missing from the `useEffect` dep array. `proIdxByBin` is computed inside that effect from `scanModel.samples`, but since `scanModel` wasn't listed, it went stale after any scanModel rebuild (e.g. `matchDirection` change) that didn't also change another listed dep. Fix: `scanModel` added to dep array. The 187/106 discrepancy the user saw was this stale render — `proIdxByBin.low` (unique rating indices per bin, a Set) and `counts.n_low` (total matched PSDs) are legitimately different units and both correct; the stale dep caused one to be from a prior model.

*Bug 4 (BiomarkerAnalytics.js):* (a) Scatter title showed `sc.x.length` (capped at max_scatter=400) rather than `ch.n_channel` (true per-channel matched count). Title now shows `ch.n_channel` with ` shown: N` suffix only when the scatter was subsampled. (b) When `matchDirty` (slider window changed since last scan run), the scatter title now shows `· scan at prior window` inline. `matchDirty` prop threaded from `index.js → BiomarkerAnalytics → SpectralFeatureImportance`.

*Bug 4 null-guard addendum (BiomarkerAnalytics.js):* cap-disclosure condition `nShown < (ch.n_channel || nShown)` was always false when `ch.n_channel` is null. Fixed to `(ch.n_channel != null && nShown < ch.n_channel)`. Frontend rebuilt.

*Tests added (9):* `test_resolver_returns_none_when_no_sense_id_and_no_index`, `test_resolver_uses_sense_id_when_present`, `test_resolver_picks_nearest_prior_config_from_index`, `test_resolver_falls_back_to_nearest_after_when_no_prior`, `test_resolver_respects_window_and_returns_none_when_too_far`, `test_resolver_excludes_all_pair_sweeps_from_index`, `test_resolver_left_hemi_key`, `test_build_sensing_config_index_accepts_power_domain_records`, `test_build_sensing_config_index_from_rows_basic`. Suite: **249/249 PASS**.

---

**Deployment modeled-LSB now pools ALL TD products, not just montage/survey (2026-06-28, UNCOMMITTED).**
The TIER-1 rewrite below wired the modeled-LSB helper correctly but the two **deployment** endpoints
(`band_lsb_and_power`, `deployment_summary`) only loaded montage/survey TD (`psd_list`,
`AVAILABILITY_PSD_TYPES`) and passed `td_recordings=list(psd_list or [])` — while the **exploration
timeline** feeds the helper the full TD superset (streaming `td_list` = `MedtronicBrainSenseTimeDomain`
+ `MedtronicIndefiniteStream`, PLUS `psd_list`). So any band the device only ever **streamed** (never
montage-swept) silently lost those TD samples from the deployable percentile-anchored threshold. Fix:
both endpoints now also load `streaming_td = _load_recordings(uid, TIMEDOMAIN_TYPES)` and pass
`td_for_modeled = streaming_td + psd_list` to `modeled_lsb_at_center`. Power-domain records and
unnamed/foreign columns are still excluded by the helper's fs/ChannelName guards; native-preferred
precedence unchanged; exploration timeline byte-unchanged. E2E on RCS08 ZERO_THREE_RIGHT: in-band
modeled pool **156 → 469** (335 streaming recs added = 232 BrainSenseTimeDomain + **103 IndefiniteStream**;
IndefiniteStream carries all 6 contacts so it adds a uniform +102 pts to EVERY channel and is the
DOMINANT streaming source for the 0-2/1-3 contacts), deployable p50 moves a few % (8.8 Hz 496.3→515.1,
26.4 Hz 102.5→105.4) — a real coverage gap, not a no-op. +1 test (`test_modeled_lsb_at_center_pools_streaming_and_montage_td`), suite **240/240**.
No frontend rebuild needed (only the modeled threshold's numeric value moved). Per-session detail:
`SESSION_HANDOFF_2026-06-28_all_TD_modeled.md`.

**Deployment LSB fallback → universal TIER-1 off raw TD; z-scored units bug fixed (2026-06-28, `09798f7` + build `e8a0d3f`).**
A cross-module LSB-consistency code review found a **CRITICAL units bug** in the deployment threshold
path: the ROC cut-point is a within-(channel,source) **z-scored log-power feature** (dimensionless,
frequently negative — built by `streaming_psd.build_pooled_detail_from_matrix`, `prelog=True`), but the
prior fallback fed it straight into `psd_lsb_model.estimate_lsb`, which expects a **linear µV²** band
power. A z≤0 clipped to 1e-12 (LSB≈0); a z>0 was silently misread as µV². This was the patient-facing
stim-threshold for any unsensed band. **Fix — one units-consistent modeled tier:**
- **New `availability.modeled_lsb_at_center(channel, center_hz, *, td_recordings=, psd_recordings=, half_hz=2.5)`**
  models the device-LSB line off the **RAW µV TD** the ROC was built from, **at the ROC's OWN band
  center** (transform `td_to_lsb` ×352.62; bridge `device_psd_to_lsb` ≈73.63 for PSD-only events), then
  the caller anchors a threshold by **RANK (percentile)** exactly like the native path — **no µV²↔LSB
  conversion of the cut-point**. Universal: covers any band the ROC can score, incl. high-gamma the
  montage never swept. **Honors the ROC center exactly (no `snap_freq` clamp)** — a 55 Hz winner converts
  at 55 Hz, not the 26.4 Hz top of the device sensing-bin table (snap is for timeline display only;
  catching this corrected a high-gamma threshold that was ~4× too high).
- **Deployment-only:** the helper only CALLS shared primitives; `lsb_series` and the Biomarker
  Exploration timeline are **byte-unchanged in behavior**. Both endpoints (`band_lsb_and_power`,
  `deployment_summary`) now source `modeled_thr` from the helper at the ROC center.
- **TIER-2 (frozen-model-on-cut-point) and the old TIER-3 are both gone.** `_modeled_lsb_threshold_estimate`
  is now a single modeled tier; fail-closed (`modeled_thr None → thr_estimate None`) only when there is
  genuinely no TD/PSD for the channel. `estimate_lsb` is **retained as a tested µV²→LSB utility (no
  production caller)** with a loud input-contract warning against z-scored/log/cut-point inputs.
- **Hardening:** channel-name guard now requires a named column matching the target (mirrors `lsb_series`);
  unnamed/extra columns (malformed packets) and power-domain records (`fs≤0`, e.g. ChronicBrainSense) are
  skipped — no cross-channel or units leak. `chronic_list` no longer passed to the TD tier.
- **Tests:** +9 net (8 helper-branch tests — named-match, foreign-channel exclusion, power-domain skip,
  malformed extra-columns, orientation, short-column, fail-closed, PSD band-gate/high-gamma — plus the
  restored `test_freq_extrapolated_guard_agrees_with_frozen_model`). Suite **239/239**.

> ⚠ This **supersedes** the conclusion of the entry below: the deployment fallback is **NOT**
> frozen-model-only. The frozen-model-on-cut-point step was itself the units bug and was removed; the
> deployment modeled threshold is now the raw-TD transform/bridge route, rank-anchored.

**welch256 / k=269 removal — deployment fallback now frozen-model-only (2026-06-28, `184ea74`+`fa2c416`).**
The Welch-256 PSD→LSB exploration backup and the `k=269` population constant were fully removed; the
deployment threshold path now converts the offline-Welch µV² ROC cut-point to LSB **solely via the
per-participant frozen PSD→LSB model** (`psd_lsb_model.estimate_lsb`), which is itself fit on the SAME
offline-Welch µV²→device-LSB mapping — so cut-point and converter share units (the principle: the
cut-point's own model converts it, not a bespoke scalar). Specifics:
- **Deleted DSP (no production caller):** `analytics.psd_band_to_lsb`, `welch256_density` (superseded by
  the CS-3 device-PSD bridge `device_psd_to_lsb`, k=73.63).
- **Deleted constant + converters:** `LSB_PER_UV2_VALIDATED` (269.0), `UV2_PER_LSB_VALIDATED`,
  `LSB_UV2_LOGLOG_SLOPE`, `lsb_from_uv2`, `uv2_from_lsb`. `LSB_UV2_SIGMA_FOLD` → renamed
  **`MODELED_LSB_SIGMA_FOLD`** (1.26, DSP-neutral; the ±1σ band on TIER-1/TIER-2 modeled estimates,
  still overridable by a frozen model's `resid_log_sigma_fold`).
- **Deployment fallback ladder (`_modeled_lsb_threshold_estimate`):** TIER-3 `validated_constant`
  population-constant last resort **DELETED**. When neither a native device threshold nor a fitted
  per-participant model entry exists, the modeled threshold is now **INDETERMINATE (fail-closed)**
  instead of a k=269 guess. The native-vs-modeled k=269 QC cross-check was deleted too (no frontend
  consumer; payload key `native_modeled_check` retained as `None` for API-contract stability).
- **Stale-label bug fixed (same pass):** TIER-1 `modeled_timeline` reported `k_effective=269` /
  "Welch256×269", but since CS-1 it reads straight off the transform×352.62 LSB timeline applying NO k.
  Payload now reports `k_effective=352.62`, `slope_b=None`, transform-route notes. Frontend
  `validated_constant` TIER_LABEL entry removed (tier no longer emitted).
- **Coverage note (audited):** removing TIER-3 only affects bands with NO frozen-model entry — i.e. any
  non-RCS08 participant, or RCS08 `ONE_THREE_RIGHT` (0 bands, `pooled_k=None`). All other RCS08 channels
  are covered by TIER-2. Suite 234→229 (net −5 from test removal/rewrite). The deployable number is
  unchanged in all covered cases (measured native threshold always wins; TIER-2 numbers identical).

**TD→LSB calibration + spectral unification (CS-1…CS-4 + Phase 0–3, 2026-06-27).** The vendored
`percept-spectral-repro` transform DSP is now the **primary TD→LSB route** (`k=352.62`; §3 decision 18,
constants in §2a). Supporting pieces:
- **PSD-source taxonomy** (`PSD_SOURCE_TAXONOMY`: patient_event / streaming_event / montage_snapshot)
  separates pooling identity from timeline display category — Streaming is its own category, not
  mislabeled "Montage PSD".
- **PSD→LSB bridge** for PSD-only patient-event snapshots: event `FFTBinData` is linear µV magnitude,
  baseline-subtracted (clamp negatives to 0). Montage law `PSD_bp = 4.789·TD_bp` (r=0.987, n=10476)
  composes to `LSB = 73.63·PSD_bp`, restricted to [7.8, 30] Hz.
- **Per-PRO LSB selection** (`availability.per_pro_lsb`), strict precedence: (1) native device LSB →
  (2) direct TD→LSB transform when a TD-bearing recording overlaps the PRO → (3) PSD bridge only for
  PSD-only patient events in [7.8, 30]. Surfaced on the timeline (`_pro_lsb_by_channel`, payload key
  `pro_lsb`): marker shape = tier (native ● / TD-transform ○ / PSD-bridge ◇), red ring = saturated.
  Live RCS08: 684 PROs × 30 ch → 239 values (51 native, 102 TD-transform, 86 PSD-bridge).
- **Per-PRO time contract:** for a PRO at time T matched to a TD recording, the transform runs on 30 s
  centered on T = [T−15 s, T+15 s], clipped to the session boundary (≥1 s, >10% Missing rejected);
  a 1 s rcs-Hann window slides at 500 ms (≈59 windows), and the **median** in-band summed-squared
  magnitude → one LSB.
- **Shared LSB cache** (`per_pro_lsb_spectrum` + `_pro_lsb_spectrum_cached`, content-keyed memo) is the
  single source of truth for BOTH the timeline and the spectral feature-importance panel — identical
  numbers at any shared band center. The spectral scan's `feature="lsb"` reads `log10(cache[...])`
  (`feature_used="lsb_cs14"`); the old Welch-density×269 / device-FFT rescale path was removed (~65
  lines). Code-review findings 1–5 in `8274d6c` (PRO-set alignment invariant, vectorized per-band LSB
  gather, thread-safe memo lock, double-dip warning for legacy payloads).

**Audit-cleanup statistical calls (§3 decision 19; suite 184→196).** Moving-block bootstrap AUC CI +
DEFF discount; BCa headline CI; per-week threshold-drift trend test. **The one trap to preserve —
C1 guard (do not undo):** BCa's bias term `z0` re-creates the manufactured beats-chance floor that
audit C1 removed, so the *displayed* CI is BCa but the **safety gate reads the de-folded percentile
bound `auc_lo_defold`** — both `auc_power` call sites pass `auc_lo=roc.get("auc_lo_defold", ...)`.
`threshold_drift_by_week` (calendar-time robustness) is distinct from `stim_state_portability`
(per-era / C3, stim-STATE robustness) — keep them separate.

**UX + perf + R-safety pass (2026-06-26, PR #8 → `v3.1.0`).** Biomarker state persistence
(`biomarkerStateStore.js`, localStorage controls + in-memory LRU heap with a `performance.memory`
guard); `run_for_participant` recompute ~63s→47s (threshold sweep vectorized, `_threshold_metric_arrays`
**24.8×** fuzz-verified; spectral CV defaults serial); `_R_GLOBAL_LOCK` (RLock) around every
pymer4/lme4 fit (embedded R is single-threaded; concurrent glmer fits corrupted it). Spectral scan
spans full 0–100 Hz; 8–30 Hz are CENTER frequencies, flagged `adaptive_valid`.

---

## 1. Project orientation

**What BRAVO_pain is.** A Django (backend) + React (frontend) web platform that ingests
JSON exports from the Medtronic Percept RC neurostimulator and provides analysis,
visualization, and decision support for **closed-loop deep brain stimulation (DBS) for
chronic pain**. The immediate engineering goal is to turn recorded neural data into
actionable Percept sensing/threshold parameters a clinician can program. Subject is
**RCS08** (de-identified code; the only participant with a frozen model so far).

**Repo & branch.**
- Repo root: `/Users/pshirvalkar/dev/BRAVO_pain` (host), bind-mounted to `/usr/src/BRAVO`
  inside the live `bravo-server` OrbStack container.
- Remote: `https://github.com/shirvalkarlab/BRAVO_pain.git`.
- **Default branch:** `v3.1.0`. The old `v3.0.0-alpha` is deleted.
- **Active working branch:** `PS_closedloop_deployment` (off `v3.1.0`), **HEAD `f6849c4`**,
  in sync with origin (audit [5]/[42] changeset uncommitted on top).
- Other remote branches: `development` (legacy) + release branches `v2.0-alpha`…`v2.2.1`.
  Retired (squash-merged into `v3.1.0`): `PS_biomarker_{actionability,clfixes,module}` (§9).

(Commit identity, the keychain-warning quirk, and other sandbox traps are in §7.)

**The agent bridge (how code runs in the live container).**
`BRAVO/_agent_bridge/` is a stdlib mailbox watcher running **inside** the `bravo-server` OrbStack
container, on the `./BRAVO ↔ /usr/src/BRAVO` bind mount, so the agent can run real code against the
live DB/REDCap:

```
python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout N --wait M "<cmd>"
python3 BRAVO/_agent_bridge/bridge_client.py --status        # heartbeat
```

- Container: **Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2, pandas 2.2.3, sklearn 1.5.2**.
- **Authoritative test runner (no pytest in container):** `python3 _agent_bridge/run_tests.py`.
- Gunicorn `--reload` makes backend edits live; nginx serves `Client/build`, so **frontend changes
  need a bundle rebuild**. The bridge itself takes effect on container **CREATE**, not restart (§7).

**Live DB / participant.** MySQL/mongoengine in-container; REDCap reachable
(`REDCAP_API_URL`/`REDCAP_API_TOKEN`). **RCS08 live uid = `2e3c75c00d7f4f37b53a048d195f11da`** — use
for all container probes (the old `_pro_dump` uid `1eda36458758461383721208bbe6bb87` is stale post
re-ingest). Cached PRO table `BRAVO/_pro_dump/RCS08_chronic_pro_df.csv` (679 rows). Source device
JSONs at OneDrive grant `/Users/.../PNL/RCS008 jsons` (filenames carry real patient names → keep out
of repo; §7 PHI note).


---

## 2. Key constants & frozen models

### 2a. Quantitative constants in the current code

In `BRAVO/modules/Biomarkers/routines/analytics.py` unless noted. Line numbers are approximate
(they drift with edits — `grep` the name to confirm).

**The three LSB conversion routes (each DSP carries its own k — do NOT cross them):**

| Constant | Value | Route | Meaning |
|---|---|---|---|
| `LSB_PER_UV2_TRANSFORM` | **352.62 LSB/µV²** | **PRIMARY TD→LSB** | k for the vendored `percept-spectral-repro` transform DSP (Hann-windowed zero-padded FFT, 50% overlap). RCS08 all-stim median, r=0.9927, RMSE 60.6 LSB. Band-agnostic. Use exactly, do not round. |
| `LSB_PER_DEVICE_PSD` | **≈73.63 LSB/(device-PSD bp)** | PSD→LSB bridge | `= 352.62 / 4.789`. For PSD-only patient-event snapshots; restricted to [7.8, 30] Hz (else `calibrated=False`). |
| `LSB_PER_UV2_DEVICE_PSD_TD_RATIO` | **4.789** | bridge composition | Device-PSD band power / TD-transform band power (geomean, r=0.987, n=10476). |
| `MODELED_LSB_SIGMA_FOLD` | **1.26** | uncertainty band | 1σ multiplicative scatter on TIER-1/TIER-2 **modeled** LSB estimates (±band on the deployment sign-off card). Per-participant `resid_log_sigma_fold` overrides it when the frozen model carries one. (DSP-neutral rename of the old `LSB_UV2_SIGMA_FOLD`.) |

> **REMOVED 2026-06-28** (`fa2c416`): `LSB_PER_UV2_VALIDATED` (269.0), `UV2_PER_LSB_VALIDATED`,
> `LSB_UV2_LOGLOG_SLOPE`, and the `lsb_from_uv2` / `uv2_from_lsb` converters — plus the welch256 DSP
> helpers `psd_band_to_lsb` / `welch256_density`. The deployment fallback now anchors the offline-Welch
> µV² cut-point to LSB via the per-participant frozen PSD→LSB model only (fail-closed when absent). See §0.

**Other current constants:**

| Constant | Value | Location | Meaning |
|---|---|---|---|
| `ADC_NV_PER_LSB` | **146.0 nV/LSB** (exact) | analytics.py:2548 | Percept time-domain ADC count scale, per Medtronic. Exact. |
| `LSB_VALIDATED_HZ_LO/HI` | **7.8 / 28.3 Hz** | analytics.py:2633-2634 | Calibration-validity window; outside → `freq_extrapolated`. |
| `LSB_DEPLOYABLE_HZ_HI` | **30.0 Hz** | analytics.py:2663 | Device adaptive-stim ceiling (firmware 8–30 Hz). |
| `TRANSFORM_N_FFT` / `_WIN_SECONDS` / `_STEP_SECONDS` | 256 / 1.0 / 0.5 | analytics.py:2874-2876 | Transform DSP: 256-pt FFT, 1 s window, 500 ms step (50% overlap). |
| `TRANSFORM_CENTERED_EXTENT_SECONDS` | **30.0** | analytics.py:2975 | Rating-centered TD extent fed to the per-PRO LSB sweep. |
| `CONVERSION_FFT_SIZE` | **256** | analytics.py:2598 | FFT size the conversion model assumes; only 256-pt modes are convertible. |
| `THRESHOLD_MODES` / `COMPATIBLE_THRESHOLD_MODES` | Dual (256-pt), Single (64-pt), SingleInverse (256-pt) / ("Dual","SingleInverse") | analytics.py | FFT/window per Percept threshold mode. **Single (64-pt) is NOT convertible.** |
| `WELCH_MAX_MISSING_FRAC` | **0.10** | streaming_psd.py | Missing-fraction floor for Welch epochs; above it → all-NaN PSD, row skipped (Fix A). |
| `SMALL_SAMPLE_CLUSTER_FLOOR` / `BOOT_CI_VALID_FLOOR` | 10 / 100 | analytics.py:25,32 | Small-sample advisory floor; valid-replicate floor below which the bootstrap CI is suppressed. |
| `DRIFT_MIN_SAMPLES_PER_WEEK` / `DRIFT_MIN_WEEKS` | 6 / 4 | analytics.py:2226-2227 | Gates for `threshold_drift_by_week` (else `not_assessed`). |

**Transform calibration provenance (`k=352.62`, the deployed primary).** RCS08 all-stim median k
from the vendored transform DSP run on paired `BrainSenseLfp`+`BrainSenseTimeDomain` blocks:
r=0.9927, RMSE 60.6 LSB, median fold ≈1.10×. The stim-off-only k (356.61) is recorded for
provenance only and is NOT deployed. **k cancels in r/AUC only when the feature column is
homogeneous in k** — on a native-vs-modeled mixed axis it does not, so the native-preferred
precedence matters. The 1σ multiplicative scatter is ≈1.26× and propagates into the
estimated-threshold path (`sigma_fold`, `estimated_upper_lsb_lo/hi`). Full derivation:
`HANDOFF_TD_LSB_calibration_2026-06-27.md`.

### 2b. Frozen per-participant PSD→LSB model — `RCS08.json`

`BRAVO/modules/Biomarkers/data/psd_lsb_models/RCS08.json` — `schema:
psd_lsb_conversion/v1`, `generated_utc: 2026-06-25T01:03:47Z`. It is a **frozen asset**
(loaded, never refit on request) so the reviewed cleaning decisions stay fixed.

**Model form (per channel):** `log10(LSB) = a_f + b·log10(µV²)` — a per-channel **common
slope `b`** with a per-frequency **intercept `a_f`** (= device LSB at 1 µV²). The on-board
power gain falls as sensing frequency rises; that frequency dependence lives entirely in
`a_f`, **not** in the slope (per-frequency slope differences are statistically unsupported:
LR n.s., adjusted-R² does not improve). The frequency effect is a **gain/intercept shift,
not a slope change**.

**Pipeline baked into the freeze:** nearest device-LSB sample per offline PSD epoch (each
PSD used once/channel); **±30 min** match window; **fixed 10-min-bin averaging**
(`floor(t/600s)`); Iglewicz-Hoaglin robust-z outlier omission per band
(`|0.6745·(r−med)/MAD| > 3.5` on `log10(LSB/µV²)`, MAD>0 guard); hard **n≥6-per-band**
reliability floor. `fit_basis`: n_total_clusters=685, n_outliers_excluded=33; estimator =
per-channel common slope (OLS log-log), intercept = robust `median(logL − b·logP)` per band.

**Fittable channels:**

| Channel | fittable | common_slope b | R² | pooled_k | n_clusters |
|---|---|---|---|---|---|
| **ZERO_THREE_RIGHT (0-3R)** | yes | **0.8545** | **0.841** | 81.35 | 524 |
| **ZERO_THREE_LEFT (0-3L)** | yes | 0.5164 | 0.253 | 278.76 | 81 |
| ONE_THREE_LEFT (1-3L) | no | — | — | 198.67 (pooled only) | 28 |
| ZERO_TWO_RIGHT (0-2R) | no | — | — | 646.27 (pooled only) | 9 |
| ZERO_TWO_LEFT (0-2L) | no | — | — | 333.98 (pooled only) | 8 |
| ONE_THREE_RIGHT (1-3R) | no | — | — | **None (unmodelable)** | 2 |

**ZERO_THREE_RIGHT per-band intercepts** (the deployed channel of record):

| center_hz | n | intercept a | intercept CI | LSB @ 1 µV² |
|---|---|---|---|---|
| **8.8** | 42 | **1.7695** | [1.7152, 1.8452] | 58.8 |
| 9.8 | 40 | 2.5995 | [2.4604, 2.6808] | 397.7 |
| 10.7 | 13 | 2.5841 | [2.5527, 2.7342] | 383.8 |
| 11.7 | 8 | 2.5673 | [2.5386, 2.6214] | 369.3 |
| 24.4 | 37 | 1.9275 | [1.9140, 1.9403] | 84.6 |
| 26.4 | 202 | 1.8544 | [1.8356, 1.8675] | 71.5 |

(ZERO_THREE_LEFT fits bands at 8.8/9.8/10.7/11.7/22.5 Hz but R²=0.25 — mostly streaming-only
LSB, treat as unreliable.)

**`special` notes in the JSON (the frozen exclusions):**
- **`ZERO_THREE_RIGHT_8.8Hz` — restricted to ≥2026-03-01.** Chronic 0-3R sensing was
  reassigned off the 8.8 Hz band on **2025-12-05**, then bounced across 28/24.4/26.4 Hz before
  settling. The 8.8 Hz gain falls through a **settling transient** over Dec–Feb (post-2025-12-05
  within-regime trend **−0.078 log10/month, p=0.039**) and only reaches stationarity from
  **~2026-02-15** (p=0.72 → 0.91 at 03-01). The 03-01 cut isolates the stable current-config
  regime (n=42, mean 1.69 log10(LSB/µV²), flat trend p=0.91). Using the config-change date
  2025-12-05 instead would inject the higher-gain declining transient and bias the deployable
  threshold. **CLOSED — see §3 item 16.**
- **`ZERO_THREE_RIGHT_23.4Hz` — excluded** (noisy, inconsistent with its 24.4/26.4 Hz neighbors).

### 2c. Constants/claims later corrected or retracted

- **welch256 `k=269` was REMOVED entirely (2026-06-28, `fa2c416`).** It was the rigorous stim-off
  paired-block constant (superseding an even looser early direct fit of k≈74.1); CS-1 first demoted it
  to a PSD-exploration backup, then the 2026-06-28 pass deleted it outright once the device-PSD bridge
  (k=73.63) and the per-participant frozen model covered every live path. The deployed primary TD→LSB is
  the transform route **`k=352.62`** (§2a); the deployment fallback converts the offline-Welch µV²
  cut-point via the frozen model only (fail-closed when no fitted entry exists). See §0.
- **8.8 Hz "ρ=−0.64 temporal regime shift, ~3× gain drop, unexplained"** — superseded by the
  documented settling-transient mechanism (see §2b / §3 item 16).
- **Forced log-log slope = 1.1** was explored as within ~0.005 R² of the forced optimum (0.90)
  once 8.8 Hz and 23.4 Hz are cleaned, but the **deployed model uses the per-channel free common
  slope** (b=0.8545 for 0-3R), not a forced 1.1.

---

## 3. Decision log

Durable decisions and why, chronological. All **Adopted** unless noted. Commit SHAs are pointers
into history, not current HEAD.

| # | Decision | Why | Ref |
|---|---|---|---|
| 1 | **rpy2/pymer4 glmer converter fix** — `_rpy2_converter_ctx()` returns `localconverter(ro.default_converter)`, NOT `+ pandas2ri.converter` | pandas2ri context converted pymer4's `glmerControl` R list to a dict rpy2 3.5.15 can't return to glmer. | `33f45a5` |
| 2 | **PRO-timestamp timezone correction** — REDCap `date_time_s1_daily` is California local wall-clock; convert via `bravo_service._pro_timestamps_utc` (LA→UTC, DST-aware) | Device StartTime is already UTC; parsing PRO as UTC smears matches 7–8 h. Census 67/678 within 60 min. | `a4e4e68` |
| 3 | **Concatenation is robust to PRO matching** — keep `FixBreaking` zero-fill concat; no change to matching | Both-ways re-decode: 67 vs 67 matched, 0 changes. | no-op |
| 4 | **Fix A — missing-aware Welch epochs** — TD windows over `WELCH_MAX_MISSING_FRAC=0.10` → all-NaN PSD → skipped | Zero-fill from FixBreaking entered Welch PSDs as real zeros, deflating band power. | `adcaf15` `c438ce1` |
| 5 | **ClosedLoopSim figure-reset fix** — memoize `requestParams`; permanent Plotly `<div ref>`; draw-once + restyle-by-trace-index | New object identity per render refetched all 4 panels → every figure flashed to loading. Hard constraint (§7). | PR #3 `255e0ef` |
| 6 | **Removed the `net benefit` cut-point rule** | Its objective equals `prevalence × cost` — always picks the identical point as `cost` (two buttons that can't disagree). | PR #3 |
| 7 | **C1 — de-fold the deployment-ROC bootstrap CI** — append `float(ab)`, not `max(ab,1−ab)` | Folding hid null bands; a de-folded lower bound can honestly fall below 0.5. **(See the C1 guard in §0 — BCa later re-threatened this.)** | PR #5 `c50be37` |
| 8 | **C3 — signed era AUC + pooled-orientation** — pooled orients first, eras reuse `pooled_flip`, era AUC signed not folded | A folded per-era AUC masks within-era sign reversals (a closed-loop failure mode). | PR #5 |
| 9 | **C8 — tri-state deployment gates, fail-closed** — gate ∈ {pass, fail, indeterminate}; stim-stable gate ABSTAINS when LRT unavailable | A gate that goes green on *absence* of evidence is unsafe for "ready to program". | PR #5 |
| 10 | **C9/C10 actionability** — single-source `CUTPOINT_TRACE=2`; recommend→program Δ; conservative-abstain ramp guidance | Actionable recommendation, fail-closed discipline kept. | PR #6 `b0597f8` |
| 11 | **PSD→LSB conversion panel + frozen model** — freeze per-participant `RCS08.json`, tiered fallback (band→channel_freq→channel_pooled→none); modeled threshold → `indeterminate` gate | Device reports LSB, Welch reports µV²; an unsensed band needs an estimated threshold, clearly flagged. | PR #6 `771f3c2` |
| 12 | **C2 — forward-chaining / out-of-sample validation** — expanding-window blocked-by-week; threshold fit on TRAIN only; held-out AUC not re-folded | In-sample AUC masked forward reversals (26.4 Hz: 0.55→0.24; 8.8 Hz: 0.52→0.37). Last HIGH finding. | PR #7 `d9d58a4` |
| 13 | **Remove 60 Hz mains notch default** — `_band_power_notched(notch=False)` | Implanted/battery-powered, no mains coupling; notching removes real signal. `notch=True` retained. | `f915257` |
| 14 | **Threshold-mode FFT-size guard** — only `COMPATIBLE_THRESHOLD_MODES=("Dual","SingleInverse")` (256-pt FFT) are convertible | A 64-pt Single-mode FFT is a different quantity; same gain can't convert it. | `f915257` |
| 15 | **PSD→TD→LSB back-translation = null** — direct PSD→LSB is the rigorous path | Phase-randomized TD reconstruction matches the direct PSD integral within 0.8%. | `f915257` |
| 16 | **8.8 Hz cut stays ≥2026-03-01** (NOT the 2025-12-05 config-change date) | The config-change date sits inside a declining settling transient (−0.078 log10/mo, p=0.039); stationarity only from ~2026-02-15. Frozen fit UNCHANGED. | `e9d7a80` |
| 17 | **Impedance term `c=1.02` — REJECTED** | Significant only under naive OLS (pseudoreplication: 2985 epochs share 230 impedance measurements). Cluster-robust SE n.s. (p=0.26); a slow-time proxy, not a physical gain. Threshold impact 1.22× < model scatter. Frozen fit UNCHANGED. | `a9c3a01` |
| 18 | **Primary TD→LSB → transform `k=352.62`** (welch256 `k=269` demoted to backup) | The vendored transform DSP reaches r=0.9927 / RMSE 60.6 LSB; welch256 produces a PSD from TD and can't consume a device PSD, so it was never a valid no-TD backup. | CS-1 (§0) |
| 19 | **Audit-cleanup statistical calls** — moving-block bootstrap CI + DEFF; BCa headline CI with de-folded `auc_lo_defold` as the C1-safe gate; per-week threshold-drift trend test | Honest CIs under autocorrelated ratings; keep the C1 beats-chance floor from being re-manufactured by BCa's bias term. | §0, `8509e96`/`2ef0408`/`abe8a23` |
| 20 | **welch256 `k=269` REMOVED — deployment fallback frozen-model-only** *(superseded by 21)* | The cut-point's own model converts it: the offline-Welch µV² cut-point → LSB via the per-participant frozen model (fit on the same Welch→LSB mapping), not a bespoke population scalar. Population-constant TIER-3 retired → fail-closed (indeterminate) when no fitted entry. Dead welch256 DSP + converters deleted. | §0, `184ea74`/`fa2c416` |
| 21 | **Deployment LSB fallback → universal TIER-1 modeled off raw TD** (frozen-model TIER-2 deleted) | The ROC cut-point is a **z-scored** log-power feature, NOT linear µV² — feeding it to the frozen model (decision 20) was a units bug (z≤0→LSB≈0, z>0 mis-read). Model the LSB line off the raw µV TD at the ROC's OWN center (transform ×352.62 / bridge ≈73.63) and anchor by RANK like native — no µV²↔LSB conversion of the cut-point. Honors the ROC center exactly (no snap-clamp); fail-closed when no TD/PSD. Deployment-only; Exploration timeline unchanged. | §0, `09798f7` |

---

## 4. Open items

> Dropped by PI (do NOT re-open as work): "generalize beyond RCS08", "PHI hygiene". PHI context
> is an operational note in §7 only.

**Currently open:**

1. **Audit backlog — Bucket C/D + low-polish.** Of the original four-lens audit (4 high · 28 medium ·
   24 low), all HIGH (C1/C2/C3/C8) and C4 are resolved, and the 2026-06-27 audit-cleanup session
   cleared Bucket B + four statistical calls; **[5] and [42] closed 2026-06-28** (§0). Remaining:
   - **[14]** reconcile clustering granularity (per-rating ROC `n_clusters` vs weekly-glmer
     elapsed-week units report different N). **Needs a PI judgment call before coding.**
   - **[49]** embed Plotly PNG snapshots of the 4 figures into the deploy export / printed sheet
     (needs the bridge for kaleido — §7).
   - **Low-polish cluster:** [0]/[15]/[22]/[28]/[39]/[43]/[48] — labeling/navigation niceties, batchable.
   Source of record: `closedloop_audit_report.md` + the `AUDIT_TRIAGE_*` decision sheets.
2. **Anchor test** for "timeline circle == spectral point at same band center" — the identity holds
   by construction (one shared cache) but has no live E2E test across the two call sites.
3. **`per_pro_lsb_overlay`** (within-rating sliding-window LSB trace + saturation QC) is available
   but not yet drawn — natural next step is a hover/expand detail on a rating's 30 s LSB trace.

**Closed (do not re-open):** all four HIGH (C1/C2/C3/C8) + C4; **[5]** (server-side full-array
cut-point — `operating_points` table); **[42]** (LSB op-point chip + histogram resulting-LSB);
figure-reset bug; C5/C6/C7
(figure-honesty); C9/C10 (actionability); 8.8 Hz cut date; 60 Hz notch default; threshold-mode guard;
TD→LSB validation + PSD→TD→LSB back-translation; impedance `c=1.02` (rejected); high-gamma 55.5 Hz
(not actionable — firmware limited to 8–30 Hz; the `freq_extrapolated` guard stays).

---

## 5. Test & build status

- **Backend suite: 240/240 PASS** in the live container via the bridge:
  `python3 _agent_bridge/run_tests.py`. **No pytest in the container** — `run_tests.py` is the
  authoritative runner (globs `test_*.py`, sets up Django, reloads the module). `test_analytics.py`
  holds ~96 of the test functions.
- **Local standalone runner caveat:** running `modules/Biomarkers/tests/` outside the container
  shows harness-only failures (`test_normalize_pro_times*`, `test_pain_scores_emit_utc_t_epoch`,
  `test_pain_series_epochs_match_pro_match_arrays` need Django `INSTALLED_APPS`; model-dependent
  files can't run in the local importlib runner at all). Not regressions — use the container runner.
  Pure-function analytics checks CAN run locally by importing `analytics.py` Django-free in `bravo_app`.
- **Frontend build:** CRA production build exits 0:
  `cd Client && export npm_config_cache=/tmp/npmcache && GENERATE_SOURCEMAP=false
  NODE_OPTIONS=--openssl-legacy-provider CI=false npx --no-install react-scripts build`.
  The repo **commits `Client/build/` alongside source**; nginx serves the mounted build, so the
  bundle must be rebuilt and committed for any frontend change. ClosedLoopSim is code-split into
  **chunk 431**; the timeline is **chunk 768**.

---

## 6. Key documents & artifacts

**Design spec of record (read before any biomarker-pipeline work):**
- `DESIGN_biomarker_pipeline_v2.md` (artifact `bab71722-0293-453e-9d21-36b77a26cbac`) — the
  biomarker pipeline design ledger v2: Percept RC controller facts + 8–30 Hz adaptive range;
  the corrected five-product BrainSense taxonomy; the **BandCandidate contract v1** (serializable
  interface between the Biomarker module and the future Closed-Loop Simulation module); the
  LSB↔µV² conversion as a confidence-rated FYI; stim-era heterogeneity confounds; the Option-3
  UI split + data-availability-timeline design that replaces `BiomarkerTimeline`. (Its conversion
  section predates the `k=352.62` transform primary — cross-reference §2 here.)

**In-repo provenance / decision docs (current, keep):**
- `HANDOFF_TD_LSB_calibration_2026-06-27.md` — full TD→LSB transform calibration derivation (`k=352.62`).
- `CS3_FFTBinData_units_recon_2026-06-27.md` — PSD-bridge units finding + montage TD↔PSD fit (4.789).
- `closedloop_audit_report.md` (version `e3a12136-e0e1-4fff-b95f-baa42d0a0a46`) — the four-lens
  audit of record (source for the remaining Bucket C/D backlog).
- `AUDIT_TRIAGE_medium_low.md` / `AUDIT_TRIAGE_v3_decisions.md` — the medium/low audit decision sheets.
- Frozen model: `BRAVO/modules/Biomarkers/data/psd_lsb_models/RCS08.json` (§2b).
- Per-session narrative: the dated `SESSION_HANDOFF_*.md` / `HANDOFF_*.md` files (newest:
  `SESSION_HANDOFF_2026-06-27.md`).

(Older per-figure artifact IDs from superseded sessions — early PSD→LSB panels, k=269 calibration
figures, Phase-2 encoding mockups — were dropped from this index; recover them from the dated
session handoffs or `operon.artifacts()` if ever needed.)

---

## 7. Known gotchas (operational traps)

- **Git identity.** `.git/config` is unwritable in the sandbox. Set identity per-commit via
  `GIT_AUTHOR_NAME/EMAIL` + `GIT_COMMITTER_NAME/EMAIL` (`Prasad Shirvalkar <prasad.shirvalkar@ucsf.edu>`).
  The `could not write config file` / keychain `-50` / `~/.config/git/ignore` warnings are harmless.
- **Bridge: takes effect on container CREATE, not restart;** and the watcher (pid 8) stalls
  periodically (heartbeat age climbs, jobs time out) — fix is an OrbStack container restart, which the
  sandbox can't do, so ask the user. After a commit recycle workers with `kill -HUP 1` in-container
  (VirtioFS needs `--reload-engine poll`; inotify doesn't propagate).
- **`save_artifacts`:** dedups by filename and won't re-read changed content — use a fresh filename
  when content changes; and it only resolves WORKSPACE-relative paths, so copy repo files in first.
- **sklearn skew — correctness risk.** Container has sklearn **1.5.2**; some pickled classifiers were
  trained under 1.6.1. Loading across the skew can silently mis-predict — re-validate before trusting.
- **REDCap PRO timezone.** `date_time_s1_daily` is **California local wall-clock**, not UTC. Always
  convert via `bravo_service._pro_timestamps_utc` (LA→UTC, DST-aware); device StartTime is already UTC.
- **Local decode (`bravo_app`) needs a dummy Fernet key:** set
  `os.environ["DATASERVER_ENCRYPTION"] = Fernet.generate_key().decode()` **before** importing `HelperFunctions`.
- **datetime ns-resolution.** Epoch conversions use `…to_numpy().astype("datetime64[ns]").astype("int64")/1e9`
  at all source sites. A bare `.astype("int64")` gives microseconds under pandas 3.0's `datetime64[us]`
  default and **mis-assigns stim eras** — must be ns.
- **CRLF files.** `Server/APIs/DataAnalysis.py` and `Server/APIs/urls.py` are **CRLF** (all other
  source is LF). `edit_file` preserves line endings; raw Python `open()` writes strip them → giant
  spurious diff. Use `edit_file` for these two.
- **GitHub from the sandbox.** No `gh`/PyGithub on PATH — use `urllib` + `GITHUB_TOKEN` (Bearer, API
  2022-11-28). Self-approval of your own PR is blocked → post the review as an issue comment, then
  `PUT /pulls/{n}/merge` (squash).
- **kaleido/Chrome PNG export is broken in the sandbox** — use `write_html`, matplotlib, or the bridge
  (kaleido in-container), never kaleido PNG in `rocqa`.
- **ClosedLoopSim Plotly discipline (hard constraint).** Panels draw **once** via `Plotly.react` and
  mutate via `Plotly.restyle(…, [traceIndex])` / `Plotly.relayout` — **never rebuild a figure on
  interaction** (commit `255e0ef` fixed the reset bug). Following the Python `ps-plotly` figure-rebuild
  pattern verbatim re-introduces the bug; keep the restyle-by-trace-index pattern
  (`const CUTPOINT_TRACE = 2` in DeploymentRocPanel).
- **PHI note (operational, not an action item).** Stage-1 device JSON filenames in the OneDrive grant
  carry real patient names — keep that folder out of the repo; RCS08 is the de-identified code. Repo
  exports are derived spectral features only; `secrets/redcap.env` + the bridge mailbox are gitignored.

---

## 8. Key file map

**Backend (`BRAVO/modules/Biomarkers/`):**
- `routines/analytics.py` — glmer converter (`_rpy2_converter_ctx`); LSB constants + converters
  (`td_transform_band_power`, `td_to_lsb`, `device_psd_to_lsb`, `THRESHOLD_MODES`,
  `_band_power_notched`); deployment stats (`deployment_roc`, `deployment_roc_by_era`,
  `deployment_forward_chaining`, `threshold_drift_by_week`, `auc_power`); bootstrap/CI helpers
  (`_block_bootstrap_aucs`, `_auto_block_len`, `_bca_ci`, `_jackknife_cluster_aucs`); spectral scan
  (`spectral_feature_importance`, `feature="lsb"→lsb_cs14`); stim-era assignment (`_assign_stim_eras`,
  `_elapsed_week_cluster`).
- `routines/availability.py` — per-PRO LSB selection (`per_pro_lsb`, `per_pro_lsb_overlay`,
  `per_pro_lsb_spectrum`), modeled `lsb_series` tier, and `modeled_lsb_at_center` (deployment-only:
  models the device-LSB line off raw TD at the ROC's own band center — the units-consistent fallback,
  decision 21).
- `routines/streaming_psd.py` — Welch (`welch_psd_for_instance`, `welch_rating_centered`,
  `WELCH_MAX_MISSING_FRAC`), `build_pooled_detail_from_matrix`.
- `routines/psd_lsb_model.py` — frozen-model loader/estimator (`load_model`, `has_model`,
  `estimate_lsb`, `model_plot_payload`); tiered fallback band→channel_freq→channel_pooled→none.
- `bravo_service.py` — timeline + scan wiring (`_build_availability`, `_pro_lsb_by_channel`,
  `_pro_lsb_spectrum_cached`, `run_for_participant`, `_pro_timestamps_utc`); deployment
  (`deployment_summary`, `band_deployment_roc`, `band_lsb_and_power`, `recommended_vs_programmed`,
  `_ramp_guidance`).
- `data/psd_lsb_models/RCS08.json` — frozen PSD→LSB model (§2b).
- `tests/` — `test_analytics.py` (~96 fns), `test_match_to_pro.py`, `test_psd_lsb_model.py`,
  `test_welch_missing_aware.py`, etc.

**API:** `Server/APIs/DataAnalysis.py` + `Server/APIs/urls.py` (`QueryPsdLsbConversion[Model]` views /
`queryPsdLsbConversion[Model]` routes). **Both files are CRLF — edit with `edit_file` only.**

**Decode chain:** `modules/MedtronicPercept/{Percept,BrainSenseStream,IndefiniteStream,Session}.py`;
ingest concatenate toggle at `modules/DataCurator.py:148/150`
(`metadata["automatic_concatenation"]` → `JSON["AutomaticStreamingFix"]` → `Session.py:423`).

**Frontend (`Client/src/views/Reports/`):**
- `ClosedLoopSim/` — `index.js`, `DeploymentRocPanel.js`, `EraRefitPanel.js`, `LsbPowerPanel.js`,
  `DeploySignoffCard.js`, `DeploymentVerdictStrip.js`, `PsdLsbPanel.js`, `ConversionModelPanel.js`,
  `palette.js` (Okabe-Ito). Code-split **chunk 431**.
- `Biomarkers/BiomarkerDataTimeline.js` (modeled-LSB markers, chunk **768**),
  `Biomarkers/BiomarkerAnalytics.js` (spectral caption), `Biomarkers/biomarkerStateStore.js`.
- `Client/build/` — committed compiled bundle (rebuild + commit for any frontend change).
- `Client/public/static/docs/METHODS_lsb_estimation.html` — served methods doc.

**Data / config:** device JSONs at OneDrive grant `/Users/.../PNL/RCS008 jsons` (keep out of repo);
cached PRO table `BRAVO/_pro_dump/RCS08_chronic_pro_df.csv` (679 rows); `secrets/redcap.env` (gitignored).

---

## 9. PR / commit lineage (quick map)

| PR | Squash SHA | Into | Content |
|---|---|---|---|
| #3 | `52337f5` (merge) / `255e0ef` (fix) | v3.1.0 | Pain Biomarkers engine + ClosedLoopSim reset fix |
| #4 | `52010ec` (merge) | v3.1.0 | ClosedLoopSim Phase-2 visualizations |
| #5 | `c50be37` | v3.1.0 | Four-lens audit Wave 1+2 (C1/C3/C5/C6/C7/C8) |
| #6 | `b0597f8` | v3.1.0 | C9/C10 + PSD→LSB panel + pandas-3/numpy-2 forward-compat |
| #7 | `d9d58a4` (merge) / `b2e01f1` | v3.1.0 | Forward-chaining / out-of-sample validation (C2) |
| #8 | `a191b758` (merge) | v3.1.0 | UX + perf + R thread-safety lock pass (§0) |
| — | `f915257` | v3.1.0 / branch base | Modality-sensitive conversion, threshold-mode guard, LSB estimation |
| — | `e9d7a80` | branch | 8.8 Hz cut rationale; keep ≥2026-03-01 (decision 16) |
| — | CS-1…CS-4 + Phase 0–3 | branch | TD→LSB transform primary; PSD bridge; per-PRO selection; spectral-scan unify (§0) |
| — | `8274d6c` | branch | code-review fixes for the Phase 2–3 spectral rewire |
| — | `184ea74` | branch | remove dead welch256 DSP; fix stale TIER-1 modeled-timeline labels (§0) |
| — | `fa2c416` | branch | remove k=269 population constant; deployment fallback frozen-model-only (§0) |
| — | `e15e57e`/`fe31c87`/`45c39a9` | branch | MEGA top-of-doc update instructions; un-track ~100 stray scratch files + restore docs |
| — | `09798f7` | branch | deployment LSB fallback → universal TIER-1 off raw TD; fix z-scored units bug (decision 21, §0) |
| — | **`e8a0d3f`** | `PS_closedloop_deployment` (HEAD) | **rebuild frontend (drop retired k=269 tier label)** |

**Engineering envs:** `bravo_app` (py 3.11, local decode — Django-free pure-function checks),
`rocqa` (plotly 6.8 + kaleido — broken Chrome export in sandbox; use `write_html` or the bridge),
`python` (read-only). Live container: Python 3.12.3, rpy2 3.5.15, pymer4 0.8.2, pandas 2.2.3,
sklearn 1.5.2.

---

*End of mega-handoff. Branch `PS_closedloop_deployment` @ **`e8a0d3f`** + 1 uncommitted changeset, suite **240/240**.
Authoritative sources: `RCS08.json`, the dated `SESSION_HANDOFF_*.md` / `HANDOFF_*.md` files,
and the current `analytics.py`. Preserve exact numbers, SHAs, paths, and dates when editing —
and verify constants against source (`grep`), not against this doc, before relying on a line number.*
