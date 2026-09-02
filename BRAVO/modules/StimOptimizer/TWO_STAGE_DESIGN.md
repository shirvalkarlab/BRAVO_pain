# The two-stage architecture: open-loop search, a gate, then closed-loop policy

Status: implemented and tested. Every number in this document was re-derived from the design matrix
at the time of writing, by running the code described here. Run date 2026-09-02; design matrix
`rcs08_bo_design_matrix.csv`, 86 exposure epochs, declared data horizon 2026-08-12, wash-in 1
minute (the PI-declared 60-second wash-in). The primary outcome resolved to `left_leg_vas`, the
left-leg score, which is the primary outcome for this project because the global rating misses the
stimulation effect that every site-specific score detects.

## 1. Why the device forces two stages

Everything in this module used to model a single flat search over stimulation frequency and
amplitude. The A610 Clinician Programming Guide (M066414C001 Rev B, pp. 34-35) makes that search
represent a decision the hardware will not let a clinician make:

> Pulse width and rate cannot be adjusted once BrainSense has been set up for either hemisphere.

To change either one afterwards, BrainSense has to be removed from the group, which discards the
closed-loop configuration entirely. So closed-loop therapy on this device adapts **amplitude only**,
with rate and pulse width held at whatever values were in force when sensing was configured. There
is a second, independent constraint pushing the same way: a group configured for Adaptive Therapy
has a **higher** minimum stimulation rate than an open-loop group, and the value is 55 Hz. A rate
that is perfectly usable open loop can therefore be unusable closed loop.

Together these mean the open-loop search is not one option among several. It is a prerequisite stage
that must finish and freeze before closed-loop configuration can begin, and freezing is
irreversible in the sense that matters clinically: it forecloses the open-loop search. A flat
optimizer can propose moving the rate at a point in the programme where the rate is already frozen,
which is why the module now has an explicit sequence with a decision point between the halves.

The three constraint values above are not inferred. They live in
`routines/percept_adaptive.py`, each recorded with its source, and that file distinguishes what is
quoted from the labelling from what is PI-supplied. The 8-30 Hz sensing range and the freeze are
quoted; the 55 Hz figure is PI-supplied and consistent with the labelling's stated direction, and it
is marked as such rather than presented as a quotation.

## 2. The architecture

```
                 rcs08_bo_design_matrix.csv
                            |
                            v
        +---------------------------------------+
        | STAGE 1   stage1_openloop.py          |
        | search: rate x pulse width x amplitude|
        | objective: routines/objective.py      |
        | surrogate: routines/surrogate.py      |
        | acquisition: routines/acquisition.py  |
        +---------------------------------------+
                            |
                  FrozenConfiguration
             (rate + pulse width per hemisphere,
              with the evidence and an explicit
              statement of whether it is RESOLVED)
                            |
                            v
        +---------------------------------------+
        | GATE   routines/stage_gate.py         |
        | 4 conditions, or 6 when selected      |
        | biomarker bands are supplied; each     |
        | reported alone, never short-circuited   |
        | must be able to say NO                 |
        +---------------------------------------+
                            |
                  passed?  ---- no ---->  terminal answer, with named reasons
                            | yes
                            v
        +---------------------------------------+
        | STAGE 2   stage2_closedloop.py        |
        | search: threshold mode, sensed band,   |
        | thresholds, adaptive amplitude limits  |
        | validate: percept_adaptive.validate_   |
        |           policy() on EVERY candidate  |
        +---------------------------------------+
```

Two entry points live in `pipeline.py` and neither replaces the other:

- `pipeline.run(...)` is the **original flat entry point, unchanged**. It fits one (frequency,
  amplitude) surface per arm — an arm being one pain site crossed with one hemisphere's amplitude —
  and emits the tables and the five-figure set that existing callers and the service layer expect.
  Its arguments, behaviour and return type are exactly what they were.
- `pipeline.run_two_stage(...)` runs Stage 1, evaluates the gate on the configuration Stage 1
  freezes, and runs Stage 2 only if the gate licenses it. Use it for any question about closed-loop
  deployment.

