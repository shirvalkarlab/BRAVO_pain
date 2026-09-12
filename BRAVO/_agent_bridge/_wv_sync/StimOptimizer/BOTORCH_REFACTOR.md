# An ordinal safety model, a BoTorch objective surrogate, and whether torch belongs in the container

This document reports three things. The first is what an ordinal Gaussian-process model of
side-effect severity says about participant RCS08 when it is fitted to the coded acute-step
record. The second is whether the BoTorch objective surrogate in `routines/surrogate_torch.py`
computes the same posterior as the scikit-learn surrogate it would replace, and where the two
diverge. The third is a recommendation about adding PyTorch to the production Django container.

Every number below was computed in the session that wrote this file and re-read from the
computation before being written down. The commands that reproduce each one are listed in the
last section. Where something was not measured, this document says so rather than estimating it.

## Contents

1. [Part one: the ordinal safety model](#part-one-the-ordinal-safety-model)
2. [Part two: the BoTorch objective surrogate](#part-two-the-botorch-objective-surrogate)
3. [Part three: should PyTorch go into the production container](#part-three-should-pytorch-go-into-the-production-container)
4. [Reproducing every number in this document](#reproducing-every-number-in-this-document)

---

## Part one: the ordinal safety model

### Why the previous safety model had to be replaced

`routines/surrogate.SafetyGP` models side-effect severity as a continuous number and gives it a
prior mean that is constrained to be non-decreasing in stimulation amplitude. Both parts of that
are wrong for this participant.

Severity is not a number. The record labels each step with one of four ordered categories — none,
mild, moderate, severe. Treating those as 0, 1, 2 and 3 and fitting a Gaussian likelihood asserts
that the step from none to mild is the same size as the step from moderate to severe, which
nobody established. It also produces predictions such as "severity 0.31", which corresponds to no
clinical statement and cannot be acted on.

Severity does not increase with amplitude here. Over the 417 steps that enter the model the
Spearman correlation between amplitude and severity rank is **-0.0129 with p = 0.793**. The rate
of moderate-or-worse events by amplitude band is 0 of 26 below 1 mA, 9 of 183 between 1 and
2 mA (4.92 percent), 5 of 103 between 2 and 3 mA (4.85 percent), 3 of 86 between 3 and 4 mA
(3.49 percent) and 2 of 19 at or above 4 mA (10.5 percent). There is no monotone trend to fit,
and a model that assumes one has assumed its own answer.

`routines/safety_ordinal.OrdinalSeverityGP` replaces it with an ordered-probit Gaussian process:
a latent function with a GP prior over the stimulation parameters, and a set of learned cutpoints
that turn the latent value into a probability for each ordered category. The likelihood and the
variational fit are adapted from Meta's AEPsych package, specifically
`aepsych/likelihoods/ordinal.py` and `aepsych/models/ordinal_gp.py`, which were built for
adaptive psychophysics experiments in which a person rates a stimulus on an ordered scale. That
is the closest published analogue to rating-driven stimulation optimisation. AEPsych is
MIT-licensed; the approach is adapted and the source file is cited in a comment at each place it
was used.

### What went into the model, and one problem with the labels

The file is `rcs08_acute_steps_coded.csv`, artifact version
`b4886a4f-7080-4484-9932-e23e71681f18`, 774 coded acute steps.

| Step | Rows |
|---|---|
| Input rows | 774 |
| Dropped: procedural | 151 |
| Dropped: severity could not be coded | 26 |
| Dropped: incomplete rate, amplitude or pulse width | 22 |
| Dropped: amplitude zero (stimulation off) | 158 |
| **Fitted** | **417** |

The 417 fitted steps carry 375 none, 23 mild, 18 moderate and 1 severe, an observed
moderate-or-worse rate of **4.56 percent**.

The 26 steps whose severity could not be coded are dropped and never recoded as "none", because a
step read as no-side-effect is a positive claim that a setting was tolerated, and inventing that
claim for a step nobody could code would tell the model that an untested region is safe. The
158 zero-amplitude steps are dropped from the fit because the frequency and pulse width recorded
alongside a zero amplitude do not describe stimulation that was delivered, but their adverse-event
rate is retained and reported: **3.16 percent**, against 4.56 percent with stimulation on. Adverse
events are therefore not rare when the device is off, which is itself a caution against
attributing them to stimulation.

**There is a larger problem with the labels, and it changes the conclusions.** Of the 774 rows,
346 carry `coded = True`, meaning a coder classified them; 26 carry `coded = False`, meaning a
coder looked and could not classify them; and **402 have no value at all, meaning they were never
presented to a coder. Every one of those 402 rows carries the label "none".** In other words, 402
of the 696 "none" labels in the file — 58 percent of them — record the absence of a side-effect
note rather than a recorded observation that no side effect occurred. That is the same category
of error as treating an uncoded row as tolerated, arriving through a different door.

`prepare_coded_steps` reports this split in its audit dictionary and offers `explicit_only=True`,
which keeps only rows a coder actually classified. Both fits are reported below, because the
difference between them is large and a reader has to see both to know how much weight the primary
result can carry.

### What the model says about this participant

Fitted on the 417 steps over frequency (on a base-2 logarithmic axis), amplitude and pulse width,
with 188 distinct settings all used as inducing points:

| Fitted quantity | Value |
|---|---|
| Cutpoints (latent scale) | 0, 0.470, 1.802 |
| Length scale, frequency (standardised log2 axis) | 0.381 |
| Length scale, amplitude (standardised) | 0.464 |
| Length scale, pulse width (standardised) | 2.465 |
| Constant mean | -1.593 |
| Mean probability assigned to the observed category, in sample | 0.825 |
| Predicted against observed adverse rate, in sample | 0.0494 against 0.0456 |

The reporting grid is the 10 observed frequencies crossed with amplitudes from 0.5 to 4.9 mA in
0.1 mA steps, at the modal pulse width of 100 microseconds: 450 cells. Across that grid the
estimated probability of a moderate-or-worse event runs from **0.7 percent to 23.4 percent**, with
a median of 5.7 percent.

**The risk structure is in frequency, not amplitude.** Averaged across frequencies, the estimated
probability varies with amplitude only between 3.3 percent (at 2.5 mA) and 8.9 percent (at
1.9 mA), a spread of 5.6 percentage points with no trend in either direction. Holding amplitude at
2.0 mA and varying frequency, the same probability runs from **1.1 percent at 55 Hz to 21.2 percent
at 125 Hz**, a factor of 18.7:

| Rate | P(moderate or worse) | 90% credible interval | Effective local sample size |
|---|---|---|---|
| 10 Hz | 0.043 | 0.000 to 0.183 | 11.0 |
| 25 Hz | 0.066 | 0.000 to 0.287 | 5.7 |
| 55 Hz | 0.011 | 0.000 to 0.051 | 41.2 |
| 85 Hz | 0.041 | 0.000 to 0.184 | 49.2 |
| 100 Hz | 0.054 | 0.004 to 0.171 | 63.7 |
| 110 Hz | 0.086 | 0.029 to 0.173 | 69.8 |
| 125 Hz | **0.212** | 0.066 to 0.417 | 66.1 |
| 145 Hz | 0.176 | 0.039 to 0.391 | 52.9 |
| 165 Hz | 0.077 | 0.003 to 0.255 | 39.4 |
| 180 Hz | 0.057 | 0.001 to 0.230 | 30.5 |

Only three cells on the whole grid are classified `elevated`, meaning the LOWER end of the 90
percent credible interval exceeds the 5 percent tolerance: 125 Hz at 1.9 and 2.0 mA, and 10 Hz at
1.4 mA. Fourteen cells are classified `safe`, all of them at 55 Hz, at amplitudes between 0.9 and
2.9 mA. The remaining 433 cells are `unknown`.

That the safe set is 14 cells out of 450 is the honest summary of this record. Almost nothing in
this parameter space is resolved.

### Above 4 mA the model reports ignorance, not safety

This was the specific question asked, and the answer is unambiguous. Comparing the 90 cells above
4 mA against the well-sampled band from 1 to 3 mA:

| Quantity (median over cells) | 1 to 3 mA | Above 4 mA | Ratio |
|---|---|---|---|
| Width of the 90% credible interval on P(moderate or worse) | 0.165 | 0.301 | 1.8x |
| Upper end of that interval | 0.171 | 0.301 | 1.8x |
| Latent posterior standard deviation | 0.647 | 0.947 | 1.5x |
| Effective local sample size | 43.6 | 4.1 | 0.09x |

**Zero of the 90 cells above 4 mA are classified safe.** The latent standard deviation of 0.947
should be read against the prior value of exactly 1: above 4 mA the model has recovered almost no
information relative to what it assumed before seeing any data. The declared clinical amplitude
ceiling is 4.9 mA, and nothing in this analysis supports raising it or treating the range between
4 and 4.9 mA as explored.

Two mechanisms keep an unvisited region out of the safe set, and it is worth knowing which does
what. The credible interval does most of the work: where the latent variance has reverted to the
prior, the interval on the probability is wide and its upper end exceeds any reasonable tolerance.
The second is an explicit requirement for local evidence, measured as the summed kernel
correlation between a cell and every training observation, which is on the scale of a count of
observations. Probing two settings nobody has ever delivered makes the point concretely. At
180 Hz, 4.8 mA, 260 microseconds the model reports an estimated probability of 8.0 percent — which
looks unremarkable — with an interval reaching 36.5 percent, a latent standard deviation of 0.998
and an effective local sample size of 0.82. At 10 Hz, 4.9 mA, 20 microseconds the corresponding
numbers are 7.0 percent, 33.0 percent, 0.999 and 0.14. Both are labelled `unknown`.
`test_a_region_with_no_data_is_unknown_and_never_safe` pins this behaviour and demonstrates the
evidence requirement in isolation by relaxing the probability tolerance until only the evidence
condition can decide.

### The safe set: recomputed against cumulative, and whether it is programmable

Cole's MATLAB SAFE-OPT reference makes the safe set cumulative. The update in
`code/safe_opt_memory/safe_opt_update_ND.m` reads
`safe_set = any([safe_set  Q_low > threshold], 2)`, so a cell that has ever qualified stays in
permanently and the set can only grow. That removes the instability of recomputing the set from
scratch at every iteration, where a recommendation can appear and disappear between updates.

`SafeSetTracker` implements both rules, and they were compared on the real record by refitting the
model on a growing prefix of the 25 visits and classifying the same 450-cell grid after each
refit. The two rules were identical until visit 23, when both admitted 15 cells. At visit 24 the
recomputed set fell to 13 while the cumulative set rose to 16, and at visit 25 the recomputed set
stood at **14** and the cumulative set at **16**. The difference is **two cells at 3.0 and 3.1 mA
that the model admitted at visit 23 and withdrew at visit 24, and that the cumulative rule
retained.** That is a small number, but it is a direct demonstration of the risk: a cumulative set
cannot withdraw an admission made on a posterior that later data contradict.

**The recomputed rule is the default in this module,** for that reason and because the evidence
here is thin enough that admissions should remain revisable. The cumulative rule is available and
gates admission on the same minimum-evidence requirement, so a cell admitted only because nothing
contradicted it cannot enter a set it can never leave. Nothing here should be described as "using
SAFE-OPT": only the safe-set update rule is borrowed. In the reference, safety and efficacy are
the same Gaussian process over a single discriminant score, whereas here pain relief and
side-effect severity are different quantities with different likelihoods, so the model structure
does not transfer.

**An ordinal model does not by itself give a contiguous safe set.** This is worth stating plainly
because the disconnected-island defect was one of the motivations for this work. At 55 Hz the
recomputed safe set covers 0.9 to 1.3 mA and then 2.1 to 2.9 mA, with a gap from 1.4 to 2.0 mA.
A clinician ramps amplitude upward through intermediate values, so the cells above the gap are not
programmable, whatever the model thinks of them. Removing the monotone prior mean removed a false
assumption; it did not produce contiguity, and contiguity has to be imposed separately.
`SafeSetTracker.contiguity_violations` reports the gaps and `SafeSetTracker.lower_interval`
truncates the set at the first unsafe amplitude, which never adds a cell.

Applying that projection to this record leaves **zero cells**, because the safe set does not
include the lowest amplitude on the grid at any frequency. Part of that is a property of the grid
rather than of the patient: the grid starts at 0.5 mA and the record holds only 26 steps below
1 mA, so the very lowest amplitudes are themselves poorly evidenced. The practical reading is that
a ramp starting from 0.5 mA on this grid is not supported end to end by the current evidence, and
a clinician ramping from an already-tolerated starting amplitude rather than from the bottom of
the grid is outside what this projection models.

### Sensitivity to the label-provenance problem, and it is large

Refitting on only the 153 steps that a coder explicitly classified changes the picture
substantially:

| | Primary fit | Explicit-coded only |
|---|---|---|
| Steps fitted | 417 | 153 |
| Observed moderate-or-worse rate | 4.56% | **12.42%** |
| Adverse rate at zero amplitude | 3.16% | **16.13%** |
| Median estimated probability across the grid | 0.057 | **0.167** |
| Highest estimated probability on the grid | 0.234 at 10 Hz, 1.3 mA | **0.644 at 125 Hz, 1.9 mA** |
| Median credible-interval width, 1 to 3 mA | 0.165 | 0.462 |
| Median credible-interval width, above 4 mA | 0.301 | 0.643 |
| Cells classified safe | 14 | **0** |
| Cells classified elevated | 3 | **63** |

**Under the strict reading, no cell on the grid is safe and 63 are elevated.** The entire safe set
of the primary fit depends on counting 402 never-coded rows as observations of no side effect.

Neither fit is obviously the right one. The primary fit is optimistic if a step went uncoded
because nothing was written down when something did happen. The strict fit is pessimistic if
coding was triggered by the presence of a note, so that coded rows are enriched for events by
construction — and the zero-amplitude adverse rate of 16.13 percent under the strict reading,
against 3.16 percent under the primary reading, is consistent with exactly that enrichment. What
can be said is that the two directions of the finding are robust to the choice: frequency near
125 Hz carries the highest estimated risk under both, and no region above 4 mA is safe under
either. The absolute probability level is not robust and should not be quoted without saying which
reading produced it.

**This should be resolved by looking at the source records, not by modelling.** Until it is, the
absolute risk level for this participant is uncertain by roughly a factor of three.

### Stability of the fit

The model was refitted with four random seeds on the primary data. The fitted length scales,
cutpoints and constant mean agree to three decimal places across all four. The estimated
probability at four probe settings has an across-seed standard deviation of at most 0.0053 and an
across-seed range of at most 0.0147. The classification
counts move a little more, because cells sitting close to the 5 percent tolerance flip: safe
counts of 14, 11, 13 and 15, and elevated counts of 3, 5, 2 and 2, out of 450 cells. The maximum
safe amplitude is 2.9 mA for three seeds and 3.0 mA for the fourth. **The underlying posterior is
stable; the boundary of the safe set is not, at the level of one or two cells.**

One setting is not a free performance dial and is worth recording. With the inducing-point set
capped at 128 and therefore subsampled from the 188 distinct settings, the same data give fitted
length scales of 1.25, 3.35 and 5.77 rather than 0.38, 0.46 and 2.47, and 26 safe cells rather
than 14. A subsampled inducing set makes the surface look much smoother than the data support. The
default is now 256 so that every distinct setting is retained and the sparse approximation is
exact at the observations.

### What this part does not establish

- No out-of-sample validation was run. The only fit statistic reported is in-sample, and it is
  there to catch a broken fit, not to establish predictive performance. Leave-one-visit-out
  calibration of the ordinal model was **not assessed**.
- Amplitude and frequency are not independent in this record, so the frequency effect reported
  above is not adjusted for anything that co-varies with frequency, including the visit on which
  each frequency was tested. It is an association in the delivered design, not a causal estimate.
- The 1 severe event is a single observation. Nothing in this document distinguishes moderate
  from severe.
- Left and right hemispheres are modelled together through the left-side parameters, since
  `amp_R` is present for only 165 of the 623 non-procedural rows. A separate right-hemisphere
  model was **not fitted**.

---

## Part two: the BoTorch objective surrogate

### Two defects found in the inherited draft, and fixed

A previous session left a draft of `routines/surrogate_torch.py`. Reviewing it against the
scikit-learn backend it claims to match turned up two defects in the reported hyperparameters,
both of which produced wrong numbers that looked plausible.

**The marginal likelihood was evaluated with the model in the wrong mode.** GPyTorch's
`ExactGP.__call__` returns the prior latent distribution in training mode and the posterior
predictive distribution in evaluation mode, and the draft evaluated it in evaluation mode, where
GPyTorch itself emits a `GPInputWarning`. Evaluating a marginal likelihood on the posterior at the
training inputs is not the marginal likelihood of anything. On the RCS08 design matrix the
reported value was **-97.32** where the correct value for the same expression is **-104.27**, an
error of 7.0 nats.

**The log prior was counted twice.** `ExactMarginalLogLikelihood` already adds the log density of
every registered prior into the value it returns before dividing by the number of observations.
Multiplying back by the number of observations therefore recovers the log likelihood plus the log
prior, which is the log posterior. The draft labelled that quantity `log_marginal_likelihood` and
then added the log prior to it again to form `log_posterior`.

The corrected decomposition subtracts instead. It can be checked against an external reference,
which is what `test_reported_marginal_likelihood_matches_sklearn_when_the_models_are_identical`
now does: with matched hyperparameters, a zero mean and the same total noise, both backends
describe the same Gaussian density over the same data, and the two log marginal likelihoods agree
to **0.0** at `-102.4053533`. A second check that the wrong value failed: the corrected marginal
likelihood under the prior is **-100.362**, which sits just below the **-100.302** that
scikit-learn reaches when it maximises the marginal likelihood directly with free length scales.
It has to be at or below that maximum, and it is, by 0.06 nats. The old value of -97.32 was above
it, which is impossible.

A third, smaller change: reading the `hyperparameters` property now restores whichever mode it
found the model in, so logging the hyperparameters between two predictions cannot silently change
the second one. `test_reading_the_hyperparameters_leaves_the_model_ready_to_predict` pins that.

The draft's `SeverityGP` was left in place because `ConstrainedBatchSelector` needs a model with a
Gaussian posterior on the constraint scale, but its docstring now says plainly that it fits a
Gaussian likelihood to an ordered categorical outcome and directs any clinician-facing statement
about safety to `safety_ordinal.OrdinalSeverityGP` instead.

### The equivalence check

Both backends were fitted to the same real design matrix, `rcs08_bo_design_matrix.csv`, artifact
version `79ee9a9b-7344-4a42-97ef-51caabf49861`, reduced by `build_objective` to the **71 feasible
epochs** with a positive frequency and a recorded left amplitude, on a **230-cell grid** of 10
frequencies by 23 amplitudes. The incumbent is epoch 102, the most recent by start time.

**Matched arm — identical hyperparameters, nothing fitted.** This isolates the posterior
calculation itself.

| Quantity | Value |
|---|---|
| Largest absolute difference in posterior mean over the grid | 1.22e-15 |
| Root-mean-square difference in posterior mean | 2.86e-16 |
| Largest absolute difference in posterior standard deviation | 6.66e-16 |
| Root-mean-square difference in standard deviation | 1.02e-16 |
| Correlation of the two mean surfaces | 1.000 |
| Best cell | 55 Hz, 4.1 mA, both backends |

Agreement is at machine precision. **The two backends compute the same Gaussian-process
posterior.** Matching required three conventions to line up: the objective is standardised with
the population standard deviation in both, the fitted homoscedastic noise appears in the
predictive standard deviation in both (because scikit-learn's `WhiteKernel` sits inside the
kernel), and the BoTorch mean function is set to zero because the scikit-learn backend has none.

**As-used arm — each backend fitted the way it would actually be used**, scikit-learn with its
length scales pinned at 0.823 and 0.72 and BoTorch fitting them under the log-normal prior.

| Quantity | Value |
|---|---|
| Largest absolute difference in posterior mean | 1.020 (units of J) |
| Root-mean-square difference in posterior mean | 0.381 |
| Largest absolute difference in posterior standard deviation | 0.102 |
| Correlation of the two mean surfaces | 0.592 |
| Correlation of the two standard-deviation surfaces | 0.632 |
| Worst cell | 110 Hz, 4.3 mA: scikit-learn 0.057, BoTorch 1.078 |
| Best cell | 55 Hz, 4.1 mA, both backends |
| Range of the mean surface | scikit-learn -0.149 to 1.184; BoTorch -0.350 to 1.400 |

**This is a material divergence and it needs explaining rather than accepting.** The objective is
in NRS points relative to the incumbent, so a disagreement of one full point at a grid cell is a
disagreement about whether that setting is worth trying. A correlation of 0.592 between the two
mean surfaces means the two backends substantially disagree about the shape of the response
surface, even though they happen to agree on the single best cell.

### Why they diverge: the frequency length scale has two answers, not one

The divergence is entirely attributable to the length scales, and the cause is more specific than
"the likelihood is flat", which is what the existing `surrogate.py` docstring says.

Profiling the log posterior over the frequency length scale — pinning it and re-optimising the
amplitude length scale, the signal variance and the noise at each value, so this is a profile and
not a slice — gives a **bimodal** surface. Under the default prior there are two interior local
maxima, at a frequency length scale of **0.219** and of **2.562** on the standardised log2 axis.
The first is the model treating each frequency as nearly independent of its neighbours; the second
is the model borrowing across the whole frequency range. The likelihood prefers the first by
**2.789 nats** (-100.305 against -103.094).

The hand-pinned value of **0.823 sits in the valley between the two modes** and is preferred by
neither: its profile log marginal likelihood is -101.691, which is 1.39 nats worse than the short
solution and 1.40 nats better than the long one.

The default log-normal prior of Hvarfner et al. (2024), which BoTorch adopted as its default, has
a median length scale of 5.82 on these axes but a scale parameter of the square root of 3, which
is broad. It does not overturn the likelihood's preference. Sweeping the prior scale:

| Prior scale | Fitted length scales (freq, amp) | Max abs difference in mean | Correlation of means | Best cell agrees |
|---|---|---|---|---|
| 1.732 (default) | 0.222, 1.461 | 1.020 | 0.592 | yes |
| 1.000 | 0.541, 2.163 | 0.693 | 0.765 | no |
| 0.500 | 4.664, 3.674 | 0.540 | 0.854 | no |
| 0.350 | 5.239, 4.626 | 0.580 | 0.835 | no |
| 0.250 | 5.465, 5.464 | 0.691 | 0.798 | no |

For reference, the scikit-learn backend with free length scales and no prior lands at 0.203 and
2.018 on this data, so the default prior moves the frequency length scale only from 0.203 to
0.222.

**That last sentence is true of this data set and is not a property of the model, and the
distinction matters enough to state separately.** Fitted with free length scales and no prior on
the six-epoch synthetic fixture the test suite uses, the same scikit-learn backend runs to the
**upper** bound of its length-scale box, 20.0, rather than to a near-zero value — the opposite end
of the permitted range, from the same non-identifiability. Under the default prior that fixture
lands at 0.288. So on one data set the default prior barely moves the estimate and on the other it
moves it by almost the whole range. Any claim of the form "the prior barely moves the estimate"
has to name the data set it was measured on.

What generalises is less comfortable. Fitting at a fixed prior scale across four data sets whose
likelihoods disagree — the RCS08 design matrix and three variants of the six-epoch fixture with
the outcome reversed and rescaled — gives fitted frequency length scales that barely differ
between the data sets at four of the five scales tested:

| Prior scale | RCS08 (71 epochs) | Fixture (6 epochs) | Spread across all four data sets |
|---|---|---|---|
| 1.732 (default) | 0.222 | 0.288 | 0.066 |
| 1.000 | 0.541 | 2.140 | 1.599 |
| 0.500 | 4.664 | 4.530 | 0.133 |
| 0.350 | 5.239 | 5.146 | 0.093 |
| 0.250 | 5.465 | 5.465 | 0.0001 |

**The spread is not monotone in the prior scale, and reading it as a single threshold would be
wrong.** Ranked from most to least agreement between data sets, the scales run 0.25 (spread
0.0001), **1.732, the default (0.0659)**, 0.35 (0.0926), 0.5 (0.1333) and 1.0 (1.5989). The
default scale is the second most convergent row in the table, not a row where the data are
driving the answer, and a scale of 1.0 is the single setting at which the four data sets separate
at all.

What that means is worse for identifiability than a threshold would be. At the default scale all
four data sets land between 0.222 and 0.288 — a short length scale — even though their
unpenalised maximum-likelihood estimates are 0.203 and 20.0, two orders of magnitude apart. At
0.5 and tighter all four land near the prior median of 5.817. So at four of the five scales
tested the fit returns essentially the same number regardless of which data set it was shown;
what changes between those four is which number, and that is set by the prior scale. **No tested
setting returns a frequency length scale that is both stable and data-driven.**

The move between scales of 1.0 and 0.5 is the two basins changing places rather than a smooth
adjustment — at a scale of 0.5 the profile's global maximum is at 2.175 with a second local
maximum at 4.938, and the fitted 4.664 shows the optimiser settling in the second.

`prior_scale_sweep` and `profile_frequency_lengthscale` are in the module so this can be
re-measured rather than remembered, and `test_a_tight_prior_picks_the_length_scale_rather_than_estimating_it`
and `test_which_way_the_free_fit_degenerates_is_a_property_of_the_data_not_the_model` pin both
findings. The profile function deliberately uses the scikit-learn backend to do its fitting, so
that a property of the likelihood surface cannot be confused with a property of BoTorch's
optimiser.

### What to do about the length scale

The honest summary is that switching to a prior does not solve the identifiability problem. It
makes the assumption explicit, lets it update as prospective data arrive, and propagates the
smoothness uncertainty into the posterior standard deviations the acquisition function reads — all
of which are real advantages over pinning. But on this data the default prior selects the same
near-independent-frequency solution that maximum likelihood does, so adopting it as a drop-in
replacement for the pinned 0.823 would change the surrogate substantially without anyone having
decided to; and tightening it far enough to reach the smooth solution replaces the data's answer
with the prior's rather than sharpening it.

The recommendation is to **keep the scikit-learn backend as the default for now**, and to treat
the choice of frequency length scale as an open scientific question rather than a setting. Two
things would close it.

The first is prospective data in which frequency is varied within a visit, which would break the
confounding between frequency and time that makes the short length scale attractive to the
likelihood. This is the only route that resolves the question with evidence rather than by
assumption, and it is the one worth pursuing.

The second is a declared assumption. If the group's position is that neighbouring frequencies
should behave similarly, that position should be written into `OBJECTIVE_SPEC.md` as an assumption
with a stated value, and the value should be reported as an assumption everywhere it appears. An
earlier draft of this document recommended implementing it as a prior scale near 0.5 rather than a
pinned point value, on the reasoning that a prior is more honest than a pin. **That
recommendation is withdrawn.** At a prior scale of 0.5 the fitted length scale agrees to within
0.13 across four data sets whose likelihoods disagree, so the number the fit reports is the
prior's, not this patient's. Reporting it as a fitted quantity would be less honest than pinning,
not more, because it would carry the appearance of having been estimated. If the assumption is
being made, it should be made visibly as a pinned value with a written justification.

### What part two does not establish

- The claim of equivalence is about the posterior calculation, established at machine precision in
  the matched arm. It is **not** a claim that the two backends give the same recommendations. In
  the as-used arm they do not.
- No calibration comparison was run between the backends. Leave-one-epoch-out calibration of the
  BoTorch backend was **not assessed**.
- `ConstrainedBatchSelector` and `TorchPreferenceGP` were inherited from the draft, are covered by
  the existing tests, and were reviewed but not re-derived. The preference model's agreement with
  the hand-written Laplace approximation in `routines/preference.py` was **not measured**.

---

## Part three: should PyTorch go into the production container

### The backend can be optional, and this is verified rather than asserted

Both `surrogate_torch.py` and `safety_ordinal.py` import the PyTorch stack inside a `try` block
that captures the exception. Importing either module on a machine without PyTorch succeeds,
`torch_available()` and `ordinal_torch_available()` return `False`, and constructing a model
raises an `ImportError` that names the missing packages and the file to install them for.

The evidence is the test suite itself. Run in the `stimopt_torch` environment the full
`StimOptimizer` suite gives **352 passed, 1 skipped**. Run in `bravo_app`, which has no PyTorch
installed, the same suite gives **312 passed, 41 skipped** — the same 353 tests collected, with
41 of them skipped for the absent dependency instead of 1. Every skip is attributable to the
torch marker and no errors. The parts of the safety reasoning that do not need a fitted model —
the label handling in `prepare_coded_steps`, including the never-coded audit, and all of the
safe-set bookkeeping and contiguity checking in `SafeSetTracker` — run without PyTorch and are
covered by tests that run in the torch-free environment.

### On size: not measured for the relevant artefact

The size of the CPU-only Linux wheel could not be measured, because `download.pytorch.org` is not
on this sandbox's network allowlist. **That number is not estimated here.**

What was measured is the on-disk footprint of the already-installed macOS ARM64 packages in the
`stimopt_torch` environment: **torch 528 MB, gpytorch 2.7 MB, botorch 6.7 MB, linear_operator
1.7 MB**, against scikit-learn 47 MB, SciPy 64 MB and NumPy 34 MB in the same environment. That
is an installed footprint on a different platform, not a wheel size, and the CPU-only Linux build
is smaller than a build carrying GPU kernels — by how much is not established here. The direction
is nonetheless clear: PyTorch is roughly an order of magnitude larger than the largest scientific
dependency the container already carries.

Import and fit costs were measured on this machine and are small. Importing torch takes 0.66
seconds, with gpytorch and botorch adding 0.04 seconds on top. Fitting the ordinal severity model
on 417 steps for 600 iterations takes 4.7 seconds, and classifying the 450-cell grid afterwards
takes 3 milliseconds. Fitting the BoTorch objective surrogate on 71 observations and predicting
the whole 230-cell grid takes 0.02 seconds, against 0.13 seconds for the scikit-learn backend with
12 restarts.

### Recommendation

**Do not add PyTorch to the production Django container. Keep it an optional dependency of a
research environment, and keep the scikit-learn backend as the default.** No container or
dependency configuration was modified in producing this document.

The reasoning rests on what was established rather than on the size that could not be measured.

The objective surrogate does not need it. The two backends agree to machine precision when given
the same hyperparameters, so BoTorch buys no accuracy in the posterior; the only difference is how
the length scales are chosen, and part two shows that the default prior does not resolve that
question either. On a 230-cell grid the acquisition function is evaluated exhaustively, so there
is nothing for a gradient-based acquisition optimiser to do.

The ordinal safety model is the piece that genuinely needs GPyTorch, since no scikit-learn or
statsmodels routine implements a variational GP with an ordinal likelihood. But it does not need
to run inside the request path. It is fitted from a batch of coded acute steps that arrive after a
visit, not per request, and refitting takes about five seconds. Fitting it offline in a research
environment and shipping the fitted classification — the per-cell probability, its credible
interval, the effective local sample size and the three-state label — to the web layer as data is
both simpler to deploy and easier to audit, because the numbers a clinician saw are then a stored
artifact rather than the output of a model version nobody recorded.

The condition under which this recommendation should be revisited is closed-loop operation in
which the safety classification has to be recomputed inside a request, or a decision to use
BoTorch's joint batch acquisition over a grid large enough that exhaustive evaluation stops being
practical. Neither applies now.

---

## Reproducing every number in this document

Environment `stimopt_torch` for anything involving PyTorch, `bravo_app` for the torch-free checks.
From `BRAVO/modules` with `PYTHONPATH=.`:

```python
import numpy as np, pandas as pd
from StimOptimizer.routines import safety_ordinal as so
from StimOptimizer.routines import surrogate_torch as st
from StimOptimizer.routines.objective import build_objective
from StimOptimizer.routines.surrogate import ParameterGrid, ObjectiveGP

# --- part one: the ordinal safety model -------------------------------------------------
# artifact b4886a4f-7080-4484-9932-e23e71681f18
steps = pd.read_csv("rcs08_acute_steps_coded.csv")
prep = so.prepare_coded_steps(steps)                 # audit dict holds every drop count
model = so.OrdinalSeverityGP(("rate_hz", "amp_L", "pw_L")).fit(prep["X"], prep["y"])
model.hyperparameters                                # cutpoints, length scales, constant mean
rates = np.unique(prep["X"][:, 0])
amps = np.round(np.arange(0.5, 5.0, 0.1), 2)
G = np.array([[r, a, 100.0] for r in rates for a in amps], float)
c = model.classify(G)                                # label, p_mean, p_lower, p_upper, n_eff
so.SafeSetTracker.contiguity_violations(c["label"] == "safe", G)
strict = so.prepare_coded_steps(steps, explicit_only=True)   # the sensitivity fit

# --- part two: the equivalence check ----------------------------------------------------
# artifact 79ee9a9b-7344-4a42-97ef-51caabf49861
dm = pd.read_csv("rcs08_bo_design_matrix.csv")
obj = build_objective(dm, incumbent_epoch=float(dm.sort_values("t0")["epoch"].iloc[-1]))
keep = obj["feasible"] & obj[["freq_hz", "amp_mA_Left"]].notna().all(axis=1) & (obj["freq_hz"] > 0)
o = obj[keep]
X = o[["freq_hz", "amp_mA_Left"]].to_numpy(float)
y, yv = o["J"].to_numpy(float), o["obs_var"].to_numpy(float)
# The design matrix contains only 6 distinct frequencies (10, 55, 110, 125, 145, 165 Hz), so the
# grid is the union of those with the 10 rates the acute record actually tested, which is the
# space the optimiser searches. That union has 10 entries; 10 x 23 amplitudes = 230 cells.
TESTED_RATES = [10, 25, 55, 85, 100, 110, 125, 145, 165, 180]
grid = ParameterGrid(sorted(set(np.r_[np.unique(X[:, 0]), TESTED_RATES])),
                     np.round(np.arange(0.5, 5.0, 0.2), 2))
st.equivalence_report(grid, X, y, yv)                # matched and as_used arms
st.prior_scale_sweep(grid, X, y, yv)                 # the transition table
st.profile_frequency_lengthscale(grid, X, y, yv)     # the bimodality, no torch required
```

Test suites:

```bash
# with the PyTorch stack: 352 passed, 1 skipped
cd BRAVO/modules && PYTHONPATH=. python -B -m pytest StimOptimizer/tests -q \
  -p no:cacheprovider -W ignore                       # env: stimopt_torch

# without it, which is the container's configuration: 312 passed, 41 skipped
cd BRAVO/modules && PYTHONPATH=. python -B -m pytest StimOptimizer/tests -q \
  -p no:cacheprovider -W ignore                       # env: bravo_app
```

The suite stood at 218 passed before this work began. The 41 tests added here — 32 in
`tests/test_safety_ordinal.py` and 9 in `tests/test_surrogate_torch.py` — account for part of the
increase; the rest came from other work landing in this repository at the same time, so the total
will have moved again by the time this is read. What should not move is the relationship between
the two lines: the same number of tests is collected in both environments, and the only difference
is how many are skipped.

The seed-stability and safe-set-rule comparisons were run from a driver script in the working
directory rather than from the repository. The safe-set comparison refits the model on a growing
prefix of the 25 visits and folds each classification into both a `SafeSetTracker(mode=
"recomputed")` and a `SafeSetTracker(mode="cumulative")`; the seed check refits with
`random_state` in 0, 1, 2, 3 and compares fitted hyperparameters, grid classifications and the
estimated probability at four probe settings.
