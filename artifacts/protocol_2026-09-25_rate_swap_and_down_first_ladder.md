# Next visit, draft protocol: the rate swap and a ladder that steps down first

> Draft for the PI (Prasad Shirvalkar), 2026-09-25. **Nothing is scheduled and nothing here is an
> instruction to program anything.** Lane C item 1 of `artifacts/research_2026-09-25_options/11_REVISED_PLAN.md`,
> with every accepted critique folded in (`08_critique_science.md` M3; `09_critique_feasibility.md`
> on staff time, discard windows, the 29.5-30 Hz band, open-label wording and prerequisites 0.2 and
> 0.3) and decision 277 (the one harmonic check). Every number below is either quoted from a decision
> with its number, or was computed for this draft on 2026-09-25 by a read-only script whose name is
> given; none is carried forward from a document without being re-read.

**Words used here.** A **ladder** is a planned run of current steps within one visit, one setting at
a time. A band **carries a folded multiple of the stimulation rate** when a whole multiple of the
pulse rate, folded down by the device's sampling of the brain signal at 250 times a second, lands
within 2.5 Hz of the band's centre (half the 5 Hz band width). At 55 Hz, five times the rate
(275 Hz) reappears at 25 Hz. That is a statement about where numbers land and needs care, never
disbelief (your correction of 2026-09-06); it does not say the band measures the stimulator.
**Band power** is always raw power in the device's units; log power enters nothing here
(decision 202). **Open-label** means the patient may know, or feel, which setting is running, and no
reading assumes otherwise.

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
   by stepping down reverses the order at the same currents.

The first question is the priority: if the visit is cut short, the rate swap's first cycle is the
part to keep. Both answers will be leads to repeat, not established results (METHODS §7; one visit
day settles nothing).

---

## 2. Before it can be scheduled

| Item (numbering from the revised plan's Lane 0) | Why this visit needs it | If the answer is unfavourable |
|---|---|---|
| **0.2** Research-ethics coverage | This visit holds no stimulation-off block beyond the 2-minute passes through 0 mA that every ladder since decision 160 already includes and the lab's usual off-stimulation baseline at the end. But the rate change is made for a research question, and 60 Hz has never been programmed on this patient (the rates in the device's settings history are 10, 55, 110, 125, 130, 145 and 165 Hz; read 2026-09-25). Whether a research-motivated rate change at a clinic visit counts as covered titration is the part of 0.2 this visit needs answered | The rate swap waits; the down-first ladder alone is ordinary titration and could run first |
| **0.3(b)** Does a rate-only change dip the delivered current? | The design assumes the current is the same before and after each rate change. Nothing in this project measures it: the ramp times in `DEVICE_percept_rc.md` §9 are for current steps only | If it dips, the discarded minute after each change is extended until the tablet shows the current back at its setting, and the sheet records that time (built into the change rows below) |
| **0.3(d), new** Can the rate be changed without stopping BrainSense streaming, and can it change on one side alone? | Unverified. The two sides have carried the same rate in all but 1 of 3,344 settings rows aligned in time (device settings history, read 2026-09-25), which suggests the rate is set for both sides together | If streaming must stop for a rate change, each change row becomes: stop streaming, change the rate, restart. Each recording this patient's exports hold lasts about 100-500 s (`DEVICE_percept_rc.md` §3), and the 2026-09-16 session restarted twice (decision 213), so restarts are expected either way; the analysis already joins recordings separated by under 20 s with the current held (decision 213) |
| **0.3(a) and (c)** | Not needed by this visit (they concern the home sequence) | — |

Also agreed in advance with the clinical team, not improvised on the day: the stop rules of §6 and a
second person for ratings (§6, staff time).

---

## 3. The settings the visit holds

Read from the device's own settings history on 2026-09-25 (the newest row per side of the stored
therapy settings); **confirm on the tablet on the day, and if the currents in force differ, keep the
day's currents and shift the ladder's steps to start from the left current in force.**

