# BRAVO pain biomarker pipeline — design ledger v2, revision 13

*Working document. Consolidates the device constraints, the data-stream analysis, the
cross-references, and the open decisions from the rethink session. Nothing here is built yet —
this is the spec we build against.*

*Revision 12, 2026-09-06 — added §8f: the three-source comparison of how stimulation current moves
band power (voltage trace vs the device's own spectrum vs the device's own band power), built and
rendered live on RCS08. Records what each source is, the five honesty constraints with the PI's
acceptance of all five on 2026-09-06, how the design makes each visible, why the ladder of currents
is read from the device's own current record rather than the clinic testing sheet, what was found on
the 2026-08-18 visit, and what the panel deliberately does not do (gate anything, or claim the three
sources are independent). Nothing else in this document was changed.*

---

## 0. The reframing (why we are redoing this)

The prior module optimized a biomarker in the abstract (a threshold on the best band). The deliverable
for closed loop is a **device-implementable controller spec**, and the device is the **Percept RC**, not
the Summit RC+S the trial deployed on. The pipeline must be designed around what the Percept RC actually
implements.

**Firmware decision (confirmed):** we have investigational permission to configure pain patients in
**Parkinson's adaptive mode**. So the full adaptive engine is available — but we are bound to the PD-mode
parameter ranges, fixed per-mode timing, and the **8–30 Hz adaptive sensing range**.

**Module split (confirmed):**
- **Biomarker module** (this doc) — owns Discover → Commit-to-band → Binarize/Threshold. Output: a
  validated band-candidate object.
- **Closed-Loop Simulation module** (separate, future) — consumes the band-candidate + time series,
  emulates the Percept state machine, scores against pain. Not built here.

The contract between them is one serializable **band-candidate object** (schema in §6).

---

## 1. Percept RC controller facts (from Medtronic white paper UC202012929dEN, verify against firmware)

One power band in, 1–2 thresholds out. Not a multi-feature LDA. Per-mode fixed timing:

| Parameter | Dual Threshold | Single Threshold | Single Thr. Inverse |
|---|---|---|---|
| Adaptive? | Yes | Yes | Sensing only |
| Control law | LFP↑ above upper → stim ramps **up**; below lower → ramps **down** | LFP↑ above → stim up; below → down | n/a |
| Reaction | minutes | milliseconds | n/a |
| Adaptive band | 8–30 Hz | 8–30 Hz | 1–96 Hz (sensing) |
| FFT size | 256 pt | 64 pt | 256 pt |
| FFT update | 5 Hz | 20 Hz | 2 Hz |
| Averaging | 1200 ms | 100 ms | 3000 ms |
| Onset | 1200 ms | 200 ms | n/a |
| Blanking | 2000 ms | 550 ms | n/a |
| Transition up/down | 2.5 / 5 min | 250 / 250 ms | n/a |

**Polarity (corrected):** the table's "high LFP ↔ low stim" is the equilibrium correlation (stim
suppresses biomarker), NOT the control law. The control law ramps stim UP when LFP exceeds the upper
threshold. So a **positively-pain-correlated** biomarker maps naturally onto Dual/Single adaptive mode —
no ±1 inversion (which RC+S had and Percept does not).

**The real subtlety the sim module must catch:** Percept adaptive assumes **negative feedback** — that
stimulation drives the biomarker back across threshold. True for PD beta. For a pain biomarker it holds
only if **stim actually moves that biomarker**, not just the pain. If the biomarker tracks pain state but
is stim-unresponsive, the loop can stick "on" → why the 3-state Dual config + blanking exist, and why
offline simulation against ambulatory data is required before deployment. (Same point as the Frontiers
negative-feedback / two-threshold argument.)

**Data-fidelity facts:**
- Timeline = **10-min averaged** power; crossing decisions = 1200 ms / 100 ms. Cannot validate a fast
  threshold against Timeline alone.
- LFP Power is unitless LSB (~0.01 µV²/LSB rule of thumb); **not comparable across center freqs or
  threshold modes** (different FFT sizes). Cross-band ranking must normalize or stay within-band.

---

## 2. The three power-domain streams (verified on RCS08 JSONs)

Decision: **time-domain is discovery-only (scarce); the deployed decoder is power-domain.** Combine the
three power streams.

| Stream | JSON key | Unit | Window T | Label | Band |
|---|---|---|---|---|---|
| Timeline (chronic) | `DiagnosticData.LFPTrendLogs[hemi]` | LSB | **600 s** (verified) | timestamp-join, loose | locked to programmed |
| Streaming (in-clinic) | `BrainSenseLfp.LfpData` (+`BrainSenseTimeDomain`) | LSB (+250 Hz µVp) | ~1–3 s | in-clinic task | **full 0–125 Hz PSD** from 250 Hz TD (CONFIRMED) — NOT band-locked for discovery |
| Events (snapshots) | `DiagnosticData.LfpFrequencySnapshotEvents[i].…[hemi].FFTBinData` | µVp PSD | **30 s, +30 s AFTER press** | time-locked, corroboration | any band (full PSD) |

**Discovery streams (full PSD): Events + streaming on-demand.** Both expose the full 0–100 Hz spectrum, so
both feed the spectral feature-importance scan (§8b). The device's *programmed* `BrainSenseLfp` scalar and
Timeline are band-locked (deployment), but the underlying streaming TD is not.

**Bonuses found in the data:**
- Streaming `LfpData` carries **per-sample `mA`** → direct stim ground-truth. `TherapySnapshot` carries
  full adaptive config (thresholds, averaging, onset, transitions, active electrodes, `FrequencyInHertz`).
- Event `EventName` confirms scheduled-prompt protocol: "Higher Pain" (n=26 pooled), "High Pain",
  "Lower Pain", "Feeling Good", "Tingly/Burning", etc. Snapshot timestamp = press + 30 s.

---

## 3. Measured stream statistics (RCS08, Left, ~8.8 Hz ±2.5 Hz band)  → fig `stream_integration_analysis.png`

**Integration-window precision law:** CV ≈ 1/√(T·B), B=5 Hz.

| Stream | T | K=T·B | CV floor | CV observed |
|---|---|---|---|---|
| Timeline | 600 s | 3000 | 1.8% | 32.5% |
| Events | 30 s | 150 | 8.2% | 62.4% (across states) |
| Streaming | 3 s | 15 | 25.8% | 30.8% |

**Findings:**
1. Observed ≫ floor everywhere → the spread is **real physiological/pain fluctuation**, not estimator
   noise. Timeline's 10-min averaging has already removed nearly all estimator noise.
2. Event CV of 62% is **across pain states**. Within-state CV is **heterogeneous, not uniformly tight**:
   the largest pain class (Higher Pain, n=26) is **60.4%**; Feeling Good 32.8%, Feeling Off 56.3%; only
   the small classes are tight (High Pain n=10 → 5.2%, Tingly n=10 → 4.6%, Lower Pain n=4 → 0%). The tight
   ones are small-n and may be single-session/single-burst, so they do NOT generalize to "events are clean
   enough to set thresholds." → **Events are noisy at the single-snapshot level and are used to
   CORROBORATE the biomarker, not to define it or set the deployed threshold.** (Consistent with the
   label-source decision: REDCap PROs define; events corroborate.)

**Weighting rules (the answer to "how to balance the windows"):**
- For **discovery**: inverse-variance weight ∝ K = T·B (Timeline dominates point-stability).
- For **threshold-setting**: the deployed threshold is anchored to the **deployment stream** (Timeline /
  adaptive power in LSB), since that is the only stream the device adapts on in the wild. Streaming (~1–3 s,
  closer to the device decision window of 1200/100 ms) calibrates the crossing-frequency expectation;
  Events corroborate band choice but are not used to set the cut.
