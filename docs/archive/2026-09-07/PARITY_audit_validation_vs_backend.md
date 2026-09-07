# Parity Audit — Offline Validation/Scan Pipeline vs Production Biomarker Backend

**Participant:** RCS08 (`2e3c75c00d7f4f37b53a048d195f11da`)
**Repo:** `/Users/pshirvalkar/dev/BRAVO_pain` · branch `PS_biomarker_module`
**HEAD at audit:** `bb64b9b` (Wave-2 Phase B frontend: deployment ROC + cut-point search panel)
**Method:** code read of both sides for each discrepancy class, plus empirical bridge probes
(`_agent_bridge/parity_probe.py`, `parity_probe2.py`) that recompute each quantity *both ways* on the
live RCS08 cached matrix and count divergence. Empirical proof was prioritized over reading suspicion.

> No production source was edited. All probes live in `BRAVO/_agent_bridge/` only.

---

## Executive summary

| # | Class | Status | Severity | One-line |
|---|-------|--------|----------|----------|
| 1 | Matching (PSD↔PRO) | **OK** | — | Offline phase0 genuinely ran `pro_first`/tol=60; live default matches. Reproduced **290** unique vas PROs exactly. |
| 2 | Timestamp / timezone | **DISCREPANCY** | med | `_pro_match_arrays` + `pain_scores_for_participant` are tz-fixed, but `availability.pain_series` and `adapter` still parse PRO times naively. |
| 3 | Binarization (scan) | **OK** | — | Live scan and offline phase1 use identical global tertile (73.0/84.0); 0 disagreeing rows. |
| 4 | Band-power feature | **OK** | — | Both consume the same log+z-scored `prelog` stack via `nanmean`; no double-log. |
| 5 | Clustered inference | **OK** | — | Both pass the PRO `rating_group` (290 clusters) to `_cluster_robust_logit_p`. |
| 6 | Mixed-effects / glmer | **DISCREPANCY** | med | `weekly_era` derived differently (49 elapsed-week buckets offline vs 29 ISO-week strings live) **and** glmer binarization basis differs (per-channel offline vs global live). |
| 7 | Stim era | **DISCREPANCY** | **high** | Offline interpolates stim by **LOCF** (`kind="previous"`); live uses **next-sample** (`searchsorted`). 3253/4722 mA differ, **814 rows change era**. |
| 8 | Claimed-but-missing | **OK** | — | All 6 claimed wave-1/2 items (a–f) verified present at HEAD. |

**Totals:** 8 classes checked · **3 discrepancies** · **0 claimed-missing.**

---

## 1 — Matching (PSD↔PRO)  ·  OK

**Question.** Does the live scan match with the same direction/tolerance/cap as offline phase0, and
did phase0 *actually* pass `pro_first` (vs the suspected `prior`)?

**Offline.** `phase0_build_v2.py:14-17,37-39` — `DIRECTION="pro_first"`, `TOL_MIN=60.0`,
`MAX_PER_RATING=3`, `REFRACTORY=2.0`, calling `sp.build_pooled_detail_from_matrix(... match_direction=DIRECTION)`.
**Backend.** `streaming_psd.build_pooled_detail_from_matrix` defaults `tolerance_min=60.0,
max_per_rating=3, refractory_min=2.0, match_direction="pro_first"` (`streaming_psd.py:521-524`);
`run_for_participant` / `build_band_candidate` parse `MatchDirection` default `"pro_first"`
(`bravo_service.py:1857-1863`, `2373-2379`).

**Empirical proof.** Reproducing phase0's *exact* args on the live matcher:

| match_direction | unique vas PROs |
|---|---|
| **pro_first** (phase0 + live default) | **290** |
| nearest | 288 |
| prior | 67 |

`survey_usage` from the live build: `n_pro_total=682, n_pro_used=290, pct_pro_used=42.5,
psd_per_pro_median=3, max=18`. **The report's headline 290/682 is exactly reproduced by `pro_first`.**
The earlier worry that offline phase0 ran `prior` (which would give 67) is **disproved** — the matcher
and the report agree.

**Fix:** none.

---

## 2 — Timestamp / timezone  ·  DISCREPANCY (med)

**Question.** Is the PRO naive-parse bug still present, and which readers of `date_time_s1_daily`
disagree on tz?

**Fixed (correct) readers** — route through `_pro_timestamps_utc`, which localizes the naive REDCap
wall-clock string as `America/Los_Angeles` (DST-aware) then converts to UTC (`bravo_service.py:1509-1525`):
- `_pro_match_arrays` (`bravo_service.py:1537`) — the matcher input. **Correct.**
- `pain_scores_for_participant` (`bravo_service.py:2920`). **Correct.**

