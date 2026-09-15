# Percept BrainSense Adaptive: the closed-loop timing parameters — documented ranges, and what RCS08's own record says to set them to

**Written 2026-09-13**, answering the PI's brief of the same day: find the published or manual-stated
ranges for the device's closed-loop timing parameters (onset duration, transition up and down,
adaptive startup delay, and any other closed-loop parameter with a published range), cite every
source exactly, use no default without a stated range, and justify each chosen value from the
participant's own recorded dynamics.

Three reports feed this one and carry the full evidence:

- `research_2026-09-13_percept_adaptive_parameter_ranges_MANUALS.md` — the Medtronic documents on
  this machine (the March 2025 BrainSense Adaptive white paper; the tip cards; the LFP compendium).
- `research_2026-09-13_percept_adaptive_parameter_ranges_WEB.md` — the FDA approval summary, the
  ADAPT-PD papers, and the open toolkits' JSON field names.
- `research_2026-09-13_percept_adaptive_timing_RCS08_DATA.md` — RCS08's programmed state today and
  the measurements on her record (tables as CSV under `_agent_bridge/_probe_tl/_timing/`).

**Where this lives.** These are device settings entered on the clinician tablet. On the platform
they appear on the **Closed-Loop Deployment page**, in the "Full parameter recommendation" card and
the "CL-DBS simulations" card (which replays the controller with an onset and two transition
durations). Nothing on the platform writes to the device.

---


> **Addendum 2026-09-15 (decision 169).** The PI read the ranges off the clinician tablet's Adaptive
> Therapy setup screens. Against this synthesis: averaging 0-30 s and transitions 2 s-30 min agree
> with the tip card and the white paper's p. 16 slider; **the onset (both Dual timers) is 0.00 ms to
> 30.00 s on the tablet, not the FDA summary's 0-6 min** -- the white paper and the A610 manual print
> no onset range, so the tablet's 30 s is applied and the FDA figure is kept as a discrepancy;
> detection blanking has a range now, 0-30 s; sensing blanking reads 0-2.28 ms on the tablet against
> the tip card's 0-2500 us, and by the PI's rule the tip card stands. Consequences: the recommended
> onset of 30 s / 30 s is the tablet's maximum; the design rule's finding that "at 30 s averaging no
> onset under 120 s reaches one false crossing an hour" now reads "no enterable onset does", which
> strengthens 3 s averaging with a 30 s onset; the robustness intervals (36-90 s on L 1-3+, 27-60 s
> on L 0-2+) run past the enterable maximum and the card now says so.

## 1. Three corrections to what the platform has believed, before any recommendation

1. **The adaptive timings are programmable, not fixed.** `DEVICE_percept_rc.md` §2 has said since
   September that "the timing is fixed per mode and is not adjustable." The white paper's Table 1
   (p. 14) is titled "Threshold Mode **Default** Settings"; its p. 16 shows the Transition Durations
   screen with sliders from **2.00 s to 30.00 min**, and lists Onset Duration, Detection Blanking
   Duration and Adaptive Startup Delay under "Advanced Settings for Adaptive Therapy". The FDA's
   approval summary gives the selection ranges outright (§2). And RCS08's own device has run onset
   from 200 ms to 30 s, transitions from 250 ms to 300 s, averaging from 100 ms to 30 s, and startup
   delay at 0, 10 and 30 s across her 572 session reports. `DEVICE_percept_rc.md` §2 is corrected in
   place today with the original struck.
2. **The "A610" clinician programming guide the device rules cite is not on this machine.** The
   local "4NR010 Research Lab Programmer Guide M979053A001" is the Summit RC+S research guide
   (Model B35300R, 2018), not a Percept document. Every "A610 p. NN" citation in
   `ClosedLoopDeployment/constraints.py` is therefore unverified here. If the PI has the Percept RC
   clinician programmer guide, dropping it into the lab's Medtronic Manuals folder closes the gaps
   in §2 marked "not documented".
3. **The record has two facts the rules never read.** RCS08's right sensing channel is
   `GangedToHemisphere = Left`: one left-side signal drives both stimulators. And the programmed
   thresholds are 167 and 166 — one unit apart on a signal whose scatter is about a hundred units,
   so the Dual Threshold controller behaves as a single threshold (0.3 % of readings ever sit
   between them). Both bear on every recommendation below.

---

## 2. The documented ranges