- Unifying form: **hierarchical / mixed-effects model** — pain as fixed effect on band power; stream /
  session / center-freq / **stim-context** as random effects; per-stream residual variance.

---

## 4. LSB ↔ µV² conversion — the sanity check (must live in the pipeline as an FYI)

- Medtronic rule of thumb: 1 LSB ≈ 0.01 µV².
- **Empirical** (concurrent streaming TD + device LSB, same channel/band, 0 mA): **≈0.0034 µV²/LSB
  ≈ 0.34× rule**. BUT the absolute constant is **normalization-dependent** (moved with Hann window &
  /(N/2) scaling) — trust it no better than ~3×.
- **No LSB↔µV² converter exists anywhere in BRAVO** (grep-confirmed; the only `0.01` hits are p-values /
  filter regularizers / a plot offset). So this is a new capability and the absence is itself a finding.
- The community `perceive` toolbox (`perceive_fft.m`, `perceive_power_normalization.m`) **deliberately
  avoids absolute conversion** — it normalizes to relative power (100·pow/Σpow over 5–45,55–95 Hz) or
  std/sum-normalizes within recording. Independent corroboration of the "standardize within stream;
  treat conversion as a checked FYI, not a calibration" stance.
- **Implementation:** report the empirical ratio + its scatter per overlapping session, and **flag when
  it diverges from 0.01**. The J. Neural Eng. tutorial (ad1dc3) explains WHY it's normalization-dependent
  (ADC is 146 nV/LSB in the *time domain* — distinct from the "LFP Power" LSB; plus 0.5 Hz HP / 100 Hz LP
  analog + elliptic digital filters shape the spectrum).

---

## 5. Confounds & handling

- **Stim contamination (per-sample):** Streaming has per-sample `mA`; Timeline has
  `AmplitudeInMilliAmps` per trend point. Tag stim-on/off directly. (`perceive` flags StimOn when
  `any(amp>0.1)`.)
- **Stim-context heterogeneity over trial history (user flag):** active **contact + stim frequency +
  amplitude** changed across eras (exploratory past vs consistent recent). Volume of tissue activated and
  artifact spectrum differ → a 2024-era stim-on sample is NOT exchangeable with a 2025-era one at the same
  mA. Reconstruct full `(contact montage, stim freq, mA, cycling)` per epoch from `Groups`/`GroupHistory`/
  `TherapySnapshot`; either stratify/standardize within stim-context, or restrict threshold-setting to
  **stim-off** samples and use stim-on only with context as a modeled covariate. Whether the remote-past
  heterogeneity needs correction is **empirically testable** (does biomarker–pain separation differ by
  stim era?) — don't assume.
- **Event selection bias:** scheduled prompts mitigate it, but verify balance of low- vs high-pain labels
  before threshold-setting.
- **Cycling forward-calc:** for Timeline, on/off within a cycling program must be forward-calculated from
  cycling settings + ramp (read Percept RC ramp-vs-cycling interaction). Streaming needs no forward-calc
  (per-sample mA present).

---

## 6. BandCandidate contract (the interface to the sim module) — FINALIZED v1

**The label is REDCap-PRO-defined.** The biomarker is built against one of the module's existing PRO
metrics (`BIOMARKER_METRICS`: nrs, vas, left_leg_vas, back_vas, mpq_sum, composite_mpq_leftleg). Multiple
PRO flavors stay selectable (the menu the module already exposes via `LabelMetric`). **Events corroborate;
they never define the label or set the threshold.** Every candidate is stamped with which PRO metric +
binarization it was built against, so two candidates are only comparable within the same `label` block.

**Selection bias is recorded, not hidden.** The candidate pool is non-uniform by construction (intuition
favored right 0-3 @ ~26.4 Hz, so more data exists there). The schema carries a `provenance` block so
downstream consumers and any cross-candidate ranking know the pool is biased and how.

```python
BandCandidate = {
  # ---- identity (the atomic device unit) ----
  "hemisphere": "Left" | "Right",
  "contact": str,                  # sensing montage, e.g. "ZERO_THREE_RIGHT"
  "center_freq_hz": float,         # snapped to Percept FFT bin (250/256 or 250/64)
  "bandwidth_hz": float,           # ~5 (device band width)
  "snapped_bin_note": str,         # which FFT size the snap assumed (256 Dual / 64 Single)

  # ---- label provenance (REDCap PRO, NOT events) ----
  "label": {
    "pro_metric": str,             # one of BIOMARKER_METRICS keys
    "pro_metric_label": str,       # display label
    "is_composite": bool,
    "composite_parts": [str]|None, # e.g. ["mpq_sum","left_leg_vas"], z-scored blend
    "binarization": {              # mirrors _threshold_pain_level
       "strategy": "median"|"cutoff"|"tertile"|"percentile",
       "pain_cutoff": float|None,
       "low_pct": float, "high_pct": float,
       "daily_broadcast": bool
    },
    "join": "nearest_date",        # PRO(daily) -> sample alignment used
    "n_labeled_days": int, "n_pos_days": int, "n_neg_days": int
  },

  # ---- device-control mapping ----
  "adaptive_valid": bool,          # center_freq within 8-30 Hz adaptive range?
  "adaptive_valid_reason": str,    # e.g. "7.8 Hz below 8 Hz adaptive floor"
  "polarity": "positive"|"negative",   # sign of corr(band_power, PRO pain)
  "suggested_mode": "Dual"|"Single"|None,

  # ---- threshold, in DEPLOYMENT-STREAM LSB (Timeline/adaptive power) ----
  "threshold_lsb": {"upper": float, "lower": float|None},   # None lower => single-threshold
  "threshold_basis": str,          # "Timeline-anchored percentile p=..", etc.

  # ---- unit sanity check (FYI, confidence-rated; §4) ----
  "conversion_check": {
     "ratio_uV2_per_lsb": float|None,   # empirical, from concurrent TD+LSB at 0mA
     "n_overlap_sessions": int,
     "scatter_cv": float|None,
     "rule_of_thumb": 0.01,
     "fold_off_rule": float|None,       # ratio / 0.01
     "diverges": bool,                  # |log2(fold)| large -> flag
     "confidence": "high"|"medium"|"low"
  },

  # ---- evidence (per-stream, de-pooled; stim-context aware) ----
  "evidence": {
     "discovery_auc": float|None,       # TD/Events discovery score (flagged discovery-only)
     "discovery_method": str,           # "ROC"|"LASSO"|"LDA"|"mixed_effects" (TBD which is headline)
     "per_stream_n": {"timeline": int, "streaming": int, "events": int},
     "event_corroboration": {           # corroborate-only: do labeled events agree in sign?
        "n_events_by_label": {str: int},
        "agrees_with_pro_biomarker": bool|None
     },
     "mixed_model_effect": float|None,  # optional; decide later if headline
     "stim_off_only": bool              # was threshold set on stim-off samples?
  },

  # ---- confounds / honesty about the pool ----
  "provenance": {
     "selection_biased": True,          # pool is intuition-narrowed, non-uniform
     "selection_note": str,             # e.g. "right 0-3 ~26.4 Hz over-sampled by design"
     "stim_context_eras": [             # active therapy context per epoch (§5)
        {"start": ts, "end": ts, "contact": str, "stim_freq_hz": float,
         "amp_mA": float, "cycling": str}
     ],
     "stim_era_heterogeneity_tested": bool
  },

  # ---- handoff to the Closed-Loop Simulation module ----
  "timeseries_ref": str   # artifact/pointer to the band's labeled power series (deployment-stream
                          # LSB + per-sample stim mA + PRO label), for state-machine emulation
}
```