They are not cross-checks on each other. `run` searches frequency and amplitude jointly over the
whole record; Stage 1 searches rate and amplitude *within pulse-width strata* against a single
common incumbent. They answer different questions and can legitimately prefer different cells.

## 3. Stage 1, the open-loop search

### 3.1 Representing the third dimension

The existing surrogate, `routines/surrogate.ParameterGrid`, is a two-dimensional (rate, amplitude)
grid — 12 rates by 50 amplitude steps, 600 cells — and Stage 1 does not change it. The third
dimension is represented instead as a set of **pulse-width strata**: one (rate, amplitude) surface
per pulse-width level that has at least 8 fitted epochs, which is the same floor the pooled fit in
`routines/plots.build_context` already applies. `ObjectiveGP`, `SafetyGP`, the acquisition functions
and the stopping rule are called as they stand; nothing is re-implemented.

Stratifying rather than fitting one three-dimensional kernel has a real cost — no information is
borrowed between pulse-width levels — and that cost runs in the conservative direction. A shared
length scale across pulse width would smooth the strata towards each other and make a pulse-width
difference look better determined than the design supports. The design gives an independent reason
to prefer no borrowing, reported in section 5.2 below.

### 3.2 One incumbent for every stratum

`routines/objective.build_objective` defines `J_pain` as the primary pain item minus its value at
the incumbent epoch, so `J` is only comparable between two fits that used the same incumbent.
`build_context` derives the incumbent from the most recent epoch of whatever frame it is handed,
which is right for a whole-record fit and wrong here: handed one stratum at a time it would
reference each stratum to its own most recent epoch, and the posterior means could not be compared
across strata at all.

So Stage 1 calls `build_objective` **once** on the whole matrix, with the globally most recent epoch
as incumbent, and fits the surrogate per stratum on that one shared `J` column. On this matrix the
incumbent is epoch 102, 2026-08-12 23:05:21 UTC, at 55 Hz and 100 µs, running 3.5 mA on the left and
3.0 mA on the right.

### 3.3 What "resolved" means, and the correction that mattered most

Resolution uses the criterion already recorded in `pipeline.ArmResult.
surface_can_resolve_its_optimum`: a candidate counts as resolved only when it beats the comparison
cell by more than the standard deviation **of the difference**, with both posterior standard
deviations propagated. Because the joint covariance between two cells is not carried,
`var1 + var2` stands in for `var1 + var2 - 2·cov`; nearby cells on a smooth kernel are positively
correlated, so this overstates the variance and the criterion is strictly conservative. It can
withhold a recommendation it might have supported; it cannot manufacture one.

Two consequences look like bugs and are not. A configuration identical to the setting already in
force can never be resolved, because the gain is zero by construction — retaining the incumbent is
reported as an unresolved default rather than as a positive finding. And a verdict is three-valued:
`None` means the question could not be put to the data, which blocks the gate but tells the
clinician to go and measure rather than that the measurement failed.

**The correction.** Running the real matrix exposed a false positive produced by the stratification
itself, and finding it is the main reason this document exists. `J` at the incumbent is **zero by
construction**. A pulse-width stratum that never delivered the incumbent's *rate* has no data
anywhere near that cell, so its posterior there reverts towards the stratum's own mean. On this
matrix the 140 µs stratum contains no 55 Hz epoch on either hemisphere, and it predicted:

| hemisphere | stratum | posterior at the incumbent cell | its SD | apparent gain | SD of difference | verdict before the fix |
|---|---|---|---|---|---|---|
| Left | 140 µs | +1.6625 | 1.6019 | 2.2800 | 1.7334 | **resolved** |
| Right | 140 µs | +1.6776 | 1.6173 | 2.3048 | 1.7475 | **resolved** |

A definitional zero was reported as 1.66 points worse than it is, and against that fictitious
baseline the stratum's own optimum showed a gain of roughly 2.3 points that cleared the criterion.
Both hemispheres would have reported a resolved rate move on the strength of an extrapolation into a
rate the stratum never ran.

