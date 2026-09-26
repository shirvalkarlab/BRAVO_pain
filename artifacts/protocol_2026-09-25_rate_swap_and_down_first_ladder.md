# Next visits, draft protocol: the rate swap, a ladder that steps down first, a stimulation-off visit, and a home hold-and-return sequence

> Draft for the PI (Prasad Shirvalkar), first written 2026-09-25, revised 2026-09-25 with your
> rulings of that day, **revised 2026-09-26 for the 2-hour visit limit, and again the same day with
> your choice of the stimulation-off option and your acceptance of the 2 mA hold's condition.** Your
> ruling: "max visit is 2 hrs", door to door, counting the setup before the patient's first rated
> minute and the export and comfort check after. The draft before this revision planned one visit of
> 334 minutes in the chair (about 6 h 10 min of clinic time); it is now split. **Visit 1** (§6)
> holds the rate swap and the ladder and takes 98 minutes door to door (120 with the conditional
> second rate-swap cycle). The stimulation-off block could not keep its 90-minute wait inside 2
> hours; **you chose option (c), a shorter wait inside one 2-hour visit ("stim off -c yes")**, and
> **Visit 2** (§6.1) is that visit: a 30-minute wait, 10 ratings after it, 120 minutes door to door.
> **Every question for you is now answered**; what remains is for Medtronic or the clinical team
> (§11). Your answers of 2026-09-26, each applied here: ethics coverage of the multi-day home
> sequence confirmed ("yes multi day home seq ok"); the home holds approved as proposed (left 3, 4,
> 3, 2, 3 mA, 3-4 days each, the 2 mA hold only if the ladder showed the lower currents were
> tolerated), and that condition written as "1.5 and 2.5 mA both tolerated on both legs of the Visit
> 1 ladder" accepted; the ladder starts with a rise to 3.5 mA ("sure start with ladder to 3.5"); the
> patient files the REDCap survey at every rating in any stimulation-off block ("yes files redcap on
> off blocks"); the first exposure to 60 Hz is covered ("60 hz ok"). Rulings of 2026-09-25 that
> stand: the ladder at 55 Hz with the rate swap first (answer 9; ruling 233(3)); stimulation off
> covered by the research protocol ("Stim off is OK, it's in our protocol"); the rate changes
> without stopping BrainSense streaming (Lane 0 item 0.3(d), first half); the ladder keeps 1 mA
> steps (your ruling of 2026-09-14, decision 160); a second rate-swap cycle only if really needed.
> **Nothing is scheduled and nothing here is an instruction to program anything.** Lane C of
> `artifacts/research_2026-09-25_options/11_REVISED_PLAN.md`, with every accepted critique folded in
> (`08_critique_science.md` M3; `09_critique_feasibility.md` on staff time, discard windows, the
> 29.5-30 Hz band, open-label wording, prerequisites 0.2 and 0.3, and stating the likely outcome of
> the off block beside its burden), decision 277 (the one harmonic check), and the off block and
> home sequence of the options report
> `artifacts/research_2026-09-25_options/02_next_clinic_visit_protocol.md` (report 02). Every number
> below is quoted from a decision with its number or from report 02, or was computed for this draft
> by a read-only script whose name is given; none is carried forward from a document without being
> re-read.

**Words used here.** A **ladder** is a planned run of current steps within one visit, one setting at
a time. A band **carries a folded multiple of the stimulation rate** when a whole multiple of the
pulse rate, folded down by the device's sampling of the brain signal at 250 times a second, lands
within 2.5 Hz of the band's centre (half the 5 Hz band width). At 55 Hz, five times the rate
(275 Hz) reappears at 25 Hz. That is a statement about where numbers land and needs care, never
disbelief (your correction of 2026-09-06); it does not say the band measures the stimulator.
**Band power** is always raw power in the device's units; log power enters nothing here
(decision 202). **Open-label** means the patient may know, or feel, which setting is running, and no
reading assumes otherwise. A **hold** is a stretch of days on one unchanged setting. **Door to door**
is the patient's whole visit, from the start of setup to the end of the export. **The wait** is how
long after stimulation is switched off before a rating counts in the main reading of an off block
(90 minutes in report 02's design; 30 minutes in Visit 2, by your choice).

---

## 1. What the visits ask

1. **Does the power in the left 21.5-27.5 Hz family follow the stimulation rate?** At 55 Hz every
   band from 22.5 to 29.5 Hz carries a folded multiple of the rate (decision 277). If part of the
   power in those bands is locked to the stimulator's pulses, moving the rate to 60 Hz moves where it
   lands, and the bands it leaves should fall. If the power is the brain's own and not locked to the
   pulses, it should stay where it is. Current and pulse widths are held fixed; only the rate moves,
   55 then 60 then 55 Hz. **Visit 1.**
2. **Does pain on the way down differ from the way up when the fall comes first?** On the one visit
   that rated the same current on both legs (2026-09-16), every fall came after its rise, so a
   difference could be carry-over or could be pain drifting over the visit (decision 272: down minus
   up on the 0-10 score, left ladder -0.75 over 4 currents, right +1.00 over 4). A ladder whose falls
   come before its rises reverses the order. **Visit 1.**
3. **Do the left bands still rise with pain when no current is running at all, with each rating
   matched to a recording taken within minutes of it?** In the one stretch with both sides at 0 mA
   (2025-07-16 to 08-22), L 1-3+ at 21.5 and 22.5 Hz rose with the 0-100 pain scale (+0.38 and
   +0.34, decision 264(1)), but the ratings and recordings were matched only by day, typically 5.1
   hours apart (report 02). **Visit 2** (§6.1), after a 30-minute wait by your choice: it describes
   the first hour off, not the settled off state.
4. **Does a current's effect on pain linger for days?** A current with memory never predicted pain
   better than the current in force (decision 262(b)), but the currents on file were rarely held and
   then returned to, which is the one pattern that would show a short memory (report 02). The home
   sequence holds the left current for 3 to 4 days at a time, moves it, and returns to it. **Starts
   at the end of Visit 1** (its ethics coverage is confirmed).

**If Visit 1 is cut short**, keep the rate swap before the ladder. The home sequence starts at the
end of Visit 1 whether or not the ladder ran, but its 2 mA hold needs the ladder (§6.2). Every
answer will be a lead to repeat, not an established result (METHODS §7; one visit day settles
nothing).

---

## 2. Before it can be scheduled

| Item (numbering from the revised plan's Lane 0) | State on 2026-09-26 | What the visits do meanwhile |
|---|---|---|
| **0.2** Research-ethics coverage, **for a stimulation-off block in clinic** | **Answered** (2026-09-25): "Stim off is OK, it's in our protocol" | Visit 2 (option (c), §6.1) needs nothing more |
| **0.2**, **for the multi-day home sequence** | **Answered** (2026-09-26): "yes multi day home seq ok" | The home sequence starts at the end of Visit 1 (§6.2) |
| **0.2**, **for a stimulation-off period at home** (option (b) of §6.1) | **Covered only if both answers above apply together**: the protocol's stimulation-off clause is not limited to supervised clinic time, and the home-sequence coverage extends to a hold at 0 mA. Neither answer names an unsupervised off period at home in words | Not needed: option (b) was not chosen (§6.1) |
| **0.2**, **for the rate change to 60 Hz** | **Answered** (2026-09-26): "60 hz ok". 60 Hz has never been programmed on this patient (the rates in the device's settings history are 10, 55, 110, 125, 130, 145 and 165 Hz; read 2026-09-25) | The rate swap is in Visit 1 |
| **0.3(b)** Does a rate-only change dip the delivered current? | Open. Nothing in this project measures it: the ramp times in `DEVICE_percept_rc.md` §9 are for current steps only | The minute after each rate change is discarded, and extended until the tablet shows the current back at its setting, with that time written on the sheet (built into the change rows of §9). An extension also rules out the second cycle at Visit 1 (§5) |
| **0.3(d)** Can the rate change without stopping BrainSense streaming? | **Answered: yes** (2026-09-25). Streaming runs through both rate changes with no restart planned around them | — |
| **0.3(d)** Can the rate change on one side alone? | Open. The two sides have carried the same rate in all but 1 of 3,344 settings rows aligned in time (device settings history, read 2026-09-25) | Not needed here: Visit 1 changes the rate on both sides together. It matters only for a later left-only repeat |
| **0.3(a)** Does Single Threshold Inverse change the delivered current? | Open | Not needed: the chronic log is not re-pointed. It stays as it is today, on L 1-3+ at 23.44 Hz, and the home sequence reads it as it is |
| **0.3(c)** Can the home controller trigger more than the 10-minute chronic log? | Open | Not needed: the home sequence uses the ratings and the chronic log as they are today |

Also agreed in advance with the clinical team, not improvised on the day: the stop rules of §6,
a second person for ratings during Visit 1 (§6.3), and, for Visit 2's off block, a
fresh clinical review and the pain or distress level at which stimulation is restored at once
(report 02: the only earlier stretch at 0 mA had 81% of its ratings at 8 or 9 out of 10).

---

## 3. The settings the visits hold

Read from the device's own settings history on 2026-09-25 (the newest row per side of the stored
therapy settings); **confirm on the tablet on the day, and if the currents in force differ, keep the
day's currents and shift the ladder's steps (a rise of 0.5 mA first) and the home holds to start from
the left current in force.**

| | Left | Right |
|---|---|---|
| Stimulating contacts | C+2- (cathode 2a-2b-2c) | C+1-2- (cathode 1a-1b-1c-2a-2b-2c) |
| Current | 3.0 mA | 2.5 mA |
| Pulse width | 100 µs | 150 µs |
| Rate | 55 Hz | 55 Hz |
| Sensing pair the device allows (decision 217) | L 1-3+ | R 0-3+ |

The safety ceiling is 4.5 mA each side (decisions 145, 160). **The highest current in Visit 1 is the
ladder's 3.5 mA on the left, 1.0 mA under the ceiling.** The left has had 3.5 mA before: it was held
there from 2026-08-12 to 2026-09-03, after 4.0 mA and then 4.5 mA from 2026-07-22 to 2026-08-12
(decision 252), and the 2026-09-16 ladder rated 3.5 mA on both of its legs (decision 272). The home
sequence's upper hold, 4.0 mA on the left, is 0.5 mA under the ceiling at a current the left has also
held before. Moving from 55 to 60 Hz delivers 9.1% more pulses a second at the same charge per
pulse. 60 Hz is inside the rates the device's closed-loop mode accepts (55 Hz and above,
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
falling, which is the second reason for the ladder of §7. The device's own power reading at
23.44 Hz shows the same thing: +0.33 over its 3 pairs.

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
   not settle it; a longer repeat at a later visit is the answer to that, not more minutes today;
   or
2. **the two passes at 55 Hz disagree beyond their scatter:** A1 and A2 differ from each other by
   more than 58% of the band's power (a 16% scatter per block, two blocks, corrected for the four
   bands). The setting that did not change moved more than its scatter allows, so B1 has no steady
   baseline to be read against, and a second cycle adds the third 55 Hz block that measures how much
   the baseline wanders.

**The 2-hour limit adds a condition on the clock.** Visit 1 is 98 minutes door to door without the
second cycle and **exactly 120 with it: no minute to spare** (§6). So the second cycle runs at Visit 1
only if the rule above is met on numbers in hand at the end of A2 **and** A2 ends on time, at
door-to-door minute 54 or earlier, **and** no discard window was extended for a ramping current
(item 0.3(b)). Otherwise it does not run at Visit 1: it moves to a later visit, run in the reverse
order (60-55-60), which is also the order report 02 asks for to balance the first. The rule itself
is unchanged.

**What leaving it out saves.** 22 minutes of the patient's time, 44 minutes of staff time (two
people), 10 ratings and 22 sheet rows.

**The numbers the rule reads come from the recording**, which has to be taken off the tablet and
analysed. Whether that can be done while the patient is still in the chair is open (§11). If it
cannot be done before the ladder starts, no second cycle is run at Visit 1; the rule is applied when
the recording is analysed, and if it is met, the second cycle goes to a later visit as above.

**Stated in advance: a result of no change closes nothing.** If no band changes by more than the
detectable change, the write-up says "no change larger than X% of the band's power was detectable
across N blocks", and the next step is a longer repeat (20-minute blocks, or the order reversed,
60-55-60), never "these bands are not locked to the stimulator".

