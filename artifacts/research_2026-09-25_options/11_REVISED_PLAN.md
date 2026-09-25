# The plan after the critiques (2026-09-25)

> For the PI. What was done today and what it found; what the three critiques changed; the plan in
> four lanes, each item with the problems likely to meet it; and the questions only you can answer.
> Sources: the seven option reports (01-07), the synthesis (00), the three critiques (08 science,
> 09 feasibility, 10 your rulings and writing rules), the scan of every earlier handoff
> (`artifacts/pending_items_from_handoffs_2026-09-25.md`) and decisions 270-276.

Terms used once and not again: a **settings period** is one stretch during which one exact current,
rate and pulse width was programmed. **Shuffling the data to see what happens by chance** is how
every p-value here is made: the pain ratings are rotated in time, keeping their day-to-day
persistence, and the question is how often the rotated data do as well. A **folded multiple of the
stimulation rate** is a whole multiple of the pulse rate that, because the device samples the brain
signal 250 times a second, reappears at a lower frequency (at 55 Hz, five times the rate, 275 Hz,
reappears at 25 Hz). A band that carries one is flagged for care, not disbelief (your correction of
2026-09-06).

---

## 1. Done today, each with its number

| # | What | What it found | Where it is |
|---|---|---|---|
| 270 | The tablet's participant sync | Works for RCS08 again: 569 sessions, chronic data from 2025-07-16 18:10 | committed |
| 271 | CI installs numba | The compiled design-rule filter's equality test now runs in CI | committed |
| 272 | Up the ladder and down (carry-over) | Of 30 clinic and at-home sheets since implant, one visit (2026-09-16) rated the same current on the way up and the way down: 8 currents, every fall after its rise, so carry-over cannot be told from pain drifting over the visit. Down minus up on the 0-10 score: left ladder -0.75 over 4 currents, right +1.00 over 4. A setting rated twice about a minute apart: -0.06 (-0.26 to +0.27), 62 times on 13 visits | Stim Optimizer page, control analyses card |
| 273 | Pain ratings saved under a label that ignored them | The Closed-Loop page's saved inputs held the settings periods with their pain ratings, filed only under the recordings and constants. Measured: the file on disk matched a fresh build in every value (92 settings periods; written after the newest report), so the fault had not yet produced a wrong number. Fixed: pain is rebuilt on every request from a table filed under the reports. The Closed-Loop report before and after: 59,169 fields, 3 differing (timing only); no cost in time | committed |
| 274 | Log noise | The first design-rule fit in each server worker wrote 38,760 lines of numba's internal checking; silenced below warnings | committed |
| 275 | Regression to the mean | The fall decision 253 found at 1.6/1.2 mA (55 Hz, 60/160 us: +1.53 / +0.54 / -0.05 across three blocks of time) is the group's own pattern, not something about that current pair: a group of 8 drawn from the same 19 settings periods swings as much in 84.6% of all 75,582 ways to draw it, and a swing that size appears in 34% of 68 runs elsewhere. So 253's sentence "the setting did not change and the patient's response to it did" should read "the whole group's readings moved over those weeks" | Stim Optimizer page, control analyses card |
| 276 | Decision 262's "p 0.04" | It was read against the wrong shuffles. Against its own: the left 1-3 pair with the current taken out gives p 0.030 (60 s of signal, 187 ratings) and 0.035 (30 s, 201); the other ten of the 12 combinations tried give 0.21 to 0.86. Corrected for the 12, about 0.21. A lead, not a finding | Biomarkers page, control analyses card |

| 277 | One harmonic check | At 55 Hz the fourth and fifth multiples of the rate fold to 30 and 25 Hz, so every band from 22.5 to 29.5 Hz carries a folded multiple, 24.5 Hz included (decision 236 had called it the one clean band); 9 of 22 bands stay clear. At 60 Hz the landings are 10, 20 and 30 Hz | Stim Optimizer page, titration card and readiness table |
| 278 | Recording-set identity once per request | Closed-Loop report 46.8 / 41.8 / 38.3 / 35.9 s (before / after / before / after); 59,169 fields, 3 differing (timing) | committed |
| 279 | The grid's medians in one computation | 12.5 / 8.9 / 11.2 / 7.8 s; 34,129 fields, 19 differing (timing) | committed |
| 280 | Page label and three-week note; stale record corrected | "log-power" gone from the ROC panel; the sign-off card says the mixed model leaves out the first three weeks | Closed-Loop page |

**Held:** the clinic-sheet correction-cell fix (P-13), saved as a patch; you approved its live check on
2026-09-25, and it runs next, counts only.

**RCSchronicpain (the other study, read and edited only through headless MATLAB, nothing merged or
pushed):** the HamD6 report (sent to you); the two plots recoloured by condition and left
uncommitted on `refactor_stages123`; and the pre-merge checks, of which one needs you (Lane 0).