**Still-naive (buggy) readers** — `pd.to_datetime(...)` with no `tz_localize`, then `.timestamp()`
treats the wall-clock as UTC, placing the value **7–8 h early**:
- **`availability.pain_series` (`availability.py:189`).** Feeds the always-on exploration-timeline
  pain row (called at `bravo_service.py:1659` inside `_build_availability`, and it also contributes to
  the timeline `span`). The pain trace is therefore drawn 7–8 h offset from the correctly-localized
  PSD/stim marks and from the matched analysis — a clinician-visible misalignment on the live timeline.
- **`adapter.align_pros` (`adapter.py:134`)** and **`adapter.bravo_chronic_to_lfp_df`**
  (`timestamp_col` parsed naively). `bravo_chronic_to_lfp_df` is live on the chronic threshold-detector
  path (`bravo_service.py:1306`), so its PRO↔chronic alignment inherits the same 7–8 h skew.

**Severity med:** does **not** corrupt the spectral biomarker numbers (those go through the fixed
`_pro_match_arrays`), but corrupts the timeline pain-row position and the legacy chronic-detector PRO
alignment.

**Fix:** make `pain_series` and the `adapter` PRO readers call `bravo_service._pro_timestamps_utc`
(or share the `_PRO_LOCAL_TZ` localize→UTC step) instead of a bare `pd.to_datetime`.

---

## 3 — Binarization (scan)  ·  OK

**Offline (phase1).** `phase1_scan_v2.py:44-47` — global tertile over all finite labels:
`lo_c,hi_c = percentile(finite_lab,[33.33,66.67])`; `<=lo→0`, `>=hi→1`, middle NaN.
**Backend.** `analytics._binarize_labels` (`analytics.py:926-932`) — same percentiles, same inclusive
`<=`/`>=` boundaries, middle NaN; called **once** globally in `spectral_feature_importance`
(`analytics.py:1154`).

**Empirical proof.** On the vas pool: offline cut `[73.0, 84.0]` == live cut `[73.0, 84.0]`;
n0=545/n1=650 both ways; **`n_disagree_rows = 0`.** Parity-clean for the scan.

**Fix:** none. *(But see §6 — the glmer click-validate path uses a different binarization basis.)*

---

## 4 — Band-power feature  ·  OK

**Offline.** `phase1_scan_v2.py:56`, `phase2_glmer_v2.py:55` — `bp = nanmean(cube[...][:,ci,fmask], axis=1)`
over a 5-Hz mask, where `cube` **is** the pooled `psd` stack (already `10*log10` + within-(channel,source)
z-scored). No second log.
**Backend.** `spectral_feature_importance` honors the `prelog` flag: when `prelog=True` it does
`bp_log = nanmean(sub, axis=1)` with **no** second `log10` (`analytics.py:1196-1198`); the linear→log
branch only runs when `prelog=False` (`:1201`). `band_mixedmodel_inference` / `band_stim_stability`
do the same (`analytics.py:1600`, `1722`).

**Empirical proof.** Live pooled detail reports `prelog=True`,
`transform="log_zscore_within_channel_source"`, `psd` shape `(4722, 6, 101)` — identical stack both
sides. Both use the same mean-over-5-Hz-mask. **No log/linear mismatch.**

**Fix:** none.

---

## 5 — Clustered inference  ·  OK

**Offline.** `phase1_scan_v2.py:73` — `_cluster_robust_logit_p(bp, ybin, groups=rg)` with `rg` = the
matched PRO `rating_group`.
**Backend.** `spectral_feature_importance` sets `auc_groups = rating_group` and passes it to
`_cluster_robust_logit_p(bp_log, y_bin, groups=auc_groups)` (`analytics.py:1228`). The cluster key is
the PRO rating index (`rating_group`), **not** channel or day — `_cluster_robust_logit_p` clusters the
sandwich SE on `groups` (`analytics.py:1086-1088`).

**Empirical proof.** `rating_group` length == labels length; **290 unique clusters** = the 290 matched
PROs. Same cluster key both sides.

**Fix:** none.

---

## 6 — Mixed-effects / glmer  ·  DISCREPANCY (med)

Formula, family, and engine match: both fit `pain_high ~ band_power + (1|<weekly cluster>)`, binomial,
via pymer4→lme4 (`phase2_glmer_v2.py:81`; `analytics.py:1618-1620`). Two real divergences:

**(6a) `weekly_era` / cluster derivation differs.**
- Offline (`phase2_glmer_v2.py:25-26`): **integer elapsed-week index** from the first sample —
  `((t_epoch - t0)/(7·86400)).astype(int)`.
- Live (`band_mixedmodel_inference`, `analytics.py:1606-1607`): **ISO-calendar-week string**
  `"{year}-W{week}"` via `.dt.isocalendar()`.

  **Empirical:** offline → **49 clusters**, live → **29 clusters**, and the two partitions are **not**
  a relabeling of each other (`weekly_era_same_partition = False`). Elapsed-week buckets that straddle a
  Monday boundary split across two ISO weeks (and vice versa), so the random-intercept structure — hence
  the fixed-effect SE, p, OR-CI, and FDR q — differ between the validated set and what the app shows.

