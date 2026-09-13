# Percept adaptive (closed-loop) settings: what the Medtronic documents on this machine actually bound

**Written 2026-09-13. Read-only research; no code changed.** Every number below is quoted from a
document on this machine, with the document, page and sentence beside it. Where a document shows a
value only in a screenshot of the programming tablet, that is said, because a screenshot of a demo
patient is weaker evidence than a sentence.

**How each value is labelled**, per the PI's rule that a default or a recommendation is not a range:

| Label | Meaning |
|---|---|
| **(a) adjustable range** | the document states a minimum and a maximum the user can set |
| **(b) fixed value** | the document states the value and that it cannot be changed, or shows no way to change it |
| **(c) default** | the document calls it a default, or prints it in a table titled "Default Settings" |
| **(d) recommendation** | the document says "consider", "recommend", "should" |
| **(e) not documented** | no local document states it |

---

## 0. Which documents these are, and which is the "A610" the repository cites

The repository's rule ledger (`BRAVO/modules/ClosedLoopDeployment/constraints.py`) cites two
sources for the adaptive rules: **"WP"** (the white paper) and **"A610"** (the A610 Clinician
Programming Guide, model M066414C001 Rev B, named in `BRAVO/modules/StimOptimizer/TWO_STAGE_DESIGN.md`).

| File on this machine | What it is | Device | Useful here? |
|---|---|---|---|
| `Medtronic_PerceptAdaptive_WhitePaper_032025.pdf` | "DBS Sensing and Adaptive Therapy White Paper, Percept PC and RC", document code UC202012929dEN, FY25. **This is "WP".** Page numbers below are the printed page numbers in its footer. | Percept PC and RC | **Yes — the only local document that describes Adaptive Therapy.** |
| `4NR010 Research Lab Programmer Guide M979053A001.pdf` | "Research Lab Programmer 4NR010, For use with Model B35300R neurostimulation system with Brain Radio Technology", dated 2018-03-01, "Investigational Device". | **Model B35300R — the Summit RC+S research system, not Percept.** | **No. It is NOT the A610 guide.** Its adaptive settings belong to a different device and are listed separately in §4 so nobody mistakes them for Percept's. |
| `M979047A_RevA_Model_4NR009_Patient_Therapy_Manager_Programming_Guide.pdf` | "Controller 4NR009, DBS therapy user manual for neurostimulation system model B35300R", 2018-03-01. | Summit RC+S patient controller | No. Its adaptive section (pp. 83-85) says only how the patient switches the ADAPTIVE group on and off. No parameter, no range. |
| `Tip cards-Brainsense (20) FIELDPORTAL1594651482409.pdf` | "DBS BrainSense Tip Cards", UC202013723EN, "FY21", (c) 2020. Clinician-programmer tip cards for BrainSense on Percept PC, **written before Adaptive Therapy existed on Percept.** | Percept PC (sensing only) | **Yes, for the sensing settings the adaptive mode is built on** (averaging, sensing blanking, high-pass, band limits, stimulation-rate restrictions). Nothing on onset, transition, startup delay. |
| `Tip Cards clinicial programmer Percept FIELDPORTAL1594650608351.pdf` | "DBS Clinician Programmer Application Tip Cards" (Percept), 2020. | Percept PC | No adaptive content. Patient-limit and ramp material is about ordinary stimulation. |
| `DBS LFP Compendium.pdf` | "Scientific Compendium: Research on Brain Sensing", a literature summary. | Percept PC (mentioned once) | No. Contains no device parameter. |
| `M982098A_a_001_view.pdf` | "SenSight Extension Kit B34000 Implant manual", 2021. | extension hardware | No. |
| `Report_Json_Session_Report_20210716T095308.json` | A Percept PC session report, programmer version 3.0.1062, device firmware 07.05.00, 2021-07-16. | Percept PC | **Partly.** It carries the sensing and threshold fields the 2021 firmware had. **It carries no adaptive field at all** — no onset, transition, startup-delay, detection-blanking or adaptive-status field exists in it. |

**The A610 Clinician Programming Guide is not on this machine.** Every "A610 p. NN" citation in
the repository's ledger was therefore not checked here. The white paper's own Advanced Settings
screen says: "Refer to the Medtronic clinician programming guide for information regarding
advanced settings." (WP p. 16, screenshot) — so the guide, not the white paper, is where the
adjustable ranges would be printed.

