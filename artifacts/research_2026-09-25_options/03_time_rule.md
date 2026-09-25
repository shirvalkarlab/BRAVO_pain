# Option 3: should the rule that time enters no calculation be revisited?

> Research report, prepared for the PI (Prasad Shirvalkar)
> Researcher: worker-research | Date: 2026-09-25
> Confidence: MIXED — the new evidence is real, but nothing on record yet lets a calendar-time
> effect be told apart from a stimulation-setting effect on this one patient's data.

Terms used below, defined once here and not repeated in a gloss every time: **an "epoch"** is one
continuous stretch of days during which one stimulation setting (rate, pulse width, and the current
on each side) was left unchanged — the code's own name for it. **A "block of time"** means the data
inside one stratum's date range cut into a few roughly-equal pieces in calendar order, used only to
check a model, never to feed it (defined precisely in "What the record already says" below).
**"Pooled"** means one estimate computed across many visits or epochs at once rather than one
estimate per visit. Every other term is defined at first use in the section that needs it.

## 1. The question

Decision 196 (2026-09-17) says: "this patient has had the disease for more than three years, so any
drift in the rating is an effect of the stimulation settings, not of the disease — time is not a
confound and is modelled nowhere." In practice this means: nowhere in the code that predicts this
patient's pain from a stimulation setting does a calendar date, a patient age, or an elapsed-time
number ever appear as an input. The only look at time anywhere in the pipeline is a check that never
feeds back into a prediction: cut a stretch of data into a few blocks in calendar order, see if a
setting that never changed still reads differently in an early block than a late one, and report the
answer as a warning next to the number, never as a correction to it (decision 253, described fully
below).

Since that rule was written, three separate checks on the live data have each found something the
current setting does not explain:

- **Decision 253** found that at one fixed, unchanged setting (55 Hz, 60/160 microsecond pulse width,
  the setting the current-map card's answer rests on, 19 epochs), the pain read at the most-delivered
  current pair fell hard across three blocks of time — from a level about 1.5 points worse than the
  incumbent setting, to about 0.5 worse, to about 0.1 better than it, on the 0-10 pain scale the
  module fits to (p = 0.0006 that this is more than noise; the setting really did not change).
- **Decisions 262 and 264** tried to explain that fall as "the current a while ago still matters"
  (a memory of current, not just the current right now) at six different memory lengths from 1 hour
  to 14 days. None of them predicted the patient's pain better than just using the current in force
  at the moment of each rating; the model that remembers 14 days actually predicts far worse.
  Re-running decision 253's same check with a remembered current in place of the current right now
  still found the pain moving across blocks of time by nearly the same amount (61-63% of the error
  shared by whole blocks, however much memory was assumed). So "the current a while ago" is not the
  missing piece either.
- **Decision 265** found this patient's daily pain rating runs higher on weekends than on weekdays
  within the same week, by about 0.3 points on the 0-10 scale (95% interval 0.12 to 0.48, p = 0.003,
  measured over 58 weeks) — something that has nothing to do with which stimulation setting is
  programmed.

None of this proves the disease is progressing, and the PI's stated reason for decision 196 — this
patient is more than three years past the point where the underlying nerve injury itself would be
expected to still be changing fast — is not contradicted by any of it. What it shows is that
something besides "the current programmed right now" moves this patient's pain report over the
course of weeks, and the platform currently has no way to see that except as a side report that
changes no recommendation. This report lays out precisely what changing that would take, whether the
data can actually support it, and what the honest options are.

## 2. What the record already says

**The rule has already been tried, broken, and pulled back once.** `OBJECTIVE_SPEC.md` §3 records
that an "age" term — a number that grew with how long ago an epoch happened, used to make old data
count for less when fitting the response surface — was added on 2026-09-17 (decision 193) and found
to make no difference at any weight tried, then a genuine calendar-time input was built the same day
and removed the same day on the PI's ruling (decision 194, 196): "time soaked up the settings'
effect." Concretely, measured on this record: settings and calendar time are entangled. In the
45-epoch matrix documented in `OBJECTIVE_SPEC.md`'s 2026-08-29 amendments, days-versus-pain
correlation is -0.61 (pain falling as the months pass) and is itself collinear with days-versus-left-
current at +0.39 and days-versus-frequency at -0.48 — the current went up and the frequency came down
as the months passed, in the same stretch pain came down. A model given both "how long ago" and "what
setting" as inputs has no way, from this design alone, to say which one deserves credit for the
improvement. The project's own fitted-model check found exactly the failure mode this predicts: the
frequency parameter (the setting's own smoothness across different stimulation rates) could not be
estimated at all from the data — the best-fitting value collapsed to treating every rate as
completely unrelated to its neighbours (`routines/surrogate._make_kernel`'s own note; log marginal
likelihood, a measure of how well a value explains the data, is flat between -48.14 and -48.21 across
a wide range of that parameter). The stated reason, confirmed again on 2026-09-23, is that
"frequency levels are separated in time" — the patient was tried at one rate for a while, then
another, never both at once — so a rate contrast and a calendar-time contrast are close to the same
comparison. The fix adopted was to fix that one number by hand as a stated assumption (one octave of
smoothness) rather than let the model guess it, precisely because guessing it would have quietly let
a time trend pass as a rate effect. This is the identifiability problem in miniature, already paid
for once.

**The one check that does look at time only ever warns; it changes no number.** Decision 253 built
`stage1_openloop.calibration_diagnosis`. For each fitted response curve (one per pulse-width pairing,
called a "stratum" — the model does not fit one curve across every pulse width, it fits a separate
one per pulse-width combination and, since 2026-09-14, separately again per stimulation rate inside
that, called a "rate stratum"), the epochs are cut into three roughly-equal pieces in calendar order.
The model is refit leaving each piece out in turn and asked to predict it from the other two. If the
prediction error is mostly explained by which piece an epoch fell in — more than half the squared
miss, and more than chance would produce (a moving-block test, p below 0.05) — the curve is labelled
"moves between blocks of time." If the curve's own uncertainty already covers the miss, it is labelled
"calibrated" or, when it does no better than a plain average, "honest but uninformative: thin data."
This is purely a report card on the fitted curve. It changes no forecast, blocks no recommendation,
and the code's own comment names the ruling behind that: "a warning, never blocking (the PI,
2026-09-22): a failed check refuses nothing and changes no recommendation." Nothing about time enters
`routines/objective.py`'s calculation of the pain score to beat, or `routines/surrogate.py`'s fitted
curve itself — it is entirely a check computed after the fact from the same fitted curve, using the
`_fold_labels_by_time` helper to make the three time-ordered groups.

**A parallel, entirely separate set of read-only reports exists for exactly this kind of question**
(decision 264, the `ControlAnalyses` package: `registry.py`, `snapshots.py`, `stats.py`, `runners.py`,
`time_of_day.py`). It runs offline, saves its answers as plain files (never through the one cache
store that other pages use, and never automatically), and shows a card at the foot of the Biomarkers
and Stim Optimizer pages. It already includes the current-with-memory check (262/264) and the
on/off-switch pain comparison (264). None of it writes back into a recommendation.

**A plausible, much simpler explanation for decision 253's drift has not yet been checked.** The
synthesis document from the day before this one (`research_2026-09-24_SYNTHESIS...`, proposed
analysis 5) lists, as still to do: "was each block preceded by an unusually good stretch?" — asking
whether the fall decision 253 found is regression toward the average after an unusually bad run of
ratings, rather than anything about the setting or the calendar. This has not been run. Section 3
below explains why this matters before any model change is considered.

**One further, independent probe pointed the same direction but is weak.** Decision 252 compared the
device's own automatic power reading (once every 10 minutes) before and after four settings changes
on the side where enough data existed. Only one of the four showed a change bigger than the day-to-
day noise around it (2026-08-12, an increase after the current was lowered); the other three did not.
This is not a time effect by itself — it is compared setting to setting, not against a calendar — but
it shows the device's own signal, not just the pain rating, moves around when settings change, which
is the ordinary thing a working stimulator should do and is not evidence for or against a separate
time effect.

## 3. Evidence and literature

**Tolerance and habituation to DBS is a recognised phenomenon, best documented in tremor, not chronic
pain.** Peters and Tisch's 2021 review (Frontiers in Neurology) surveyed studies of essential and
Parkinsonian tremor patients on long-term thalamic (VIM) stimulation and found the benefit measured
against stimulation being turned off ("on" minus "off") shrinking over time in most studies, by
4-42% depending on the study and the follow-up length, though the authors note the change reaches
statistical significance in only one of the seven studies with adequate data. They separate two
possible causes carefully: comparing the *off*-state severity at two time points measures disease
progression alone; comparing the *on*-state severity conflates disease progression with a possible
separate loss of stimulation benefit; only the *difference between the two* (on minus off, measured
twice) can isolate a true loss of stimulation effect from a general worsening of the underlying
disease. They cite post-mortem and neurophysiological evidence for genuine brain-level adaptation to
chronic high-intensity stimulation as one candidate mechanism, alongside disease progression, cited
alongside each other rather than settled. They do not use or discuss any time-varying statistical
model; their own recommended approach is exactly the pre/post-switch comparison this platform already
partly has in decision 264's on/off analysis, not a continuously-varying time term. A companion
finding often attributed to "Kumar 1997" in second-hand summaries could not be verified as a 1997
paper; see "Unverified" below. A verified, closely related finding is Kumar et al.'s 2003 long-term
follow-up in Neurology, which followed 13 patients with thalamic DBS for 3-5 years and found two of
five essential-tremor patients developed "marked tolerance" to stimulation within two years, while
Parkinsonian-tremor patients in the same series did not show the same pattern — a hint that tolerance
may depend on the underlying disease, which is exactly the PI's own reasoning in decision 196 (a
patient years into a stable disease is a different case from one early in a progressive one), just
applied to a different disease.

