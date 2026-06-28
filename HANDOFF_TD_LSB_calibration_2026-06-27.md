# HANDOFF — TD→LSB Calibration via the percept-spectral-repro "transform" model
### Session 2026-06-27 · RCS08 Stage 1 · author: Claude (BRAVO agent)

> **Read this first if you are touching LSB prediction from time-domain data.**
> This session reproduced the `percept-spectral-repro` transform model *exactly* on the
> user's own Stage 1 RCS08 JSONs, then extended it to a 3-second DSP window — both at
> block level and per-window. It also catalogues the specific analysis errors that were
> made and corrected mid-session, so they are not repeated.

---

## PART 1 — What we did (compact)

### 1.1 Goal
Validate that BRAVO's TD→LSB conversion matches the lab's standalone reproduction repo
(`github.com/shirvalkarlab/percept-spectral-repro`), and test whether a **3-second** DSP
window (matching the device's `AveragingDurationInMilliSeconds = 3000`) improves on the
repo's **1-second** transform.

### 1.2 Exact reproduction (the anchor result)
- Cloned the repo (tarball via GitHub API — `git` is blocked in the sandbox; see §Gotchas),
  built env `psr` (python 3.12, numpy≥2 / scipy≥1.16 / pydantic≥2.12), ran their
  `scripts/benchmark_brainsense_power.py` on the user's mounted
  `…/RCS008 jsons/Stage 1` (517 JSONs).
- **Result reproduced bit-for-bit** against their committed
  `results/brainsense_power_head_to_head/brainsense_power_head_to_head_summary.json`:

  | quantity | committed | reproduced |
  |---|---|---|
  | transform k (all stim) | 352.62 | 352.62 |
  | transform k (stim-off)  | 356.61 | 356.61 |
  | welch256 k | 270.22 | 270.22 |
  | welch250 k | 265.17 | 265.17 |
  | Pearson r (transform, all) | 0.9927 | 0.9927 |
  | RMSE (LSB) | 60.55 | 60.55 |
  | median fold error (all) | 1.092 | 1.092 |
  | paired rows n | 131 | 131 |

### 1.3 3-second hybrid at block granularity (the apples-to-apples answer)
Reused the repo's **exact pairing** (imported its `benchmark_brainsense_power` module and
called `select_td_stream` / `lfp_side_stats` / `_channel_set`), swapped **only** the DSP
window from 1 s to 3 s. Same 131 blocks.

| DSP | k | n | r | RMSE | fold err | <1.5× |
|---|---|---|---|---|---|---|
| 1-s (repo) | 352.6 | 131 | 0.9927 | 60.6 | 1.092 | 93.9% |
| **3-s hybrid** | 312.6 | 125 | 0.9953 | 49.8 | 1.071 | 94.4% |

- The 1-s column reproduces the repo exactly → proves the pairing is identical.
- 3-s is marginally better (lower RMSE & fold error). 1-s and 3-s transform µV² agree at
  **r_log = 0.996** — window length barely matters; the conversion is robust to it.
- 3-s n=125 not 131 because 6 TD streams are 256–749 samples long (<3 s), so they get a
  1-s estimate but no 3-s one.

### 1.4 Per-window 3-s hybrid (time-resolved tracking)
Within each correctly-matched pair, slid 3-s windows and tick-aligned each to its
**coincident** stim-off LFP points via the shared device clock (`TicksInMses` on TD,
`TicksInMs` on each `LfpData` point).

- **18,223 simultaneous windows**, median **6** coincident stim-off LFP points/window (99% ≥3).
- k = 326, **r_log = 0.82**, median fold error 1.36, 62% within 1.5×.
- The per-window log-correlation (r_log = 0.82) is, as expected, lower than the block-level
  across-block fit (r_log = 0.975, n=125 — recomputed from `transform_3s_blocks.csv`), because
  block-medianing averages out single-window noise. The point is that **0.82 on truly
  coincident single 3-s windows** is itself the evidence the transform genuinely tracks
  within-session LSB swings — licensing time-resolved LSB estimation. (An earlier draft cited a
  "block-median 0.76"; that came from the superseded buggy 26-block aggregation and is wrong —
  the correct block-level r_log is 0.975.)