Kinds: **(a)** a documented adjustable range; **(b)** a documented fixed value; **(c)** a documented
default; **(d)** a value a study chose; **(e)** not documented anywhere found. Only (a) is a range.

| Parameter (JSON field) | Documented range | Kind | Source, exactly | Defaults and other stated values |
|---|---|---|---|---|
| Onset duration, upper and lower timers, Dual Threshold (`UpperThresholdOnsetInMilliSeconds`, `LowerThresholdOnsetInMilliSeconds`) | **0 to 6 min** | a | FDA SSED P960009/S478 (20 Feb 2025), Table 2 "Key aDBS Configurable Parameters", p. 8 of 59: "Dual Threshold - 0 to 6 min" | default 1200 ms (WP Table 1, p. 14 — "Default Settings"); ADAPT-PD let clinicians set 1.2–2 s (Stanslaski 2024 npj PD 10:174, Methods); RCS08 has run 200 ms to 30 s |
| Onset duration, Single Threshold | **0 to 30 s** | a | FDA SSED Table 2: "Single Threshold - 0 to 30 seconds" | default 200 ms (WP p. 14); ADAPT-PD 200–500 ms |
| Transition up, transition down (`TransitionUpInMilliSeconds`, `TransitionDownInMilliSeconds`; FDA calls them "Stimulation Ramp Up/Down Duration") | **250 ms to 30 min, each** | a | FDA SSED Table 2: "250ms-30 minutes"; WP p. 16 screenshot slider "2.00 secs" to "30.00 mins" (Dual demo) | defaults 2.5 min up / 5 min down Dual, 250 ms Single (WP p. 14; Medtronic LFP compendium "Introduction to aDBS Modes"); ADAPT-PD allowed 1–10 min each (Stanslaski Table 3); RCS08 runs 4 s / 4 s today, has run 250 ms to 300 s |
| Current step inside a ramp | 0.01 mA (Percept RC), 0.1 mA (PC) | b | Cascino 2026, Methods | — |
| Adaptive startup delay (`AdaptiveStartupDelayInMilliSeconds`) | — | **e** | Defined only: WP p. 16, the delay before automatic adjustments begin, demo value 10.0 s; no document, paper or toolkit states a range | RCS08 has run 0, 10 s and 30 s; today 0 |
| Detection blanking (`DetectionBlankingDurationInMilliSeconds`) | — | **e** | Defined: WP p. 16 (a hold on re-classifying the signal after a threshold decision; an edit control is shown); Stanslaski 2024 Methods "default 550 ms following stimulation changes" | default 2000 ms Dual / 550 ms Single (WP p. 14); RCS08 has run 550 ms to 30 s, today 30 s |
| Averaging duration (`SensingSetup.AveragingDurationInMilliSeconds`) | **0 to 30 s** | a (2020 sensing-era tip card) | BrainSense Tip Cards (FIELDPORTAL1594651482409) p. 8 | defaults 1200 ms Dual adaptive / 3000 ms sensing-only, 100 ms Single (WP p. 14); RCS08 runs 30 s today |
| The two thresholds (`UpperLfpThreshold`, `LowerLfpThreshold`) | **0.55 to 400 µVrms each**; Single mode: lower = upper | a | FDA SSED Table 2 | resolution not stated (e); ADAPT-PD placed them at the 30 s mean power at each limit; RCS08 today 167 / 166 |
| Sensing band centre | **8 to 30 Hz** | a | FDA SSED Table 2 "Sensing Band 8-30 Hz"; WP p. 14 | max centre = min(100, 240 − rate) Hz; rate ≥ band + 10 Hz (Tip Cards p. 9) |
| Band width | 5 Hz, no control | b | WP p. 8, p. 10; Stanslaski; Thenaisie 2021 | — |
| Amplitude lower / upper limit under adaptive (`LowerLimitInMilliAmps`, `UpperLimitInMilliAmps`) | **0 to 25.5 mA each**, the clinician sets both | a | FDA SSED Table 2 "0-25.5 mA" | how they relate to the group's limits: not stated (e) |
| Paused ("suspend") amplitude (`SuspendAmplitudeInMilliAmps`) | clinician-defined, no range | b | WP p. 13, p. 15; ADAPT-PD CIP v5.0 p. 66 | RCS08 Left 2.5 mA, Right 2.0 mA |
| FFT size / update rate | 256 pt at 5 Hz Dual; 64 pt at 20 Hz Single; 250 Hz sampling; bin 0.98 Hz | b | WP p. 14; Tip Cards p. 9 | no control shown anywhere |
| Minimum signal | ≥ 1.2 µVp peak, "recommended for aDBS" | d | FDA SSED p. 17 | — |
| Stimulation rate with sensing | 50–185 Hz (3389 lead); 55–180 Hz SenSight; pulse width ≤ 300 µs | b / d | Tip Cards p. 9 (2020, sensing-era); FDA SSED p. 17 (trial rates 55–180 Hz) | the Stim Optimizer's 55 Hz floor is PI-stated (decision 138) and appears in no document |
| "Ramp rate" as mA/s | not a device parameter on Percept; the transition durations are the ramp | e | — | one research case used 0.05 / 0.025 mA/s (Brain Stimul 2026) |
| "CLIO" | not found in any Medtronic, FDA, paper or toolkit source | e | — | do not treat as a synonym for Summit RC+S |