**Design rules encoded above:**
1. `label.*` makes the PRO metric + binarization first-class — candidates compare only within a `label`.
2. Events appear ONLY under `evidence.event_corroboration` — never in `label` or `threshold_lsb`.
3. `threshold_lsb` is in deployment-stream units so it can be typed into the tablet.
4. `conversion_check` is advisory and confidence-rated, never a silent calibration.
5. `provenance.selection_biased` is hard-coded True until a balanced pool exists — the schema refuses to
   pretend the candidate set is unbiased.
6. `adaptive_valid` gates whether this candidate can run adaptive at all (8–30 Hz).

---

## 7. Pipeline flow (re-sequenced)

1. **Discover** (TD + Events full-PSD, off-device): rank (contact, center-freq) by pain tracking against
   the selected **REDCap PRO** metric. Events provide full-PSD band scanning + **corroboration** (do
   labeled "High/Higher/Lower Pain" snapshots agree in sign?), but the label is PRO-defined. Output:
   ranked shortlist, flagged "discovery only."
2. **Commit to band** (top of report): pick one (channel, center freq, width). Gates everything below.
3. **Binarize + threshold** on that band, in **LFP-Power LSB**, polarity explicit, mode suggested,
   flagged adaptive-valid/invalid vs 8–30 Hz, with the §4 conversion FYI.
4. **→ hand BandCandidate to Closed-Loop Simulation module.**

Reused primitives (exist, keep): `frequency_hz` tagging, `_available_frequencies`,
`_decode_by_frequency`, ROC/Otsu/cost-slider, binarization preview, per-channel de-pooling.

---

## 8. Code to reuse (BRAVO + perceive)

- **`BRAVO/modules/MedtronicPercept/Percept.py`** — canonical parser: `LFPTrendLogs`,
  `BrainSenseTimeDomain`/`BrainSenseLfp` via `FirstPacketDateTime`, `GroupHistory` for program-change
  tracking, **`TicksInMs` reversal correction** (real gotcha — reuse).
- **`BRAVO/modules/MedtronicPercept/BrainSenseEvent.py:saveBrainSenseEvents`** — snapshot parser:
  `FFTBinData`→`"Power"`, `Frequency`→`"Frequency"`. Band power computed downstream (not precomputed) —
  matches our extraction.
- **`ExtractSpectralFeaturesDuringStimulation.py`** — consumes precomputed PSDs (`psd["PowerSpectrum"]`);
  a consumer, not a converter.
- **`perceive` toolbox** (MATLAB, neuromodulation/perceive): `perceive_fft.m` (pwelch + relative-power
  normalization), `perceive_power_normalization.m`, `perceive_extract_diagnostic_lfpsnapshot.m` (has a
  TODO: tag event stim-on/off by matching snapshot datetime to lfptrend mA — exactly our cross-stream
  stim-tagging idea), `perceive_extract_diagnostic_lfptrend.m`.

---

## 8b. UI architecture — Option 3 (CHOSEN) + visualization spec

**Module split (frontend):**
- **`Reports/Biomarkers/` (keep + clean)** = discovery + visualization surface. Emits a BandCandidate.
- **`Reports/ClosedLoopSim/` (new)** = consumes BandCandidate, threshold-in-LSB + controller simulation.
- Seam = the §6 BandCandidate contract. Build/test independently; "commit band" is an explicit handoff.

**What "the streaming visualizations I love" actually means (corrected):** NOT the ROC/distribution
decode panels — it's the **raw linked time-series stack below the recorded-power table**. Keep all of it,
cleaned:
- Chronic 24/7 time series — Left + Right hemisphere
- Streaming on-demand time series — Left + Right hemisphere
- Pain (PRO) survey time series
- Stimulation mA time series
- **All x-axis-linked** ("link access" = shared/linked time axis across the stack).

**Changes to that stack:**
- **Recorded-power channels TABLE**: relabel as "most recently recorded" (or remove). Lean: keep,
  relabeled, demoted.
- **Add EVENT time series overlay** — ideally onto the streaming on-demand panel (and/or as markers on
  the PRO/stim axes). This is the event-display gap the user flagged (events currently not shown). Events
  are CORROBORATION markers (labeled "High/Higher/Lower Pain" snapshots), consistent with §6.
