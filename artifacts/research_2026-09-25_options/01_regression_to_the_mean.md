# Option 1: does regression to the mean explain decision 253's drift at an unchanged setting?

> Research report — worker-research | Date: 2026-09-25
> Confidence: MIXED — the record clearly shows a real block-to-block swing (decision 253); whether
> it is specific to the one current pair, or just this patient's pain moving for some other reason at
> the same time, is not yet tested. This report specifies the test; it does not run it.

A note on words used here. "The record" means all the data collected for RCS08 so far. "A setting"
means one exact combination of left and right current (in milliamps, mA), pulse rate (pulses per
second, Hz) and pulse width (millionths of a second, µs) programmed into the device. "A
setting-period" (the code calls it an "epoch") is one continuous stretch of time during which one
exact setting was in force; a new one starts the moment anything about the setting changes. "The
objective" (the code calls it "J") is a single number built for each setting-period: the average of
one pain score during that period, minus the average of the same pain score during whatever setting
is in force right now. J is zero for today's setting by construction; a positive J means that
period's pain was worse than pain is today; a negative J means it was better. "Threshold" below is
used only in its device sense (the switching value the paper's own titles use); nowhere here is it
used as a cut-off for statistical significance — I write "small p-value" or "cut-off" for that.

## The question

Decision 253 found that at the one setting programmed most often inside one group of setting-periods
that all shared the same pulse rate and pulse width (55 pulses per second, 60 µs pulses on the left
side and 160 µs on the right; the setting itself was 1.6 mA left / 1.2 mA right), the objective fell
across three time blocks — 1.51, then 0.53, then −0.06 — while the setting itself never changed
(decision 253, `BRAVO/modules/StimOptimizer/stage1_openloop.py`, `calibration_diagnosis` and
`_reference_setting`). Decisions 262 and 264 then tested one explanation, a current that leaves a
trace after it is turned down or up ("wash-in," modelled as an exponentially fading memory of past
current), and found it does not explain the drift: at every memory length tried, the pattern is still
there. This report tests a second, different explanation: **regression to the mean** — the general
statistical fact that when a value is unusually far from average, the next measurement of it tends to
land closer to average again, purely because of measurement noise and because of how the value came
to be looked at in the first place, with no real change required. If the 1.6/1.2 mA setting was kept
in place, or came to be the most-delivered setting in that group, partly because the record's early
weeks there happened to look bad (block 1's high objective, 1.51), some of the later "improvement"
could be this statistical fact rather than a change in how well the setting itself works.

## What the record already says

- **Decision 253** (`stage1_openloop.calibration_diagnosis`, `stratum_calibration`): on the 19
  setting-periods that share 55 Hz / 60 µs (left) / 160 µs (right), the left-leg pain surface "moves
  between blocks of time" — 62% of the miss between what the fitted surface predicted and what
  actually happened is shared by whole time blocks rather than scattered epoch to epoch, with a
  cut-off-beating small p-value (p ≈ 1×10⁻⁷ on that heterogeneity check). Inside that same group, the
  8 setting-periods at the most-delivered setting (1.6 mA left / 1.2 mA right) show the objective
  falling block by block: 1.51 (± 0.12), then 0.53 (± 0.24), then −0.06 (± 1.50); a direct
  heterogeneity check on those three numbers alone gives p 0.0006. Decision 253's own words: "the
  setting did not change and the patient's response to it did."
- **Decisions 262/264** (`ControlAnalyses/runners.py`, `run_current_with_memory` /
  `_drift_with_memory`): replacing "the current programmed right now" with a fading memory of past
  current (time constants of 0 hours up to 14 days) never predicts pain better, out of sample, than
  just using the current programmed right now; and re-running decision 253's exact diagnosis with
  every one of those memory versions in place of the plain current still gives "moves between blocks
  of time" at every memory length, 61–63% of the miss shared by whole blocks, p < 1×10⁻⁷ throughout.
  So a fading trace of past current is ruled out as the explanation; the question of whether the
  block-to-block change is a real response to that specific setting, or something else that happened
  to coincide with those calendar weeks, is still open.
- The 2026-09-24 synthesis (`artifacts/research_2026-09-24_SYNTHESIS_state_washin_threshold_offperiods.md`,
  §3 item 5) proposed exactly this check — "was each block preceded by an unusually good stretch?" —
  as read-only, not yet built. This report is the specification for building it.
- Separately, the same synthesis (§4d) reports that as the memory time constant grows, the remembered
  current tracks calendar time more and more closely on the left side (correlation with time rising
  from about 0.54 to 0.68 as the memory lengthens) — a warning that current and calendar time are
  hard to tell apart in this record, which matters for the design below.
- The record's overall size, as given for this task: 92 rated setting-periods and 776 individual pain
  ratings for RCS08 in total (across every setting and every pulse rate/pulse width group, not only
  the 19-setting-period group decision 253 flagged). I have not independently re-run a count against
  the live database in this session — I have no tool here that executes code or reaches the container
  — so this figure is carried as given rather than freshly verified; the review document
  `artifacts/review_2026-09-12_StimOptimizer_IMPLEMENTED.md` independently states "92 epochs" for
  RCS08's full setting-period table as of 2026-09-12, which is consistent with it.

## Evidence and literature

Regression to the mean is one of the oldest known traps in before/after and single-patient
medicine: whenever a period, a patient, or a setting is picked out (or kept in place) partly *because*
an early measurement looked unusually good or bad, later measurements of that same thing will drift
back toward the average even if nothing about the treatment changed. The literature below is general
clinical-statistics guidance (not DBS-specific — a targeted search found no published discussion of
regression to the mean in deep-brain-stimulation programming specifically; see "Unverified" below),
plus a chronic-pain-specific paper making exactly this point, plus methodology for the kind of
repeated single-patient check that would settle it going forward.

1. **Barnett AG, van der Pols JC, Dobson AJ. "Regression to the mean: what it is and how to deal
   with it." Int J Epidemiol. 2005;34(1):215–220. DOI 10.1093/ije/dyh299. PMID 15333621.** (Correction:
   Int J Epidemiol. 2015;44(5):1748.) This is the standard tutorial reference. It walks through why
   an unusually extreme measurement is followed, on average, by a less extreme one purely from
   measurement noise, gives the formula for how much reversion to expect (it depends on how far from
   average the first measurement was, and on how reliable — how repeatable — the measurement is), and
   lays out the two standard defences: a comparison group that went through the same selection process
   but not the treatment, or measuring reliability directly and correcting for it. Its main limitation
   for us is that its worked examples assume a designed study with a known selection rule; here the
   "selection" (which setting a clinician kept using) is informal and not recorded as a rule. It
   matters here because it supplies both defences this report's specification uses: an internal
   comparison group (Step 5 below) and an external one (Step 6).
2. **Whitney CW, Von Korff M. "Regression to the mean in treated versus untreated chronic pain."
   Pain. 1992;50(3):281–285. DOI 10.1016/0304-3959(92)90032-7. PMID 1280801.** This paper is the
   closest match in subject matter. It studies people with jaw-joint and other chronic pain who sought
   treatment during a flare-up, and shows that their pain fell afterward whether or not they actually
   received treatment, because entering care itself was triggered by an unusually bad patch. Its main
   limitation is that it is an observational comparison of treated versus untreated patients, not a
   randomized trial, so it cannot rule out that treatment also helped on top of the reversion; its
   point is only that reversion alone is enough to produce the improvement usually credited to
   treatment. It matters here because RCS08's own programming decisions are, in the same way,
   triggered by how the patient is doing at the time — a clinician does not usually keep repeating a
   setting that just produced a bad week.
3. **Morton V, Torgerson DJ. "Effect of regression to the mean on decision making in health care."
   BMJ. 2003;326(7398):1083–1084. DOI 10.1136/bmj.326.7398.1083. PMID 12750214.** A short, widely
   cited piece aimed at clinicians rather than statisticians: it warns that picking out the patients
   who are doing worst and then crediting whatever was done next for their recovery is one of the most
   common statistical errors in medicine, and that the error gets worse the more extreme the group
   picked out. Its limitation is that it is a commentary, not a new method or a new dataset. It matters
   here as the clearest statement of exactly the risk in reading decision 253's numbers at face value:
   1.6/1.2 mA was the *most-delivered* setting in its group, which itself suggests it was singled out
   for some reason at some point, and "singled out" is the precondition for this whole concern.
4. **Yudkin PL, Stratton IM. "How to deal with regression to the mean in intervention studies."
   Lancet. 1996;347(8996):241–243. DOI 10.1016/S0140-6736(96)90410-9. PMID 8551887.** This paper gives
   practical designs for telling a real effect apart from reversion when a study only measures people
   who were extreme at the start, including using a comparison group measured over the same calendar
   window and, where that is not available, statistically correcting using an independent estimate of
   how repeatable the measurement is. Its limitation is the same as Barnett's: the corrections assume
   the selection rule is known, which is not fully true here. It matters here because it is the direct
   source for this report's Step 6 (an outside comparison window that never received the setting being
   judged, drawn from the same calendar record).
