# Next visit, draft protocol: the rate swap, a ladder that steps down first, a timed stimulation-off block and a home hold-and-return sequence

> Draft for the PI (Prasad Shirvalkar), first written 2026-09-25 and **revised 2026-09-25 with your
> rulings of that day**: the visit covers all three parts (your answer 8 to the revised plan); the
> ladder stays at 55 Hz and the rate swap runs first (answer 9; ruling 233(3) stands); stimulation
> off is covered by the research protocol ("Stim off is OK, it's in our protocol"); the device
> changes rate without stopping BrainSense streaming (Lane 0 item 0.3(d), first half); the ladder's
> down leg keeps 1 mA steps (your ruling of 2026-09-14, decision 160); a second rate-swap cycle
> only if really needed. **Nothing is scheduled and nothing here is an instruction to program
> anything.** Lane C of `artifacts/research_2026-09-25_options/11_REVISED_PLAN.md`, with every
> accepted critique folded in (`08_critique_science.md` M3; `09_critique_feasibility.md` on staff
> time, discard windows, the 29.5-30 Hz band, open-label wording, prerequisites 0.2 and 0.3, and
> stating the likely outcome of the off block beside its burden), decision 277 (the one harmonic
> check), and the off block and home sequence of the options report
> `artifacts/research_2026-09-25_options/02_next_clinic_visit_protocol.md` (report 02). Every number
> below is quoted from a decision with its number or from report 02, or was computed for this draft
> on 2026-09-25 by a read-only script whose name is given; none is carried forward from a document
> without being re-read. The questions still open are listed in §11.

**Words used here.** A **ladder** is a planned run of current steps within one visit, one setting at
a time. A band **carries a folded multiple of the stimulation rate** when a whole multiple of the
pulse rate, folded down by the device's sampling of the brain signal at 250 times a second, lands
within 2.5 Hz of the band's centre (half the 5 Hz band width). At 55 Hz, five times the rate
(275 Hz) reappears at 25 Hz. That is a statement about where numbers land and needs care, never
disbelief (your correction of 2026-09-06); it does not say the band measures the stimulator.
**Band power** is always raw power in the device's units; log power enters nothing here
(decision 202). **Open-label** means the patient may know, or feel, which setting is running, and no
reading assumes otherwise. A **hold** is a stretch of days on one unchanged setting.

---

## 1. What the visit asks

1. **Does the power in the left 21.5-27.5 Hz family follow the stimulation rate?** At 55 Hz every
   band from 22.5 to 29.5 Hz carries a folded multiple of the rate (decision 277). If part of the
   power in those bands is locked to the stimulator's pulses, moving the rate to 60 Hz moves where it
   lands, and the bands it leaves should fall. If the power is the brain's own and not locked to the
   pulses, it should stay where it is. Current and pulse widths are held fixed; only the rate moves,
   55 then 60 then 55 Hz.
2. **Does pain on the way down differ from the way up when the fall comes first?** On the one visit
   that rated the same current on both legs (2026-09-16), every fall came after its rise, so a
   difference could be carry-over or could be pain drifting over the visit (decision 272: down minus
   up on the 0-10 score, left ladder -0.75 over 4 currents, right +1.00 over 4). A ladder that starts
   by stepping down reverses the order.
3. **Do the left bands still rise with pain when no current is running at all, with each rating
   matched to a recording taken within minutes of it?** In the one stretch with both sides at 0 mA
   (2025-07-16 to 08-22), L 1-3+ at 21.5 and 22.5 Hz rose with the 0-100 pain scale (+0.38 and
   +0.34, decision 264(1)), but the ratings and recordings were matched only by day, typically 5.1
   hours apart (report 02). The timed stimulation-off block repeats that reading with a recording
   started within 1-2 minutes of each rating.
4. **Does a current's effect on pain linger for days?** A current with memory never predicted pain
   better than the current in force (decision 262(b)), but the currents on file were rarely held and
   then returned to, which is the one pattern that would show a short memory (report 02). The home
   sequence holds the left current for 3 to 4 days at a time, moves it, and returns to it.

**If the day is cut short**, keep the parts in this order: the rate swap, the ladder, the off block.
The home sequence starts at the end of the visit only if its research-ethics coverage has been
confirmed by then (§2); nothing else in the visit depends on it. Every answer will be a lead to
repeat, not an established result (METHODS §7; one visit day settles nothing).

---

## 2. Before it can be scheduled

| Item (numbering from the revised plan's Lane 0) | State on 2026-09-25 | What this visit does meanwhile |
|---|---|---|
| **0.2** Research-ethics coverage, **for the stimulation-off block** | **Answered.** Your words: "Stim off is OK, it's in our protocol" | The off block is in the visit plan (§6.1) |
| **0.2**, **for the multi-day home sequence** | **Not stated.** Report 02 asks for a separate safety and rescue plan for it, since a pain flare can outlast the visit | Open. Until it is answered the visit ends by restoring the settings in force, which is also the first hold of the home sequence, so starting it later loses nothing |
| **0.2**, **for the rate change to 60 Hz** | Not stated separately. The rate change is made for a research question, and 60 Hz has never been programmed on this patient (the rates in the device's settings history are 10, 55, 110, 125, 130, 145 and 165 Hz; read 2026-09-25) | Open. If the coverage does not extend to it, the ladder and the off block can run without it |
| **0.3(b)** Does a rate-only change dip the delivered current? | Open. Nothing in this project measures it: the ramp times in `DEVICE_percept_rc.md` §9 are for current steps only | The minute after each rate change is discarded, and extended until the tablet shows the current back at its setting, with that time written on the sheet (built into the change rows of §9) |
| **0.3(d)** Can the rate change without stopping BrainSense streaming? | **Answered: yes** (you, 2026-09-25). Streaming runs through both rate changes with no restart planned around them | — |
| **0.3(d)** Can the rate change on one side alone? | Open. The two sides have carried the same rate in all but 1 of 3,344 settings rows aligned in time (device settings history, read 2026-09-25) | Not needed here: this visit changes the rate on both sides together. It matters only for a later left-only repeat |
| **0.3(a)** Does Single Threshold Inverse change the delivered current? | Open | Not needed: the chronic log is not re-pointed. It stays as it is today, on L 1-3+ at 23.44 Hz, and the home sequence reads it as it is (the revised plan's Lane C row 3) |
| **0.3(c)** Can the home controller trigger more than the 10-minute chronic log? | Open | Not needed: the home sequence uses the ratings and the chronic log as they are today |

Also agreed in advance with the clinical team, not improvised on the day: the stop rules of §6,
including a fresh clinical review of the off block (report 02: the only earlier stretch at 0 mA had
81% of its ratings at 8 or 9 out of 10), and a second person for ratings during the rate swap and
the ladder (§6.3).

---

## 3. The settings the visit holds

Read from the device's own settings history on 2026-09-25 (the newest row per side of the stored
therapy settings); **confirm on the tablet on the day, and if the currents in force differ, keep the
day's currents and shift the ladder's steps and the home holds to start from the left current in
force.**

| | Left | Right |
|---|---|---|
| Stimulating contacts | C+2- (cathode 2a-2b-2c) | C+1-2- (cathode 1a-1b-1c-2a-2b-2c) |
| Current | 3.0 mA | 2.5 mA |
| Pulse width | 100 µs | 150 µs |
| Rate | 55 Hz | 55 Hz |
| Sensing pair the device allows (decision 217) | L 1-3+ | R 0-3+ |

The safety ceiling is 4.5 mA each side (decisions 145, 160). Nothing in the clinic part of the visit
goes above 3.0 mA. The home sequence's upper hold, 4.0 mA on the left, is 0.5 mA under the ceiling;
the left was held at 4.0 mA for at least a week before 2026-07-22 and at 4.5 mA from then to
2026-08-12 (decision 252). Moving from 55 to 60 Hz delivers 9.1% more pulses a second at the same
charge per pulse. 60 Hz is inside the rates the device's closed-loop mode accepts (55 Hz and above,
decision 138).

---

## 4. Which bands carry a folded multiple at each rate

Computed 2026-09-25 with the Stim Optimizer's own check (`titration_plan.harmonic_avoidance`, which
takes its landings from `Biomarkers/routines/analytics.harmonic_landings_hz`, multiples up to the
eighth, 2.5 Hz either side of each of the 22 centres, plus half, a quarter and three quarters of the
rate, which the check adds itself).