The fix is a support requirement on the **rate axis specifically**, and the reason it is the rate
axis is not arbitrary. The frequency length scale is *pinned* rather than fitted
(`routines/surrogate._make_kernel`, pinned because the marginal likelihood is essentially flat in it
on this design). Borrowing across rates therefore rests on a stated assumption rather than on
anything the data determined, and a comparison that depends entirely on that borrowing is not a
measurement. Amplitude, whose length scale *is* fitted, is not treated this way. A stratum that
never delivered the comparison cell's rate now returns `None`, and both hemispheres' verdicts above
became `None`.

### 3.4 The terminal output

`FrozenConfiguration` is a frozen dataclass, so `cfg.rate_hz = 130` raises `FrozenInstanceError`
rather than quietly changing the plan. The device freeze and the language-level freeze coincide
deliberately: the type system is made to enforce the device constraint. A clinician can proceed on
an unresolved configuration through `stage1_openloop.clinician_override`, which requires a
non-empty reason — an override without a stated reason is indistinguishable from disabling the
check — and which changes no setting and makes nothing resolved. The gate reports it as an override,
never as a pass.

## 4. The gate

`routines/stage_gate.py` decides whether Stage 1's result licenses starting Stage 2. Four
conditions, each evaluated and reported individually, with **no short-circuiting**: the conditions
fail for unrelated reasons, so fixing the first does not predict what the second will say, and a
clinician needs the whole picture in one pass.

| condition | what it requires | why |
|---|---|---|
| `rate_at_or_above_adaptive_minimum` | every frozen rate ≥ 55 Hz | a group with Adaptive Therapy has a higher minimum rate than an open-loop group; below it the policy is not programmable |
| `openloop_choice_resolved` | rate and pulse width resolved, or a recorded override | freezing forecloses the open-loop search, so freezing values indistinguishable from the ones in force spends that option for nothing |
| `adaptive_band_passes_lfp_response` | a band entirely inside 8-30 Hz that responds to stimulation amplitude | outside 8-30 Hz is Sensing Only: the signal can be recorded but a change in it will not change stimulation. And the controller acts on the band, not on pain, with amplitude as its only actuator — so a band that tracks pain perfectly and does not move with amplitude gives the loop no authority |
| `amplitude_limits_inside_envelope_and_under_ceiling` | limits under 4.9 mA and inside the delivered envelope | amplitude does **not** predict side-effect severity in this record (Spearman rho = −0.013, p = 0.79 over 417 non-procedural steps with stimulation on), and only 5 of those rows sit above 4 mA, so above 4 mA is *unknown* rather than safe |

When **selected biomarker bands** are supplied as `SelectedBand` objects, two further conditions are
evaluated and reported separately:

| condition | what it requires |
|---|---|
| `selected_band_inside_adaptive_window` | at least one selected band lies **entirely** inside 8-30 Hz. A pure device question, decided without reference to any p-value |
| `selected_band_statistically_supported` | an **adaptive-capable** selected band clears `SELECTION_ALPHA` on its selection-corrected permutation p-value and, where a q-value exists, survives FDR correction at `SELECTION_FDR_Q`. Both are fixed at 0.05 |

Splitting them is the whole point rather than a convenience. A band can fail either one alone, and
on the current RCS08 plate the two candidates fail for exactly these two different reasons — one is
outside the window whatever its statistics say, the other is inside the window and unsupported. Only
adaptive-capable bands enter the statistical condition, because a band the device cannot use is
already refused by the window and its p-value is beside the point. A band chosen as the best of a
family cannot be tested with the uncorrected p-value of that maximum, which is why the selection
correction is required and why these numbers are an input to this module rather than something it
computes.

The response test is `routines/lfp_response.assess_response`, called as it stands. The gate supplies
candidate bands and interprets verdicts; it computes no statistics of its own. A `ResponseSummary`
may instead supply a verdict established elsewhere — over the whole historical record, every sensing
channel crossed with every stimulation rate, which is a larger family than `assess_response` covers
for one band — and the gate then reports that verdict **with its source named**, never as something
it computed itself. Band power is
computed in the device's own definition — the linear sum of squared magnitude over the band, not a
log and not a mean — because the threshold handed to the device has to be in the units the device
thresholds.

