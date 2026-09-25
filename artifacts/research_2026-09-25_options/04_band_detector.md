# Option 4: the research band detector — three open choices for the PI

> Research report, prepared for the PI (Prasad Shirvalkar)
> Researcher: worker-research | Date: 2026-09-25
> Confidence: MIXED — the statistics machinery to answer this already exists and runs on live data;
> the open question is which inputs to feed it, and the record so far gives one weak, unreplicated
> lead and no result that clears its own comparison against chance.

**Terms used throughout, defined once here.** A **band** is a roughly 5 Hz-wide slice of the brain's
electrical frequency spectrum — this platform already reads 22 such bands, spaced from about 8.5 to
29.5 Hz, on each of six sensing-contact pairs. **"Threshold"** below means only one thing, by this
project's own house rule: the power level at which the Percept RC device switches the delivered
current up or down. It never means a statistical cut-off. A statistical cut-off is called a **cut
point** here instead. **AUC** (area under the curve) is a score from 0 to 1 for how well a number
tells two states apart by ranking alone — 0.5 is a coin flip, 1.0 is perfect separation; this
project's own rule (decision 8) is that AUC is reported signed, so a score of 0.30 means the model
got the direction wrong on data it had not seen, and is a failure, not a success read backwards.
**Ridge regression** is a way of predicting one number from many inputs at once (here, all 22 bands
together) that shrinks each input's own weight, so the model cannot simply memorise noise when it
has almost as many inputs as data points. **"Held out in blocks of time, with a gap"** means a model
is tested only on a contiguous stretch of time it never trained on, with the ratings on both sides of
that stretch also removed from training — because two pain ratings filed minutes apart are nearly the
same measurement, and a model trained on the neighbours of its own test data has already seen most of
the answer. The **shuffled-data comparison (null)** scrambles the pain ratings in a way that still
lets nearby ratings look alike, the way real pain drifts slowly day to day, then asks how well the
same model does on the scrambled version — if the real result does not clearly beat this, the model
may only be reading "today's pain looks like yesterday's," not anything about the brain.

---

## 1. The question

This project already has code that reads every band on a sensing-contact pair at once, with a
regression model, and reports four things side by side: how well the stimulation current alone
predicts pain, how well the bands do, how well the bands do once the current's own contribution is
statistically taken out of them, and how that compares with a shuffled-data comparison that would
score well by chance alone if pain simply drifts slowly (`Biomarkers/routines/confound_diagnostic.py`,
built under decision 240, extended under decision 241). A parallel, offline package saves the results
of runs like this so a clinician can read them later without recomputing anything
(`ControlAnalyses/`, decision 264).

The design under review adds a second, much simpler reading beside that one: a **device-shaped
detector** that looks at exactly what the Percept RC device itself could look at — one band, one
switching value, and the device's own timing (how long it averages a reading before deciding, and how
long a reading must persist before the device treats it as a real change). Comparing the two answers
the question this project has asked from the start: is a real signal being thrown away by the
device's simplicity, or is the more flexible research model only finding patterns a fielded device
could never use anyway? A fourth reading is proposed alongside the three that already exist: what the
bands say about pain during a stretch when the stimulation current never changed at all, so there is
no current to take out statistically — a much smaller, but much cleaner, test of the same question.

Before any of this is built, three choices are open, listed here as the assignment gave them: (1)
which pain ratings to use — the app-based diary alone, or also the clinician's paper ratings taken
during a clinic visit; (2) how to describe pain as an outcome — a high-versus-low split with the
middle dropped, or the pain score itself, kept continuous; (3) whether to apply the device's own
timing limits (how long it averages a signal, how long a change must persist) from the very start of
the analysis, or only at the end, as a check on whatever the research model finds.

## 2. What the record already says

