# Stimulation amplitude and LFP band power: what the literature and RCS08's own record say about the shape, and what should feed the evidence triangle

**Written 2026-09-11** for decision 6 of the Closed-Loop page redesign plan
(`.planning/2026-09-11-closed-loop-page-redesign/`). The PI's question, in his words: the
relationship between stimulation amplitude and band power is "inverted-U-shaped (sometimes
M-shaped) ... focus on identifying the peak of the inverted-U; gather more evidence."

**Four research workers ran in parallel**, one topic each; their full reports, with every citation
and a confidence note per claim, are the four files beside this one:

| Worker | File | Sources |
|---|---|---|
| A — what shape human DBS amplitude sweeps actually show | `research_2026-09-11_amp_power_A_empirical_shape.md` | 18 |
| B — how a peak is fitted and given an interval | `research_2026-09-11_amp_power_B_fitting_methods.md` | 32 |
| C — how much of a rise-then-fall can be artifact | `research_2026-09-11_amp_power_C_artifact_vs_physiology.md` | ~12 primary |
| D — chronic-pain targets specifically | `research_2026-09-11_amp_power_D_pain_targets.md` | 18 |

**Plus the measurement on our own record** (RCS08, every run of rising current the device logged,
findings §5–§6 of the plan). Every number below that is about RCS08 comes from that measurement, run
today; every number about the literature is traced to a worker file and its source.

---

## 1. The short answer