---

## 6. Visit 1: the rate swap and the ladder, 98 minutes door to door

Minute-by-minute rows in the lab's sheet format are in §9.1; this is the outline. BrainSense
streaming runs on L 1-3+ and R 0-3+ without a break from the first chair minute to the end of the
ladder, through both rate changes (item 0.3(d), answered). The setup before and the export after are
this draft's own allowances, kept from the draft before (20 and 15 minutes); the lab may know its
own better.

| Door to door (min) | Chair (min) | Part | Setting | Ratings |
|---|---|---|---|---|
| 0-20 | — | Setup: settings check on the tablet, stop-rule review, connect | as in force | — |
| 20-22 | 0-2 | Start streaming, confirm the settings in force, change nothing | L 3 / R 2.5 mA, 55 Hz | — |
| 22-32 | 2-12 | **A1**, 10 min | 55 Hz | 5 (every 2 min) |
| 32-33 | 12-13 | Change to 60 Hz, both sides; minute discarded | 60 Hz | — |
| 33-43 | 13-23 | **B1**, 10 min | 60 Hz | 5 |
| 43-44 | 23-24 | Change to 55 Hz; discarded | 55 Hz | — |
| 44-54 | 24-34 | **A2**, 10 min; end of the rate swap | 55 Hz | 5 |
| *(54-76)* | *(34-56)* | *Second cycle, only under the rule and the clock condition of §5: change, **B2**, change, **A3**; every later minute shifts by 22* | *60, then 55 Hz* | *10* |
| 54-70 | 34-50 | **Ladder**, left stepped, right held at 2.5 mA, 55 Hz: 8 steps of two 1-minute rows (§7) | L 3.5 → 2.5 → 1.5 → 0.5 → 1.5 → 2.5 → 3.5 → 3.0 mA | 8 (one per step) |
| 70-71 | 50-51 | Settings in force are back after the ladder's last step; stop streaming | L 3 / R 2.5 mA, 55 Hz | — |
| 71-72 | 51-52 | Impedance test at a fixed measurement current (decision 133) | — | — |
| 72-73 | 52-53 | Confirm the settings in force on the tablet | L 3 / R 2.5 mA, 55 Hz | — |
| 73-83 | 53-63 | Comfort check; go through the home sequence's dates (today is day 0, hold 1); start the export | L 3 / R 2.5 mA, 55 Hz | 1 (at minute 10) |
| 83-98 | — | Export the session files, upload the sheet | — | — |