- **At 55 Hz** the fourth multiple (220 Hz) lands at 30 Hz and the fifth (275 Hz) at 25 Hz; half the
  rate is 27.5 Hz and a quarter 13.75 Hz. **9 of 22 centres are clear**: 8.5-10.5 and 16.5-21.5 Hz.
- **At 60 Hz** the fourth multiple (240 Hz) lands at 10 Hz and the eighth (480 Hz) at 20 Hz; half the
  rate is 30 Hz and a quarter 15 Hz. **4 of 22 centres are clear**: 23.5, 24.5, 25.5 and 26.5 Hz. (The
  eighth multiple is usually much weaker than the fourth or fifth, but the check flags it the same way.)
- The device's own power reading on L 1-3+ sits at its programmed centre, 23.44 Hz: within 2.5 Hz of
  the 25 Hz landing at 55 Hz, clear of every landing at 60 Hz.

| Centre (Hz) | 55 Hz | 60 Hz | Role in the swap |
|---|---|---|---|
| 8.5, 9.5, 10.5 | clear | carries (10 Hz, 4th multiple) | moves in |
| 11.5 | carries (13.75, quarter) | carries (10) | no contrast |
| 12.5-15.5 | carries (13.75, quarter) | carries (15, quarter; 12.5 also 10) | no contrast |
| 16.5 | clear | carries (15, quarter) | moves in |
| 17.5-21.5 | clear | carries (20 Hz, 8th multiple; 17.5 also 15) | moves in |
| 22.5 | carries (25, 5th) | carries (20, 8th) | no contrast |
| **23.5, 24.5** | **carries (25, 5th)** | **clear** | **moves out** |
| **25.5, 26.5** | **carries (25, 5th; 27.5, half)** | **clear** | **moves out** |
| 27.5 | carries (30, 4th; 25, 5th; 27.5, half) | carries (30, half) | no contrast |
| 28.5 | carries (30, 4th; 27.5, half) | carries (30, half) | no contrast |
| 29.5 | carries (30, 4th; 27.5, half) | carries (30, half) | **observation only** (below) |

**What each result would look like.**

- If part of the power in 23.5-26.5 Hz at 55 Hz is locked to the pulses, those four bands fall at
  60 Hz and come back at 55 Hz; the bands that "move in" may rise at 60 Hz. In the PSD computed from
  the voltage trace at fine frequency resolution, a narrow peak at exactly 25.0 Hz under 55 Hz would
  be absent under 60 Hz, and a peak at 27.5 Hz (half the rate) would move to 30.0 Hz.
- If the power in 23.5-26.5 Hz is the brain's own and not locked to the pulses, those bands read the
  same at both rates within the detectable change of §5. That would count against the two
  stimulator-locked explanations (a folded pulse multiple; the brain locking to half the rate). It
  would not by itself show the band tracks pain.
- **The 29.5 Hz band is for observation only.** It spans 27-32 Hz, partly above the firmware's 30 Hz
  limit on where a closed-loop sensing band may sit and outside the range of frequencies ever checked
  against the device's own reading (7.8-28.3 Hz, `DEVICE_percept_rc.md` §6). It can show where half
  the rate moves to; it can never itself become a band the device senses from.

---

## 5. The smallest change the rate swap could detect, and when a second cycle is needed

