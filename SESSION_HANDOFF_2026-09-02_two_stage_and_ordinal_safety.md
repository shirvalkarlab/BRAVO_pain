# Session handoff — 2026-09-02 — two-stage split, F8 reconciliation, ordinal safety model

Working branch `PS_closedloop_deployment`. This session ran overnight and unattended after the PI
asked for the two-stage architecture split, the F8 family reconciliation, and use of whatever is
genuinely reusable from the published Bayesian-optimization codebases.

## State at the start of the overnight stretch

- Container Biomarkers suite `PASS=311 FAIL=0`; StimOptimizer suite 203 passed, 15 skipped.
- All thirteen actionable inference-audit items closed except the second part of F8.
- Local and remote in sync at `4105b2f`.

## What the reference codebases actually contain — corrects an earlier claim in this project

An earlier note recorded four repositories as candidates for reuse. Inspecting them tonight
changes the picture substantially, and two of the earlier characterisations were wrong.

| repository | what it actually is | usable? |
|---|---|---|
| `facebookresearch/aepsych` | 186 Python files on gpytorch/botorch — Meta's adaptive-psychophysics stack for human-rating experiments | **Yes, the real reference** |
| `ericrcole/SafeOpt` | **MATLAB**, 74 author `.m` files plus a vendored GPML MATLAB toolbox, zero `.py` files | Algorithm only, must be reimplemented |
| `markjconnolly/meta_bayesian_optimization` | an 83-byte README and nothing else | **No — the repository is empty** |
| `jerdra/BOONStim` | a Nextflow pipeline for transcranial magnetic stimulation targeting | Not relevant |

Note for whoever fetches these: **`git clone` fails in this sandbox** because creating a `.git`
directory is blocked. Use the codeload tarball endpoint
(`https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/main`) and extract it instead.
GitHub itself is reachable; only `download.pytorch.org` is off the network allowlist.

### What `aepsych` supplies that we actually need

`aepsych/likelihoods/ordinal.py` and `aepsych/models/ordinal_gp.py` implement a cutpoint ordinal
likelihood inside a variational Gaussian process. That is the correct structure for this project's
side-effect data, which is four ordered categories (none, mild, moderate, severe) rather than a
number, and it does **not** impose a monotone dose-response — which matters here, because imposing
one is precisely the error the current two-anchor safety seed makes and the error the data refuses.
`aepsych/models/pairwise_probit.py` is the probit preference model the module currently
approximates by hand.

### What Cole's MATLAB algorithm supplies, having read it

Two structural ideas, both relevant to defects already recorded against our safety layer:

1. **The safe set is CUMULATIVE.** `safe_opt_update_ND.m` line ~27 reads
   `safe_set = any([safe_set  Q_low > threshold], 2)`, so a grid cell that has ever qualified stays
   in the safe set permanently — the set only grows. Ours is recomputed from scratch on every
   update, which is why safe regions can appear and disappear between iterations and why proposed
   optima have been landing in disconnected islands. Adopting a cumulative set would remove that
   instability. **The caveat is real and must be stated:** a set that never shrinks is only sound if
   the safety model is genuinely conservative, because a cell admitted on a wrong posterior can
   never be withdrawn.
2. **His safety model and his objective model are the same Gaussian process.**
   `safety_mean = ds_mean_est` and `acquisition_mean = ds_mean_est` are the same array. In his
   setup safety and efficacy are one discriminant score with a floor beneath it. In ours they are
   genuinely different quantities — pain relief against side-effect severity — so his single-model
   structure does not transfer, and any claim that we are "using SAFE-OPT" should be qualified to
   the safe-set update rule rather than the model structure.

His safety criterion is a pessimistic lower bound, `Q_low = mean - beta*sigma > threshold`, and his
acquisition is an upper confidence bound with the standard growing schedule
`beta = 2*log(t^2*pi^2/6)` scaled by a separate exploration coefficient. Both are conventional; the
cumulative safe set is the distinctive part.

## Work dispatched

Three parallel tracks, with strict file ownership so they cannot collide:

1. **Two-stage split** — `stage1_openloop.py`, `stage2_closedloop.py`, `routines/stage_gate.py`,
   rewires `pipeline.py`, plus tests and `TWO_STAGE_DESIGN.md`.
2. **F8 reconciliation** — `Biomarkers/pipeline.py` and its tests, plus `RECONCILIATION_F8.md`.
3. **Ordinal safety model and BoTorch surrogate** — `routines/safety_ordinal.py`,
   `routines/surrogate_torch.py`, tests, and `BOTORCH_REFACTOR.md`.

Results, decisions and any refusals are recorded below as each track lands.

## Results

Four commits: `6001e00`, `ba089e2`, `bca0a01`, `ef6a996`. Container Biomarkers suite **320/320**;
host StimOptimizer suite **352 passed / 1 skipped** with the torch stack and **312 passed / 41
skipped** without it. Every suite figure here was confirmed by a run of my own rather than taken
from a track's report. Detail for each piece is in the commit messages and in §0 of the mega handoff;
what follows is what a reader most needs and what remains open.

### The single most important finding is a data defect, not a model

`rcs08_acute_steps_coded.csv` has a label-provenance problem that makes it much weaker than its 774
rows imply. The `coded` column is True for 346 rows, False for 26, and **absent for 402 — never
presented to a coder — and every one of those 402 carries `se_severity = "none"`.** So 58% of the
696 "none" labels are unexamined defaults. Only 294 rows were coded "none" by a human.

A trap to note: the sibling column `se_coded` is True for 748 rows *including* the never-coded ones,
so it is not a provenance flag. Use `coded`.

The defaults are not a random subset, which is what makes this substantive. They sit at
systematically lower amplitude (median 1.20 against 1.90 mA, Mann-Whitney p = 6.0e-11) and higher
rate (110 against 55 Hz, p = 2.1e-10). Free "no side effect" labels concentrated at low amplitude is
exactly the structure that flattens an amplitude–severity relationship.

**This corrects a figure I published earlier in this project.** I reported "amplitude does not
predict severity, Spearman rho = -0.013, p = 0.79 (n = 417)". On coder-examined rows only that
becomes **rho = -0.175, p = 0.027 (n = 161)** — a significant *negative* association — with the
moderate-or-worse rate rising from 4.4% to 11.8% once the defaults stop diluting it. The direction of
the conclusion survives and strengthens: a monotone *rising* amplitude–severity relationship is
unsupported, so the safe set must not impose an amplitude ceiling. The specific "no association,
p = 0.79" figure must not be requoted.

Settling the provenance of those 402 rows is the highest-value next action on the safety side, and it
is a records question rather than a modelling one.

### What the ordinal severity model says, all provisional to roughly a factor of three

Risk structure sits in **rate, not amplitude**: holding amplitude at 2.0 mA, P(moderate-or-worse)
runs 0.011 at 55 Hz, 0.086 at 110 Hz, 0.212 at 125 Hz and 0.176 at 145 Hz, an 18.7-fold range, while
moving amplitude at fixed rate spans only 3.3%–8.9%. 55 Hz is therefore both the device's closed-loop
minimum rate and the safest rate in this model.

Two counterweights, measured rather than assumed. A plain rank test does **not** support the rate
association marginally (rho = +0.031, p = 0.53 on all labels; +0.115, p = 0.16 on examined rows) —
the model conditions on amplitude while the rank test does not and the two covary here, so they are
not contradictory, but the effect is model-conditional and unadjusted for visit. And above 4 mA the
model reports **ignorance rather than safety**: 0 of 90 cells clear its evidence bar, credible
intervals are 1.8× wider and effective local sample size 11× smaller.

An honest negative: **an ordinal likelihood does not by itself fix the non-contiguous safe set.** At
55 Hz the safe region is 0.9–1.3 and 2.1–2.9 mA with a gap at 1.4–2.0 mA a clinician cannot ramp
through. Removing the monotone prior mean removed a false assumption; it did not produce contiguity.

