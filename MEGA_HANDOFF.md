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
> **HEAD `b06b0e2`** (biomarker matching: TWO-WINDOW MODALITY SPLIT + cache-only path). The two match
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