**Sources that are about a different device.** Oehrn 2024, Gilron 2021 and the 2025 beta-burst gait
paper are Summit RC+S, whose onset and termination are counted in update-rate units; nothing in
them transfers to Percept. **No open toolkit validates a range** for any adaptive field; the
`neuromodulation/perceive` mock files carry the field names but randomise every digit.

---

## 3. What the record says, per parameter

The measurements are on the calibrated 3-second pieces of the voltage trace on each sensing
contact (the same series the CL-DBS simulation card replays), for the two bands the PI works
with — L 1⁻3⁺ at 24.5 Hz (his browser) and L 0⁻2⁺ at 24.5 Hz (decision 139) — never pooled
across contacts. 31.6 and 27.4 hours of streaming respectively.

**The signal's own time scale.** A 3-second reading is nearly an independent draw: its correlation
with the next reading is 0.19 (L 1⁻3⁺) and 0.08 (L 0⁻2⁺) once spikes are set aside; 55–62 % of a
reading's variance sits at periods shorter than 10 s; a 60-second average keeps 16 % (L 1⁻3⁺) and
9 % (L 0⁻2⁺) of the variance, against 5 % for pure noise. An excursion past a threshold lasts one
or two readings: median dwell 3–6 s, nine in ten over within 30 s.

**Onset duration.** Replaying the device's Dual Threshold controller over the recorded stretches
with the onset swept on the device's 3-second clock:

| Onset | L 1⁻3⁺ transitions / h | of which undone within one onset | L 0⁻2⁺ transitions / h | undone |
|---|---|---|---|---|
| 3 s | 447 | 5,111 in 31.6 h | 438 | 5,364 |
| 6 s | 89 | 503 | 109 | 708 |
| 9 s | 28 | 74 | 42 | 128 |
| **15 s** | **7.3** | **1** | 11.4 | 9 |
| **30 s** | 2.5 | 0 | **2.6** | **0** |
| 60 s | 1.5 | 0 | 1.1 | 0 |
| 120 s | 0.7 | 0 | 0.3 | 0 |

The knee — the shortest onset above which the switching rate stops falling steeply — is **15 s on
L 1⁻3⁺ and 30 s on L 0⁻2⁺**. Beyond it each doubling halves both the switching rate and the loop's
time at its limits, which is the loop doing less, not doing better. The device's documented 1.2 s
default cannot be expressed on the 3-second clock; its switching rate would be at least the 3 s
row, about 440 an hour with a third undone within one onset.

**Transition up and down.** Once the onset is 30 s the replay cannot tell 4 s from 60 s (time at
the limits within 1.2 percentage points; 4.3–5.0 mA travelled per hour either way); it can tell
2.5 min and longer, because the ramp then outlasts the typical dwell and the loop stops reaching
its limits. The settling time after a current step — the number that would anchor the choice —
cannot be measured on this record: a 0.5 mA step moves the band by 0.30–0.46 of the scatter and an
exponential fit explains 4–13 % of the variance (14 steps in 4 runs on L 1⁻3⁺, 8 in 1 on L 0⁻2⁺).
The pain ratings change over days (their correlation halves at 4–7 days), so no transition on the
grid is too slow for the outcome.

**Adaptive startup delay.** The first three readings after the device starts sensing read 0.24–0.41
of the scatter low (two to four standard errors, over 85 and 71 stretches); the bias is gone by the
fourth reading, at 12 s. Minutes after a programming change the band already sits at its later
level, and the device's own 10-minute series shows no settling over hours. Nothing argues for a
delay longer than 15 s; the record does argue against 0.

