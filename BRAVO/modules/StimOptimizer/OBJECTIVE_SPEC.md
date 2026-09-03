# Pre-registered objective and stopping rule — StimOptimizer

Written **before** any surrogate was fitted to the RCS08 history, so that the objective, the
side-effect penalty calibration, and the stopping thresholds cannot be chosen to flatter a result.
Phase 1 inventory (`PHASE1_inventory_RCS08.md`) is the only input consulted: it supplies the grid,
the effective sample size, and the confound structure, not any fitted response surface.

Anything changed after this file is committed must be recorded as a dated amendment at the bottom,
with the reason. Silent edits defeat the purpose.

---

## 1. Search space

Launch space is two-dimensional:

| dimension | levels | notes |
|---|---|---|
| frequency | 10, 20, 30, 40, 55, 70, 85, 110, 125, 130, 145, 165 Hz | group-level, shared by both hemispheres (device constraint) |
| left-hemisphere amplitude | 0.8 – 2.6 mA in 0.1 mA steps | per-hemisphere; step matches the programmer's resolution |

Frequency is modelled on a **log2 scale**. DBS frequency effects are conventionally multiplicative,
and a single ARD length scale cannot serve 10 Hz and 165 Hz on a linear axis.

Held fixed for the prospective phase, and recorded with every observation:

- **pulse width pinned at 60 us.** It co-varied over 60-180 us historically (Phase 1), which is a
  third uncontrolled dimension. Pinning it is a protocol change, not a modelling choice.
- **right-hemisphere amplitude** fixed, or yoked to left by a declared constant ratio. The historical
  ratio at the incumbent is 1.2/1.6 = 0.75.
- **cathode configuration** enters as a categorical block, not a searched dimension: left ring 1
  (`1a-1b-1c`) or left ring 2 (`2a-2b-2c`), right both-rings. Contact becomes a searched third
  dimension only once the 2D surface has prospective coverage in the 10-55 Hz / >1.8 mA region that
  the history never sampled. Phase 1: frequency and amplitude are not globally correlated
  (Spearman rho = +0.08, p = 0.66), but amplitude was swept 0.0-4.0 mA only at 110 Hz and above,
  while at 10-55 Hz it never left 1.4-1.8 mA in any well-sampled epoch.

Grid size is 12 x 19 = 228 cells. The acquisition function is evaluated exhaustively at every cell;
no gradient optimization is used or needed, following Sarikhani et al. 2022.

## 2. Objective

Minimised. Lower is better.

```
J(x) = J_pain(x) + J_SE(x) + w_E * J_energy(x)
```

### 2.1 J_pain — primary

```
J_pain(x) = mean(NRS | x) - mean(NRS | incumbent)
```

NRS is 0-10 and 100% complete across the 597 usable reports. The reference is the **incumbent chronic
setting**, epoch 50 (55 Hz, 1.6 mA left / 1.2 mA right, 60 us), which carries 155 reports over 2035 h
at mean NRS 7.28 (SD 1.24). Referencing the incumbent rather than a grand mean or a stim-off baseline
makes J directly answer the clinical question — is this setting better than what she is on now — and
keeps the units interpretable as NRS points. `J_pain < 0` means improvement.

No stim-off baseline is used: the two historical epochs with 0.0 mA left still delivered 3.1 mA right,
so a true bilateral-off reference does not exist in this dataset.

### 2.2 J_pain — pre-specified sensitivity composite

```
J_comp(x) = mean over items of z(item),  items = {NRS, VAS, MPQ-sum, -relief}
```

z-scored over all usable reports; `relief` enters with a negative sign because higher relief is better.
Item completeness (Phase 1): NRS 100%, VAS 100%, relief 100%, MPQ-sum 99.5%. `left_leg_vas` and
`back_vas` (74%) and `tingly` (28%) are **excluded** — differential missingness across epochs would
make the composite a function of which items were answered.

The composite is reported **alongside** the primary, never in place of it. If the two disagree about
the ranking of the top three cells, that disagreement is surfaced in the report and the primary
decides.

### 2.3 J_SE — side-effect penalty

Ordinal ladder, following Sarikhani et al. 2022 but recalibrated to NRS units:

| patient-reported severity | penalty (NRS points) |
|---|---|
| none | 0 |
| mild | 1.0 |
| moderate | hard infeasible (+inf) |
| severe | hard infeasible (+inf) |

**Calibration statement:** one mild side effect exactly cancels 1.0 point of NRS improvement — a
finite, negotiable trade-off. A moderate or severe side effect makes the cell **infeasible**: it may
never be selected, however large its apparent pain benefit. The trade-off lives in the objective
rather than in the optimizer's judgement.

Sarikhani et al. expressed the same intent with a finite penalty of 4 (severe = 5), which works
because their tremor term was bounded to [-4, 4] and so no efficacy gain could outweigh it. `J_pain`
here is referenced to an incumbent at NRS 7.28 and is therefore bounded below by -7.28: a finite
penalty of 4.0 would be beaten by any cell showing more than 4 NRS points of improvement
(7.3 -> 3.3, clinically conceivable). Transplanting the finite penalty would have quietly permitted
selection of a moderate-side-effect setting, so the rejection is implemented as `+inf` with an
explicit `feasible` flag instead.