Each condition returns `True`, `False` or `None`. **`None` is not a pass.** Treating an unasked
question as satisfied would license closed-loop configuration on evidence nobody collected. It is
also not a failure, because a failure says the data answered and the answer was no. Both block; they
differ in what the clinician should do next, which is why they are distinguished.

## 5. What the current data says, end to end

Running `pipeline.run_two_stage('rcs08_bo_design_matrix.csv', data_horizon='2026-08-12',
washin_min=1.0)`:

### 5.1 Strata fitted

Seven surfaces were fitted and two strata were skipped, each with 2 fitted epochs at 120 µs, below
the 8-epoch floor. Skipped strata are recorded, never pooled into a neighbouring pulse width.

Three epoch counts appear below and they are deliberately distinguished, because reporting one
under another's name is easy and produces a table that contradicts itself. **Eligible** is every
epoch surviving the amplitude-above-zero and feasibility filters. **On a fitted surface** is what
remains after strata below the 8-epoch floor are skipped. The per-stratum figures sum to the
second, not the first, and the difference is exactly the skipped 120 µs stratum.

| hemisphere | eligible epochs | on a fitted surface | delivered amplitude envelope | epochs per pulse width (all levels) | strata fitted |
|---|---|---|---|---|---|
| Left | 54 | 52 | 1.0-4.8 mA | 60 µs: 22, 100 µs: 8, **120 µs: 2 (skipped)**, 140 µs: 22 | 60, 100, 140 µs |
| Right | 63 | 61 | 1.0-4.5 mA | 60 µs: 19, 100 µs: 12, **120 µs: 2 (skipped)**, 140 µs: 22, 180 µs: 8 | 60, 100, 140, 180 µs |

Per-stratum results, all in NRS points, with `J = 0` at the incumbent and lower better:

| hemisphere | pulse width | epochs | optimum | posterior mean | its SD | gain over incumbent | SD of difference | resolved | incumbent rate delivered here |
|---|---|---|---|---|---|---|---|---|---|
| Left | 60 µs | 22 | 55 Hz, 2.2 mA | +0.3827 | 1.1726 | 0.0000 | 1.6583 | False | yes |
| Left | 100 µs | 8 | 40 Hz, 4.9 mA | −0.7131 | 0.9151 | 0.0359 | 0.9308 | False | yes |
| Left | 140 µs | 22 | 165 Hz, 4.8 mA | −0.6175 | 0.6622 | 2.2800 | 1.7334 | **None** | **no** |
| Right | 60 µs | 19 | 55 Hz, 1.6 mA | +0.2484 | 1.1848 | 0.0015 | 1.6756 | False | yes |
| Right | 100 µs | 12 | 55 Hz, 4.2 mA | −0.2847 | 0.9281 | 0.0020 | 1.3126 | False | yes |
| Right | 140 µs | 22 | 165 Hz, 2.7 mA | −0.6271 | 0.6618 | 2.3048 | 1.7475 | **None** | **no** |
| Right | 180 µs | 8 | 55 Hz, 1.9 mA | +0.8875 | 0.4549 | 0.0018 | 0.6434 | False | yes |

Read the first, fourth, fifth and seventh rows together and a pattern is visible: wherever the
stratum *can* speak about the incumbent cell, the gain over the incumbent is between 0.0000 and
0.0020 NRS points against a difference SD between 0.64 and 1.68. Those are not near-misses. The
surfaces cannot distinguish their own optima from the setting already in force at all.

### 5.2 The rate and pulse width are aliased in this record

A pulse-width effect can only be separated from a rate effect at a rate delivered at more than one
pulse width. Counting delivered cells over the **eligible** epochs, so all pulse-width levels are
represented including the 120 µs one that was too thin to fit a surface:

| hemisphere | rate × pulse-width cells | delivered | coverage | rates with two levels (thin cells counted) | rates with two levels that both clear the 8-epoch floor |
|---|---|---|---|---|---|
| Left | 24 | 11 | 45.8% | 5 | **0** |
| Right | 30 | 12 | 40.0% | 4 | **0** |

Rate and pulse width were moved together in this programme. No rate was ever delivered at two
adequately-sampled pulse widths, so a pulse-width contrast here is partly a rate contrast and no
model unaliases it.

A second, independent view was fitted as a check: weighted least squares on `J`, with pulse width as
a factor, **rate blocked** as a factor, era blocked by calendar quarter, and rows weighted by
`1/obs_var` so a sparsely-rated epoch does not count as much as a densely-rated one. The weighting
matches how the surrogate treats the same rows, which is why weighted rather than ordinary least
squares. Coefficients are relative to the 100 µs reference, which is the pulse width in force;
positive means worse than the reference.

| hemisphere | n | eras | R² | level | estimate | 95% CI | p |
|---|---|---|---|---|---|---|---|
| Left | 52 | 4 | 0.665 | 60 µs | +0.1492 | −2.0396 to +2.3380 | 0.891 |
| Left | 52 | 4 | 0.665 | 140 µs | −0.6216 | −2.6599 to +1.4167 | 0.541 |
| Right | 61 | 5 | 0.629 | 60 µs | +3.6579 | +0.8037 to +6.5121 | 0.013 |
| Right | 61 | 5 | 0.629 | 140 µs | +3.0909 | +0.3096 to +5.8723 | 0.030 |
| Right | 61 | 5 | 0.629 | 180 µs | +1.9865 | −0.3232 to +4.2962 | 0.090 |

Two things must be said about this table rather than left implicit. First, it rests on a declared
data-scope reduction: the 120 µs level (2 epochs, delivered at 145 Hz only) is excluded, and with it
included the design matrix is rank deficient and nothing is estimable at all — 13 of 14 columns
independent on the left, 15 of 16 on the right, with the pulse-width columns computed to be the
dependent ones. The exclusion drops the same levels the stratified surrogate omits, so both views
are fitted on the same rows, and the excluded levels are reported in the output.

Second, **the two views disagree about the sign on the right hemisphere.** The stratified surrogate
prefers 140 µs; the regression puts 140 µs +3.09 NRS points *worse* than the 100 µs reference (95%
CI +0.31 to +5.87, p = 0.030). The two methods adjust for different things, and given that rate and
pulse width are aliased there is no basis for declaring one of them right. A pulse width whose sign
two reasonable analyses disagree about is not a pulse width to freeze, and Stage 1 now reports the
disagreement as one of the configuration's stated reasons rather than reporting only the view that
favours the proposal.

### 5.3 The frozen configuration

| hemisphere | rate | pulse width | preferred amplitude | rate resolved | pulse width resolved |
|---|---|---|---|---|---|
| Left | 40 Hz | 100 µs | 4.90 mA | False | False |
| Right | 165 Hz | 140 µs | 2.70 mA | None (not assessed) | None (not assessed) |

Overall: **not resolved.** Three further caveats are attached to the left-hemisphere setting by the
code itself. The chosen 40 Hz was never delivered at 100 µs — that stratum ran 55, 110 and 125 Hz —
so the proposal interpolates across the pinned frequency length scale. In fact 40 Hz was never
delivered anywhere in this record at any pulse width. And the preferred 4.90 mA is above the highest
amplitude ever delivered on that hemisphere (4.80 mA), so it extrapolates on the amplitude axis too.

### 5.4 The reconciled biomarker plate

The biomarker track reconciled the permutation family with the family each band was actually
selected from (audit item F8 part 2, commit 6001e00, handed over 2026-09-02), and the gate is
evaluated against those numbers rather than against anything inferred here. They are recorded once,
in `routines/stage_gate.RCS08_SELECTED_BANDS`, so this document, the module and its tests cite one
set of values instead of three drifting copies.