**Placebo response and its decline over time is well documented in chronic pain trials generally, but
was not found described specifically for DBS with a stated time course.** Search results point to
individual-differences work on who responds to placebo (predictable in part from resting-state brain
connectivity) and to trial-design guidance that DBS trial staging (implant, then a period with the
stimulator off before it is turned on) is meant to separate the placebo effect of implantation from
the effect of stimulation itself, but no source found gives a specific numeric decay curve for how
fast a placebo response fades in DBS for pain. This is listed as unverified for a specific claim, not
as "no placebo effect exists here" — the mechanism is plausible and cannot be ruled out from what was
found.

**A much older and simpler statistical explanation for an apparent decline is well established: patients
tend to seek or report treatment when their pain is unusually bad, and unusually bad readings tend to
be followed by more ordinary ones even with no effective treatment at all.** Whitney and Von Korff
(Pain, 1992) compared people who sought treatment for jaw pain (chosen because they were doing badly)
against a similar group who were not seeking treatment, and found the treatment-seeking group's pain
fell over time by an amount that tracked how far above average their starting pain was — the same
pattern a group getting no treatment at all would be expected to show from statistics alone. This
is the check the synthesis document's proposed analysis 5 has not yet run on decision 253's own
finding, and it is a materially different explanation from either "the current has memory" or "the
disease/response is drifting": if the block that read 1.5 points worse than the incumbent setting
was itself an unusually bad stretch relative to the visits around it, the fall to 0.5 and then to
0.1 could be ordinary reversion, not tolerance, habituation, or a slow disease change, and needs no
new model of any kind — only the check that has not been run yet.

**Bayesian optimization and Gaussian-process methods built specifically for a response that changes
over time exist and are directly on point for the search this module runs, but every one found
either needs randomised timing or a validated case with known ground truth, neither of which this
record yet has.** Bogunovic, Scarlett and Cevher (AISTATS 2016) build two algorithms — one that resets
the search's memory at fixed intervals, one that gradually forgets old data — for a reward that
follows a Gaussian process whose value drifts step to step according to a fixed, assumed rate of
drift; their proof of how well the method works depends on that assumed drift rate being roughly
right, and the paper (from the parts read) does not address what happens when the arm chosen and the
passage of time are not independent of each other, which is exactly the situation on this record
(settings and calendar time move together). Fleming et al. (PLOS Computational Biology, 2023) built
essentially the identical idea for neurostimulation directly — a time-adaptive Bayesian optimizer that
multiplies the existing shape-of-response kernel by a second kernel over elapsed time, either a smooth
forgetting curve, a repeating (for example once-a-day) curve, or both together — and showed it beats a
standard, non-time-aware optimizer when the true best setting genuinely moves over the course of a
day. Their method was tested where the true, time-varying answer was already known (simulated, or a
setting known in advance to have a daily rhythm); it was not tested, from what was found, on a record
where the tested settings themselves trend across the same span of days the drift is measured over.
That is the missing piece for RCS08: nothing found shows this class of method being validated when
the input (the setting tried) and the clock are as correlated as OBJECTIVE_SPEC's own numbers show
them to be on this patient.

**Sarikhani et al.'s method (Journal of Neural Engineering, 2022), which this module's core search
design already follows for its stopping rule and safety envelope, does not itself model drift across
visits.** Its published description covers within-session, same-day convergence (about 15-18 settings
tried per patient); nothing found in it addresses multi-week non-stationarity or discusses tolerance,
habituation, or regression to the mean as something the algorithm needs to guard against.