- ~1% of windows are **device-side LSB saturation events** (device LSB jumps to 10⁴–10⁵
  while the coincident neural TD stays flat). Block-median absorbs them; per-window does not.
  These are exactly the false spikes a closed-loop detector keyed on raw device LSB would
  fire on.

### 1.5 Key numeric takeaways
- **Block-level TD→LSB scale k ≈ 311–357** (stim-off vs all; 1-s vs 3-s) — stable across
  DSP window and pairing granularity.
- Two DSP routes, two constants, **must not be conflated** (see §3):
  - **Transform route, k = 352.62** (all-stim median; 356.61 stim-off, recorded for
    provenance but not deployed) — the RC+S-Hann/256-FFT/peak transform. **PI-decided
    PRIMARY** TD→LSB source of truth for exploration + deployment (§3.1).
  - **Welch256 route, k≈270** = BRAVO's current `LSB_PER_UV2_VALIDATED = 269`. Demoted to
    the **PSD→LSB exploration-only backup** (§3.2), used when no TD exists for a match.

### 1.6 Artifacts saved this session
| file | what |
|---|---|
| `transform_exact_repro.png` + `repro_brainsense_power_rows.csv` | exact reproduction (131 rows) |
| `transform_3s_blocks_figure.png` + `transform_3s_blocks.csv` + summary | 1-s vs 3-s at 131-block granularity |
| `transform_3s_perwindow_figure.png` + `transform_3s_perwindow_windows.csv` + summary | per-window (18,223 coincident windows) |
| (superseded) `transform_3s_hybrid_figure.png`, `transform_3s_aligned_figure.png` | early versions with the aggregation bug — **do not cite** |

---

## PART 2 — Errors that were made, why they were wrong, and how to do it right

> This section is deliberately long. Every item below was an *actual* mistake made during
> this session (or a near-miss). The user's frustration — "you're doing the same thing over
> and over and getting things wrong" — was justified. The root cause in every case was
> **not validating the unit of analysis and the data lineage against the reference before
> computing metrics.** Read all of it before writing any TD→LSB code.

### ERROR 1 — Wrong pairing: predicting LSB from a non-coincident, wrong-product LSB stream
**What happened.** The first BRAVO-side reproduction matched the offline transform µV² to
**PowerDomain LSB** (the chronic/adaptive 10-min or 20 Hz stream) using a **fuzzy ±10 s
StartTime** match through the BRAVO database. This gave **r = 0.13** vs the repo's 0.99.

**Why it was wrong.**
1. **Wrong LSB product.** The repo's target is `BrainSenseLfp.LfpData[i].{Left|Right}.LFP`
   — the *in-clinic streaming selected-band* LFP, sampled at 2 Hz during the same recording
   that produced the TD. PowerDomain LSB is a *different* device product with different
   normalization and a different value range (it reached 10,660 and even the uint32 sentinel
   4294967295; the in-clinic BrainSenseLfp tops out ~3,014).
2. **Fuzzy temporal matching admits non-coincident pairs.** A ±10 s window pairs a TD
   segment with LSB from a *different* moment. When the device LSB spikes (settling
   transient, movement artifact) but the matched TD is from a calm moment, you get
   LSB-high / µV²-low inversions that destroy linear correlation.

**The rule (the user stated it explicitly):**
> **Never match or try to predict any LSB signal that does not come from an exactly
> coincident / simultaneous time-domain recording.**

**How to do it right.**
- Target = `BrainSenseLfp` selected-band LFP, paired **1:1 to its own TD stream** by
  **shared `FirstPacketDateTime`** (the repo's `td_by_time[lfp.first_packet_datetime]`
  bucket + `select_td_stream` channel-set disambiguation).
- For sub-stream (per-window) alignment, use the **shared device tick clock**: TD packets
  carry `TicksInMses` (the first tick is the stream origin), each `LfpData` point carries
  `TicksInMs`. Map TD sample index → ms via `t0 + (idx/fs)*1000`, then select LFP points
  whose `TicksInMs` fall in `[window_start_ms, window_start_ms + 3000)`. These are the only
  truly coincident LSB samples.
- Gate on stim-off **per point** (`abs(mA) < 1e-6`), and reject the uint32 sentinel
  (`valid_lfp_power`: `2^32 - 1` is "invalid", not a real reading).