**Treat these as provisional.** Three successive corrections have now moved this statistic. They
are the current best estimates, not a settled result.

| outcome | band centre | band at 5 Hz width | r | perm_p before | perm_p reconciled | FDR q | exceeds its null 95th percentile |
|---|---|---|---|---|---|---|---|
| `nrs` | 3.9215 Hz | 1.4-6.4 Hz | −0.5303 | 0.0500 | **0.0809** | — | no |
| `left_leg_vas` | 14.817 Hz | 12.3-17.3 Hz | −0.6343 | 0.6074 | **0.4166** | **0.5055** | no |

**Both candidate bands are now null, and they fail for two independent reasons that must not be
conflated.**

The `nrs` band has lost its nominal significance under selection correction, moving from 0.0500 to
0.0809. But that is not why it is unusable for closed loop. At 5 Hz width it spans roughly 1.4-6.4
Hz, **entirely outside the 8-30 Hz adaptive window**, so it could never have driven Adaptive Therapy
whatever its p-value had turned out to be. That exclusion is a **device constraint** and is
independent of its statistics. The module encodes the independence rather than asserting it: a test
constructs the same band with a hypothetical perm_p of 0.0001 and confirms the window condition
still refuses it.

The `left_leg_vas` band **is** adaptive-capable — 12.3-17.3 Hz sits inside the window — and is
therefore the only candidate the device could have used. It fails on its statistics alone:
perm_p = 0.4166 after selection correction, and FDR q = 0.5055, so it does not survive multiplicity
correction at all. Neither band's observed correlation exceeds its own permutation null's 95th
percentile.

Separately, the LFP-response requirement was run on the historical record and fails: only **3 of 15
channel-by-rate cells show suppression** (one-sided binomial p = 0.996), and the sole bilateral
replication is at 165 Hz. That verdict was computed outside this module, over a larger family than
`assess_response` covers for a single band, so the gate reports it **with attribution** rather than
recomputing something smaller and presenting it as the same claim.

### 5.5 The gate refuses, for six separately reported reasons

Supplying selected bands splits the band question into its device half and its statistical half, so
the gate reports six conditions rather than four and a reader can see exactly which binds:

| condition | verdict | reason, with its number |
|---|---|---|
| `rate_at_or_above_adaptive_minimum` | **FAIL** | the frozen left rate is 40 Hz, below the 55 Hz adaptive minimum. It may be usable open loop; the floor belongs to the adaptive configuration |
| `openloop_choice_resolved` | **FAIL** | not resolved on the left (gain +0.0359 against a difference SD of 0.9308), not assessed on the right |
| `selected_band_inside_adaptive_window` | PASS | 1 of 2 selected bands is inside 8-30 Hz: `left_leg_vas` at 14.82 Hz (12.32-17.32 Hz). `nrs` at 3.921 Hz spans 1.421-6.421 Hz and is excluded by the **device** window regardless of its statistics |
| `selected_band_statistically_supported` | **FAIL** | the only adaptive-capable band is not supported: `left_leg_vas`, r = −0.6343, selection-corrected perm_p = 0.4166, FDR q = 0.5055, does not exceed its own null 95th percentile |
| `adaptive_band_passes_lfp_response` | **FAIL** | fails on the historical record: 3 of 15 channel-by-rate cells suppress, one-sided binomial p = 0.996, sole bilateral replication at 165 Hz (supplied verdict, attributed) |
| `amplitude_limits_inside_envelope_and_under_ceiling` | PASS | Left 1.0-4.8 mA, Right 1.0-4.5 mA, both under the 4.9 mA ceiling — but on **defaulted** limits, so the envelope test is satisfied by construction rather than by a check on a proposal |

Note that the window condition **passes** while still naming the `nrs` exclusion. That is deliberate
and it is the point of separating the two halves: a band inside the window does exist, so the
condition is not what blocks, and the exclusion is attached to the band it applies to rather than
being charged against the gate as a whole. Reporting it as a gate failure would overstate the case.