**Length.** 63 minutes in the chair, **98 minutes door to door, 22 minutes inside the 2-hour limit.**
With the second cycle: 85 in the chair, **120 door to door, exactly at the limit**, which is why §5
adds the clock condition. 24 ratings (34 with the second cycle). Visit 1 has no stimulation-off block
and so no REDCap survey at its ratings; the 22 spare minutes are too few for an off block (about
20 minutes at 0 mA, one rating, shorter than even Visit 2's 30-minute wait).

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
return to 55 Hz and end the rate swap there. The ladder's lowest step is 0.5 mA on the left for two
minutes; if a step is not tolerated the ladder turns back up from the current reached. In Visit 2's
off block, the pain or distress level at which stimulation is restored at once is agreed with the
clinical team before the visit (report 02), and the patient's own request is always enough. Any pain
or distress the patient or clinician judges too much ends the visit and restores the settings in
force at once.

### 6.1 Visit 2: the stimulation-off block, option (c), 120 minutes door to door

Your choice of 2026-09-26 ("stim off -c yes"): a shorter wait than 90 minutes, inside one 2-hour
visit. Rows in §9.3.

**Said first, because it governs every reading of this visit.** The record does not support a wait
shorter than 90 minutes, because nothing measured here covers minutes 15 to 90 after a switch-off,
so this visit's readings describe the first hour off, and a flat result cannot be told apart from
relief that has not yet worn off; you chose this knowing that.

**Why the 90-minute design could not fit.** It set both sides to 0 mA for 4 h 34 min, with a rating
every 20 minutes and a 2-minute streamed recording after each, and counted only the ratings from
minute 90 on, because relief can linger after stimulation stops: a median of 5 hours before pain
returned after spinal cord stimulation was switched off (Meier et al. 2024), up to about 4 hours for
the slowest Parkinson's signs after brain stimulation was switched off (Temperli et al. 2003)
(report 02). A 2-hour visit, less the 20-minute setup, the 15-minute export, the two setup rows, the
minute to switch off, the impedance test, the restore and the 10-minute comfort check, leaves
**70 minutes at 0 mA**.

**The wait: 30 minutes.** Option (c) was put to you with a 30-minute wait; it is about twice the
14 minutes over which the record shows pain not rising after a switch-off (decision 272), and every
4 minutes added to it costs one counted rating. The trade, on the rating clock below:

| Wait (min) | 20 | **30** | 40 | 50 | 60 | 90 |
|---|---|---|---|---|---|---|
| Ratings after the wait, within the 70 minutes off | 12 | **10** | 7 | 5 | 3 | 0 |

**The rating clock.** Each rating takes 2 minutes (the sheet's three 0-10 scores, then the REDCap
survey; your answer of 2026-09-26) and is followed by a 2-minute streamed recording, so the
tightest clock is one rating every 4 minutes, back to back. From minute 30 that places ratings at
minutes 30, 34, 38, 42, 46, 50, 54, 58, 62 and 66: **10 ratings after the wait**, the last
recording ending at minute 70. Two more ratings sit inside the wait, at minutes 6 and 18, each
labelled with its minutes since 0 mA and **not counted**: they cost no counted rating, they give the
start of the time course, and the one at minute 18 falls just past the 14 minutes decision 272
covered. **12 ratings at 0 mA in all, each with the REDCap survey and its own recording.** If the
patient or the clinical team finds back-to-back ratings too much, a 5-minute clock (a minute's pause
after each recording) gives 8 ratings after the wait instead of 10.

| Door to door (min) | Chair (min) | Minutes since 0 mA | Part | Setting | Ratings |
|---|---|---|---|---|---|
| 0-20 | — | — | Setup: settings check on the tablet, review of the stop rules and the agreed stop level, connect | as in force | — |
| 20-21 | 0-1 | — | Start streaming, confirm the settings in force, change nothing | L 3 / R 2.5 mA, 55 Hz | — |
| 21-22 | 1-2 | — | Streaming running; at the home sequence's follow-up, hold 5 is rated here (sheet only) | as in force | (1 at the follow-up) |
| 22-23 | 2-3 | — | Both sides to 0 mA; the time the later side reaches 0 mA is minute 0 | L 0 / R 0 mA | — |
| 23-29 | 3-9 | 0-6 | Wait | 0 mA | — |
| 29-33 | 9-13 | 6-10 | Rating (sheet, then REDCap), then a 2-minute recording; **not counted** | 0 mA | 1 |
| 33-41 | 13-21 | 10-18 | Wait | 0 mA | — |
| 41-45 | 21-25 | 18-22 | Rating, then a recording; **not counted** | 0 mA | 1 |
| 45-53 | 25-33 | 22-30 | Wait; **the wait ends at minute 30** | 0 mA | — |
| 53-93 | 33-73 | 30-70 | **Counted: 10 ratings, one every 4 minutes (at 30, 34, ..., 66), each followed by its 2-minute recording** | 0 mA | 10 |
| 93-94 | 73-74 | 70-71 | Impedance test at a fixed measurement current (decision 133) | — | — |
| 94-95 | 74-75 | — | Restore the settings in force; stop streaming | L 3 / R 2.5 mA, 55 Hz | — |
| 95-105 | 75-85 | — | Comfort check; rating at its minute 10 (sheet only); start the export | as in force | 1 |
| 105-120 | — | — | Export the session files, upload the sheet | — | — |

**Length.** 85 minutes in the chair, **120 door to door, no minute to spare**: each extra minute of
setup or export comes off the end of the counted ratings, one rating for every 4 minutes. 70
minutes at 0 mA. 13 rating rows on the sheet (12 at 0 mA and 1 back on stimulation), plus hold 5's
rating at the follow-up. One person for the whole visit, about 2.0 person-hours, with a clinician
reachable for the stop level.

**What it can answer.** How pain (0-10 and 0-100) and band power in all 22 bands on L 1-3+ and
R 0-3+ move over the first 70 minutes after switching off from a current held for 3 to 4 days,
every point labelled with its minutes since 0 mA; and, on the 10 ratings after the wait, each
matched to a recording taken in the 2 minutes after it, the rank correlation of pain with band power,
including L 1-3+ at 21.5 and 22.5 Hz, the bands of the 2025 reading. That reading matched ratings to
recordings only by day, typically 5.1 hours apart (report 02); here they are minutes apart.

**What it cannot.** A settled-off reading (the sentence at the head of this section). A p-value on
the band-against-pain reading: rotating 10 ratings in time gives a smallest possible p of 0.1. And
the 10 ratings span 36 minutes of one visit, so pain may move little across them; a
correlation needs pain to vary.

**The REDCap survey (your answer of 2026-09-26).** At each rating at 0 mA the patient gives the
sheet's three 0-10 scores and then files the REDCap survey, so the block reads the same 0-100 scale as
the 2025 reading (which rose with that scale and was not detectable with the 0-10 score, decision
262(a)).

**What the record says about the wait.** Three measurements in this project bear on it, and none
covers the window the wait is for:

- The clinic ladders' carry-over model (`StimOptimizer/OBJECTIVE_SPEC.md`, 2026-08-30): an effect
  that builds while a current is delivered and fades after, with the fading time tried from 1.2
  seconds to 8 hours on the left-leg ratings. The fit got steadily worse as the fading time grew
  (406.8 at the shortest, 423.7 at 60 minutes, 424.5 at 8 hours, lower is better): no carry-over on
  any time scale tested. But those steps last minutes and move between currents mostly above 0 mA;
  none is a switch-off after days at a steady current.
- Decision 272: a stimulation-off setting rated and then rated again, a median of 14 minutes later,
  on 10 occasions: -0.10 on the 0-10 score (-1.11 to +0.58). Pain did not detectably rise over about
  a quarter of an hour. Nothing in the record follows an off period past that.
- Decision 262(b), as report 02 reads it: a current with memory, from 1 hour to 14 days, never
  predicted pain better than the current in force; up to about 3 days it was no worse. That cannot
  tell a memory of 0 from one of an hour or two.

So a 30-minute wait is a ruling, not a finding. Visit 2's own readings from minute 6 to minute 66
will be the first measurement of part of that span, which is what any later ruling on the wait
would rest on.

**Where it goes.** At the home sequence's follow-up, after hold 5 has been rated, so the switch-off
comes after 3 to 4 days at the left 3.0 mA in force: the case the record has never measured. Not
inside the home sequence, since a day at 0 mA would break a hold.

**Considered and not chosen** (the numbers of the 2026-09-26 draft):

- **(a)** The same 70 minutes at 0 mA with the 90-minute wait kept: 4 ratings (minutes 6, 26, 46, 66), none after the wait, so a description of the first hour only.
- **(b)** Off started in clinic and continued at home to minute 270: 10 ratings after minute 90 against the chronic log's one band a side (it keeps logging at 0 mA: 9,593 left readings on 76 days), at the cost of about 3.2 hours on call, a rescue plan for switching stimulation back on at home, and ethics coverage no answer names in words.
- **(d)** No off block this round: nothing new on question 3; the 2025 day-matched reading stays the only zero-current lead.

### 6.2 The home hold-and-return sequence (open-label; ethics confirmed 2026-09-26)

**What it is.** Report 02, part 3, and the revised plan's Lane C row 3: the left current is held for
3 to 4 days, moved, and returned, five holds in all; the right side stays at 2.5 mA, the rate at
55 Hz and the pulse widths as in force throughout. Day 0 is Visit 1, which ends on the settings in
force, so the first hold needs no change. **The currents are approved as proposed (2026-09-26).**

| Hold | Left current | Length | Started by |
|---|---|---|---|
| 1 | 3.0 mA (in force) | 3-4 days | the end of Visit 1 |
| 2 | 4.0 mA, up 1 mA | 3-4 days | at-home session 1 |
| 3 | 3.0 mA, back to the start | 3-4 days | at-home session 2 |
| 4 | 2.0 mA, down 1 mA, only if the lower currents were tolerated in the Visit 1 ladder and the patient agrees | 3-4 days | at-home session 3 |
| 5 | 3.0 mA, back to the start | 3-4 days | at-home session 4 |

The whole sequence runs 15 to 20 days and ends with a rating at the follow-up. **Why 3 to 4 days:**
a current with memory was no worse than the current in force up to about 3 days and clearly worse at
7 days or more (decision 262(b), as report 02 reads it), so 3-4 days sits at the edge the data on
file could not resolve. **Why 1 mA either way:** the ladder's own step, which keeps the upper hold
0.5 mA under the ceiling at a current the left has held before (§3).

**The 2 mA hold's condition, and the new ladder.** Your approval reads "the 2 mA hold only if 2 mA was
tolerated in that day's ladder". The ladder you then approved (starting with a rise to 3.5 mA) steps
through 2.5, 1.5 and 0.5 mA and **never delivers 2.0 mA**. This draft writes the condition as: 1.5
and 2.5 mA both tolerated on both legs of the Visit 1 ladder (they bracket 2.0 mA), and the patient
agrees. **Accepted (2026-09-26).**

**How each change is made.** By the study team, in person, with the clinician's programming tablet,
at an at-home session written on an at-home testing sheet, as the lab already does (the 30 sheets on
file are clinic and at-home sheets, decision 272). Each session first rates the hold that is ending,
then sets the next current, then watches for comfort for 10 minutes before leaving (§9.4). The
patient does not change their own settings. Ratings otherwise continue on the patient's usual REDCap
schedule. **At home the sessions are not bound by the 2-hour rule. If any is held in clinic instead,
it is well inside it:** 20 minutes of setup, a rating, the change, a 10-minute comfort check and a
15-minute export come to about 47 minutes door to door on this draft's own allowances.

**What it records.** Pain from REDCap and the at-home sheets; band power from the left chronic log
as it is today, one reading every 10 minutes (decision 252), on L 1-3+ at 23.44 Hz, not re-pointed
(item 0.3(a) is not needed for this). The rate stays at 55 Hz, so the 25 Hz landing of §4 sits in
the chronic log's band in every hold alike.

**Open-label.** A patient with years of stimulation can likely feel a 1 mA change (critique 09), so
the sequence is open-label and sequential, not blinded.

**Safety.** A pain flare can outlast a session, so report 02 asks for a separate safety and rescue
plan for this part, agreed with the clinical team, not folded into the visit sign-off: who the
patient calls, and that any hold can be ended early by returning to 3.0 mA.

### 6.3 Staff time and patient time, per visit

| Visit | Door to door | Person at the tablet | Second person (ratings, minute-3 question) | Total |
|---|---|---|---|---|
| **Visit 1** (rate swap, ladder) | **98 min** | 98 min | setup, streaming start, rate swap and ladder: 20 + 50 = 70 min | **about 2.8 person-hours** |
| Visit 1 with the second cycle | 120 min | 120 min | 92 min | about 3.5 person-hours |
| **Visit 2** (the off block, option (c)) | **120 min** | 120 min (ratings included) | not needed | **about 2.0 person-hours**, a clinician reachable |
| Each of the four at-home sessions | not a visit; about 47 min if held in clinic | the whole session | not needed | under 1 person-hour each, travel not counted |

The draft before this revision, one visit of 334 minutes in the chair, came to about 6 h 10 min of
clinic time and 7.3 person-hours; the off block was almost all of it.

---

## 7. The ladder whose falls come first

**Design (your answer of 2026-09-26, "sure start with ladder to 3.5").** From the current in force,
3.0 mA, the left side **rises once to 3.5 mA, then steps down in 1 mA steps to 0.5 mA, back up in
1 mA steps to 3.5 mA, and returns to the 3.0 mA in force**:

| Step | Left current | Reached by | Rated |
|---|---|---|---|
| 1 | 3.5 mA | a rise from 3.0 (the one rise before the falls) | yes |
| 2 | 2.5 mA | a fall | yes: pair with step 6 |
| 3 | 1.5 mA | a fall | yes: pair with step 5 |
| 4 | 0.5 mA | a fall (the turn) | yes, once |
| 5 | 1.5 mA | a rise | yes |
| 6 | 2.5 mA | a rise | yes |
| 7 | 3.5 mA | a rise | yes: the same current as step 1, 12 minutes later, also reached by a rise |
| 8 | 3.0 mA | a fall, back to the current in force | yes |

**8 steps, each a 1-minute ramp row and a 1-minute test row with a rating: 16 minutes and 8 ratings.**
The right side is held at 2.5 mA and the rate at 55 Hz, the rate in force (your ruling 3 of decision
233, kept by your answer 9 of 2026-09-25). **Every step is at or under 3.5 mA, 1.0 mA under the
4.5 mA ceiling,** and 3.5 mA has been delivered on the left before (§3).

**The pairs.** Two currents are rated on both legs, **1.5 and 2.5 mA, and at both the fall comes
first**, the reverse of 2026-09-16. They are the currents that visit also paired (0.5, 1.5, 2.5 and
3.5 mA, decision 272: down minus up -0.5 at 1.5 mA and 0.0 at 2.5 mA on its left ladder), so the two
visits can be compared at the same currents. 0.5 mA is rated once, where the ladder turns. 3.5 mA is
rated twice, both times reached by a rise, which gives a repeat of one setting 12 minutes apart
within the ladder. 3.0 mA is rated held in A2 just before the ladder and again at step 8, reached by
a fall. The first move is a rise, which the earlier draft avoided; the rise is a single 0.5 mA step
from the current in force, and the pairs themselves are unaffected.

**What it costs against the earlier draft** (3, 2, 1, 0, 1, 2, 3 mA): one more step and two more
minutes (8 steps and 16 minutes against 7 and 14), the same number of pairs, and the lowest current
0.5 mA instead of 0 mA.

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
  difference of 0.44) would be detected about 55% of the time at a two-sided 5% level (computed on
  2026-09-25, same method as §5; the number of pairs is unchanged by the new start). That rests on
  three occasions' worth of scatter and should be read as rough.