Cumulative versus recomputed safe sets were compared on 25 visit-prefix refits rather than argued:
identical through visit 23, then differing by exactly two cells at 3.0–3.1 mA that the model admitted
and later withdrew. Recomputed is the default despite SAFE-OPT's cumulative rule, because an
admission made on a wrong posterior can never be withdrawn from a set that never shrinks.

### Two backends, one model — and an identifiability problem

With hyperparameters matched, the scikit-learn and BoTorch surrogates agree to 1.22e-15 on the
posterior mean over 230 grid cells: the same model to machine precision. Fitted as each would
actually be used they diverge by up to 1.020 J units with surface correlation only 0.592. The cause
was investigated rather than asserted: the profile log posterior over the frequency length scale is
**bimodal** on this design matrix (interior maxima at 0.219 and 2.562), not flat as
`routines/surrogate.py`'s docstring claims, and the default prior is too broad to choose between the
modes. That is a property of the data, not a backend bug.

**Recommendation: do not put PyTorch in the production container.** The optional import is verified,
not asserted — 353 tests collect in both environments with no errors. The CPU-only Linux wheel size
could not be measured (`download.pytorch.org` is not on the network allowlist); the recommendation
rests on the measured macOS footprint (torch 528 MB against scikit-learn 47 MB) and on the fact that
the backends compute the same posterior, so torch buys no accuracy here.

Gotcha worth keeping: the inducing-point count is a scientific setting, not a performance dial. At
128 the same data give length scales 1.25/3.35/5.77 and 26 safe cells; retaining all 188 distinct
settings gives 0.38/0.46/2.47 and 14 safe cells.

### A retraction of my own reasoning, recorded so it is not repeated

Chasing an item the reconciliation left unassessed, I found the `nrs` rating series strongly
autocorrelated and concluded that a block length of 1 meant an independent shuffle and therefore an
anti-conservative p-value, and replaced the lag-1 estimator with an integrated autocorrelation time.
Then I checked what block length 1 actually does: `circular_block_perm_matrix` returns the *n*
circular rotations, verified directly. A rotation preserves the entire autocorrelation function and
is **stricter** than a shuffle, so the old estimator was reaching the right null and my replacement
made it worse. Reverted; no published number moved. What survived is worth having: the false
"i.i.d. shuffle" docstring is corrected, and the p-value's resolution limit is now published
(`perm_n_distinct_nulls`, `perm_p_floor`, `perm_p_step`), because with only *n* rotations the floor
is ~1/(n+1) whatever the permutation count — so `nrs` at 0.0809 means "about 6 of 72 rotations" and
must not be read to three decimals or finely compared against 0.05.

## Open items, in the order I would take them

1. **Settle the 402 never-coded rows.** Every absolute severity probability depends on it, and it is
   a records question. Until then no safe set built from this file should gate a clinical decision.
2. **Out-of-sample calibration is not assessed anywhere** — not for the ordinal severity model, not
   for either objective backend, not per pulse-width stratum in stage 1. A surrogate that cannot
   predict a held-out era should not select settings.
3. **The frequency length scale is not identified by this data** under any prior tested, and the
   profile is bimodal. That is upstream of every posterior the module reports.
4. **The rotation-versus-block design question** in `block_length_for` — a decision for the PI, since
   changing it moves published p-values.
5. A right-hemisphere severity model was not fitted (`amp_R` present for only 165 of 623
   non-procedural rows), and hemispheres are currently modelled through the left-side parameters.
6. `TorchPreferenceGP` and `ConstrainedBatchSelector` were reviewed but left as inherited and their
   behaviour was not re-derived.

## Housekeeping

`BRAVO/modules/StimOptimizer/tests/_ordinal_analysis_driver.py` is untracked and was created by a
track outside its authorised file list. It asked to delete it, which needs a human approval that was
not available overnight, so the request was denied and the file left for the PI to bin. `pytest`
ignores it (leading underscore). `README_CORRECTIONS_SUMMARY.md` at the repo root remains untracked
and is not ours. Reference tarballs were extracted under the agent workspace, not the repo.
