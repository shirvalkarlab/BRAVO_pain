# Findings: Closed-Loop grid stability column

Observations only. Nothing here is an instruction. Every code location below was read directly in
this session, not recalled — but every line number will move, so search for the name.

## 1. What is actually built, and what is not

Track D (decision 67) shipped both halves of the stability answer and the switch that would run
them, and nothing turns the switch on.

| Piece | Where | State |
|---|---|---|
| Raw, untranslated answer per (contact, band centre) | `Biomarkers.bravo_service.raw_stability_result_for_point` | built |
| Attaches it to every grid row | `Biomarkers.bravo_service._attach_grid_export_columns` | built, runs only behind the flag |
| The honest four-valued translation | `ClosedLoopDeployment.stability.finding_from_stability_result` | built |
| Reader that applies the translation | `ClosedLoopDeployment.adapter.band_sweep_grid_for_closed_loop` | built |
| The panel that displays it | `ClosedLoopSim/BandSweepGridPanel.js`, `StabilityChip` | built |
| Anything that sets `IncludeCrossSettingStability` | — | **does not exist** |

Confirmed by grep across the repository with the compiled bundle excluded: the string
`IncludeCrossSettingStability` appears in `bravo_service.py` (the one place that reads it), in two
`BandSweepGridPanel.js` lines that are a comment and a tooltip, and in documentation. No client
code sets it in any request body. So `StabilityChip`'s "stability: not yet computed" branch is the
only branch any real page view has ever taken.

## 2. Why it is off, stated as the measurement rather than as a preference

Decision 68 records a full grid build with the flag off at 5.85 s and with it on at 326.7 s, for all
six sensing contact pairs. **That pair is a document number and Phase 1 re-measures it** — CLAUDE.md
§10 rule 3 forbids carrying a timing forward, including this project's own.

The same decision records what turning it on did to the response: 27,865 fields in common, 0
dropped, 10,560 new fields (all under `cross_setting_stability_raw` and `device_rules_status`), and
of the common fields only 22 differed — every one a timing field or the store key, which changes
correctly because the flag is folded into the sweep's own cache key. Zero scientific values moved.
That is the shape Phase 4's own proof should reproduce.

## 3. The import direction is a hard rule, and it has already been broken once

`stability.py`'s docstring makes it explicit: `ClosedLoopDeployment` may import `Biomarkers`, never
the reverse. An earlier Track D draft applied the four-valued translation inside Biomarkers, which
broke that direction and was caught only when the container could not import it.

A second, related finding from decision 67 worth carrying: `stability.py` had imported
`Biomarkers.routines.analytics` with the bare host-only spelling, which the production container
cannot resolve. The consequence was that `adapter.py`'s already-shipped single-candidate
`band_stability` field had likely never returned its real four-valued answer inside the real
gunicorn container since the day it was wired in — only ever "not tested" with a swallowed import
error. It was fixed with the double-import pattern. The lesson for this task: a swallowed import
error in this codebase produces a normal-looking, fast response that is silently missing its
answer, so "it returned without raising" proves nothing.

## 4. The failure mode this column is most likely to hit