**The PI's own earlier work on this same style of pain-DBS platform names tolerance as a known reason
open-loop stimulation loses effect over time**, distinct from tracking real fluctuation in the
patient's pain state — Shirvalkar et al. (Nature Neuroscience, 2023) frames closed-loop stimulation,
driven by a moment-to-moment brain signal rather than a fixed program, partly as a way around this.
That framing is consistent with treating a slow loss of benefit at an unchanged setting as a real,
expected phenomenon worth naming — but it is a motivation for closed-loop control (which senses a
biomarker and adjusts the current itself, on a timescale of seconds), not a specific method for fitting
a slow time trend into the open-loop search this module runs, and the exact wording quoted in second-
hand summaries of the paper's introduction could not be independently confirmed against the full text
(access was blocked); treat the framing as supported by the paper's existence and by widely reported
descriptions of it, not as a verified direct quotation.

**A state-space or hidden-state model of the rating series specifically was tried on this record and
found not to work.** This is not from outside literature but from the project's own prior work, worth
restating here because it answers half of the task's own question directly: the 2026-09-22 research
panel (`research_2026-09-22_SYNTHESIS...`, item B) built and tested a two-state hidden-state model of
the pain ratings (the idea being that the patient might be in one of two underlying states — closer to
a hidden Markov model, a way of modelling a series as switching between a small number of unseen
"modes" — rather than smoothly drifting). On sixty simulated series built from the model's own fitted
parameters, refitting it twenty-nine times recovered wildly wrong answers for how long each state
lasts (1 and 220 ratings, against a true value of 11), and on pure single-state noise with no real
states at all, it invented a forty-five-rating "regime" where the true gap was twenty-two. The panel's
verdict, carried into the synthesis: "not identifiable; record it." This is the closest thing on
record to a direct test of "can a model of a patient's changing state, as opposed to a smooth time
trend, be told apart from noise on this data" and the answer, on that specific model, was no.

## 4. The options

