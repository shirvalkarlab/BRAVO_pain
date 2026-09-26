# Synthesis — the Biomarkers pipeline, alternative methods, the Stim Optimizer's Bayesian algorithm and the Closed-Loop Deployment page (2026-09-22)

What this is: the PI asked (2026-09-22) for a literature audit of the Biomarkers pipeline, alternative detection and symptom-tracking methods, an end-to-end analysis of the Stim Optimizer's Bayesian algorithm, and an integration review of the Closed-Loop Deployment page, with the frontend goal "simple, human-readable, clearly separated ideas in logical order"; then for each report a three-reviewer panel (biostatistician, engineer, pain neurologist standing in for him) debating on a shared board and voting until consensus (at most five rounds, three reviewers at once); then a measure of uncertainty on every decision, with the statistical probability and its intervals tested on the record. Four research reports, four panel plans and this synthesis are in `artifacts/research_2026-09-22_*`. Every measurement below was run tonight on RCS08's live record through the bridge with the store's writes off; the probe scripts are gitignored scratch (`BRAVO/_agent_bridge/_*`).

Two ruled tonight by the PI and built: the reliable-change index deleted (decision 231, commit `2f8fb985`); the exploratory ladder committed (decision 230, `2e8a4e5f`).

## 1. The one finding that runs through all four reports

**On the left lead, the bands that "rise with pain" rest on the current in force.** The grid's correlation between band power and pain is a plain Pearson r with no term for the stimulation current (`analytics._weighted_pearson_matrix`); the evidence triangle's E2 estimator (`edges.state_edge` → `band_pain_auc`) has none either; the older per-session search (`pipeline.py`, `partial_corr`) does. Measured tonight:

- L 1-3+, every cell of the 21.5-26.5 Hz cluster decision 229 called "supported" (60 s, 120-minute pre-report window, n 59): r drops by 0.10-0.18 once the left current in force at each rating is partialled out, and every adjusted interval spans zero; the drop's block-bootstrap interval excludes zero in all six cells (24.5 Hz: r 0.331 (0.17-0.49) → 0.170 (-0.05-0.39); drop -0.161 (-0.31 to -0.04), shuffle p 0.030). Pain and power both fall with current (r -0.40 and -0.50).
- L 0-3+, the exploratory ladder's own watch bands under the readiness screen's settings (NRS, 60-minute window): 24.5, 25.5, 26.5, 27.5 Hz all lose their wholly-positive interval (24.5 Hz 0.207 → 0.113, -0.07 to 0.27); NRS falls with the left current at r -0.45.
- Out of sample, the current in force alone does not forecast the pain label (purged time-blocked CV, AUC 0.41 against a rotation null median 0.38, 95th 0.57, 611 ratings), even though in the pooled record Left Leg VAS averages 58 at 0 mA and 46-53 at 3.0-4.8 mA: the good stretches were the high-current stretches, not a dose signal.

What it changes: the 24.5-27.5 Hz bands are not a pre-specified watch list for the ladder's ramp (part A); a band earns credit only if it also moves during the fixed-current holds (part B). The ramp still measures the current-to-power slope, which is what part A is for. Every panel's top build is the same one: the grid's correlation adjusted for the current in force, behind a switch (panel A item 1; 2-3 days; P 65%, 30-92), with its consequences on the readiness table (C item 6) and the evidence triangle (D items 9 and 4).

## 2. The four verdicts