`_attach_grid_export_columns` carries its own warning, written after it happened: the first draft
read `center_hz` (a synthetic test's field name) instead of `band_center_hz` (the real row field).
Because a missing key is treated as "skip this row" rather than an error, the bug attached nothing
to any row while still returning a normal-looking, fast response with no exception anywhere. It was
caught only by comparing a flag-on response's own field count against a flag-off one and finding
them equal when they should not have been.

So the check that actually discriminates here is a field COUNT comparison between flag-off and
flag-on, not a shape check and not the absence of an exception.

## 5. What a reader sees today, and why that matters for the options

`BandSweepGridPanel.js`'s `StabilityChip` renders a greyed chip reading "stability: not yet
computed" with a tooltip naming the flag. That is honest — it says the answer was not computed
rather than implying the band is stable — and it matches this project's standing three-state
discipline (decision 9: a gate that goes green on absence of evidence is unsafe). Whatever option
Phase 2 picks, that branch should survive for rows whose answer genuinely has not been computed
yet, rather than being replaced by a blank cell.

## 6. Cost structure, as far as reading goes (to be confirmed by measurement in Phase 1)

`_attach_grid_export_columns` caches per band centre within a channel (`cache = {}` keyed on
`center_hz`), and the correlation and AUC grids share the same 22 centres, so the per-channel call
count is 22 rather than 44. With six real sensing contact pairs on RCS08 that is on the order of
132 calls to `raw_stability_result_for_point`.

Decision 67 recorded two individual live calls at 4.61 s and 2.17 s, the first paying rpy2/R's
one-time initialisation. 132 calls at roughly 2.2 s each is in the region of 290 s, which is
consistent with the 326.7 s full-grid figure. **This is arithmetic over two sampled calls, not a
measurement** — Phase 1 replaces it with a real per-point cost and a real count.

If that structure holds, it is the fact that makes option (b) — compute for the one row a reader
opens — attractive: a single point is a couple of seconds, which is an ordinary click-through cost,
and it is the same shape the grid's existing per-cell drill-down already uses.

## 7. Open item 26 sits on the same grid and is NOT part of this task

Open item 26 (the length-of-signal axis means nothing for a cell served by the device's own
spectrum, and nothing marks which cells those are) is a display and reporting decision on this same
grid, explicitly recorded as the PI's call. It is noted here so it is not rediscovered as new, and
deliberately left out of this plan's scope: it needs its own answer, and bundling a display question
into a cost question would put two decisions behind one go-ahead.

## 8. MEASURED: where the per-point cost actually goes (2026-09-09, live RCS08)

Probe: `BRAVO/_agent_bridge/_probe_stability_cost.py`, three band centres on ONE_THREE_LEFT,
timing each inner call inside `_validate_band_core` by wrapping the module attribute.

| Inner call | Point 1 (cold) | Point 2 | Point 3 | Depends on the band centre? |
|---|---|---|---|---|
| `_load_pros` | 0.937 | 0.740 | 0.709 | **No** |
| `_cached_psd_matrix` | 0.346 | 0.347 | 0.340 | **No** |
| `build_pooled_detail_from_matrix` | 0.101 | 0.096 | 0.108 | **No** |
| `_load_recordings` (chronic, for the stim series) | 0.282 | 0.268 | 0.269 | **No** |
| `band_mixedmodel_inference` (glmer) | 2.069 | 0.189 | 0.190 | Yes — **and the result is discarded** |
| `band_stim_stability` | 0.725 | 0.645 | 0.568 | Yes — **this is the only thing wanted** |
| **whole call** | **4.526** | **2.301** | **2.202** | |

The parts account for the whole: point 2's inner calls sum to 2.285 s against a 2.301 s total.

### 8a. The setup is participant-level, not point-level and not even channel-level

Read directly in `_validate_band_core`: none of `_load_pros`, `_cached_psd_matrix`,
`build_pooled_detail_from_matrix` or `_load_recordings` takes a `channel` or a `center_hz`
argument. `build_pooled_detail_from_matrix(mat, pm[0], pm[1], ...)` builds the pooled detail for
EVERY channel at once, and the channel is resolved later, inside `band_stim_stability`, by the
`for i, raw in enumerate(chans)` scan over `chan_order`.

So **1.451 s of every 2.25 s point (about 63%) is work that produces an identical answer every
time and is redone for all 132 points.** It only ever needed to run once per participant.

### 8b. The grid path pays for a mixed model it throws away

`raw_stability_result_for_point` returns `(core.get("stim") or {})` — only the stim half.
`_validate_band_core` computes `glmer = analytics.band_mixedmodel_inference(...)` unconditionally
before that, at 0.189 s steady-state per point. For the grid export path that fit is computed and
discarded, 132 times.

### 8c. What that predicts, and what it does not

6 sensing contact pairs x 22 centres = 132 points.

- Current shape: 132 x ~2.25 s = **~297 s**, consistent with the 326.7 s on record.
- Setup hoisted out, glmer skipped: 1.45 s once + 132 x 0.645 s = **~86 s**, about 3.5x faster.

**This is arithmetic over a three-point sample, not a measured full-grid run.** It is the
hypothesis the build is aimed at; the real full-grid pair gets measured in alternating rounds
before any speed claim is made.

### 8d. Vectorization does not apply to the fit itself, and saying otherwise would be wrong

`band_stim_stability` fits two R mixed models per point through pymer4/rpy2 — `m0`
(`pain_high ~ band_power + stim_era + (1|era)`) against `m1`
(`pain_high ~ band_power * stim_era + (1|era)`) — and takes the likelihood-ratio test between
them, plus separate per-era GLM fits for the displayed odds ratios. Each point needs its own fit
on its own band-power column. There is no numpy formulation of that, and no way to batch it into
one call through rpy2.

What IS vectorizable is the band-power extraction feeding each fit (integrating the spectrum over
a 5 Hz window is a slice-and-mean that could be computed for all 22 centres at once instead of
once per call). That is real but small next to a 0.645 s fit.

Parallelism across points is the other lever and is deliberately NOT taken first: rpy2 holds a
single embedded R process, this repository already has a commit devoted to R thread safety
(`a191b758`), and `band_stim_stability` returns "pymer4/rpy2 unavailable" rather than raising when
the import fails — so a threading mistake here degrades to a silently answerless column rather
than to a crash. Hoisting and skipping are deterministic wins with no concurrency risk; they come
first, and parallelism is only considered afterwards if the number still is not good enough.

## 9. MEASURED: 93-98% of a stability call is inside R's model fitting

Probe: `BRAVO/_agent_bridge/_probe_fit_split.py`. Wraps `pymer4.models.Lmer.fit` with a timer and
calls `band_stim_stability` directly on a setup bundle, five centres on ONE_THREE_LEFT.

| Centre | Whole call | Inside R fits | R fits | Everything else (Python) | Share in R |
|---|---|---|---|---|---|
| 12.5 (first, pays R warm-up) | 1.2885 | 1.2041 | 2 | 0.0845 | 93.4% |
| 18.5 | 0.6509 | 0.6392 | 2 | 0.0117 | 98.2% |
| 24.5 | 0.5213 | 0.5100 | 2 | 0.0113 | 97.8% |
| 9.5 | 0.5608 | 0.5504 | 2 | 0.0105 | 98.1% |
| 15.5 | 0.4929 | 0.4821 | 2 | 0.0108 | 97.8% |

Exactly two `Lmer.fit` calls per point, as the docstring says: `m0` reduced against `m1` full.

### 9a. This closes the vectorization question with a number

All the Python-side work in a steady-state call — band-power extraction over the 5 Hz window, era
binning, assembling the frame — is **0.011 s**. Vectorizing the band extraction across all 22
centres could recover at most that, so about 1.5 s across a 132-point grid that costs ~86 s. It is
roughly 1.7% of the total and not worth the risk of changing what feeds a statistical fit.

The remaining 98% is `lme4` fitting inside R, reached through rpy2. It is not Python, not numpy,
and not reachable by any array rewrite on this side.

### 9b. And it rules GPU acceleration out, for a structural reason rather than a missing library

The hot path is `lme4::lmer`, compiled C++ (Eigen) running on CPU. There is no Metal or CUDA
backend for `lme4`, and the shape of the work is wrong for one anyway: 132 sequential fits of a
SMALL mixed model, where each fit is a short iterative optimization over a few hundred rows. GPUs
win on large dense linear algebra; here per-kernel launch overhead would exceed the work.

The honest framing: this is a **many-small-sequential-fits latency problem, not a throughput
problem**. The lever that matches that shape is process-level parallelism, not a GPU.

Two further points that would decide it even if a GPU backend existed. Production is the Linux
`bravo-server` container, so a Mac GPU is not the deployment target. And replacing `lme4` with a
GPU-capable mixed-model implementation would change the estimator, which would invalidate every
equality proof this feature rests on — including the ONE_THREE_LEFT/12.5 Hz case the whole honest
four-valued answer is anchored to.

### 9c. What the remaining lever actually is

rpy2 holds ONE embedded R process and is not thread-safe, so threads cannot help. Separate
PROCESSES each get their own R, and the 132 fits are independent. At the measured ~0.645 s per
point: 4 workers would put a full grid near 22 s, 8 near 11 s, before accounting for each worker
paying its own setup and R warm-up. Not attempted yet — it is Phase 4's decision, and it comes
after the deterministic wins are proven, per the plan's decision 3.

## 10. Alternatives to lme4/glmer — external research, 2026-09-09

**Every number in this section is a published third-party benchmark on someone else's data. None of
it is a measurement of this repository's code.** Our own measured figure is the only one that
describes us: 0.645 s per point, 93-98% inside two `Lmer.fit` calls (§9).

The model to replace, read from `analytics.band_stim_stability`: `family="binomial"`, so a logistic
GLMM, not a Gaussian LMM — `pain_high ~ band_power * stim_era + (1|era)` against the reduced form,
a single scalar random intercept, a few hundred rows, LRT from the two log-likelihoods. Many
"fast mixed model" packages address the Gaussian case and do not help here.

### 10a. The size finding that decides the GPU question

Stan's own OpenCL guidance states speedups arrive when input variables contain **at least 20,000
elements**, and that only some functions have GPU support at all. Our fits are hundreds of rows.
**We are three orders of magnitude below the threshold where GPU offload begins to pay**, so this
is ruled out by problem size, not by a missing library — and that holds for CUDA and for Metal
alike. No Apple-GPU path exists for any GLMM package found.

The one genuinely GPU-accelerated GLMM result found (a Monte Carlo maximum-likelihood /
stochastic Newton-Raphson method, arXiv Jan 2026, >100-fold on GPU) is for LARGE spatial datasets
and is research code, not a package.

### 10b. Shortlist

| Option | Backend / GPU | Published evidence | Fit for us |
|---|---|---|---|
| Keep lme4, drop pymer4's wrapper | R/C++ (Eigen), no GPU | none — but see 10c | **Test first.** No statistical change at all. |
| `glmer(..., nAGQ=0)` | same | ~3-4x on a Poisson GLMM benchmark | Cheap, but changes the estimator; needs equality re-proof |
| [GLMMadaptive](https://cran.r-project.org/package=GLMMadaptive) | R/C++, no GPU | 2-4x vs lme4; **best accuracy and convergence** of 7 packages in the 2026 survey | Built for scalar random intercepts — our exact shape. Best accuracy-preserving candidate |
| [glmmTMB](https://journal.r-project.org/articles/RJ-2017-066/index.html) | TMB / auto-diff, no GPU | 29x faster than lme4 on negative-binomial | Same survey found **lower convergence and more variance-component bias** — risky for an honest four-valued answer |
| [MixedModels.jl](https://juliastats.org/MixedModels.jl/) | Julia, no GPU | 0.374 ms vs lme4's 24.5 ms on a **333-row** LMM (~65x); lme4's own docs point to it | Fastest found, and the benchmark size matches ours — but adds a Julia runtime to the container |
| [GPBoost](https://github.com/fabsig/GPBoost) | C++, R+Python, optional CUDA | ">100x faster than lme4 in some cases" (author's own claim) | **CUDA covers the Gaussian-process part, not the GLMM linear part**; NVIDIA only, no Metal |
| Stan / brms + OpenCL | OpenCL GPU | 2-50x, **only above ~20,000 elements** | Ruled out by our size; also Bayesian, not an LRT |

### 10c. The unmeasured suspicion worth testing before any migration

Published lme4 on a 333-row Gaussian LMM: 24.5 ms. Ours on a few hundred rows: 645 ms, roughly 26x
slower. Binomial GLMM is genuinely harder than Gaussian LMM, so some gap is expected — but our §9
probe wrapped `pymer4.models.Lmer.fit`, which includes pymer4 building an R data frame through
rpy2 and pulling results back. **How much of our 645 ms is lme4's optimizer versus pymer4/rpy2
marshalling is NOT known**, and it is the cheapest thing to find out: it needs no new dependency,
no new estimator, and no re-proof of any number. If marshalling is a large share, the fix is local
and keeps lme4's answers byte-identical.

Order of work this implies, cheapest and safest first:
1. Measure the pymer4/rpy2 share of the 645 ms (no risk, no migration).
2. Process-level parallelism (§9c) — no statistical change.
3. Only then consider GLMMadaptive, and only with a full equality proof against the current answers
   including the ONE_THREE_LEFT / 12.5 Hz "cannot tell" case.

Anything that changes the estimator changes numbers this feature's existing proofs are anchored to,
so it is a scientific decision for the PI, not a performance tweak.

## 11. MEASURED: pymer4's share, and 16-worker parallelism (2026-09-09, live RCS08)

### 11a. pymer4 wrapper vs lme4 itself — `_probe_pymer4_vs_lme4.py`

Captured the EXACT frame `band_stim_stability` hands to `Lmer` (421 rows, 37 clusters, formula
`pain_high ~ band_power * stim_era + (1|cluster)`, binomial), then timed three things on that one
frame, five rounds each.

| What | Median |
|---|---|
| pymer4 `Lmer(...).fit()` — today's path | **0.359 s** |
| pandas -> R data.frame conversion alone | **0.002 s** |
| `glmer(...)` alone, frame already in R, timed by R's own `system.time` | **0.216 s** |

**60.2% of the call is lme4. The other 0.143 s (40%) is pymer4.** The earlier suspicion that data
marshalling was the overhead is WRONG and is recorded as wrong: moving the frame into R costs 2 ms.
The 143 ms is pymer4's post-fit work — pulling coefficients, random effects and design information
back into pandas — which it does even with `summarize=False`.

Since each point runs two fits, dropping the wrapper is worth roughly 0.29 s per point. **It changes
no statistics whatsoever: it is the same `glmer` call on the same frame.** The one thing to carry
across is `logLike`, which the LRT needs; `logLik(fit)` supplies it.

### 11b. 16-worker process pool — `_probe_parallel.py`, full 132-point grid

Six real sensing contact pairs x 22 centres. Alternating rounds, as this project's rules require.

| Round | Serial | 16 workers | Speedup |
|---|---|---|---|
| 1 | 78.27 s | 9.75 s | 8.03x |
| 2 | 78.25 s | 9.81 s | 7.98x |

Serial is 0.593 s per point, which independently reproduces §8's 0.645 s single-point figure.

**Equality, not just speed:** all four runs returned 132 of 132 points with an `lrt_p`, and the sum
of every `lrt_p` was **52.212424853 in all four**, with identical values on the first three points.
Parallel and serial produce the same answers, not merely the same count.

8x on 16 cores rather than 16x is expected: each worker pays its own R start-up, and the fits are
short enough that per-task dispatch is visible.

### 11c. Forking is safe here for one specific reason, which must not be broken

R is not fork-safe once initialised. This works because `analytics.band_stim_stability` imports
pymer4 INSIDE the function rather than at module level, so a parent that only builds the setup
never starts an R process, and each forked child initialises its own. The probe asserts this and
recorded `r_loaded_in_parent_before_run: false` on every run.

**If anything ever moves that import to module scope, the fork approach breaks** — probably not
loudly. Any implementation must keep the check.

### 11d. Where this leaves the whole cost

| Stage | Full grid |
|---|---|
| As recorded before this work (decision 68) | 326.7 s |
| Setup hoisted + discarded glmer skipped, serial | **78.3 s measured** |
| The same, 16 workers | **9.8 s measured** |
| Plus dropping the pymer4 wrapper (projected, not yet built) | ~6 s |

The first two rows are measured. The last is arithmetic from 11a and is not a claim.

## 12. MixedModels.jl: the GPU benchmark cannot be run, and why (2026-09-09)

### 12a. Environment, checked rather than assumed

| Check | Result |
|---|---|
| `julia` on the Mac host | not installed |
| `julia` in the `bravo-server` container | not installed |
| `nvidia-smi` in the container | no NVIDIA GPU |

### 12b. MixedModels.jl has no GPU backend at all

This is not a missing driver or an unconfigured build. Verified two ways: the package's own
documentation describes no CUDA, Metal or other GPU backend, mentioning distributed computing only
for the parametric bootstrap; and a performance issue on the JuliaStats repository discusses GPU
methods as something that "would be possible" in places — i.e. not implemented.

So "MixedModels.jl on a single GPU" is not a benchmark that can be set up. There is nothing to run.
Two further facts would independently block it even if a backend existed: the production container
has no NVIDIA device, and Apple Metal is not reachable from a Linux container.

This is consistent with §10a: at a few hundred rows we are far below the ~20,000-element threshold
where GPU offload starts to pay for ANY framework.

### 12c. The 16-thread CPU benchmark is runnable, but not for free

Julia would have to be installed somewhere first — a language runtime plus the package registry and
MixedModels.jl's own dependencies. Two candidate targets, with different consequences:

- **The production container.** Comparable with every number already measured here (§8, §9, §11),
  since those all came from that machine. But it means installing a language runtime into the live
  server, which is a shared-system change.
- **The Mac host.** Touches nothing in production. Also 16 cores, so the thread-scaling shape would
  be informative — but the absolute numbers would NOT be comparable to the container figures, so it
  could not be placed beside the 78.3 s / 9.8 s pair without a caveat.

### 12d. What the benchmark would actually have to beat, and the risk it carries

The bar is no longer 326.7 s. It is **78.3 s serial and 9.8 s on 16 workers, both measured, with
the estimator unchanged and answers proven identical** (§11b).

And a Julia result would not be a like-for-like substitution. MixedModels.jl fits its own
generalized linear mixed model; its deviance and log-likelihood conventions for GLMMs are not
guaranteed to match lme4's, and this feature's whole output is a likelihood-ratio test built from
two log-likelihoods. Any adoption would need a full equality proof against the current answers,
including the ONE_THREE_LEFT / 12.5 Hz "cannot tell" case. A speed benchmark alone would not
settle whether it can be used.

## 13. BUILT AND PROVEN: direct glmer, core-count parallelism, batch failure policy (2026-09-09)

### 13a. pymer4 replaced by a direct `glmer` call — 5,148 fields, 0 differing

`analytics._binomial_glmer_loglik_pair` fits the reduced/full pair through rpy2 and returns their
log-likelihoods, which is ALL the LRT consumes (`ll0`/`ll1`; everything else in the result comes
from statsmodels). The pymer4 path is kept as the reference implementation behind
`USE_DIRECT_GLMER`, the same contract `USE_CHANNEL_INDEX` already established (decision 43).

Equality on all 132 real grid points, alternating rounds, flattened to scalar leaves:

| | |
|---|---|
| Fields compared | **5,148** |
| Fields differing | **0** |
| Fields only in one side | **0 / 0** |
| pymer4 reference | 77.80 s, 77.03 s |
| direct glmer | 36.97 s, 34.85 s |

**2.15x, with byte-identical answers.** It is the same `lme4::glmer` on the same frame — pymer4 is
itself a wrapper around exactly this call.

### 13b. Parallelism defaults to the machine's usable core count

`_stability_worker_count` uses `len(os.sched_getaffinity(0))` rather than `os.cpu_count()`:
affinity reports the cores this process may actually run on, which is what a container CPU limit
constrains; `cpu_count` would report the host's cores and oversubscribe. Measured `auto_workers:
16` on this container, detected rather than hardcoded. `workers=1` forces serial.

Parallel against serial through the public function, all 132 points: **5,148 fields compared, 0
differing, 0 points missing**, and `on_point` fired exactly 132 times.

### 13c. The fork guard fired during its own verification, which is the best evidence for it

The verification ran parallel, serial, parallel, serial and produced parallel timings of **8.23 s
then 35.84 s**. That is not variance. The serial run in between initialised rpy2's embedded R in
the parent, so the second parallel call's `_r_is_already_initialised()` check correctly refused to
fork and fell back to serial.

**This is the load-bearing operational constraint of the whole feature**: a process that has
already fitted anything can no longer fork. The background and scheduled entry points (Phases 4 and
5) must therefore run in their OWN process, not inside a gunicorn worker that has already served a
single-candidate request. A worker that has answered one such request would silently get serial
speed.

### 13d. Batch failure policy: carry on, stop after 3 consecutive raises

`STABILITY_BATCH_MAX_CONSECUTIVE_FAILURES = 3`. Ordinary "cannot answer" outcomes are RETURNED by
`band_stim_stability` (no stim series, one era, pymer4/rpy2 missing) and are stored as answers; the
counter only counts points that RAISED. Scattered failures look like bad bands and reset the
counter; a run of them looks like a broken fitting process and ends the batch.

Proven by making every fit raise: **3 points attempted, 129 never attempted**, all three marked
`available: False` carrying the real reason. A point that was never reached has NO ENTRY, which
stays distinguishable from an entry saying `available: False` — the Closed-Loop panel renders those
two differently, because "not computed" is not the same claim as "computed, and the answer is no".

### 13e. Where the cost now stands, all measured on the same machine

| Stage | Full 132-point grid |
|---|---|
| As recorded before this work (decision 68) | 326.7 s |
| Setup hoisted + discarded glmer skipped | 78.3 s |
| + pymer4 replaced by direct glmer | **~36 s** |
| + 16 cores | **8.2 s** |

About **40x**, with every step proven to change no value.

## 14. BLOCKER FOUND: the whole ClosedLoopDeployment module cannot be imported by the Django app

Found 2026-09-09 while verifying that Phase 4's stored grid reaches the Closed-Loop page. **This is
pre-existing, is not caused by any change in this task, and blocks the feature from ever being
visible.**

### 14a. The evidence, from Django's own process shape

Run through `manage.py shell` -- the exact process gunicorn's workers use, the technique decision 68
already established for this class of question:

```
PATHHAS_MODULES  False
IMPORT_FAIL      ModuleNotFoundError("No module named 'ClosedLoopDeployment'")
PYTHONPATH_ENV   None
```

`modules/ClosedLoopDeployment/adapter.py` line 35 is `from ClosedLoopDeployment import edges as
_edges` -- the bare, host-only spelling. Nothing anywhere puts `modules/` on `sys.path`: not
`settings.py`, not `manage.py`, not `modules/__init__.py`, and `PYTHONPATH` is unset. The host test
suite resolves it only because it runs from `BRAVO/modules` with `PYTHONPATH=.`.

It is not one import. Eight module-level bare imports across seven files:

| File | Line | Import |
|---|---|---|
| `adapter.py` | 35 | `from ClosedLoopDeployment import edges` |
| `authority.py` | 40 | `from StimOptimizer.routines.lfp_response import ...` |
| `clinic_steps.py` | 71, 311 | `from Biomarkers.routines.analytics ...`, `from StimOptimizer.routines.within_visit ...` |
| `edges.py` | 55 | `from Biomarkers.routines.analytics import ...` |
| `protocol.py` | 42 | `from StimOptimizer.routines import percept_adaptive` |
| `replay.py` | 89 | `from StimOptimizer.routines import percept_adaptive` |
| `three_source_response.py` | 98, 100 | `from Biomarkers.routines import analytics`, `from StimOptimizer.routines import within_visit` |

### 14b. Why it has been invisible

`Server/APIs/DataAnalysis.py` line 919-927 wraps the adapter import and the whole report in one
`try/except Exception` and returns **HTTP 200** with
`{"available": False, "reason": "deployment report error: " + str(e)}`.

So the endpoint answers 200 with a plausible-looking refusal instead of failing. This is exactly the
failure mode decision 67 already recorded once for `stability.py`: a swallowed import error produces
a normal-looking, fast, answerless response.

**It also means decision 67's live browser check may have been reading this, not a genuine empty
state.** That check screenshotted "no calibrated grid is available for this participant yet", which
is the PANEL's own empty message -- and the panel shows that same message whenever
`band_sweep_grid` is absent from the response, which is what an import failure produces. The
screenshot cannot distinguish the two. Recorded as a caveat on that decision, not as a claim that it
was wrong.

### 14c. When it started

`git log -L 35,35` puts the bare import at commit `293a1c98`, **2026-09-04**, "Interface rebuild
with the mode toggle, and seven backend defects the UI lanes found". So the Closed-Loop Deployment
endpoint has been answering `deployment report error: No module named 'ClosedLoopDeployment'` for
five days.

### 14d. Two possible fixes, materially different

1. **Eight double-import spellings**, the pattern CLAUDE.md and `CacheStore/__init__.py` already
   establish and that decision 67 used for `stability.py`. Explicit and local, but edits seven files
   in a module this task was not asked to touch, and every future sibling import must remember it.
2. **One `sys.path` entry for `modules/`**, making true the assumption all eight imports already
   make. One line, no module edits, but it is action-at-a-distance and changes import resolution for
   the whole app.

This is a production module and a real behaviour change either way, so it is put to the PI rather
than chosen here (CLAUDE.md §10 rule 8).
