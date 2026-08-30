# Interim decision figures — StimOptimizer / RCS08

**PROVISIONAL. Data horizon: settings to 2026-06-24, PROs to 2026-06-16. Wash-in window: 5 minutes.**
Today is later than that horizon, so roughly ten weeks of stimulation changes and pain reports are
absent from every number below. Each figure carries the horizon and the wash-in in a footer stamp,
and every quantity in this document is provisional against it. Nothing here is a final verdict —
in particular the estimated optimum, the plateau/coverage decision and the exploration queue are
all quantities that a data refresh can move.

Regenerate everything, against a new design matrix, with one call:

```python
from StimOptimizer.routines import plots
plots.render_all("<new design matrix>.csv", outdir="figs",
                 data_horizon="settings to <date>, PROs to <date>", washin_min=5.0)
```

`render_all` writes five interactive HTML figures, five PNGs at 200 dpi and
`stimopt_figure_metadata.json` (every fitted number in this document), so a refresh can be diffed
against this run without re-reading the figures. Static images are drawn by matplotlib directly;
no kaleido, no headless browser, no render bridge.

## Fitted configuration, this run

| quantity | value |
|---|---|
| epochs / reports | 45 epochs, 678 usable reports |
| objective kernel | `0.589**2 * Matern(length_scale=[0.823, 2.23], nu=1.5) + WhiteKernel(noise_level=0.225)` |
| log marginal likelihood | -64.19 |
| length-scale pinning | frequency pinned at one octave (0.823); **amplitude fitted** |
| incumbent | epoch 50, 55 Hz / 1.6 mA, posterior mu -0.0996 |
| posterior mean range | -0.100 to +0.663 NRS points |
| posterior SD range | 0.330 to 0.468 NRS points |
| safe set (beta=2) | 240 of 396 cells; contiguous only to 1.8 mA |
| exploration queue | 369 of 373 under-tested cells |

The amplitude length scale fitted to **2.23** on a unit-scaled axis. That is the single most
consequential number in this run: it says the surrogate finds the response very nearly **flat in
amplitude** across 0.8–4.0 mA, and that what structure remains lives in **frequency**. Every
figure below is a view of that same conclusion.

---

## Figure 1 — Posterior surface, delivered settings, safe-set boundary

Posterior mean of the composite objective over the 12 x 33 prospective grid, frequency on a log2
axis. The 45 historically delivered settings are overlaid with marker area
proportional to the report count and marker fill on the same diverging colour scale as the
surface, so an observed epoch can be read directly against the model's prediction for its cell.
Two epochs delivered 0.0 mA on the left, below the grid floor; they are drawn as down-pointing
triangles at 0.8 mA rather than dropped. Hatching marks the cells the safety model rejects at
beta = 2; the dashed contour is the threshold `mu_SE + 2*sigma_SE = 3.0`; the star is the
estimated optimum, argmin of the posterior mean within the safe set.

**Decision supported: where to place the next setting.** The figure's answer is largely negative,
and that is the finding. The posterior mean spans -0.100 to +0.663, and its
minimum is -0.0996 at 55 Hz / 1.7 mA — one grid step
in amplitude from the incumbent, and numerically indistinguishable from it: the
apparent advantage over the incumbent is -5.6e-05 NRS points, while the posterior SD at that cell is
0.331 — four orders of magnitude larger than the gap it is supposed to resolve, and 0.43 times the
full 0.763-point range of the mean surface.
No cell on the grid is predicted better than the setting the patient is already on. The high-frequency
half of the grid is predicted clearly *worse*, which is the one strong statement the surface makes.

