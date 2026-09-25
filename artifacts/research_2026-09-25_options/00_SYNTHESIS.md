# Synthesis: the seven 2026-09-25 research options

> Synthesis, prepared for the PI (Prasad Shirvalkar)
> Date: 2026-09-25 | Confidence: MIXED — the engineering proposals rest on measured code; several of
> the scientific findings rest on a small, non-random record and are explicitly leads, not results.

**Terms used throughout, defined once.** *Current* is the electrical current the stimulator delivers,
in milliamps (mA). *Rate* is how many times a second it pulses, in Hz. A *band* is a roughly 5 Hz-wide
slice of the brain's electrical activity read from a pair of electrode contacts, named by its centre
frequency. *AUC* is a score from 0 to 1 for how well a number tells two groups apart; 0.5 is a coin
flip. A *setting-period* (the code calls it an "epoch") is one continuous stretch during which one
exact combination of current, rate and pulse width was programmed. The *block-of-time check* (decision
253) splits a group of setting-periods into three chunks in calendar order and asks whether the fitted
answer moves between them, purely as a warning — it changes no recommendation. *"The current taken
out"* means a statistical step that removes the current's own contribution to a band's power, or to
pain, before asking what is left; by the PI's ruling (decision 233, answer 2) this is always shown
beside the plain reading, never in place of it, and never re-selects a band on its own. *Clinic-sheet
ratings* are pain scores written down by hand during a clinic or at-home visit while the current is
being deliberately changed; *REDCap ratings* are the ones the patient enters at home, unprompted, on
their own schedule.

---

## 1. The answer on one page

Six of the seven reports investigate this patient's own record (RCS08); the seventh is a different
study and is summarised separately in section 4. Read together, they say one thing clearly: **almost
every open scientific question here comes back to the same missing piece of data — a setting, or a
step in a ladder of currents, repeated at a different point in time or in the opposite order, so a
real effect can be told apart from the calendar or from where a ladder happened to start.** Decision
253 found pain reads differently across calendar time at one setting that never changed. Decision 272,
which the report on regression to the mean did not know about (it dates the session incorrectly and
says the check "has not been run" — see section 3), already tried the cheapest version of this: on
the one visit where a current was rated on the way up and the way down, **every fall came after its
rise**, so the visit still cannot separate carry-over (does relief linger from the current just
lowered) from ordinary drift over the visit. Nothing on record yet answers this, and three separate
reports independently propose the same fix: a ladder, or a home schedule, that steps down before it
steps up, or returns to a setting weeks apart rather than minutes apart.

A second theme: **one number is being asked to carry more weight than it can.** Decision 262's finding
that the left-side bands still track pain after the current is taken out, at 60 seconds of signal
(0.683, just outside the range chance alone would produce) is the only piece of evidence anywhere in
this record that a real, current-independent left-side signal might exist. I read the code that
produces it (`BRAVO/modules/Biomarkers/routines/confound_diagnostic.py` and
`BRAVO/modules/ControlAnalyses/runners.py`) and confirmed what the small-rulings report found: **the
shipped, tested code never computes a p-value for that adjusted reading at all** — only for the plain,
current-included one. The "p = 0.04" figure came from a one-off script that no longer exists. Corrected
for the several signal lengths and sensing pairs tried, the honest answer is close to a coin flip
(roughly 0.5), not 1-in-25. This does not mean the lead is dead; it means it is exactly that — a lead —
and the band-detector report's own plan (Section 5 of its report) already says a pre-registered rerun,
corrected honestly, is the way to find out.

A third, separate finding, found while checking speed rather than science: the report on remaining
slow requests turned up a real correctness question, not a speed problem. Two of the Closed-Loop page's
numbers (how well a band tracks pain, and how well the current itself tracks pain) may be built from a
saved file whose label does not include which pain reports went into it — so a new pain report can
land and the page's numbers can still be built from the old ones, with nothing on the page to say so.
Decision 215 already saw this exact symptom once, for a different reason, and fixed the calibration and
recording-set parts of the label but not this one. This is precisely the failure CLAUDE.md's project
rule 5 exists to prevent (a pain rating in the payload of a stored product, serving a stale answer with
no visible symptom), and it has not been measured, only found by reading the code. **This should be
checked before anything else in this document, because it is cheap to check and, if real, it means a
number on a page today does not mean what it says.**