**One more thing the PI should know.** RCS08's own newest session report (2026-09-11, described in
decision 136 as GROUP_D at 55 Hz with adaptive therapy RUNNING) is the only file on this machine
that would carry the **programmed values** of these adaptive fields for this participant. It was
not opened for this report, which was scoped to the Medtronic documents; the repository currently
reads only `AdaptiveTherapyStatus` from it (`session_report_facts.py`).

---

## 1. The parameters, one table each

### 1.1 Onset Duration

Definition (WP p. 16, prose): *"Onset Duration: The amount of time that the LFP signal must remain
above the upper threshold, or below the lower threshold (or threshold) before the system classifies
the LFP state as above or below the threshold and initiates the consequental change in stimulation
amplitude."*

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| 1200 ms (Dual Threshold, adaptive) | **(c) default** | WP p. 14, Table 1 | Table title: *"Table 1: Threshold Mode Default Settings"*; row: *"Onset Durations — 1200ms (Adaptive) (N/A - Sensing Only)"* |
| 200 ms (Single Threshold, adaptive) | **(c) default** | WP p. 14, Table 1 | *"Onset Durations — 200ms (Adaptive) (N/A - Sensing Only)"* |
| not applicable (Single Threshold Inverse) | **(b) fixed: no onset exists in this mode** | WP p. 14, Table 1 | *"N/A – Sensing Only"* |
| Upper 1.2 s / Lower 1.2 s (Dual, demo patient) | **screenshot value** — shows onset has **two values in Dual mode, one per threshold**; not labelled default or range | WP p. 16, Advanced Settings screenshot | *"ONSET DURATION — Upper: 1.2 Seconds, Lower: 1.2 Seconds"* |
| It is an adjustable setting | **(a)-adjacent: listed as an "Advanced Setting"; the range is not printed** | WP p. 16, prose | *"Advanced Settings for Adaptive Therapy include the following: Onset Duration ... Detection Blanking Duration ... Adaptive Startup Delay"* |
| **Minimum, maximum, step, upper-bound definition** | **(e) not documented** in any local document | — | — |

What the repository says: D21 states the only published range is the ADAPT-PD paper's (1.2 to 2 s
dual; 200 to 500 ms single). That paper is not on this machine and was **not** verified here.

### 1.2 Transition Up Duration and Transition Down Duration

Definition (WP p. 16, prose): *"When Adaptive Therapy is set to Adapting, Transition Durations
determine the speed with which stimulation amplitude automatically increases or decreases in
response to changes in the LFP signal."*

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| Up 2.5 min, Down 5 min (Dual Threshold) | **(c) default** | WP p. 14, Table 1 | *"Transition Up/Down Durations (Adaptive Only) — Up: 2.5 mins, Down: 5 mins"* |
| Up 250 ms, Down 250 ms (Single Threshold) | **(c) default** | WP p. 14, Table 1 | *"Up: 250ms, Down: 250ms"* |
| not applicable (Single Threshold Inverse) | **(b) fixed: none** | WP p. 14, Table 1 | *"N/A – Sensing Only"* |
| "on the order of minutes" (Dual) / "on the order of milliseconds" (Single) | **(c) default, in words** | WP p. 13; WP p. 14 | *"...this mode provides a slower stimulation amplitude reaction to LFP changes (e.g., due to medication cycles), **by default** on the order of minutes"* / *"...a faster stimulation amplitude reaction to LFP changes, **by default** on the order of milliseconds"* |
| They are adjustable, and should be tested on the patient | **(d) recommendation**, and confirms adjustability | WP p. 16, prose | *"Consider testing the Transition Durations to ensure that the patient can tolerate the speed of amplitude changes he or she will encounter while using Adaptive Therapy."* |
| **Slider from 2.00 secs to 30.00 mins, both up and down (Dual Threshold demo)** | **(a) adjustable range — but shown only as slider endpoints in a screenshot, not stated in prose** | WP p. 16, "TRANSITION DURATIONS" screenshot (demo patient, Dual Threshold, 60 us / 125 Hz) | On-screen: *"TRANSITION UP DURATION — 2.00 secs [left end] ... 2.30 mins [marker] ... 30.00 mins [right end]"*; *"TRANSITION DOWN DURATION — 2.00 secs ... 5.00 mins ... 30.00 mins"*; caption: *"Transition durations affect the speed with which stimulation adapts in response to changes in the LFP signal."* |
| Step / resolution | **(e) not documented** | — | the marker reads to 0.01 min ("2.30 mins"), which is display precision, not a stated step |
| Range in **Single Threshold** mode | **(e) not documented** | — | Single's default of 250 ms is **below** the 2.00-second bottom of the slider in the Dual screenshot, so that slider cannot be Single mode's range. Single mode's range is not shown anywhere locally. |
| The screen also offers a "TRANSITION UP TEST" / "TRANSITION DOWN TEST" control | feature, no value | WP p. 16 screenshot | *"TRANSITION UP TEST"*, *"TRANSITION DOWN TEST"* |