- **A. The Biomarkers pipeline** is above the two landmark human studies on band-wise correction, autocorrelation handling and out-of-sample honesty; its two gaps are the current confound (§1) and no family-wide accounting across the 252-setting search. The family-wide gap was measured rather than built: positive p < 0.05 cells in 6 of 252 settings against about 106 expected under independent tests (with sheets on, 61% of rows are negative under 0.05: the clinic sheets, taken while current is stepped). Consensus in round 4; 7 actions adopted, 1 resolved by measurement (every recording is bipolar; the cardiac artefact bounded), 1 dropped by the PI (231).
- **B. Alternative methods**: of thirteen, one build now (decision 230's three fixed-current holds presented as the titration card's first pain reading), three guards (the current-confound gate on every offline model, a shared purge/embargo helper for time-blocked cross-validation, a caveat where current is shown against pain), one report fix, and two stops: the two-state model of the ratings is not identifiable (on 60 series simulated from its own fit, 29 refits converge and recover dwell times of 1 and 220 ratings against a truth of 11; on one-state noise it invents a 45-point regime gap against the real 22), and the multivariate decoder waits on a two-part gate (its current-partialled diagnostic clearing the null, and a device-allowed pair carrying a pain-positive band; today none). The chronic 10-minute log does cover 19 held setting changes with 7+ days on both sides, so the dated-event level-shift check is buildable (8-14 h). Consensus in round 3.
- **C. The Stim Optimizer's Bayesian algorithm**: the engine is sound and correctly prints no current (92 epochs, 64 settings, 47 tried once; no rate passes the honest-current rule; the closest is the clinic stream at 55 Hz, two of three checks passing and 4 current pairs short), but **the surrogate fails its own pre-registered calibration check and nothing on the live path runs it**: on the live per-rate strata, 55 Hz (19 epochs) leave-one-quarter-out error ratio 1.315 with 95% coverage 0.37 and PIT p 0.000; 110 Hz (10 epochs) 1.087. The panel read it as misspecification (a surface that moves between quarters) rather than sparsity, demoted the report's boundary-avoiding kernel behind that diagnosis, and adopted: the check as a reported field (1-2 days), the clinic-stream site defect fixed (`fit_clinic_rate_strata` hard-codes the left leg, found tonight), the back site retired from the request pending the PI, the titration session aimed at the 4 missing pairs, the page's order with the two readiness cards kept apart. Consensus in round 4.
- **D. The Closed-Loop Deployment page**: the argument is in the right order; the evidence is weaker than the verdict word (E1 -7.31 per mA, -47.3 to +32.6; E2 AUC 0.559, 0.42-0.70; thresholds and timing without intervals; stability "cannot tell") and the page does not say E2 rests on the current in force. Adopted: an interim E2 caveat now, one verdict on the sign-off card, band stability into "what would change this", one ranked caveats list on the printed record naming the numbers without intervals, E2 re-measured with the current partialled out (method named), three unread field groups deleted from the response. The right-hemisphere check the report could not run was run: a right candidate reads the right lead's own record (45 points over 9 runs; slope +29.3 per mA, power rising with current, which the control law cannot use; "blocked"). Consensus in round 3.

## 3. The cross-cutting build order, with the panel's uncertainty and the measurement behind each

| Order | Action | Panel | Cost | P (range) | Measured premise |
|---|---|---|---|---|---|
| 1 | The grid's correlation adjusted for the current in force, behind a switch; drawer lines state the adjusted values | A-1, A-5 | 2-3 days + 1 h | 65% (30-92) | yes (§1) |
| 2 | Interim caveats now: on the evidence triangle's E2 axis; beside the current-map card; the drawer's "established" versus q wording | D-9, B-8, A-5 | under 2 h each | 10-15% | yes |
| 3 | Decision 230's fixed-current holds as the titration card's first pain reading after the visit; both ladder readings available | B-1, A-8 | low-medium | 55% (15-85) / 40% (15-70) | after the visit |
| 4 | The Stim Optimizer's calibration check as a reported field; the clinic-stream site defect fixed; the back site retired from the request | C-2, C-9, C-1 | 1-2 d, under 1 d, under 1 d | 45% (20-90) / 70% (45-90) / 60% (40-80) | yes (C §1) |
| 5 | The titration session aimed at the 4 missing current pairs at clinic 55 Hz (60/160 µs) | C-10 | 1 d | 40% (15-65) | yes |
| 6 | The current-confound gate and the shared embargo helper for every offline model | B-2, B-7 | low; 2-4 h | 40% (10-70) / 30% | yes |
| 7 | The closed-loop page: one verdict on the sign-off, stability into "what would change this", the caveats list, stability beside the triangle, E2 re-measured with the current partialled out | D-1, D-2, D-3, D-5, D-4 | 1-4 h, 2-5 h, 5-6 h, 4-5 h, 1-2 d | 15-30% | yes |
| 8 | The Stim Optimizer page's order and wording (two readiness cards kept), the readiness table's "still positive once the current is removed" field (PI ruling), the multiple-comparison exposure, the length-scale pin, the labelling pass | C-5, C-6, C-4, C-7, C-8 | 1-2 d, 1 d, hours, under 1 d, under 1 d | 10-40% | — |
| 9 | Housekeeping: effective count on the grid page, the F8 reconciliation fields on the grid's permutation path, the time-of-day diagnostic, the family-wide proxy paragraph, the coverage-number wording, the unread closed-loop fields deleted | A-4, A-3, A-9, A-2, B-6, D-10 | 3-5 h, 4-6 h, hours, hours, under 1 h, 2 h | 3-15% | yes where measurable |

