# Closed-Loop Deployment Module — Four-Lens Expert Audit

**Module:** `Client/src/views/Reports/ClosedLoopSim/` (5 panels) + `BRAVO/modules/Biomarkers/` analytics  
**Repo state:** HEAD `a25e0a8` on `PS_biomarker_module` (v3.1.0)  
**Reviewers:** four expert lenses, each evaluating all five panels against the same verbatim source bundle. Three (Scientific Visualization, Statistical Rigor, Time-Series) ran as independent delegated sub-agents; the fourth (Plotly Interaction + Actionability) was orchestrator-authored from the same source after the delegated reviewer's connection dropped mid-run.

**The module's job:** turn one validated `BandCandidate` into a deployable Percept RC adaptive-stim controller spec — a sense band, an **LSB threshold**, and the evidence a clinician signs against. Every finding below is weighed by whether it changes a number the clinician programs or a verdict they trust.

## Panels under review

| Panel | Name | What it calculates |
|---|---|---|
| **P0** | Identity header | Device identity + mixed-effects evidence summary (OR/CI/p, stim stability, per-era OR). Display-only. |
| **PB** | Deployment ROC + cut-point | Clustered-bootstrap AUC + CI; browser-side cut-point rules (Youden / F1 / cost); feature-distribution histogram with a movable threshold line. |
| **PC** | LSB threshold + power | Percentile-anchored device-LSB threshold (the deployable number); power-vs-N sufficiency curve; µV²/LSB FYI ratio. |
| **PD** | Per-era refit | AUC forest plot across OFF/LOW/HIGH stim eras vs pooled; portability verdict. |
| **PE** | Deploy-to-Percept review | Gate checklist, headline LSB threshold, evidence table, caveats, print/JSON export. |

**Tally:** 56 findings — **4 high · 28 medium · 24 low**. 7 of 10 thematic clusters were raised independently by more than one lens.

## Convergent findings (ranked)

These are the themes where independent lenses hit the same defect — the highest-confidence work.

### 1. C3 — Per-era portability (PD) can mislead three different ways  ·  *HIGH*
**Panels:** PD  **·  Raised by:** STATS · TIME · VIZ

STATS (high): each era oriented independently (flip per era) → a band whose sign REVERSES under stim still folds to AUC>0.5 and reads 'portable' — the worst closed-loop failure (controller ramps wrong way) is hidden; and the verdict keys on raw point-AUC spread (>0.10), ignoring the CIs the plot draws and the existing band×era LRT. TIME: per-era Youden cut-points are re-optimized on thin strata → cutpoint_spread inflated by noise, 'fragile' can fire on a 12-sample era; and stim-era is a STATE stratum, not a temporal fold, so 'the threshold travels' must not be read as forward stability. VIZ: non-estimable eras are drawn AS A MARKER AT x=0.5 (the chance line) → reads as 'performs at chance' rather than 'no estimate'.

**Fix:** Orient once from pooled, apply that fixed sign to every era (reversals show as sub-0.5). Base the verdict on CI overlap / the band×era LRT, not raw spread; attach a bootstrap CI to the spread. Move the missing-data glyph OFF the AUC scale and label 'n/a (insufficient samples)'. Scope the verdict wording to stim STATE.

### 2. C1 — AUC bootstrap CI is not honest evidence the band beats chance  ·  *HIGH*
**Panels:** PB → PC, PE  **·  Raised by:** STATS · TIME