- **At 55 Hz every band from 22.5 to 29.5 Hz carries a folded multiple of the rate** (decision 277),
  including the whole pain-linked family on the left, so the ladder's band readings in that family
  need the rate swap's answer beside them.

**What it does not do.** It holds the right side at 2.5 mA, so it does not add the current pairs
decision 258 named as missing for your ruling 5 (the pairs need the right side at 3 to 3.5 mA); the
home sequence holds the right at 2.5 mA too. Visit 1's ratings enter the clinic-sheet stream as
usual: 12 at L 3 / R 2.5 mA and 55 Hz, 5 at 60 Hz (a rate with no other clinic ratings), 2 each at
L 3.5, L 2.5 and L 1.5 mA and 1 at L 0.5 mA with the right at 2.5.

---

## 8. The analysis, stated before the visits

**The rate swap and the ladder (Visit 1)**

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
   whichever way it goes, with whether the clock condition held.
4. **The PSD computed from the voltage trace at fine resolution** (a fraction of a hertz over a
   10-minute block, against the 5 Hz bands): narrow peaks at 25.0 Hz and 27.5 Hz under 55 Hz; at 10.0,
   20.0 and 30.0 Hz under 60 Hz. Descriptive.
5. **The device's own power reading** at 23.44 Hz, 55 Hz blocks against the 60 Hz block, the same way.
6. **Pain in the swap:** the mean of each block's ratings with its count, by rate and by whether the
   patient noticed a change. Descriptive; the swap is not sized for pain.