5. **McDonald CJ, Mazzuca SA, McCabe GP Jr. "How much of the placebo 'effect' is really statistical
   regression?" Stat Med. 1983;2(4):417–427. DOI 10.1002/sim.4780020401. PMID 6369471.** This is an
   older but influential re-analysis showing that much of what older trials called a "placebo effect"
   disappeared once trials were designed to protect against picking out patients at an extreme moment;
   modern trials designed that way showed almost no placebo improvement (a median change of 0.3%, not
   statistically different from zero). Its limitation is that it is itself a re-analysis of other
   people's trials, not new data. It matters here as a reminder that the size of an apparently real
   effect can shrink to almost nothing once the selection-driven part is properly accounted for — a
   caution against over-reading a single significant-looking block-to-block swing.
6. **Senn S, Grender JM, Johnson WD, Elston RC. "Regression to the mean and crossover trials
   revisited." Stat Med. 1994;13(11):1181–1186. DOI 10.1002/sim.4780131108.** This paper works through
   how regression to the mean plays out specifically when the same patient is measured repeatedly under
   different conditions, as opposed to different patients being measured once each — the situation this
   project is in, since RCS08 is one person tested under many settings over more than a year. Its
   limitation is that it is written for formally randomized crossover designs, where which condition
   comes first and second is decided by a coin flip; RCS08's setting history is not randomized, so its
   formulas apply only as a guide to the general shape of the problem, not as a plug-in correction. It
   matters here for exactly that reason: it is the right conceptual frame (repeated measures on one
   person) but cannot be used off the shelf.