Infeasible cells are **not** discarded. They are excluded from the objective surrogate's argmin — an
intolerable setting carries no useful information about where the pain optimum is — while still
informing the safety GP. That is how a constrained Bayesian optimizer is supposed to treat an
infeasible observation.

**Phase 1 finding that constrains this:** there is no structured side-effect severity field in the
current PRO battery. `tingly` (28% complete) and `electrocuting` (93%) are McGill pain-quality
descriptors, not adverse-event reports, and are **not** used as a severity proxy. Therefore:

- historical cells enter with `J_SE = 0` and an explicit `se_observed = False` flag;
- the ladder is collected prospectively from the first batch onward;
- the safety GP is seeded from the programmed `UpperLimitInMilliAmps` recorded in each session JSON,
  which is a clinician-set tolerability bound and the only safety information the history contains;
- epoch duration is available as a weak tolerability surrogate (a setting sustained for weeks was
  tolerated) but is **off by default**, because epoch length is confounded with clinic scheduling.

### 2.4 J_energy — energy penalty

```
J_energy(x) = amplitude^2 * pulse_width * frequency        (TEED, up to the impedance constant)
```

Normalised by TEED at the most expensive cell of the declared grid — 165 Hz, 5.0 mA, and the pinned
60 us pulse width, TEED 247500 (`objective.ENERGY_REF`). The divisor is a fixed constant, not the
maximum of whatever epoch table is passed in, so `w_E` means the same thing across runs. In-grid
values therefore lie in [0, 1]; a setting outside the declared grid scores above 1 and is left
unclipped deliberately, because that is worth seeing rather than hiding. Default weight `w_E = 0`. Enabled only on explicit request, as in
the central post-stroke pain case report, which penalised high-energy settings during preference
search. Battery life is a real constraint but it is not a pain outcome and must not silently move the
optimum.

## 3. Warm start from the historical record

All 35 historical epochs are used. None is discarded. Each enters as **one** observation — not one per
PRO — at its (frequency, amplitude) cell, with an observation variance:

```
sigma^2_obs = s^2/n  +  tau^2_dur  +  tau^2_age
```

- `s^2/n` — squared standard error of NRS within the epoch. For `n = 1` epochs, `s^2` is imputed as the
  pooled within-epoch variance across epochs with `n >= 3`.
- `tau^2_dur` — inflation for short exposures, `c_dur * max(0, 1 - dur_h/168)^2`. An epoch shorter than
  a week has not reached steady state.
- `tau^2_age` — inflation with observation age, `c_age * (age_days/365)^2`. This is the interim stand-in
  for nonstationarity; the time-varying kernel is deferred (see README).

This is what "use all the data" means operationally: nothing is thrown away, and nothing is
overtrusted. The dominant epoch contributes an observation with a very small variance; a single-report
epoch contributes one with a large variance. Both are in the fit.

Kernel hyperparameters (ARD length scales, signal variance) are fitted by marginal-likelihood
maximization on the full historical set. That is the legitimate transfer from history — it teaches the
model how smooth the response surface is — as distinct from letting history dictate where the optimum
is.

## 4. Stopping rule — both conditions required

The optimizer stops only when **both** hold, and the report states which condition was binding:

**(a) Plateau.** No improvement in the posterior best `J` of at least `delta` for `k` consecutive
batches.

- `delta = 1.0` NRS points, default. This is a **per-batch increment** threshold and is deliberately
  set below the trial-level minimal clinically important difference for chronic pain NRS, which is
  commonly cited as roughly 2 points or 30%: an optimizer that only recognises full-MCID steps will
  stop while real gradient remains.
- `k = 3`.

**(b) Coverage.** The maximum optimistic bound over never-tested cells no longer beats the incumbent:

```
min over x in UNEXPLORED of [ mu(x) - kappa*sigma(x) ]  >=  mu(x_incumbent)
```

with `kappa = 2.0` fixed in advance, `UNEXPLORED = {x : n_reports(x) < 3}`, and the sign convention
minimising `J`, so `mu - kappa*sigma` is the optimistic (best-case) bound. While any unexplored cell's
optimistic bound is better than the incumbent, **the plateau is not established as global** and the run
continues.

The cells that violate condition (b) form the **exploration queue**, ordered by optimistic bound. That
queue is the answer to "is this a local plateau" — a specific list of settings that must be tested
before the question can be closed.

**(c) Hard ceiling.** 8 batches, independent of (a) and (b). If the ceiling is reached with (b) still
violated, the run is reported as **truncated, not converged**, and the outstanding exploration queue is
carried forward. A truncated run may not be described as having found the optimum.

## 5. Safety constraint

Safe set:

```
S(beta) = { x : mu_SE(x) + beta*sigma_SE(x) < 3.0 }        (severity threshold = moderate)
```

`beta` is the single exposed conservatism knob. Cole et al. 2024 swept 30 configuration combinations
and found beta the only parameter that significantly predicted unsafe overshoot, while the exploration
weight and the hyperprior weight did not. **Default beta = 2.0.** Tune beta; leave the rest alone.

Per-batch safe-set expansion is additionally capped by the worst severity reported so far, following
Sarikhani et al. 2022:

| worst severity so far | max amplitude step this batch |
|---|---|
| none | +0.4 mA |
| mild | +0.2 mA |
| moderate or severe | 0.0 mA (expansion halted) |