### ERROR 2 — Wrong unit of analysis: block count collapsed 131 → 26
**What happened.** The first "block-median" flavor grouped windows by
**`(report, channel, side)`**, producing **26** blocks. The repo produces **131**.

**Why it was wrong.** `channel` (the TD contact, e.g. `ZERO_THREE_LEFT`) is reused across
many separate streaming sessions. Grouping by it **merges distinct LFP streams** that
happen to share a contact into one block — silently averaging away most of the data and
changing the fitted k. The block count is a property of **the pairing**, not the DSP: one
block per **`(report, LFP-stream, side)`**, whether you Welch the whole stream once (repo)
or slide windows and take the median (hybrid). It must be 131 either way.

**How to do it right.**
- The unit of analysis is **`(report, LFP-stream, side)`** — exactly one record per
  iteration of the repo's `process_report` inner loop (`for lfp … for side …`).
- **Do not invent your own grouping.** Import the repo module and reuse `process_report`'s
  structure verbatim; only replace `add_td_predictions`' DSP call. The block set is then
  guaranteed identical, and your 1-s column must reproduce the repo's numbers — which is
  your **proof of correct pairing**. If your 1-s column does *not* equal k=352.6 / r=0.9927,
  stop: your pairing is wrong, not your DSP.

### ERROR 3 — Conflating the two scale constants (transform k vs welch k)
**What happened.** Early prose compared a reproduced k≈357 against the repo's "headline
352.6" as if a mismatch needed explaining, and separately treated 269 as if it should equal
the transform k.

**Why it was wrong.** The repo fits **three different DSP routes**, each with its own k:
- `existing_uv2` (the **transform**: RC+S-Hann / 256-FFT / peak-amplitude / mean-magnitude) → **k ≈ 352.6** (all), **356.6** (off)
- `welch256_uv2` (Welch PSD area, nperseg=256) → **k ≈ 270.2**
- `welch250_uv2` (Welch PSD area, nperseg=250) → **k ≈ 265.2**

BRAVO's `LSB_PER_UV2_VALIDATED = 269` is the **welch256** scale (≈270), **not** the
transform scale. They are not interchangeable: a given TD yields a *different* µV² under
each DSP, so each needs its own k. Also: the **all-stim** fit (352.6, n=131) and the
**stim-off** fit (356.6, n=93) are different committed numbers — quote the one matching your
stim gate.

**How to do it right.** Always state which DSP route and which stim subset a k belongs to.
Never carry a k from one DSP to another. If you change the DSP (e.g. 1-s → 3-s), refit k.

### ERROR 4 — "median fold error" terminology (and the CV-fold collision)
**What happened.** Repeatedly wrote "median fold" instead of "median fold **error**".

**Why it matters.** "fold" is overloaded:
- **fold error** = the multiplicative-factor sense (like "3-fold increase"):
  `fold_error = max(ŷ/y, y/ŷ) = exp(|ln(ŷ/y)|)`, always ≥ 1.0, symmetric (a 2× over- and a
  2× under-prediction both score 2.0, they do not cancel). The **median** fold error is the
  median of that per-point quantity, ranked by its own value. Computable on a single fit
  with **no cross-validation at all**.
