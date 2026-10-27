# Home recording protocol: separating the current and time of day from the pain signal

Draft, 2026-10-18 (item 8 of the signal-to-noise changes, `.planning/snr_2026-10-18.md`). **This is a
proposal for the clinical team; it changes nothing on the device or in BRAVO.** Any step that changes
stimulation, including the brief lower-current block, needs the treating clinician's judgement and
whatever approval the study protocol requires.

## Why

- On RCS08's left lead the stimulation current lowers pain and also moves band power, so a band can
  look like a pain signal when it only follows the current (decision 233; `stim_current.py`).
- Band power in the chronic log swings 2 to 6.7-fold between day and night (2026-10-18 measures,
  `_agent_bridge/_snr_03b_chronic_clean.out`), and ratings are given at habitual times.
- Only 17 Left / 27 Right pain ratings have BrainSense time-domain (TD) recording within 15 minutes.
  The TD recording is the only one that gives both the device's band power and the raw trace at
  once, with the current on the same clock.

A small number of planned home sessions, each with two current levels in random order and spread
over the day, gives comparisons within one session at one time of day: the current changes, the
hour does not, and the rating says whether pain changed.

## Each session (about 15 minutes, at an at-home visit)

1. Keep the stimulation rate and pulse width as programmed (the closed-loop rate and pulse width
   are fixed once BrainSense is set up, rule D30). Sensing pairs as programmed: Left 1-3, Right 0-3.
2. Pain rating on the tablet (NRS and VAS), with the clock time written in the visit sheet's Notes tab.
3. **Block A** – 5 minutes of BrainSense streaming at the current in force. Hold still; no tablet
   taps during the block (taps put movement into the recording around the rating).
4. Rating at the end of block A, written with its time.
5. **Block B** – change to the second current level (the order of A and B decided by coin toss per
   session and written down). Wait 60 s after the ramp ends before starting the block (ramps run
   up to 75 s; the device leaves a 7 s gap when stimulation is switched while streaming, rule D48).
   5 minutes of streaming.
6. Rating at the end of block B, with its time.
7. Optional, only where the clinician judges it safe: 2 minutes of Indefinite Streaming
   (stimulation off, all six contact pairs), to see the brain signal with no stimulation artefact.
8. Export the session's JSON as usual (it reaches BRAVO through the Dropbox sync).

## Spread over the day

Rotate sessions through three time blocks so each block holds roughly a third of them:
morning 07:00–10:00, afternoon 13:00–16:00, evening 19:00–22:00 (California time). Do not record
during recharging, impedance tests or MRI mode (closed loop is suspended then, rule D35).

## Current levels

The two levels are the clinic-chosen low and high currents of the device's two measurements for
closed loop (the band power read at a low current and at a high one), within the safe limits already
on the visit sheet. Change nothing else between blocks.

## What BRAVO does with it

- The sheets are read as now (`docs/clinic_sheets_parsing.yaml`); the time-stamped Notes ratings
  are matched to the block in force.
- Within each session, the difference in band power between blocks A and B, against the
  difference in rating, separates what the current does to power from what pain does.
- Comparisons stay within one time-of-day block, so the daily swing does not enter them.

## How many

Count the sessions needed from the first 10 sessions' own scatter: the gap between the two blocks'
band power, in units of its own scatter, sets how many sessions resolve a given pain effect.
No count is promised before that.