The cap is applied as `min(safe-set boundary, previous boundary + cap)`. Two independent brakes, because
the confidence-bound safe-set formulation with an unbounded Lipschitz constant is known to expand
aggressively.

## 6. What the optimizer is not permitted to do

- **Select settings before the surrogate passes held-out calibration.** Leave-one-epoch-out and
  leave-one-era-out prediction of held-out epoch means must reach the pass criterion declared in Phase 4
  before any batch is emitted. A surrogate that cannot predict a held-out era does not get to choose.
- **Attribute the historical time trend to a parameter.** Phase 1 found NRS improving over the year
  (rho = -0.49, p = 0.003) collinear with falling frequency (rho = -0.45) and falling right amplitude
  (rho = -0.89). Era-blocked estimation is mandatory, and prospective batches must be delivered in
  randomised order within a batch so that time and parameter are not re-confounded going forward.
- **Report a preference optimum and a composite optimum as one number.** They are fitted independently
  and reported side by side.

---

## Amendments

### 2026-08-29 — amplitude grid widened to 0.8-4.0 mA

Section 1 originally capped the search at 2.6 mA. Phase 1 shows the patient sustained 3.3 mA for
528 h and 4.0 mA for 646 h at 110 Hz, both tolerated. A hard grid ceiling at 2.6 mA would discard
that region by fiat and would also throw away the only tolerability evidence the history contains.
The ceiling is now set by the **safety GP** rather than by the grid: amplitude runs 0.8-4.0 mA in
0.1 mA steps (33 levels, grid 12 x 33 = 396 cells) and the safe set decides what is reachable.
Reason: the safety model is the right place for a safety bound; an arbitrary grid limit is not.

### 2026-08-29 — frequency length scale pinned, not fitted

Marginal-likelihood maximization on the 35-epoch warm start drives the **frequency** ARD length
scale to zero: log marginal likelihood is -48.14 at a lower bound of 0.02 and -48.21 at 0.15 on the
standardised log2 axis, i.e. the likelihood surface is flat and the MLE degenerates. The consequence
is that the surrogate treats each frequency as an independent block and cannot borrow any strength
between, say, 55 Hz and 70 Hz.

This is a property of the historical *design*, not of the physiology: frequency levels are separated
in time (Phase 1: days vs frequency rho = -0.45, p = 0.007), so between-frequency contrasts absorb
the temporal trend and look like uncorrelated noise.

Resolution: the frequency length scale is **pinned at one octave** (0.823 standardised units), stated
as a scientific assumption, and only the amplitude length scale, signal variance and nugget are
fitted. Cost of pinning is 0.48 log-likelihood units (-48.62 pinned versus -48.14 free), which
confirms the data are indifferent. When the data cannot determine a hyperparameter, a stated
assumption is more honest than a degenerate maximum-likelihood estimate.

Consequence for the protocol: **frequency must be sampled directly by the prospective batches.** The
warm start cannot interpolate it, so every batch should include at least one frequency the recent
record has not visited.

### 2026-08-29 — wash-in exclusion cut from 24 h to 5 minutes

PI report: RCS08 is a rapid responder with a wash-in demonstrated repeatedly in clinic at under five
minutes. The 24 h exclusion window was therefore discarding valid observations, not transients.

Effect on the warm start: all 678 reports become usable (was 597), **45 epochs carry data (was 35)
and 33 have n >= 3 (was 23)**. The incumbent becomes n = 159 at mean NRS 7.24 (SD 1.28). The best
epoch with n >= 5 becomes epoch 57 — 55 Hz, 1.8 mA left, 60 us, n = 7, NRS 6.29 (SD 0.76),
relief 50.4 — a clearer separation from the incumbent than the 24 h matrix showed.

Two consequences that are not improvements:

- **The time confound got stronger.** Days versus NRS rho = -0.61 (p < 0.0001), up from -0.49, still
  collinear with days versus frequency -0.48 and days versus right amplitude -0.92. More data has
  sharpened the temporal trend, not diluted it.
- **The coverage-geometry claim is revised.** 55 Hz now reaches 3.0 mA (n = 4) and 4.0 mA (n = 3) at
  the n >= 3 threshold, so it is no longer true that amplitude never left 1.4-1.8 mA at 10-55 Hz.
  Corrected statement: 10 Hz still spans only 1.5-1.8 mA, and of the 110 prospective-grid cells in
  the 10-55 Hz / >1.8 mA band, 108 still carry fewer than three reports.

Wash-in is now a **declared parameter stamped on every output**, not an implicit default. The
sensitivity table (5 min / 0 / 12 / 24 / 48 / 72 h) is retained so the cost of any other choice is
visible.

### 2026-08-29 — two-stage design: acute for search, daily NRS to confirm (PI decision)

A sub-five-minute wash-in means an **acute** readout responds within a clinic visit, but the daily NRS
still integrates over hours. These are different quantities and the module now treats them as such.

**Stage 1, in-clinic search.** A sequential (not batched) optimizer against an acute in-session pain
rating collected roughly 5-10 minutes after each setting change. Because each evaluation costs minutes
rather than days, 10-20 settings per session are feasible — the Sarikhani et al. regime, where they
converged in 15.1 +/- 0.7 settings in phase I and 17.7 +/- 4.9 in phase II. Stage 1 does not decide
anything; it narrows the space.