| | Left | Right |
|---|---|---|
| Stimulating contacts | C+2- (cathode 2a-2b-2c) | C+1-2- (cathode 1a-1b-1c-2a-2b-2c) |
| Current | 3.0 mA | 2.5 mA |
| Pulse width | 100 µs | 150 µs |
| Rate | 55 Hz | 55 Hz |
| Sensing pair the device allows (decision 217) | L 1-3+ | R 0-3+ |

The safety ceiling is 4.5 mA each side (decisions 145, 160); nothing here goes above 3.0 mA.
Moving from 55 to 60 Hz delivers 9.1% more pulses a second at the same charge per pulse. 60 Hz is
inside the rates the device's closed-loop mode accepts (55 Hz and above, decision 138), so a 60 Hz
closed-loop configuration stays possible if you later choose it (the revised plan's question 9).

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
  limit on where a closed-loop sensing band may sit and outside the range of frequencies ever checked against the
  device's own reading (7.8-28.3 Hz, `DEVICE_percept_rc.md` §6). It can show where half the rate
  moves to; it can never itself become a band the device senses from.

---

## 5. The smallest change the rate swap could detect (critique 08, M3)

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
so this offset may come from order and time rather than from whether the current was rising or falling, which is the second reason for the
down-first ladder (§7). The device's own power reading at 23.44 Hz shows the same thing: +0.33 over
its 3 pairs.

**The scatter of one reading.** Taking the 22% offset as a real effect of order and removing it, a
single 30-second reading scatters by about 16% of the band's power (0.23 / √2 = 0.164). Counting the
offset as scatter too, 23% (root mean square of the pairs, 0.225). In the four "moves out" bands,
23.5-26.5 Hz, the first figure runs from 12% to 19% band by band, on 3 pairs each.

**The smallest detectable change**, as a fraction of the band's power at 55 Hz, with 80% power at a
two-sided 5% significance level, treating the scatter as known:

| Design | Contrast | Scatter 16% | Scatter 23% | Scatter 16%, corrected for the 4 "moves out" bands |
|---|---|---|---|---|
| One cycle, 55-60-55 | 60 Hz block against the two 55 Hz blocks | 56% | 77% | 67% |
| Two cycles, 55-60-55-60-55 | two 60 Hz blocks against three 55 Hz blocks | **42%** | 58% | 50% |

These treat each 10-minute block as no steadier than one 30-second reading, which is right if the
scatter comes from slow wandering over minutes. If it came only from piece-to-piece noise, a
10-minute block (about 200 pieces against 10) would be about 4.5 times steadier and the two-cycle
figure would fall to about 9%; the 3-second pieces are not independent (METHODS §4), so the truth
lies between, nearer the upper figure the more the power wanders. The visit replaces this estimate
with its own: in two cycles the three 55 Hz blocks are the same setting repeated, and their
differences measure the wandering directly. This is one more reason to run the second cycle.

**What this means.** The rate swap can see a stimulator-locked part only if it is large: in the
two-cycle design, roughly two fifths of the band's power or more. For scale, the change in power
per milliamp on the two left-lead ladders at 55 Hz, averaged over the two, was +0.9%, -1.5%, -5.6%
and -6.2% of the band's power in 23.5, 24.5, 25.5 and 26.5 Hz; so a rate-locked part the size of
the whole current effect over the range tested would be far below what one visit could see. The
narrow-peak reading of §4 (25.0 Hz present at 55 Hz and absent at 60 Hz, in the PSD from the voltage
trace) is not diluted across a 5 Hz band and may see a much smaller locked part; no scatter estimate
exists for it yet.

**Stated in advance: a result of no change closes nothing.** If no band changes by more than the
detectable change, the write-up says "no change larger than X% of the band's power was detectable
across N blocks", and the next step is a longer repeat (20-minute blocks, or the order reversed,
60-55-60), never "these bands are not locked to the stimulator".

---

## 6. How the visit runs