The figure also exposes a defect in the safety seed that a reader must not mistake for a physiological
boundary. The safe set is **not** an amplitude ceiling: it is a set of horizontal bands, identical at
every frequency, safe from 0.8 to 1.8 mA, then rejected, then safe again
in patches up to 4.0 mA. `SafetyGP.max_safe_amplitude` therefore returns
4.00 mA — a maximum over a disconnected mask — while the largest amplitude
reachable without crossing a rejected band is 1.8 mA. The cause is that
the two-anchor seed is internally inconsistent in amplitude: programmed upper limits near 1.9–2.5 mA
enter at the severity threshold while exposures sustained at 3.3 and 4.0 mA (110 Hz) enter at severity
zero. Use the contiguous 1.8 mA figure for any programming decision, and
treat `max_safe_amplitude` as unsafe to quote until the seed is repaired or real severity reports
replace it. This also does not reproduce the 3.30 mA at beta = 2.0 recorded in the OBJECTIVE_SPEC
amendment of 2026-08-29; the discrepancy is unresolved and should be reconciled before the safety
model gates a batch.

## Figure 2 — Explore/exploit acquisition decomposition

Panels a–c are the three surfaces that make up the decision: posterior mean (what the model thinks
is good), posterior SD (what it does not know), and expected improvement against the incumbent (the
trade-off it actually maximises), with EI's argmax starred. Panel d is the per-iteration exploration
fraction — the share of the acquisition value at the *selected* cell contributed by the uncertainty
term — over a forward simulation of 3 within-visit batches of q = 4, selected
under the safety mask with the no-side-effect expansion cap. Between batches the surrogate is
conditioned on kriging-believer fantasy observations; nothing in panel d is a measurement.

**Decision supported: whether the next batch buys information or buys benefit.** Unambiguously
information. Across all 12 simulated selections the exploration fraction stays between
0.932 and 1.000, and every one is classified `explore` — not one
`exploit`. That is a direct consequence of the geometry in panels a and b: the posterior mean varies
by less than 0.76 NRS points across the entire grid while the posterior SD sits
near 0.33–0.47, so the uncertainty term dominates the mean term at every
candidate. The practical reading for a clinician is that the first three batches cannot be justified
as "trying to make her better"; they are justified as "finding out whether anything else works", and
consent and expectation-setting should say so. It also means the exploration fraction is not yet a
useful discriminator between iterations — it will only start to separate once prospective data shrinks
sigma enough for the mean surface to matter.

The frequency concentration is the actionable part: 9 of 12
selections land at **40 Hz** and 3 at 55 Hz, with amplitudes confined to
1.0–1.8 mA. 40 Hz is a grid frequency the history has never
visited, immediately adjacent to the best-performing 55 Hz. With the amplitude length scale at 2.23 the
optimizer has nothing to gain from moving amplitude and everything to gain from moving frequency, and
it behaves accordingly.

## Figure 3 — Stacked search trajectory

Three rows against iteration index, following Cole et al.'s figure 5. Row a: frequency and amplitude
sampled, with the amplitude ceiling the safety model permits. Row b: safety-model severity at each
sampled setting, with the decision quantity `mu_SE + 2*sigma_SE` and the moderate = hard-infeasible
line at 3.0. Row c: objective at each sample with the running best-so-far. The 45
observed epochs appear in chronological order; the 12 simulated selections follow after a
dash-dot break. Filled circles are observations, open diamonds are simulated — and in row c the
diamonds are *predicted* J, so the flat forward segment is the model's expectation, not a result.

**Decision supported: whether the search is moving.** Row c shows best-so-far improving in steps
through the year to -0.953 NRS points at the chronologically last epoch, then flat across
the forward simulation, which is what a kriging-believer simulation must do and carries no information
about whether real batches would improve on it. Row a shows the confound that Phase 1 flagged, in a
form that is hard to argue with: frequency and amplitude both drift monotonically over long stretches
of the record, so calendar time, frequency and amplitude are not separable in this history. The
prospective protocol's randomised within-batch delivery order exists to stop that recurring.

Row b carries a caution. The historical trace of `mu_SE + 2*sigma_SE` **crosses the infeasibility
threshold** around iterations 17–21 — settings the patient actually received and tolerated. Since the
seed encodes sustained exposures as severity 0, the crossing is an artefact of the same inconsistent
seed as in Figure 1, not evidence of harm. It is drawn rather than suppressed because a safety model
that retrospectively condemns tolerated settings is not yet fit to gate a prospective batch.