**Stage 2, between-visit confirmation.** The top 2-3 Stage 1 candidates plus the incumbent are
programmed as selectable home groups and scored on the **daily NRS** over the following interval, using
the existing between-visit batch machinery with its minimum-separation constraint. The Stage 2 result
is what decides.

**Instrument status.** The acute in-session rating does **not** exist in the current battery and must be
added; it is a different instrument from `nrs` (`date_time_s1_daily`), which is a once-or-twice-daily
chronic report. Until it exists, Stage 1 cannot run and only Stage 2 is executable. Both instruments
require their own validation; neither may be substituted for the other.

**Pre-specified disagreement rule.** Acute and chronic rankings will sometimes disagree — Louie et al.
found exactly this between an objective measure and patient preference. Fixed in advance:

1. **Stage 2 governs.** The chronic daily NRS is the therapeutic target. An acute optimum that fails to
   beat the incumbent on daily NRS is not adopted, regardless of its Stage 1 margin.
2. **Disagreement is recorded, not resolved by fiat.** Every Stage 1 -> Stage 2 transition logs the
   acute ranking, the chronic ranking, and Kendall's tau between them. Accumulated across visits this
   is the estimate of how well the acute proxy predicts the chronic outcome — the quantity that decides
   whether Stage 1 is worth running at all.
3. **The proxy must earn its place.** If, after a pre-declared minimum of 4 visits, the acute ranking
   does not predict the chronic top-2 better than chance, Stage 1 is dropped and the design reverts to
   between-visit batches only. This is the same standard Zhao et al. applied to their preference models,
   which they validated prospectively at 65.6% accuracy rather than assuming.
4. **Safety is not staged.** The safety GP and the safe set apply identically in both stages, and any
   moderate or severe side effect reported in Stage 1 makes the cell infeasible for Stage 2.

Both stages inherit the 5-minute wash-in for exposure attribution; only the outcome instrument and the
evaluation interval differ.

### 2026-08-29 — length-scale pinning is per dimension; amplitude is fitted

The earlier amendment said "only the amplitude length scale, signal variance and nugget are fitted",
but the implementation pinned every dimension whenever `fixed_length_scale` was supplied, so the
canonical configuration `[0.823, 0.72]` pinned amplitude too. That also falsified `loo_predict`'s
contract, since folds inherited the full-data amplitude hyperparameter instead of re-estimating it —
a leak that would inflate any calibration result.

`_make_kernel` now pins **per dimension**: `None` in a slot leaves that dimension free. The canonical
configuration is **`fixed_length_scale=[0.823, None]`** — frequency pinned at one octave for the
identifiability reason above, amplitude fitted by marginal likelihood.

Refit on the 45-epoch matrix with amplitude free:
`0.589^2 * Matern(length_scale=[0.823, 2.23], nu=1.5) + WhiteKernel(noise_level=0.225)`, lml -64.19.

**The fitted amplitude length scale of 2.23 on a unit-scaled axis says the response is nearly flat in
amplitude across 0.8-4.0 mA, and that frequency carries the remaining signal.** The
highest-expected-improvement cells are consequently all at 40 Hz, the untested frequency adjacent to
the best-performing 55 Hz. This inverts the reading of the 24 h matrix and should be treated as the
leading structural hypothesis, to be confirmed once the missing ten weeks of data arrive.

### 2026-09-02 — the randomisation prerequisite is DISCHARGED, and it mattered

This module has said since its first draft that randomising the order of settings within a visit is
the prerequisite for interpreting any in-clinic contrast, because a monotone ramp makes "later
setting" and "better setting" the same variable. On 2026-09-02 that randomised design was run for
the first time. The result settles the question in favour of the concern.

The schedule was executed exactly as issued: seven settings in three randomised complete blocks,
twenty-one steps, with the setting in force repeated once per block as an anchor and the optional
165 Hz probe run last. Mapping every step back to the plan gives twenty-two steps and zero
unmatched.

**The within-visit drift is large, monotone and highly significant.** On the Overall rating,
Spearman correlation with elapsed time is -0.873 (p = 2.4e-07). Fitted as a linear term alongside
setting, the slope is -0.051 rating points per minute (p < 0.0001), which is **-3.79 points across
the 74-minute session** on a 0-10 scale. The anchor setting traces it on its own: identical
parameters scored 5, then 4, then 3 across the three blocks.

**Once that drift is removed, no setting differs from the anchor.** The joint F-test across all
seven setting contrasts gives F = 0.520, p = 0.804, and every individual confidence interval spans
zero. The raw between-setting spread is 2.00 points; the drift-adjusted spread is 0.73.

**What the design bought, as a counterfactual.** Under the monotone ordering used in previous
sessions, the setting that happened to run last would have appeared roughly 3.8 points better than
the one that ran first for no reason other than when it was run. That is five times the entire
drift-adjusted spread between settings. Any apparent winner from a monotonically ordered session
should be treated as uninterpretable rather than merely noisy.