Everything else divides cleanly into three lanes: small, non-blocking checks that can be built now
under the pattern this project already uses (Options 1, most of Option 5, and the fast parts of Option
6); choices that need the PI to pick a direction before any code is written (Options 3, 4, and the
default-toggle question in Option 5); and things that need a patient visit (most of Option 2, and the
down-first ladder three reports independently call for). Section 5 lays these out in order.

---

## 2. What runs through the reports

- **The same missing design element — order and repetition, not more data — shows up in options 1, 2,
  and 4.** The regression-to-the-mean report needs the same setting reprogrammed again later to tell
  a real effect from statistical reversion. The next-visit report's hold-and-return design and its
  rate-swap design exist for the same reason: nothing in the record yet separates "the setting really
  works" from "time was passing anyway." The band-detector report's fourth reading (bands during a
  stretch where current never changed) runs into the identical problem decision 253 already found: a
  positive or negative answer there could just be the same drift, not a real brain-pain relationship.
- **The current and the calendar move together throughout this record, and three reports measure this
  independently.** The time-rule report: settings and calendar time are collinear (days-vs-pain −0.61,
  days-vs-current +0.39, days-vs-rate −0.48). The regression-to-the-mean report: as the assumed memory
  of past current grows, the remembered current tracks calendar time more and more closely (0.54 to
  0.68). The band-detector report treats this collinearity as the reason a model given both time and a
  setting could not tell them apart once already (decision 194, "time soaked up the settings' effect").
  All three point to the same practical conclusion: no time-varying model should be built until
  calendar-separated repeats of the same setting exist.
- **The left sensing pair (L 1-3+) and the 21.5–27.5 Hz band family are the one place any positive
  signal has ever appeared, and every report that touches it also flags the same 55 Hz half-rate
  contamination problem.** Decision 253's drift is on the setting this pair's current recommendation
  rests on. The confound check's one positive reading is on this pair. The next-visit report's rate
  swap and the band-detector report's harmonic warning both exist because, at 55 Hz, the stimulator's
  own half-rate signal falls inside three of these five bands, leaving only 24.5 Hz clear.
- **Two independent reports reach the same recommendation about clinic-sheet ratings without being
  asked the same question.** The band-detector report (built to design a passive detector) and the
  small-rulings report (built to review one already-shipped toggle) both conclude: never merge
  clinic-sheet ratings, taken while current is being deliberately changed, into the same fitted answer
  as REDCap ratings, taken during ordinary life. Report the two side by side, labelled, instead.
- **Every report that touches a positive-looking finding independently asks for the same next check:
  has it been corrected for how many things were tried, and does it hold up on a repeat?** This is
  explicit in reports 1, 3, and 4, and is exactly what report 5 then computed for decision 262's number.

---

## 3. Where the reports disagree, and the resolution

**(a) The time-rule report misdates and mis-states the carry-over check.** In its discussion of
modelling tolerance (its Option 4), the report says the up-versus-down ladder comparison "already
recorded in the 2025-09-16 titration session... has not yet been run." Two things are wrong, checked
against the decision log: the titration session was **2026-09-16** (decision 213), and the check
**has** been run — decision 272, committed the same day this synthesis was written, after that report
was finished. The resolution does not close the question, though: decision 272 found only one visit
where a current was rated on the way up and back down, and on that visit every fall came after its
rise, so the carry-over question the report raises is still open. The fix decision 272 itself names — a
ladder that steps down before it steps up — is exactly the design gap the time-rule report and the
next-visit-protocol report both independently describe. Treat this as confirmed still-open, not
resolved, and fold the "step down first" design into the next visit (see section 5).