Minute-by-minute rows in the lab's sheet format are in §9; this is the outline. Streaming runs on L
1-3+ and R 0-3+ from the first minute to the last.

| Minutes | Part | Setting | Ratings |
|---|---|---|---|
| 0-2 | Setup: start streaming, confirm settings, change nothing | L 3 / R 2.5 mA, 55 Hz | — |
| 2-12 | **A1**, 10 min | 55 Hz | 5 (every 2 min) |
| 12-13 | Change to 60 Hz, both sides; minute discarded | 60 Hz | — |
| 13-23 | **B1**, 10 min | 60 Hz | 5 |
| 23-24 | Change to 55 Hz; discarded | 55 Hz | — |
| 24-34 | **A2**, 10 min; end of cycle 1 | 55 Hz | 5 |
| 34-56 | Cycle 2 if the patient is comfortable: change, **B2**, change, **A3** | 60, then 55 Hz | 10 |
| 56-82 | **Down-first ladder**, left stepped, right held at 2.5 mA, 55 Hz: 13 steps of two 1-minute rows | L 3.0 → 0 → 3.0 in 0.5 mA steps | 13 (one per step) |
| 82-86 | Off-stimulation baseline (2 min), impedance test (1 min), restore settings (1 min) | 0 mA, then as in force | — |

**Length.** 86 minutes with both cycles, 64 without the second. The lab's usual off-stimulation
baseline and impedance test come at the end only, not also at the start: two minutes off just
before A1 would disturb the setting the patient has held for days, and the A1-B-A2 design can
bracket slow drift but not a recovery from an off period.