**THE SESSION'S LIMITATION, AND IT IS SEVERE.** The primary outcome was almost never recorded. Left
leg has two values across twenty-two steps, both 2.0, so no setting contrast is estimable on it at
all; left foot has two, back three, right leg two, right foot two, head none. Only the Overall
rating was scored, on twenty-one of twenty-two steps. The 2026-08-30 amendment above established
that the Overall rating does NOT detect the stimulation on-versus-off effect that site-specific
scores do (+0.27, p = 0.25 for Overall against +1.31, p = 0.016 for the left leg). **So the null
result above is a null on the wrong outcome and is not evidence that the settings do not differ.**
The single highest-value change for the next session is recording the per-site scores, above all
the left leg, at every step rather than occasionally.

**A structured side-effect severity field now exists in the sheet**, which the module has wanted
since Phase 1, carrying an in-sheet instruction to stop and contact the PI at a score of 2 or
higher. It was completed on eight of twenty-two steps, never exceeded 1, and both severity-1 events
were the SAME setting on two separate blocks (110 Hz, 2.5 mA left with 2.0 mA right). A reproducible
mild effect at one setting is a more useful observation than scattered events, and is worth
confirming prospectively rather than treated as established from two occurrences.

One protocol deviation is recorded in the sheet itself: at step 2 the left pulse width was set to
110 us instead of the planned 100 us, so that anchor step is not a clean anchor. It is retained with
the deviation noted rather than dropped, because dropping it would remove one of only three anchor
observations.

### 2026-08-30 — the objective changes site: LEFT LEG replaces the global rating

PI direction: the left leg is the critical site, the head is not a target, and the back warrants a
separate parallel optimizer. The acute clinic-testing data support this on their own terms.

Fitting each pain site separately with visit fixed effects and cluster-robust standard errors by
visit (442 steps at or above the 60 s threshold, 24 visits), the **site-specific scores detect a
stimulation on/off effect that the global rating misses entirely**:

| site | on/off effect (NRS) | 95% CI | p | n |
|---|---|---|---|---|
| left leg | +1.31 | [+0.25, +2.38] | 0.016 | 125 |
| left foot | +1.46 | [+0.47, +2.46] | 0.004 | 90 |
| back | +1.22 | [+0.20, +2.25] | 0.020 | 134 |
| right leg | +1.14 | [+0.01, +2.28] | 0.048 | 92 |
| right foot | +2.09 | [+0.44, +3.75] | 0.013 | 88 |
| **Overall** | **+0.27** | **[-0.19, +0.73]** | **0.25** | **256** |

The mechanism is visible in the correlation structure: the Overall rating correlates 0.84 with the
back score but only 0.71 with the left leg. When this participant reports a single global number
she is largely reporting her back, so a left-leg-specific effect cannot surface in it. Optimising
the Overall score would optimise the wrong quantity, and it has the largest sample of any item,
which is exactly how a well-powered analysis of the wrong outcome produces a confident null.

**Head is excluded**, both by PI direction and because it is unusable: 19 scored steps across 7
visits, against 126 for the left leg.

**Back is a parallel optimizer, not a blend.** Left leg and back correlate 0.67, so roughly 55% of
their variance is site-specific; averaging them would discard exactly the distinction that motivates
tracking both. Two independent optimizers over the same parameter grid, with the trade-off between
them surfaced to the clinician, is the honest structure.

Implementation: the pain metric is now a registered object (`PAIN_METRICS` in `objective.py`) rather
than a hard-coded column, with `left_leg` as the default. `ITEM_COLUMNS` resolves canonical item
names across the chronic REDCap frame (`left_leg_vas`) and the acute clinic frame (`pain_Left_Leg`).
Single-item metrics are NOT z-scored, so J_pain stays in NRS points; the legacy mixed-scale
composite still is, and its J_pain is in pooled SD units. A metric whose item is absent raises
rather than silently averaging over whatever is present.

The previous exclusion of `left_leg_vas` and `back_vas` for 74% completeness is **withdrawn**. The
missingness is real and is now handled as a weighting problem through `observation_variance`, the
same mechanism that handles short exposures, rather than by discarding the PI's primary outcome.

**What this does NOT establish.** With an explicit on/off term in the model, amplitude titration
among active settings is still not resolved at the left leg (-0.37 NRS/mA, 95% CI [-0.94, +0.20],
p = 0.21). The one titration effect that reaches significance runs the *wrong* way: **right-hemisphere
amplitude is associated with worse left-leg pain** (+0.82 NRS/mA, 95% CI [+0.14, +1.51], p = 0.018,
active steps only), consistent in sign across every specification and at the back as well. That is a
concrete, testable hypothesis pointing at *reducing* right-side amplitude, and it is the opposite of
the "push amplitude higher" reading the chronic surrogate produced. It is one test among many run
here and must be treated as a hypothesis for prospective testing, not an established effect.

### 2026-08-30 — the two frames record the same construct on DIFFERENT SCALES

Caught while rebuilding the chronic matrix on the new primary metric. The chronic REDCap items
ending in `_vas` are **0-100 visual analogue scales** (`left_leg_vas` median 59, max 100) while the
acute clinic-testing items are **0-10 numeric rating scales** (`pain_Left_Leg` median 4, max 8).
Resolving one metric name across both frames without declaring this produced a J_pain range of
-19.6 to +38.4, which is impossible on a 0-10 outcome.

Two consequences, both corrected. First, J_pain would silently have meant different things
depending on which frame supplied it. Second and worse, the section 2.3 side-effect ladder is
calibrated so that one mild side effect cancels exactly 1.0 NRS point; against a 0-100 objective
that penalty is ten times too weak, so a setting causing a mild side effect would have been
selected over one that did not.