**(b) The band-detector report's central piece of positive evidence cannot be reproduced by the shipped
code, and once corrected, is not evidence of much.** I read `confound_diagnostic.py`'s
`pre_build_diagnostic` function directly: it computes a shuffled-data p-value only for the plain
"every band" reading (`plain["p_value"]`), never for the "bands with current taken out" reading. I then
read the live page code that runs this check, `ControlAnalyses/runners.py`'s `run_current_explains`: it
assigns `p=d["bands_plain"].get("p_value")` — the plain reading's p-value — to the row, and for the
adjusted reading only records whether it is inside or outside the chance range, never a p-value. This
confirms the small-rulings report's finding exactly: the "p = 0.04" quoted in decision 262 and repeated
in the regression-to-mean, next-visit, and band-detector reports came from a one-off scratch script
under the gitignored scratch folder, not from any code that can be rerun today. The small-rulings
report's own arithmetic — treating this as one result out of roughly four to twelve tried — gives a
Bonferroni-corrected value of about 0.48, essentially a coin flip. **Resolution: the band-detector
report's framing of this number as "the entire positive evidence on the record" still stands as a
fair description of how little evidence exists, but the number itself should never be quoted as
"p = 0.04" again.** Recommended fix: extend `confound_diagnostic.py` to compute a real, correctable
p-value for the adjusted reading (mirroring the loop it already runs for the plain one), so a
pre-registered rerun — which report 4 already recommends as the bar for treating this as more than a
lead — produces a number that survives being checked.