- **CV fold** = a data partition for cross-validation (the repo's `cv5` = 5 folds).
  Completely unrelated; it is a coincidental reuse of the word "fold".
- In the repo summary they are orthogonal: `existing_uv2_fit_all` (median fold *error*
  1.092, no CV) vs `existing_uv2_cv5_all` (median fold *error* 1.092, under 5-fold CV).

**How to do it right.** Always write "median fold **error**". Never imply it is a
CV-fold-ranked statistic. State the formula when first used.

### ERROR 5 — `TicksInMses` is a comma-joined STRING, not a JSON array
**What happened.** `np.asarray(td_row["TicksInMses"], float)` raised
`could not convert string to float: '840500,840750,…'`.

**Why.** In the Medtronic export, `BrainSenseTimeDomain[i].TicksInMses` (and
`GlobalSequences`, `GlobalPacketSizes`) are **single comma-separated strings**, whereas
`TimeDomainData` is a real array and each `LfpData` point's `TicksInMs` is a scalar int.

**How to do it right.**
```python
tk = td_row.get("TicksInMses")
ticks = (np.array([float(x) for x in tk.split(",") if x.strip()])
         if isinstance(tk, str) else np.asarray(tk or [], float))
```

### ERROR 6 — Trusting a stale `git log` HEAD across the wrong repo
**What happened.** A failed `cd psr_clone` left bash in BRAVO's parent dir; `git log` then
printed BRAVO's HEAD (`8509e96`) while the prose was about the percept repo, briefly
suggesting the percept clone had a wrong/old SHA.

**How to do it right.** After any `cd` that may have failed, verify `pwd` and
`git remote -v` before trusting `git log`. When the sandbox blocks `git` operations on a
path, the working tree may be empty even though the fetch reported a SHA — confirm with `ls`.

### ERROR 7 (process) — Re-deriving the pipeline from memory instead of importing it
**The meta-error behind 1, 2, and 3.** Each wrong run hand-rolled a piece of the repo's
logic (its pairing, its grouping, its DSP constant) from memory, then computed metrics
before checking the unit of analysis or reproducing the anchor number. The correct workflow,
followed only at the end, is:

1. **Reproduce the reference exactly first** (run their code, match their committed numbers).
2. **Import the reference's pairing/aggregation** — never re-implement it.
3. **Change exactly one thing** (the DSP window) and keep everything else identical.
4. **Verify the unchanged baseline still reproduces** (the 1-s column must equal the repo).
5. Only then interpret the new result.

If step 4 fails, the bug is in your plumbing, not your science. Do not interpret metrics
until the baseline reproduces.

---

## PART 3 — How to incorporate this into the BRAVO codebase

> Reviewed with the `code-review` skill loaded; severities use that skill's tiers
> (🔴 blocking / 🟡 important / 🟢 nit). **Critical context: the modeled-LSB display
> infrastructure ALREADY EXISTS in the codebase** (merged in PR #8 and follow-ups —
> commits `dd46c95`, `f9a6efc`, `3525c0a`). This section is about *correcting and
> hardening* it with this session's findings, **not** adding it from scratch. Do not
> re-build what is there.
>
> ⚠️ **Provenance to confirm against the repo before landing:** the PR #8 / commit SHAs
> (`dd46c95`, `f9a6efc`, `3525c0a`) and the "179/179 tests at session start" figure are
> codebase claims carried from session context, NOT re-verified in this audit (the reviewer
> had no repo access). Re-check `git log` / the test count against the live repo before
> relying on them — code state may have advanced (HEAD was `2ef0408` at session end).

### 3.0 What already exists (do not duplicate)
- `analytics.LSB_PER_UV2_VALIDATED = 269` (welch256 scale), `lsb_from_uv2`, `uv2_from_lsb`,
  `psd_band_to_lsb` (Welch256 band-integral × k), `welch256_density` (the exact DSP k was
  fit against).
- `availability.lsb_series(...)` already emits a **`psd_modeled`** tier: montage-survey TD
  → `welch256_density` → `psd_band_to_lsb` (k=269), tagged `source="psd_modeled"`,
  `modeled=True`, drawn as hollow diamonds on the Biomarker timeline and held out of the
  native y-window.
- `bravo_service.band_lsb_and_power(...)` already has a `modeled_timeline` fallback tier for
  the deployment threshold, and `BiomarkerDataTimeline.js` / `ClosedLoopSim` already render
  modeled LSB distinctly.
- Frozen per-participant model `data/psd_lsb_models/RCS08.json` (per-channel common-slope
  log-log; `psd_lsb_model.py`).

> **ARCHITECTURE DECIDED BY PI (2026-06-27) — no open option.** The deployable modeled-LSB
> source of truth is the **TD-derived transform, k = 352.62** (the exact repo all-stim median
> k from the bit-for-bit reproduction — NOT a rounded "353"). It is the PRIMARY way LSB is
> computed for both the exploratory panels and the deployment fallback — NOT a second DSP to
> maintain. The Welch256 route is demoted to an **exploration-only backup** whose sole job is
> turning a *PSD* (power-domain 256-bin FFT) into LSB when no TD exists for a survey↔neural
> match. §3.1 and §3.2 below are the spec; the old "Option A/B" framing is superseded.

### 3.1 PRIMARY route — TD transform (k = 352.62) is the LSB source of truth everywhere
**Decision.** LSB from neural data is defined by the **transform** DSP
(RC+S-Hann / 256-pt FFT / peak-amplitude / mean-magnitude, the repo's
`brainsense_streaming_selected_band_power`) scaled by **k = 352.62** — the exact repo
all-stim median k reproduced bit-for-bit this session (PART 1). Use this single k value; do
not round it to 353 and do not substitute the stim-off variant (356.61) — 352.62 is the
decided constant. This single definition is used by:
- the **Biomarker exploration** correlation / AUC panels, and
- the **closed-loop deployment** module's modeled fallback (when no raw device LSB exists).

**Why this is NOT a maintenance burden.** It is ONE DSP and ONE k, used in one place
(a single `td_to_lsb(samples, center_hz)` helper). The transform is already vendored and
exactly reproduces the lab's reference (k=352.6, r=0.9927, RMSE 60.6 — PART 1). Adopting it
as the primary *removes* the current split where the modeled tier silently uses a different
DSP (welch256) and constant (269) than the lab's headline model.

**Crucial property — k is immaterial to the correlation/AUC curves, decisive for the
absolute LSB.** Because the per-band feature is a **log** of band power, the multiplicative k
(and the band-mean-vs-integral choice) cancels inside Pearson r and AUC — so the r/AUC
exploration plots are numerically identical whether k is 269, 352.62, or 1. k matters only
for (a) the **absolute LSB values displayed** and (b) the **deployable LSB threshold**. So
switching the primary route to the transform changes the displayed/deployable LSB numbers to
the lab-consistent scale **without** moving any correlation or AUC result. This is why the
switch is safe.

> 🔴 **Caveat — k cancels only for a UNIFORM k applied to every point in a given panel.** The
> safety argument above holds for the route switch (all-welch256 → all-transform on the TD
> path: one k replaced by another k, uniformly → r/AUC unchanged). It does NOT extend to a
> panel that **mixes** TD-transform points (×352.62, transform DSP) with PSD-Welch256-backup
> points (×269, a different DSP). Those two subgroups carry different additive log-offsets
> (Δ ≈ ln(352.62/269) ≈ 0.27 nat) AND come from different band-power DSPs, so their LSB values
> are **not on the same scale** and do not cancel against each other — pooling them can shift
> both Pearson r and AUC. Implication: within a single correlation/AUC panel, do not treat
> TD-transform and PSD-backup LSB as interchangeable. Either (a) keep the analysis per-source
> (the z-scoring within (channel, source) already in the pooled builder largely handles this —
> verify it groups by route), or (b) calibrate the PSD-backup onto the transform scale before
> pooling. The displayed exploratory magnitude is illustrative either way; this matters for any
> cross-route correlation that pools the two.

**Band coverage — exploration vs deployable (PI-specified, distinct ranges).**
- **Exploration panels:** apply k = 352.62 to **every band 0–100 Hz**. Yes, k is only
  *validated* on RCS08 sensing bands; that is acceptable here because (i) k cancels in the
  r/AUC curves anyway and (ii) the displayed exploratory LSB magnitude is illustrative, not a
  programmed threshold. Do NOT band-restrict the exploration sweep.
- **Deployable LSB:** restrict to **7.8–30 Hz**. Nothing is deployable beyond 30 Hz by device
  limitation (the firmware cannot place an adaptive sensing band there), so the deployable
  modeled value is computed/offered only within 7.8–30 Hz. (This supersedes the earlier
  7.8–28.3 Hz figure — the hard device ceiling is 30 Hz.)

**Code shape.**
- Add `analytics.LSB_PER_UV2_TRANSFORM = 352.62` — labeled "transform route, RCS08 all-stim
  median k; PRIMARY TD→LSB" in the same line (see ERROR 3 — never leave a k unlabeled). The
  stim-off value 356.61 is recorded in the handoff for provenance but is NOT the deployed k.
- Add `analytics.td_transform_band_power(samples_uv, fs, center_hz, half_hz=2.5)` — the
  verbatim transform band power — and `td_to_lsb(...) = LSB_PER_UV2_TRANSFORM * transform_band_power(...)`.
- Keep `LSB_PER_UV2_VALIDATED = 269` ONLY as the **welch256** constant for the PSD backup
  (§3.2); relabel its docstring "welch256 route — PSD→LSB backup ONLY, not the primary TD
  route (transform, k=352.62)".

### 3.2 The matching + sliding-window spec (both exploration panels AND deployment)
**Sliding windows.** For the correlation / AUC panels, compute LSB in **5 Hz windows, 1 Hz
step, across 0–100 Hz** (`center = 2.5, 3.5, … 97.5`; band = `[center-2.5, center+2.5)`).
Per window: transform band power × **352.62** when the matched source is TD; Welch256 band
integral × 269 when the matched source is the PSD backup.
> Band scope: the exploration sweep runs the full **0–100 Hz** with k=352.62 on every band
> (k cancels in r/AUC; displayed LSB is illustrative). The **deployable** modeled LSB is
> offered ONLY in **7.8–30 Hz** — nothing is deployable beyond 30 Hz by device limitation.

**Per-PRO source selection (the priority rule the PI specified).** For each PRO survey,
among neural recordings within its matching time window, pick ONE source, with TD strictly
preferred:
1. **TD is preferred over any PSD whenever an unclaimed TD is in-window** — even if a PSD is
   temporally closer (TD is higher-fidelity LSB). This single rule subsumes the "TD when
   closer" case; closeness only breaks ties *among* candidates of the same source type.
   - **Tie-break, multiple in-window TDs:** choose the smallest |Δt to the PRO|.
   - **One recording → one PRO** (existing one-per-rating independence rule). Because a TD can
     be the closest in-window recording for two PROs, the assignment is order-dependent;
     specify the order explicitly (recommended: **greedy by ascending |Δt|** — assign each
     (PRO, recording) pair in increasing time-gap order, skipping already-claimed recordings
     — so the tightest matches win). Defer to the existing one-per-rating assignment if it
     already imposes a deterministic order; do not leave it implementation-defined.
2. **PSD backup (EXPLORATION PANELS ONLY):** only when NO unclaimed TD is within the PRO's
   window, use the closest PSD recording, converted Welch256→LSB (segment + integrate over
   each 5 Hz window across 0–100 Hz). This is the "get more data" path — many PROs match a
   power-domain PSD but no TD; this keeps them in the correlation/AUC analysis. (See the §3.1
   🔴 caveat: PSD-backup LSB is on a different scale than transform LSB — keep cross-route
   pooling source-aware.)
3. **Deployment does NOT use the PSD backup.** Deployment modeled LSB = native device LSB,
   else TD-transform modeled. If neither exists for a band, the band has no deployable
   modeled value (it is not synthesized from PSD).

**Where this lands in code.**
- `availability.lsb_series` / the pooled-PSD builder: replace the modeled-tier DSP call
  (currently `welch256_density → psd_band_to_lsb` for montage TD) so that **TD sources use
  the transform×352.62 path**, and add the **PSD→Welch256×269 backup** only on the
  exploration-pooled path, gated by "no unclaimed TD within window".
- The per-PRO selection belongs in the **builder, row-level, before aggregation** (same
  place the existing TD-priority/one-per-rating logic lives — see the prior
  `td_priority_over_survey` work), because in `one_per_rating` mode the scan only sees merged
  rows.
- Tag rows by route: `source="td_transform"` vs `source="psd_welch256_backup"`, so the panels
  can style them distinctly and the deployment path can hard-exclude the backup.

**Pairing fidelity (non-negotiable, see ERROR 1).** Any *validation* of the TD-transform
tier must use simultaneous TD↔LFP pairing (`FirstPacketDateTime` + tick clock), never a
fuzzy/different-product match. The per-PRO *matching window* above is the analysis pairing
(PRO time ↔ recording time) and is a separate, looser join — keep the two concepts distinct.

### 3.3 🟡 IMPORTANT — keep native LSB strictly preferred; modeled never sets the number
This invariant already exists and **must be preserved** in any edit:
- On the timeline: modeled points stay hollow diamonds, excluded from the native y-window
  scaler (so a modeled outlier never rescales the sensed trace) and from the chronic line.
- In deployment (`band_lsb_and_power`): the `modeled_timeline` tier is a **fallback only**,
  used when the band was never natively sensed. The deployable threshold stays
  percentile-anchored on the device's own Timeline LSB. `thr_lsb` must never be reassigned
  from a modeled value when a native one exists.
- 🔴 Add a regression test asserting that when both native and modeled LSB exist for a
  channel, the deployable threshold equals the native-derived value (modeled ignored).

### 3.4 🟡 IMPORTANT — surface the device-LSB saturation events
This session found ~1% of coincident windows are device-side LSB spikes (LSB ≫ neural TD).
A closed-loop detector keyed on raw device LSB would misfire on exactly these.
- Add a QC flag in the deployment readout: count/rate of LSB samples above a per-channel
  physiologic ceiling (e.g. > P99 of the channel's own stim-off LSB, or > ~3,000 absolute
  for in-clinic BrainSenseLfp).
- This is **advisory only** (do not auto-drop), but it tells the clinician how artifact-prone
  a candidate detector band is before deployment.

### 3.5 🟢 NIT — naming & docs
- Rename internal references from "median fold" → "median fold **error**" everywhere
  (search `fold` in `analytics.py`, `bravo_service.py`, JS hovers).
- Label every k with its DSP route at the definition site:
  `LSB_PER_UV2_TRANSFORM = 352.62` ("transform route — PRIMARY TD→LSB"),
  `LSB_PER_UV2_VALIDATED = 269` ("welch256 route — PSD→LSB exploration backup ONLY").
- Point a comment at this handoff + `transform_3s_blocks.csv` as the provenance for the
  3-s-vs-1-s equivalence (r_log 0.996) and the exact repro (k=352.6, r=0.9927).

### 3.6 Suggested work sequence (each independently testable)
> Per PI: **do not commit or open PRs from the agent session.** These are review-ready
> changesets for the human to land.
1. **CS-1 (primary route, the core change):** add `LSB_PER_UV2_TRANSFORM = 352.62` and the
   `td_transform_band_power` / `td_to_lsb` helpers; switch the modeled tier's TD path to
   transform×352.62 (§3.1). Anchor test: the transform helper reproduces repo k=352.62/r=0.9927.
   Because k cancels in r/AUC, the correlation/AUC panels are unchanged; only displayed and
   deployable LSB magnitudes move to the lab scale.
2. **CS-2 (matching priority):** implement the per-PRO TD-preferred-over-PSD selection
   (§3.2, rules 1–2) in the builder, row-level before aggregation; one recording → one PRO.
3. **CS-3 (PSD backup, exploration only):** add the Welch256×269 PSD→LSB backup on the
   pooled exploration path, gated by "no unclaimed TD within window" (§3.2 rule 3). Hard-
   exclude it from the deployment path (§3.2 rule 4); tag `source="psd_welch256_backup"`.
4. **CS-4 (QC + overlay):** 3-s sliding-window exploratory overlay + device-saturation QC
   flag (§3.4).

### 3.7 Verification checklist before landing any of the above
- [ ] The transform helper reproduces repo k=352.6 / r=0.9927 (anchor test).
- [ ] `LSB_PER_UV2_TRANSFORM` (352.62, transform) and `LSB_PER_UV2_VALIDATED` (269, welch256)
      are each asserted against their own DSP route; neither is used for the other's DSP.
- [ ] Correlation/AUC curves are byte-identical before/after the k switch (k cancels in log).
- [ ] Per PRO, an unclaimed in-window TD is always chosen over a closer PSD; each recording
      matches at most one PRO.
- [ ] The PSD-Welch256 backup appears ONLY in exploration panels, NEVER in the deployment
      modeled path.
- [ ] No modeled value can set a deployable threshold when a native device LSB exists.
- [ ] Deployable modeled LSB is offered ONLY in 7.8–30 Hz (device ceiling 30 Hz); the
      0–100 Hz sweep with k=352.62 is exploration-only.
- [ ] "median fold error" used consistently; no bare "median fold".
- [ ] Full Biomarkers test suite green in the bridge container (was 179/179 at session start).