STATS: each replicate re-folds with max(ab,1-ab) on an already-oriented score → lower 95% CI is censored at ~0.5 (simulated 0.505 vs honest 0.411 under null), so 'AUC 0.62 (CI 0.51-0.74)' is not evidence of signal. TIME: clusters are per-PRO-rating (finer than the glmer's weekly unit) and treated as exchangeable, ignoring between-rating serial correlation → CI further over-narrowed. Both propagate into the PC power calc and the PE 'credible CI'/'powered' gates.

**Fix:** De-fold: orient once on the full sample, append the fixed-direction AUC per replicate (not max(ab,1-ab)). Switch to a moving-block / weekly-cluster bootstrap to absorb serial correlation. Backend-only; no Plotly change.

### 3. C2 — Every reported number is in-sample; no forward/temporal validation  ·  *HIGH*
**Panels:** PB, PE (whole module)  **·  Raised by:** TIME · STATS

TIME (high, PB+PE): ROC/AUC/operating-point/sens/spec are all fit AND evaluated on one contiguous record with no forward-chaining; for a deployable controller the decision-relevant number is next-week held-out performance, and the sign-off gates carry no prospective-validity check. STATS: the AUC point estimate is additionally winner's-curse biased away from 0.5 for borderline bands (mean 0.56 under null at N=60). Caveats state the optimism but no de-biased number is shown.

**Fix:** Add expanding-window / blocked-by-week forward-chaining: report mean held-out AUC + held-out sens/spec at the train-fold operating point, shown beside the in-sample number. Add a 'forward-validated' PE gate. Backend numbers only.

### 4. C4 — Power readout & 'powered' gate run on the optimistic AUC  ·  *MEDIUM*
**Panels:** PC → PE  **·  Raised by:** STATS · TIME

Power is monotone in AUC, so the fold-biased + selection-optimistic + in-sample AUC OVERSTATES current power and UNDERSTATES ratings-needed — 'adequately powered' passes optimistically exactly at the deploy/no-deploy margin. TIME adds: the power-vs-N curve assumes iid exchangeable future ratings, but autocorrelated ratings make 'N independent ratings' overcount effective N, so 'need X more' is optimistic in calendar terms.

**Fix:** Drive power from the (de-folded) AUC CI lower bound or report a power BAND across [auc_lo, auc]. Discount effective N by a design-effect factor or relabel the x-axis 'effective independent ratings'. Resolves automatically once C1 lands.

### 5. C5 — needed-N marker is drawn off the power curve  ·  *MEDIUM*
**Panels:** PC  **·  Raised by:** STATS · PLOTLY

STATS (math): n_ratings_needed comes from the SE²·N≈const closed form while the curve is exact Hanley-McNeil — the two can diverge. PLOTLY (render): the marker is placed at y=target_power*100 (on the 80% line), not at the curve's power at n_need, so it can sit visibly off the line and read as a glitch on the figure whose whole message is 'how many more ratings'.

**Fix:** Place the needed-N marker at the curve's interpolated power at n_need (interpolate the existing curve array), or solve n_need by interpolating the curve's 80% crossing. Marker and curve then always coincide. Presentation fix.

### 6. C7 — Figures are not self-contained for the printed/grayscale device record  ·  *MEDIUM*
**Panels:** PB, PC, PD, PE  **·  Raised by:** VIZ · PLOTLY

VIZ: the PD pooled-CI shaded band and the PC now/needed markers are identified only by faint color or hover — unreadable in a printout or grayscale, yet portability and data-sufficiency are exactly what must be judged from them; CIs labeled only '95% CI' (not 'clustered bootstrap'), and the histogram overlay blends to a muddy third color in the separation zone. PLOTLY: displayModeBar:false strips figure export from all panels, so PE's auditable record (numbers-only JSON) cannot carry the figures.

**Fix:** Add static on-figure annotations (drawn once in layout — no rebuild). Render one histogram class as an outline/step. Label CI method on every figure. Enable a minimal modebar (toImage + resetScale2d) so figures export into the record.

### 7. C8 — Sign-off gate arithmetic treats absence-of-evidence as a pass  ·  *MEDIUM*
**Panels:** PE  **·  Raised by:** STATS · TIME

STATS: the stim-stable gate FAILS OPEN — when the band×era LRT does not converge (singular fit on a tiny OFF stratum) it falls back to the verdict string and shows a green PASS check; and n_gates_passed is a flat count of 6 heterogeneous gates with no necessary-vs-supportive distinction, so '5 of 6' reads near-ready even if the one failure is a hard necessary gate. TIME: the credible-CI and powered gates inherit the over-narrow CI / optimistic power, so they can pass prematurely.

**Fix:** Give stim-stable an 'indeterminate' (neutral, non-pass) state when the LRT didn't run. Mark necessary gates (deployable threshold, adaptive band) and block 'ready to program' on any necessary-gate failure regardless of count.

### 8. C6 — Warn-orange (#E69F00) fails contrast on the module's most safety-critical alerts  ·  *MEDIUM*
**Panels:** P0, PB, PC, PE  **·  Raised by:** VIZ

White-on-#E69F00 and #E69F00-text-on-white both measure 2.25:1 (below WCAG AA 4.5 and large-text 3.0). This ink carries the verdict badge (P0), the degenerate-cutpoint callout (PB), underpowered/low-confidence notices (PC), and the 'review caveats before programming' sign-off headline (PE) — the alerts meant to STOP a bad deployment are the least readable on screen and in print.

**Fix:** Dark text on orange fills; reserve #E69F00 for area, not small/critical text; darken the warn foreground tone. Text already carries every verdict redundantly, so CVD/grayscale safety is unaffected. Pure cosmetic, logic-free.

### 9. C9 — Latent regression hazard: hardcoded cut-point trace index  ·  *MEDIUM*
**Panels:** PB  **·  Raised by:** PLOTLY

Plotly.restyle targets a literal [2] with the base-trace ordering (chance=0, ROC=1, cut-point=2) implicit and uncommented at the restyle site. Any future trace insert/reorder silently mutates the wrong trace with no error — a latent re-introduction of exactly the reset-class bug commit 255e0ef fixed.

**Fix:** Single-source a `const CUTPOINT_TRACE = 2` used at both the traces-array build and the restyle index. Zero behavior change.

### 10. C10 — Actionability: the module stops short of the device-tuning last mile  ·  *MEDIUM*
**Panels:** PC, PE  **·  Raised by:** PLOTLY

PC shows a recommended LSB threshold with NO anchor to the currently-programmed device value — the task is tuning an existing setting, so a recommended number alone forces a programmer context-switch to know if it's a nudge or a large change. PE covers band + threshold but the closed-loop tuning surface is band + threshold + RAMP, and there is no ramp guidance; the exported record also omits the justifying figures.

**Fix:** Show recommended-vs-currently-programmed (Δ) in PC. Add advisory ramp-parameter guidance to the sign-off. Embed figures into the exported record (pairs with C7's modebar enable).

---
## Per-lens detail

### Statistical Rigor
> Architecturally and in its disclosure posture the module is strong: clustered (independent-unit) resampling, the clustered effective-n denominator for power, the always-on selection-bias caveat, operating-point provenance in the export, and the sound removal of the redundant net-benefit rule all reflect real statistical care and three prior review rounds. The deploy-readiness gap is a single estimation defect with wide reach — re-folding the AUC inside every bootstrap replicate (and the parallel independent per-era orientation) censors the CI at chance and masks direction reversals, which then propagate into the power calc, the evidence table, and two PE gates. None of the fixes touch the imperative Plotly pattern; with the de-fold, a pooled-orientation per-era refit, a CI/LRT-based portability verdict, and an indeterminate stim-stability gate, the module's numbers would honestly support the program/don't-program decision they are designed to inform.

**P0** — actionability: *medium*  
- **[low]** Per-era ORs (OFF/LOW/HIGH) are printed as bare point estimates with no CI and no test, inviting the reader to eyeball cross-era differences that the module elsewhere (P0 LRT, PD) handles formally. Three unadjusted point ORs next to each other read as a comparison the numbers cannot support.
  - *fix:* Either attach the per-era CIs already available upstream, or relabel as 'descriptive, see Per-era refit (PD) for the tested comparison' so the header does not imply a per-era inference the point values don't license.
- **[low]** The 'credible CI' boolean is shown without the rule that produced it (_band_credible_ci threshold on CI width). A clinician cannot tell whether 'credible' means 'CI excludes 1' or 'CI width below some cutoff'. The same flag gates a deployment gate in PE, so its definition matters.
  - *fix:* Tooltip the criterion (e.g. 'OR CI width / position rule') so the badge is interpretable and consistent with the PE credible_ci gate.

**PB** — actionability: *medium*  
- **[high]** ⚑act The clustered bootstrap RE-FOLDS each replicate with max(ab, 1-ab). Because the score is ALREADY globally oriented once (use_score), re-folding per replicate censors the lower tail at chance: any replicate whose weak signal reverses is reflected back above 0.5. I simulated this — for a true-null band the folded lower 95% CI sits at 0.505 vs an honest 0.411, and for a weak true-0.59 band the lower CI moves from 0.44 to 0.504. The CI lower bound therefore can essentially never fall below 0.5, so 'AUC 0.62 (95% CI 0.51–0.74)' is NOT evidence the band beats chance — the 0.51 floor is manufactured by the fold, not by the data. This is the headline number the clinician trusts and it feeds the PE evidence table.
  - *fix:* Orient ONCE on the full sample (keep the existing global flip into use_score), then in each replicate append the AUC of the FIXED-direction score WITHOUT re-max: boot_aucs.append(ab). The CI is then a valid percentile interval for the oriented AUC and its lower bound can honestly drop below 0.5, conveying real uncertainty. This is a one-line change and does not touch the Plotly draw pattern.
- **[medium]** ⚑act The AUC POINT estimate uses the full-sample orientation flip auc = max(raw_auc, 1-raw_auc). Under the null this is upward-biased (I measured mean 0.56 at N=60), a winner's-curse distinct from operating-point optimism. The note says 'AUC oriented >= 0.5' but does not warn that the point AUC is biased away from 0.5 for borderline bands — exactly the bands near the deploy/no-deploy boundary.
  - *fix:* Make the bootstrap CI (once de-folded per the finding above) the primary evidence statement and present the point AUC against it, and add one clause to the note that the oriented point AUC is optimistic near chance. No need to remove the flip — the flip is fine for a pre-validated band; the disclosure and CI honesty are what's missing.
- **[medium]** The valid-replicate floor for computing percentiles is only >=20. The 2.5/97.5 percentiles of 20 values are each effectively the min/max-ish order statistics and are extremely noisy — the CI endpoints have large Monte-Carlo error at that count. With class-collapse skips this floor can be hit on small-cluster bands, precisely where the CI matters most.
  - *fix:* Raise the floor to >=100 (ideally report n_boot_ok and widen via BCa or at least flag when n_boot_ok is low). The frontend already prints n_boot_ok — gate the CI display on a higher count and show 'CI unstable, n_boot_ok low' below it.
- **[low]** Skipping replicates that lose a class is a non-ignorable, prevalence-dependent exclusion: surviving replicates are biased toward more class-balanced resamples, which can slightly narrow the AUC CI for low-prevalence bands. Currently undocumented as a source of CI optimism.
  - *fix:* Acceptable to keep (the alternative — stratified cluster resampling — changes the estimand), but note in the returned 'note' that class-collapsed replicates are dropped and that this mildly narrows the CI at low prevalence.
- **[low]** The browser re-solves the cut-point on the DOWNSAMPLED fpr/tpr/thr (max_points=300, linspace on index), while the backend's default Youden operating_point is computed on the FULL arrays. The two Youden points can differ slightly, and it is the browser one that is lifted to Phases C–E. For coarse curves this can move the programmed threshold a notch.
  - *fix:* Either solve the default/displayed cut-point server-side on full arrays and pass the index, or keep the un-downsampled thr for cut-point solving while downsampling only the drawn curve. Low impact at typical resolutions but it is a silent point-vs-displayed inconsistency.

**PC** — actionability: *high*  
- **[medium]** ⚑act The AUC fed into the power calc is the in-sample, selection-optimistic, fold-biased point AUC from deployment_roc. Power is monotone increasing in AUC, so an upward-biased AUC OVERSTATES current power and UNDERSTATES n_ratings_needed — the 'adequately powered' verdict (and the PE 'powered' gate) is optimistic for borderline bands. The power machinery is correct; its input is biased.
  - *fix:* Drive power from the LOWER bound of the (de-folded) AUC CI, or report a power band across [auc_lo, auc] rather than a point. At minimum, annotate that power is computed at the optimistic point AUC.
- **[low]** The scalar n_ratings_needed comes from the SE^2·N≈const closed-form solve, while the plotted curve uses exact HM power at each N. These are not guaranteed consistent: the needed-N marker is drawn at exactly tgt·100 (the target line) rather than at the curve's own 80% crossing, so on bands where the approximation and the exact curve diverge the marker can sit off the curve, reading as a glitch.
  - *fix:* Solve n_need by interpolating the exact curve to the 80% crossing (the curve already exists), or place the marker at the curve's power(n_need) value so marker and curve always coincide. The HM SE^2∝1/N approximation is fine to keep for a first guess but should not drive the plotted marker independently of the exact curve.
- **[low]** n_clu >= 4 is a very permissive floor for invoking an asymptotic-normal AUC variance and a Gaussian power formula. At 4–8 independent ratings the HM normal approximation and the (auc−0.5)/se z are unreliable, yet a confident 'X% power, need Y ratings' is printed.
  - *fix:* Either raise the floor (e.g. >=8–10) or tag the power readout 'small-sample, approximate' below ~10 independent ratings so the clinician discounts it.

**PD** — actionability: *medium*  
- **[high]** ⚑act Each era is oriented INDEPENDENTLY (flip = raw<0.5 inside _roc_for), so an era whose band-pain relationship REVERSES sign relative to pooled is still folded to AUC>0.5 and compared as if same-direction. A direction reversal across stim states is the WORST closed-loop portability failure (the controller would ramp the wrong way under stim), yet it appears as two high AUCs with small auc_spread → 'portable'. The cutpoint_spread cannot rescue this because thr_dev = -thr if flip, so per-era thresholds with different orientations are on differently-signed scales and their spread is not comparable either.
  - *fix:* Fix the orientation ONCE from the pooled fit and apply that fixed sign to every era; let per-era AUC fall below 0.5 when an era reverses. Then auc_spread and a sign-aware threshold spread genuinely capture direction reversals, and the verdict can flag 'direction reverses in HIGH era' — the exact failure mode this panel exists to catch.
- **[medium]** ⚑act The portability verdict is computed from the SPREAD OF POINT AUCs alone (auc_spread>0.10), ignoring the per-era CIs the plot displays. Two eras at 0.65 and 0.80 with hugely overlapping CIs are flagged 'fragile' (spread 0.15) while two tight-CI eras at 0.58 and 0.67 are called 'portable' (spread 0.09). The verdict therefore tests point-estimate distance, not whether the eras differ beyond sampling error — and a formal band×era interaction test (the stim-stability LRT) already exists on the same strata but is not used here.
  - *fix:* Base the verdict on inference, not raw spread: require non-overlapping per-era vs pooled CIs (or defer to the existing band×era LRT p-value) before declaring 'fragile/portable'. Keep the spread as a descriptive annotation. The 0.10/0.5 cutoffs are otherwise arbitrary and uncalibrated to the CIs.
- **[low]** Per-era bootstraps reuse seed=0 and the same >=20 valid-replicate floor as pooled, but per-era cluster counts are far smaller, so class-collapse skips are more frequent and the per-era CIs are correspondingly noisier — the forest whiskers are not on equal estimation footing across rows, which the eye-balling of CI overlap assumes.
  - *fix:* Report n_boot_ok per era (already computable) and visually de-emphasize eras whose CI rests on few valid replicates, so cross-era CI comparison is not misled by unequal Monte-Carlo precision.

**PE** — actionability: *medium*  
- **[medium]** ⚑act The stim_stable gate FAILS OPEN when the LRT does not converge: if st is unavailable it falls back to the verdict string and can show a green PASS check ('treated as stim-stable per the band's validated verdict'). Non-convergence (typically a singular fit on a tiny OFF stratum) is absence of evidence, not evidence of stability — yet it is rendered as a passed deployment gate. The detail text is transparent, but the green check is what a signer scans.
  - *fix:* Give this gate a third 'indeterminate' state (neutral icon, not a pass) when the LRT did not run, so a non-converged stability test never counts toward 'all gates passed → ready to program'. Fail-closed or abstain, don't pass-by-default.
- **[medium]** ⚑act The 'powered' gate and the AUC CI in the evidence table inherit the optimistic, fold-biased AUC from PB/PC (see those panels). So 'Adequately powered (>=80%)' can pass and 'Deployment AUC (95% CI 0.51–0.74)' can appear to exclude chance when neither is honestly established. These are the two evidence rows a signer weights most.
  - *fix:* After de-folding the bootstrap CI (PB finding) and powering off the CI lower bound (PC finding), these rows become honest automatically. Until then, annotate the AUC-CI row that the lower bound is censored at 0.5.
- **[low]** n_gates_passed is a simple count of six heterogeneous gates with no notion that some are necessary (deployable threshold, adaptive band) vs supportive (powered, credible CI). '5 of 6 passed' reads as near-ready even if the one failure is a hard necessary gate. The multiple-comparison exposure from the band sweep is disclosed as a caveat but never enters the gate arithmetic.
  - *fix:* Mark necessary gates and block 'ready to program' on any necessary-gate failure regardless of the passed count; keep supportive gates as the soft tally. Optionally note that no gate is corrected for the band-selection search.


### Time-Series / Temporal Validity
> Through the temporal-validity lens this is an honest, well-guarded module: the causal forecasting default is the deploy choice, within-cluster double-dipping is correctly removed, power uses the cluster count, and in-sample optimism is stated in caveats. The remaining gaps are about uncertainty quantification and forward validity rather than gross leakage. The two that matter most for 'will this threshold still fire correctly next month': (1) every reported number is in-sample with no forward-chaining estimate, and (2) the bootstrap clusters on per-rating units finer than the glmer's weekly unit and ignores between-cluster serial correlation, over-narrowing the very AUC CIs that the deploy gates depend on. One caveat I cannot resolve from this bundle: the causal-matching code that builds td_detail is upstream and not shown, so 'no look-ahead' in the forecasting match is asserted but unauditable here and should be unit-tested.

**P0** — actionability: *medium*  
- **[medium]** ⚑act The header's independence unit ('weekly eras', from the glmer per-week random intercept) is a COARSER cluster than the unit used downstream in the ROC bootstrap (per-PRO-rating 'rating_group'; deployment_roc docstring calls it 'the per-rating random intercept'). A clinician comparing 'N weekly eras' here against 'M independent ratings' in panel PB sees two different effective-sample numbers for the same band, and — more importantly — the two analyses disagree on what counts as one independent observation. If the mixed model clusters by week because within-week ratings are correlated, the per-rating ROC bootstrap is under-clustered.
  - *fix:* Reconcile the independence granularity across panels: either label PB's count explicitly as 'per-rating clusters (finer than the weekly model unit)' or, preferably, cluster the ROC/era bootstraps on the same weekly unit as the glmer (see PB finding). At minimum, make the header note that the AUC CI in PB uses a finer cluster than the OR CI shown here.
- **[low]** 'Stim stability' is presented as a binary stim-stable/stim-dependent from a single LRT over the whole record. Stim-state is itself time-varying and the eras are interleaved in calendar time; a band can be stable on average yet drift within a long OFF block. The header gives no sense of WHEN the per-era ORs were measured.
  - *fix:* Acceptable as a summary, but consider a tooltip noting that per-era ORs pool temporally-scattered samples within each stim state (not contiguous time windows).

**PB** — actionability: *medium*  
- **[high]** ⚑act Every number in this panel is in-sample on one contiguous record: the ROC, the AUC, the Youden/F1/cost operating point, and its sensitivity/specificity are all fit and evaluated on the same data, with NO temporal hold-out or forward-chaining (train on weeks 1..k, test on week k+1). For a deployable controller the decision-relevant quantity is forward (next-week) performance, not pooled in-sample AUC. The caveat text acknowledges optimism but the panel still shows only the optimistic numbers — there is no de-biased / forward estimate the clinician can read.
  - *fix:* Add a time-ordered forward-chaining estimate (expanding-window or blocked k-fold over elapsed weeks) and report the mean held-out AUC and the held-out sensitivity/specificity AT the operating point chosen on the training fold. Show it alongside the in-sample number ('in-sample AUC 0.74 · forward-validated 0.6x'). This is the single biggest deploy-readiness gap and does not touch the Plotly.react/restyle pattern (it is new backend numbers, not a figure rebuild).
- **[medium]** ⚑act The clustered bootstrap resamples WHOLE rating clusters but treats clusters as exchangeable/independent. Adjacent-in-time ratings are serially correlated (pain state evolves smoothly week-to-week; device/baseline drift), so resampling individual clusters removes within-cluster but not BETWEEN-cluster (serial) correlation. The CI is therefore still over-narrow, and it is computed on a per-rating cluster that is finer than the glmer's weekly unit (compounding the narrowing). The note's claim that 'the CI reflects the count of INDEPENDENT ratings' overstates independence.
  - *fix:* Use a moving-block / circular-block bootstrap over time-ORDERED clusters (block length ~ the rating autocorrelation horizon, e.g. 1 week), or cluster on the same weekly unit the glmer uses. Either widens the CI to reflect residual serial correlation. Report the block choice in the note so the CI is interpretable.
- **[medium]** Whether the 'prior'/forecasting match is genuinely causal (neural window strictly BEFORE the rating, no look-ahead) cannot be verified from this bundle — the matching that builds td_detail (labels/rating_group/times) is upstream and not shown. This is the most deploy-critical temporal property (any look-ahead inflates AUC), yet it is unauditable in the reviewed source, and the forecasting horizon (how far before the rating, and how it relates to the device's real-time sensing latency) is not surfaced.
  - *fix:* Surface and unit-test the prior-match logic: assert every matched neural window's end time < rating time, and expose the match tolerance / horizon in the panel provenance line. A one-line invariant check at match time prevents silent look-ahead leakage from inflating every downstream number.

**PC** — actionability: *medium*  
- **[medium]** ⚑act Both the feature percentile and the device Timeline-LSB percentile are computed GLOBALLY over the whole record, so the deployable LSB number assumes the band-power and the device-LSB distributions are stationary. If the device LSB baseline drifts over weeks (gain/impedance drift, or genuine neural baseline drift), the fixed programmed threshold will fire at a different effective operating point next month — the 'will this threshold still fire correctly next month' question is not addressed and no drift check is shown.
  - *fix:* Add a drift diagnostic: compute the band-LSB percentile (or the threshold's implied firing rate) per elapsed week and show its trend/spread; warn if the weekly threshold drifts beyond a tolerance. This reuses the existing weekly-cluster machinery and does not change the headline number, only qualifies its durability.
- **[medium]** ⚑act The power-vs-N curve extrapolates by scaling n_pos/n_neg at fixed prevalence and re-evaluating Hanley-McNeil power, i.e. it assumes each future rating is an independent iid draw. Because ratings accrue over time and are autocorrelated, 'N independent ratings' overcounts effective sample size, so the current power is overstated and 'need ~X more ratings for 80% power' is optimistic (more calendar time / more effectively-independent ratings will actually be required).
  - *fix:* Discount the effective N by an estimated autocorrelation/design-effect factor (e.g. derive an effective-rating count from the weekly clustering), or relabel the x-axis as 'effective independent ratings' and state that calendar ratings needed will be higher. Keep the curve as-is visually; only the N mapping changes.

**PD** — actionability: *medium*  
- **[medium]** ⚑act Stim eras are strata defined by amplitude, not contiguous time folds — OFF/LOW/HIGH samples are interleaved across calendar time as stim is cycled. So this panel measures robustness to stim STATE, not temporal generalization; it does not tell the clinician whether the threshold holds at a LATER time, only across stim levels. The module presents no time-ordered hold-out anywhere, and a reader may mistake per-era stability for forward stability.
  - *fix:* Keep this panel, but add (or cross-reference) a genuinely temporal split (per-week or first-half/second-half AUC and cut-point) so 'portable across stim states' is not read as 'portable across time'. Word the verdict to scope it to stim state.
- **[medium]** ⚑act The portability verdict keys on cutpoint_spread (max-min of the per-era Youden thresholds), but each per-era Youden cut-point is RE-OPTIMIZED on a small, possibly thin stratum. On small OFF/LOW strata the Youden threshold is a high-variance estimate, so the cut-point spread is inflated by re-optimization noise and the 'Fragile across stim states' verdict can fire on estimation noise rather than true non-portability. The spread has no uncertainty attached.
  - *fix:* Put a bootstrap CI on the cut-point spread (resample clusters, recompute per-era Youden, take the spread distribution) and base the fragility verdict on whether the spread CI excludes a small tolerance, and/or require a minimum cluster count per era before including it in the spread. This avoids labeling a band fragile because a 12-sample era moved its threshold.
- **[low]** A single PRO rating cluster whose matched neural windows straddle a stim change can have its samples split across two eras (era is assigned per-sample by time). That cluster is then partially counted in two eras' bootstraps, mildly violating the cluster-as-independent-unit assumption within eras.
  - *fix:* Assign each rating cluster a single era (e.g. by the cluster's rating time / modal era) so clusters are not split across strata; negligible effect for most bands but tidies the independence accounting.

**PE** — actionability: *medium*  
- **[high]** ⚑act The gate checklist the clinician signs against is entirely in-sample. 'Credible effect-size CI' depends on the bootstrap/glmer CIs that are over-narrow due to residual serial correlation, and 'Adequately powered (>=80%)' depends on the iid-rating power that overcounts effective N — so both gates can PASS prematurely. There is no gate for forward/temporal-holdout performance, meaning the strongest visual signal of 'ready to program' carries no prospective-validity check.
  - *fix:* Add a 'forward-validated' gate (passes only when the forward-chaining held-out AUC CI clears chance) and widen the CI/power inputs per the PB/PC fixes. Until a forward estimate exists, downgrade 'credible CI' and 'powered' to caveats or annotate them 'in-sample' so the sign-off does not imply prospective readiness.
- **[low]** The exported JSON record (schema deploy_signoff_v1) captures the operating point and in-sample evidence but has no field for temporal-validation status or threshold-drift, so the device-programming record cannot later show whether the threshold was checked for forward stability or re-checked as the signal drifted.
  - *fix:* Add forward_validation and threshold_drift fields (even if 'not assessed') to the export schema so the auditable record states the temporal-validity status at sign-off time.


### Scientific Visualization
> From the publication-grade visualization lens this module is close to deploy-ready and clearly past its earlier rounds: the Okabe-Ito palette is adopted with genuine CVD discipline (blue/vermillion histogram, green/orange/vermillion decision triad with no green/red pairing), the sign-off gates are correctly redundant (icon + color + text), and the chart choices are right (ROC + movable cut-point, power-vs-N sufficiency curve, per-era forest replacing text cards). The defects are concentrated and fixable without touching the imperative Plotly.react-once + restyle/relayout architecture: a systemic contrast failure of the warn-orange ink on exactly the safety-critical alerts, one genuine misencoding (non-estimable eras rendered on the chance line), a muddy overlapping histogram, and a handful of self-containedness/CI-labeling gaps. None are blocking, but the orange-contrast and chance-line items should be resolved before the card is printed for an actual programming decision, since both degrade the figures precisely where they must stop a bad deployment.

**P0** — actionability: *medium*  
- **[medium]** ⚑act The verdict badge sets backgroundColor=verdictColor(...) with color:'white'. White-on-warn-orange (#E69F00) has a measured contrast ratio of 2.25:1 (fails WCAG AA 4.5 and large-text AA 3.0). The 'VALIDATED (stim-dependent)' verdict — the one that most needs to be read carefully — is the least legible badge.
  - *fix:* Keep the orange fill but switch badge text to near-black (#1a1a1a) for the warn role (orange→dark text = ~8:1), or darken the warn ink to a vermillion-family tone for badges. Text already carries the verdict, so this is purely a legibility fix and changes no logic.
- **[low]** The adaptive-band chip uses MUI color='success' (framework green) when valid and a one-off backgroundColor '#f1d9b5' (pale tan) when off-band. Both escape the shared PAL palette that the module otherwise standardized on — the 'success' green is not the vetted Okabe-Ito bluishGreen, and #f1d9b5 is an un-vetted low-contrast fill.
  - *fix:* Route this chip through PAL (pass fill for valid, warn fill for off-band) so the one remaining hardcoded color obeys the same CVD discipline as the rest of the module. The chip already carries text ('adaptive-valid' / 'off adaptive band'), so encoding stays redundant.

**PB** — actionability: *high*  
- **[medium]** ⚑act Overlapping histogram: barmode='overlay' with opacity 0.62 on BOTH classes. Where pain-low (blue) and pain-high (vermillion) overlap, the blend renders as a muddy purple-brown that reads as a third category — and the overlap region is exactly the class-separation zone the figure exists to show. In grayscale the blended band is uninterpretable.
  - *fix:* Render one class as a filled bar and the other as an outline/step histogram (Plotly: a bar trace + a line 'shape=hvh' or a second bar with marker.line only), or drop opacity on the rear class and outline the front. This removes the blended-third-color ambiguity and survives grayscale. It is part of the once-per-dataset trace build, so the Plotly.react-once discipline is untouched.
- **[medium]** The AUC CI is labeled only '95% CI' in the figure title. A reader of the figure alone cannot tell it is a rating-CLUSTERED bootstrap CI (the methodological point that distinguishes it from a naive, over-tight per-sample CI — the whole reason the backend computes it that way). The 'clustered' provenance lives only in the detail line / backend note.
  - *fix:* Title or a one-line subtitle: 'AUC = X (95% clustered-bootstrap CI a–b, k ratings)'. Static layout text built once; no interaction rebuild.
- **[low]** Feature x-axis label phrasing is inconsistent across the module: histogram says 'Oriented band power (cut-point scale)', the cut-point readout says 'oriented log-power units', and the backend feature_units says 'oriented log10 band power (z-scored)'. Three names for one axis, and none tells the clinician the quantity is standardized/unitless (z-scored), so the absolute number looks like it should mean something physical when it does not.
  - *fix:* Pick one phrasing everywhere, e.g. 'Oriented band power (standardized, cut-point scale)', and note once that it is dimensionless — the deployable number is the LSB threshold in Phase C. The histogram's job is showing overlap, so the standardized scale is fine once it is named as such.
- **[low]** Degenerate cut-point marker annotation uses white text on the warn-orange bgcolor (white-on-#E69F00 = 2.25:1). Same contrast weakness as the P0 badge, here on an on-curve callout.
  - *fix:* Use dark annotation text when mColor is the warn orange (keep white only for the bluishGreen non-degenerate marker), via relayout — preserves the no-rebuild pattern.

**PC** — actionability: *high*  
- **[medium]** ⚑act Power-curve self-containedness: the two markers ('now' and 'need X') are identified only by hover tooltip and color; only the 80%-target LINE carries an on-figure annotation. A glance, a printout, or a grayscale view cannot tell which marker is current vs required, which is the entire message of the panel.
  - *fix:* Add two static layout annotations next to the markers ('now: N', 'need: M for 80%') in the once-built layout. Plotly.react draws them once; nothing rebuilds on interaction.
- **[medium]** µV²/LSB confidence color is `confidence==='low' ? fail : warn` — so a HIGH-confidence ratio is painted warn-orange, identical to medium. The color signals 'caution' for a value that is actually trustworthy, contradicting the text. Orange-on-white at this small size is also 2.25:1.
  - *fix:* Map confidence to three roles: high→pass (or neutral), medium→warn, low→fail; and use a darker tone for the orange text. The textual '(confidence: …)' already carries the label, so this only fixes the misleading at-a-glance hue.
- **[low]** Power-curve y-axis label 'power vs AUC 0.5 (%)' is statistical jargon for a clinician audience; 'power' here is statistical power, not a neural-power quantity (which the same panel ALSO discusses as 'band power'), inviting a terminology collision on one screen.
  - *fix:* Rename to 'Statistical power to detect AUC > 0.5 (%)' or 'Detection power (%)' to disambiguate from band power. Section header already says 'POWER vs SAMPLE SIZE'.
- **[low]** The degenerate-cutpoint guard box has `border: '1px solid '` with no color token — an incomplete CSS border that falls back to currentColor, so the warning box that must stand out gets an unintended/weak border.
  - *fix:* Set `border: \`1px solid ${PAL.warnBorder}\`` to match the other warn boxes.

**PD** — actionability: *high*  
- **[medium]** ⚑act Non-estimable eras are drawn as a faint open marker placed AT x=0.5 — exactly on the chance line. Visually this reads as 'this era's AUC = 0.5 (chance)' rather than 'this era has no estimate'. A clinician scanning portability could misread an under-sampled era as 'performs at chance', which is a different and consequential conclusion.
  - *fix:* Do not place the missing-data glyph on a meaningful data value. Render the row with an explicit on-figure 'n/a (insufficient samples)' text annotation at the axis margin and no point on the AUC scale, or a distinct '×' off to the side. Keeps the row visible (its stated goal) without encoding absence as chance.
- **[medium]** ⚑act The shaded pooled-CI reference band (accent blue at ~0.09 effective alpha) carries no on-figure label, so a reader of the figure alone — or a grayscale print, where the faint blue fill nearly vanishes — cannot tell the vertical band IS the pooled 95% CI. The whole 'do per-era CIs overlap pooled' read depends on knowing what the band is.
  - *fix:* Add a small static annotation ('shaded = pooled 95% CI') in the once-built layout, and/or bracket the band with thin dotted edges so it reads in grayscale. No interaction rebuild involved.
- **[low]** X-axis label 'AUC (95% CI)' does not state the CI is a clustered bootstrap (same gap as PB). And LOW (orange) vs HIGH (vermillion) are the closest-luminance pair in the palette (0.638 vs 0.441 is fine, but orange vs vermillion hues are the weakest contrast) — acceptable only because row position disambiguates.
  - *fix:* Label as '(95% clustered-bootstrap CI)'. Era color pairing is acceptable given the labeled rows; no change needed there.

**PE** — actionability: *high*  
- **[medium]** ⚑act The headline verdict ('X of Y gates passed — review caveats') is rendered in warn-orange (#E69F00) on the near-white warnFill at 14px when not all gates pass — orange-on-white = 2.25:1, failing WCAG. The most safety-critical line on the deploy card (the 'do not just program this' signal) is the least legible text in the module.
  - *fix:* For the warn state, use dark text on the orange fill (or a darker amber for foreground); reserve #E69F00 for fills/area, not small critical text. Wording already carries the verdict, so this is a pure contrast fix.
- **[low]** The evidence table labels both the Deployment AUC CI and the Odds-ratio CI as '(95% CI)', but they come from different procedures (AUC = clustered bootstrap; OR = glmer profile/Wald). A reader cannot tell two different interval methods apart in one table — minor for a clinician, relevant for the auditable record this card is meant to be.
  - *fix:* Tag the methods once: 'AUC 95% CI (clustered bootstrap)' / 'OR 95% CI (mixed-effects)', or a single footnote on the table.


### Plotly Interaction + Actionability
> From the interaction-engineering lens the module is in strong shape: the imperative Plotly.react + restyle([index]) + relayout pattern is implemented correctly and consistently, the 250 ms cut-point debounce and the requestParams memoization are exactly the right calls to stop interaction-driven refetch storms, and purge-on-unmount-only reuses graph nodes across refits — the no-rebuild contract from 255e0ef holds everywhere. The remaining gaps are about ACTIONABILITY and record-keeping rather than correctness: the figures cannot be exported (modebar hidden), the deployable threshold is shown with no current-programmed anchor for tuning, the sign-off record omits the justifying figures, and the closed-loop ramp parameter is absent from a module that otherwise covers band + threshold. The one latent code hazard is the hardcoded cut-point trace index, which should be single-sourced before the next edit to those traces.

**P0** — actionability: *medium*  
- **[low]** The header surfaces the band's identity and evidence but offers no affordance to act on it — there is no link/jump to the panel that consumes each fact (e.g. 'off adaptive band' chip does not point to the PE caveat that explains the consequence). For a multi-panel deploy workflow a clinician scans top-to-bottom; the header could anchor the workflow.
  - *fix:* Optional: make the adaptive-band chip and verdict badge scroll-link to the corresponding PE gate. Low priority — the information is present, only the navigation is manual.

**PB** — actionability: *high*  
- **[medium]** The cut-point marker's trace position is a hardcoded literal `[2]` in the Plotly.restyle call, with the index relationship to the base-trace array (chance=0, ROC=1, cut-point=2) implicit and uncommented at the restyle site. Any future edit that reorders or inserts a base trace (e.g. adding a second curve, a confidence band) silently moves the marker and the restyle will mutate the wrong trace with no error — a latent regression of exactly the class of bug 255e0ef fixed.
  - *fix:* Define a named constant at module top (e.g. `const CUTPOINT_TRACE = 2;`) used both when building the traces array and in the restyle index, so the index is single-sourced and self-documenting. Zero behavior change; removes the silent-reorder hazard.
- **[medium]** ⚑act displayModeBar:false removes the toImage (PNG download) and resetScale controls from every figure in the module. For an auditable device-programming decision the clinician cannot export the ROC/histogram as an image for the record (PE's JSON carries numbers, not figures), and after zooming the ROC there is no visible reset affordance (double-click still resets axes, but nothing signals that). The clean look costs the two affordances the clinical-record use-case most wants.
  - *fix:* Enable a MINIMAL modebar instead of hiding it: `modeBarButtonsToRemove` everything except `['toImage','resetScale2d']`, with `displaylogo:false`. Preserves the uncluttered view, gives the clinician figure-export for the record and an explicit zoom-reset, and does not touch the draw pattern.
- **[medium]** ⚑act The panel hands a threshold to PC in 'oriented log-power units' and PC re-displays it as 'power ≥ X LSB' — two different numbers on two cards connected only by prose ('→ device LSB in the next panel'). The clinician must trust that the abstract feature number and the LSB number are the same operating point; nothing visually ties them, and the lifted cut-point's provenance (which rule, what sens/spec) is re-shown in PC/PE but not visually linked back to the marker they moved.
  - *fix:* Echo the chosen rule + sens/spec as a one-line chip at the top of PC ('Operating point: Cost-weighted · sens 0.74 / spec 0.69 · from ROC panel') so the PB→PC handoff is explicit, and/or annotate the histogram threshold line with the resulting LSB value once PC has computed it. Reinforces that one operating point flows through all four panels.
- **[low]** The figure container is hidden via display:none until roc arrives, and Plotly.react is called with responsive:true. Plotly sizing on a display:none node reads clientWidth 0; here the div flips to block in the same commit that sets roc, so the post-paint effect generally sees a laid-out node — but this is the documented Plotly hidden-div footgun and is fragile to any future change that mounts the panel inside a collapsed/tabbed container (the band-candidate JSON inspector below already uses a collapse).
  - *fix:* Low-risk as currently laid out. If any panel ever moves into a tab/accordion, add a Plotly.Plots.resize(gd) on reveal. No change needed today; note the invariant in a comment so the next editor doesn't wrap these in a collapse.

**PC** — actionability: *high*  
- **[medium]** ⚑act The needed-N marker is placed at y = target_power*100 (on the 80% line) rather than at the curve's own power value at n_ratings_needed. Because n_ratings_needed comes from the closed-form SE²·N≈const solve while the curve is exact Hanley–McNeil, the marker can sit visibly OFF the plotted curve, which reads as a rendering glitch on exactly the figure whose message is 'how many more ratings'. (Stats reviewer flagged the same inconsistency from the math side; from the interaction side it is a marker-placement bug.)
  - *fix:* Place the needed-N marker at the curve's interpolated power at n_ratings_needed (the curve array already exists — interpolate curve.power at curve.n≈n_need), so the marker always lies on the line. Pure presentation fix, no backend change.
- **[medium]** ⚑act The deployable LSB threshold is presented with no comparison to what is CURRENTLY programmed on the device. The entire clinical task is TUNING an existing setting; a recommended number with no current-value anchor forces the clinician to context-switch to the programmer to know whether this is a small nudge or a large change — the single most actionable thing this panel could add.
  - *fix:* If the current device adaptive-threshold setting is available in the recording metadata, show 'recommended X LSB vs currently programmed Y LSB (Δ)'. If not available, surface a one-line 'current programmed value unknown — enter to compare' field. This is the highest-value actionability add for the tuning workflow.
- **[low]** The degenerate-cutpoint guard MDBox has `border: '1px solid '` with no color token — an incomplete CSS value that falls back to currentColor, so the warning box that must stand out gets an unintended/weak border. (Also caught by Viz.)
  - *fix:* Set `border: \`1px solid ${PAL.warnBorder}\`` to match the other warn boxes.

**PD** — actionability: *medium*  
- **[low]** ⚑act The forest plot is the module's portability evidence but is entirely non-interactive — no hover-to-compare against the pooled band beyond the per-point tooltip, and (with displayModeBar:false) no way to export it for the sign-off record. Given PE assembles an auditable sheet, the portability figure cannot travel into that record except by screenshot.
  - *fix:* Covered by the module-wide minimal-modebar recommendation (PB finding): enabling toImage lets this figure be exported into the device record. No structural change to the panel.
- **[low]** The portability verdict (a text MDBox) is rendered separately from the figure, so the 'fragile/portable' conclusion and the visual it is drawn from are not co-located for a glance or a printout — a reader can see the forest without the verdict scrolling into view, or vice-versa.
  - *fix:* Optionally render the verdict as a short on-figure annotation (drawn once in the layout) in addition to the box, so figure and conclusion are one unit in a screenshot/print. Preserves the draw-once pattern.

**PE** — actionability: *high*  
- **[medium]** ⚑act The exported JSON record (deploy_signoff_v1) and the printed sheet contain only NUMBERS and gates — none of the four figures (ROC, histogram, forest, power curve) that justify the decision. For a device-programming record meant to be auditable months later, the visual evidence the clinician actually judged is not captured; window.print() will include whatever is on screen but the structured JSON export (the durable artifact) has no figure payload or even a thumbnail/URL.
  - *fix:* Add the four figures to the record: either embed Plotly.toImage(gd) PNG data-URIs (the panels expose their gd refs) into the exported JSON, or at minimum list the operating point + the in-sample-vs-(future)forward numbers so the record is self-justifying. Pairs naturally with enabling toImage via the minimal modebar.
- **[medium]** ⚑act The module surfaces sense-band (P0 identity) and threshold (PC) for tuning, but the project's stated closed-loop tuning surface is sense band + threshold + RAMP, and there is no panel or field for the adaptive ramp parameters (onset/offset duration, rate). A clinician leaves the sign-off with two of the three programmable closed-loop quantities specified.
  - *fix:* Add a ramp-guidance line to the sign-off (even a defaulted/advisory 'ramp: clinician-set; suggested onset/offset N s' tied to the feature's temporal dynamics), so the deploy record covers all three tunable parameters. Larger scope than a fix — flag as the natural Phase-3 actionability item.
- **[low]** Print relies on window.print() with no print-specific stylesheet, so the printed sheet inherits screen layout (dark JSON inspector background, MUI cards with shadows) and the four figures may paginate awkwardly. The auditable artifact's print fidelity is left to the browser default.
  - *fix:* Add a @media print stylesheet (hide the JSON inspector + nav, force light backgrounds, avoid breaking a figure across pages). Low effort, materially improves the printed record.


---
## Recommended fix sequencing

**Wave 1 — correctness (backend-only; no Plotly change, no risk to the no-rebuild contract):**
1. **C1** de-fold the AUC bootstrap (`append ab`, not `max(ab,1-ab)`) + move to a weekly/block bootstrap. This single fix de-biases the CI that **C4** (power) and **C8** (gates) inherit.
2. **C3** orient per-era ROC once from pooled (surfaces sign reversals); base the portability verdict on the existing band×era LRT / CI overlap, not raw spread.
3. **C8** give the stim-stable gate an *indeterminate* state; mark necessary vs supportive gates.
4. **C2** add forward-chaining (expanding-window by week) and report held-out AUC beside the in-sample number; add a 'forward-validated' gate.

**Wave 2 — figure honesty & self-containedness (draw-once layout annotations only):**
5. **C7** label CI method on every figure; outline one histogram class; add on-figure annotations for the PD pooled-CI band and PC now/needed markers. **C5** place the needed-N marker on the curve. **C6** dark text on warn-orange.

**Wave 3 — actionability & hygiene:**
6. **C9** single-source the cut-point trace index. **C10** recommended-vs-programmed Δ in PC, ramp guidance + figure embedding in the PE record, minimal modebar (toImage + resetScale) across panels.

> Every Wave-1/2 fix preserves the imperative `Plotly.react` + `restyle/relayout` pattern (commit 255e0ef). None requires rebuilding a figure on interaction.