**(c) A correctness question, not a disagreement between reports, sits underneath both the speed
report and the small-rulings report's recommendation.** The speed report found that the Closed-Loop
page's saved evidence-inputs file carries pain-report columns inside it, but the file's own label (used
to decide whether it needs rebuilding) does not include which pain reports went into it — only the
recording set, two calibration constants, and a rule version (decision 215). Decision 215's own text
already shows this happening once: rebuilding that file after new reports arrived moved 20 fields that
were "all pain-report columns." This is not yet shown to be currently wrong on the live page — it is a
read of the code, not a live measurement — but it means the small-rulings report's recommendation to
build a current-adjusted version of the deployment ROC, and the band-detector report's reuse of the
same evidence-inputs machinery, would both inherit this same risk until it is checked. **I recommend
checking this first, ahead of every other item in this document**, because it is one comparison
(today's saved file against a freshly built one) and it bears on whether numbers already on the page
mean what they say.

**No other disagreement was found between reports on a shared factual claim.** Every specific number
each report repeats from decision 262 (0.600, 0.708, 0.722, 0.743, 0.681, 0.683, the two null values)
matches across reports 1, 2, 4, and 5 and matches the decision log. The recommendation to keep
clinic-sheet ratings separate (reports 4 and 5) is convergence, not conflict, and is listed in section
2 rather than here.

---

## 4. One row per option

| # | Option | Cost | What it would tell us | PI decision needed | Depends on | Recommendation |
|---|---|---|---|---|---|---|
| 1 | Regression to the mean | ~1 engineering session; no visit | Whether decision 253's drift is a statistical artefact of picking out an unusual stretch, or specific to that current pair | No — follows the existing "warning, never blocking" pattern | Nothing new; reuses decision 253's own numbers | Build it |
| 2 | Next clinic visit protocol | 1–2 visits; rate swap ~1–2 hrs low burden; zero-current block several hours, high burden; hold-and-return multi-week, moderate burden | Whether the left-side band family is a real, current-free signal; whether it is the stimulator's own half-rate echo; whether a short lingering effect exists | Yes — safety and scheduling sign-off for each part separately | Clinical/device team confirming take-home streaming and sensing-only mode; a caregiver to hold the blind | Run the rate swap first (cheap, safe, decisive against one explanation); schedule the rest after |
| 3 | Time rule (decision 196) | ~1 small build if extending visibility; no visit | Whether a clinician sees decision 253's warning wherever a current is recommended, not only on a separate card | Yes — a plain yes/no | Nothing; explicitly recommends **not** building any time-varying model yet | Extend visibility (say "no" to keeping it hidden); do not build a time-varying model |
| 4 | Band detector, 3 choices | ~2–3 engineering sessions once the choices are set; no visit | Whether a device-realistic, single-band, single-current-adjusted signal survives the sensing-pair rule and the harmonic warning | Yes — the three named choices | Fixing confound_diagnostic's p-value gap first (item b above); decision 272-style repeats for real power | Adopt the report's own defaults (REDCap primary, continuous outcome, device timing only on the device-shaped tier) |
| 5 | Small rulings + stale numbers | (a) ~1 session to build a current-adjusted deployment ROC; (b) ~0.5–1 session to add the missing p-value; (c) ~30 min of document edits | Whether the clinic-sheet-ratings drop in the deployment ROC survives taking the current out; an honest, quotable number for decision 262's finding | Yes for (a)'s default toggle (status quo already correct); no for (b) and (c) | (c) some documents should be corrected regardless of any other build | Keep the toggle off by default (no change); build (b) before quoting decision 262 again; fix (c) opportunistically |
| 6 | Remaining speed-ups | Each proposal its own commit, engineering time only; no visit | How much faster the Closed-Loop and Stim Optimizer pages can load without moving any number | No for the ten speed proposals (equality-preserving, same pattern as decisions 266–269); yes for proposal 2's new saved-answer kind | Nothing for most; proposal 2 needs a go-ahead on where the new saved rows live | Build in the order the report gives (1, 3, 5, 4, then 2); check the stale-pain-rating question first |
| 7 | HamD6 (different study, RCSchronicpain) | Already done; not a BRAVO decision | See below | No — not this project's data | N/A | For information only |

**Option 1.** A saved, descriptive check that asks whether decision 253's block-to-block swing at one
unchanged setting is something the whole nineteen-setting-period group was doing regardless of current,
or specific to the one setting most often delivered. It reuses code already built for decision 253 and
adds no new risk; like every other control analysis on this platform it reports and never blocks. Its
own power calculation says it can reliably catch a large, setting-specific swing but not a small one
riding on top of a shared trend — worth saying on the card, not hiding.

**Option 2.** Three separable pieces answering three different questions: whether the left-side bands
track pain with no current running at all (a tightly-timed repeat of the very first current-free
window, done properly this time); whether that same signal is the stimulator's own half-rate echo at
55 Hz (swap to 60 Hz for a few minutes, current and pulse width unchanged); and whether a short
lingering effect of current exists that the existing memory-length check could not rule out (a
multi-day hold, move, and return, at home). The rate swap needs no interruption to stimulation and is
the safest, cheapest, most decisive of the three. The zero-current block asks the patient to go without
their programmed stimulation for hours; that needs its own fresh safety review regardless of what
happened a year ago. Given decision 272's finding, I recommend adding one more small piece: at least
one step of the next ladder taken in decreasing order before increasing, so the carry-over question can
finally be separated from ordinary drift.

**Option 3.** Decision 196 says time enters no calculation anywhere, because on this record time and
the settings tried are too entangled to tell apart (measured, not assumed — decision 194 already found
a time-input model absorbing a real setting's effect). Nothing here argues for reversing that. The
question is narrower: should the block-of-time warning decision 253 already computes be shown next to
every recommended current, not filed inside a separate research card a clinician might never open. That
costs nothing new to compute and blocks nothing; it is a display decision, not a modelling one.

**Option 4.** The report specifies a research-grade detector (every band read together, current taken
out with a shape that can turn over) and a device-realistic one (one band, the device's own averaging
and persistence timing) side by side, and asks the PI to settle three choices before any of it is
built: which pain ratings to use, whether to keep pain continuous or split it into high/low groups, and
whether to build the device's timing in from the start or check it only at the end. The report's own
recommended defaults — REDCap ratings as the primary reading with clinic-sheet ratings shown separately
and never merged; the continuous pain score for the research tier and a cut-off only where the device
tier needs one; the device's real timing built into the device-shaped tier from the first pass — line
up with what report 5 independently concluded about clinic-sheet ratings. I recommend adopting them as
a package rather than deciding the three questions separately.

**Option 5.** Part (a): whether clinic-sheet ratings should be included, by default, in the number the
sign-off sheet shows a clinician (the deployment ROC). The evidence — this project's own numbers
(adding sheets makes the number worse, 0.623 to 0.564, and makes nearly every band on the grid look
positive at once, which a real single-band signal should not do) and outside literature on ratings
taken during an active treatment change — both point the same way: keep the default off, as it is
today, and build the still-missing check (current taken out of the sheets-on number) before trusting it
either way. Part (b): the specific "p = 0.04" figure cannot be reproduced by the tested code and should
be retired from future writing in favour of the honest, corrected description in section 3(b) above.
Part (c): three 2026-09-24 research documents still state retracted numbers from before decision 262's
correction as current fact; low-priority, but worth a one-line correction each since they will be read
again.

**Option 6.** Ten proposals to make the Closed-Loop and Stim Optimizer pages load faster with no number
changing, each already checked for exactness in the report and several already measured live (the
recording-set-identity fix is proven exact and 38 times faster). None needs a scientific ruling; most
need only the routine go-ahead to implement, one commit at a time, each with its own before/after field
count on live data, per this project's own standing rule. One item (rebuilding the settings history
only for changed files) is a genuinely new kind of saved answer and is the one piece here that deserves
an explicit go-ahead rather than a routine one. Separately, and more urgent than any of the ten speed
items: the report found that two of the Closed-Loop page's numbers may be built from a saved file whose
label does not track which pain reports it contains, which is a correctness risk, not a speed one, and
should be checked first.

**Option 7 (different study).** A separate MATLAB repository (RCSchronicpain) asked whether a
symmetric, bell-curve statistical model is the right way to compare a six-item mood questionnaire
between two blinded stimulation conditions. Read for completeness only; no BRAVO decision follows from
it.
- The recommended model is a count-based model built for non-negative whole numbers with extra
  allowance for uneven scatter between patients, in place of the original bell-curve model.
- The choice of model does not change the answer: every alternative tried, including a model-free
  reshuffling test, agrees in direction and none finds a clear difference between the two conditions.
- The two code branches merge cleanly with no conflicts.
- One tracked file holds a research-database credential and was deliberately not opened; it needs a
  manual check for a live secret before that branch is merged or shared.
- This is a different patient population and a different repository from BRAVO; no number from it
  belongs in this project's record.

---

## 5. Proposed order of work

**Lane A — build now, no new PI ruling needed beyond the routine go-ahead to implement (CLAUDE.md §8
rule 8 still applies: a plan is not permission, so each item still needs his go-ahead before landing,
but none of them asks him to choose between named alternatives).**

1. **Check the stale-pain-rating question (Option 6's correctness finding) first.** One comparison: a
   freshly built evidence-inputs file against today's saved one, on live data. Cheap, and it bears on
   whether two numbers on the Closed-Loop page already mean what they say.
2. **Fix confound_diagnostic.py to compute a real p-value for the current-adjusted reading** (Option
   5b), so decision 262's finding, and any future rerun of it, can be quoted honestly.
3. **Build the regression-to-the-mean check** (Option 1), following the same non-blocking pattern as
   every other saved control analysis.
4. **Correct the three stale research documents** (Option 5c) — one line each, pointing to decision
   262's correction.
5. **Speed proposals 1, 3, 5** from Option 6 (recording-set identity, grid medians, joined-table
   labels) — each already specified with its own equality proof, lowest risk first.

**Lane B — needs the PI's ruling before any code is written.**

6. Option 3's yes/no: show decision 253's warning wherever a current is recommended.
7. Option 4's three choices (or approval of the report's recommended defaults as a package).
8. Option 5a's status quo confirmation (keep clinic-sheet ratings off by default) plus a go-ahead to
   build the current-adjusted version of that same number.
9. Option 6's proposal 2 (a new saved-answer kind for the settings history) and proposal 4 (the
   simulation loop compiled) — larger, still equality-proof-backed, but a bigger piece of work each.