**Source.** The stored ladder points (`three_source_run_points`, the table behind the Closed-Loop
page's three-source comparison), L 1-3+, the route through the voltage trace, read-only on
2026-09-25 (`BRAVO/_agent_bridge/_rateswap_mdc.py`). The table holds 3,278 rows on L 1-3+ across 5
runs, but **only one run held the same current more than once: three currents, each reached once
on the way up and once on the way down, at 55 Hz.** Each reading is the average over a 30-second
settled window (10 pieces of 3 seconds). That gives 66 band-and-current pairs (22 bands x 3
currents), but they share 3 occasions, so they are not 66 independent measurements, and the scatter
below is a rough estimate.

**What the pairs show.** At the same current, the reading on the way down was on average 22% higher
than on the way up (fall minus rise, as a fraction of the pair's average: mean +0.22, standard
deviation 0.23 over the 66 pairs; +0.33 to +0.35 in 22.5-26.5 Hz). Every fall came after its rise,
so this offset may come from order and time rather than from whether the current was rising or
falling, which is the second reason for the down-first ladder (§7). The device's own power reading
at 23.44 Hz shows the same thing: +0.33 over its 3 pairs.

**The scatter of one reading.** Taking the 22% offset as a real effect of order and removing it, a
single 30-second reading scatters by about 16% of the band's power (0.23 / √2 = 0.164). Counting the
offset as scatter too, 23% (root mean square of the pairs, 0.225). In the four "moves out" bands,
23.5-26.5 Hz, the first figure runs from 12% to 19% band by band, on 3 pairs each.

**The smallest detectable change**, as a fraction of the band's power at 55 Hz, with 80% power at a
two-sided 5% significance level, treating the scatter as known:

| Design | Contrast | Scatter 16% | Scatter 23% | Scatter 16%, corrected for the 4 "moves out" bands |
|---|---|---|---|---|
| **One cycle, 55-60-55 (the default)** | 60 Hz block against the two 55 Hz blocks | **56%** | 77% | **67%** |
| Two cycles, 55-60-55-60-55 (only if needed, below) | two 60 Hz blocks against three 55 Hz blocks | 42% | 58% | 50% |

These treat each 10-minute block as no steadier than one 30-second reading, which is right if the
scatter comes from slow wandering over minutes. If it came only from piece-to-piece noise, a
10-minute block (about 200 pieces against 10) would be about 4.5 times steadier and the figures
would fall several-fold (the two-cycle figure to about 9%); the 3-second pieces are not independent
(METHODS §4), so the truth lies between, nearer the upper figure the more the power wanders. The
visit replaces this estimate with its own: A1 and A2 are the same setting repeated 12 minutes apart,
and their difference measures the wandering directly.

**What this means.** The rate swap can see a stimulator-locked part only if it is large: with the
one cycle that is now the default, more than half the band's power (56%; 67% once corrected for the
four bands); with a second cycle, about two fifths (42%; 50% corrected). For scale, the change in
power per milliamp on the two left-lead ladders at 55 Hz, averaged over the two, was +0.9%, -1.5%,
-5.6% and -6.2% of the band's power in 23.5, 24.5, 25.5 and 26.5 Hz; so a rate-locked part the size
of the whole current effect over the range tested would be far below what one visit could see. The
narrow-peak reading of §4 (25.0 Hz present at 55 Hz and absent at 60 Hz, in the PSD from the voltage
trace) is not diluted across a 5 Hz band and may see a much smaller locked part; no scatter estimate
exists for it yet.

**When a second cycle is needed (your ruling: only if really needed).** It is not in the default
timeline. The rule reads the main reading, the four "moves out" bands 23.5-26.5 Hz, each corrected
for the four as §8 corrects them, and is written down before the visit so it cannot be adjusted on
the day. Run a second cycle only if, in at least one of those four bands, either:

1. **the first cycle's change sits in the zone only a second cycle could resolve:** the 60 Hz block
   differs from the average of A1 and A2 by at least 50% of the band's power (what two cycles could
   detect) but by less than 67% (what one cycle could detect). A change of 67% or more is already
   clear. A change under 50% is below what a second cycle could detect too, so a second cycle would
   not settle it; §5's longer repeat at a later visit is the answer to that, not more minutes today;
   or
2. **the two passes at 55 Hz disagree beyond their scatter:** A1 and A2 differ from each other by
   more than 58% of the band's power (a 16% scatter per block, two blocks, corrected for the four
   bands). The setting that did not change moved more than its scatter allows, so B1 has no steady
   baseline to be read against, and a second cycle adds the third 55 Hz block that measures how much
   the baseline wanders.

**What it saves.** Leaving the second cycle out by default saves 22 minutes of the patient's time,
44 minutes of staff time (two people), 10 ratings and 22 sheet rows.

**The numbers the rule reads come from the recording**, which has to be taken off the tablet and
analysed. Whether that can be done while the patient is still in the chair is open (§11). If it
cannot be done before the ladder starts, no second cycle is run at this visit; the rule is applied
when the recording is analysed, and if it is met, the second cycle goes to the repeat visit §10
already calls for, run in the reverse order (60-55-60), which is also the order report 02 asks for
to balance the first.

**Stated in advance: a result of no change closes nothing.** If no band changes by more than the
detectable change, the write-up says "no change larger than X% of the band's power was detectable
across N blocks", and the next step is a longer repeat (20-minute blocks, or the order reversed,
60-55-60), never "these bands are not locked to the stimulator".

---

## 6. How the visit runs

Minute-by-minute rows in the lab's sheet format are in §9; this is the outline. BrainSense streaming
runs on L 1-3+ and R 0-3+ without a break from the first minute to the end of the ladder, through
both rate changes (item 0.3(d), answered). In the off block, a 2-minute streamed recording follows
each rating (report 02); if the team prefers to leave streaming running through the off block, that
meets the design too.

| Minutes | Part | Setting | Ratings |
|---|---|---|---|
| 0-2 | Setup: start streaming, confirm settings, change nothing | L 3 / R 2.5 mA, 55 Hz | — |
| 2-12 | **A1**, 10 min | 55 Hz | 5 (every 2 min) |
| 12-13 | Change to 60 Hz, both sides; minute discarded | 60 Hz | — |
| 13-23 | **B1**, 10 min | 60 Hz | 5 |
| 23-24 | Change to 55 Hz; discarded | 55 Hz | — |
| 24-34 | **A2**, 10 min; end of the rate swap | 55 Hz | 5 |
| *(+22, only if needed)* | *Second cycle, only if the rule of §5 is met and its numbers are in hand: change, **B2**, change, **A3**; every later minute shifts by 22* | *60, then 55 Hz* | *10* |
| 34-48 | **Down-first ladder**, left stepped, right held at 2.5 mA, 55 Hz: 7 steps of two 1-minute rows | L 3 → 2 → 1 → 0 → 1 → 2 → 3 mA | 7 (one per step) |
| 48-49 | Stop streaming; both sides to 0 mA | L 0 / R 0 mA | — |
| 49-322 | **Timed stimulation-off block** (§6.1): a rating every 20 minutes from minute 10 to minute 270 of the block, each followed at once by a 2-minute streamed recording | L 0 / R 0 mA | 14 (10 counted, from minute 90 of the block) |
| 322-324 | Impedance test (1 min); restore the settings in force (1 min) | as in force | — |
| 324-334 | Back on stimulation: comfort check; if the home sequence goes ahead, go through its dates (§6.2); export the session | L 3 / R 2.5 mA, 55 Hz | 1 (at minute 10) |

**Length.** 334 minutes, 5 h 34 min, in the chair (5 h 56 min with the second cycle); the off block
alone is 4 h 36 min of it, from the move to 0 mA to the restored settings. Report 02 put the rate
swap and the off block together at roughly 4-6 hours and suggested splitting them across two visits
to reduce the burden; you ruled for one visit. If the patient cannot manage the day, the off block
is the part to move to a second visit. The lab's usual off-stimulation baseline before and after a
ladder is replaced by the off block at the end; two minutes off just before A1 would disturb the
setting the patient has held for days, and the A1-B1-A2 design can bracket slow drift but not a
recovery from an off period.