**The handoff scan:** 44 BRAVO handoffs, 187 items after merging repeats: 93 done, 53 made moot, 21
still pending, 20 needing you (`artifacts/pending_items_from_handoffs_2026-09-25.md`); RCSchronicpain
14 handoffs, 7 pending and 11 needing you (sent separately; it is not this project's record).

---

## 2. What the critiques changed

**Accepted, and what was done about it**

1. *Check the saved pain ratings before anything else* (all three critiques). Done: decision 273.
2. *Decision 253's causal sentence is not earned* (science, critical). Tested: decision 275 says the
   swing is the group's, not the setting's. The digest's wording should follow (one line; A3).
3. *"About 0.48" pretends to a precision nobody has* (science, critical). Replaced by the reading's
   own shuffle (276). The number of combinations is 12, not 4 as the critique supposed: the saved run
   covers six sensing pairs at two lengths of signal. Corrected, about 0.21.
4. *The rate swap should not wait behind the builds* (science, critical). Agreed: it has no dependency
   on any build and runs on the clinic's calendar. It moves to its own track, starting with Lane 0.
   The harmonic finding of section 3 (A1) makes it more pressing, not less.
5. *Quote the carry-over test with its numbers* (science, critical). Done in 272 and above.
6. *"Decisive" overstates the rate swap* (science, major). It is "informative". Before it runs, state
   the smallest change it could detect; a result of no change means repeat it longer, not close it.
7. *The visit power figures treat days as independent* (science, major). Daily pain ratings are
   correlated with the days around them, so the 52-98 days figure is too few. Check proposed (A4).
8. *The clinic-sheet effect may be electrical, not psychological* (science, major). Nearly every band
   moves with pain when the sheets are included (decision 229); a broad electrical change during
   active stepping of the current would do that too. Check proposed (A5).
9. *Ethics approval, device facts in writing, staff time, and honest labels* (feasibility, critical and
   major): a stimulation-off block and a blinded home sequence need research-ethics coverage, not only
   your sign-off; the home plan relies on "Single Threshold Inverse" being sensing only, which this
   project's device document says and outside descriptions dispute; nobody has checked whether a
   rate-only change dips the current; the visit needs 4-5 hours of staff time at the tablet; a patient
   with years of stimulation can likely feel current changes, so the home sequence is "open-label",
   not "blinded"; a band at 29.5-30 Hz is for observation only, outside the device's range. All in
   Lane 0 and Lane C below.
10. *Writing* (rulings and language): three questions split, bare "record", "null" and "direction"
    replaced, code names moved to brackets. Applied here. No standing ruling was contradicted.

**Not accepted**

- "The live comparison has not been run" (feasibility): it has, decision 273.
- "The code's family is 4" (science): the saved analysis ran 12.

---

## 3. The plan

### Lane 0: only you can do these, and Lane C waits on them

| Item | Why | Likely problems |
|---|---|---|
| 0.1 Rotate the three REDCap tokens tracked in RCSchronicpain's `credentials/` file (two on `main` since April 2026, a third on the branch; the repository is private). Then the file can be untracked and a template kept | They are in the repository's history; anyone given the repository has them. Not opened or printed by any agent | Removing them from history needs a rewrite of `main`, which every clone must follow; rotating makes the history harmless without it |
| 0.2 Confirm research-ethics coverage for a planned stimulation-off block and a multi-day home sequence | The protocol may cover clinical titration only | An amendment can take months; that sets the date of Lane C items 3 and 4 |
| 0.3 From Medtronic in writing: (a) does Single Threshold Inverse change the delivered current; (b) does a rate-only change dip the current; (c) can the home controller trigger more than the 10-minute log | The home plan and the rate swap rest on these | If (a) is "yes", this project's device document is wrong and its closed-loop compatibility list (`COMPATIBLE_THRESHOLD_MODES`) needs a second look |

### Lane A: built without a ruling (your /swarm-execute of 2026-09-25)

| Item | State | Likely problems |
|---|---|---|
| A1 One harmonic check: the Stim Optimizer folds every multiple of the rate, as the Biomarkers check does, and says "carries a folded multiple", never "measures the stimulator" | Done (277) | Confirmed: at 55 Hz every band from 22.5 to 29.5 Hz carries a folded multiple (25, 27.5 or 30 Hz), including the whole family that rises with pain on the left; decision 236's "24.5 Hz, the one clean band" goes. The next ladder at 55 Hz then cannot watch a clean band in that family, which makes the rate swap a precondition rather than an option |
| A2 Speed-ups: the recording-set identity once per request; the grid's medians in one computation | Done (278, 279), both exact | None left |
| A3 The "log-power" label on the Closed-Loop ROC panel; dated corrections in three research documents that quote withdrawn numbers; the digest's stale open item and 253's sentence | Done (280) | The titration card's "analyse at" row still says a band near a harmonic "is struck"; whether the plan should drop such bands is a separate question |
| A4 Day-to-day correlation of the pain ratings, to correct every visit-count estimate | Proposed | Needs only the REDCap series; an hour's work |
| A5 The electrical-artifact check: during stepped current, do bands with no plausible pain relationship move together as much as the pain-linked ones? | Proposed | The clinic-sheet ratings sit on the same stepped currents, so a positive answer implicates the current, not the ratings |
| A6 The handoff scan's other 20 pending items, most harmful first: the page never says the first three weeks are left out of the mixed model (P-04); saved files filed under a hand-written version name (P-05); a sheet cell with a written correction misread (P-13); the "proven better" check leaves out a covariance term (P-14) | Proposed | Each is small; P-14 changes a published verdict's arithmetic and needs its own live proof |
| A7 Further exact speed-ups (the joined table's labelling, the simulation loop compiled as decision 269 did, the design rule's local-level filter) | Proposed | The per-file settings history is a new kind of saved answer and needs its write-then-mark rule and your separate yes |

### Lane B: your rulings (section 5)

### Lane C: a clinic visit, after Lane 0

| Order | What | What it tells us | Likely problems |
|---|---|---|---|
| 1 | The rate swap: 55 then 60 then 55 Hz, current and pulse widths fixed, BrainSense streaming throughout, 30-60 s discarded after each change; plus one ladder that steps DOWN first | Whether the left 21.5-27.5 Hz family follows the brain or the stimulator; whether pain on the way down differs from the way up when the fall comes first | Informative, not decisive; the patient may feel 60 Hz; about 1-2 hours of staff time; 0.3(b) unanswered |
| 2 | The timed stimulation-off block (recordings within 1-2 minutes of each rating) | Whether the left bands track pain with no current at all | Needs 0.2 and a fresh safety review; even a clean result stays a lead (one day against 52-98 needed, more once A4 is in) |
| 3 | The home hold-and-return sequence, open-label | Whether a current's effect lingers for days | Needs 0.2 and 0.3(a); the chronic log stays on the band it has today unless (a) is answered |

---

## 4. Problems likely to meet the whole plan

1. **The weeks confound everything already on file.** Current, rate and calendar moved together
   (days against pain -0.61, against left current +0.39, against rate -0.48). No analysis of existing
   data separates them; 272, 275 and the time-rule report all end at the same place. Only a new
   design separates them: order reversed, and the same setting repeated weeks apart.
2. **At 55 Hz the pain-linked bands all carry a folded multiple of the rate** (277). So no
   analysis at 55 Hz can say whether those bands follow pain or the stimulator, and your ruling 233(3)
   (the ladder at 55 Hz) needs revisiting against the rate swap.
3. **One visit settles nothing** (METHODS section 7): on 15 ladder steps a band with no pain
   relationship reads beyond 0.4 once the current is out about one time in eight (decision 237).
4. **Ethics and device answers set the calendar**, not the builds (Lane 0).
5. **The container and its bridge are the only place Biomarkers work can be tested or proved.** The
   bridge is one job at a time and was queued most of today; a stall stops every proof.
6. **Security, outside this project's code:** the RCSchronicpain tokens (0.1), and 4.7 GB of loose
   device session files in this project's bridge folder (outside git; handoff item N-15), whose file
   names may carry patient names.

---

## 5. Questions for you

Each can be answered yes or no, or by naming one option.

1. RCSchronicpain: once you have rotated the tokens, may I untrack the credentials file and add a
   template, on the branch only, not pushed?
2. RCSchronicpain: commit the two recoloured plots on `refactor_stages123` (local, not pushed)?
3. RCSchronicpain: make the Poisson mixed model the primary HamD6 model, the Gaussian one a sensitivity
   check?
4. Show decision 253's block-of-time warning next to every recommended current on the Stim Optimizer
   page (it changes no recommendation)?
5. The research band detector:
   - 5a: REDCap ratings primary, clinic-sheet ratings shown separately and never merged?
   - 5b: pain kept as a number for the research version, split into two groups only for the
     device-shaped version?
   - 5c: the device's own timing built into the device-shaped version from the start?
6. Keep the clinic-sheet ratings off by default in the deployment summary, and build the same number
   with the current taken out beside it?
7. Build checks A4 (rating correlation) and A5 (electrical artifact)?
8. The next visit: rate swap with a down-first ladder only; or that plus the timed off-block; or all
   three (each after Lane 0)?
9. Every pain-linked band carries a folded multiple at 55 Hz (277): run the next ladder at 60
   Hz instead of 55 (revisiting ruling 233(3)), or keep 55 Hz and run the rate swap first?
10. Further speed-ups A7, one commit each with its proof; and separately, the per-file settings
    history?
11. From the handoff scan, three that are only yours: delete the 4.7 GB of loose session files in the
    bridge folder (N-15)? Consent to an outside code review service (N-19)? The June mock-ups at the
    repository root: keep, archive or delete (N-20)?