7. **The ladder:** as §7, at 1.5 and 2.5 mA reported beside the 2026-09-16 ladder's numbers at the
   same currents; the two 3.5 mA readings beside each other.

**The off block (Visit 2, §6.1)**

8. **Pain and band power against minutes since 0 mA**, every point, the 2 ratings inside the wait
   included, so a fade after stopping stimulation shows as a trend; pain on both the 0-10 and the
   REDCap 0-100 scales; all 22 bands on L 1-3+ and R 0-3+ from the 2-minute recording after each
   rating. Descriptive.
9. **Band against pain on the 10 ratings after the wait** (minutes 30 to 66): the rank correlation
   of the REDCap 0-100 scale and of the 0-10 score with each band's power in the recording taken in
   the 2 minutes after each rating, L 1-3+ at 21.5 and 22.5 Hz (the 2025 reading's bands) named
   first, each side read on its own, with the count. No p-value: 10 ratings 4 minutes apart on one
   day cannot carry one (rotating 10 ratings in time, the project's way of seeing what happens by
   chance, gives a smallest possible p of 0.1). Read with the sentence at the head of §6.1: a flat
   result cannot be told apart from relief that has not worn off.
10. **The same bands with the current on**, read from the stored grid with the current taken out
    (decision 234), beside items 8 and 9 (report 02).

**The home sequence**

11. **Pain at the same current, 3.0 mA, in holds 1, 3 and 5**, and in holds 2 and 4 beside them, from
    the REDCap ratings and the at-home sheet ratings, each hold's mean with its count. A lingering
    effect shows as hold 3 differing from hold 5, or as the first days of a hold differing from its
    last. Hold 1 starts the day of the ladder, which spent 6 minutes at 1.5 mA or less, so holds 3
    and 5 are the cleaner comparison.
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
forward to the rows below, as it does for the two-row steps today. In Visit 1 a row is one minute.
In Visit 2 a row is a rating (120 s: the sheet's scores, then the REDCap survey), a
recording (120 s) or a wait, its length in the Duration column. **Left blank for the day:** Group,
sEEG Contacts, Threshold, Side Effect? (write any side effect and its 0-4 score), Timestamp (write
the time as each row begins), Movement/Change point, and the seven pain columns (on rows whose note
says "Pain rating now", fill Overall, Back and Left Leg on the 0-10 scale).

**Checked against the lab's own reader.** Generated by `BRAVO/_agent_bridge/_protocol_rows_gen.py`
(rewritten 2026-09-26), filled with a constructed placeholder score on every rating row and read back
through the clinic-sheet parser (`clinic_pain._parse_generic_stim_testing`) by
`BRAVO/_agent_bridge/_protocol_sheet_check.py`, no data read. Run on 2026-09-26 in the server
container:

- **Visit 1: 24 rating rows placed, 24 read, 0 dropped, 0 flagged as unparsed prose, 0 skipped for a
  missing setting.** Read back as 12 at 55 Hz L 3 / R 2.5 mA, 5 at 60 Hz L 3 / R 2.5 mA, 2 each at
  L 3.5, L 2.5 and L 1.5 mA and 1 at L 0.5 mA with the right at 2.5 mA, every one at L 100 / R 150 µs.
- **Visit 1 with the second cycle inserted: 34 placed, 34 read, 0 dropped**; 17 at 55 Hz L 3 / R 2.5 mA
  and 10 at 60 Hz, the rest unchanged.
- **Visit 2, the off block (option (c)), rerun 2026-09-26 after the rows were regenerated: 13 rating
  rows placed, 13 read, 0 dropped, 0 flagged as unparsed prose, 0 skipped for a missing setting**:
  12 with both sides at 0 mA and 1 at L 3 / R 2.5 mA (the rating after stimulation is back on). The
  REDCap instruction and the counted / not-counted words on its rating rows are not mistaken for a
  written score. The reader reads all 12 off ratings alike, as both sides at 0 mA; which 10 count is
  decided in the analysis, from the time written on each row against the time of 0 mA. The same run
  read Visit 1, the second cycle and the home sheets exactly as above.
- **The home sheets: 5 placed, 5 read, 0 dropped** (3 at L 3, 1 at L 4, 1 at L 2 mA).

### 9.1 Visit 1 (55 rows, 63 minutes in the chair, 98 door to door)

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
,,,,,,,60,,,,"Block A2, 55 Hz, minute 10 of 10. Pain rating now: Overall, Back, Left Leg. END OF THE RATE SWAP. A second cycle only if the rule of section 5 is met on numbers in hand now AND the visit is on time (this row ends at door-to-door minute 54 or earlier; with the second cycle the visit is exactly 120 minutes); otherwise go to the ladder and the second cycle moves to a later visit.",,,,,,,
,L C+2- / R C+1-2-,,L 3.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 1 of 8: set LEFT to 3.5 mA (up, the one rise before the fall); right held at 2.5 mA. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 1 of 8, test row, left 3.5 mA (up, the one rise before the fall). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 2.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 2 of 8: set LEFT to 2.5 mA (down); right held at 2.5 mA. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 2 of 8, test row, left 2.5 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 1.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 3 of 8: set LEFT to 1.5 mA (down); right held at 2.5 mA. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 3 of 8, test row, left 1.5 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 0.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 4 of 8: set LEFT to 0.5 mA (down, the turn); right held at 2.5 mA. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 4 of 8, test row, left 0.5 mA (down, the turn). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 1.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 5 of 8: set LEFT to 1.5 mA (up); right held at 2.5 mA. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 5 of 8, test row, left 1.5 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 2.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 6 of 8: set LEFT to 2.5 mA (up); right held at 2.5 mA. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 6 of 8, test row, left 2.5 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 3.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 7 of 8: set LEFT to 3.5 mA (up); right held at 2.5 mA. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 7 of 8, test row, left 3.5 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 8 of 8: set LEFT to 3 mA (down, back to the current in force); right held at 2.5 mA. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 8 of 8, test row, left 3 mA (down, back to the current in force). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,End of the ladder: the settings in force are back (L 3 / R 2.5 mA). Stop streaming. Not analysed.,,,,,,,
,,,,,,,60,,,,Impedance test at a fixed measurement current (decision 133). No rating.,,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Confirm the settings in force on the tablet after the impedance test (L 3 / R 2.5 mA, 55 Hz, L 100 / R 150 us); write the time. Not analysed.",,,,,,,
,,,,,,,540,,,,"Comfort check, minutes 1 to 9: watch for comfort. Go through the home sequence's dates with the patient: today is day 0, the start of hold 1 (left 3 mA, in force). No rating.",,,,,,,
,,,,,,,60,,,,"Comfort check, minute 10. Pain rating now: Overall, Back, Left Leg. Export the session.",,,,,,,
```

### 9.2 The second rate-swap cycle, only under the rule and the clock condition of §5 (22 rows, 22 minutes)

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

### 9.3 Visit 2, the off block, option (c) (34 rows, 85 minutes in the chair, 120 door to door)

At the home sequence's follow-up, the second row ("Streaming running") is also where hold 5 is rated.
The 2 ratings inside the wait say "not counted" on their rows; the 10 from minute 30 say "Counted".

```csv
Group,Contacts,sEEG Contacts,Amp (mA),Rate (Hz),PW (µs),Threshold,Duration (s),Side Effect?,Timestamp,Movement/Change point,General Notes / Pt Verbal Notes,Overall,Head,Back,Left Leg,Left Foot,Right Leg,Right Foot
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,Start BrainSense streaming on L 1-3+ and R 0-3+. Confirm the settings in force on the tablet; change nothing. Not analysed.,,,,,,,
,,,,,,,60,,,,Streaming running; patient seated and still. Not analysed.,,,,,,,
,L C+2- / R C+1-2-,,L 0 / R 0,55,L 100 / R 150,,60,,,,Set BOTH sides to 0 mA: the stimulation-off block begins. Write the time each side reaches 0 mA; the later of the two is minute 0 of the block. Stop rules of section 6 apply throughout. Not analysed.,,,,,,,
,,,,,,,360,,,,"Off block, minutes 0 to 6: wait. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 6. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Inside the 30-minute wait: labelled with its minutes since 0 mA, not counted.",,,,,,,
,,,,,,,120,,,,"Off block, minute 8: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,480,,,,"Off block, minutes 10 to 18: wait. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 18. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Inside the 30-minute wait: labelled with its minutes since 0 mA, not counted.",,,,,,,
,,,,,,,120,,,,"Off block, minute 20: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,480,,,,"Off block, minutes 22 to 30: wait. No rating. The wait ends at minute 30.",,,,,,,
,,,,,,,120,,,,"Off block, minute 30. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Counted: after the 30-minute wait.",,,,,,,
,,,,,,,120,,,,"Off block, minute 32: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 34. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Counted: after the 30-minute wait.",,,,,,,
,,,,,,,120,,,,"Off block, minute 36: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 38. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Counted: after the 30-minute wait.",,,,,,,
,,,,,,,120,,,,"Off block, minute 40: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 42. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Counted: after the 30-minute wait.",,,,,,,
,,,,,,,120,,,,"Off block, minute 44: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 46. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Counted: after the 30-minute wait.",,,,,,,
,,,,,,,120,,,,"Off block, minute 48: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 50. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Counted: after the 30-minute wait.",,,,,,,
,,,,,,,120,,,,"Off block, minute 52: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 54. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Counted: after the 30-minute wait.",,,,,,,
,,,,,,,120,,,,"Off block, minute 56: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 58. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Counted: after the 30-minute wait.",,,,,,,
,,,,,,,120,,,,"Off block, minute 60: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 62. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Counted: after the 30-minute wait.",,,,,,,
,,,,,,,120,,,,"Off block, minute 64: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,120,,,,"Off block, minute 66. Pain rating now: Overall, Back, Left Leg on the sheet (0-10), then the patient files the REDCap survey (its 0-100 scales); write the time it is submitted. Counted: after the 30-minute wait.",,,,,,,
,,,,,,,120,,,,"Off block, minute 68: start a 2-minute BrainSense streaming recording on L 1-3+ and R 0-3+; write its start time. No rating.",,,,,,,
,,,,,,,60,,,,"Off block, minute 70: impedance test at a fixed measurement current (decision 133). No rating.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Restore the settings in force (L 3 / R 2.5 mA, 55 Hz, L 100 / R 150 us); write the time each side is back at its current. End of the off block. Stop streaming.",,,,,,,
,,,,,,,540,,,,"Back on stimulation, minutes 1 to 9: watch for comfort. No rating.",,,,,,,
,,,,,,,60,,,,"Back on stimulation, minute 10. Pain rating now: Overall, Back, Left Leg. Export the session.",,,,,,,
```

### 9.4 The home sequence, one at-home sheet per session (9 rows)

Each at-home session is its own sheet, so its first row writes the settings in force; the reader
carries nothing over from one sheet to the next. The Duration column is left blank: each hold is 3
to 4 days, and the sheet records the time each hold starts.

```csv
Group,Contacts,sEEG Contacts,Amp (mA),Rate (Hz),PW (µs),Threshold,Duration (s),Side Effect?,Timestamp,Movement/Change point,General Notes / Pt Verbal Notes,Overall,Head,Back,Left Leg,Left Foot,Right Leg,Right Foot
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,,,,,"Home sequence, at-home session, end of hold 1 of 5 (left 3 mA, held 3 to 4 days). Pain rating now: Overall, Back, Left Leg. Write any side effect and its 0-4 score.",,,,,,,
,L C+2- / R C+1-2-,,L 4 / R 2.5,55,L 100 / R 150,,,,,,"Set LEFT to 4 mA (up); right held at 2.5 mA, 55 Hz, pulse widths unchanged. Watch for comfort for 10 minutes before leaving. Hold 2 of 5 starts now; write the time.",,,,,,,
,L C+2- / R C+1-2-,,L 4 / R 2.5,55,L 100 / R 150,,,,,,"Home sequence, at-home session, end of hold 2 of 5 (left 4 mA, held 3 to 4 days). Pain rating now: Overall, Back, Left Leg. Write any side effect and its 0-4 score.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,,,,,"Set LEFT to 3 mA (back to the start); right held at 2.5 mA, 55 Hz, pulse widths unchanged. Watch for comfort for 10 minutes before leaving. Hold 3 of 5 starts now; write the time.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,,,,,"Home sequence, at-home session, end of hold 3 of 5 (left 3 mA, held 3 to 4 days). Pain rating now: Overall, Back, Left Leg. Write any side effect and its 0-4 score.",,,,,,,
,L C+2- / R C+1-2-,,L 2 / R 2.5,55,L 100 / R 150,,,,,,"Set LEFT to 2 mA (down, only if 1.5 and 2.5 mA were tolerated on both legs of the Visit 1 ladder and the patient agrees); right held at 2.5 mA, 55 Hz, pulse widths unchanged. Watch for comfort for 10 minutes before leaving. Hold 4 of 5 starts now; write the time.",,,,,,,
,L C+2- / R C+1-2-,,L 2 / R 2.5,55,L 100 / R 150,,,,,,"Home sequence, at-home session, end of hold 4 of 5 (left 2 mA, held 3 to 4 days). Pain rating now: Overall, Back, Left Leg. Write any side effect and its 0-4 score.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,,,,,"Set LEFT to 3 mA (back to the start); right held at 2.5 mA, 55 Hz, pulse widths unchanged. Watch for comfort for 10 minutes before leaving. Hold 5 of 5 starts now; write the time.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,,,,,"Home sequence, end of hold 5 of 5 (left 3 mA, held 3 to 4 days), at the follow-up. Pain rating now: Overall, Back, Left Leg. No change: the setting in force stays.",,,,,,,
```

---

## 10. What these visits cannot settle

- One visit day is one day. A shift in the rate swap is a lead to repeat at a later visit, in the
  reverse order (60-55-60); no shift is the detectable change of §5 and a reason to repeat longer.
- The rate swap says whether power follows the rate. It says nothing about whether any band tracks
  pain; that question stays with Visit 2's off block and with the current-removal work
  already built (decisions 234, 240-242).
- Visit 2 reaches no rating after minute 66 off. Its 10 counted ratings follow a 30-minute wait the
  record does not support, so it describes the first hour off, not the settled off state, and a flat
  result cannot be told apart from relief that has not worn off. Its 10 pairs on one day can show the
  sign and rough size of a zero-current reading matched in minutes, not confirm it (decision 282:
  52 to 132 calendar days).
- The ladder gives two pairs on one day. It can show which way the order effect points; it cannot
  size carry-over.
- The home sequence is one pass: two comparisons at the same current (holds 1 and 3, holds 3 and 5),
  enough to show the sign of a lingering effect if it is large, not its size (report 02). Repeating
  the whole sequence later is how confidence is built.
- The weeks confound everything already on file (the revised plan, §4): current, rate and calendar
  moved together. Visit 1 separates rate from calendar within one day, and the home sequence
  repeats one current weeks apart; neither undoes the weeks already on file.

---

## 11. Questions

**Answered by you on 2026-09-26, and applied above**

- The 2-hour visit limit, door to door ("max visit is 2 hrs"): Visit 1 is 98 minutes, Visit 2
  (the off block, §6.1) 120.
- Research-ethics coverage of the multi-day home sequence ("yes multi day home seq ok"): the sequence
  starts at the end of Visit 1.
- The home holds' currents, left 3, 4, 3, 2, 3 mA, 3-4 days each, approved as proposed.
- The ladder starts with a rise to 3.5 mA ("sure start with ladder to 3.5"): 3.5, 2.5, 1.5, 0.5, 1.5,
  2.5, 3.5, 3.0 mA (§7).
- The REDCap survey at every rating of any stimulation-off block ("yes files redcap on off blocks").
- Coverage for the first exposure to 60 Hz ("60 hz ok").
- **The stimulation-off block: option (c)**, a shorter wait than 90 minutes inside one 2-hour visit
  ("stim off -c yes"): Visit 2 (§6.1), a 30-minute wait, 10 ratings after it, 120 minutes door to
  door; options (a), (b) and (d) kept in §6.1 as considered and not chosen.
- **The 2 mA home hold's condition**, "1.5 and 2.5 mA both tolerated on both legs of the Visit 1
  ladder" (that ladder never delivers 2.0 mA), accepted (§6.2).

**Still open for you: nothing.**

**For Medtronic or the clinical team**

1. **Item 0.3(b)**: does a rate-only change dip the delivered current? The discard rule covers it
   either way; an extended discard rules out the second cycle at Visit 1.
2. **Item 0.3(d), second half**: can the rate change on one side alone? Not needed for Visit 1.
3. **Item 0.3(a)**: does Single Threshold Inverse change the delivered current? Needed only to
   re-point the home chronic log; without it the log stays as it is.
4. **Can the first cycle's recording be taken off the tablet and analysed while the patient is still
   in the chair?** If not, the second-cycle rule is applied afterwards and a needed second cycle goes
   to a later visit (§5).
5. **For Visit 2's off block**: the stop level, a fresh clinical review, and whether the patient can
   manage 12 surveys in 70 minutes, the last 10 back to back (if not, the 5-minute clock of §6.1: 8
   ratings after the wait).
6. **For the home sequence**: its safety and rescue plan, and who makes the four at-home sessions.
7. **A second person for ratings** during Visit 1.
8. **The setup and export allowances** (20 and 15 minutes) are this draft's; if the lab's are
   longer, Visit 1's 22 spare minutes absorb it without the second cycle, and the second cycle then
   moves to a later visit. Visit 2 has no spare minute: each extra minute of setup or export comes off
   the end of the counted ratings, one rating for every 4 minutes.

## 12. Sources

- Revised plan and critiques: `artifacts/research_2026-09-25_options/{11_REVISED_PLAN,08_critique_science,09_critique_feasibility,02_next_clinic_visit_protocol}.md`.
- Decisions 133, 138, 145, 160, 165, 181, 202, 213, 217, 230, 233, 234, 237, 252, 258, 262, 264,
  272, 276, 277, 282 (`DECISIONS_and_open_items.md`; the full rows in `docs/decision_log_full_2026-09-19.md`
  for decisions up to that date).
- The clinic ladders' carry-over model: `BRAVO/modules/StimOptimizer/OBJECTIVE_SPEC.md`, amendment of
  2026-08-30.
- Device facts: `DEVICE_percept_rc.md` §§3, 6, 9.
- Literature cited through report 02: Meier et al. 2024 (*Neuromodulation*, PMID 38456888); Temperli
  et al. 2003 (*Neurology*, PMID 12525722).
- Read-only scripts run for this draft, printing counts and aggregates only (gitignored scratch):
  `BRAVO/_agent_bridge/_rateswap_mdc.py` (2026-09-25: the scatter of §5 and the change per
  milliamp), `BRAVO/_agent_bridge/_rateswap_settings.py` (2026-09-25: the settings in force, the rates
  in the settings history, the one row of 3,344 with different rates on the two sides),
  `BRAVO/_agent_bridge/_protocol_offlog_probe.py` (2026-09-26: the chronic log at 0 mA, for option (b) of §6.1, not chosen),
  `BRAVO/_agent_bridge/_protocol_rows_gen.py` (the rows of §9, their minutes and rating counts,
  rewritten 2026-09-26, and its off-block rows again the same day for option (c)) and `BRAVO/_agent_bridge/_protocol_sheet_check.py` (the reader check of §9,
  run 2026-09-26). The harmonic table of §4 was run on the host from `StimOptimizer.titration_plan`
  with no data. The detectable changes of the second-cycle rule and the ladder's 55% were computed by
  hand from §5's scatter with the same normal-approximation method as the table.