### 1.3 Adaptive Startup Delay

Definition (WP p. 16, prose): *"Adaptive Startup Delay: The delay after switching to, or
activating, Adaptive Therapy before automatic adjustments to stimulation begin."*

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| 10.0 seconds (Dual, demo patient) | **screenshot value only** — not labelled default, not in Table 1 | WP p. 16, Advanced Settings screenshot | *"ADAPTIVE STARTUP DELAY — 10.0 Seconds"* with an edit (pencil) control beside it |
| It is an adjustable Advanced Setting | adjustability stated; **range (e) not documented** | WP p. 16, prose | *"Advanced Settings for Adaptive Therapy include the following: ... Adaptive Startup Delay"* |
| Minimum, maximum, step | **(e) not documented** | — | — |

**The repository's per-mode table has no row for this parameter at all** (`DEVICE_percept_rc.md`
§2 and `THRESHOLD_MODE_TABLE` in `constraints.py`). It is also absent from the white paper's own
Table 1, so the repository's omission mirrors the table it transcribed; the parameter exists all
the same.

### 1.4 Detection Blanking Duration

Definition (WP p. 16, prose): *"Detection Blanking Duration: Once the system classifies an LFP
signal as above or below a threshold, it will not attempt to re-classify the LFP signal until after
the Detection Blanking Duration."*

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| 2000 ms (Dual) / 550 ms (Single) / N/A (Inverse) | **(c) default** | WP p. 14, Table 1 | *"Detection Blanking Duration — 2000ms (Adaptive) (N/A - Sensing Only) / 550ms (Adaptive) (N/A - Sensing Only) / N/A – Sensing Only"* |
| 2.0 Seconds (Dual, demo) | screenshot value, with an edit control | WP p. 16, Advanced Settings screenshot | *"DETECTION BLANKING DURATION — 2.0 Seconds"* |
| Adjustable | stated as an Advanced Setting; **range (e) not documented** | WP p. 16 | as above |

**This is not "blanking of sensing around a stimulation change".** By the white paper's own
definition it is a refractory period on the *classification* after a threshold decision. See
contradiction 5 in §2.

### 1.5 The two LFP thresholds (Upper and Lower), and the single threshold

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| Dual: set manually, upper and lower | **(b) method fixed**; values are the user's | WP p. 14, Table 1 | *"Threshold Setting Algorithm — Manual Setting of Upper and Lower"* |
| Single and Single Inverse: computed as 0.75 x (Upper − Lower) + Lower | **(b) fixed formula** | WP p. 14, Table 1; WP p. 15 | *"Calculated Single Threshold Based upon 0.75 × (Upper – Lower) + Lower"*; *"The generated single threshold value is based on 75% of the difference between the two captured values."* |
| Unit: "LFP Power", integer-looking, about 0.01 uV² per unit | **(b) unit definition**, approximate | WP p. 9 | *"1 unit of LFP Power is approximately 0.01uV2."*; *"It is calculated as the sum of the squared LFP magnitude at each frequency with the selected frequency band"* |
| Capture: Dual = capture at the lower then the upper therapeutic amplitude; Single = capture at the upper therapeutic amplitude, then the system captures again at 0.0 mA | **(b) fixed procedure** | WP p. 15 | *"Single Threshold: Increase the stimulation amplitude to the upper limit of therapeutic benefit and capture the LFP. The system will automatically capture a second LFP signal with stimulation amplitude set to 0.0mA"* |
| Two named failure modes: too close together, inverted; manual adjustment then defaults the slider to the average of the upper capture | **(b) fixed behaviour** | WP p. 15 | *"...it is possible that the thresholds gathered by the system are either too close together or are inverted. ... If the thresholds were inverted, the manual adjustment slider will default to the average LFP value of the upper LFP threshold capture"* |
| Thresholds may be adjusted on the Streaming screen only with streaming paused and adaptive paused | **(b) fixed behaviour** | WP p. 12 | *"LFP thresholds can be adjusted directly on this screen when streaming is paused. If Adaptive Therapy is configured, Adaptive Therapy must also be paused to adjust thresholds."* |
| On-screen example: Upper 552 (captured 206 at 2.9 mA), Lower 200 (captured 200 at 3.0 mA), up/down arrow controls | screenshot values | WP p. 15, LFP Thresholds screenshot | *"UPPER LFP THRESHOLD 552 ... CAPTURED AT 2.9 mA"*, *"LOWER LFP THRESHOLD 200 ... CAPTURED AT 3.0 mA"* |
| 2021 report fields: `UpperLfpThreshold: 30.0`, `LowerLfpThreshold: 20.0` (floats), `UpperCaptureAmplitudeInMilliAmps`, `LowerCaptureAmplitudeInMilliAmps`, `MeasuredUpperLfp`, `MeasuredLowerLfp` | field names in the device export | `Report_Json_Session_Report_20210716T095308.json`, `Groups.Final[].ProgramSettings.SensingChannel[]` | (values as listed) |
| **Allowed minimum, maximum, step of a threshold; the minimum separation that counts as "too close"** | **(e) not documented** | — | — |