- **Streaming on-demand is FULL PSD, not band power (CONFIRMED).** The panel currently labels it "band
  power" but the 250 Hz TimeDomain yields a full **0–125 Hz PSD** (67 s, 0.98 Hz bins, 129 bins). So
  streaming joins Events as a **full-spectrum discovery stream** — update §2 (streaming is NOT band-locked
  for discovery; only the device's programmed sensing is). Relabel the panel; expose the full PSD.

**Sliding-window toggle (in the "Both" tab, below binarization): REMOVE.** Replace with the exploratory
feature-selection plots below.

### NEW exploratory discovery plot (the "Discover" stage made visual)

A **spectral feature-importance curve**: slide a 5 Hz band across 0–100 Hz and, per band, plot how well it
tracks the selected PRO. Two y-series:
1. **Pearson r** between that 5 Hz band power and the selected PRO metric (per-band univariate corr).
2. **AUC or R²** from a simple per-band model (logistic regression for binary pain_level; or the
   mixed-effects regression) on that band's power.

X = band center (0–100 Hz). This finds the **top univariate spectral feature** directly and visually, and
is exactly the Frontiers Fig 1E method ("power-spectrum-based feature selection: correlate band power with
symptom state as a proxy for feature importance"). Peaks in this curve nominate `center_freq_hz`
candidates → feed the band-commit step → BandCandidate. Flag bands outside 8–30 Hz as adaptive-invalid on
the same axis.

**ALL THREE full-PSD streams drive the scan together — Indefinite Streaming + on-demand Streaming TD +
Events.** Each covers a gap the others have:
| Stream | Channels | Label linkage | Stim | Role in the scan |
|---|---|---|---|---|
| Indefinite | all 6, stim-off | none (ambient) | off | breadth — every contact, cleanest signal |
| On-demand TD | 1–2 | in-clinic task | on/off | the programmed contact, controlled |
| Events | 1/hemi | **time-locked to PRO** | either | the labeled anchor — ties power to reported pain |

Indefinite = breadth across contacts but no pain label; Events = tight pain label but one contact/snapshot.
Pooled in standardized µV², the curve gets both; **a band where they AGREE is a high-confidence
candidate.** (Montage Survey peaks ride alongside as the device-blessed prior, §8a-bis.)

**Discovery-use vs threshold-use of events (the crisp line):** events' full PSD feeds band DISCOVERY (per-
band r / AUC averages out per-snapshot noise across many events). Events do NOT set the deployed LSB
threshold (not in LSB; device never adapts on them) — that stays Timeline-anchored. "Corroborate, don't
define" applies to the THRESHOLD, not to band discovery, where the time-locked label is events' strength.

**Internal refactor required regardless:** `BiomarkerAnalytics.js` (94 KB) entangles display with decode.
Split display components (time-series stack, PSD curve, ROC/dist) from decode logic before/while adding
the above. (Entanglement audit pending — sizing the refactor.)

## 8a-bis. CORRECTED BrainSense product taxonomy (verified on RCS08 JSONs)

There are THREE TD-bearing products + a montage survey + timeline. The LSB lives in the PROGRAMMED
products only (on-demand streaming, Timeline), NOT in indefinite streaming or the surveys.

| Product | JSON key | TD | PSD | LSB | Stim | Channels |
|---|---|---|---|---|---|---|
| **Indefinite Streaming** | `IndefiniteStreaming` | ✅250Hz | ❌ | ❌ | **off** | up to **6 simultaneous** (0-3,1-3,0-2 ×L/R; ~280 s) |
| **Montage Survey** | `LFPMontage` (+`LfpMontageTimeDomain`) | ✅ | ✅ **0–96.7Hz** | ❌ | **off** | all 6 pairs/hemi + `PeakFrequencyInHertz` + `ArtifactStatus` |
| **BrainSense Streaming (on-demand)** | `BrainSenseLfp` (+`BrainSenseTimeDomain`) | ✅250Hz | ❌(derive) | ✅ | on/off | 1–2 (programmed band) |
| **Events / Snapshots** | `LfpFrequencySnapshotEvents` | ❌ | ✅ **0–96.7Hz** | ❌ | either | 1/hemi, +30s post-press |
| **Timeline** | `LFPTrendLogs` | ❌ | ❌(in-band) | ✅ | either | 1 (programmed), 10-min avg |

(Also `BrainSenseSurveys`/`ElectrodeSurvey` = related electrode-survey variant.)

**Discovery → calibration → deployment LADDER** (146 nV/LSB TD→µV makes all TD commensurable in µV²):
- **Indefinite Streaming = multi-channel discovery.** ONLY product with all 6 contacts at once, stim-off,
  ~280 s. Best substrate for the §8b spectral feature-importance scan — answers "which contact AND band."
- **Montage Survey = device-blessed band prior + QC.** Device already computed per-contact peak freq +
  artifact flag. Cross-check the scan's peak vs `PeakFrequencyInHertz` (agreement → high confidence);
  drop contacts flagged `ArtifactStatus`. Free independent corroboration of band choice.
- **Events = corroboration** (decided; noisy per-snapshot).
- **On-demand Streaming = calibration bridge.** ONLY product with TD AND LSB on the same signal → where
  the LSB↔µV² confidence check is measured and a committed band is expressed in deployment units.
- **Timeline = deployment threshold anchor** (10-min LSB, ambulatory).

**Pooling:** discovery pools Indefinite + Montage + on-demand-TD (+events corroboration) in standardized
µV²; threshold anchors to Timeline LSB. Montage peaks/artifact flags ride alongside as prior + QC.

**Schema touch:** `evidence.per_stream_n` gains `indefinite` and `montage`; add
`evidence.montage_prior` = {peak_hz, agrees_with_scan, artifact_status} per contact.

## 8c. Time-domain streaming IN the decode + collapse to ONE tab (DECIDED)

**Two different LSBs (do not conflate):** the J. Neural Eng. paper's **146 nV/LSB** is the ADC
*time-domain* conversion (raw TD sample → µV), **exact**. It does NOT solve the power-domain "LFP Power"
LSB (still ~0.0034 µV²/LSB, ~3× uncertain, normalization-dependent). Different units.

**But the conversion is not needed to include TD in the decode.** Within-stream standardization (already
adopted §3/§4; `perceive` does the same) removes the absolute scale, so TD-derived band power pools with
device-LSB band power with NO conversion. Proven on RCS08: same streaming sessions, TD-band-power vs
device-LSB, robust-z quantiles align (TD −0.64/−0.39/0/0.61/1.5 vs LSB −0.75/−0.43/0/0.57/1.27; fatter TD
upper tail = its shorter averaging window). The absolute LSB matters at ONE place only: the final deployed
threshold, which anchors to Timeline regardless.

**Strongest reason to include TD (the decisive one):** the device LSB scalar (`BrainSenseLfp`) exists ONLY
for the single programmed sensing band. A discovered candidate band is usually NOT that band. For any
off-programmed band, **TD is the only way a streaming session contributes a band-power sample.** Without
TD, streaming informs one band; with TD, streaming informs every candidate band → discovery→validation
continuity.

**Double-counting rule (one representation per session×band):** `BrainSenseLfp` (LSB) and
`BrainSenseTimeDomain` are the SAME streaming session (device computes LSB on-board from that signal).
- committed band == programmed band → device LSB scalar (deployment unit).
- committed band ≠ programmed band → TD-derived band power (only option).
They cover different bands; never pool both for the same band.

**Collapse TD/PD/Both tabs → ONE tab.** The tab split was an artifact of treating TD and PD as separate
decoders. Band-first: ONE decode per (channel, band, PRO); each stream (Timeline, streaming-LSB,
TD-derived, events) is a labeled source. Preserve discovery-vs-deployment as two STAGES inside the one tab:
- Discovery stage = spectral feature-importance plot (full-PSD: TD + events) → nominates band.
- Deployment stage = threshold-in-LSB anchored to Timeline → BandCandidate.

**Visual:** TD streaming is ALREADY shown — it is the "streaming on-demand" panel in the kept time-series
stack (250 Hz trace). Events overlay as markers on it. No separate TD markers needed.

**Schema touch:** `evidence.per_stream_n` gains a `td_derived` count; each streaming contribution tags its
representation (`"device_lsb"` | `"td_derived"`) so the double-counting rule is auditable.

## 8d. Entanglement audit — `BiomarkerAnalytics.js` (DONE)

**Headline: the display/decode split is BETTER than feared — the kept time-series stack is already a
SEPARATE FILE.** The refactor is a tidy lift, not surgery.

**File map:**
- `BiomarkerTimeline.js` (38 KB) — **the linked time-series stack you keep.** Already renders chronic /
  streaming / **pain** / **stim amplitude** as linked rows with shared color identity (`C.pain` vermillion,
  `C.stim` orange), one row per measure, per-contact one-at-a-time (Percept-faithful). THIS is the panel
  family to clean + add the event overlay to. It is NOT entangled with the decode file.
- `BiomarkerAnalytics.js` (1474 lines / 94 KB) — **almost pure decode.** One giant component (lines
  142–1474) with 33 derived/`useState` bindings, emitting: PSD-correlation spectrum (R vs freq, l.452),
  perm-null + per-session scatter, mean-PSD-by-pain, sliding-correlation spectrogram, sliding-window
  performance, honest in-vs-CV bars, ROC (l.1080), power-vs-pain scatter, Otsu distribution (l.1212),
  per-band binarization. Display helpers (`Fig`, `Panel`, `Section`) are already factored at top.
- `BinarizationPreview.js` (16 KB) — standalone, already clean.

**Two findings that shrink the build:**
1. **The spectral feature-importance plot PARTLY EXISTS.** Line 452 already renders a "PSD correlation with
   {pain} (Pearson R vs frequency)" panel with FDR-corrected peak stars, computed on time-domain PSD. The
   §8b discovery scan is an EXTENSION of this (add the per-band AUC/logistic y-series; feed it all three
   full-PSD streams Indefinite+on-demand-TD+Events; add the 8–30 Hz adaptive-valid shading), not a new
   build from zero.
2. **The TD/PD "tabs" are `<Section>`s, not tabs** — `Section title="Time-domain analysis…"` (l.1463) and
   `Section title="Power-domain analysis…"` (l.1466) in ONE scrolling component. Collapsing to one tab
   (§8c) = merge two Section blocks + delete the `slidingActive` branch (l.677–713), NOT a routing change.

**Refactor sizing:**
- Keep + clean `BiomarkerTimeline.js`; add event overlay there. **Low effort** (isolated file).
- `BiomarkerAnalytics.js`: delete sliding-window toggle branch; merge TD+PD Sections into one
  discovery→deployment flow; extend the l.452 PSD-correlation panel into the full §8b scan. **Medium
  effort**, but contained — the 33 state bindings are decode-only (no display coupling to unpick).
- Backend emits BandCandidate from `pipeline.py`/`bravo_service.py` — independent of the above.

**No blocker found.** Display and decode were already in separate files; the "94 KB god-file" is 94 KB of
DECODE, which is exactly the part being re-sequenced anyway. The viz you love is untouched by the decode
refactor.

## 8e. Per-channel unified data view — naming demystification + design convergence

**Goal:** ONE clean per-channel view (Left | Right) showing ALL available data for that channel, replacing
the confusing Medtronic product names with plain-language labels keyed to WHAT THE DATA IS, not the
device feature that produced it.

**Proposed rename table (device name → what it actually is → plain label):**

| Medtronic name | Physical quantity | Axis | Time span | Stim | Plain label |
|---|---|---|---|---|---|
| Indefinite Streaming | raw voltage µV, 250 Hz, 6 contacts | time (s) | ~280 s | off | **Raw signal (all contacts, off-stim)** |
| Montage Survey (`LFPMontage`) | PSD µV vs Hz, per contact | frequency (Hz) | one-shot | off | **Spectrum — survey (off-stim)** |
| BrainSense Streaming | raw µV 250 Hz **+** 1-band LSB power | time (s) | ~100–500 s | on/off | **Raw signal + band power (in-clinic)** |
| Event / LFP Snapshot | PSD 0–97 Hz, symptom-locked | frequency (Hz) | 30 s | either | **Spectrum — at symptom report** |
| Timeline (`LFPTrendLogs`) | 1-band LSB power, 10-min avg | time (days) | ≤35 d | either | **Band power — chronic (24/7)** |

**The three-axis problem (the design crux):** the five products live on THREE incompatible axes —
(A) µV vs time [Raw signal ×2], (B) power vs frequency [Spectrum ×2], (C) band-power LSB vs time→days
[Band power ×2]. Time spans seconds→35 days (6 orders of magnitude). The view must group by AXIS-TYPE, not
by Medtronic product, and make stim-on/off + unit unmistakable. The relationship to surface: the two
SPECTRUM panels (B) are how you PICK a frequency band; that band becomes the single BAND-POWER trace in
(C). So the layout should read left-to-right as discover-band (spectrum) → track-band (power over time).

**Design pivot (user, decisive):** NOT per-product mini-plots. The view is a **data-availability TIMELINE
over real calendar time** that REPLACES the current BiomarkerTimeline. Per channel, rows by data type, on
one shared time axis; each recording shows when it exists and (for dense streams) what it actually is.
First draft built on real data (`availability_timeline.png`): 7118 recordings, 357 days
(2025-06-18→2026-06-11); Right 0-3 has 4× Left (selection bias, visible). Then refined by a scientific-
visualization expert sub-agent.

**FINAL DESIGN (sci-viz expert, mockup `bravo_timeline_mockup.png` v=4e11cded):** overview+inspector on
one shared calendar axis.
- **Blocks-vs-inline gated by DENSITY, not data-type** (the key sharpening of the user's idea): within
  each channel lane, three stacked sub-bands — (1) raw TD = grey COVERAGE ribbon (block; "zoom to see
  waveform" — 250 Hz is meaningless at calendar scale); (2) band-power LSB = INLINE real trend line (the
  one product both dense AND trend-meaningful at day–month scale); (3) PSD = thin TICKS (one-shot spectra,
  hover→curve). Rule: continuous+low-rate+trend-meaningful→inline; high-rate raw→coverage block; one-shot
  spectra→marker.
- **Crowding solution (3 pairs/hemi × 2 × 3 types):** overview/detail split — every channel gets ONE
  compact lane (block+trend+ticks in ~40px, products in horizontal bands not separate rows); only ONE
  selected channel expands into full-res PSD/TD/LSB in a right-hand INSPECTOR column. Raw waveforms are
  NEVER drawn for all channels at once — summoned one channel at a time via **semantic zoom** (a TD block
  resolves into the decimated→full 250 Hz waveform as you zoom past its duration). Hemispheres grouped
  L-then-R, color family per hemisphere (blue/orange), collapsible.
- **Integration (replaces BiomarkerTimeline):** pain (PRO) row + stim-mA row stacked on the SAME x-axis
  below the neural lanes → read biomarker–symptom–therapy off one vertical time slice.
- **Frequency swatch (upgraded):** left-edge color TAB per LSB lane encodes sensing center freq via
  perceptually-uniform cividis ramp + printed Hz + shared colorbar (real data spans 7.8–26.4 Hz); in
  inspector the center freq is a dashed line ON the PSD curve, threading swatch→trend→spectral peak.
- **Workflow hand-off (timeline = front door to decoder):** select channel+band (click) → set threshold
  (drag cursor on LSB trend, with pain row directly below for alignment) → seed aDBS controller. The
  timeline both motivates and parameterizes the decode.
- **Expert's critique of the raw-inline idea (accepted):** inline raw 250 Hz for ALL channels = ~450k
  pts/lane, browser-killer + illegible. Correct axis is density/interpretability, not TD-vs-LSB. Honest
  n.d. for the 4/6 channels with no configured band power (not faked).
- **Deferred to expert mode:** ring/segment + montage channels, multi-channel raw overlay, per-recording
  QC/artifact hatching, spectrograms, coherence, editable/multi-band, packet-loss diagnostics.

**Frequency swatch — FINAL (user fix, done v=ba650bc4):** the cividis blue→yellow ramp is REJECTED
(yellow invisible on white; gradient blurs adjacent bands). Use the platform's existing **categorical
`FREQ_PALETTE`** (ported verbatim from BiomarkerTimeline.js — fixed colorblind-aware hue per Percept FFT
bin, stable across patients/sessions). The **LSB trend line AND the PSD ticks are colored by sensing
center frequency** (categorical), thick enough to read the hue; left-edge swatch same color with
luminance-aware Hz label printed on it. Legend = categorical chips of bands actually present, NOT a
continuous colorbar. (Mockup legend shows 5 bands — 7.8/8.8/12.7/13.7/26.4 Hz — because `center_hz` reads
all channels in the availability records, though only 0-3 L@12.7 and 0-3 R@13.7 render a trend in this
bundle; on rebuild, drive the legend from channels that actually render so it matches the lanes.) Stim-amplitude row height reduced (0.60→0.34; pain row stays 0.60).

**Dynamic downstream plots (user requirement, for build):** the analysis plots BELOW this timeline must be
**dynamic under pain binarization / grouping** — i.e. re-render as the user changes the pain dichotomization
(cutoff/median/tertile/percentile, or which PRO metric), so one can SEE how different pain groupings reshape
the PSDs / LSB distributions / band power. The binarization control drives both the decode stats AND these
exploratory comparison plots (high-pain vs low-pain spectra/power). This is the link between the timeline
(data availability) and the decode (how grouping changes the biomarker).

**Replacement intent (confirmed):** this timeline REPLACES the current BiomarkerTimeline component in the
pain Biomarker platform (not an addition alongside it).

**Title fix (must correct on rebuild):** the sci-viz mockup's headline reads "RC+S device sensing
overview" — WRONG device. Target is **Medtronic Percept RC**; "Summit RC+S" is the trial-only research
device (§0/§9). The rebuilt figure title must say "Percept RC" (e.g. "Biomarker Data Timeline — Percept RC
sensing overview"). Design content unaffected; label only.

**Build notes / real-data fixes:** (a) montage-survey PSD timestamps ARE available
(`LfpMontageTimeDomain.FirstPacketDateTime`, all 113 files) — first extraction's channel-label filter
(`ZERO_THREE` vs montage's `ZERO_AND_THREE`) dropped them; one-line fix on rebuild. (b) Pain = REDCap
(`redcap_client`); stim mA = `_session_stim_amplitude` per-recording or `GroupHistory` longitudinal —
mockup used synthetic pain/stim for layout; real wiring is a build step. (c) SEPARATE figure still wanted:
a PSD GALLERY showing the actual PSD curves of all spectral recordings (montage + events).

## 8f. Three-source comparison of how stimulation current moves band power (BUILT 2026-09-06)

The closed-loop deployment page now shows, side by side, how band power responded to rising
stimulation current when that band power is computed three different ways from three different
recordings. The PI's ask: "look at data from all three sources and compare them. They shouldn't gate
anything, but it should be informative to the user, specifically looking at how stimulation affects
band power when it's calculated from the time domain versus when it was calculated from PSD versus
when it's calculated from LSB directly. All three plots should be reported in a very clean and
simple way."

### The three sources, and what each one actually is

| # | Source | Stream | How band power is reached | Spectrum coverage |
|---|---|---|---|---|
| 1 | Voltage trace | `BrainSenseTimeDomain`, 250 samples/s in µV | transform recipe on 3 s pieces × `LSB_PER_UV2_TRANSFORM` = 352.62 | whole spectrum, all 98 candidate bands |
| 2 | Device's own spectrum | `LfpFrequencySnapshotEvents[].FFTBinData` (patient snapshots) and `LFPMagnitude` (contact surveys) | sum of squared in-band magnitude, sub-noise bins clamped to zero, × `LSB_PER_DEVICE_PSD` = 73.63 | whole spectrum |
| 3 | Device's own band power | `BrainSenseLfp.LfpData` (stored as `MedtronicBrainSensePowerDomain`), ~2 samples/s with per-sample mA on the same clock | none — already in the device's units | the ONE programmed sensing band |

Routes 1 and 2 are read from the existing tile cache
(`Biomarkers.routines.availability.raw_lsb_spectrum_cache`); nothing recomputes a band-power recipe
and no new calibration constant was introduced. Route 3 is read directly from the stored streaming
recordings by `read_device_band_power`.

### The five honesty constraints — PI reviewed and accepted all five on 2026-09-06

1. The device's own band power exists for the single programmed sensing band only, so route 3
   covers one band while routes 1 and 2 cover all 98. Structural, not missing data.
2. The three routes are not independent. The device computes its own band power on board from the
   very voltage trace route 1 reads, and the contact surveys behind route 2 are the source the
   spectrum-to-device-units constant was fitted on. Agreement is a check on the conversion, not
   replication of a physiological effect.
3. The conversion is checked only between 7.8 and 28.3 Hz (`LSB_VALIDATED_HZ_LO/HI`, nine sensing
   centres). Outside it routes 1 and 2 extrapolate. Route 3 converts nothing and needs no range.
   Note 28.3 Hz is our data limit; the 30 Hz in §1 is the firmware's adaptive limit — not the same
   number and not interchangeable.
4. Some bands measure the stimulator, not the brain. At 55 Hz with 250 samples/s the landings are
   25, 30, 55, 60, 80 and 85 Hz, contaminating 33 of the 98 bands including eight centres (22.5 to
   29.5 Hz) inside the 8–30 Hz adaptive range. Folding comes from
   `analytics.harmonic_landings_hz` via `clinic_steps.amplitude_response_band_mask`.
5. Band power is not monotonic in current, and a measurement taken while the current is moving
   measures the move. Every point is the settled level: the mean of the pieces in the 30 s before
   the next increase, only along a run of increases, never carried across a fall.

Presentation, per the PI on 2026-09-06: the five points are recorded here and in the module
docstrings, and the figures carry one compact footer line rather than arguing each point. The ONE
exception that stays on every panel is the marking of bands that are measuring the stimulator — that
is a data label, not a caveat, and the reason is concrete: before it existed the largest apparent
effect on a heat map of this record reached 45506 device units and 18.2× its starting value and
looked like a spectacular biomarker. It was the stimulation artifact.

### How the design makes each one visible

- (1) Route 3's column carries a single point at its one band with the derived line "the device
  reports this band and no other", rather than an empty curve that reads as missing data.
- (2) One footer line, computed into every figure and carried in the payload's `notes`, so a panel
  cannot show the numbers without the sentence.
- (3) Every table row carries `band_inside_checked_conversion_range`, and a column whose band falls
  outside says so in its caption. The checked span is shaded on the frequency axis.
- (4) Faint shading over the affected band centres plus dashed lines at the actual landing
  frequencies, drawn under the data so printed values stay readable.
- (5) The settled rule is `within_visit.mean_power_before_next_change` for routes 1 and 2. Route 3
  additionally requires its OWN current record to show the current standing still across the whole
  window and to have stopped moving ≥5 s before it opened. The 5 s comes from measurement: on
  2026-08-18 the device's own power was 1.32× its settled level in the first 5 s after the last
  current change and ≤1.03× from 5 s on (right side, 7.81 Hz, nine holds ≥40 s); the left side at
  23.44 Hz showed 1.01× in the first 5 s across fourteen holds, i.e. no resolvable excursion.
  Twenty-four holds on one visit is thin — the honest reading is that the excursion is short, not
  that it is exactly 5 s. It does not bite here: settings were held ~60 s.

### Where the ladder of currents comes from — the device, not the clinic sheet

The parsed in-clinic testing sheets live in the analysis folder and the server has no copy, so run
detection reads the device's own per-sample current record (`read_device_current`,
`find_single_side_runs_from_device`). The decisive reason is not availability but the clock: the
device writes the current on the SAME clock as the band power it reports, so a setting and the power
measured during it cannot be misaligned by clock drift. Cross-checked on 2026-08-18 across the
eleven settings of the two single-side runs, the two agree on every setting and its order; the
moment each setting begins differs by −4 s to +22 s on the device's clock (median +6 s), in both
directions, so it is spread rather than a correctable offset. It is small against the ~60 s holds
and against a 30 s window taken from the END of each setting, so it moves no reported number.

One consequence, and it shortens runs rather than lengthening them: the device's log stops when
streaming stops. On 2026-08-18 the clinician kept stepping the right side to 3.0 mA but streaming
ended after 2.0 mA, so the reported run ends at 2.0 mA. Nothing is lost — route 1's voltage trace is
the same streaming session and stopped at the same moment. A run is never joined across such a gap.

### What was found on RCS08 (rendered live, 2026-08-18, 55 Hz, single-side ladders)

- 11 single-side rising runs exist across the whole record; the report renders the 4 most recent.
- **Left, 12:51:42–12:58:26, 0.5→3.5 mA, sensing `ONE_THREE_LEFT` at 23.44 Hz.** Routes 1 and 3 both
  produced 6 of 7 settings and agree to within 1.39×. Both are non-monotonic: route 1 rose to 415
  device units at 3.0 mA and ended at 268 (0.99× its 1.0 mA value); route 3 rose to 501 at 2.0 mA
  and ended at 243 (0.97×). **The 23.44 Hz band the device was programmed to sense is one of the
  bands measuring the stimulator at 55 Hz** — this is on the headline, derived.
- **Right, 13:00:29–13:04:11, 0.5→2.0 mA, sensing `ZERO_THREE_RIGHT` at 7.81 Hz.** Routes 1 and 3
  produced 2 of 4 settings and agree to within 1.10×. Route 1's nearest cache band, 7.5 Hz, sits
  outside the checked 7.8–28.3 Hz range, so that column is extrapolating and says so.
- **Route 2 produced nothing in any of the four runs.** The device computes its own spectrum only on
  a patient button press or a contact survey with stimulation off, and neither happened during a
  current ladder. That is reported as an explicit count and reason, not a blank panel.
- The bottom row of each figure is restricted to 7.5–30 Hz. Two reasons. First, the firmware cannot
  place a sensing band above 30 Hz (§1), so nothing above it can be acted on from this page. Second,
  the full spectrum will not fit on one linear axis. Each figure computes and prints its own pair of
  factors at render time rather than quoting a fixed one, and across the four rendered runs the
  whole-spectrum span runs from 4,616-fold to 4,242,165-fold while the same values inside the drawn
  range span only 4.4-fold to 10.7-fold. Per run: 2026-08-18 left 19,789 against 10.7; 2026-08-18
  right 16,119 against 10.3; 2025-10-21 right 4,616 against 9.0; 2025-10-02 right 4,242,165 against
  4.4. In 3 of the 4 runs the whole-spectrum peak sits in a band that is measuring the stimulator
  (54.5 or 55.5 Hz at a 55 Hz rate); the exception is the 145 Hz run, whose peak is at 2.5 Hz. The
  saved table keeps all 98 bands. **No logarithm anywhere**: the device sums squared magnitude and
  compares against a threshold typed in those units, and never takes one.

### What this panel deliberately does NOT do

- **It gates nothing.** No badge, no verdict, no pass, no fail, no `blocking_status`. Nothing else on
  the page reads it, and a test asserts the payload carries none of those words.
- **It does not claim the three sources are independent.** See constraint 2.
- It does not substitute one source for another to fill a panel. A source with no data reports the
  count it had and why, and a test asserts the three routes carry three distinguishable values.
- It never combines neighbouring band columns. They are 5 Hz wide on 1 Hz spacing, so adding two
  counts the same signal twice; one band is one column, and a test pins the width.

### Files

- `modules/ClosedLoopDeployment/three_source_response.py` — the three routes, the settled rule, run
  detection from the device's current record, `build_for_participant`, and the flat table.
- `modules/ClosedLoopDeployment/three_source_plots.py` — one context, two renderings (matplotlib for
  the report, Plotly for the browser) plus `report_payload`. All figure text derived, none asserted.
- `modules/ClosedLoopDeployment/adapter.py` — `three_source_response` block, wrapped so a failure
  there cannot take down the report and reports its own reason when it does.
- `Client/src/views/Reports/ClosedLoopSim/ThreeSourceResponsePanel.js` + `index.js` mount at
  `#cl-three-source`, after the band-stability card.
- `modules/ClosedLoopDeployment/tests/test_three_source_response.py` — 26 tests.

---

## 8g. The band-by-integration-time sweep, and the measurement rules it runs on (BUILT 2026-09-06)

A new last section on the biomarker exploration page. It answers one question the earlier design
left implicit: **how long a stretch of signal should one band-power measurement average over?** The
page had a single slider fixing that length; this section sweeps it instead.

**The grid.** 22 band centres, 8.5–29.5 Hz, each 5 Hz wide, against 10 candidate lengths of signal.
The centres come from the cached spectra's OWN centre list rather than a range written here, so a
centre with no measurements behind it cannot appear. The full 220-cell surface is returned, not only
the best cell per band.

**The length asked for is not the length delivered, and both travel with every row.** One band-power
measurement is built from whole 3-second pieces, so 5 of the 10 requested lengths cannot be given
exactly: 1 → 3 s, 5 → 6 s, 10 → 9 s, 20 → 21 s, 25 → 24 s. Labelling the shortest row "1 s" would
have misstated it threefold.

**It reuses the existing matcher rather than inventing a rule.** `availability.live_lsb_spectrum_match`
already takes the length of signal as an argument and is the same function the full-spectrum scan
uses; sweeping that one argument IS the mechanism.

### The two measurement rules the PI set on 2026-09-06, verbatim

> "Rule number one: The band centers should reflect plus or minus 2.5 Hz for a total 5 Hz band
> centered at the frequency that it is named for. Rule number two: Use a 10-chunk sliding window in
> steps of 3."

**Rule one requires NO arithmetic, and that is the load-bearing point.** The cache is already built
at a half-width of 2.5 Hz on a 1 Hz centre grid, so the stored column named 12.5 Hz already IS the
band from 10.0 to 15.0 Hz. **Neighbouring columns must therefore never be summed or averaged to
build a 5 Hz band** — they overlap heavily and doing so would double-count the shared frequencies
and inflate every value. Read the column, label its span. Code should read the cache's own
half-width and stop if it is not 2.5 rather than assume it.

**Rule two is a sliding window with 70% overlap** — ten consecutive 3-second pieces, advancing three
pieces, so 30 s wide stepping 9 s and successive points sharing 21 s. **The consequence must be
stated wherever such points are plotted: the number of points is NOT the number of independent
measurements.** Dividing by ten-thirds gives roughly the independent-sample equivalent. Without that
written down a reader counting points credits the analysis with about three times more independent
data than it has.

### The reported best-of-ten is optimistic by construction, and the verdict accounts for it

Taking the maximum over ten correlated integration times inflates the answer. So a row reads
`established` only when its resampling interval stays off the no-relationship value **and** the
value beats what the same best-of-ten choice reaches on 1000 circular block shuffles of the pain
scores. Measured on RCS08:

| | intervals off the no-relationship value | HELD BACK by the shuffled best-of-ten | `established` |
|---|---|---|---|
| correlation | 125 of 264 | **77** | 48 |
| high-versus-low pain | 105 of 264 | **70** | 35 |

No `established` row fails the shuffled test. **About 60% of rows that look significant on their own
interval do not survive having been chosen.** This project has already retracted one candidate
biomarker for exactly that error.

**0.5 is the no-discrimination reference, never zero** — both colour scales centred on the right
value, 0.5 inside the scale rather than at an end, an interval spanning it reading `not_resolved` in
word, sentence and headline, and `not_resolved` kept distinct from not-assessed.

**Declared deviation:** the grid draws the UNFOLDED area under the curve. A one-predictor logistic
regression's in-sample value is exactly the band power's own value or one minus it, with the fitted
slope deciding which — so the fitted number is direction-folded, cannot fall below 0.5, and for it
0.5 is a floor rather than a neutral middle. Confirmed on the live record: unfolded spans
0.208–0.787 while folded bottoms out at 0.516. Both are reported.

### Live values on RCS08

* NRS: **r = −0.527 at 16.5 Hz on `ONE_THREE_LEFT`, 15 s delivered**, n = 173, interval −0.632 to
  −0.399, shuffled best-of-ten 0.195, p = 0.0010 → **established**.
* Left Leg VAS: r = −0.377 at 10.5 Hz on `ZERO_TWO_LEFT`, 9 s delivered (asked 10), n = 55, interval
  −0.583 to −0.157, shuffled 0.387, p = 0.0709 → **not resolved**. The case the correction exists
  for: an interval clear of zero that does not survive selection.

### This section deliberately ignores the extent slider

`bravo_service.py:5364–5366`. Sweeping the length of signal is the whole point of the section, so
`MatchExtentSec` — which fixes a single length — is intentionally not read here. It still governs the
rest of the page. **A reader moving that slider and seeing the sweep unchanged would reasonably
think something was broken**, so the interface and the README need to say so.

### Where a warm sweep request spends its time, after three speedups on 2026-09-06

| piece | seconds | share |
|---|---|---|
| **recordings read off disk and unpickled** | **1.647** | **21.1%** |
| every statistic, six sensing contact pairs | 1.248 | 16.0% |
| matching, six sensing contact pairs | 1.063 | 13.6% |
| pain reports pulled from REDCap | 0.725 | 9.3% |

The matcher went 18.263 → 0.852 s (21.4x), the REDCap pull 1.662 → 0.651 s, the statistics
2.127 → 1.196 s. **Disk reads are now the largest item, so that is what to attack next — not any of
the three already done.** Each speedup was proven to change no output value: the matcher over 1,080
live configurations with 0 field differences, the statistics over 7,920 grid cells and 8,358 fields
with 0 differences, REDCap with 760 pain reports before and after and zero differing cells.

**There is no cross-request cache of the pain reports and that is deliberate.** Reports are filed
continuously, so a cache outliving a request would eventually serve an analysis silently missing the
newest ones, with every correlation and verdict wrong while looking normal. A cross-request cache was
made conditional on a freshness key cheaper than the pull; measured twice on the live record, there
is none — REDCap's record-edit-log check costs the same few tenths of a second as an outright fresh
narrowed fetch. The speedup came from asking REDCap for the columns the page reads (765 rows × 28
columns instead of 3,496 × 637), not from remembering anything.

## 9. Reference papers
- **Trial (medRxiv 2025.08.11.25333010):** deployed on **Summit RC+S**, single power channel + single
  threshold, ±1 feature sign, onset/offset from offline sim, 2nd LDA for sleep deactivation.
- **Frontiers (fnins.2021.762097, Prosky/Shirvalkar):** closed-loop principles — onset/termination/
  blanking/ramp, threshold-by-percentile, negative-feedback to avoid stuck-on, 0 mA ≠ stim-off.
- **J. Neural Eng. (ad1dc3):** Percept PC signal-processing tutorial — ADC 146 nV/LSB (time domain),
  filter response, aliasing; explains why absolute power conversion is normalization-dependent.

---

## 10. Open decisions / next steps
- [x] **Finalize BandCandidate schema (§6 v1 done).** Label is REDCap-PRO-defined (6-metric menu +
      composite); events corroborate only; selection bias recorded in `provenance`.
- [ ] Confirm exact unlocked PD-mode parameter ranges for our firmware (vs commercial defaults table §1).
- [ ] Decide discovery scoring: keep ROC/LASSO/LDA, add the mixed-effects validation as the headline stat?
      (Leaning mixed-effects; decide later.) **PARTLY ANSWERED IN PRACTICE 2026-09-06 by the
      band-by-integration-time sweep (§8g), which reports BOTH a correlation and a
      high-versus-low-pain discrimination per band and corrects for having chosen the best of ten
      integration times. That correction is not Benjamini-Hochberg and deliberately so: a q-value
      does not account for taking a maximum over ten correlated windows. It held back 77 of 125
      correlation rows and 70 of 105 discrimination rows whose own intervals cleared the
      no-relationship value. Whether that sweep becomes the headline statistic is still the PI's
      call.**
- [ ] Test empirically whether remote-past stim-context heterogeneity affects biomarker–pain separation
      (`provenance.stim_era_heterogeneity_tested`).
- [ ] Verify low/high PRO-day balance per metric before threshold-setting (events are corroboration only).
- [ ] Wire §6 schema into `bravo_service`/`pipeline` output (emit one BandCandidate per committed band).
- [x] **UI architecture: Option 3 chosen** — clean `Reports/Biomarkers/` (discovery+viz, emits
      BandCandidate); new `Reports/ClosedLoopSim/` (consumes it).
- [x] **Entanglement audit DONE (§8d).** Display (`BiomarkerTimeline.js`) and decode
      (`BiomarkerAnalytics.js`) already separate files → refactor is a tidy lift. PSD-correlation panel
      (l.452) already exists → §8b scan is an extension. TD/PD are `<Section>`s not tabs → one-tab merge
      is trivial. No blocker.
- [ ] **Frontend cleanup (§8b):** keep linked time-series stack (chronic L/R, streaming L/R, PRO, stim mA);
      add event overlay onto streaming on-demand; relabel recorded-power table "most recent"; relabel
      streaming "band power" → full PSD; REMOVE sliding-window toggle.
- [ ] **Build the spectral feature-importance plot (§8b):** 5 Hz sliding band 0–100 Hz × {Pearson r,
      logistic/mixed AUC or R²} vs selected PRO, on full-PSD streams; peaks nominate center_freq.
- [x] **TD streaming included in decode; TD/PD/Both tabs → ONE tab (§8c).** Standardization removes the
      need for LSB conversion to pool; TD is the only way streaming covers off-programmed bands;
      double-counting rule = one representation per session×band. Discovery/deployment become stages.
- [x] **Three-source comparison built and mounted (§8f).** Voltage trace / device's own spectrum /
      device's own band power, side by side over the same rising-current settings, in device units,
      no logarithm. Informative only — it gates nothing. Route 2 produced nothing in any of the four
      runs on RCS08 and says so with a count and a reason.
- [ ] **Route 2 has no coverage during current ladders, and that is a protocol gap, not a code
      one.** The device computes its own spectrum only on a patient button press or a contact survey
      with stimulation off. If we want the middle column populated, the visit protocol needs a
      button press (or a survey) at each held setting. Worth deciding before the next in-clinic
      session, because it is the only route that would exercise the spectrum-to-device-units
      constant against the other two at the same setting.
- [ ] **The left device's programmed sensing band, 23.44 Hz, contains a folded multiple of 55 Hz
      (§8f). REWORDED AND RE-REASONED 2026-09-06 — the earlier entry called it a
      "stimulator-contaminated band", and the PI rejected both the word and the inference.** His
      argument: a stimulation artefact GROWS WITH CURRENT and keeps growing, so a band that comes
      back down cannot be one. Measured on RCS08's 2026-08-18 visit, three separate things support
      him and none supports the old reading:
        1. On that same visit the bands containing 55 Hz ITSELF rise monotonically to 18.2x their
           starting value. That is what the stimulator looks like. The 25–28 Hz bands instead RISE
           AND FALL, curvature p 0.014–0.025, peaking near 2.1 mA.
        2. The peak position DRIFTS smoothly with frequency — 2.120, 2.089, 2.071, 2.063 mA across
           25, 26, 27 and 28 Hz. A folded landing sits at one frequency, 25.0 Hz, and cannot produce
           a peak that moves.
        3. Curvature varies as a smooth gradient across frequency rather than stepping at the
           landing. The earlier "clean split along the landings" was an artefact of a 0.05 cutoff
           crossing that gradient, not a categorical discriminator.
      So the flag means only "a folded landing lies inside this band, treat its amplitude response
      with care", and nothing stronger. **The decision that actually needs making is different from
      the one this item used to pose:** not whether to escape contamination, but whether a threshold
      can sit on a band whose response is PEAKED — see the new item below. Still a finding, not a
      gate; §8f gates nothing.
- [ ] **A PEAKED amplitude response breaks the device's two-point threshold logic, and this needs
      deciding before the next ladder.** The device places its switching value BETWEEN two power
      readings. A band that rises to ~2.1 mA and then falls can satisfy the same threshold on BOTH
      sides of its peak at different currents, so the control law cannot tell "not enough
      stimulation" from "too much". Open: fit one straight line across the whole range, or something
      that admits curvature? Note that the earlier LINEAR retraction of `ONE_THREE_LEFT` at 55 Hz
      (family-wise p = 0.670) does NOT settle this — a linear cluster test has almost no power
      against a rise-then-fall, and a CURVATURE test on the one clean day gives p = 0.125. Neither
      is significant; both are on 8 steps from a single visit.
- [ ] **55 Hz has almost no side-attributable coverage on the left electrode, and that is a protocol
      gap.** Of six visit days with 55 Hz recordings on `ONE_THREE_LEFT`, exactly ONE has the right
      stimulator held at zero (2026-08-18, 8 steps). The other five ramped both sides together, so
      nothing on them can be attributed to the left current. **No cross-day replication is available
      at 55 Hz at all.** At 110 Hz two of three days have the right side at exactly 0.0 mA, which is
      why that rate is the one with a replicated result.
- [ ] Then: design the Closed-Loop Simulation module against the BandCandidate contract.