All five options below act on the same two files: `BRAVO/modules/StimOptimizer/routines/objective.py`
(defines the pain number the search tries to beat, currently the patient's own current setting) and
`BRAVO/modules/StimOptimizer/routines/surrogate.py` (fits the curve that predicts pain at settings
never tried, currently `ObjectiveGP`, a fixed-noise Gaussian process — a statistical curve-fitter that
also reports how sure it is at every point — built on a Matern-3/2 kernel, a standard choice of
"how smooth is the true curve" assumption, with one adjustable smoothness number per input dimension).
`BRAVO/modules/StimOptimizer/stage1_openloop.py` calls both and adds the block-of-time check
(`calibration_diagnosis`) and the "does the design actually let two things be told apart"
check (`current_coverage`) described above.

### Option 1 — keep the rule exactly as it is

**What it means.** No code changes. Decision 196 stands: no calendar date, age, or elapsed-time
number of any kind anywhere in `objective.py` or `surrogate.py`, and nothing changes about the
block-of-time check already built (decision 253), which stays a separate warning.

**Implementation.** None.

**Identifiability.** Not applicable — the whole point of this option is to avoid the exact failure
decision 194 already measured (a time input absorbing the settings' own effect, because the two have
moved together throughout this patient's record).

**What it changes on the pages.** Nothing.

### Option 2 — report drift as a diagnostic only (extend what decision 253 already built)

**What it means.** Keep decision 196's prohibition on any time input to a prediction, but make the
already-built check (decision 253) load-bearing in visibility, not in the model: show it wherever a
current recommendation is shown, not only inside the separate research card (decision 264's
`ControlAnalyses`), and add the still-open regression-to-the-mean check (the synthesis document's
proposed analysis 5) alongside it as the same kind of warning.

**Implementation.** `calibration_diagnosis` already runs per stratum and is already carried on the
Stim Optimizer's response (`stage1.audit`, since decision 238). The change needed is small: read that
same field where the current-map card prints a recommended setting, and print one sentence next to it
("this setting's response has moved across the time blocks we can check it against" or "this
setting's response has not been shown to move, but the data are thin") rather than leaving it to a
separate card a clinician might not open. The regression-to-the-mean check would be a new, small
function next to `_reference_setting` in `stage1_openloop.py`, comparing each block's mean pain
against the block immediately before it, with no new free parameter and no new input to the surrogate
— purely descriptive, the same kind of thing `_reference_setting` already computes.

**Identifiability.** Not a concern — nothing new is being estimated from the data; this only reports
what a fold-based check (already computed to check the model, not to build it) found.

**What it changes on the pages.** A recommendation could now come with a plainly worded caveat that it
rests on a curve shown to be unstable over time, without changing the recommended number itself or
blocking anything — the same relationship decision 253's check already has to the rest of the module,
just surfaced more widely.

### Option 3 — add a slowly varying level term (a random walk or a block random effect)

**What it means.** Give the fitted curve a second, additive piece that is allowed to drift slowly
with calendar time — either a smooth random walk (each block's baseline pain wanders a little from
the last one) or a block random effect (one adjustable number per block of time, shared across every
setting, subtracted before the setting's own effect is fit).

**Implementation.** This would touch `routines/objective.py`'s `build_objective` (the pain-versus-
incumbent number every epoch carries) and/or `surrogate.py`'s `_make_kernel`/`ObjectiveGP.fit`. The
project already has the exact machinery needed to remove a nuisance term this way, built for a
different nuisance: decision 241's `stats_utils.CovariateShape`, which currently takes the
stimulation current itself out of a prediction, offers a menu of removal shapes (a straight line, a
3-knot smooth curve, three different kernel-based smoothers, or one level per delivered setting) and
reports how much flexibility each one costs. The same machinery, pointed at calendar time instead of
current, is the natural way to build this option, rather than inventing a second mechanism.

**Identifiability.** This is exactly the failure decision 194 already found and decision 196 was
written to stop. `OBJECTIVE_SPEC.md` states plainly, as a rule the search must never break: "Attribute
the historical time trend to a parameter" is something "the optimizer is not permitted to do." The
reason is measured, not assumed: on the 45-epoch matrix, days-versus-pain correlation is -0.61 while
days-versus-current and days-versus-frequency are also large and same-signed, and the one place a
smoothness parameter was left free to find its own answer across time-separated settings (the
frequency length scale), the answer it found was degenerate — treating every rate as unrelated to its
neighbours because the true smoothness could not be told apart from the passage of time. A time-block
term added today would be estimated from the same design and would face the identical trap: it could
just as easily take credit for (or discredit) a genuine current effect as it could correctly isolate
a real drift. The way out is not a smarter model on today's data; it is different data — repeats of
the *same* setting at *different*, separated points in calendar time, which is what would let a time
term and a setting effect be told apart. That data does not exist yet in enough quantity: most
settings in the matrix were delivered once (`OBJECTIVE_SPEC.md`, 2026-08-29: "of 86 epochs... 50 are
bilaterally active"), and the home hold-and-return schedule and the coverage checks built in decisions
236, 239, 251 and 255 are aimed at collecting exactly this kind of repeat, but for currents, not yet
explicitly for calendar-separated repeats of one setting.

**What it changes on the pages.** Potentially a lot, and in a way that is hard to bound in advance:
subtracting a fitted time-block term before comparing a candidate setting to the setting in force
could move which setting looks best, could change whether a setting counts as "resolved" (beats the
current setting by more than the combined uncertainty), and could change the stopping rule's plateau
condition, all without a reliable way to check whether the move is real or an artifact of the
entanglement above.

### Option 4 — model habituation or tolerance to a setting explicitly

**What it means.** Rather than a generic time term, a term specific to the tolerance idea: the
longer a setting has been continuously in force (its own "dwell time," separate from the calendar
date), the more its benefit is expected to fade, following the pattern Peters and Tisch describe for
tremor.

**Implementation.** The closest existing code is not the time-with-memory check (262/264, which
models memory of *current*, decaying at various rates) but `OBJECTIVE_SPEC.md`'s already-tested
carryover model (2026-08-30 amendment), which modelled each setting's effect as building up while
delivered and then decaying with a time constant after being withdrawn — a first-order kinetic
process, the same style of model, just fit at the scale of minutes within one clinic visit rather than
weeks between visits. A tolerance model would be this same structure at the opposite end of the
timescale: effect *shrinking* the longer a setting is *sustained*, rather than *building up and then
decaying* after a change.

**Identifiability.** The within-visit version of essentially this idea was tried and rejected
outright: profiling the time constant from just over one second to eight hours, the fit got worse
monotonically as the assumed memory got longer, with no point of best fit anywhere except the
shortest one tested — "no evidence of carryover on any timescale tested." A tolerance version at the
much longer, weeks-to-months scale has not been built or tested in this form (262/264 tested memory
of *current*, not a fading of *effect*, which is a different quantity), and testing it properly needs
exactly what option 3 needs: the same setting delivered again after a gap, so a fresh, un-fatigued
response can be compared with a stale one. The synthesis document's proposed analysis 4 — comparing
pain on the way up a ladder of currents against pain on the way back down, at matched currents,
already recorded in the 2025-09-16 titration session (1,588 falling rows, decision 213) — is a cheap,
already-available first test of carry-over/fatigue at the scale of one visit and has not yet been run;
it would be the natural next step before building anything at the multi-week scale.

**What it changes on the pages.** Similar in kind to option 3 (it changes which setting looks best,
and by how much), but potentially easier to explain in plain language ("this setting seems to help
less the longer it has been running") if the identifiability problem above can actually be solved with
new data.

### Option 5 — a time-varying Gaussian process or Bayesian-optimization formulation

**What it means.** Replace the fixed-shape curve-fitter (`ObjectiveGP`, one Matern-3/2 kernel, fit
once on all the data with no forgetting) with one of the published time-aware versions: Bogunovic et
al.'s reset-based or gradually-forgetting search, or Fleming et al.'s approach of multiplying the
existing "how smooth is the response across settings" kernel by a second "how much do we still trust
old data" kernel over elapsed time.

**Implementation.** This touches the same two files as options 3 and 4, but more deeply: the kernel
construction in `_make_kernel`, the fitting and prediction methods on `ObjectiveGP` (`fit`, `predict`,
`loo_predict`), the acquisition functions in `routines/acquisition.py` that decide which setting to
try next, and the stopping rule's plateau and coverage conditions in `OBJECTIVE_SPEC.md` §4, since a
forgetting kernel changes what "no improvement in the last three batches" even means once old batches
count for less. This is a genuine rebuild of the search engine's core, not an addition next to it.

**Identifiability.** The same core problem as option 3, sharper. A forgetting rate (how fast old data
should be discounted) is itself a number that has to be chosen or fit, and Fleming et al.'s own
results show performance is sensitive to whether the assumed forgetting rate or repeating pattern
matches the true one — get it wrong and the method can do worse than a plain, non-time-aware search.
Both published methods were demonstrated where the true, time-varying answer was independently known
(simulation, or a daily rhythm known in advance); nothing found demonstrates either one validated on
a record where the tested settings and the passage of time are as entangled as `OBJECTIVE_SPEC.md`'s
own numbers show them to be here. Building this without first breaking that entanglement (calendar-
separated repeats of the same setting) risks a forgetting kernel that, like the frequency smoothness
number before it, ends up fit to the pattern of *when settings were tried* rather than to any real
change in the patient.

**What it changes on the pages.** The largest of all five options. `TWO_STAGE_DESIGN.md` records 93
tests passing across the module's three core files (plus one skipped) and 312 passing across the
whole test folder, all written and checked against the current, non-time-aware behaviour; this
change would touch the assumptions many of those tests encode. Per this project's own rule (CLAUDE.md
§2.4): a change to the shape of an estimate is a genuine change of substance, not a refactor, and must
not be bundled with anything else, must come with its own before/after equality proof on the live
data (field counts and difference counts, never a rounding tolerance), and needs its own explicit
go-ahead before any of it is built, per the standing rule that a plan being written is not the same as
permission to start (CLAUDE.md §8, rule 8).

## 5. Recommendation and the yes/no question for the PI

**Recommendation: do not reverse decision 196 today, but do not treat this as closed either.** The
new evidence (decisions 253, 262, 264, 265) is real: something besides "the current programmed right
now" moves this patient's pain report over weeks. But every method found in the literature for
handling exactly this — a response surface that drifts while you are searching it — either needs the
timing of what is tried to be independent of the calendar (which nothing on this record is, by the
project's own repeated measurements) or needs an independently known, validated ground truth to tune
against (which a single patient's open-loop record cannot supply). The project has already paid once
for building a time input on data shaped like this (decision 194: "time soaked up the settings'
effect"), and the diagnostic-only path (decision 253) already gives an honest, safe way to say "we
saw something move" without pretending the design can say *why* it moved. The one check that could
cheaply rule out the simplest explanation — regression toward the average pain level, a much older and
better-established statistical pattern (Whitney and Von Korff, 1992) that needs no new model at all —
has not yet been run, and should be, before any of options 3-5 are even considered.

**What should change regardless of the answer below**: extend the diagnostic (option 2) so a
clinician looking at a recommended setting on the page sees, in the same place, whether that setting's
response has been shown to move across the blocks of time the record can check — not buried in a
separate research card. This changes no recommendation and carries none of the identifiability risk
of options 3-5.

**The yes/no question for the PI:**

*Do you want to keep decision 196 exactly as it is today — time enters no calculation anywhere,
including as a required, always-visible check — or do you want the platform to additionally show
decision 253's block-of-time check next to every current recommendation on the Stim Optimizer page,
while changing no recommendation and blocking nothing?*

- **Yes** — keep decision 196 exactly as it is; the block-of-time check stays where it is today, a
  separate research card nobody has to open.
- **No** — extend it: show the check everywhere a current is recommended (option 2), and treat
  building any actual time-varying model (options 3, 4 or 5) as on hold until the home schedule has
  delivered a handful of settings repeated weeks apart at the same rate, pulse width and current,
  which is the specific new data any of those three options would need to be trustworthy.

## 6. Feasibility risks

- **The core risk is the one already measured, not a new one.** Settings and calendar time move
  together throughout this record (days-versus-pain -0.61; days-versus-left-current +0.39;
  days-versus-frequency -0.48, all from `OBJECTIVE_SPEC.md`'s own 2026-08-29 figures). Any model that
  adds a time-related number without first getting calendar-separated repeats of the same setting is
  liable to repeat decision 194's exact failure — crediting the wrong cause, in either direction.
- **Too little data per group once split further.** Most settings were tried once; the richest
  pulse-width-and-rate group on record has 19-22 epochs (`TWO_STAGE_DESIGN.md` §5.1). Splitting those
  further into calendar blocks to fit a time term, on top of the rate-and-current split the model
  already does, leaves very few points to estimate anything reliably from.
- **Regression to the mean has not been ruled out**, and it is a simpler, well-established
  explanation (Whitney and Von Korff, 1992) that would need no model change at all — just the
  already-proposed check. Building a time-varying model before running that check risks mistaking an
  old, generic statistical pattern for a finding specific to this patient or this stimulator.
- **Test and review burden.** `TWO_STAGE_DESIGN.md` records 93 passing tests (plus 1 skipped) across
  the module's three central files and 312 across the whole test folder, all written against the
  current, non-time-aware behaviour. Options 3-5 would need their own equality proof against live
  data (field counts and difference counts, per `ARCHITECTURE_cache_store.md` §5) and, per this
  project's own rule, cannot be bundled with any other kind of change in the same piece of work.
- **Communication risk.** A random-walk or forgetting-kernel term is harder to explain in plain
  language than "compare this setting to what is on now," and the PI has been explicit that anything
  shown to him, and by extension anything a clinician reads off the page, has to be readable without
  reading the code (`CLAUDE.md` §8, rule 12). A time-varying model that cannot be explained in one
  or two plain sentences should not ship even if it is statistically defensible.
- **Clinical risk of getting it wrong in either direction.** If a drifting-response model is built on
  data that cannot actually identify drift, it could recommend abandoning a setting that is genuinely
  working (mistaking the weekend effect, decision 265, or regression to the mean for tolerance), or it
  could just as easily hide a real loss of benefit by quietly absorbing it into a term nobody looks
  at, when the tremor literature's own suggested response to real tolerance — a scheduled change or
  break in stimulation (Peters and Tisch, 2021, citing cycling-stimulation studies) — is a
  fundamentally different clinical action than searching for a new setting.

## 7. References (verified)

1. Whitney, C.W., Von Korff, M. "Regression to the mean in treated versus untreated chronic pain."
   *Pain*. 1992;50(3):281-285. doi:10.1016/0304-3959(92)90032-7. (Citation confirmed via Crossref;
   full text not read, findings taken from the PubMed/publisher abstract summary.)
2. Peters, J., Tisch, S. "Habituation after deep brain stimulation in tremor syndromes: prevalence,
   risk factors and long-term outcomes." *Frontiers in Neurology*. 2021;12:696950.
   doi:10.3389/fneur.2021.696950. (Read via the publisher's PMC copy.)
3. Kumar, R., Lozano, A.M., Sime, E., Lang, A.E. "Long-term follow-up of thalamic deep brain
   stimulation for essential and parkinsonian tremor." *Neurology*. 2003;61(11):1601-1604. (Title and
   the "2 of 5 essential-tremor patients developed marked tolerance" finding confirmed via search
   summaries citing the paper directly; the paper's own full text was not read.)
4. Koller, W.C., Pahwa, R., Busenbark, K., et al. "High-frequency unilateral thalamic stimulation in
   the treatment of essential and parkinsonian tremor." *Annals of Neurology*. 1997;42(3):292-299.
   doi:10.1002/ana.410420304. (Confirmed as a genuine 1997 thalamic-DBS paper; its relationship, if
   any, to a "Kumar 1997" reference could not be established — see Unverified.)
5. Bogunovic, I., Scarlett, J., Cevher, V. "Time-Varying Gaussian Process Bandit Optimization."
   *Proceedings of the 19th International Conference on Artificial Intelligence and Statistics
   (AISTATS)*. 2016;51:314-323. (Method summary taken from the publisher's abstract and search
   summaries; full paper not read.)
6. Fleming, J.E., Pont Sanchis, I., Lemmens, O., Denison-Smith, A., West, T.O., Denison, T., Cagnan,
   H. "From dawn till dusk: time-adaptive Bayesian optimization for neurostimulation." *PLOS
   Computational Biology*. 2023;19(12):e1011674. doi:10.1371/journal.pcbi.1011674. (Author list and
   bibliographic details confirmed via Crossref; method description taken from the publisher's page.)
7. Sarikhani, P., Ferleger, B., Mitchell, K., Ostrem, J., Herron, J., Mahmoudi, B., Miocinovic, S.
   "Automated deep brain stimulation programming with safety constraints for tremor suppression in
   patients with Parkinson's disease and essential tremor." *Journal of Neural Engineering*.
   2022;19(4):046042. doi:10.1088/1741-2552/ac86a2. (Already cited in this repository's
   `OBJECTIVE_SPEC.md`; re-verified independently here via the publisher's page. That page's abstract
   does not itself address non-stationarity or tolerance; this report treats it only as the source of
   the stopping-rule and safe-search-boundary design already adopted in this module.)
8. Shirvalkar, P., Prosky, J., Chin, G., Ahmadipour, P., Sani, O.G., Desai, M., Schmitgen, A., Dawes,
   H., Shanechi, M.M., Starr, P.A., Chang, E.F. "First-in-human prediction of chronic pain state using
   intracranial neural biomarkers." *Nature Neuroscience*. 2023;26(6):1090-1099.
   doi:10.1038/s41593-023-01338-z. (Author list and bibliographic details confirmed via Crossref; the
   full text could not be opened directly, so the specific framing of tolerance as a motivation for
   closed-loop control is reported here as coming from widely repeated descriptions of the paper's
   introduction, not from a directly verified quotation — see Unverified.)

## 8. Unverified

- **"Kumar 1997" as a specific paper reporting tolerance or loss of efficacy in DBS could not be
  found.** Repeated targeted searches (PubMed and general web) turned up no 1997 paper by an author
  named Kumar on this subject. The closest genuine 1997 thalamic-stimulation paper found is Koller et
  al. 1997 (Annals of Neurology, listed above), which does not appear from search summaries to be
  primarily about tolerance. The closest genuine Kumar paper directly reporting a tolerance finding is
  dated 2003 (Neurology, listed above). Either the year in the task's framing is a slight
  misremembering of the 2003 paper, or it refers to a source not found in these searches (for example
  a conference abstract, a book chapter, or a paper indexed under a different spelling). This should
  be treated as an open item rather than resolved in either direction.
- **The exact wording attributed to Shirvalkar et al. 2023** ("DBS...prone to loss of effect owing to
  nervous system adaptation") could not be verified against the paper's own full text; PubMed access
  returned only a verification page during this session. The framing is consistent with how the paper
  is described in multiple independent secondary sources (a UCSF-affiliated press description and
  search-engine summaries of the introduction), but should be treated as a paraphrase of the paper's
  known motivation, not a verified direct quotation, until the full text is read.
- **A specific, numeric account of placebo-response decay over time in DBS for chronic pain** was not
  found. General chronic-pain placebo-response literature exists (cited above only in passing, not as
  a numbered reference, since no single paper with a specific decay time course was identified); this
  remains an open gap rather than a documented absence of the phenomenon.
- **Whether Bogunovic et al. 2016 discuss identifiability when the sequence of settings tried is not
  randomised with respect to time** could not be confirmed one way or the other; only the abstract and
  secondary summaries were available, not the full paper.