**Discard windows.** The minute of each rate change is discarded (critique 09 asked for 30-60 s;
this takes the upper end, and the sheets' own note says current takes 30-45 s to arrive). If the
tablet shows the current ramping after a rate change, the discard runs until the time the sheet
records it back at its setting (item 0.3(b)). As a check stated in advance, every rate-swap result is
also read with the first 2 minutes of each block dropped. In the ladder, each step's first row is the
ramp row and is not analysed; the reading is the second row (the lab's two-row step, decision 160;
the analysis uses a 30-second settled window from it).

**Open-label.** The patient is not told which rate is running, but a patient with years of
stimulation may feel 60 Hz, so the design is open-label and no reading assumes the patient did not
know. At minute 3 of every rate-swap block the patient is asked whether they noticed any change, and
the answer is written down; the ratings can then be read apart by whether a change was noticed. The
off block and the home sequence are open-label too: the patient will know stimulation is off, and
may feel each change of current at home.

**Stop rules, agreed before the visit.** 60 Hz is a first exposure for this patient. A side-effect
score of 2 or more (0-4, decision 165; the first-exposure stop rule of decision 230) at 60 Hz means
return to 55 Hz and end the rate swap there. The ladder passes through 0 mA on the left for one
2-minute step, as every ladder does; if that is not tolerated the ladder turns back up from the
current reached. In the off block, the pain or distress level at which stimulation is restored at
once is agreed with the clinical team before the visit (report 02), and the patient's own request is
always enough. Any pain or distress the patient or clinician judges too much ends the visit and
restores the settings in force at once.

### 6.1 The timed stimulation-off block

**What it is.** Both sides at 0 mA for about 4½ hours after the ladder, 4 h 34 min from the time the later side reaches 0 mA to the restore row (report 02, part 1; the revised
plan's Lane C row 2). Minute 0 of the block is the time the later side reaches 0 mA. A pain rating
every 20 minutes, from minute 10 to minute 270 of the block (14 ratings), each followed at once by a
2-minute BrainSense streamed recording on L 1-3+ and R 0-3+, so each rating has a recording started
within 1-2 minutes of it, where the 2025 stretch had them hours apart. Then an impedance test at a
fixed measurement current (decision 133) and the settings in force restored.

**Why the first 90 minutes are not in the main reading.** Report 02 sets a 1.5-hour wait before the
counted readings, because relief can linger after stimulation stops: a median of 5 hours before pain
returned after spinal cord stimulation was switched off (Meier et al. 2024), up to about 4 hours for
the slowest Parkinson's signs after brain stimulation was switched off (Temperli et al. 2003). The
wait only lets the fastest part pass, so the ratings before minute 90 are still taken and recorded,
on the same 20-minute clock (a choice of this draft; report 02 asks only that the wait not be
thrown away), and every point carries its minutes since 0 mA, so a slow fade shows as a trend
rather than being hidden. The counted part runs from minute 90 to minute 270: 3 hours, report 02's
aim, and 10 rating-and-recording pairs.

**What to expect from it, stated beside its cost (critique 09).** About 4½ hours off stimulation, for a
patient whose only earlier stretch at 0 mA had 81% of its ratings at 8 or 9 out of 10 (report 02).
Even a clean result stays a lead: it is one day, and decision 282 puts confirming the zero-current
reading at 52 to 132 calendar days, depending on how many bands are tested. What one day can add is a
reading matched in minutes rather than hours, more than a year after implant, when the settling of
the tissue around a new lead no longer confounds it (report 02).

**Which pain scale.** The 2025 reading rose with the 0-100 pain scale filed in REDCap and was not
detectable with the 0-10 score (decision 262(a)). The sheet rates on 0-10 (Overall, Back, Left Leg).
To read the same scale, the patient would also file the REDCap survey at each of the 14 ratings;
whether that is acceptable is open (§11). Without it, the block reads the 0-10 scores only.

### 6.2 The home hold-and-return sequence (open-label; waits on research-ethics coverage)

**What it is.** Report 02, part 3, and the revised plan's Lane C row 3: the left current is held for
3 to 4 days, moved, and returned, five holds in all; the right side stays at 2.5 mA, the rate at
55 Hz and the pulse widths as in force throughout. Day 0 is the visit, which ends on the settings
in force, so the first hold needs no change.

| Hold | Left current | Length | Started by |
|---|---|---|---|
| 1 | 3.0 mA (in force) | 3-4 days | the visit's restore row |
| 2 | 4.0 mA, up 1 mA | 3-4 days | at-home session 1 |
| 3 | 3.0 mA, back to the start | 3-4 days | at-home session 2 |
| 4 | 2.0 mA, down 1 mA, only if 2.0 mA was tolerated in the ladder that day and the patient agrees | 3-4 days | at-home session 3 |
| 5 | 3.0 mA, back to the start | 3-4 days | at-home session 4 |

The whole sequence runs 15 to 20 days and ends with a rating at the follow-up. **Why 3 to 4 days:**
a current with memory was no worse than the current in force up to about 3 days and clearly worse at
7 days or more (decision 262(b), as report 02 reads it), so 3-4 days sits at the edge the data on
file could not resolve. **Why 1 mA either way:** report 02 leaves the step to the clinician; this
draft proposes the ladder's own step, which keeps the upper hold 0.5 mA under the ceiling at a
current the left has held before (§3), and the lower hold at a current the ladder rates on both of
its legs the same day. The clinician confirms both (§11).

**Who changes the current.** The study team, at an at-home session written on an at-home testing
sheet, as the lab already does (the 30 sheets on file are clinic and at-home sheets, decision 272).
Each session first rates the hold that is ending, then sets the next current. The patient does not
change their own settings. Ratings otherwise continue on the patient's usual REDCap schedule.

**What it records.** Pain from REDCap and the at-home sheets; band power from the left chronic log
as it is today, one reading every 10 minutes (decision 252), on L 1-3+ at 23.44 Hz, not re-pointed
(item 0.3(a) is not needed for this). The rate stays at 55 Hz, so the 25 Hz landing of §4 sits in
the chronic log's band in every hold alike.

**Open-label.** A patient with years of stimulation can likely feel a 1 mA change (critique 09), so
the sequence is open-label and sequential, not blinded.

**Safety.** A pain flare can outlast the visit, so report 02 asks for a separate safety and rescue
plan for this part, agreed with the clinical team, not folded into the visit sign-off: who the
patient calls, and that any hold can be ended early by returning to 3.0 mA.

### 6.3 Staff time and patient time

About 20 minutes of setup before the patient's first minute (settings check, stop-rule review,
streaming start) and 15 minutes after (export the session files, upload the sheet), around 334
minutes in the chair: **about 6 h 10 min of clinic time** (6 h 30 min with the second cycle).

- **One person at the tablet throughout**, about 6.2 hours: reprogramming on the minute, writing the
  time of every row and of any streaming restart, and in the off block rating and starting a
  recording every 20 minutes and staying with the patient for the stop rules.
- **A second person for the ratings and the minute-3 question** during the setup, the rate swap and
  the ladder (20 + 48 minutes), about 1.1 hours.
- **Total about 7.3 person-hours** (8.0 with the second cycle). The draft before these rulings, the
  rate swap with two cycles and a 13-step ladder and no off block, was about 2 hours of clinic time
  and 3.5 person-hours; the off block is almost all of the difference.
- **The home sequence adds four at-home sessions**, each a rating and one change of current, plus the
  rating at the follow-up. Their length is the lab's to estimate from its own at-home sessions and is
  not counted above.

---

## 7. The ladder that steps down first

**Design.** Left current from the current in force, 3.0 mA, down to 0 mA in 1 mA steps, then back
up to 3.0 mA in 1 mA steps: **3.0, 2.0, 1.0, 0, 1.0, 2.0, 3.0 mA, 7 steps**, each a 1-minute ramp row
and a 1-minute test row with a rating, **14 minutes and 7 ratings**. Every current stays at or below
the 3.0 mA in force and far under the 4.5 mA ceiling. The right side is held at 2.5 mA and the rate at
55 Hz, the rate in force (your ruling 3 of decision 233, kept by your answer 9 of 2026-09-25).

**Why 1 mA steps, and what they cost.** Your ruling of 2026-09-14 (decision 160) keeps the ladder's
down leg at 1 mA steps; the way up in the ordinary ladder is 0.5 mA. Here the way up also uses 1 mA,
so that each current rated on the way down is rated again on the way up. The cost: **two currents
are rated on both legs, 1.0 and 2.0 mA, against five (0.5 to 2.5 mA) in the 0.5 mA draft**, three
fewer; 0 mA is rated once, where the ladder turns, and 3.0 mA at the start (held since before the
visit) and at the end (reached by a rise). The ladder is 6 steps and 12 minutes shorter (7 steps
against 13). Stepping up in 0.5 mA instead would add three currents rated once (0.5, 1.5 and
2.5 mA) and 6 minutes, and no pair. Neither pair is at a current the 2026-09-16 visit rated on both
legs (0.5, 1.5, 2.5 and 3.5 mA, decision 272), so the comparison across the two visits is also a
comparison across currents. Starting instead with a rise to 3.5 mA (3.5, 2.5, 1.5, 0.5, 1.5, 2.5,
3.5 mA, then back to 3.0) would put the two pairs at 1.5 and 2.5 mA, currents that visit paired, at
the cost of a first move that is a rise and two more minutes (§11).

**Why it starts from the current in force and not from the top.** Its first move must be a fall
from a setting the patient has held for days, the mirror of the 2026-09-16 ladder's first rise.
Starting from the top would need a rise to get there first.

**What it can tell.**

- **Pain.** The same comparison as decision 272 and the carry-over check on the Stim Optimizer page:
  at each current rated on both legs, down minus up. If the down leg reads lower whichever leg came
  first, that is what carry-over predicts; if the sign follows the order (lower when the fall came
  later, higher when it came first), that is pain drifting over the visit. Described with its
  numbers; two pairs is not a test.
- **Band power.** The 22% offset of §5 (the fall reading higher) came from falls that all followed
  their rises. If it is drift over the visit, it should reverse sign in this ladder; if it belongs to
  whether the current was rising or falling, it should keep its sign. Using the scatter of §5 (0.23
  per pair), two pairs here against the three of 2026-09-16 give a standard error of 0.21 on the
  difference between the two sessions, so a reversal of the size seen (from +0.22 to -0.22, a
  difference of 0.44) would be detected about 55% of the time at a two-sided 5% level, against about
  74% with the five pairs of the 0.5 mA draft (computed for this revision, same method). That rests
  on three occasions' worth of scatter and should be read as rough.
- **At 55 Hz every band from 22.5 to 29.5 Hz carries a folded multiple of the rate** (decision 277),
  including the whole pain-linked family on the left, so the ladder's band readings in that family
  need the rate swap's answer beside them.

**What it does not do.** It holds the right side at 2.5 mA, so it does not add the current pairs
decision 258 named as missing for your ruling 5 (the pairs need the right side at 3 to 3.5 mA); the
home sequence holds the right at 2.5 mA too. The visit's ratings enter the clinic-sheet stream as
usual: 13 at L 3 / R 2.5 mA and 55 Hz, 5 at 60 Hz (a rate with no other clinic ratings), 2 each at
L 2 and L 1 mA and 1 at L 0 mA with the right at 2.5, and 14 with both sides at 0 mA.

---

## 8. The analysis, stated before the visit

**The rate swap and the ladder**

1. **Band power** per 3-second piece from the voltage trace on L 1-3+ and R 0-3+, all 22 centres,
   by the platform's own transform (the route that builds the stored pieces), raw power. Each block's
   mean over its kept minutes. For each band: the 60 Hz block's mean against the 55 Hz blocks' mean,
   as a fraction of the 55 Hz mean, with an interval from resampling runs of neighbouring pieces
   within blocks, and the difference between A1 and A2 beside it. A point value and an interval,
   never a pass or fail (report 02).
2. **Read by set, named in advance:** "moves out" 23.5-26.5 Hz (the main reading; corrected for the
   four bands); "moves in" 8.5-10.5 and 16.5-21.5 Hz; no contrast 11.5-15.5, 22.5, 27.5-28.5 Hz;
   29.5 Hz observation only. R 0-3+ read the same way as a comparison (its contacts differ, so its
   bands are never pooled with the left, and neither side is read from a figure that mixes both
   sides' currents; METHODS §7).
3. **The second-cycle rule of §5**, applied to the numbers of item 1, and its outcome written down
   whichever way it goes.
4. **The PSD computed from the voltage trace at fine resolution** (a fraction of a hertz over a
   10-minute block, against the 5 Hz bands): narrow peaks at 25.0 Hz and 27.5 Hz under 55 Hz; at 10.0,
   20.0 and 30.0 Hz under 60 Hz. Descriptive.
5. **The device's own power reading** at 23.44 Hz, 55 Hz blocks against the 60 Hz block, the same way.
6. **Pain in the swap:** the mean of each block's ratings with its count, by rate and by whether the
   patient noticed a change. Descriptive; the swap is not sized for pain.
7. **The ladder:** as §7, reported beside the 2026-09-16 ladder's numbers.

**The off block**

8. **Band against pain**, on L 1-3+ and R 0-3+, 22 bands, raw power from the 2-minute recording that
   follows each rating: the rank correlation over the 10 counted pairs, with the count. The two bands
   of the 2025 reading, L 1-3+ at 21.5 and 22.5 Hz, are reported first and named in advance; all 22
   follow as an uncorrected look. L 0-2+, the other pair in the 2025 reading, is not streamed at this
   visit. No p-value is attached: 10 ratings 20 minutes apart on one day cannot carry one (rotating
   10 ratings in time, the project's way of seeing what happens by chance, gives a smallest possible
   p of 0.1).
9. **Pain and band power against minutes since 0 mA**, all 14 points, so a slow fade after stopping
   stimulation shows as a trend. Descriptive.
10. **The same bands with the current on**, read from the stored grid with the current taken out
    (decision 234), beside item 8, so the two readings sit side by side (report 02).

**The home sequence**

11. **Pain at the same current, 3.0 mA, in holds 1, 3 and 5**, and in holds 2 and 4 beside them, from
    the REDCap ratings and the at-home sheet ratings, each hold's mean with its count. A lingering
    effect shows as hold 3 differing from hold 5, or as the first days of a hold differing from its
    last. Hold 1 starts the same day as the off block and its first day may carry that after-effect,
    so holds 3 and 5 are the cleaner comparison.
12. **The left chronic log per hold**, the median of California-day medians, as decision 252 reads
    it; each hold has 3 to 4 days, fewer than the 7 decision 252 required, so this is descriptive.
13. **The saved analysis of a current with memory** (decision 264(4)) run again with the new
    sequence in it.

Every result is a lead to repeat (METHODS §7; decision 237). A result of no change is written as the
change that could have been detected and was not (§5).

---

## 9. Clinic-sheet rows

The lab's "Stim Testing" tab, columns A-S in the template's own order (`titration_plan.SHEET_COLUMNS`,
header row 11, data from row 12). Contacts, current and pulse width are written in the sheet's own
left-then-right form (`L C+2- / R C+1-2-`, `L 3 / R 2.5`, `L 100 / R 150`, decision 181; trap 4 of
`clinic_steps.py`). Settings are written on the rows where they change; the lab's reader carries them
forward to the rows below, as it does for the two-row steps today. In the rate swap and the ladder a
row is one minute. In the off block a row is a rating (60 s), a recording (120 s) or a wait (600 s
before the first rating, 1,020 s between ratings), its length in the Duration column. **Left blank
for the day:** Group, sEEG Contacts, Threshold, Side Effect? (write any side effect and its 0-4
score), Timestamp (write the time as each row begins), Movement/Change point, and the seven pain
columns (on rows whose note says "Pain rating now", fill Overall, Back and Left Leg on the 0-10
scale).

**Checked against the lab's own reader.** Generated by `BRAVO/_agent_bridge/_protocol_rows_gen.py`,
filled with a constructed placeholder score on every rating row and read back through the
clinic-sheet parser (`clinic_pain._parse_generic_stim_testing`) by
`BRAVO/_agent_bridge/_protocol_sheet_check.py`, no data read. Run on 2026-09-25 in the server container: **the visit's 37 rating rows read, 0 flagged as unparsed prose, 0 dropped**; the settings read back as 13 ratings at 55 Hz L 3 / R 2.5 mA, 5 at 60 Hz L 3 / R 2.5 mA, 2 each at L 2 and L 1 mA and 1 at L 0 mA with the right at 2.5 mA, and 14 with both sides at 0 mA, every one at L 100 / R 150 µs. With the second cycle inserted: 47 read, 18 at 55 Hz L 3 / R 2.5 mA and 10 at 60 Hz, the rest unchanged, 0 dropped. The home sheets: 5 read (3 at L 3, 1 at L 4, 1 at L 2 mA), 0 dropped. No note contains a pattern the reader mistakes for a written score.

### 9.1 The visit (the default, 95 rows, 334 minutes)

```csv
Group,Contacts,sEEG Contacts,Amp (mA),Rate (Hz),PW (µs),Threshold,Duration (s),Side Effect?,Timestamp,Movement/Change point,General Notes / Pt Verbal Notes,Overall,Head,Back,Left Leg,Left Foot,Right Leg,Right Foot
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,Start BrainSense streaming on L 1-3+ and R 0-3+ and keep it running to the end of the ladder. Confirm the settings in force on the tablet; change nothing. Not analysed.,,,,,,,
,,,,,,,60,,,,Streaming running; patient seated and still. Not analysed.,,,,,,,
,,,,,,,60,,,,"Block A1, 55 Hz, minute 1 of 10.",,,,,,,
,,,,,,,60,,,,"Block A1, 55 Hz, minute 2 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A1, 55 Hz, minute 3 of 10. Ask whether the patient noticed any change; write the answer.",,,,,,,
,,,,,,,60,,,,"Block A1, 55 Hz, minute 4 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A1, 55 Hz, minute 5 of 10.",,,,,,,
,,,,,,,60,,,,"Block A1, 55 Hz, minute 6 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A1, 55 Hz, minute 7 of 10.",,,,,,,
,,,,,,,60,,,,"Block A1, 55 Hz, minute 8 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A1, 55 Hz, minute 9 of 10.",,,,,,,
,,,,,,,60,,,,"Block A1, 55 Hz, minute 10 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,60,L 100 / R 150,,60,,,,"Change the rate to 60 Hz on BOTH sides; current and pulse widths unchanged; streaming keeps running. Minute discarded from analysis. If the tablet shows the current ramping, write the time it is back at the set current.",,,,,,,
,,,,,,,60,,,,"Block B1, 60 Hz, minute 1 of 10.",,,,,,,
,,,,,,,60,,,,"Block B1, 60 Hz, minute 2 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block B1, 60 Hz, minute 3 of 10. Ask whether the patient noticed any change; write the answer.",,,,,,,
,,,,,,,60,,,,"Block B1, 60 Hz, minute 4 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block B1, 60 Hz, minute 5 of 10.",,,,,,,
,,,,,,,60,,,,"Block B1, 60 Hz, minute 6 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block B1, 60 Hz, minute 7 of 10.",,,,,,,
,,,,,,,60,,,,"Block B1, 60 Hz, minute 8 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block B1, 60 Hz, minute 9 of 10.",,,,,,,
,,,,,,,60,,,,"Block B1, 60 Hz, minute 10 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Change the rate to 55 Hz on BOTH sides; current and pulse widths unchanged; streaming keeps running. Minute discarded from analysis. If the tablet shows the current ramping, write the time it is back at the set current.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 1 of 10.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 2 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 3 of 10. Ask whether the patient noticed any change; write the answer.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 4 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 5 of 10.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 6 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 7 of 10.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 8 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 9 of 10.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 10 of 10. Pain rating now: Overall, Back, Left Leg. END OF THE RATE SWAP. A second cycle only if the rule of section 5 is met and its numbers are in hand now; otherwise go to the ladder.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 1 of 7, left 3 mA, start (held since before the visit): NO CHANGE (ramp row kept so every step has two rows). Not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 1 of 7, test row, left 3 mA (start (held since before the visit)). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 2 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 2 of 7: set LEFT to 2 mA (down); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 2 of 7, test row, left 2 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 1 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 3 of 7: set LEFT to 1 mA (down); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 3 of 7, test row, left 1 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 0 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 4 of 7: set LEFT to 0 mA (down); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 4 of 7, test row, left 0 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 1 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 5 of 7: set LEFT to 1 mA (up); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 5 of 7, test row, left 1 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 2 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 6 of 7: set LEFT to 2 mA (up); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 6 of 7, test row, left 2 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 7 of 7: set LEFT to 3 mA (up); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 7 of 7, test row, left 3 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 0 / R 0,55,L 100 / R 150,,60,,,,Stop streaming. Set BOTH sides to 0 mA: the timed stimulation-off block begins. Write the time each side reaches 0 mA; the later of the two is minute 0 of the block. Stop rules of section 6 apply throughout. Not analysed.,,,,,,,
,,,,,,,600,,,,"Off block, minutes 0 to 10: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 10. Pain rating now: Overall, Back, Left Leg. Waiting period, not in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 11: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 13 to 30: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 30. Pain rating now: Overall, Back, Left Leg. Waiting period, not in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 31: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 33 to 50: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 50. Pain rating now: Overall, Back, Left Leg. Waiting period, not in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 51: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 53 to 70: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 70. Pain rating now: Overall, Back, Left Leg. Waiting period, not in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 71: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 73 to 90: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 90. Pain rating now: Overall, Back, Left Leg. Counted in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 91: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 93 to 110: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 110. Pain rating now: Overall, Back, Left Leg. Counted in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 111: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 113 to 130: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 130. Pain rating now: Overall, Back, Left Leg. Counted in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 131: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 133 to 150: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 150. Pain rating now: Overall, Back, Left Leg. Counted in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 151: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 153 to 170: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 170. Pain rating now: Overall, Back, Left Leg. Counted in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 171: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 173 to 190: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 190. Pain rating now: Overall, Back, Left Leg. Counted in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 191: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 193 to 210: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 210. Pain rating now: Overall, Back, Left Leg. Counted in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 211: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 213 to 230: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 230. Pain rating now: Overall, Back, Left Leg. Counted in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 231: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 233 to 250: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 250. Pain rating now: Overall, Back, Left Leg. Counted in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 251: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,1020,,,,"Off block, minutes 253 to 270: wait. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 270. Pain rating now: Overall, Back, Left Leg. Counted in the main reading.",,,,,,,
,,,,,,,120,,,,"Off block, minute 271: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,60,,,,Impedance test at a fixed measurement current (decision 133). No rating.,,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Restore the settings in force (L 3 / R 2.5 mA, 55 Hz, L 100 / R 150 us); write the time each side is back at its current. End of the off block.",,,,,,,
,,,,,,,540,,,,"Back on stimulation, minutes 1 to 9: watch for comfort. If the home sequence goes ahead, go through its dates with the patient; today is day 0, the start of its first hold. No rating.",,,,,,,
,,,,,,,60,,,,"Back on stimulation, minute 10. Pain rating now: Overall, Back, Left Leg. Export the session.",,,,,,,
```

### 9.2 The second rate-swap cycle, only if the rule of §5 is met (22 rows, 22 minutes)

Inserted after the last row of block A2 ("END OF THE RATE SWAP"), before the first ladder row.

```csv
Group,Contacts,sEEG Contacts,Amp (mA),Rate (Hz),PW (µs),Threshold,Duration (s),Side Effect?,Timestamp,Movement/Change point,General Notes / Pt Verbal Notes,Overall,Head,Back,Left Leg,Left Foot,Right Leg,Right Foot
,L C+2- / R C+1-2-,,L 3 / R 2.5,60,L 100 / R 150,,60,,,,"Change the rate to 60 Hz on BOTH sides; current and pulse widths unchanged; streaming keeps running. Minute discarded from analysis. If the tablet shows the current ramping, write the time it is back at the set current.",,,,,,,
,,,,,,,60,,,,"Block B2, 60 Hz, minute 1 of 10.",,,,,,,
,,,,,,,60,,,,"Block B2, 60 Hz, minute 2 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block B2, 60 Hz, minute 3 of 10. Ask whether the patient noticed any change; write the answer.",,,,,,,
,,,,,,,60,,,,"Block B2, 60 Hz, minute 4 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block B2, 60 Hz, minute 5 of 10.",,,,,,,
,,,,,,,60,,,,"Block B2, 60 Hz, minute 6 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block B2, 60 Hz, minute 7 of 10.",,,,,,,
,,,,,,,60,,,,"Block B2, 60 Hz, minute 8 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block B2, 60 Hz, minute 9 of 10.",,,,,,,
,,,,,,,60,,,,"Block B2, 60 Hz, minute 10 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Change the rate to 55 Hz on BOTH sides; current and pulse widths unchanged; streaming keeps running. Minute discarded from analysis. If the tablet shows the current ramping, write the time it is back at the set current.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 1 of 10.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 2 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 3 of 10. Ask whether the patient noticed any change; write the answer.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 4 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 5 of 10.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 6 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 7 of 10.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 8 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 9 of 10.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 10 of 10. Pain rating now: Overall, Back, Left Leg. END OF THE SECOND CYCLE; go to the ladder.",,,,,,,
```

### 9.3 The home sequence, one at-home sheet per session (9 rows)

Each at-home session is its own sheet, so its first row writes the settings in force; the reader
carries nothing over from one sheet to the next. The Duration column is left blank: each hold is 3
to 4 days, and the sheet records the time each hold starts.

```csv
Group,Contacts,sEEG Contacts,Amp (mA),Rate (Hz),PW (µs),Threshold,Duration (s),Side Effect?,Timestamp,Movement/Change point,General Notes / Pt Verbal Notes,Overall,Head,Back,Left Leg,Left Foot,Right Leg,Right Foot
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,,,,,"Home sequence, at-home session, end of hold 1 of 5 (left 3 mA, held 3 to 4 days). Pain rating now: Overall, Back, Left Leg. Write any side effect and its 0-4 score.",,,,,,,
,L C+2- / R C+1-2-,,L 4 / R 2.5,55,L 100 / R 150,,,,,,"Set LEFT to 4 mA (up); right held at 2.5 mA, 55 Hz, pulse widths unchanged. Hold 2 of 5 starts now; write the time.",,,,,,,
,L C+2- / R C+1-2-,,L 4 / R 2.5,55,L 100 / R 150,,,,,,"Home sequence, at-home session, end of hold 2 of 5 (left 4 mA, held 3 to 4 days). Pain rating now: Overall, Back, Left Leg. Write any side effect and its 0-4 score.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,,,,,"Set LEFT to 3 mA (back to the start); right held at 2.5 mA, 55 Hz, pulse widths unchanged. Hold 3 of 5 starts now; write the time.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,,,,,"Home sequence, at-home session, end of hold 3 of 5 (left 3 mA, held 3 to 4 days). Pain rating now: Overall, Back, Left Leg. Write any side effect and its 0-4 score.",,,,,,,
,L C+2- / R C+1-2-,,L 2 / R 2.5,55,L 100 / R 150,,,,,,"Set LEFT to 2 mA (down, only if 2 mA was tolerated in the ladder and the patient agrees); right held at 2.5 mA, 55 Hz, pulse widths unchanged. Hold 4 of 5 starts now; write the time.",,,,,,,
,L C+2- / R C+1-2-,,L 2 / R 2.5,55,L 100 / R 150,,,,,,"Home sequence, at-home session, end of hold 4 of 5 (left 2 mA, held 3 to 4 days). Pain rating now: Overall, Back, Left Leg. Write any side effect and its 0-4 score.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,,,,,"Set LEFT to 3 mA (back to the start); right held at 2.5 mA, 55 Hz, pulse widths unchanged. Hold 5 of 5 starts now; write the time.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,,,,,"Home sequence, end of hold 5 of 5 (left 3 mA, held 3 to 4 days), at the follow-up. Pain rating now: Overall, Back, Left Leg. No change: the setting in force stays.",,,,,,,
```

---

## 10. What this visit cannot settle

- One visit day is one day. A shift in the rate swap is a lead to repeat at a later visit, in the
  reverse order (60-55-60); no shift is the detectable change of §5 and a reason to repeat longer.
- The rate swap says whether power follows the rate. It says nothing about whether any band tracks
  pain; that question stays with the off block and with the current-removal work already built
  (decisions 234, 240-242).
- The off block gives 10 counted pairs on one day. It can show the sign and rough size of the
  zero-current reading when ratings and recordings are minutes apart; it cannot confirm it
  (decision 282: 52 to 132 calendar days).
- The down-first ladder gives two pairs on one day. It can show which way the order effect points;
  it cannot size carry-over.
- The home sequence is one pass: two comparisons at the same current (holds 1 and 3, holds 3 and 5),
  enough to show the sign of a lingering effect if it is large, not its size (report 02). Repeating
  the whole sequence later is how confidence is built.
- The weeks confound everything already on file (the revised plan, §4): current, rate and calendar
  moved together. This visit separates rate from calendar within one day, and the home sequence
  repeats one current weeks apart; neither undoes the weeks already on file.

---

## 11. Questions still open

For you:

1. **Research-ethics coverage of the multi-day home sequence** (item 0.2). Not stated on 2026-09-25.
   Until it is, the visit ends on the settings in force and the home sequence waits.
2. **Does the same coverage extend to the rate change to 60 Hz**, a first exposure made for a
   research question? Your answer named the off block. If not, the ladder and the off block can run
   without the rate swap.
3. **The home sequence's two holds away from 3.0 mA**: 4.0 and 2.0 mA, as proposed here, or other
   currents the clinician prefers (report 02 leaves the step to the clinician).
4. **The ladder's start**: from 3.0 mA as ruled, or with a rise to 3.5 mA first so its two pairs sit
   at 1.5 and 2.5 mA, currents the 2026-09-16 visit also paired (§7).
5. **The REDCap survey at each off-block rating** (14 in 4.5 hours), so the off block reads the same
   0-100 scale as the 2025 reading (§6.1).

For Medtronic or the clinical team:

6. **Item 0.3(b)**: does a rate-only change dip the delivered current? The discard rule covers it
   either way.
7. **Item 0.3(d), second half**: can the rate change on one side alone? Not needed for this visit.
8. **Item 0.3(a)**: does Single Threshold Inverse change the delivered current? Needed only to
   re-point the home chronic log; without it the log stays as it is.
9. **Can the first cycle's recording be taken off the tablet and analysed while the patient is still
   in the chair?** If not, the second-cycle rule is applied afterwards and a needed second cycle goes
   to the repeat visit (§5).
10. **The stop level for the off block** and a fresh clinical review before it; **the safety and
    rescue plan for the home sequence**; a second person for ratings; and whether the patient can
    manage a 5.6-hour day, or the off block should move to a second visit (report 02's own
    suggestion).

## 12. Sources

- Revised plan and critiques: `artifacts/research_2026-09-25_options/{11_REVISED_PLAN,08_critique_science,09_critique_feasibility,02_next_clinic_visit_protocol}.md`.
- Decisions 133, 138, 145, 160, 165, 181, 202, 213, 217, 230, 233, 234, 237, 252, 258, 262, 264,
  272, 277, 282 (`DECISIONS_and_open_items.md`; the full rows in `docs/decision_log_full_2026-09-19.md`
  for decisions up to that date).
- Device facts: `DEVICE_percept_rc.md` §§3, 6, 9.
- Literature cited through report 02: Meier et al. 2024 (*Neuromodulation*, PMID 38456888); Temperli
  et al. 2003 (*Neurology*, PMID 12525722).
- Read-only scripts run for this draft on 2026-09-25, printing counts and aggregates only (gitignored
  scratch): `BRAVO/_agent_bridge/_rateswap_mdc.py` (the scatter of §5 and the change per milliamp),
  `BRAVO/_agent_bridge/_rateswap_settings.py` (the settings in force, the rates in the settings
  history, the one row of 3,344 with different rates on the two sides). The harmonic table of §4 was
  run on the host from `StimOptimizer.titration_plan` with no data. For this revision:
  `BRAVO/_agent_bridge/_protocol_rows_gen.py` (the rows of §9, their minutes and rating counts) and
  `BRAVO/_agent_bridge/_protocol_sheet_check.py` (the reader check of §9); the detectable changes
  of the second-cycle rule and the ladder's 55% were computed by hand from §5's scatter with the
  same normal-approximation method as the table.