`NATIVE_SCALE` now declares each column's native range and everything is rescaled to a common 0-10
reference before J_pain is formed, with the SD rescaled by the same factor. Unknown columns are
assumed to be already on the target scale. Two regression tests pin this: the chronic and acute
paths must produce identical J_pain for the same pain, and the rescaled VAS path must agree with
the legacy NRS path.

### 2026-08-30 — the two site objectives disagree, which is why they stay separate

Built on the rebuilt 60 s matrix, the left-leg and back objectives rank the same 71 epochs with a
Spearman correlation of only **0.479**, and they select different best epochs (66 versus 63). A
single blended objective would have averaged away a real disagreement about which setting is best
and reported false confidence. The parallel-optimizer structure is therefore not a stylistic
preference; it is required by the data.

### 2026-08-30 — the laterality hypothesis is NOT corroborated chronically

The acute data suggested right-hemisphere amplitude worsens left-leg pain (+0.82 NRS/mA, p = 0.018).
The chronic record does not replicate this. Across 34 bilaterally-active epochs with at least three
left-leg reports, **both** left (Spearman rho = -0.435, p = 0.010) and right (rho = -0.392,
p = 0.022) amplitude correlate with *lower* left-leg pain, and the left-minus-right contrast is null
(rho = -0.078, p = 0.66).

These chronic correlations are unadjusted and amplitude is confounded with time in that record
(rho = +0.39 with date while pain fell), so the chronic estimate cannot arbitrate — it is the same
confound that has invalidated every other chronic amplitude reading here. The two records disagree
in sign on right amplitude, and neither is currently able to settle it. The hypothesis stays open
and untested rather than corroborated.

### 2026-08-30 — wash-in cut from 5 minutes to 60 seconds

PI direction: 60 s is the operative threshold, and each test step is judged against its own recorded
duration rather than a single global window. `DEFAULTS["washin_h"]` is now 60/3600 h. In the acute
data the recorded durations range from 10 s to 720 s with a median of 60 s, so the threshold is
load-bearing: it retains 257 scored steps and excludes 68.

### 2026-08-30 — carryover between steps was TESTED and is not supported

The concern was that a rating reflects not only the current setting but stimulation delivered at
earlier steps. This was modelled as a first-order kinetic process: each step's amplitude builds an
effect toward its asymptote while delivered, then decays with time constant tau, with the effect
evaluated at the moment the rating is given. The exposure history uses **every** step including those
below the 60 s scoring threshold, since a step too short to score still delivers current.

Profiling tau from 1.2 seconds to 8 hours on the left-leg outcome, **AIC increases monotonically with
tau across the entire range** (406.8 at the shortest, 423.7 at 60 min, 424.5 at 8 h). The optimum sits
at the boundary where the accumulated effect becomes numerically identical to the instantaneous
setting. There is therefore **no evidence of carryover on any timescale tested**, which is consistent
with the PI's clinical observation of a rapid responder and independently supports the 60 s wash-in.

This also disposes of a competing explanation for the within-session decline. If pain fell through a
session because therapeutic effect accumulated, a long tau would have fit better than a short one; it
fits worse. The decline of roughly -0.09 to -0.11 NRS per step is robust at every site and is **not**
accumulated dose. Its cause remains unidentified — habituation to the rating task, relaxation over
the visit, and regression to the mean after arriving in pain all remain live, and this design cannot
separate them.

Note for the surrogate: because carryover is absent, the GP may continue to treat each step as an
independent observation of its own setting. Had tau been large, the input would have had to be the
convolved exposure rather than the programmed value.

A probit Gaussian process is a separate mechanism and is unaffected by this result: it is the link
function for learning from forced binary preference comparisons (Louie 2021), not a model of
temporal carryover. It remains part of the preference-model track.

### 2026-08-29 (late) — zero-amplitude epochs are a distinct state, not the low end of the dose axis

A third of the warm start is not amplitude-titration data. Of 86 epochs carrying reports, only **50 are
bilaterally active** (456 reports); 21 have the left hemisphere at 0 mA with the right active (118
reports), 9 the reverse (38 reports), and **6 have both hemispheres at 0 mA** (134 reports, 1466 hours).

The zeros are real, not an unpopulated field. Three independent fields agree: among the 83
active-group left sensing channels reporting `SuspendAmplitudeInMilliAmps` = 0, the summed per-contact
`ElectrodeAmplitudeInMilliAmps` is 0.0 in **all 83**, and the same-session PDF reports 0.0 mA in 39 of
the 42 sessions that could be matched. Note that 76 of the 83 have device stimulation status ON, which
is consistent: the group is enabled but delivers nothing on that side, i.e. unilateral or sensing-only.

**These epochs must not enter the amplitude surrogate as points at amplitude 0.** A left amplitude of
0 mA is not a small left-hemisphere dose; it is a qualitatively different therapeutic state, sometimes
with the contralateral side active and sometimes with no stimulation at all. Including them steepens
the fitted amplitude gradient because they carry the worst pain scores. Measured effect: refitting on
the 59 epochs with left amplitude above 0 reduces the fitted gradient across 0.8-4.8 mA from **0.803 to
0.599 NRS points**, a 25% reduction. The dose-response therefore survives as an effect among genuinely
active settings, but a quarter of its apparent magnitude was the trivial contrast between stimulating
and not stimulating. A `state` column (`bilateral_active`, `left_off_right_on`, `right_off_left_on`,
`both_off`) is now carried in the design matrix, and only `bilateral_active` and `right_off_left_on`
rows belong in the left-amplitude surrogate.