**Detection blanking.** No direct measurement is possible at 3-second resolution. The only bearing
datum is the same 12-second start-up dip.

---

## 4. Recommended settings for RCS08

Every value sits inside a documented range where one exists; where none exists the value is one
the device has demonstrably accepted on this participant, and that is said.

| Parameter | Recommend | Inside documented range? | Why, in one sentence | Confidence |
|---|---|---|---|---|
| Onset, upper and lower timers | **30 s each** (15 s acceptable on L 1⁻3⁺ alone) | yes: 0–6 min (FDA) | The 3-second readings are near-independent draws whose excursions last one or two readings, so 30 s is the shortest onset that switches the current ~2.5 times an hour with no switch undone within one onset, on both bands; 1.2 s would switch ~440 times an hour. | High — measured on 31.6 and 27.4 h of her own signal |
| Averaging duration | **30 s** (keep) | yes: 0–30 s (tip card) | More than half of a reading's variance is faster than 10 s and is noise to a loop that should follow the slow part; 30 s is the documented maximum and the device already runs it. | High |
| Transition up | **30 s** | yes: 250 ms–30 min (FDA) | Outcomes are indistinguishable from 4 s up to 60 s once the onset is 30 s, so within that band the choice is about ramp comfort, not control; 30 s smooths a 1 mA change over 100 steps of 0.01 mA and stays well below the 2.5 min at which the loop stops reaching its limits. Keeping today's 4 s is equally defensible on the data. | Medium — the settling time that would decide this needs the titration session (open item 30) |
| Transition down | **30 s** | yes | Same evidence as up; the data give no reason for down to differ from up on this record. The white paper's 2.5 / 5 min defaults are Parkinson's-beta defaults and would leave this loop mid-ramp most of the time. | Medium |
| Adaptive startup delay | **15 s if the tablet offers it, else 30 s** | no range documented; the device has accepted 0, 10 and 30 s on RCS08 | The first 12 s of sensing read 0.24–0.41 of the scatter low, so a delay shorter than that lets a startup artefact drive the first decision; today's 0 is the one value the record argues against. | Medium — 85 / 71 stretches; whether the dip is the device or the tissue is unknown |
| Detection blanking | **30 s** (keep, equal to the onset) | no range documented; the device has accepted 550 ms–30 s on RCS08 | With a 30 s onset, blanking shorter than the onset would let a decision be re-classified while the ramp it triggered is still under way; equal to the onset is the consistent choice and is what runs today. | Low — no direct measurement possible |
| The two thresholds | **separate them**: place lower and upper at least 0.4 of the scatter apart (about 40 units on L 1⁻3⁺), or run Single Threshold openly | yes: 0.55–400 µVrms | 167 / 166 is a single threshold in all but name (0.3 % of readings between); the platform's own stored pair for L 1⁻3⁺ at 24.5 Hz, 210.6 / 161.9, leaves 11 % of readings between and reaches its onset knee at 15 s rather than 30. | High on the fact; the placement rule is decision 139's |
| Ganged right channel | **decide it on purpose** | — | The right stimulator follows the left signal; every recommendation here is a left-signal recommendation, and no right-side sensing evidence exists that passed the screen (decision 146). | — |

**What the record cannot decide, and what would.** The settling time after a current step
(needs the titration session the Stim Optimizer page now lays out: 0.5 mA steps, ≥ 60 s holds,
up and down); anything shorter than 3 s; the averaging and the onset as separate stages (the
replay applies one); transitions between 4 s and 60 s; the first minute after a programming
change (one event per contact); the right side; whether the start-up dip is the device or the
tissue.

---

## 5. What should change on the platform

1. `DEVICE_percept_rc.md` §2 corrected (done today, original struck).
2. The CL-DBS simulation card's replay should take the onset, transitions and startup delay from
   the device's own programmed group (§1.3 shows the fields) rather than the white-paper defaults,
   and show the switching-rate-against-onset table above as a small panel — the derived headline
   convention. Not built today; a decision for the PI.
3. The device rules D20/D21 (timing) should read the FDA ranges as the documented envelope and the
   programmed values as the candidate's, instead of treating the white paper's defaults as fixed.
   Not built today.