## Figure 4 — Dual-model overlay (ILLUSTRATIVE)

Composite-objective posterior beside the preference-model posterior, on shared axes, both argmaxes
marked on both panels and the gap annotated, following Louie et al.'s disagreement result.

**This panel is ILLUSTRATIVE and must not be read as a clinical finding.** No A-versus-B preference
judgements exist in this dataset. The comparisons were constructed: the 29 distinct
tested cells were pooled and cell *i* recorded as preferred to cell *j* whenever
`J_i + 0.15 < J_j`, yielding 345 ordered pairs. Five-fold held-out
accuracy is **0.841**, which is above the 71.5% internal and 65.6%
prospective figures Zhao et al. reported for spinal cord stimulation — and that comparison is not
favourable evidence, it is a warning: the comparisons are a deterministic function of the same J the
objective GP is fitted to, so the accuracy is optimistically biased by construction and measures
self-consistency, not preference prediction.

**Decision supported: whether an objective-driven optimum would be the setting the patient actually
prefers — and, at this horizon, what infrastructure is needed to answer that.** The two optima differ
by 15 Hz (55 Hz objective vs
40 Hz preference) and by 0.00 mA in amplitude.
The direction — preference sitting at a lower frequency than the objective argmin — is the same
direction Louie et al. found, but with derived comparisons that agreement is a property of the
construction, not a replication. The real conclusion is the gap in the data: a forced-choice A-vs-B
item is the missing instrument, and until it is collected the preference track cannot contribute to a
setting decision.

## Figure 5 — Coverage / plateau audit

Posterior SD across the grid, with the never-sampled 10–55 Hz / >1.8 mA region outlined, the top of
the exploration queue circled and labelled with its optimistic bound `mu - 2*sigma`, and
the incumbent posterior-mean level drawn as a reference contour.

**Decision supported: whether the apparent plateau is local or global. It is local.**
369 of the 373 cells with fewer than three reports have an optimistic
bound that still beats the incumbent, the best of them at -0.845
against the incumbent's -0.0996. Under the pre-registered stopping rule the coverage
condition is therefore violated and **the run may not be described as converged**, regardless of how
flat the mean surface looks. 11 of the top 12 queue cells are
at 40 Hz.

Two honest notes on this panel. The reference contour is nearly degenerate: only
2 of 396 cells sit at or below the incumbent
level, so the "incumbent contour" encloses those cells and nothing more — which is itself the plateau
result stated geometrically. And the coverage-condition margin is driven by sigma, not by any predicted
benefit: with sigma near 0.33–0.47 across an unexplored grid, almost any cell's
optimistic bound will beat an incumbent whose mean is -0.100. The queue is a
statement about how little this warm start knows, not a list of 369 promising settings.
Ranking it by expected improvement rather than by the raw bound is what makes the ordering meaningful;
membership is identical either way.

The coverage geometry revision matters here and supersedes the earlier Phase 1 phrasing. It is **not**
true that at 10–55 Hz amplitude never left 1.4–1.8 mA: 55 Hz reaches 3.0 mA (n=4) and 4.0 mA (n=3) at
the n>=3 threshold. The correct statement, which the figure annotates: 10 Hz still spans only
1.5–1.8 mA, and of the 110 prospective-grid cells in the 10–55 Hz / >1.8 mA band,
**108 still carry fewer than three reports** — the only exceptions being 55 Hz at
3.0 and 4.0 mA.

---

## What a data refresh could change

Ten weeks of settings and PROs are missing. Specifically at risk: the incumbent identity and its mean
(a chronic setting may have been changed); the fitted amplitude length scale of 2.23 and therefore the
"flat in amplitude, signal in frequency" conclusion; the estimated optimum; the size and composition of
the exploration queue; and the confound correlations, which strengthened rather than weakened between
the v1 and v2 design matrices and could strengthen again. The safety-seed defects described under
Figures 1 and 3 are structural and will **not** be fixed by more data — they need either a repaired
seed or a real ordinal side-effect item.