7. **Linden A. "Assessing regression to the mean effects in health care initiatives." BMC Med Res
   Methodol. 2013;13:119. DOI 10.1186/1471-2288-13-119. PMID 24073634.** A practical, general-purpose
   method paper showing how to estimate how much of an observed before/after change in a health
   program is regression to the mean, using only the program's own before-and-after numbers plus an
   estimate of measurement reliability, without needing a formal control group. Its limitation is that
   its reliability estimate is itself assumed known or separately estimated; getting that estimate
   wrong biases the correction. It matters here as the source of the general shrinkage idea behind the
   "how extreme was block 1" plausibility check in the specification below (Step 7's extremity number).
8. **Guyatt G, Sackett D, Taylor DW, Chong J, Roberts R, Pugsley S. "Determining optimal therapy —
   randomized trials in individual patients." N Engl J Med. 1986;314(14):889–892. DOI
   10.1056/NEJM198604033141406.** The paper that first formally described the "N-of-1 trial": testing
   two or more treatments on the same single patient, in a randomly ordered series of paired periods,
   to separate a real difference from chance in that one person. Its limitation for us is that its
   method needs the ordering of periods to be randomized by the investigator and often blinded, neither
   of which happened for RCS08's setting history (settings were changed for clinical reasons, in a
   clinically sensible order, not at random). It matters here because it names the gold-standard fix:
   deliberately reintroducing a setting later, more than once, in an order nobody can predict from how
   the patient is doing, to see whether the same effect reappears — exactly the follow-up recommended
   below when this record cannot settle the question by itself.
9. **Kravitz RL, Duan N, eds. (DEcIDE Methods Center N-of-1 Guidance Panel). "Design and
   Implementation of N-of-1 Trials: A User's Guide." Agency for Healthcare Research and Quality;
   AHRQ Publication No. 13(14)-EHC122-EF, January 2014.** A methods guide (not a peer-reviewed
   journal article) written for exactly this kind of single-patient, repeated-measurement question,
   including how many repeated periods are usually needed before a within-patient effect can be told
   apart from day-to-day noise. Its limitation is that its worked examples assume the treatment can be
   started and stopped cheaply and safely many times, which is not fully true of a DBS current setting
   (each change needs a clinic visit or a home step under supervision, and any first exposure to a new
   setting carries its own side-effect stopping rule, decision 230). It matters here because its
   guidance on how many repeats are enough is the right reference point for planning the
   next-visit follow-up recommended below.
10. **Kravitz RL, Schmid CH, Marois M, et al. "Effect of Mobile Device–Supported Single-Patient
    Multi-crossover Trials on Treatment of Chronic Musculoskeletal Pain: A Randomized Clinical Trial."
    JAMA Intern Med. 2018;178(10):1368–1377. DOI 10.1001/jamainternmed.2018.3981. PMID 30193253.** A
    randomized trial testing whether a smartphone-supported single-patient repeated-crossover design
    (patients cycling through pairs of treatments for their own chronic musculoskeletal pain, each
    pair in a random order) improves how well a chronic-pain treatment is actually matched to the
    patient, compared with usual care; it is one of the largest modern demonstrations that this kind of
    design is workable in chronic pain outside a research lab. Its limitation is that its patients
    were self-tracking with pills or supplements on a phone, not a surgically implanted stimulator
    that a clinician must reprogram in person. It matters here as evidence that repeated, orderly
    re-testing of the same options in one patient is a proven, practical way to separate a real
    within-patient effect from noise — the direction the next-visit recommendation below points in.