1. **The inverted-U is not the established shape in the human literature.** Where amplitude has been
   stepped and band power measured in people (almost all Parkinson's, STN), power **falls** with
   amplitude and the fall **flattens** — steepest below about 1.5 mA, little further change above
   about 2 mA (Feldmann 2022, n = 10, 0.5 mA steps; Hammer 2026, 11 hemispheres: −21.5 dB at
   1.85 mA against −21.0 dB at 2.84 mA). A **rebound** — power falling then rising again as
   amplitude approaches the side-effect level — is reported once, in GPi, n = 1, 0–5 mA
   (Cagle 2021). Two n = 1 STN reports show one beta peak shrinking while a neighbouring peak
   shifts or resists; **no paper reports a single band's power rising, falling and rising again
   (an M) as a function of amplitude**. Hysteresis between ramp-up and ramp-down: no human study
   found. (Worker A.)
2. **For chronic pain targets the question is unanswered in print.** No published amplitude sweep
   with LFP band power exists for ACC, OFC, VPL/VPM or PAG/PVG. Shirvalkar 2023 is recording-only.
   The one quantitative inverted-U in pain neuromodulation is rat dorsal-horn spinal-cord
   stimulation (peak inhibition at 40–85 % of threshold, over-recruitment above); the human
   ECAP-controlled SCS dataset (n = 690) is monotonic-then-plateau with no downturn. The 2025 UCSF
   closed-loop preprint, the likeliest source of pain-target amplitude data, was not accessible
   (401/403 on every attempt). (Worker D.)
3. **A rise-then-fall can be manufactured by the recording chain.** Stimulation sub-harmonics that
   switch on above ~2.5 mA (Thenaisie 2021), amplifier slew overflow at 4.5–5.3 mA on the RC+S
   (Alarie 2022), and blanking-related data loss together produce measured power that rises and
   then caps or falls with no change in the brain. Percept exposes no blanking control, so this
   cannot be tuned away. Hammer 2022's ≤ 3.5 % residual after template subtraction is the only
   published benchmark for "how clean is clean". A ten-item control list is in worker C's report
   (off-stimulation baseline, harmonic-free band, kink at a threshold current, ramp buffer, raw
   clipping check, symmetric up/down, impedance, bipolar cross-check, bandwidth, residual
   quantified).
4. **Fitting a peak is standard statistics, and it needs data we do not have.** A quadratic in
   amplitude with one intercept per visit, its vertex = −b/(2c), and a Fieller interval on the
   vertex (or a bootstrap) is the simplest defensible estimator; `segmented` (Muggeo) for a knee;
   `drc`'s Brain–Cousens / Cedergreen models for a rise-then-sigmoid-fall; a curvature test
   (likelihood-ratio or F, straight line against quadratic) before trusting any peak. Design
   guidance: at least 3, typically 5, distinct amplitude levels, replicated; two peaks need
   roughly double the points of one. (Worker B.)
5. **On RCS08 no band inside 8–30 Hz shows an established bend.** Time-domain route, one intercept
   per run, 194 contact-band pairs with ≥ 8 points: the quadratic beats the line at p < 0.05 in
   **1** (72.5 Hz, outside the sensing range; fitted peak 3.4 mA, bootstrap interval 2.85–25.9 mA).
   The project's own stored pooled model (decision 55/103): **9 of 194** rows with p < 0.05 — 4.6 %,
   the chance rate — and none would survive a correction for 194 tests. Per run, the largest power
   sat at an interior current in 38 % of 388 series, which is the chance rate for 3–6 currents. The
   record holds 12–13 points per contact across 3–4 visits, at most 6 currents per run, and the
   right side mixes **three stimulation rates** (55, 110, 145 Hz). (Findings §6.)

**Recommendation for the evidence triangle's current→power edge: do not feed it a peak.** Feed it the
pooled straight-line slope per sensing contact that the stored table already carries
(`pooled_slope_per_mA`, its standard error and p), which is the quantity the new pooled tab will
draw, and show the curvature answer as a caveat on the edge: "bend detected / no bend detected /
not assessable", with the fitted peak and its interval as an annotation only when the bend is
established. A peak is not established anywhere on this record today, and decision 55 already
says where a switching value may sit when one is: on the one-sided stretch past the peak.

**What would let a peak be estimated** (worker B's design guidance + worker C's controls, applied
to this device): one titration session per side per sensing contact, at **one** stimulation rate,
from 0 mA to the side-effect level in 0.5 mA steps, ≥ 60 s per step (the settled window is 30 s),
**up and then down**, streaming throughout so the voltage trace exists, with an off-stimulation
baseline before and after, impedance read before and after, and the analysis band chosen away from
`|250 − rate|` and the rate's 1/2, 1/4, 3/4 sub-harmonics. That gives ≥ 8 settled points per visit
on its own (decision 55's floor), and a second visit makes the pooled quadratic with per-visit
intercepts answerable.

---

## 2. What the human amplitude sweeps show (worker A)

| Shape | Evidence | Where | n | Confidence |
|---|---|---|---|---|
| Monotonic fall, diminishing returns | Feldmann 2022: STN low-beta 4.31 % → 4.09 (0.5 mA) → 2.27 (1.0) → 1.53 (1.5) → 1.17 (2.0) → 1.12 % (2.5 mA); log fit R² 0.71 | STN, offline analysis of Percept stream | 10 | HIGH |
| Plateau | Hammer 2026: −21.5 ± 4.6 dB at 1.85 mA vs −21.0 ± 4.6 dB at 2.84 mA | STN | 6 (11 hemispheres) | MEDIUM-HIGH |
| Rebound near side-effect level | Cagle 2021: beta and low-gamma fall to ~3 mA then rise by 3–4 mA; 0–5 mA, 0.5 mA steps, ≥ 20 s dwell | GPi, Percept on-device and offline | 1 | MEDIUM |
| Two peaks behaving differently | Koeglsperger 2020 (15 Hz peak replaced by a 13 Hz peak between 0.8 and 1.2 mA); Giannini 2023 (high-beta suppressed, low-beta not) | STN | 1 each | MEDIUM |
| A single band rising, falling, rising (M) | none found | — | — | LOW that it exists |
| Hysteresis up vs down | none found | — | — | NOT ESTABLISHED |

Worker A's contradictions: Feldmann calls the relationship "linear, no plateau" while its own steps
shrink from −1.82 to −0.05 percentage points per 0.5 mA; STN protocols stop at 2.5–3 mA, so
whether STN would rebound like GPi at higher amplitude is untested.

## 3. Pain targets (worker D)

- ACC after-discharges appear at a **threshold** (4–5 V, 1 V steps, Huang 2019, n = 3), not on a
  graded curve; an 8 s ramp removed them at 6 V. That is the only amplitude-stepped LFP result in a
  pain-DBS cortical target.
- PVG / thalamus: band power correlates with relief across patients (theta inversely; thalamic
  high-beta and PVG alpha positively; Huang 2016, n = 10; low-beta state occurrence, Huang 2017,
  n = 13) — during ordinary programming, no sweep.
- The "therapeutic window" in PAG/PVG programming (1 → 5 V, side effects above) is two thresholds,
  never a measured relief-vs-amplitude curve.
- Titration protocols in print: 1 V steps with seconds between (ACC); 0.5 mA/V steps in the
  Parkinson's monopolar-review convention; UCSF's own wash-in / wash-out timing rather than fixed
  steps (Provenza & Shirvalkar 2021).

## 4. Artifact and saturation (worker C)

- Aliased artifact lands at |250 − rate| Hz on Percept; sub-harmonics at 1/2, 1/4, 3/4 of the rate
  appeared only above ~2.5 mA in one patient (Thenaisie 2021) — an amplitude-**gated** onset that
  looks like a kink in a power-vs-amplitude curve.
- Slew overflow (the artifact's rate of change exceeding the converter) at 4.5–5.3 mA on the
  RC+S widened the artifact from 147–153 Hz to 140–180 Hz; default blanking still overflowed
  60–80 % of packets (Alarie 2022). Percept offers no blanking control.
- Evoked resonant activity grows with amplitude but lives at 200–500 Hz, above Percept's ~100 Hz
  low-pass; direct contamination of 8–30 Hz band power is **unverified**, not established.
- This project already applies several of the controls: the settled window drops the first part of
  each step; bands carrying a folded multiple of the rate are marked (`striped`); the device route
  has a per-channel saturation ceiling (decision 52). Not applied today: an off-stimulation
  baseline in the same session, a ramp-down, impedance before and after, and residual-artifact
  quantification.

## 5. Fitting a peak (worker B)

| Method | Peak estimate and its interval | Minimum data | Software |
|---|---|---|---|
| Quadratic, one intercept per visit | vertex −b/(2c); Fieller interval (exact under normality) or bootstrap; delta method is optimistic when c is imprecise | ≥ 3 distinct levels, 5 typical, replicated | any OLS / `lme4` |
| Segmented (broken-stick) | breakpoint with score-based CI; Davies' test for "is there a break" | points on both sides of the break | `segmented` (Muggeo 2003/2017; random breakpoints 2014) |
| Hormesis dose-response (Brain–Cousens, Cedergreen–Ritz–Streibig) | maximal-response dose with delta-method SE | a floor and a ceiling visible | `drc` |
| Gaussian process / loess / unimodal regression | peak of the posterior mean; band from the GP | ~10+ points across the range | `sklearn`, `GPy` |
| Bayesian optimisation (Grado 2018, Sarikhani 2019/2022, SAFE-OPT 2024) | finds an optimum sequentially — a data-collection strategy, not a fit to a fixed sweep | — | — |
| Two peaks | spline / two-breakpoint segmented with AIC selection; SiZer; Dr Fit | about double a single peak's | `mgcv`, `segmented` |

Curvature first: compare straight line against quadratic (likelihood-ratio or F) and trust a peak
only when the curved model wins. For several visits, a random intercept per visit does not move the
vertex (a vertical shift leaves the x-location alone), so the population peak comes from the
fixed effects with its interval from their covariance — which is what decision 55's pooled model
already does, run label as the group.

## 6. RCS08 (findings §5–§6, measured today)

- 11 runs of rising current on one side, all 11 built in 3.7 s with the tile cache warm.
- Right side: all on R 0⁻3⁺, 6 runs, 4 visits, 12 settled points, **three stimulation rates**. Left
  side: L 1⁻3⁺ 4 runs, 3 visits, 13 points; L 0⁻2⁺ 1 run, 5 points.
- The device's own FFT route: 0 settled points in every run. The direct-LSB route: 4 runs with
  ≥ 3 points, each at that run's own programmed centre (7.8–23.4 Hz), so it cannot be pooled across
  visits at one band. The time-domain route carries all 22 centres per run and is the only route
  that pools.
- Curvature: 1 of 194 pairs by the F test (72.5 Hz, peak interval 2.85–25.9 mA); 9 of 194 by the
  stored pooled model (4.6 %). Interior maxima per run: 38 % (chance for 3–6 currents: 33–67 %).
- The programmed centre differs run to run, so "the same band" across visits exists only on the
  time-domain route.

## 7. Cross-cutting themes and contradictions

- **Suppression, not a hump, is the default physiology where it has been measured** (STN beta).
  The PI's inverted-U describes something the accessible literature has recorded once (GPi, n = 1)
  and RCS08 has not recorded at all. That is not evidence against it in pain targets — nobody has
  swept amplitude there with LFP on — but it means a peak-finding method is being asked to find
  something unmeasured.
- **Artifact can counterfeit the hump.** Worker C's mechanisms line up with worker A's one rebound
  (near the side-effect level, where sub-harmonics switch on and saturation begins), and Cagle 2021
  did not run the controls that would separate them.
- **Rat dorsal horn (inverted-U) vs human ECAP-SCS (plateau)** disagree; unresolved, and neither is
  brain DBS.
- **Two workers' gaps coincide**: no DBS-LFP paper applies a named peak-fitting method to an
  amplitude sweep (B), and no pain-target sweep exists (D). The 2025 UCSF preprint may close both
  and needs institutional access.

## 8. Confidence summary

HIGH: STN beta falls with amplitude with diminishing returns; Fieller/quadratic and `segmented`
are the standard peak/knee estimators; Percept's 250 Hz / |250 − rate| aliasing; the RCS08 counts
above (measured). MEDIUM: GPi rebound (n = 1); Percept-specific artifact gating thresholds; the
PVG/thalamus band–relief directions. LOW / NOT ESTABLISHED: any M-shaped single-band curve;
hysteresis; ERNA reaching the 8–30 Hz readout; the un-sourced 0.67/1/2.25/3.375 mA dataset worker
A flagged; everything about the 2025 preprint.

## 9. Gaps and follow-up

1. Access the 2025 UCSF/Provenza closed-loop preprint and Hubers 2026 (Brain Stimulation) with
   institutional credentials.
2. Run the titration protocol in §1 on RCS08 before any peak is estimated.
3. Add the missing controls to the three-source build: off-stimulation baseline segments, a
   ramp-down, impedance stamps, and a residual-artifact figure.
4. Keep the evidence triangle on the pooled slope with the curvature caveat until 2 has happened.

Full source indices are in the four worker files; nothing in this synthesis rests on a source not
listed there, and the two claims worker A could not trace to a peer-reviewed paper are marked LOW
above rather than repeated as findings.