### 1.6 Averaging Duration (the smoothing window)

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| Dual: 1200 ms adaptive / 3000 ms sensing-only; Single: 100 ms / 1000 ms; Inverse: 3000 ms | **(c) default** | WP p. 14, Table 1 | *"Averaging Duration — 1200ms (Adaptive) 3000ms (Sensing Only) / 100ms (Adaptive) 1000ms (Sensing Only) / 3000ms"* |
| **0 to 30 s** | **(a) adjustable range** — printed in a 2020 sensing-only tip card, i.e. before adaptive existed on Percept; whether the adaptive-mode averaging has the same range is not stated | BrainSense Tip Cards p. 8, table "Advanced Settings for BrainSense" | *"Averaging Duration — 0-30s — Average Duration reduces noise by averaging the signal over a duration and assigning it a single value. A longer duration may reduce noise to a greater extent than a shorter duration. A shorter duration may result in a faster LFP response when streaming BRAINSENSE data"* |
| It is a unique (non-overlapping) average, set in Advanced Settings | **(b) fixed behaviour** | WP p. 12 | *"...a unique solution is only calculated at the power averaging duration. Moreover, the power averaging duration is not a moving average it is a unique average, i.e. each average contains a unique set of data, not overlapping. This parameter is available in the Advanced Settings of the BrainSense Setup workflow."* |
| 1.2 Seconds (Dual, demo) | screenshot value | WP p. 16, Advanced Settings screenshot | *"AVERAGING DURATION — 1.2 Seconds"* |
| 3000 ms in the 2021 report | field value | JSON `SensingSetup.AveragingDurationInMilliSeconds: 3000` | — |
| Step | **(e) not documented** | — | — |

### 1.7 FFT size and FFT update rate

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| 256 points (Dual, Inverse); 64 points (Single) | printed in the "Default Settings" table; **no document shows any control for it**, so treated as **(b) fixed per mode** with that caveat | WP p. 14, Table 1 | *"FFT Size — 256 points / 64 points / 256 points"* |
| Update 5 Hz adaptive, 2 Hz sensing (Dual); 20 Hz adaptive, 2 Hz sensing (Single); 2 Hz (Inverse) | same caveat | WP p. 14, Table 1 | *"FFT Update Rate — 5Hz (Adaptive) 2Hz (Sensing Only) / 20Hz (Adaptive) 2Hz (Sensing Only) / 2Hz"* |
| Frequency bin 0.98 Hz; sampling 250 Hz | **(b) fixed** | BrainSense Tip Cards p. 9 and p. 13; WP p. 10, p. 19 | *"Sample Rate: 250 Hz"*, *"FFT Resolution: 0.98Hz"*; *"All recorded data is sampled at 250Hz."* |
| LFP power and stimulation amplitude recorded at 2 Hz when streaming | **(b) fixed** | BrainSense Tip Cards p. 15 | *"The LFP Power and Stim Amplitude is recorded at 2Hz for each hemisphere"* |