## The analysis specification

**Data already available, reused as-is.** The specification below reuses the record exactly as
decisions 253/262/264 already build it, with no new source of truth:

- `AD.build_design_matrix(participant, {"ParticipantId": uid}, washin_min=1.0)`
  (`BRAVO/modules/StimOptimizer/adapter.py`, `exposure_epochs` + `attach_pros`) — one row per
  setting-period, with its start time, the settings, the ratings-based averages and the day count.
  This is the exact table `_drift_with_memory` already builds in
  `BRAVO/modules/ControlAnalyses/runners.py`.
- `S1.run_stage1(es, primary_item="left_leg", calibration_check=True, pool_pulse_widths=False)`
  (`BRAVO/modules/StimOptimizer/stage1_openloop.py`) — the same call `_drift_with_memory` already
  makes, giving the fitted rate-by-rate surfaces and, on each one, `rs.meta["calibration"]["diagnosis"]`
  (decision 253's own numbers) and `rs.meta["points"]` (one entry per setting-period in that group:
  its two currents, its rating count, its objective value, and its own identifying number).
- The target group is the same one decision 253 flagged: 55 Hz, 60 µs (left) / 160 µs (right),
  primary pain score "left leg" (the PI-designated primary pain site, reported on a 0–10 scale, the
  same default `routines/objective.py` already uses).

**Two small, additive code changes needed first** (neither changes any existing number; both only
add fields nothing currently reads):

1. In `_fit_rate_stratum` (`stage1_openloop.py`), extend each entry already built for
   `rs.meta["points"]` to also carry the setting-period's start time (`t0`) and its own noise number
   (`obs_var`) — both already sitting on the same table (`sub`) that builds every other field in that
   same dictionary; this only adds two keys.
2. Add one new function, `regression_to_mean_diagnosis(sub, blocks, ...)`, next to the existing
   `_reference_setting` in the same file, and call it from `calibration_diagnosis`'s returned
   dictionary as a new key, `"regression_to_mean"`, sitting beside the existing `"reference_setting"`
   key. Like every other calibration check in this module, it must be a warning that refuses nothing
   (`CALIBRATION_CONSEQUENCE`) — it reports, it never selects a setting and never blocks a
   recommendation.

**The algorithm**, in the order it would run:

*Step 1 — find the setting being asked about.* Exactly as `_reference_setting` already does: round
each setting-period's two currents to three decimal places, find the one pair delivered in the most
setting-periods, call those the "target" group (here, 8 setting-periods) and every other
setting-period in the same rate/pulse-width group the "other" group (here, 11).

*Step 2 — reuse the existing time blocks.* Use the same three time blocks `_fold_labels_by_time`
already computes for the whole 19-setting-period group (setting-periods sorted by start time, cut
into three roughly equal-sized, contiguous groups in that order). Do not recompute or redefine these;
using the same blocks decision 253 already reports means the new check is directly comparable to it.

*Step 3 — the two summary numbers, computed for the target group.* Both use the target group's own
per-setting-period noise numbers (`obs_var`) as inverse weights, exactly as `_reference_setting`
already does for its own three block averages:
   - `Q_target`: the same heterogeneity number `_reference_setting` already returns (how far the
     three block averages sit from their own combined average, weighted by how much each block's
     average can be trusted). This is a two-sided number: it says the three block averages disagree
     with each other by more than noise alone would explain, but not which direction.
   - `trend_target`: new — a weighted straight-line fit of the three block averages against block
     order (first, second, third), weighted the same way, giving the size and direction of the
     block-to-block change in pain points. This is the one-sided number: it says whether pain is
     getting better or worse over the three blocks, and by how much per block.

*Step 4 — the same two numbers, computed for the "other" group.* Same recipe, same time blocks,
using only the 11 setting-periods NOT at 1.6/1.2 mA.