**Stage 2 did not start, and zero policies were enumerated.** Four of the six conditions block. This
is the correct outcome and not a bug. No threshold was relaxed to change it, and none should be:
`SELECTION_ALPHA` and `SELECTION_FDR_Q` are both fixed at the conventional 0.05 and a test asserts
those values, because a threshold adjusted until the answer changes is not a threshold.

Note what would and would not fix each refusal, since they call for entirely different responses.
The rate floor is arithmetic on a device constraint and is fixed by freezing a rate at or above
55 Hz. The resolution failure needs new data — settings delivered at a rate the comparison stratum
has also seen — and no reweighting of the existing 86 epochs will produce it. The statistical
refusal needs a band that survives its own selection correction, which is a biomarker-discovery
problem and not something this module can move. And the response refusal needs a measurement whose
historical version has already come back negative: 3 of 15 cells is worse than chance in the
required direction. That last one is the substantive finding, and it is independent of everything
the biomarker work has established about which bands correlate with pain, because the controller
does not act on pain — it acts on the band, and its only actuator is amplitude.

## 6. Stage 2, when the gate does license it

Stage 2 takes the frozen configuration as an input it cannot modify, enforced three ways. The
configuration is a frozen dataclass. `run_stage2` **refuses** a caller-supplied `rate_hz` or
`pw_us` outright rather than accepting and ignoring it, because accepting it silently would hide
the caller's misunderstanding of the sequencing. And every emitted policy reads its rate and pulse
width off the frozen configuration, so no proposal anywhere can carry a rate the clinician did not
freeze.

The search space is threshold mode, sensed band centre and width, the threshold values, and the
adaptive amplitude limits with the paused amplitude. Every candidate goes through
`percept_adaptive.validate_policy` and a candidate with any problem is **discarded with its problems
recorded, never clipped into range**. Clipping turns "this policy is not programmable" into "here is
a nearby policy", and a nearby policy is a different clinical proposal that nobody evaluated:
clipping a 6 Hz band centre up to 10.5 Hz substitutes a different control signal, and clipping an
amplitude ceiling down to the declared limit silently discards the reason the higher ceiling was
proposed. A rejection with its reason attached is information; a clipped value is a fabrication
wearing the shape of a result.

Thresholds are handled differently per mode because the device handles them differently. In Dual
Threshold mode the clinician sets an upper and a lower threshold manually, so the two LFP captures
are the natural pair. In Single Threshold mode the clinician sets nothing: the device computes
`0.75 × (upper − lower) + lower` from the two captures, so a Single-mode policy must **predict** the
threshold the device will produce rather than propose one.

To confirm the machinery works when the gate does pass, the right hemisphere was run with
synthetic LFP that is suppressed by amplitude in a 13-17 Hz band, plus a recorded override.
**This is a demonstration of the code path on fabricated spectra and not a result about this
patient.** The gate then passed, and of 630 enumerated candidates 330 were valid and 300 were
rejected: 294 because the band in question does not respond to amplitude, and 6 because a 6 Hz-wide
band centred at 10.5 Hz reaches down to 7.5 Hz and falls outside the adaptive range.

The valid set is ranked, but **by deployability and not by efficacy.** Stage 1 can rank by a pain
objective because pain outcomes exist for open-loop settings in this record. No closed-loop pain
outcome exists for anyone here — the loop has never been run — so there is nothing to fit a
surrogate to and no honest way to predict which valid policy relieves more pain. The ordering uses
the device's own criterion for whether a threshold can be placed at all: the standardised separation
between the two LFP captures. Better separation means the device can put a threshold the signal
reliably crosses in both directions. That is necessary for the loop to function and is not a claim
about benefit. `Stage2Result.ranking_basis` says so, and every summary the module prints repeats it,
because a ranked table invites being read as a preference ordering and this one is not.

## 7. Known limitations

- **The safety model is pulse-width marginal.** One `SafetyGP` is fitted per hemisphere on the whole
  record and shared across strata. Charge per pulse rises with pulse width, so at a fixed amplitude
  a 180 µs pulse delivers more charge than a 60 µs pulse, and one safe set across all strata is
  therefore *optimistic* at the wider pulse widths. It is shared because the safety seed is built
  from the programmed `UpperLimitInMilliAmps` anchors, which carry a frequency and an amplitude and
  no pulse width, so there is nothing in the record to stratify it by.