**(6b) Binarization basis differs (per-channel vs global).**
- Offline (`phase2_glmer_v2.py:49`): tertile cut computed on **this channel's** labels only
  (`percentile(labels[finite & ch_row], …)`).
- Live (`band_mixedmodel_inference`, `analytics.py:1602`): `_binarize_labels(labels, …)` on the **full
  pooled** label array (**global** cut), then restricted to the channel by the band-power NaN mask.

  **Empirical:** per-channel cuts diverge from the global `[73.0, 84.0]` — e.g. `ZERO_THREE_RIGHT`
  `[71.0, 82.7]`, `ONE_THREE_LEFT` `[78.0, 85.0]`. Borderline samples flip high/low between the two,
  changing n and the OR/p of the click-validated band.

**Minor (low):** offline z-scores band power with `std(ddof=1)` (`phase2:56`); live uses `np.nanstd`
(ddof=0) (`analytics.py:1614`). Negligible at n≫1 but not identical. Separation guard also differs:
offline flags `|beta|>50` (`phase2:95`), live flags `|coef|>10` (`analytics.py:1640`).

**Severity med:** the glmer OR/CI/p/q the click-validate panel reports per band will not equal the
offline validated numbers for the same band.

**Fix:** make `band_mixedmodel_inference` derive the cluster as the integer elapsed-week index from the
first sample (match `phase2`), and binarize per-channel (cut on the channel's own labels) — or, if the
global basis is intended, re-run the offline validation with a global cut so the two agree.

---

## 7 — Stim era  ·  DISCREPANCY (HIGH)

Thresholds and LRT match: OFF `<0.1`, LOW `0.1–1.5`, HIGH `>1.5` mA; reduced
`band_power + stim_era + (1|era)` vs full `band_power * stim_era + (1|era)`
(`phase2b_hetero_v2.py:36-37,80-82`; `analytics.py:1739-1741,1750-1752`). **The interpolation direction
of stim onto PSD times is opposite:**

- Offline (`phase2b_hetero_v2.py:31-33`): `scipy.interp1d(kind="previous")` = **LOCF** — the stim
  amplitude in effect *at or before* each PSD sample (the physically correct "what was stim when this
  PSD was recorded").
- Live (`band_stim_stability`, `analytics.py:1731-1733`): `idx = np.searchsorted(stim_t, t_epoch)` →
  `stim_y[idx]` = the stim value at the first stim timestamp **≥** the PSD time = the **next** reading
  (NOCB), the opposite direction.

**Empirical proof (vas pool, 4722 rows):**

| | OFF | LOW | HIGH |
|---|---|---|---|
| Offline (LOCF) | 1376 | 2073 | 1273 |
| Live (next-sample) | 1147 | 2166 | 1409 |

`stim_mA differs on 3253/4722 rows`; **`stim_era changes on 814/4722 rows (17%)`.** Mislabeling 17% of
samples' stim state biases the band×stim-era interaction LRT — the very test that decides whether a band
is a stim-stable closed-loop anchor.

**Severity high:** directly affects the stim-stability verdict used for deployment-anchor selection.

**Fix:** in `band_stim_stability`, use LOCF — `idx = np.searchsorted(stim_t, t_epoch, side="right") - 1`
(clipped to ≥0), or `scipy.interpolate.interp1d(kind="previous")` — to match the offline (and physically
correct) carry-forward semantics.

---

## 8 — Claimed-but-missing  ·  OK (all present)

Every item the session claimed to ship is present at HEAD `bb64b9b`:

| Claim | Status | Location |
|---|---|---|
| (a) PRO-first matcher in `_match_to_pro` w/ `channels`/`max_per_rating` | **present** | `streaming_psd.py:337-338,380-417` |
| (b) `DEFAULT_MATCH_TOLERANCE_MIN = 60.0` | **present** | `bravo_service.py:1550` |
| (c) three-way `MatchDirection` parser at BOTH parse sites | **present** | `bravo_service.py:1857-1863` and `2373-2379` |
| (d) `survey_usage` `psd_per_pro_{mean,median,max}` | **present** | `streaming_psd.py:713-726` |
| (e) frontend `binarizationModel.js` `pro_first` branch | **present** | `binarizationModel.js:149` |
| (f) `BinarizationPreview.js` PRO-first captions/badges | **present** | `BinarizationPreview.js:129-347` |

**Fix:** none.

---

## Recommended fix priority

1. **§7 stim interpolation (HIGH)** — flip live `band_stim_stability` to LOCF; affects the closed-loop
   stim-stability verdict.
2. **§6 glmer era + binarization basis (MED)** — align `band_mixedmodel_inference` cluster derivation
   and per-channel binarization to phase2 so click-validate OR/CI/p reproduce the validated set.
3. **§2 timezone (MED)** — route `availability.pain_series` and `adapter` PRO readers through
   `_pro_timestamps_utc`; timeline-display + legacy-chronic-detector alignment only.