**Lane C — needs a clinic visit, in this order.**

10. **The rate swap (Option 2, part b).** Cheapest, safest, and answers the harmonic question outright
    before any more analysis time is spent on the 24.5–27.5 Hz family.
11. **A ladder with a down-first step** (the fix decision 272's own finding calls for, echoed in Option
    1 and Option 2). This can likely ride along with whatever visit is scheduled next for other reasons.
12. **The tightly-timed zero-current block** (Option 2, part a), pending a fresh safety review.
13. **The hold-and-return home schedule** (Option 2, part c), pending confirmation that take-home
    streaming or sensing-only logging is workable, and that a caregiver can hold the blind.

---

## 6. Questions for the PI

1. Should the stale-pain-rating question in the Closed-Loop evidence-inputs file (section 3c) be
   checked before any other item in this document proceeds? (Recommended: yes.)
2. Approve building the regression-to-the-mean check as a new saved, non-blocking control analysis,
   run first on the 55 Hz / 60–160 µs left-leg group already flagged in decision 253? (Yes/No.)
3. Approve fixing confound_diagnostic.py to compute an honest, correctable p-value for the
   current-adjusted reading, replacing today's inside/outside-the-chance-range-only report? (Yes/No.)
4. Time rule: keep decision 253's block-of-time warning where it is today, on a separate research card,
   or show it next to every recommended current on the Stim Optimizer page? (Choose one; no change to
   any recommendation either way.)