**The three-reading version of this already ran, on live data, twice, with different answers each
time — and the difference between the two runs is itself the most important thing on the record.**
Decision 240 first ran this check matching each pain rating to the nearest recording within 60
*seconds*. On the left sensing-contact pair used for the current clinical candidate band (called
"L 1-3+" in this project, meaning the two contacts flanking the left lead's active contact), with 53
matched ratings: the stimulation current alone scored 0.879, every band together scored 0.701 (a
shuffled-data comparison's top value was 0.713, so this did not clearly beat chance), and the bands
with the current's contribution taken out scored 0.526. Read plainly, at that matching window the
current alone was the strongest single explanation and nothing about the bands beat chance once
current-only prediction was accounted for.

Then decision 262 found the first run had used the wrong matching window — it had matched to
recordings within 60 *seconds*, when the page's own default is 60 *minutes*, which is generous enough
to keep far more ratings. Re-run at the page's real 60-minute window: with 201 ratings matched to 30
seconds of signal, the current alone scored 0.600, every band scored 0.722 (a shuffled-data top value
of 0.716 — just outside it), and the bands with current taken out scored 0.681 (inside the 95th
percentile of the shuffled comparison, so not distinguishable from chance). With 187 ratings matched
to 60 seconds of signal, the current alone scored 0.708, every band scored 0.743 (comparison top value
0.673 — clearly outside it), and the bands with current taken out scored 0.683 — this time *outside*
the shuffled-data top value, with an uncorrected two-sided chance of 0.04 of seeing that by luck alone
if nothing real were there. The other five sensing-contact pairs on this participant stayed inside
their own shuffled-data range throughout (the right pair used for the other candidate band, "R 0-3+",
scored 0.445 on bands and 0.357 on current alone with 459 matched ratings — no signal detected by this
test at all). **This one uncorrected result (p = 0.04, on one of twelve pair-and-length combinations
tried across the two runs) is the entire positive evidence on the record today that anything survives
taking the stimulation current out of the bands.** It has not been corrected for how many combinations
were tried, and it has not been repeated on an independent stretch of data.

A separate, related finding narrows what that result could mean even if it holds up. The panel review
of 2026-09-22 (decision 232) found that on this same left pair, the specific bands (21.5–26.5 Hz) that
looked like they rose with pain on the page's own correlation grid lose their "wholly positive"
interval once the stimulation current in force is statistically taken out of them — the same
operation the confound check performs. So the two checks agree with each other in direction (current
matters a great deal here) but the confound-diagnostic reading is the more forgiving of the two: it
lets the removal take a curved shape (a shape that can turn over, not just a straight line, decision
241), while the correlation-grid check the panel used takes current out as a straight line only. The
PI's ruling on this exact tension (decision 233, answer 2) is that a band no longer being "wholly
positive" after current is removed does not by itself disqualify it — the removed reading is shown
*beside* the plain one, descriptively, and never re-selects a band or changes a verdict on its own.

**Two more record facts bound how ambitious this design can be today.** First, the device's own
sensing rule (decision 217: a sensing pair must be the two contacts immediately flanking the lead's
active stimulating contact) currently allows only two sensing-contact pairs on this participant at
all — "L 1-3+" on the left and "R 0-3+" on the right — and, as of the most recent count on the
record, *neither* has a single band that clears even the simplest existing screen (a band that falls
as current rises and rises with pair, decision 199, loosened to "supported" by decision 210): zero of
fifty contact-and-rate combinations are usable today (decision 217, restated in decision 243's live
proof). So a device-shaped detector built today, on the two pairs the device would actually let a
clinician sense from, starts from zero usable bands, before any of the three choices below are even
made. Second, one of the earliest, cleanest-looking findings on this record — the left 21.5–25.5 Hz
band family rising with pain during the first five weeks after implant, while both sides were off
(decision 262a, confirmed with the implant-date fix in decision 264) — is explicitly written up as
"a lead to confirm, not an established result," because it sits inside one 25-day stretch, right after
surgery, and the same bands read the *opposite* sign in the very next stretch, where a different trend
(current rising on the right, pain falling) was also present at the same time. That is the shape of
every finding on this record so far: real, measured, and not yet strong enough to act on.

## 3. The three choices

### Choice 1 — which pain ratings to feed the detector: the app diary alone, or also the clinic paper
ratings

**What each source is.** The app diary is REDCap: a web survey the patient fills out at home,
whenever they choose, roughly once a day. The clinic paper ratings are the "clinic sheet" — a paper
or verbal 0-to-10 rating the clinician writes down by hand once a minute, during a visit, while
*deliberately* stepping the stimulation current up and down to find a comfortable setting (a
"titration ladder"). This project has already built one shared function that adds the clinic sheet
ratings to the app diary when asked (`_merge_clinic_sheet_ratings`, decision 258, itself built on
`Biomarkers/routines/sheet_ratings.py`, decision 186); it is switched off by default everywhere it is
used today, and every rating it adds is tagged so a reader can tell which ratings came from which
source.

**Evidence for including more, from outside this project.** Retrospective and clinic-based pain
reports are known to be biased by the patient's pain *at the moment of reporting*, not just by what
actually happened. Haase (2023), comparing one week of daily diary pain against a single retrospective
questionnaire in 94 chronic pain patients, found that current pain at the time of answering was the
strongest predictor of the recalled average (standardised beta 0.441, p < 0.001) — people in more
pain when asked recalled a worse week than the diary said, and about 37% of patients differed from
their own diary average by a full point or more on a 0-to-10 scale. Jamison, Sbrocco and Parris (1989)
found the opposite direction of the same effect in a diary-monitoring study: patients who were pain-
free at the time of recall *underestimated* their pain over the preceding days, and those in high pain
overestimated it. Stone, Schwartz, Broderick and Shiffman (2005) describe the general mechanism as a
"peak/salience" memory heuristic: how *variable* a person's pain was during a period, not just its
average, shapes what they later recall as typical. Applied here: the clinic sheet ratings are not a
neutral second copy of the same measurement — they are collected in a setting (a visit, under active
titration, with a clinician present) that differs systematically from the setting REDCap measures
(daily life, patient alone, no stimulation change in progress), so combining them is combining two
different instruments, not just adding sample size.

**Why the clinic sheet ratings are a poor match for exactly this detector, more than for other uses
on this platform.** The module's own documentation states this plainly: every clinic-sheet rating "was
taken while current was being stepped on purpose, so band power and pain both move with the ladder."
That is precisely the confound this detector exists to remove. Feeding the clinic sheet ratings into
the "bands with current taken out" reading would add rows where the removed quantity (current) has by
far its largest and fastest variation in the whole record, collected once a minute; whatever shape the
current's effect is given (see Choice 3 and decision 241), a curve fitted mostly to fast, deliberate
current changes is not the same fitted quantity as one fitted mostly to REDCap's slow, ambulatory
current changes, and mixing the two inside one model risks the curve fitting the clinic visits' fast
dynamics and then being applied, wrongly, to the ambulatory rows. The clinic sheet ratings also add
much less independent information than their count suggests: the module's own numbers show they
roughly double the count of ratings on the thinner sensing pairs (91 to 168 on one pair, on this
project's own count), but arrive one a minute inside a session, so "168 ratings" may be closer to
fifteen or twenty sessions' worth of near-duplicate information — the same clustering problem this
project's own block-bootstrap and block-shuffle statistics already correct for elsewhere (decision
183), but which this detector's `purged_time_blocked_folds` gap is not designed to size correctly if
fast clinic-visit ratings are mixed in with slow ambulatory ones (see Feasibility risks).

**Recommendation: REDCap only, for the primary reading; clinic-sheet ratings only as a clearly
labelled, separate secondary reading, never merged into the same fitted model.** The two data sources
answer two different questions. REDCap alone answers "does this band track ambulatory pain, at
whatever current happens to be in force that day" — the question a device that will run unattended at
home actually needs answered. The clinic sheet answers "does this band respond when current is
changed on purpose" — a real and useful question, but a different one, closer to the exploratory
ladder already designed for a live visit (decision 230/236/237) than to a passive detector. Running
the clinic-sheet ratings through the *same* four-reading detector, reported as its own row rather than
merged in, would let a reader see whether the two sources agree in direction without letting the
clinic sheet's confound-by-design contaminate the ambulatory answer. **Trade-off:** REDCap alone keeps
the analysis honest but starts thin — as few as 53 to 201 ratings depending on the match window
already tried, and the confound_diagnostic module's own floor (`MIN_ROWS = 40`) will refuse to answer
at all below that on some pairs and lengths. Adding the clinic sheet buys real sample size on the
thinner sensing pairs, at the cost of contaminating the exact thing being measured.

### Choice 2 — how to describe pain as an outcome: a high/low split with the middle dropped, or the
score itself

**What the platform does today.** Everywhere this platform screens a band against pain with an AUC
score, it first turns the continuous pain score into a high/low label by a tertile split: the bottom
third of ratings become "low," the top third become "high," and the middle third is dropped entirely
(`Biomarkers/routines/analytics.py`, `_binarize_labels`; used by the existing heat-map screens and by
`confound_diagnostic.pre_build_diagnostic`'s own label). This is the design the research detector
inherits by default.

**Evidence against doing this, read directly for this report.** Cohen (1983), in the foundational
paper on this exact question, shows analytically that splitting one continuous variable at its
midpoint — keeping *all* the data, just labelling it high/low — already reduces the statistical power
of a test for a real, medium-sized relationship (a correlation of 0.30) from 0.78 to 0.57 with 80
cases: the same loss as if 30 of those 80 cases (38%) had simply been thrown away. Splitting *both*
variables in a relationship this way, which is closer to what an AUC screen against a dichotomised
pain label does, costs the equivalent of throwing away 60% of the cases. Altman and Royston (2006),
writing for a clinical audience in the BMJ, make the same point about dichotomising a continuous
measurement more generally: it discards information, and the specific point at which the split is
made is often close to arbitrary. **This project's own design goes one step further than a plain
median split, and that step has its own name and its own dedicated critique.** Dropping the middle
third and keeping only the extremes is called the "extreme groups approach" in the measurement
literature. Preacher, Rucker, MacCallum and Nicewander (2005), read directly for this report,
distinguish two versions of it. True extreme-groups sampling — deciding *in advance* to collect data
only from people at the extremes — can genuinely increase the power of a specific test (a comparison
of two group means), and the classic "27% rule" (keep roughly the top and bottom quarter) comes from
exactly that calculation. But this platform's design is the *other* version, which the same paper
names "post hoc subgrouping": the continuous value is already measured for every rating, and only
*afterwards* is the middle third thrown away before the correlation or AUC is computed. The paper's
own words on this design: post hoc subgrouping "does not improve cost-efficiency," because the data
were already collected, and it "usually lowers the power of subsequent hypothesis tests" relative to
using the full, continuous data — the opposite of the reason a tertile split is usually chosen. The
authors' explicit recommendation: "we strongly recommend against the common practice of applying
tertile and quartile splits to otherwise full data sets."

**Why the platform still does it this way, and why that reason does not apply equally everywhere.**
The tertile split earns its keep on the existing single-band screens because it produces an AUC, and
an AUC has a direct, plain-English reading a clinician can act on ("this band tells high pain days
from low pain days X% of the time") that matches how a device threshold actually behaves — a device
switching value is itself a single cut point on a continuous power reading, so *some* dichotomisation
is unavoidable at the device end no matter what the statistics do. That argument holds for the
device-shaped tier of this design, which really is modelling a switch. It does not hold for the
research tier, which uses a ridge regression that can predict the continuous pain score directly, and
for which Spearman rank correlation (already implemented and used elsewhere in this project's own
`ControlAnalyses/stats.py`, `spearman_within`) gives a plain, ranked-based reading without discarding
the middle third of the data or assuming pain ratings are measured on an equal-interval scale — a
concern independently raised by Hjermstad et al. (2011)'s systematic review of numeric, verbal, and
visual pain scales, which recommends the 0-to-10 numeric rating scale for its usability but treats it,
and the visual analogue scale this project also fits, as ordered categories to be handled with rank
statistics rather than assumed to be a true interval scale.

**Recommendation: keep the score continuous for the research tier (Spearman correlation and a
continuous ridge-regression prediction, scored by held-out R-squared or a rank correlation on held-out
predictions, not by AUC); keep a cut point only for the device-shaped tier, where it is unavoidable,
and place that cut point at the level a real switching value would use rather than at a data-driven
tertile.** **Trade-off:** the continuous reading is more efficient with the small samples this record
has (avoiding Cohen's demonstrated power loss and the extra loss from post hoc subgrouping) and answers
a more honest question for a research tool, but it gives up the AUC's simple "percent of the time it
tells them apart" reading that this project's other pages already use, so a result from this detector
will need its own short explanation the first time it appears on a page, rather than reusing the
existing AUC language verbatim.

### Choice 3 — apply the device's own timing limits (how long it averages, how long a change must
last) from the start, or only as a check at the end

**What the device's own timing is.** This project's own device documentation
(`DEVICE_percept_rc.md` §2, sourced from the Medtronic white paper and cross-checked against the
clinician's own programming tablet) gives the two adaptive modes' timing: Dual Threshold averages its
reading for 1200 milliseconds before reacting and needs a reading to persist for 1200 milliseconds
before "onset" counts, with a slow 2.5-minute ramp up and 5-minute ramp down; Single Threshold
averages for 100 milliseconds and reacts in 250 milliseconds. Separately, the design rule this project
already recommends for setting a real switching value (decision 150, decision 169) uses its own
chosen, in-range values: averaging over 3 seconds, and requiring a reading to persist for up to 30
seconds (the largest onset value a clinician can actually enter on the tablet) before counting it as a
real change. Today's own programmed setting on this participant runs onset 30 seconds, transitions 4
seconds, averaging 30 seconds, and blanking 30 seconds.

**Evidence for building the timing in from the start.** The two large trials that tested exactly these
two device modes at scale — ADAPT-PD (Stanslaski et al., 2024; Bronte-Stewart et al., 2025) — ran
Single and Dual Threshold with their real timing throughout, not as a post-hoc check, and even so had
to exclude roughly one enrolled patient in eleven for signal quality before the algorithm could be
trusted at all (a fact already surfaced by this project's own prior literature report on tonic
stimulation, `research_2026-09-24_3_tonic_current_and_single_threshold.md`). Velisar et al. (2019),
who designed Dual Threshold's slow ramp specifically for slower, medication-timescale symptom changes
rather than instant reactions, built the timing into the controller's design from the start, not as an
afterthought. The reasoning transfers directly: a detector that ignores timing and then checks
compatibility at the end can find a pattern that only exists at a length or speed the device could
never actually run at, and would not discover that until the very last step — after already reporting
a positive result.

**Evidence for the opposite order — explore broadly first, then check device compatibility.** This
project's own record already shows why: the single positive-looking finding on the record today (the
p = 0.04 result described in Section 2) came from a 30-to-60-second matching window and 30-to-60
seconds of averaged signal, chosen because that is what happened to be available, not because it
matches any one device timing setting. If the device's exact averaging and onset rules had been
imposed from the very first pass, that finding — weak as it is — might never have been looked for at
the length where it appeared. A research tool's job in this project is explicitly to look everywhere
first (this is the entire premise of the "research detector" tier, and of the exploratory 252-setting
search already run and reported honestly as a search rather than a confirmed finding, decision 229).
Constraining the search space before looking is how a real effect at an unanticipated length gets
missed, not how one gets confirmed.

**Recommendation: run both, explicitly, as two different rows of the same detector, not as one choice
between them.** The **research tier** should keep exploring freely across window lengths (this project
already tests several: 1, 3, 5, 10, 15, 20, 30, 45, and 60 seconds, decision 170) with no device-timing
restriction, because that is what a search is for. The **device-shaped tier**, by definition, should
build the device's real timing in from the very first pass — a 3-second averaging window and a
persistence requirement before a crossing counts, per the design rule this project already recommends
elsewhere (decision 150) — because its entire purpose is to answer "could a fielded device see this,"
and a device-shaped answer without device timing is not answering that question at all. The two tiers
are already meant to be read side by side; this makes that comparison mean what it is supposed to
mean. **Trade-off:** running both means the device-shaped tier will very likely score lower and find
less than the research tier, on this small a record — that is not a bug in the design, it is the
answer to the question the whole two-tier design exists to ask, and reporting it honestly (rather than
picking the more encouraging of the two orders) is the entire point.

## 4. Build specification

Nothing below writes to the cache store or to any page a clinician sees today. Every run goes through
the existing offline runner pattern (`python3 -m modules.ControlAnalyses.run <key> [participant]`,
decision 264) and saves one JSON record per run (`ControlAnalyses/snapshots.py`) — never a per-request
computation, and never a stored cache entry, matching this project's own standing rule that a control
analysis is a saved record, not a live page feature. **This is a specification for the PI to approve
before any of it is built** — plan approval is not execution authority on this project (`CLAUDE.md`
§8, rule 8), and nothing here should be read as already built.

**New module:** `BRAVO/modules/ControlAnalyses/band_detector.py`, following the existing file's own
pattern (`runners.py`, `stats.py`).

**Reused, unchanged:**
- `Biomarkers/routines/confound_diagnostic.py` — `all_bands_auc` and `pre_build_diagnostic` already
  compute exactly readings 1 to 3 (current alone, every band, bands with current taken out), already
  held out in blocks of time with a gap, already compared with a shuffled-data null that keeps pain's
  own persistence, already reported without folding the score. `ControlAnalyses.runners.run_current_
  explains` already calls this end to end and saves the result (decision 264's analysis 2,
  `current_explains`). **This piece needs no new code**, only new arguments (see below) for Choices 1
  to 3, and a continuous-outcome variant for Choice 2.
- `Biomarkers/routines/stats_utils.py` — `CovariateShape` (the shape the removed current is allowed
  to take: a straight line, a curve, or one of three kernels; spline is the current default and
  should stay the default here too, per decision 241's own live comparison on this record),
  `purged_time_blocked_folds` and `block_length_for` (the held-out-blocks machinery and its
  automatically measured gap), `circular_block_perm_matrix` (the shuffled-data null generator).
- `ControlAnalyses/runners.py` — `_ratings` (REDCap-only pain ratings, already applies the implant-
  date cutoff, decision 260), `_stream` and `_side_steps` (the settings history, for finding
  unchanged-setting stretches), `stretches` (already finds runs where a side sat at one current for a
  minimum number of days, extend it to non-zero currents for the fourth reading, see below).
- `ControlAnalyses/stats.py` — `spearman_within` and `day_resampled_rho` (continuous-outcome
  correlation with a 95% interval built by resampling whole California days, for Choice 2's
  continuous reading and for the device-shaped tier's single-band screen), `bh_q` (the
  Benjamini-Hochberg correction already used on the existing 22-band heat-map screens, decision 63,
  reused here across the device-shaped tier's bands).
- `Biomarkers/routines/stim_current.py` — `current_in_force_for_reports` and `hemisphere_of_channel`,
  for the stimulation-current covariate.
- `Biomarkers/bravo_service.py` — `_band_time_sweep_power_by_seconds` (the existing report-to-
  recording matcher, with its `tol_s`, `match_direction`, and `allow_window_reuse` arguments) and
  `_merge_clinic_sheet_ratings` (Choice 1's optional secondary reading, called with the switch on,
  never merged into the primary reading per the Choice 1 recommendation).
- `DecodeCommon/data_start.py` — `data_start_s` and `keep_from`, the implant-date cutoff (decision
  260), applied to every input the same way `ControlAnalyses.runners._ratings` already applies it.
- `DecodeCommon/device_ranges.py` — the timing constants for the device-shaped tier (`AVERAGING_
  RANGE_MS`, `ONSET_RANGE_DUAL_MS`), and this project's own already-adopted design-rule defaults
  (decision 150: 3-second averaging, 30-second onset) as the specific numbers the device-shaped tier
  uses, rather than inventing new ones.

**New code needed:**

1. **A fourth reading, `same_setting_auc(uid, channel, seconds, ...)`.** Extend `ControlAnalyses.
   runners.stretches` (already restricted to a *side at zero milliamps*) to also find stretches where
   a side sat at any one *non-zero* current, plus rate and pulse width, for at least a stated minimum
   number of days (reuse the existing `MIN_STRETCH_DAYS` and `merge_h` visit-merging logic verbatim —
   a clinic visit's brief step should not split a real stretch, exactly as decision 264 already found
   and fixed for the zero-current case). Inside the longest such stretch for each sensing pair, since
   current never moves there is nothing to take out — this reading is simply "every band, read out of
   sample, on rows where the current genuinely never changed," using the same `all_bands_auc` function
   with `covar=None`. Report it beside the other three, with the stretch's own start and end dates,
   its length in days, and how many ratings fall inside it — and refuse to answer, by name, rather
   than print a low-confidence number, when fewer than `confound_diagnostic.MIN_ROWS` (40) ratings
   fall inside the longest available stretch, which decision 253's own count of clinic epochs suggests
   will happen on more than one sensing pair on this record.

2. **The device-shaped tier, `device_shaped_reading(uid, channel, band_center_hz, ...)`.** For one
   named band and one sensing pair: build the band's power series at the device-shaped tier's own
   timing (3-second averaging window, matching the design rule's own adopted default, decision 150;
   apply the onset rule as a persistence filter — a reading only counts as "crossing" a candidate cut
   point once it has stayed on one side of it for the onset duration, mirroring the real device's
   onset logic described in `DEVICE_percept_rc.md` §2 — using `DecodeCommon.device_ranges` for the
   exact numbers rather than a value invented for this task). Compute the same four readings on this
   one band alone: current alone (already available via `confound_diagnostic.all_bands_auc` with a
   one-column `X`), the band itself, the band with current taken out (`CovariateShape`, same default
   spline shape as the research tier, so the two tiers differ only in band count and timing, not in
   how current is removed), and the band during the longest unchanged-setting stretch. Because this
   tier reads one band at a time, run it across all 22 centres per sensing pair and apply the
   Benjamini-Hochberg correction already used elsewhere on this exact 22-band family (`stats.bh_q`,
   decision 63) — the device-shaped tier inherits the existing per-band multiple-comparison correction
   the research tier, reading every band jointly in one model, does not need.

3. **Choice 1's ratings switch.** One keyword argument, `include_clinic_sheet=False` by default, on
   every function above that reads ratings. When true, `_merge_clinic_sheet_ratings` is called and the
   *entire four-reading block is run a second time*, tagged `"source": "redcap_plus_clinic_sheet"`,
   and reported as an additional row beside the REDCap-only row — never merged into one fitted model,
   per the Choice 1 recommendation. The saved record carries both rows when the flag is set, so a
   reader can see whether the two sources agree without either one silently overriding the other.

4. **Choice 2's outcome switch.** One keyword argument, `outcome="continuous"` by default (the
   recommendation above), with `"tertile"` kept available and matching today's `_binarize_labels`
   exactly, for anyone who wants a direct comparison against the platform's existing screens. The
   continuous path predicts the pain score itself with the same ridge-regression code already in
   `all_bands_auc` (a ridge fit's prediction is a number whether or not it is later turned into a rank;
   only the *scoring* step changes: report the held-out Spearman correlation between the prediction and
   the true score, `stats.spearman_within`, with a day-resampled interval, `stats.day_resampled_rho`,
   in place of AUC) and the same shuffled-data comparison, scored the same way on the shuffled runs so
   the two are read on the same scale.

5. **Choice 3's timing switch.** Exposed only on the device-shaped tier (`apply_device_timing=True`,
   not overridable to false — a device-shaped reading with no device timing is not answering the
   question it exists to answer, per the Choice 3 recommendation); the research tier keeps its
   existing free choice of window length (1 to 60 seconds, decision 170) with no restriction, and its
   own registry entry states plainly that it does not apply device timing, so a reader is never left
   guessing which tier they are looking at.

**Registry and saved output.** Add two entries to `ControlAnalyses/registry.py`, `research_band_
detector` (page: Biomarkers) and `device_shaped_band_detector` (page: Biomarkers), each with a `what`
description in this project's own house style and a link to this report (added to `registry.LIT`
alongside the 2026-09-24 literature reports it builds on). Both write through `ControlAnalyses.
snapshots.save` exactly as the five existing analyses do — an aggregate JSON record (readings, their
intervals, which stretch or ratings source and outcome type produced them, the run date and data
span), never a single rating, never a cache-store entry, every run kept.

**What is explicitly out of scope for this build.** No result from either tier ever appears on the
Closed-Loop sign-off sheet, is folded into the one-band screen's "usable" count (decision 199), or
changes the device sensing-pair rule (decision 217) or the harmonic warning (decision 220). This
mirrors `confound_diagnostic.py`'s own stated purpose exactly: "nothing here refuses anything... a
warning, never blocking" (the PI, 2026-09-22).

## 5. What would count as a result worth acting on

No single number from this design should move a recommendation on its own; the following is what
*would* be worth bringing back to the PI as more than a lead:

1. **The "bands with current taken out" reading clears the shuffled-data comparison, on the research
   tier, after correcting for how many combinations were tried.** Today's one positive result (p =
   0.04) is uncorrected for the twelve pair-and-length combinations already tried across two runs; a
   pre-registered analysis plan (one sensing pair, one or two window lengths, one ratings choice, one
   outcome choice, decided *before* looking at the results, per the three recommendations above) would
   need its own result to clear the same bar cleanly, not benefit from having been the best of several
   tried after the fact.
2. **The result agrees in direction with the fourth reading, the unchanged-setting stretch, even
   though that reading alone will likely be too small to be decisive by itself.** This is the same
   logic this project's own titration-ladder design already uses for its two readings, the current-
   stepped ramp and the fixed-current holds (decision 237): "the ramp is the reading, the holds are
   beside it for comparison." A positive research-tier finding that a band tracks pain once current is
   removed should point the same way as what that band does during a stretch where current genuinely
   never moved, even if the second reading's own interval is wide.
3. **The device-shaped tier, using the real device timing from the start, finds the *same* band
   "supported" (a positive relationship with a block-bootstrap interval wholly above zero, this
   project's own existing language, decision 210) after its own 22-band correction.** A result that
   only appears in the research tier's more flexible, multi-band model, and vanishes once reduced to
   one band read on the device's own timing, is telling this project that the device cannot use what
   the research model found — a real and useful answer, but not a result to act on for programming a
   switching value.
4. **The band clears the existing harmonic and sensing-pair checks that already sit in front of every
   candidate on this platform** — it is not one of the bands flagged as sitting on a stimulator
   harmonic (decision 220), and it belongs to one of the two sensing pairs the device's own flanking
   rule actually allows today, L 1-3+ or R 0-3+ (decision 217). A result on a pair or band the device
   cannot legally sense from is a research finding, not a candidate.

Meeting all four would justify a targeted follow-up (for instance, a short fixed-current hold at the
visit already being planned for the exploratory ladder, decision 230/236) — never, by itself, a change
to the sign-off sheet, the one-band screen's "usable" count, or a recommended switching value.

## 6. Feasibility risks

- **Sample size.** `confound_diagnostic.MIN_ROWS = 40` already refuses to answer below that count.
  REDCap-only matching gave 53 to 201 ratings on the one pair with any signal at all, depending on the
  window (decisions 240, 262); the fourth reading further restricts this to whichever single unchanged
  stretch is longest, and decision 253's own count of only 19 epochs at the reference setting (55 Hz,
  60/160 microsecond pulse width) suggests this may fall under 40 on more than one sensing pair,
  meaning the fourth reading may only be computable at all on the pair with the deepest device-side
  coverage, R 0-3+ (this project's own device documentation records under 2% native device-power
  coverage everywhere, but far more on this pair than the others: 797 windows against 258 to 384 on
  the rest, `DEVICE_percept_rc.md` §6).
- **The clinic sheet's confound-by-design, if Choice 1 is later overridden.** The sheet ratings module
  documents its own warning plainly: every sheet rating was taken while current was being deliberately
  stepped. Merging it into the primary reading (against this report's recommendation) would let the
  "current taken out" reading remove a curve fitted mostly to fast, deliberate current swings and then
  apply it to slow, ambulatory rows it was never fitted to represent.
- **The already-measured non-stationarity problem.** Decision 253 found that even at one genuinely
  unchanged setting, the fitted response to it "moves between blocks of time" — the objective at the
  most-delivered current pair fell hard across three blocks with no setting change at all (from about
  1.5 points worse than the incumbent setting to about 0.1 points better, p = 0.0006). The fourth
  reading (bands during an unchanged-setting stretch) will run directly into this: a positive or
  negative finding there could reflect the same drift decision 253 already found, rather than the
  brain-pain relationship the reading is meant to isolate, and any result from it needs that caveat
  stated beside it every time, not once in a footnote.
- **The harmonic problem is not solved by any of the three choices.** The one band family that has
  looked positive on this record before (21.5–27.5 Hz on the left) sits on or beside the stimulator's
  own folded harmonic at the rate in force (decision 233, answer 3): at 55 Hz the harmonic falls inside
  25.5, 26.5, and 27.5 Hz, leaving only 24.5 Hz clear. None of the three choices in this report changes
  that; the harmonic warning (decision 220) still has to run on whatever this design finds, and a
  positive device-shaped result on a harmonic-adjacent band is a warning, never a disqualification by
  this project's own existing rule, but it is not a clean result either.
- **This is research code touching the same modules the live pages read.** `confound_diagnostic.py`,
  `stats_utils.py`, and the report-matching functions in `bravo_service.py` are shared, tested code
  paths; any change to their signatures (new optional keyword arguments only, per the build
  specification above) needs the full host and container test suites re-run before landing, per this
  project's own standing rule that a suite count is never quoted without a fresh run behind it.
- **No result here should be mistaken for a titration outcome.** The exploratory ladder already
  designed for the next clinic visit (decision 230, corrected by decisions 233 and 236) is the only
  design on this record that manipulates current on purpose while holding sensing fixed; everything in
  this report is a *passive* re-reading of data already collected, and even a clean result from it
  would still need that ladder's controlled test, not replace it.

## References (verified)

1. Cohen J. "The Cost of Dichotomization." *Applied Psychological Measurement*. 1983;7(3):249–253.
   (Read directly, full text, for this report.)
2. Preacher KJ, Rucker DD, MacCallum RC, Nicewander WA. "Use of the Extreme Groups Approach: A
   Critical Reexamination and New Recommendations." *Psychological Methods*. 2005;10(2):178–192. DOI
   10.1037/1082-989X.10.2.178. (Read directly, full text, for this report; the "post hoc subgrouping"
   critique and the explicit recommendation against tertile/quartile splits on already-full data sets
   are quoted from the paper's own Recommendations section.)
3. Altman DG, Royston P. "The cost of dichotomising continuous variables." *BMJ*. 2006;332(7549):1080.
   DOI 10.1136/bmj.332.7549.1080. PMID 16675816. (Citation and journal metadata independently
   confirmed via the Oxford University Research Archive and PubMed; the full text was not accessible
   in this session behind a verification page, so its own numeric claims are not separately restated
   here beyond what Cohen 1983, read directly, already establishes.)
4. Haase I. "Accuracy of retrospective pain measurement in patients with chronic pain." *Medicine
   International*. 2023;3(4):35. DOI 10.3892/mi.2023.95. (Read via PMC full text for this report;
   n = 94 chronic pain patients, current-pain-at-recall as the strongest predictor of recalled average
   pain, standardised beta 0.441, p < 0.001.)
5. Jamison RN, Sbrocco T, Parris WC. "The influence of physical and psychosocial factors on accuracy
   of memory for pain in chronic pain patients." *Pain*. 1989;37(3):289–294. (Bibliographic details and
   direction-of-bias finding — pain-free patients underestimate recent pain, high-pain patients
   overestimate it — confirmed via a search-engine summary of the paper's abstract; the primary text
   was not independently opened in this session.)
6. Stone AA, Schwartz JE, Broderick JE, Shiffman SS. "Variability of Momentary Pain Predicts Recall of
   Weekly Pain: A Consequence of the Peak (or Salience) Memory Heuristic." *Personality and Social
   Psychology Bulletin*. 2005;31(9):1340–1346. DOI 10.1177/0146167205275615. (Bibliographic details
   confirmed via search; the peak/salience mechanism it describes is summarized from the paper's own
   title and a search-engine abstract summary, not from an independently opened full text.)
7. Jamison RN, Raymond SA, Slawsby EA, McHugo GJ, Baird JC. "Pain Assessment in Patients With Low Back
   Pain: Comparison of Weekly Recall and Momentary Electronic Data." *The Journal of Pain*.
   2006;7(3):192–199. DOI 10.1016/j.jpain.2005.10.006. (Bibliographic details confirmed via search;
   full text was not accessible in this session, so its specific quantitative agreement/bias finding
   is not restated here.)
8. Hjermstad MJ, Fayers PM, Haugen DF, et al. "Studies Comparing Numerical Rating Scales, Verbal
   Rating Scales, and Visual Analogue Scales for Assessment of Pain Intensity in Adults: A Systematic
   Literature Review." *Journal of Pain and Symptom Management*. 2011;41(6):1073–1093. DOI
   10.1016/j.jpainsymman.2010.08.016. (Bibliographic details confirmed via search; the review's general
   conclusion favouring the numeric rating scale for clinical usability is well established and is
   stated here at that general level, not from an independently opened full text in this session.)
9. Stanslaski S, Summers RLS, Tonder L, et al. "Sensing data and methodology from the Adaptive DBS
   Algorithm for Personalized Therapy in Parkinson's Disease (ADAPT-PD) clinical trial." *npj
   Parkinson's Disease*. 2024;10:174. DOI 10.1038/s41531-024-00772-5. (Already independently verified
   by this project's own 2026-09-24 literature report, `research_2026-09-24_3_tonic_current_and_
   single_threshold.md`; re-confirmed as a real, indexed paper via search in this session, not
   re-opened in full text.)
10. Bronte-Stewart HM, et al. "Long-Term Personalized Adaptive Deep Brain Stimulation in Parkinson
    Disease: A Nonrandomized Clinical Trial." *JAMA Neurology*. 2025. Accessed via PMC12455485.
    (Already independently verified by this project's own 2026-09-24 literature report; not re-opened
    in full text in this session.)
11. Velisar A, Syrkin-Nikolau J, Blumenfeld Z, Trager MH, Afzal MF, Prabhakar V, Bronte-Stewart H.
    "Dual threshold neural closed loop deep brain stimulation in Parkinson disease patients." *Brain
    Stimulation*. 2019;12(4):868–876. DOI 10.1016/j.brs.2019.02.020. PMID 30833216. (Bibliographic
    details independently re-confirmed via search in this session.)
12. Little S, Pogosyan A, Neal S, et al. "Adaptive deep brain stimulation in advanced Parkinson
    disease." *Annals of Neurology*. 2013;74(3):449–457. DOI 10.1002/ana.23951. PMID 23852650.
    (Bibliographic details independently re-confirmed via search in this session; cited here only for
    the general precedent that timing is built into a threshold-based adaptive controller's design
    from the start, not for its own outcome numbers.)
13. Shirvalkar P, Prosky J, Chin G, et al. "First-in-human prediction of chronic pain state using
    intracranial neural biomarkers." *Nature Neuroscience*. 2023;26:1090–1099. DOI
    10.1038/s41593-023-01338-z. PMID 37217725. (Bibliographic details independently re-confirmed via
    search in this session; cited here as this participant's own research group's precedent for
    treating a pain biomarker as a multi-feature, carefully validated question rather than a single
    band read off a device threshold.)

**This project's own documents, read directly for this report (not external literature, listed here
for traceability):** `CLAUDE.md`; `HOUSE_RULES_writing_and_claims.md`; `DECISIONS_and_open_items.md`
(decisions 63, 150, 168–170, 183, 186, 196, 199, 210, 213, 217, 220, 229, 230, 232, 233, 236, 237, 240,
241, 243, 246, 253, 258, 260–265); `DEVICE_percept_rc.md` §§2, 6; `artifacts/research_2026-09-24_
3_tonic_current_and_single_threshold.md`; `artifacts/research_2026-09-24_SYNTHESIS_state_washin_
threshold_offperiods.md`; `BRAVO/modules/Biomarkers/routines/confound_diagnostic.py`; `BRAVO/modules/
Biomarkers/routines/stats_utils.py`; `BRAVO/modules/Biomarkers/routines/sheet_ratings.py`; `BRAVO/
modules/Biomarkers/routines/analytics.py` (`_binarize_labels`); `BRAVO/modules/Biomarkers/
bravo_service.py` (`_merge_clinic_sheet_ratings`); `BRAVO/modules/ControlAnalyses/{registry,snapshots,
run,runners,stats}.py`; `BRAVO/modules/DecodeCommon/{data_start,device_ranges}.py`.

## Unverified

- The exact quantitative claim sometimes attributed to Altman & Royston (2006) directly — that
  splitting a continuous variable at its median costs the same statistical power as discarding about a
  third of the sample — could not be confirmed against that paper's own full text in this session (the
  page was behind an automated verification screen each time it was fetched). The same numeric claim
  **was** independently confirmed against Cohen (1983)'s own full text, read directly for this report,
  which is the earlier and more detailed source for it; Altman & Royston's BMJ note is a shorter,
  clinically aimed restatement of the same general finding, and is cited above for its own
  bibliographic identity, not for a number this session could not re-derive from its text.
- Jamison, Sbrocco & Parris (1989) and Jamison, Raymond, Slawsby, McHugo & Baird (2006) — both
  bibliographically confirmed as real, indexed papers, but this session could not open either paper's
  full text (PubMed's automated verification screen blocked both attempts), so their specific
  quantitative findings beyond the general direction already reported in Section 3 above should be
  treated as MEDIUM confidence, from a search-engine abstract summary, until someone with direct
  journal access reads them.
- Stone, Schwartz, Broderick & Shiffman (2005) and Hjermstad et al. (2011) — likewise bibliographically
  confirmed but not opened in full text this session; their general conclusions as stated in Section 3
  are well-established and consistent with the wider literature this report did read directly (Cohen
  1983, Preacher et al. 2005, Haase 2023), but the specific papers themselves were not independently
  re-read.
- The exact live counts this report would need to decide Choice 1's clinic-sheet trade-off precisely
  for the current record (how many clinic-sheet-only ratings exist per sensing pair today, after the
  2026-09-24 implant-date cutoff, decision 260, and the 2026-09-24 coverage-count fix, decision 261)
  were not re-run in this session; the 91-to-168 figure quoted in Section 3 is read from
  `sheet_ratings.py`'s own docstring, dated 2026-09-16, and should be treated as approximate and
  possibly stale rather than re-measured for this report.