*Step 5 — the internal comparison ("is this specific to the one setting, or is it happening across
the whole group?").* Because the time blocks come from all 19 setting-periods' order in time and do
not depend on which 8 of them are called "target," it is possible to ask every other way of splitting
the same 19 setting-periods into a group of 8 and a group of 11, and recompute `Q` and `trend` for
each split. With 19 setting-periods and a group size of 8, there are exactly 75,582 possible splits
(choosing 8 out of 19) — few enough to try every single one, so no randomness or repeated sampling is
needed here at all, and the answer does not depend on a starting seed. From all 75,582 (skip any
split where one of the three time blocks ends up with fewer than two setting-periods, mirroring
`_reference_setting`'s own refusal in that case):
   - `p_two_sided` = the fraction of splits whose `Q` is at least as large as the real target group's.
   - `p_same_direction` = the fraction of splits whose `trend` falls at least as far, in the same
     falling direction as the real target group's, matching how large an improving trend would have
     to be to stand out.
   - Both numbers report their own floor honestly: with (up to) 75,582 usable splits, the smallest
     possible two-sided value either can ever read is about 1 in 75,582 (roughly 0.000013), so a
     result should be printed as "p < 0.00002" rather than "p = 0", and the actual number of usable
     splits (`n_valid`) should always be printed beside the p-value, since some splits may be skipped
     under Step 5's own "fewer than two setting-periods in a block" rule.

   *Reading this number.* If a randomly chosen group of 8 out of the same 19 setting-periods, in the
   same three time blocks, shows a swing this large about as often as not (a large `p_two_sided`), the
   swing is not something special about being at 1.6/1.2 mA — it is something the whole group of
   setting-periods was doing over that stretch of calendar time regardless of the exact current, which
   is exactly the pattern regression to the mean (or any other shared, time-linked cause) predicts. If
   almost no other 8-out-of-19 split comes close (a very small `p_two_sided`), the swing is unusual
   even among setting-periods that shared the same pulse rate, pulse width, and calendar window — which
   argues the specific current pair matters, though it still cannot say why (see Feasibility risks,
   point 5, below).

*Step 6 — the outside comparison ("is a swing this size common anywhere in this patient's record, not
just inside this one group?").* Using the full 92-setting-period table (every pulse rate, every pulse
width, every current, the whole record), take every run of 8 setting-periods that are next to each
other in time (sliding one setting-period at a time across the whole record; with 92 setting-periods
total this gives roughly 85 overlapping runs of 8), split each run's own neighbourhood into three time
blocks the same way, and compute the same heterogeneity number for each. Report what fraction of these
85 whole-record runs show a swing at least as large as decision 253's 1.6/1.2 mA group. This is the
kind of comparison window Yudkin & Stratton (1996) and Barnett (2005) recommend: one that never
received the specific treatment being judged, but went through the same passage of calendar time, so
it captures anything — the season, the year of recovery, an unrecorded life event, or genuine
regression to the mean — that would have moved pain regardless of which current was programmed.

*Step 7 — a plain extremity check, alongside the two p-values (descriptive, not a test).* How far was
block 1's target-group average (1.51) from the WHOLE record's own long-run average objective, measured
in units of block 1's own noise (its reported ± 0.12)? Regression to the mean predicts more reversion
the more extreme the starting point was; reporting this number lets a reader judge for themselves
whether "block 1 was only mildly unusual, yet the swing afterward was large" (which argues against
plain regression to the mean explaining all of it) or "block 1 was extremely unusual" (consistent with
a large expected swing from reversion alone).

**Output, saved exactly as the other control analyses are** (`ControlAnalyses/snapshots.py`): one
JSON record per run, under a new registry key, e.g. `"regression_to_mean_check"`, on the Stim
Optimizer page beside "A current with memory" (decision 264, item 4), carrying: the target setting and
group; the three block averages and their own noise numbers (already known from decision 253); `Q_target`,
`trend_target`, `Q_other`, `trend_other`; `p_two_sided`, `p_same_direction`, and `n_valid` from Step 5;
the outside fraction and its own count of usable runs from Step 6; the extremity number from Step 7;
and a plain-language reading following the same style as every other saved analysis
(`_zero_ma_reading`, `calibration_diagnosis`'s own wording) — reporting a small p-value and a common
outside occurrence as two separate facts, never collapsed into one verdict, and never blocking or
re-selecting anything.

## Expected power

Three separate limits apply, and all three should be read together, not just the smallest one:

1. **The internal check's own smallest possible p-value is fine.** With up to 75,582 usable 8-of-19
   splits, the check can in principle report a p-value as small as roughly 0.00002 — plenty of
   resolution for a cut-off of 0.05.
2. **How big a swing the internal check can actually detect is limited by how few setting-periods
   there are, and by how unevenly informative the three time blocks are.** Decision 253's own numbers
   show the third block's average resting on very little information: its noise number, ± 1.50, is
   about twelve times block 1's (± 0.12), which most likely means only one or two setting-periods (and
   probably not many ratings) fall in that block for the target setting. A rough calculation using
   those same noise numbers: comparing block 1 (± 0.12) against block 2 (± 0.24) alone, treating them
   as two independent averages, a swing of 1.51 − 0.53 = 0.98 pain points against a combined noise of
   about 0.27 is roughly 3.6 times that noise — plenty to detect on its own, which is consistent with
   decision 253's very small p-value for the whole-group heterogeneity check (about 1×10⁻⁷). What Step
   5 adds is not "is there a swing" (already answered, yes) but "is the swing bigger at 1.6/1.2 mA than
   it is elsewhere in the same 19 setting-periods" — and because the "other" group is only 11
   setting-periods split across the same three blocks, its own block averages will likely be about as
   imprecise as the target group's, especially in block 3. Using the standard two-sample rule of thumb
   for how big a difference a test can reliably catch (about 2.8 times the noise of the difference, for
   a conventional 80% chance of detecting it at a 0.05 cut-off), and a plausible range for that combined
   noise of roughly 0.3 to 1.6 pain points (reading off decision 253's own block noise numbers as a
   guide for both groups), Step 5 should reliably catch an extra, setting-specific swing on the order
   of about 1 to 4 pain points beyond whatever the whole group of 19 is already doing — and will most
   likely read "not distinguishable from the group as a whole" for anything smaller. This is an
   estimate reasoned from the numbers already published in decision 253, not a number computed by
   running the check; the runner, once built, should report its own achieved noise numbers directly
   rather than relying on this estimate.
3. **The outside check (Step 6) is much coarser.** With roughly 85 overlapping runs of 8
   setting-periods across the whole 92-setting-period record, the smallest possible fraction it can
   report is about 1 in 85 (roughly 0.012), and because neighbouring runs overlap heavily (each shares
   7 of its 8 setting-periods with the next), the 85 runs are far from 85 independent looks — the real
   number of independent pieces of information behind that fraction is much smaller, plausibly closer
   to 92 ÷ 8 ≈ 11 non-overlapping stretches. This check should be read as a directional, descriptive
   signal ("common" versus "unusual" across the record), not as a precise p-value, and its own count of
   usable runs should always be printed beside it.

**Bottom line on power.** This record can reliably tell the difference between "this exact current
pair behaved unusually differently from its own neighbours in time" (a fairly large, several-point
swing) and "it did about what everything else nearby was doing" (a small or no distinguishable
difference); it is not well powered to catch a modest, real, setting-specific effect on the order of a
half a pain point or less riding on top of a shared time-linked trend. That is itself worth stating on
the card plainly, the same way `calibration_diagnosis` already states "honest but uninformative: thin
data" for a surface that cannot beat its own training-fold average — a small, uncertain record should
say so, not manufacture false precision.

## Feasibility risks

1. **Time blocks are cut by count of setting-periods, not by calendar days.** `_fold_labels_by_time`
   splits setting-periods into three roughly equal-sized groups in time order; it does not check
   whether those three groups cover similar stretches of calendar time. If, say, block 1 covers four
   months and block 3 covers four days (because many short setting-periods were tried close together
   near the end), the "three blocks" would not be a fair, equal-time comparison. The specification
   above should print each block's actual date range next to its number so a reader can see this.
2. **A kind of circularity in how the "target" setting was even chosen.** The 1.6/1.2 mA setting is
   the target precisely because it was delivered the most; if that is mostly because it happened to
   fill up block 1 (say, a single long stabilization run early on), then many of Step 5's 75,582
   comparison splits will, purely by the shape of the calendar, also tend to draw several early
   setting-periods into their own "group of 8" — which could make the comparison less informative
   about whether the CURRENT specifically matters, and more about when in the record a setting-period
   happened to fall. Printing the target group's own block-by-block count (how many of its 8
   setting-periods land in each of the three blocks) up front lets a reader judge this directly.