### 2026-08-29 (late) — the age-inflation term amplifies the time confound it was meant to mitigate

Section 2.5's observation-variance inflation multiplies the sampling variance by terms in exposure
duration and observation age, so that stale evidence is down-weighted. Because amplitude is positively
confounded with time in this record (days versus left amplitude rho = +0.39, p = 0.001), the age term
systematically down-weights the older low-amplitude epochs and up-weights the recent high-amplitude
ones. It does not merely fail to correct the confound; it strengthens it.

Measured: the unweighted difference in epoch-mean NRS between low (<= 2.0 mA) and high (>= 3.0 mA)
amplitude epochs is **0.187** points. The precision-weighted difference is **0.540** points, nearly
three times larger. This is not explained by replicate count or within-epoch scatter, both of which
favour the LOW-amplitude group (mean 9.8 reports per epoch versus 6.9; mean within-epoch SD 0.752
versus 0.822). It is the age and duration terms: mean `obs_var` is 0.553 for low-amplitude epochs
against 0.445 for high-amplitude ones despite the low group having more replicates.

Required consequence: **the era-blocked analysis is now the deciding test, not a supporting one**, and
it must be run with the age-inflation term disabled as a sensitivity analysis. Any amplitude
recommendation stated before that comparison is reported is uninterpretable. The "push amplitude
higher" reading is downgraded accordingly.

### 2026-08-29 (late, REVISED) — the JSON has two program schemas; canonical source is still the JSON

**Retraction.** An earlier version of this amendment stated that the JSON session reports truncate the
amplitude record and that the PDF session reports should be used instead. That was wrong. The JSONs
contain the complete amplitude history. The apparent loss was a parser defect: amplitude lives in two
different places depending on how a group is configured, and only one was being read.

- **Legacy schema.** `ProgramSettings.{LeftHemisphere,RightHemisphere}.Programs[]`, delivered amplitude
  in `AmplitudeInMilliAmps`, rate at the group level.
- **BrainSense schema.** A sensing-configured group has **no hemisphere keys**. The per-hemisphere
  program is in `ProgramSettings.SensingChannel[]`, one entry per side keyed by `HemisphereLocation`,
  with the delivered amplitude in **`SuspendAmplitudeInMilliAmps`**, pulse width and rate on the
  channel, per-contact amplitudes in `ElectrodeState[].ElectrodeAmplitudeInMilliAmps`, and the
  closed-loop configuration in `AdaptiveTherapy` and `Upper/LowerCaptureAmplitudeInMilliAmps`.

The split is not a date cutoff and not a home-versus-clinic distinction: of 1088 active-group
hemisphere records, 681 are sensing-schema and 407 legacy, and both appear in both session types. For
this participant every active group was sensing-configured by July 2026, which is what made a
hemisphere-only parser fail exactly in the window of interest.

**Cross-validation against the PDFs.** On 439 sessions where both sources describe the same group and
hemisphere, amplitude is identical in 432 (98.4%), pulse width and rate in 99.5%. Seven disagreements
remain, two of them inside the escalation window (2026-07-07: JSON 3.5 mA / 60 us versus PDF 4.0 mA /
100 us; 2026-07-22: JSON 4.0 versus PDF 4.5). These are plausibly same-visit reprogramming captured at
slightly different moments, and the in-clinic Google Sheets record is the natural arbiter. The
"27 levels reaching 5.0 mA" claimed for the PDFs was an artifact of comparing active-group-only JSON
records against all-group PDF records; the 5.0 mA belonged to Group B on 24 sessions in July-August
2025, which was never the active group.

**Canonical warm start**, from the dual-schema parse including the dated `GroupHistory` snapshots:
**102 setting-change epochs, 86 with data, 56 with n >= 3, 746 usable reports** at the 5-minute
wash-in. Including `GroupHistory` is what raises the epoch count from 73 to 102, because those
snapshots record between-visit changes that per-session data cannot show.

**Two further corrections to earlier claims in this document.** First, `UpperLimitInMilliAmps` is a
genuine clinician ceiling, not a copy of the delivered amplitude: it exceeds the delivered value in
96.5% of legacy-schema records (median headroom 0.60 mA) and 58.3% of sensing-schema records (median
0.30 mA). The safety model can therefore be anchored on it, which removes the main reason the
two-anchor seed was internally inconsistent. Second, **pulse width is asymmetric between hemispheres**
in roughly 90% of timestamps, most commonly 60 us left with 160 us right, so section 1's instruction to
pin pulse width must specify a value per hemisphere rather than a single number.