### 1.8 Band centre range and band width

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| 8 to 30 Hz (adaptive); 1 to 96 Hz (sensing only) | **(a) adjustable range** | WP p. 14, Table 1 | *"LFP Frequency Range — 8-30Hz (Adaptive) 1-96Hz (Sensing Only)"* |
| Band width about 5 Hz | **(b) fixed, approximate** — no control is shown | WP p. 8; WP p. 10 | *"select a frequency band of interest (approximately 5Hz wide)"*; *"The clinician specified band is approximately 5Hz wide."* |
| Frequency-domain content runs 0 to 96.68 Hz | **(b) fixed** | WP p. 11 | *"The frequency ranges from 0 to 96.68Hz."* |
| Stimulation rate must be at least 10 Hz above the band; band may not exceed the smaller of 100 Hz and (240 − rate) Hz | **(a) constraint on the centre**, 2020 sensing tip card | BrainSense Tip Cards p. 9 | *"Stimulation rates must be at least 10Hz greater than the selected LFP Band of interest"*; *"Maximum LFP selection is the smaller of 100Hz or (240-StimFreq)Hz"* |
| Centre values seen in the export sit on the 0.98 Hz bin grid (9.77 Hz, 7.81 Hz) | observation, not a stated rule | JSON `SensingSetup.FrequencyInHertz` | — |
| Automatic peak selection floor 1.1 uVp; recommendation gate 1.2 uVp at > 8 Hz | **(b) fixed behaviour** — and the two numbers are two different things | WP p. 8; BrainSense Tip Cards p. 9 | *"Automatically selects the largest peak on a particular channel, if that peak is in the alpha-beta or gamma frequency range and exceeds a value of 1.1 µVp"*; tip card: *"Signal Check selects peak of sufficient magnitude in the Beta or Gamma frequency band, automatically (>1.1µVp)"* and *"The clinician application will recommend an LFP signal only if: ... A peak is detectable in the LFP measured (an amplitude ≥ 1.2µVp) at a frequency >8Hz (start of beta)"* |
| Step of the centre | **(e) not documented** | — | — |