- **No pulse width is available for the right hemisphere.** The matrix carries `pw_us_Left` only.
  Stage 1 reports the right hemisphere's pulse width as not observed when asked for `pw_us_Right`,
  rather than assuming the two sides match; in the run above the left column was used for both,
  which is an assumption the matrix cannot check.
- **The resolution criterion is conservative by a known amount.** `var1 + var2` stands in for
  `var1 + var2 − 2·cov`. Predicting both cells jointly with the full covariance would tighten it.
  This is a documented next step, not a silent approximation.
- **The real-matrix regression test skips by default.** The canonical design matrix lives in the
  project's artifact store rather than in the repository, so
  `test_the_real_design_matrix_cannot_proceed_to_closed_loop` skips unless
  `STIMOPT_DESIGN_MATRIX` points at a copy. It has been run against the real file and passes; the
  observed verdicts are recorded in its docstring. A structural fixture reproducing the record's
  aliasing and incumbent placement covers the same end-to-end behaviour unconditionally.
- **Not assessed, and deliberately so.** No calibration of the stratified surfaces (no
  leave-one-era-out on a per-stratum basis). No sensitivity of the stratum floor: 8 epochs is the
  floor the pooled fit already used and it was not swept. No test of whether a three-dimensional
  kernel over rate, pulse width and amplitude would fit better than the strata, because that would
  require changing `routines/surrogate.py`.

## 8. Files

| file | role |
|---|---|
| `stage1_openloop.py` | the open-loop search; `FrozenConfiguration`, `run_stage1`, the pulse-width design audit and contrast, `clinician_override` |
| `routines/stage_gate.py` | the gate conditions, `SelectedBand`, `ResponseSummary`, `LfpEvidence`, `evaluate_gate`, and the reconciled `RCS08_SELECTED_BANDS` / `RCS08_RESPONSE_SUMMARY` |
| `stage2_closedloop.py` | `ClosedLoopPolicy`, `enumerate_candidates`, `run_stage2` |
| `pipeline.py` | `run` (original, unchanged) and `run_two_stage` (new) |
| `tests/test_stage1.py` | 24 tests |
| `tests/test_stage_gate.py` | 41 tests |
| `tests/test_stage2.py` | 29 tests, 1 of them skipped by default |

These three files together: **93 passed, 1 skipped** (`PYTHONPATH=. python -B -m pytest
StimOptimizer/tests/test_stage1.py StimOptimizer/tests/test_stage_gate.py
StimOptimizer/tests/test_stage2.py -q -p no:cacheprovider -W ignore`). The one skip is the
real-matrix end-to-end test, which needs `STIMOPT_DESIGN_MATRIX` to point at a copy of the CSV.

The whole suite stands at **312 passed, 39 skipped** (`PYTHONPATH=. python -B -m pytest
StimOptimizer/tests -q -p no:cacheprovider -W ignore`), against a baseline of 203 passed and 15
skipped. That difference is larger than the 94 tests added here because other tracks added tests to
their own files concurrently — `tests/test_safety_ordinal.py` and `tests/_ordinal_analysis_driver.py`
appeared during this work and are not mine. Nothing previously passing changed.

Both routes for supplying the gate's biomarker inputs are exercised, and this is worth naming
because it was a real regression. `selected_bands` and `response_summary` reach the gate either as
named arguments of `run_two_stage` or inside `gate_kwargs`. Promoting them to named arguments while
still forwarding `gate_kwargs` unchanged made the older style raise "got multiple values for keyword
argument", and no test caught it because the end-to-end test used the new style and the gate's own
tests call `evaluate_gate` directly. The two are now merged rather than splatted, supplying the same
key by both routes is an explicit error rather than a silent precedence rule, and a test asserts the
two styles produce identical condition names and verdicts.