3. **Small numbers throughout make any single summary number fragile.** 19 setting-periods split
   8-and-11 across three time blocks is a small record by any standard; one mis-grouped setting-period,
   or one unusually long or short one, can move the block averages noticeably. This is the same caution
   that led the project to delete its earlier "reliable change" index for a different pain measure
   (decision 231: "too few pairs, too much scatter to mean anything"); the same warning belongs on this
   card, in plain words, not only in a hidden number.
4. **The objective (J) for the "left leg" score may or may not include a side-effect term.** In general
   the objective is pain plus a side-effect penalty (`objective.build_objective`); the side-effect part
   is zero unless the record carries a structured side-effect entry for a setting-period. This should
   be checked and stated when the runner is actually written, so a reader knows the swing is pain
   alone, not pain plus an occasional side-effect report.
5. **Even a clearly "unusual, setting-specific" result cannot say why.** If Steps 5 and 6 both come
   back small (the swing is unusual both inside its own group and across the whole record), that only
   rules out plain, non-specific drift as a full explanation; it does not prove the current itself
   caused the improvement. A clinician's own reasons for keeping this exact setting in place —
   themselves not recorded in this data — could still be doing the work (Morton & Torgerson's point,
   reference 3 above): the setting may have been kept specifically because it seemed to be working,
   which is itself a form of the same selection problem this check is trying to net out, just one
   level up.