**Discard windows.** The minute of each rate change is discarded (critique 09 asked for 30-60 s;
this takes the upper end, and the sheets' own note says current takes 30-45 s to arrive). If the
tablet shows the current ramping after a rate change, the discard runs until the time the sheet
records it back at its setting (item 0.3(b)). As a check stated in advance, every result is also
read with the first 2 minutes of each block dropped. In the ladder, each step's first row is the
ramp row and is not analysed; the reading is the second row (the lab's two-row step, decision 160;
the analysis uses a 30-second settled window from it).

**Open-label.** The patient is not told which rate is running, but a patient with years of
stimulation may feel 60 Hz, so the design is open-label and no reading assumes the patient did not
know. At minute 3 of every block the patient is asked whether they noticed any change, and the
answer is written down; the ratings can then be read apart by whether a change was noticed.

**Stop rules, agreed before the visit.** 60 Hz is a first exposure for this patient. A side-effect
score of 2 or more (0-4, decision 165; the first-exposure stop rule of decision 230) at 60 Hz means
return to 55 Hz and end the rate swap there. Any pain or distress the patient or clinician judges
too much, or the patient's own request, ends the visit and restores the settings in force at once.
The ladder passes through 0 mA on the left for one 2-minute step, as every ladder does; if that is
not tolerated the ladder turns back up from the current reached.

**Staff time (critique 09).** One person at the tablet for all 86 minutes, reprogramming on the
minute and writing the time of every row and every streaming restart; with ratings every 2 minutes
in the swap and one per ladder step, **a second person for the ratings and the minute-3 question**
is recommended. With about 20 minutes of setup (settings check, stop-rule review, streaming start)
and 15 minutes after (export the session files, upload the sheet), about 2 hours of clinic time:
about 2 person-hours with one person, about 3.5 with two.

---

## 7. The ladder that steps down first

**Design.** Left current from the current in force, 3.0 mA, down to 0 mA in 0.5 mA steps, then back
up to 3.0 mA in 0.5 mA steps (3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0 mA): 13
steps, each a 1-minute ramp row and a 1-minute test row with a rating, 26 minutes. The right side
is held at 2.5 mA and the rate at 55 Hz, the rate in force (your ruling 3 of decision 233; if your
answer to the revised plan's question 9 is 60 Hz, the Rate column of the 26 ladder rows changes and a
10-minute settling hold at 60 Hz goes before the ladder).

**Why 0.5 mA on the way down, departing from the 1.0 mA down legs of 2026-09-14.** Your ruling kept
the down leg coarse because its job in the ordinary ladder is to check a few currents a second
time. Here the comparison of the two legs at the same current is the whole point, so both legs use
0.5 mA: five currents (0.5 to 2.5 mA) are rated on both legs, plus 3.0 mA at the start (held since
before the visit) and at the end (reached by a rise). With the 1.0 mA down leg only 1.0 and 2.0 mA
would be rated on both legs. This is your call; the alternative costs the same time.

**Why it starts from the current in force and not from the top.** Its first move must be a fall
from a setting the patient has held for days, the mirror of the 2026-09-16 ladder's first rise.
Starting from the top would need a rise to get there first.

**What it can tell.**

- **Pain.** The same comparison as decision 272 and the carry-over check on the Stim Optimizer page:
  at each current rated on both legs, down minus up. If the down leg reads lower whichever leg came
  first, that is what carry-over predicts; if the sign follows the order (lower when the fall came
  later, higher when it came first), that is pain drifting over the visit. Described with its
  numbers; five pairs is not a test.
- **Band power.** The 22% offset of §5 (the fall reading higher) came from falls that all followed
  their rises. If it is drift over the visit, it should reverse sign in this ladder; if it belongs to
  whether the current was rising or falling, it should keep its sign. Using the scatter of §5 (0.23 per
  pair), five pairs here against the three of 2026-09-16 give a standard error of 0.17 on the
  difference between the two sessions, so a reversal of the size seen (from +0.22 to -0.22, a
  difference of 0.44) would be detected about 74% of the time at a two-sided 5% level. That rests on
  three occasions' worth of scatter and should be read as rough.
- **At 55 Hz every band from 22.5 to 29.5 Hz carries a folded multiple of the rate** (decision 277),
  including the whole pain-linked family on the left, so the ladder's band readings in that family
  need the rate swap's answer beside them.

**What it does not do.** It holds the right side at 2.5 mA, so it does not add the current pairs
decision 258 named as missing for your ruling 5 (the pairs need the right side at 3 to 3.5 mA). The
ratings will enter the clinic-sheet stream as usual: 17 at L 3 / R 2.5 mA and 55 Hz, one or two at
each other ladder current, and 10 at 60 Hz, a rate with no other clinic ratings.

---

## 8. The analysis, stated before the visit

1. **Band power** per 3-second piece from the voltage trace on L 1-3+ and R 0-3+, all 22 centres,
   by the platform's own transform (the route that builds the stored pieces), raw power. Each block's
   mean over its kept minutes. For each band: the 60 Hz blocks' mean against the 55 Hz blocks' mean,
   as a fraction of the 55 Hz mean, with an interval from resampling runs of neighbouring pieces
   within blocks, and the spread among the 55 Hz blocks beside it. A point value and an interval,
   never a pass or fail (report 02).
2. **Read by set, named in advance:** "moves out" 23.5-26.5 Hz (the main reading; corrected for the
   four bands); "moves in" 8.5-10.5 and 16.5-21.5 Hz; no contrast 11.5-15.5, 22.5, 27.5-28.5 Hz;
   29.5 Hz observation only. R 0-3+ read the same way as a comparison (its contacts differ, so its
   bands are never pooled with the left, and neither side is read from a figure that mixes both
   sides' currents; METHODS §7).
3. **The PSD computed from the voltage trace at fine resolution** (a fraction of a hertz over a
   10-minute block, against the 5 Hz bands): narrow peaks at 25.0 Hz and 27.5 Hz under 55 Hz; at 10.0,
   20.0 and 30.0 Hz under 60 Hz. Descriptive.
4. **The device's own power reading** at 23.44 Hz, 55 Hz blocks against 60 Hz blocks, the same way.
5. **Pain in the swap:** the mean of each block's ratings with its count, by rate and by whether the
   patient noticed a change. Descriptive; the swap is not sized for pain.
6. **The ladder:** as §7, reported beside the 2026-09-16 ladder's numbers.
7. Every result is a lead to repeat (METHODS §7; decision 237). A result of no change is written as
   the change that could have been detected and was not (§5).

---

## 9. Clinic-sheet rows

The lab's "Stim Testing" tab, columns A-S in the template's own order (`titration_plan.SHEET_COLUMNS`,
header row 11, data from row 12), one row a minute, 86 rows. Contacts, current and pulse width are
written in the sheet's own left-then-right form (`L C+2- / R C+1-2-`, `L 3 / R 2.5`,
`L 100 / R 150`, decision 181; trap 4 of `clinic_steps.py`). Settings are written on the rows where
they change; the lab's reader carries them forward to the rows below, as it does for the two-row
steps today. **Left blank for the day:** Group, sEEG Contacts, Threshold, Side Effect? (write any
side effect and its 0-4 score), Timestamp (write the time as each row begins), Movement/Change
point, and the seven pain columns (on rows whose note says "Pain rating now", fill Overall, Back and
Left Leg on the 0-10 scale).

**Checked against the lab's own reader.** Filled with a constructed placeholder score on every
rating row and read back through the clinic-sheet parser (`clinic_pain._parse_generic_stim_testing`)
on 2026-09-25: 38 rating rows read, 0 flagged as unparsed prose, 0 dropped; the settings read back
as 17 ratings at 55 Hz L 3 / R 2.5 mA, 10 at 60 Hz L 3 / R 2.5 mA, 2 at each ladder current from
0.5 to 2.5 mA and 1 at 0 mA, every one at L 100 / R 150 µs. No note contains a pattern the reader
mistakes for a written score.

```csv
Group,Contacts,sEEG Contacts,Amp (mA),Rate (Hz),PW (µs),Threshold,Duration (s),Side Effect?,Timestamp,Movement/Change point,General Notes / Pt Verbal Notes,Overall,Head,Back,Left Leg,Left Foot,Right Leg,Right Foot
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,Start BrainSense streaming on L 1-3+ and R 0-3+ and keep it running to the end. Confirm the settings in force on the tablet; change nothing. Not analysed.,,,,,,,
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
,L C+2- / R C+1-2-,,L 3 / R 2.5,60,L 100 / R 150,,60,,,,"Change the rate to 60 Hz on BOTH sides; current and pulse widths unchanged. Minute discarded from analysis. If the tablet shows the current ramping, write the time it is back at the set current.",,,,,,,
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
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Change the rate to 55 Hz on BOTH sides; current and pulse widths unchanged. Minute discarded from analysis. If the tablet shows the current ramping, write the time it is back at the set current.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 1 of 10.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 2 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 3 of 10. Ask whether the patient noticed any change; write the answer.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 4 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 5 of 10.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 6 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 7 of 10.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 8 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 9 of 10.",,,,,,,
,,,,,,,60,,,,"Block A2, 55 Hz, minute 10 of 10. Pain rating now: Overall, Back, Left Leg. END OF CYCLE 1. Continue to cycle 2 only if the patient is comfortable; otherwise go to the ladder.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,60,L 100 / R 150,,60,,,,"Change the rate to 60 Hz on BOTH sides; current and pulse widths unchanged. Minute discarded from analysis. If the tablet shows the current ramping, write the time it is back at the set current.",,,,,,,
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
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Change the rate to 55 Hz on BOTH sides; current and pulse widths unchanged. Minute discarded from analysis. If the tablet shows the current ramping, write the time it is back at the set current.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 1 of 10.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 2 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 3 of 10. Ask whether the patient noticed any change; write the answer.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 4 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 5 of 10.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 6 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 7 of 10.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 8 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 9 of 10.",,,,,,,
,,,,,,,60,,,,"Block A3, 55 Hz, minute 10 of 10. Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 1 of 13, left 3 mA, start (held since before the visit): NO CHANGE (ramp row kept so every step has two rows). Not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 1 of 13, test row, left 3 mA (start (held since before the visit)). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 2.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 2 of 13: set LEFT to 2.5 mA (down); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 2 of 13, test row, left 2.5 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 2 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 3 of 13: set LEFT to 2 mA (down); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 3 of 13, test row, left 2 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 1.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 4 of 13: set LEFT to 1.5 mA (down); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 4 of 13, test row, left 1.5 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 1 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 5 of 13: set LEFT to 1 mA (down); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 5 of 13, test row, left 1 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 0.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 6 of 13: set LEFT to 0.5 mA (down); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 6 of 13, test row, left 0.5 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 0 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 7 of 13: set LEFT to 0 mA (down); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 7 of 13, test row, left 0 mA (down). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 0.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 8 of 13: set LEFT to 0.5 mA (up); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 8 of 13, test row, left 0.5 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 1 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 9 of 13: set LEFT to 1 mA (up); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 9 of 13, test row, left 1 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 1.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 10 of 13: set LEFT to 1.5 mA (up); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 10 of 13, test row, left 1.5 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 2 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 11 of 13: set LEFT to 2 mA (up); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 11 of 13, test row, left 2 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 2.5 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 12 of 13: set LEFT to 2.5 mA (up); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 12 of 13, test row, left 2.5 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Ladder step 13 of 13: set LEFT to 3 mA (up); right held. Ramp row, not analysed.",,,,,,,
,,,,,,,60,,,,"Ladder step 13 of 13, test row, left 3 mA (up). Pain rating now: Overall, Back, Left Leg.",,,,,,,
,L C+2- / R C+1-2-,,L 0 / R 0,55,L 100 / R 150,,60,,,,Off-stimulation baseline: both sides to 0 mA (the lab's usual end-of-session baseline). No rating.,,,,,,,
,,,,,,,60,,,,"Off-stimulation baseline, minute 2. No rating.",,,,,,,
,,,,,,,60,,,,Impedance test at a fixed measurement current (decision 133).,,,,,,,
,L C+2- / R C+1-2-,,L 3 / R 2.5,55,L 100 / R 150,,60,,,,"Restore the settings in force (L 3 / R 2.5 mA, 55 Hz, L 100 / R 150 us). Stop streaming after this minute; export the session.",,,,,,,
```

---

## 10. What this visit cannot settle

- One visit day is one day. A shift in the rate swap is a lead to repeat at a later visit, in the
  reverse order (60-55-60); no shift is the detectable change of §5 and a reason to repeat longer.
- The rate swap says whether power follows the rate. It says nothing about whether any band tracks
  pain; that question stays with the timed stimulation-off block (Lane C item 2, which needs 0.2) and
  with the current-removal work already built (decisions 234, 240-242).
- The down-first ladder gives five pairs on one day. It can show which way the order effect points;
  it cannot size carry-over.
- The weeks confound everything already on file (the revised plan, §4): current, rate and calendar
  moved together. This visit separates rate from calendar within one day; it does not touch the
  weeks.

## 11. Sources

- Revised plan and critiques: `artifacts/research_2026-09-25_options/{11_REVISED_PLAN,08_critique_science,09_critique_feasibility,02_next_clinic_visit_protocol}.md`.
- Decisions 133, 138, 145, 160, 165, 181, 202, 213, 217, 230, 233, 237, 258, 272, 277 (`DECISIONS_and_open_items.md`; decisions after 271 in the full log).
- Device facts: `DEVICE_percept_rc.md` §§3, 6, 9.
- Read-only scripts run for this draft on 2026-09-25, printing counts and aggregates only (gitignored
  scratch): `BRAVO/_agent_bridge/_rateswap_mdc.py` (the scatter of §5 and the change per milliamp),
  `BRAVO/_agent_bridge/_rateswap_settings.py` (the settings in force, the rates in the settings
  history, the one row of 3,344 with different rates on the two sides). The harmonic table of §4 and
  the reader check of §9 were run on the host from `StimOptimizer.titration_plan` and
  `StimOptimizer.clinic_pain` with no data.