**The scientific conclusion inverts.** The missing window was an amplitude escalation, not a plateau:
55 Hz throughout, left/right amplitude 2.0/1.6 -> 3.5/3.5 -> 4.0/4.0 -> 4.5/4.5 -> 4.0/3.0 -> 3.5/3.0,
with pulse width moving 60 -> 100 us and the cathode moving from ring 1 to ring 2. **Four of the five**
best-performing epochs with n >= 5 come from that high-amplitude period: 4.0/3.0 at NRS 6.00, 3.5/3.5
at 6.10, 4.5/4.5 at 6.47 and 3.5/3.0 at 6.56. The fifth is **epoch 65 at 1.8/1.4 mA, 60 us, ring 1**
(t0 = 2026-06-11, n = 9, NRS 6.56), which predates the escalation (epoch 66 starts 2026-06-18) and is
one of the lowest amplitudes in the record, yet ties 3.5/3.0 for fourth-best.

That tie is evidence against a purely monotone amplitude story and must not be dropped. Two readings
survive it: either the response surface has a second low-amplitude optimum that the GP's fitted
amplitude length scale of 3.81 is too smooth to represent, or epoch 65 and the escalation epochs are
both being carried by the same underlying temporal improvement (days versus NRS -0.61). Note that
epoch 65 differs from the best escalation epochs in pulse width AND ring as well as amplitude, so it
is not a clean amplitude contrast at all. Resolving this is a specific job for the era-blocked
re-analysis, and until it is resolved the "push amplitude higher" reading is a leading hypothesis
rather than a finding.

Consequences that must be carried forward:

- **The incumbent is no longer 55 Hz / 1.6 mA.** It is epoch 73 — 55 Hz, 3.5 mA left / 3.0 mA right,
  100 us, ring 2 — with n = 18 at NRS 6.56. Every `J` value is referenced to this instead.
- **Amplitude is confounded with time in the OPPOSITE direction** to what the JSONs implied: days versus
  left amplitude is now +0.39 (p = 0.001), not -0.14. Amplitude went up as pain came down
  (days versus NRS -0.61, p < 0.0001; left amplitude versus NRS -0.21, p = 0.090).
- **The surrogate now finds a real amplitude dose-response.** Amplitude length scale 3.81, and the
  posterior mean at 55 Hz falls monotonically from +0.803 at 0.8 mA to +0.034 at 4.5 mA before
  flattening at 4.8-5.0 — roughly 0.77 NRS points of predicted benefit across the range, with
  diminishing returns above ~4.4 mA that match the clinical decision to back off from 4.5 to 3.5.
- **The highest-expected-improvement cells are 55 Hz at 4.4-5.0 mA**, i.e. push amplitude higher. The
  earlier "flat in amplitude, go to 40 Hz at 1.6 mA" reading was an artifact of the truncated record.
- Search grid amplitude extended to **0.8-5.0 mA** in 0.1 mA steps (12 x 43 = 516 cells).
- **All Phase 4 validation and figure outputs are superseded.** They were computed on the JSON-derived
  matrix. The calibration verdict, plateau decision, exploration queue, confound audit, replay numbers
  and all five figures must be regenerated from the corrected matrix before any of them is quoted.
- Pulse width and cathode are NOT constant across the record and are not yet in the model. Pinning
  pulse width prospectively (spec section 1) remains required and is now more clearly load-bearing,
  since the best epochs differ in pulse width AND ring from the earlier ones.

### 2026-08-29 — energy normaliser fixed to a grid constant (section 2.4 reworded)

Section 2.4 said `J_energy` was "Normalised to [0, 1] over the grid", but `energy_penalty` divided by
`np.nanmax` of whatever array it was handed, and `build_objective` handed it the epoch columns. The
divisor therefore moved with the epoch table, so `w_energy` silently rescaled every time the data
changed. No numeric effect at the default `w_energy = 0`, but the pre-registered meaning of the weight
did not hold once enabled.

Now divided by a fixed constant, `objective.ENERGY_REF` = 165 Hz, 5.0 mA, 60 us, TEED **247500**. The
pulse width is 60 us because section 1 pins it at 60 us prospectively; an earlier version of this
constant used 140 us, which is an historical value, not a grid value, and inflated the divisor by
2.33x so that in-grid values topped out near 0.43 instead of 1.0. Section 2.4 is reworded to state the
fixed reference and to say explicitly that out-of-grid settings score above 1 and are left unclipped.

### 2026-08-29 — safety seeding requires two anchors

Section 2.3 said the safety GP would be seeded from the programmed `UpperLimitInMilliAmps`. Seeding
from the limits alone is degenerate: every pseudo-observation sits exactly at the severity threshold,
so `mu + beta*sigma >= threshold` everywhere and the safe set is empty for any `beta > 0` (measured:
144 safe cells at beta = 0, zero at beta = 1).

Corrected seeding uses **two** anchors: settings the patient sustained for at least 72 h are encoded
at severity 0 (tolerated), and the programmed upper limits at the threshold. This gives the monotone
prior mean a ramp to fit and leaves headroom below the limit. Measured behaviour after the fix, with
21 tolerated anchors and 12 limit anchors: max safe amplitude 4.00 mA at beta = 0, 3.30 mA at
beta = 2.0, 1.70 mA at beta = 3.0, and 1.90 mA once the no-side-effect expansion cap from the
incumbent 1.6 mA is also applied.

Note this makes limited use of duration as a tolerability surrogate, which section 2.3 had marked
off-by-default. The restriction is retained for the *objective*; for the safety seed a 72 h minimum
is required and the anchors carry deliberately large variances. Seeds are dropped as soon as
prospective severity reports exist.