6. **The outside comparison (Step 6) mixes every setting together, which cuts both ways.** If different
   settings genuinely have different, real effects on pain, folding them all into one background
   comparison adds noise that could make the target swing look LESS unusual than it really is. If,
   instead, most of the record's swings share one common cause (the weekend effect and the broad
   improvement over the year already documented in decisions 246 and the 2026-09-24 synthesis), the
   background comparison could make the target swing look MORE unusual than it really is, by
   under-representing how much shared drift is normal. Both directions of bias should be named when
   this check is reported, not just one.
7. **This check is specific to the left-leg score and this one rate/pulse-width group.** Decision 238
   found the back-of-body pain score behaves differently from the left-leg score on the very same
   record; a similar check on the back score, or on the right side's own settings, would need its own
   separate run rather than assuming the same answer carries over.
8. **No later data exist yet to test for "overshoot," a classic sign that rules regression to the mean
   IN rather than out.** Plain regression to the mean predicts reversion TOWARD a stable long-run
   average, followed by levelling off — not continued improvement past it. Block 3's average (−0.06)
   is already slightly better than today's setting, and block 3 is also the last block in the record;
   there is no fourth block yet to show whether pain keeps improving (arguing against plain regression
   to the mean, which should level off) or climbs back up toward where block 1 was (a close match to
   the textbook regression-to-the-mean pattern). No analysis of the existing record can settle this;
   it needs the next time this setting, or one close to it, is programmed again.

## Recommendation

Build this as one more saved, descriptive control analysis, in the same style and under the same
rule as the four already built under decision 264: it reports, it never selects a setting and never
blocks a recommendation (`CALIBRATION_CONSEQUENCE`'s own words: "a warning, never blocking... it says
the surface has not been shown to predict a stretch of time it did not see"). Run it first on exactly
the 55 Hz / 60 µs–160 µs / left-leg group decision 253 already flagged, since that is the one already
under discussion; if it proves useful, generalize it to every rate/pulse-width group with enough
setting-periods to form three non-empty time blocks (at minimum, both non-empty per-block counts and
at least a handful of setting-periods per block — the same practical floor `PW_STRATUM_MIN_EPOCHS`
already applies elsewhere in this module). Treat a large p-value from Step 5, together with a common
outside occurrence from Step 6, as informative on its own — "this looks like the whole record's
background pattern, not something special about this current pair" — rather than as a null result
worth hiding.

## Concrete next steps

1. Add `t0` and `obs_var` to each entry of `rs.meta["points"]` in `_fit_rate_stratum`
   (`BRAVO/modules/StimOptimizer/stage1_openloop.py`) — additive, no existing field changes.
2. Add `regression_to_mean_diagnosis(sub, blocks, ...)` next to `_reference_setting` in the same file,
   implementing Steps 1–4 and 7 above, and call it from `calibration_diagnosis`'s return dictionary as
   a new `"regression_to_mean"` key.
3. Add the internal comparison (Step 5, the 75,582-split check) and the outside comparison (Step 6,
   the sliding 8-setting-period check across the full 92-setting-period record) as two more functions
   in the same file, or in `BRAVO/modules/ControlAnalyses/stats.py` beside `bh_q` and `tau_curve`, kept
   free of the database so they can be tested on made-up numbers first.
4. Write tests on made-up data before writing the runner, matching this project's own practice
   (watched failing first): (a) a made-up 19-row record where the "target" and "other" groups are
   really drawn from the same underlying process should give Step 5's p-values spread roughly evenly
   across many repeats, not clustered near zero; (b) a made-up record with a real, large,
   setting-specific swing built in on top of a shared block trend should give a small p-value. Both
   should be checked against the exact-enumeration count (75,582 for the 8-of-19 case) rather than
   only against a randomly sampled subset.
5. Add a registry entry and a runner (`run_regression_to_mean`) in `BRAVO/modules/ControlAnalyses/`,
   modelled exactly on `run_current_with_memory` / `_drift_with_memory`, and wire it into the Stim
   Optimizer page's control-analyses card beside "A current with memory."
6. Run it live on RCS08 through the project's usual bridge process, with the store's writes turned
   off for the check, and report the block date ranges, the target group's own per-block count, both
   p-values with their usable-split counts, the outside fraction with its own usable-run count, and
   the extremity number — printed beside decision 253's original numbers so a reader can compare them
   directly, following this project's own rule that a claim and its result belong in the same report.
7. At the next visit that programs 1.6 mA left / 1.2 mA right again (or a setting close to it), add a
   fourth time block and re-run the check: continued improvement argues against plain regression to
   the mean; a climb back up toward block 1's level is close to the textbook signature of it. This
   follows the N-of-1 logic in references 8–10 above — the only fully convincing way to tell a real,
   repeatable response apart from a one-time statistical artifact in a single patient is to see whether
   it reappears when the same setting is tried again, in an order the patient's current state cannot
   predict.

## References (verified)

1. Barnett AG, van der Pols JC, Dobson AJ. "Regression to the mean: what it is and how to deal with
   it." Int J Epidemiol. 2005;34(1):215–220. DOI: 10.1093/ije/dyh299. PMID: 15333621. (Correction: Int
   J Epidemiol. 2015;44(5):1748.)