4. The PI: the Percept RC clinician programmer guide (the cited "A610"), if he has it.

---

## 6. Addendum, later on 2026-09-13: the A610 clinician programming guide, read

The PI put the Percept RC clinician programmer manual in the lab Dropbox
(`ADMIN/Equipment/Percept RC/Percept RC Clinician Program MANUAL - M066414C_b_001_view_color.pdf`,
80 pages, footer "A610 English 2025-02-14"; beside it `M929534A_b_156_view.pdf`, the System
Eligibility and Battery Longevity reference, which has no adaptive parameter). This IS the A610 the
device rules cite. Read whole (text extracted; the adaptive pages 41-43 and the troubleshooting
pages 73-74 also viewed as images for slider screenshots -- there are none).

**What it settles.** Table 6 (p. 42, "Advanced settings for Adaptive Therapy") DEFINES the three
timing parameters -- Onset Duration ("the amount of time that the LFP signal must remain above the
upper threshold, or below the lower threshold, before the system classifies the LFP state ... and
initiates a consequent change in stimulation amplitude"; separate Upper and Lower Onset Durations
are named on p. 73), Detection Blanking Duration ("once the system classifies an LFP signal as
above or below a threshold, it will not attempt to re-classify the LFP signal until after the
Detection Blanking Duration"), and Adaptive Startup Delay ("the delay after switching to, or
activating, Adaptive Therapy before automatic adjustments to stimulation begin") -- and confirms
all of them, and both Transition Durations, are adjustable (p. 42: sliders and left/right arrow
marks "for incremental adjustments"; a Transition Up Test and Transition Down Test on p. 42-43).
So the correction in §1.1 stands on the manufacturer's own programming guide, not only on the
white paper and the FDA summary.

**What it does NOT give.** No minimum, maximum, step or default for any of the four timing
parameters, nor for the thresholds, the averaging window or the amplitude limits. The only
numeric bounds in the BrainSense sections are: the sensing band 8-30 Hz (p. 36-37); the
BrainSense streaming ramp interval "can be adjusted from 0.5 seconds to 10 seconds" (p. 45 --
the streaming amplitude-titration tool, not an adaptive parameter); and the artefact note on
p. 73, "if the stimulation level is above 5 mA (amplitude) or 120 us (pulse width), the artifact
of stimulation may cause the LFP to appear elevated when capturing the Lower LFP Threshold" --
which is the source of the capture ceilings the device rules D27 and the pipeline already apply.
**The FDA approval summary's Table 2 therefore remains the only document that states the selection
ranges**, and the rows marked "not documented" in §2 (startup delay, detection blanking, every step
size) stay that way.

**What it adds: the manufacturer's own tuning directions** (Table 16, p. 73-74), which read as
rules the platform could carry beside the ranges:

| Symptom the clinician sees | A610's direction |
|---|---|
| Adaptive therapy transiently delivers stimulation that is too LOW | lengthen Transition Down; shorten Transition Up (as tolerated); decrease the Upper Onset Duration and increase the Lower Onset Duration; if it persists, increase the minimum amplitude limit |
| transiently too HIGH | lengthen Transition Up; shorten Transition Down; increase the Upper Onset Duration and decrease the Lower Onset Duration; if it persists, decrease the maximum amplitude limit |
| chronically too low / stuck at the upper limit | increase the maximum limit; else decrease the upper LFP threshold, then the lower |
| chronically too high / stuck at the lower limit | decrease the minimum limit; else increase the lower LFP threshold, then the upper |
| in Single Threshold mode, repeatedly ramps to the upper limit immediately after adjusting to the lower limit | increase the Detection Blanking Duration until it stops |
| transiently at the upper limit immediately after Resuming or activating Adaptive Therapy | increase the Adaptive Startup Delay until it stops |

Two of those bear directly on §4: the blanking direction ("increase until the ramp-to-upper
immediately-after-lower stops") is the manufacturer's own reason for blanking to be at least the
onset, and the startup-delay direction ("increase until the transient at the upper limit after
Resuming stops") is the manufacturer's own reading of the 12-second start-up dip §3 measured.
Neither changes a recommended value; both strengthen the rationale.

**On the rules' citations.** The device rules cite "A610 p. NN" throughout `constraints.py`
against an edition whose page numbers were never checked here; this edition is dated 2025-02-14.
Checking all 84 citations against it is a separate pass, not done today.