### 1.9 Adaptive amplitude limits (lower and upper), and the Paused Amplitude

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| Definition: the maximum and minimum amplitude allowed while adapting | **(b) definition** | WP p. 15 | *"The Adaptive Amplitude Limits represent the maximum and minimum stimulation amplitudes allowed during adaptive stimulation. The system will automatically adjust stimulation between these limits in response to LFP power as defined by the selected Threshold Mode."* |
| Relation to patient limits: they become the patient limits when the group goes back to Sensing Only | **(b) fixed behaviour** | WP p. 15 | *"When BrainSense status is changed from Adaptive to Sensing Only for all adaptive programs in a group, the values selected for the Adaptive Amplitude Limits will become patient limits."* |
| Set with flags on the amplitude slider; in an adaptive group the patient cannot adjust amplitude even when paused | **(b) fixed behaviour** | WP p. 15, Limits screenshot | *"Use flags to set a range for Adaptive Amplitude Limits when 'Adapting' (or patient limits when Sensing Only). In an Adaptive Group, even when 'Paused', a patient cannot adjust amplitude."* |
| Demo: max 3.2 mA, min 2.4 mA, equal to the two capture amplitudes 3.2 / 2.4 mA; slider scale 0.0 to 6.0 mA with 0.1 steps | screenshot values; consistent with "defaults to the capture amplitudes" but the white paper's prose does not say "default" | WP p. 15, Limits screenshot | *"AMPLITUDE LIMITS — MAXIMUM AMPLITUDE 3.2 mA, MINIMUM AMPLITUDE 2.4 mA"*; *"AMPLITUDES USED TO CAPTURE LFP THRESHOLDS — 3.2 mA, 2.4 mA"* |
| Paused Amplitude: what the patient receives while adaptive is paused | **(b) definition** | WP p. 13; WP p. 15 | *"The Paused Amplitude is the stimulation amplitude the patient will receive when Adaptive Therapy is paused. The patient will receive this therapy until Adaptive Therapy is resumed."* |
| Adaptive is auto-paused during recharge (RC) and during an impedance test | **(b) fixed behaviour** | WP p. 13 | *"Adaptive Therapy is automatically Paused during a recharging session (Percept RC only). ... Adaptive therapy is temporarily disabled during an Impedance test, and re-enabled when the test completes."* |
| 2021 report field `SuspendAmplitudeInMilliAmps: 0.0` | field name (the export's name for the Paused Amplitude) | JSON | — |
| **Allowed range and step of the two limits; whether they may exceed the group's patient limits; minimum gap between them** | **(e) not documented** | — | The Summit guide's "0-25.5 mA, 0.1 mA resolution" (§4) is a different device. The repository's D31 quotes a Percept envelope from "A610-MD p. 119", which is not on this machine. |

### 1.10 Ramp rate

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| **Percept adaptive mode has no separately named "ramp rate".** The Transition Up/Down Durations are the ramp (§1.2). | **(e) as a named parameter** | WP p. 13, p. 14, p. 16 | *"When the LFP passes above the upper threshold, the stimulation amplitude slowly ramps up. When the LFP passes below the lower threshold, the stimulation amplitude slowly ramps down."* (p. 13) |
| "Tablet Ramp Interval" is a tablet-side ramp used when the clinician changes amplitude by hand; it can be set to OFF | **(b) feature exists**; range (e) not documented | WP p. 20 | *"Set the Tablet Ramp Interval to OFF. Start streaming with the Percept device with stimulation on at 0.0mA"* |
| SoftStart/Stop is a group setting (2021 report: enabled, 4 s) | field value; range (e) | WP p. 34 (*"GroupSettings – contains ... SoftStart, Cycling, highpassfilter, sense blanking duration"*); JSON `GroupSettings.SoftStartStop: {Enabled: true, DurationInSeconds: 4}` | — |

### 1.11 Sensing Blanking Duration (the per-pulse blanking, distinct from Detection Blanking)

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| **0 to 2500 "ms"** | **(a) adjustable range — but the unit printed is almost certainly wrong**: the device export names the field in **microseconds** (`SensingBlankingDurationInMicroseconds: 1910`), the white paper's screenshot reads "2.0 Milliseconds", and the Summit guide's equivalent tops out at 2.5 ms. Read it as 0 to 2500 microseconds. | BrainSense Tip Cards p. 8 | *"Sensing Blanking Duration — 0-2500ms — Sensing Blanking duration reduces noise introduced by stimulation. A longer duration reduces the noise to a greater extent than a shorter duration"* |
| 2.0 Milliseconds (demo) | screenshot value | WP p. 16, Advanced Settings screenshot | *"SENSING BLANKING DURATION — 2.0 Milliseconds"* |
| 1910 us in the 2021 report | field value | JSON `GroupSettings.SensingBlankingDurationInMicroseconds: 1910` | — |

### 1.12 High-pass filter

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| 1 Hz or 10 Hz (user choice), on top of a fixed 1 Hz high-pass and two 100 Hz low-passes | **(a) two-choice setting**; the rest **(b) fixed** | WP p. 19; BrainSense Tip Cards p. 8 | *"This includes 2 low pass filters at 100Hz, and two high pass filters. One high pass filter at 1Hz, and a second high pass filter at a user configurable 1Hz or 10Hz."*; tip card: *"High Pass Filter — 1Hz or 10Hz cutoff Frequency"* |
| 1 Hz in the 2021 report | field value | JSON `GroupSettings.HighPassFilterInHertz: 1` | — |

### 1.13 Stimulation rate and pulse width while sensing / adapting

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| **Rate 50 to 185 Hz; pulse width at most 300 us; no interleaving; patient control limited to amplitude** | **(a) adjustable range — printed only in the 2020 sensing tip card**, for "when Sensing", on Percept PC, before adaptive existed | BrainSense Tip Cards p. 9, "Programming Restrictions when Sensing" | *"Rate: 50 Hz – 185Hz"*; *"Amplitude: No Restrictions, but high amplitudes (>5mA) may start to increase sensing noise floor."*; *"Pulsewidth: ≤ 300μs"*; *"No interleaving"*; *"Patient Control is limited to stimulation amplitude (not PW or Rate)"* |
| Amplitude above 5 mA raises the sensing noise floor | **(d) caution**, not a limit | BrainSense Tip Cards p. 9 | as above |
| **The 55 Hz "adaptive minimum" the repository uses** | **(e) not in any local document**; `adaptive_envelope.py` labels it "PI-stated" | — | — |

### 1.14 Other timing facts in the adaptive sections

| Value | Kind | Document, page | Quoted sentence |
|---|---|---|---|
| Signal test about 90 s | **(b) fixed, approximate** | WP p. 8; Tip Cards p. 9 | *"Used: In-clinic, with approximately 90 seconds measurement for setup."* |
| Chronic record: 10-minute averages, not configurable | **(b) fixed** | WP p. 10; Tip Cards p. 6 | *"The LFP power and the stimulation amplitudes are the average value measured over a 10 minute interval"*; *"The bars on the graph time resolution is 10 min (not configurable)."* |
| Turning stimulation on or off while streaming loses 7 s | **(b) fixed** | WP p. 20 | *"turning stimulation on or off while streaming will cause a 7-second 'initializing' period in which data will not be available in the JSON export"* |
| Snapshot: about 30 s of signal after the event | **(b) fixed, approximate** | WP p. 11 | *"the neurostimulator measures approximately 30 seconds of LFP time domain data"* |
| Which adaptive settings the export carries | field list | WP p. 34, Table 4, `ProgramSettings` | *"Thresholds (captured and manually adjusted), Sensing Frequency, Averaging Duration, ... Adaptive Therapy Status, Adaptive Therapy Mode, Adaptive Transition Durations, Onset Durations, Detection Blanking Duration, Adaptive Startup Delay, Stimulation Limits, Suspend(Paused) Amplitude, and Sensing Hemisphere."* |

---

## 2. Contradictions with the repository's current table

1. **`DEVICE_percept_rc.md` §2 says "The timing is fixed per mode and is not adjustable." The white paper does not support that.** Its Table 1 is titled *"Threshold Mode Default Settings"* (WP p. 14); the mode descriptions say *"by default on the order of minutes"* and *"by default on the order of milliseconds"* (WP p. 13, p. 14); page 16 says *"Consider testing the Transition Durations"* and shows sliders from *"2.00 secs"* to *"30.00 mins"* for both transition directions; and it lists *"Onset Duration ... Detection Blanking Duration ... Adaptive Startup Delay"* under *"Advanced Settings for Adaptive Therapy"* with edit controls in the screenshot. So the transition durations, the detection blanking duration and the adaptive startup delay are adjustable, and the onset duration is presented as a setting. `constraints.py`'s D20 already says *"the device supplies these defaults itself and the adjustable ranges are not printed"* — that wording is right and `DEVICE_percept_rc.md`'s is not. The FFT size and update rate are the only rows for which no document shows a control.

2. **The repository records no range for the transition durations; the white paper shows one** (2.00 s to 30.00 min, Dual mode, screenshot on p. 16). D20 and D21 do not mention it. It is a screenshot of a demo patient, not a sentence, and it is Dual mode only — Single mode's 250 ms default sits below the 2.00 s bottom of that slider, so Single mode's range remains unknown.

3. **Adaptive Startup Delay is missing from the repository entirely.** Neither `DEVICE_percept_rc.md` §2 nor `THRESHOLD_MODE_TABLE` has a row for it. The white paper defines it (p. 16) and lists it among the export's `ProgramSettings` (p. 34). The white paper's own Table 1 also omits it, which is presumably how it was dropped.

4. **D31 says the narrower BrainSense envelope's values "are unpublished" and that a search of the programming guide and the white paper "returned no such figure".** That is true of those two documents, but the 2020 BrainSense tip card (p. 9) prints three of them: *"Rate: 50 Hz – 185Hz"*, *"Pulsewidth: ≤ 300μs"*, and the band rule *"Stimulation rates must be at least 10Hz greater than the selected LFP Band"*. Caveats that matter: the card is dated 2020 (FY21), describes Percept PC "when Sensing" before Adaptive Therapy existed on Percept, and may not equal the adaptive-group envelope on today's A610 5.0. It also gives **50 Hz**, not the 55 Hz "adaptive minimum" the Stim Optimizer uses (`adaptive_envelope.py` marks 55 Hz as "PI-stated"; no local document states 55).

5. **`DEVICE_percept_rc.md` §2 reads the 2000 ms Detection Blanking as sensing blanked "around a stimulation change".** Its sentence: *"Under Dual Threshold the device blanks its own sensing for 2000 ms around a stimulation change."* The white paper's definition is different: *"Once the system classifies an LFP signal as above or below a threshold, it will not attempt to re-classify the LFP signal until after the Detection Blanking Duration"* (WP p. 16). That is a hold on the next threshold decision after a decision has been made, and it is tied to the classification, not to the amplitude change. The per-pulse blanking of sensing is a separate setting, the Sensing Blanking Duration, of about 2 ms (§1.11). The consequence the repository draws — do not trust signal right after a current change — may still be sensible on other grounds, but it is not what this parameter does.

6. **D09's "discrepancy" between 1.1 uVp and 1.2 uVp is two different rules, not a disagreement.** The tip card prints both on one page (p. 9): the *automatic peak selection* fires above 1.1 uVp, and the *recommendation* of a channel needs at least 1.2 uVp at a frequency above 8 Hz. The white paper (p. 8) states only the 1.1 uVp selection rule. The repository's choice of 1.2 as the gate stands; the note that "neither document explains it" can be retired.

7. **The tip card's "0-2500ms" sensing-blanking range is in the wrong unit.** The export's field is `SensingBlankingDurationInMicroseconds` (2021 report value 1910), the white paper's screenshot reads *"2.0 Milliseconds"*, and the Summit guide's corresponding maximum is 2.5 ms. The range is 0 to 2500 microseconds. Anything in the repository that copies "2500 ms" from the card would be wrong by a thousand.

8. **The document the repository cites as "A610" is not on this machine, and the "Research Lab Programmer Guide" that is on this machine is not it.** The local guide is for Model B35300R (Summit RC+S, 2018, investigational). Every "A610 p. NN" citation in `constraints.py` remains unverified here.

---

## 3. Not found in any local document

For each parameter the PI asked about, what no local document bounds:

| Parameter | What is missing |
|---|---|
| Onset duration | minimum, maximum, step; any definition of an upper bound. Only the defaults (1200 ms / 200 ms) and the fact that it is an Advanced Setting with two values (upper, lower) in Dual mode. |
| Transition up / down duration | a **stated** range in prose (the 2.00 s to 30.00 min range is read off a slider in a screenshot, Dual mode only); the step; the Single-mode range. |
| Adaptive startup delay | minimum, maximum, step, default. Only a definition and one demo-screen value (10.0 s). |
| Detection blanking duration | minimum, maximum, step. Only defaults (2000 / 550 ms). |
| Thresholds | allowed minimum and maximum in LFP Power units, the step, and the minimum separation below which the device reports "too close together". |
| Averaging duration | the step; whether the adaptive-mode averaging (default 1200 / 100 ms) shares the 0 to 30 s range printed for sensing in 2020. |
| Band centre | the step (values in the export fall on the 0.98 Hz bin grid, which is an observation); whether the width can be changed at all. |
| Adaptive amplitude limits | allowed minimum, maximum, step; whether they must lie inside the group's patient limits; minimum gap between them; whether they default to the capture amplitudes (the screenshot is consistent with that; the prose does not say it). |
| Ramp rate | no such named parameter exists for Percept adaptive mode in any local document. |
| Single threshold mode "offset" | no such parameter exists in any local document; the nearest things are the 200 ms onset default and the 250 ms transition-down default. |
| Capture | the duration of a threshold capture (the screenshot's capture windows run 0 to 22 s; nothing states it), and the rule for "too close together". |
| Settling | no parameter of that name exists in any local document. |
| Rate / pulse-width envelope for an **adaptive** group on current software | only the 2020 sensing-era card's 50 to 185 Hz and 300 us; nothing dated after Adaptive Therapy shipped. |

---

## 4. For the record: what the Summit RC+S guide says (a different device, do not transfer)

Kept here only so the local "Research Lab Programmer Guide" is not mistaken for the Percept guide.

| Summit RC+S setting | Value | Document, page | Quoted sentence |
|---|---|---|---|
| Sense Blanking | minimum set by the pulse-width limit, maximum 2.5 ms | 4NR010 p. 11; p. 43 | *"Sense Blanking—Time duration when sensing is blanked during each stimulation pulse (minimum value based on pulse width limit, maximum value of 2.5 ms)."* |
| Transition Slope Limits (the adaptive ramp-rate limit) | 0.002 to 50 mA/s | 4NR010 p. 11; p. 13; p. 43 | *"Transition Slope Limits—Maximum amplitude rise and fall times when transitioning between adaptive stimulation states (0.002-50 mA/sec)."* |
| Amplitude | 0 to 25.5 mA, 0.1 mA resolution | 4NR010 p. 11 | *"Amplitude—Strength of pulse in milliamperes (mA); (0-25.5 mA, with a 0.1 mA resolution)."* |
| Adaptive group | one dedicated group; Group A is the safe fallback; cycling not allowed | 4NR010 p. 43 | *"Group A is designated as the 'safe' group that is switched to if the patient disables adaptive therapy."* |

None of these is a Percept value.

---

## 5. How this was checked

- Each PDF's text extraction (`.txt` beside it) was searched for every term in the brief (onset,
  transition, startup, delay, blanking, averaging, threshold, ramp, window, rate, capture,
  settling, limit) and the hits were read in context with printed page numbers.
- The white paper's Table 1 (p. 14), the Capturing Thresholds / Limits page (p. 15) and the
  Transition Durations / Advanced Settings page (p. 16) were rendered from the PDF at 400 dpi and the
  four tablet screenshots were read directly, because the slider endpoints and the Advanced
  Settings values exist only as pixels, not as text.
- The 2021 session-report JSON was walked programmatically for every key matching adaptive,
  threshold, ramp, blank, averaging, onset, transition, startup, delay, limit, softstart, cycling,
  highpass or sensing; the matches are the ones quoted above and no adaptive key exists in it.
- The repository's `DEVICE_percept_rc.md` §2 table and `constraints.py` (`THRESHOLD_MODE_TABLE`,
  rules D08, D09, D13, D14, D20, D21, D28, D30, D31) were read and compared line by line.