Gated or stopped: the HMM / smoothed-label hybrid (not identifiable; record it), the multivariate decoder (two-part gate), the boundary-avoiding kernel (only after the surrogate passes its check or the failure is diagnosed), the full family-wide shuffle of the 252-setting search (deferred), the aperiodic / coherence / DTW / Kalman-state ideas (dropped), a full overhaul of the optimizer (tried, measured, deleted), a time-varying kernel (reverses 193-196).

## 4. Open questions for the PI, collected

1. **How the ladder's data is read for pain**: the ramp (part A) only with the current term, or the fixed-current holds (part B) only? (A-8, B-1; P 40%, 15-70, that the choice changes the reading.)
2. Whether "supported" (decision 210) should require a band to stay positive once the current in force is partialled out; every qualifying band on the left today would fail it (C-6, D-4).
3. Whether the L 0-3+ 125 Hz cell stays the readiness screen's chosen cell for the exploratory ladder, given §1.
4. The back site: retire from the request for now, or wire a parallel fit once the clinic-stream defect is fixed (the 2026-08-30 direction says parallel)?
5. Whether the next titration session runs at 55 Hz 60/160 µs (the stratum four pairs short) although the pairing in force is 100/150.
6. Whether the calibration check, once reported, becomes blocking as the spec's §6 says.
7. Whether the adjusted grid lives on the page behind a switch or is run once and recorded.
8. Whether the chosen closed-loop band should be recorded on the server rather than in the browser.

## 5. How the uncertainty was produced, and its limits

Each reviewer gave, for every vote, a probability that the action once built changes or materially strengthens the programming decision for RCS08, with a range they would bet on at 9-to-1; the tables report the median of the three and the range from the lowest low to the highest high. That is expert elicitation by language models in assigned roles: it is a structured statement of confidence, not a measurement, and its ranges are wide. Where the premise of an action could be measured on the record tonight it was, with block-bootstrap or shuffle intervals, and those measurements are what the panels relied on to change their votes: the current-partialled correlations (A-1, four rounds to consensus, P rising from 30% to 65% as the cluster and L 0-3+ results came in), the identifiability bootstrap (B-4, a stop), the calibration failure (C-2 and C-3, the kernel demoted), the right-lead run (D-6, resolved). Every measured number carries its interval in the panel plans; the numbers that carry none on the pages today are named in D-3.

## 6. Source index (the four reports carry the full literature and codebase indexes)

- `artifacts/research_2026-09-22_A_biomarkers_pipeline_literature_audit.md` and `..._A_PANEL_consensus_and_action_plan.md`
- `artifacts/research_2026-09-22_B_alternative_detection_and_symptom_tracking.md` and `..._B_PANEL_...`
- `artifacts/research_2026-09-22_C_bayesian_algorithm_stim_optimizer_end_to_end.md` and `..._C_PANEL_...`
- `artifacts/research_2026-09-22_D_closed_loop_deployment_integration.md` and `..._D_PANEL_...`
- Decisions 229-231; `DECISIONS_and_open_items.md`; the session's debate boards (scratchpad, not committed).

## Correction, 2026-09-26 (decision 290)

The E2 figure in section D ("E2 AUC 0.559, 0.42-0.70") was computed on the pain ratings of the
settings period BEFORE each 3 s piece's own (the Closed-Loop joined table's off-by-one join,
2026-09-03 to 2026-09-25). With the join fixed, on the full saved tiles on 2026-09-26, L 1-3+ at
24.5 Hz under NRS reads 0.564 (0.438 to 0.678), p 0.29, 43 pain reports; its interval still spans 0.5,
so the synthesis's reading of D stands. See decision 290.
