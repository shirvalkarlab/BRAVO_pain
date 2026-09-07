# StimOptimizer

Bayesian optimization of DBS stimulation parameters against pain outcomes. Searches
(frequency, amplitude) on a discrete grid with a Gaussian-process surrogate over a composite pain
objective, under a separately modelled safety constraint, with a parallel preference model fitted
from forced binary comparisons.

**Read [`OBJECTIVE_SPEC.md`](OBJECTIVE_SPEC.md) before changing any threshold.** The objective, the
side-effect calibration and the stopping thresholds are pre-registered; amendments are logged there
with reasons.

## Layout

| path | contents |
|---|---|
| `routines/objective.py` | composite J, side-effect ladder, warm-start observation variance |
| `routines/surrogate.py` | `ParameterGrid`, `ObjectiveGP` (fixed-noise), `SafetyGP` (monotone prior mean) |
| `routines/preference.py` | `PreferenceGP` (pairwise probit, Laplace posterior) |
| `routines/acquisition.py` | EI / GP-UCB, safe set, batch selection, dual stopping rule |
| `tests/` | 35 regression tests; `pytest BRAVO/modules/StimOptimizer` |

Library mode only: no Django endpoint and no React view yet, the same staging the Biomarkers module
used. No torch dependency — the search grid is 396 cells, so the acquisition function is evaluated
exhaustively as Sarikhani et al. did, and scikit-learn's `GaussianProcessRegressor` covers the
Matern-3/2 ARD kernel with per-observation noise variance.

## Sign conventions, because they differ between models

- **`J` is minimised.** Lower is better. `J = 0` at the incumbent chronic setting by construction,
  so negative means better than status quo.
- The optimistic (best-case) bound at a cell is therefore `mu - kappa*sigma`.
- **Preference latent values are maximised.** Higher means more preferred. Code converting between
  the two must negate explicitly; `PreferenceGP.best()` returns an argmax, not an argmin.
- Safety severity is maximised-bad: the safe set is where `mu_SE + beta*sigma_SE < threshold`.

## The one knob to tune

`beta`, the safety conservatism multiplier. Cole et al. 2024 swept 30 configuration combinations
across 6 subject models x 15 trials and found beta the only parameter that significantly predicted
overshoot into unsafe territory; the exploration weight `eta` and the hyperprior weight did not.
Measured on the RCS08 warm start, max safe amplitude runs 4.00 mA at beta = 0, 3.30 mA at
beta = 2.0 (the default) and 1.70 mA at beta = 3.0.

## Pending obstacle: nonstationarity

**Every model in this module assumes a static response surface. Chronic DBS does not have one.**

The interim mitigation is in place and is deliberately weak: `objective.observation_variance`
inflates each historical observation's variance with its age,
`tau^2_age = c_age * (age_days/365)^2`, so a 2025 epoch is trusted less than a 2026 one. That
down-weights stale evidence but it does not *track* drift — the surrogate still has one time-invariant
mean function, so a setting whose true effect has changed will be modelled as noisy rather than as
having moved.

What is not implemented:

- **A time-varying kernel.** Fleming et al. 2023 (doi:10.1371/journal.pcbi.1011674) present
  TV-BayesOpt, which tracks both gradual drift (disease progression) and periodic variation
  (circadian and other biological rhythms), in a computational model of phase-locked DBS.
- **Adaptive recalibration.** Aiello et al. 2023 (doi:10.1088/1741-2552/acc975) add temporal
  information to GP-based Bayesian optimization to track drift in evoked-sensation location and
  perceptual threshold, evaluated offline against retrospective calibration data from a human
  implantable-neuromodulation trial.

Neither has prospective chronic human validation in the literature, so this is a genuine gap rather
than an implementation backlog item. Given that this platform already holds months of continuous
sensing plus a year of dated PROs, it is also the place where a contribution is available.

Concrete first step when this is picked up: add a forgetting factor to the objective kernel — either
an explicit `exp(-|t_i - t_j|/tau)` product term, or a spectral-mixture component for the circadian
period — and validate it the way Phase 4 validates the static model, by leave-one-era-out prediction.
If a time-varying kernel cannot predict a held-out era better than the static kernel with
age-inflated variance, it has not earned its extra parameters.

## Related pending obstacle: no side-effect channel

Phase 1 found no structured stimulation side-effect severity field in the PRO battery. `tingly` is
28% complete and both it and `electrocuting` are McGill pain-quality descriptors, not adverse-event
reports. Until an ordinal none/mild/moderate/severe item is collected, `SafetyGP` runs on the
two-anchor seed (sustained exposures at severity 0, programmed `UpperLimitInMilliAmps` at threshold)
and the objective's `J_SE` is identically zero with `se_observed = False`. This is a
data-collection change, not something the module can model around.