2. Whitney CW, Von Korff M. "Regression to the mean in treated versus untreated chronic pain." Pain.
   1992;50(3):281–285. DOI: 10.1016/0304-3959(92)90032-7. PMID: 1280801.
3. Morton V, Torgerson DJ. "Effect of regression to the mean on decision making in health care." BMJ.
   2003;326(7398):1083–1084. DOI: 10.1136/bmj.326.7398.1083. PMID: 12750214.
4. Yudkin PL, Stratton IM. "How to deal with regression to the mean in intervention studies." Lancet.
   1996;347(8996):241–243. DOI: 10.1016/S0140-6736(96)90410-9. PMID: 8551887.
5. McDonald CJ, Mazzuca SA, McCabe GP Jr. "How much of the placebo 'effect' is really statistical
   regression?" Stat Med. 1983;2(4):417–427. DOI: 10.1002/sim.4780020401. PMID: 6369471.
6. Senn S, Grender JM, Johnson WD, Elston RC. "Regression to the mean and crossover trials revisited."
   Stat Med. 1994;13(11):1181–1186. DOI: 10.1002/sim.4780131108.
7. Linden A. "Assessing regression to the mean effects in health care initiatives." BMC Med Res
   Methodol. 2013;13:119. DOI: 10.1186/1471-2288-13-119. PMID: 24073634.
8. Guyatt G, Sackett D, Taylor DW, Chong J, Roberts R, Pugsley S. "Determining optimal therapy —
   randomized trials in individual patients." N Engl J Med. 1986;314(14):889–892. DOI:
   10.1056/NEJM198604033141406.
9. Kravitz RL, Duan N, eds. (DEcIDE Methods Center N-of-1 Guidance Panel). "Design and Implementation
   of N-of-1 Trials: A User's Guide." Agency for Healthcare Research and Quality; AHRQ Publication No.
   13(14)-EHC122-EF, January 2014. (Methods guide, not a peer-reviewed journal article.)
10. Kravitz RL, Schmid CH, Marois M, et al. "Effect of Mobile Device–Supported Single-Patient
    Multi-crossover Trials on Treatment of Chronic Musculoskeletal Pain: A Randomized Clinical Trial."
    JAMA Intern Med. 2018;178(10):1368–1377. DOI: 10.1001/jamainternmed.2018.3981. PMID: 30193253.

Internal (this repository, not external literature, cited for the record's own numbers):
`DECISIONS_and_open_items.md` decisions 253, 262, 264, 238, 231, 246; `BRAVO/modules/StimOptimizer/stage1_openloop.py`;
`BRAVO/modules/StimOptimizer/adapter.py`; `BRAVO/modules/StimOptimizer/routines/objective.py`;
`BRAVO/modules/ControlAnalyses/runners.py`, `stats.py`, `registry.py`, `snapshots.py`;
`artifacts/research_2026-09-24_SYNTHESIS_state_washin_threshold_offperiods.md`;
`artifacts/review_2026-09-12_StimOptimizer_IMPLEMENTED.md`.

## Unverified

- A targeted search for published discussion of regression to the mean specifically in deep-brain
  stimulation programming or titration (as opposed to general clinical statistics or chronic pain more
  broadly) found no directly on-point paper; the DBS-programming search results returned papers about
  predicting response from baseline severity and about automated/Bayesian programming methods, not
  about regression to the mean as a statistical artifact in repeated in-person programming visits. This
  is reported as a gap, not filled with an invented citation.
- The task's stated record size ("92 rated epochs, 776 ratings") is used as given; I confirmed the
  "92" figure independently against a repository document (`artifacts/review_2026-09-12_StimOptimizer_IMPLEMENTED.md`,
  "the two sides' pulse widths differ on 67 of 92 epochs," dated 2026-09-12), but I did not
  independently re-count the 776 ratings figure against a live run — I have no tool in this session
  that executes code or reaches the database, so this number should be re-confirmed when the runner
  above is actually built and run.