5. Band detector: adopt the report's three recommended defaults as a package — REDCap ratings primary
   with clinic-sheet ratings shown separately; the continuous pain score for the research tier and a
   cut-off only for the device-realistic tier; the device's real timing built in from the start only for
   the device-realistic tier — or specify a different combination? (Choose the package, or name changes.)
6. Keep the Closed-Loop deployment summary's clinic-sheet-ratings toggle off by default, as it is today,
   while a current-adjusted version of that number is built alongside it? (Yes/No.)
7. Of the next clinic visit's three pieces — the pulse-rate swap (about 1–2 hours, no interruption to
   stimulation), the tightly-timed zero-current block (several hours off stimulation), and the
   multi-week take-home hold-and-return schedule — which should be scheduled, and in what order?
   (Choose among: rate swap only; rate swap then zero-current block; all three; none yet.)
8. Should the next ladder include at least one step taken in decreasing order before increasing, so the
   carry-over question decision 272 left open can be separated from ordinary drift? (Yes/No.)
9. Approve Option 6's ten speed proposals to proceed in the order given, each as its own commit with its
   own before/after proof, with proposal 2 (a new saved-answer kind for the settings history) called out
   for a separate, explicit go-ahead? (Yes/No, with proposal 2 named separately.)

---

## 7. Reports and key references

Full reference lists, with DOIs and verification notes, are at the end of each source report; only
citations a report itself marked as independently checked are pointed to here.

- **Report 1** (`01_regression_to_the_mean.md`): the standard regression-to-the-mean tutorials
  (Barnett et al. 2005; Whitney & Von Korff 1992, chronic pain specifically; Morton & Torgerson 2003)
  and the N-of-1 single-patient trial guides (Kravitz/AHRQ 2014; Kravitz et al. 2018) behind its
  repeat-visit recommendation.
- **Report 2** (`02_next_clinic_visit_protocol.md`): carry-over timing in spinal-cord stimulation
  (Meier et al. 2024) and Parkinson's DBS (Temperli et al. 2003); the stimulator-echo mechanism
  (Sermon et al. 2024; Mathiopoulou et al. 2025; Hammer et al. 2022); the insertional-effect literature
  bounding why an early current-free window is not a clean test (Hamani et al. 2024; this project's own
  Shirvalkar et al. 2020).
- **Report 3** (`03_time_rule.md`): the tremor-habituation review (Peters & Tisch 2021) and this
  project's own prior finding that a two-state model of the ratings is not identifiable
  (`research_2026-09-22_SYNTHESIS`).
- **Report 4** (`04_band_detector.md`): the cost of splitting continuous data into groups (Cohen 1983,
  read in full; Preacher et al. 2005, read in full) and the pain-recall-bias literature (Haase 2023,
  read in full) behind its three choices.
- **Report 5** (`05_small_rulings_and_stale_numbers.md`): DBS-programming rating reliability under
  blinding (Off et al. 2026) and the verbal-suggestion effect on pain during stimulation changes
  (Rosenkjær et al. 2024), both read directly; plus the direct code reading in
  `BRAVO/modules/Biomarkers/routines/confound_diagnostic.py` and
  `BRAVO/modules/ControlAnalyses/runners.py`, independently re-verified for this synthesis.
- **Report 6** (`06_remaining_speed_ups.md`): live, bridge-run measurements on RCS08 only; no external
  literature.
- **Report 7** (external study, path outside this repository): HAM-D6 psychometrics (Bech et al.,
  several years) and count-data modelling guides (Knief & Forstmeier 2021; Harrison 2014); not a BRAVO
  source and not re-cited here beyond this summary line.

Internal decision references used throughout this synthesis: decisions 145, 160, 186, 196, 199, 210,
213, 215, 217, 220, 229, 230, 233, 234, 236, 237, 238, 240, 241, 242, 253, 258, 260, 262, 264, 265, 266,
269, 272 (`DECISIONS_and_open_items.md`).
