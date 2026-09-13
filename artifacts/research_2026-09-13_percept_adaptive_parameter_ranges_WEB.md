# Percept BrainSense Adaptive DBS: the programmable ranges that are actually written down anywhere public

**Written 2026-09-13. Web and toolkit sources only.** A parallel search of the manuals on the
shared drive is a separate report. Nothing in this file was edited in the repository; it is the one
file this task wrote.

**How to read the labels.** Every value carries a kind and a confidence.

| Kind | Meaning |
|---|---|
| (a) | a documented **adjustable range** — the smallest and largest value a clinician can set |
| (b) | a documented **fixed value** the device uses and nobody can change |
| (c) | a **default** — what the device starts at; not a range |
| (d) | a **study's chosen setting** — what one group of authors set on their patients; not a range |
| (e) | **not found** |

| Confidence | Meaning |
|---|---|
| HIGH | a Medtronic document or an FDA document states it |
| MEDIUM | a peer-reviewed paper states it as the device's own behaviour or range |
| LOW | a study's chosen value, a toolkit's assumption, or a value read off an exported file |

**The one source that answers most of the question is the FDA's own approval summary**
(P960009/S478, approved 20 February 2025). Its Table 2, "Key aDBS Configurable Parameters", is the
only public document found that gives selection ranges. Everything else either gives defaults, a
trial's chosen values, or a narrower band that the trial let clinicians move within.

---

## 0. The FDA table, reproduced verbatim

Source: FDA, *Summary of Safety and Effectiveness Data, PMA P960009/S478*, Percept PC and Percept
RC with the aDBS software feature. https://www.accessdata.fda.gov/cdrh_docs/pdf/P960009S478B.pdf.
Section V (device description), page 8 of 59. The sentence before the table: *"Each mode has a set
of default settings, some of which the clinician will have the ability to adjust. With both aDBS
modes, the clinician is required to configure the upper and lower stimulation amplitude limits based
on safe levels for each patient. Table 2 below lists the key configurable parameters in aDBS."*

| Configurable Parameter | Selection Range (as printed) |
|---|---|
| Sensing Band | 8-30 Hz |
| Threshold Mode | Dual or Single Threshold |
| Lower LFP Threshold | 0.55-400μVrms. Note: in Single Threshold Mode, Lower = Upper LFP Threshold |
| Upper LFP Threshold | 0.55-400μVrms. Note: in Single Threshold Mode, Lower = Upper LFP Threshold |
| Lower Stimulation Limit | 0-25.5 mA |
| Upper Stimulation Limit | 0-25.5 mA |
| Upper Threshold Onset Duration | Dual Threshold - 0 to 6 min; Single Threshold - 0 to 30 seconds |
| Lower Threshold Onset Duration | Dual Threshold - 0 to 6 min; Single Threshold - 0 to 30 seconds |
| Stimulation Ramp Up Duration | 250ms-30 minutes |
| Stimulation Ramp Down Duration | 250ms-30 minutes |

**What the table does not give:** the step size (resolution) of any of these, the default of any of
them, the averaging window, the blanking time, the startup delay, or the band width. Those are
covered parameter by parameter below.

---

## 1. Onset duration (upper-threshold onset, lower-threshold onset)

What it is: how long the band power has to stay past a threshold before the device starts changing
the current. There is one timer for crossing the upper threshold and one for crossing the lower.

| Value | Kind | Confidence | Source | Where | Quoted sentence |
|---|---|---|---|---|---|
| Dual threshold: **0 to 6 min**, for both the upper and the lower onset | (a) | HIGH | FDA SSED P960009/S478 | Table 2, p. 8 | "Upper Threshold Onset Duration — Dual Threshold - 0 to 6 min"; "Lower Threshold Onset Duration — Dual Threshold - 0 to 6 min" |
| Single threshold: **0 to 30 seconds**, for both | (a) | HIGH | FDA SSED P960009/S478 | Table 2, p. 8 | "Single Threshold - 0 to 30 seconds" (printed under both onset rows) |
| Single threshold: 200–500 ms | (d), described by the authors as the range the clinician could set in the trial — narrower than the FDA range, so read it as the trial's working band, not the device's limit | MEDIUM | Stanslaski et al. 2024, npj Parkinson's Disease 10:174, doi:10.1038/s41531-024-00772-5 (Percept PC, ADAPT-PD) | Methods, "Single threshold mode" | "The time above or below threshold needs to exceed an onset duration before changing stimulation. The onset duration is programmable by the clinician to meet patient needs in a range 200–500 ms. The onset time range is intended to ensure the detection is fast enough to identify long duration alpha-beta signals >500 ms and to avoid false detecting stimulation changes (along with the blanking duration default 550 ms following stimulation changes)." |
| Dual threshold: 1.2–2 s | (d), same caveat as the row above | MEDIUM | Stanslaski et al. 2024 | Methods, "Dual threshold mode" | "In dual threshold the onset time requirements are less. The onset duration is programmable by the clinician to meet patient needs in a range of 1.2–2 s. The design drivers in setting onset for this algorithm was to ensure no false detection of stimulation changes and return to sensing with this slowly adapting algorithm." |
| Dual threshold: "more than 1.2 s" | (c), reads as the default the authors ran with | MEDIUM | Cascino et al. 2026, npj Parkinson's Disease, doi:10.1038/s41531-026-01269-z (ADAPT-START, Percept PC and one RC) | Methods | "Changes in current amplitude occur in steps of 0.1 mA for the Percept PC (Primary Cell) and 0.01 mA for the RC (Rechargeable Cell) if the beta power stays outside the threshold range for more than 1.2 s." |
| Dual threshold: 3.6 s in one patient | (d) | LOW | Busch et al. 2025, npj Parkinson's Disease, doi:10.1038/s41531-025-01124-7, PMC12397205 (Percept, dual threshold, 8 patients) | Results | "(3) increased onset duration to 3.6 s to reduce the sensitivity to brief artifact-driven transients." |
| Resolution (step size) | (e) | — | — | — | not stated in any source found |
| Default | (e) as a number; the FDA says defaults exist | — | FDA SSED | p. 8 | "Each mode has a set of default settings, some of which the clinician will have the ability to adjust." |

**Note on the disagreement.** The FDA says single-threshold onset can go to 30 s and dual to 6 min;
the ADAPT-PD methods paper says 200–500 ms and 1.2–2 s. The paper's wording ("programmable ... in a
range") sounds like a device limit but the FDA table, written after the trial, is wider. The
3.6 s dual-threshold value used by Busch et al. is outside the paper's 1.2–2 s and inside the FDA's
0–6 min, which supports reading the paper's numbers as the trial's chosen working band.

---

## 2. Transition up duration and transition down duration (FDA: "Stimulation Ramp Up/Down Duration"; JSON: `TransitionUpInMilliSeconds`, `TransitionDownInMilliSeconds`)

What it is: how long the device takes to move the current from one limit to the other.

| Value | Kind | Confidence | Source | Where | Quoted sentence |
|---|---|---|---|---|---|
| **250 ms to 30 minutes**, up and down each | (a) | HIGH | FDA SSED P960009/S478 | Table 2, p. 8 | "Stimulation Ramp Up Duration — 250ms-30 minutes"; "Stimulation Ramp Down Duration — 250ms-30 minutes" |
| Single threshold has shorter defaults than dual | (c), stated without numbers | HIGH | FDA SSED; identical wording in the ADAPT-PD protocol | p. 6; CIP v5.0 p. 39 | "This mode has shorter default stimulation ramp up and ramp down durations than dual mode." |
| Dual threshold default: 2.5 min up, 5 min down | (c) | MEDIUM | Stanslaski et al. 2024 | Table 3, step 5 | "Default ramp time of 2.5 min upwards and 5 min downwards." |
| Dual threshold, what the trial let clinicians set: 1 to 10 min up, 1 to 10 min down | (d) — a trial's allowed band, narrower than the FDA range | MEDIUM | Stanslaski et al. 2024 | Table 3, step 5 | "Ramp time was allowed to range from 1 to 10 min upwards, and 1 to 10 min downwards per clinician determination." |
| Single threshold default: 250 ms | (c) | MEDIUM | Stanslaski et al. 2024 | Table 3, step 5; Results | "Default ramp time of 250 ms."; "the single threshold mode adjusted stimulation amplitude over 250 ms between the upper and lower stimulation limits set by the clinician" |
| Same two numbers from Medtronic's own compendium | (c) | HIGH | Medtronic, *Scientific compendium, BrainSense Adaptive Deep Brain Stimulation (aDBS)*, ©2025, https://www.medtronic.com/content/dam/medtronic-wide/public/western-europe/products/neurological/deep-brain-stimulation/adbs-scientific-compendium.pdf | section "Introduction to aDBS Modes" (table) | "Single Threshold mode rapidly (milliseconds) adjusts stimulation amplitude between lower and upper limits within 250 milliseconds based on LFP power."; "Dual Threshold mode slowly (minutes) adjusts stimulation amplitude based on changes in LFP power, taking 2.5 minutes to increase and 5 minutes to decrease the amplitude." |
| Kept at default in ADAPT-START; one patient tried 10 s up, 30 s down | (d) | LOW | Cascino et al. 2026 | Methods; Results | "Ramp-up and ramp-down times were kept at the default settings (see above), consistent with those applied in the ADAPT-PD trial"; "multiple reprogramming strategies were attempted, including adjustments to ramping times (e.g., 10 s up, 30 s down)." |
| Expressed as a rate: 0.05 mA/s up, 0.025 mA/s down, on a Percept PC with the adaptive firmware unlocked for research | (d) | LOW | Brain Stimulation 2026, doi:10.1016/j.brs.2026.103028, PMC13218403 (one participant, Stanford) | main text | "A moderate ramp rate (0.05 mA/sec up, 0.025 mA/sec down) was implemented with a dual-threshold control policy to enable aDBS to respond to fluctuations in beta power without causing adverse sensations (e.g. dizziness or parethesias)". Note: the device parameter is a duration, not a rate; this paper converted it for a 2.2–2.9 mA window. |
| Step size of the current change: 0.1 mA (Percept PC), 0.01 mA (Percept RC) | (b) | MEDIUM | Cascino et al. 2026 | Methods | "Changes in current amplitude occur in steps of 0.1 mA for the Percept PC (Primary Cell) and 0.01 mA for the RC (Rechargeable Cell)" |
| Resolution of the duration setting | (e) | — | — | — | not stated |

---

## 3. Adaptive startup delay (JSON: `AdaptiveStartupDelayInMilliSeconds`)

| Value | Kind | Confidence | Source | Where | Quoted sentence |
|---|---|---|---|---|---|
| Range, default, meaning | (e) | — | — | — | **Not found in any public document, paper or toolkit.** The only evidence it exists is the field name in the Percept session-report JSON (see §12). No Medtronic document, no FDA document and no paper found uses the phrase "startup delay" for Percept adaptive therapy. |

---

## 4. The two LFP thresholds (JSON: `LowerLfpThreshold`, `UpperLfpThreshold`)

| Value | Kind | Confidence | Source | Where | Quoted sentence |
|---|---|---|---|---|---|
| **0.55 to 400 μVrms**, each threshold | (a) | HIGH | FDA SSED P960009/S478 | Table 2, p. 8 | "Lower LFP Threshold — 0.55-400μVrms"; "Upper LFP Threshold — 0.55-400μVrms" |
| In single-threshold mode the two are one value | (b) | HIGH | FDA SSED | Table 2, p. 8 | "Note: in Single Threshold Mode, Lower = Upper LFP Threshold" |
| Resolution | (e) | — | — | — | not stated. The exported values are decimals (e.g. 20.0, 30.0, 105, 270); no step is documented. |
| How the trial set them: 30-second average band power at each stimulation limit | (d) | MEDIUM | Stanslaski et al. 2024 | Table 3, steps 3–4 | "DBS stimulation is set to the lower stimulation limit. The average LFP level over a 30 s epoch is set as the upper LFP threshold."; "DBS stimulation is set to the upper stimulation limit. The average LFP level over a 30 s epoch is set as the lower LFP threshold." |
| Single-threshold default placement: 75 % of the way between the two captured values | (c) | MEDIUM | Stanslaski et al. 2024 | Table 3, step 4 | "Finally, the single threshold mode default is set at 75% of the way between upper threshold and lower threshold." |
| ADAPT-START placement: 25th and 75th percentile of daytime band power from the Timeline recording | (d) | LOW | Cascino et al. 2026; the same rule in Busch et al. 2025 | Methods | "we manually set the lower and upper LFP thresholds at about the 25th and 75th percentiles of beta power recorded during wakeful periods, respectively."; Busch: "Lower and upper LFP thresholds were set to the 25th and 75th percentile of daytime beta power based on Timeline data." |
| Factory placeholder in a device where adaptive was never configured: lower 20, upper 30 | (c) | LOW | three real exported session reports on public GitHub (a 2022 file in Le-bruit-de-nos-pas/brain_sense_dbs_tests_2022, a 2024 file in Al-Borno-Lab/Vibrotactile_Clinic_Source_Code_2026), and the upstream BRAVO client, which treats exactly these values as "Adaptive DBS Disabled" | `Groups[].ProgramSettings.SensingChannel[]` | 2022 file: `'UpperLfpThreshold': 30.0, 'LowerLfpThreshold': 20.0`; upstream `Client/src/views/Reports/TherapyHistory/index.js` line 139: `if (therapy.LFPThresholds[0] == 20 && therapy.LFPThresholds[1] == 30 && therapy.CaptureAmplitudes[0] == 0 && therapy.CaptureAmplitudes[1] == 0)` then `"Adaptive DBS Disabled"` |
| Units caution | — | — | — | — | The FDA table writes the threshold range in **μVrms**; the papers write the peak-detection criterion in **μVp** (peak). These are different quantities; do not compare a 1.2 μVp signal test against the 0.55 μVrms floor without converting. |

---

## 5. Averaging window (JSON: `AveragingDurationInMilliSeconds`)

| Value | Kind | Confidence | Source | Where | Quoted sentence |
|---|---|---|---|---|---|
| Band power is computed and averaged every 100 ms | (b) | MEDIUM | Stanslaski et al. 2024 | Methods, "Single threshold mode" | "The LFP band power is calculated by the Percept PC device by taking the fast Fourier transform of the time series data and averaging it every 100 ms." |
| Algorithm decision rate: 20 per second in single threshold, 5 per second in dual threshold | (b) | MEDIUM | Bronte-Stewart et al. 2025, JAMA Neurology, doi:10.1001/jamaneurol.2025.2781, PMC12455485 (ADAPT-PD outcomes) | Discussion | "Battery longevity is dependent on both TEED and the energy required to run the adaptive algorithm, such as sampling rate (20 Hz with ST-aDBS and 5 Hz with DT-aDBS) and the frequency of stimulation amplitude adjustments." |
| Value in exported files: 3000 ms | (c), read off files, not documented | LOW | the 2022 and 2024 real exports above; also `BrainSenseLfp.TherapySnapshot.<side>.AveragingDurationInMilliSeconds` | — | 2022 file: `'AveragingDurationInMilliSeconds': 3000`; 2024 file: `SensingSetup.AveragingDurationInMilliSeconds => 3000` |
| Adjustable range | (e) | — | — | — | Not stated anywhere. Busch et al. 2024 (Brain Stimulation 17:125–133, doi:10.1016/j.brs.2024.01.007) varied "the smoothing of real-time beta power" on a Percept PC in 12 patients, which shows it can be changed, but the full text was behind a bot wall on three sites and the values tested were not retrieved. Abstract: "We investigated changes in two aDBS parameters: the onset time and the smoothing of real-time beta power." |
| Movement and heartbeat artefacts are handled by this averaging plus the onset timers, not by a separate filter | (b) | MEDIUM | Stanslaski et al. 2024 | Methods | "Movement and cardiac artifacts are filtered by the Percept system using signal averaging and onset timers to minimize improper adaptation. In addition, slow adapting ramp rates for the dual threshold algorithm further filter movement artifacts." |

---

## 6. LFP band centre and width

| Value | Kind | Confidence | Source | Where | Quoted sentence |
|---|---|---|---|---|---|
| Centre may be anywhere in **8–30 Hz** | (a) | HIGH | FDA SSED P960009/S478 | Table 2, p. 8 | "Sensing Band — 8-30 Hz" |
| Width is **5 Hz, fixed** | (b) | MEDIUM | Stanslaski et al. 2024; Cascino et al. 2026; Thenaisie et al. 2021 J Neural Eng doi:10.1088/1741-2552/ac1d5b | Methods | Stanslaski: "The Feedback variable (LFP Power integrated over a 5 Hz band) is delivered back to the Comparator"; Cascino: "The monitored beta power is calculated within a patient-specific frequency range of 5 Hz (fixed frequency range), centered around the most prominent alpha-beta peak."; Thenaisie (Timeline mode): "Recording of the power of the pre-selected frequency band (selected frequency ±2, 5 Hz)" |
| Sampling rate of the underlying signal: 250 Hz | (b) | MEDIUM | Stanslaski et al. 2024; Thenaisie et al. 2021 | Methods | "The LFP signal of interest is a time domain signal sampled at 250 Hz by the Sensor block"; Thenaisie: "The Percept PC recording device uses a nominal sampling frequency of 250 Hz" |
| Centre resolution (the frequency bins the centre can snap to) | (e) | — | — | — | Not stated. The JSON carries `FrequencyInHertz` with two decimals and a `FrequencyIndex` integer (e.g. 17.57 Hz, index 18 in the 2022 file), which is consistent with a fixed bin grid, but no document gives the grid. |
| Minimum peak amplitude to run adaptive: 1.2 μVp | (d) — a trial inclusion criterion that Medtronic also calls "recommended" | HIGH for the trial; the FDA and Medtronic present it as a criterion, not a device limit | FDA SSED p. 17; Medtronic *ADAPT-PD clinical trial overview* (©2025, document code 2025-adapt-pd-clinical-trial-overview-en-gb-emea-18797073) | inclusion criteria | Medtronic overview: "LFP peak power amplitude ≥1.2 μVp in the Alpha-Beta band (8-30 Hz) on left and/or right DBS leads. (This peak amplitude is recommended for aDBS.)"; Stanslaski: "from 1.2 µVp (the lowest acceptable power to run aDBS) to almost 9 µVp" |

---

## 7. Stimulation amplitude lower limit and upper limit under adaptive (JSON: `LowerLimitInMilliAmps`, `UpperLimitInMilliAmps`)

| Value | Kind | Confidence | Source | Where | Quoted sentence |
|---|---|---|---|---|---|
| **0 to 25.5 mA**, each limit | (a) | HIGH | FDA SSED P960009/S478 | Table 2, p. 8 | "Lower Stimulation Limit — 0-25.5 mA"; "Upper Stimulation Limit — 0-25.5 mA" |
| The clinician must set both; the device does not default them | (b) | HIGH | FDA SSED | p. 8 | "With both aDBS modes, the clinician is required to configure the upper and lower stimulation amplitude limits based on safe levels for each patient." |
| Step: 0.1 mA (PC), 0.01 mA (RC) | (b) | MEDIUM | Cascino et al. 2026 | Methods | quoted in §2 |
| Trial rule for choosing them | (d) | MEDIUM | Stanslaski et al. 2024 | Table 3, steps 1–2 | "Determine upper stimulation limit — off Medication — DBS stimulation set to the highest safe constant amplitude at which symptoms are controlled and stimulation-related side effects are minimized per clinician determination."; "Determine lower stimulation limit — on Medication — DBS stimulation set to the lowest constant amplitude at which symptoms are controlled per clinician determination." |
| Lower limit is not allowed to be zero in practice in ADAPT-PD (design choice, not a device limit) | (d) | MEDIUM | Stanslaski et al. 2024 | Discussion | "In prior studies, aDBS in both modes was allowed to decrease stimulation amplitude to zero but this was shown in at least one study to occasionally result in sub-therapeutic therapy ... Consequently, in the ADAPT-PD study, the lower stimulation limit is individually chosen as that at which there was still acceptable therapeutic improvement." |
| "Suspend amplitude" — the fixed current the device falls back to when the patient pauses adaptive therapy (JSON: `SuspendAmplitudeInMilliAmps`) | (b), no range | HIGH | ADAPT-PD Clinical Investigation Plan v5.0, 11 Sep 2023, https://cdn.clinicaltrials.gov/large-docs/12/NCT04547712/Prot_000.pdf, p. 66; FDA SSED p. 6 | — | CIP: "This Pause Adaptive Therapy (amplitude last delivered in that group prior to starting aDBS therapy (i.e. the suspend amplitude)) is defined by the clinician as part of the aDBS setup process"; FDA: "When Adaptive Therapy is paused therapy reverts to a fixed cDBS level programmed by the clinician." |

---

## 8. Ramp rates

The device parameter is a **duration** (§2), not a rate. The only rate statements found are (i) the
Percept research paper in §2 (0.05 / 0.025 mA/s, one participant) and (ii) Summit RC+S papers,
which are a different device (§13). Kind (d), LOW, both.

---

## 9. Single-threshold mode: onset and offset

| Value | Kind | Confidence | Source | Where | Quoted sentence |
|---|---|---|---|---|---|
| Onset timer, both directions: 0 to 30 s | (a) | HIGH | FDA SSED | Table 2, p. 8 | "Single Threshold - 0 to 30 seconds" under both "Upper Threshold Onset Duration" and "Lower Threshold Onset Duration" |
| There is no separate "offset" parameter; the lower-threshold onset timer plays that role, and in single mode the two thresholds are the same number | (b) | HIGH | FDA SSED | Table 2 | "Note: in Single Threshold Mode, Lower = Upper LFP Threshold" |
| Behaviour: current goes all the way to the upper limit while power is above, all the way to the lower limit while below | (b) | MEDIUM | Stanslaski et al. 2024 | Methods | "The single threshold algorithm directs the neurostimulator to increase stimulation amplitude to the upper stimulation limit when LFP band power exceeds the threshold and to decrease stimulation amplitude toward the lower stimulation limit when the LFP power falls below the threshold" |
| Both sides move together when one side crosses | (b) | MEDIUM | Stanslaski et al. 2024 | Methods | "For single threshold mode in a bilaterally implanted patient, if the LFP power crosses the LFP threshold within one hemisphere, a change in stimulation is directed to both hemispheres." |
| Ramp default 250 ms | (c) | MEDIUM | Stanslaski et al. 2024 | Table 3 | quoted in §2 |

---

## 10. Blanking (JSON: `DetectionBlankingDurationInMilliSeconds`; and, separately, `SensingBlankingDurationInMicroseconds`)

Two different things share the word.

| Value | Kind | Confidence | Source | Where | Quoted sentence |
|---|---|---|---|---|---|
| **Detection blanking** — after the current changes, the detector ignores the signal for a while. Default **550 ms** | (c) | MEDIUM | Stanslaski et al. 2024 | Methods, "Single threshold mode" | "... to avoid false detecting stimulation changes (along with the blanking duration default 550 ms following stimulation changes). LFP power with amplitudes above the LFP threshold for longer than the onset duration trigger stimulation amplitude changes with proper control of the detection blanking time, stimulation ramp time and detection onset times." |
| Detection blanking, adjustable range | (e) | — | — | — | not stated anywhere |
| Detection blanking, value in an exported file from a non-adaptive device: 2000 ms | (c) read off a file | LOW | 2022 real export (Le-bruit-de-nos-pas) | `BrainSenseLfp[0].TherapySnapshot.Left` | `'DetectionBlankingDurationInMilliSeconds': 2000` |
| **Sensing blanking** — the amplifier is switched off around each stimulation pulse; a group-level setting in microseconds, not an adaptive-therapy setting. Values seen: 2000 µs (2022 file), 1320 µs (2024 file) | (c) read off files | LOW | the two real exports | `Groups[].GroupSettings.SensingBlankingDurationInMicroseconds` | as listed |

---

## 11. Other adaptive parameters with a published value

| Parameter | Value | Kind | Confidence | Source | Quoted sentence |
|---|---|---|---|---|---|
| Stimulation rates the trial allowed with sensing/aDBS on SenSight leads | 55, 85, 110, 125, 145, 165 or 180 Hz | (d) — a trial criterion | HIGH | FDA SSED p. 17 (inclusion criteria) | "For subjects with the SenSight leads: Subject was configured to the following stimulation rates: 55, 85, 110, 125, 145, 165 or 180 Hz (as required for sensing/aDBS)" |
| Stimulation rate range in which sensing can be enabled | 55–180 Hz (SenSight), 50–185 Hz (3389) | (b) | MEDIUM | Cascino et al. 2026, Results | "sensing can be enabled only when stimulation frequency is in the range 55–180 Hz (SenSight leads) or 50–185 Hz (3389 leads), a limitation that prevented aDBS activation in one patient." |
| Chronic Timeline record used to check the adaptive settings | 10-minute averages, up to 60 days | (b) | MEDIUM | Stanslaski et al. 2024 | "The BrainSense Timeline feature allows a 5 Hz-wide frequency band of interest to be recorded chronically outside of the clinic and stored as 10 min averages for up to 60 days." |
| Which hemisphere's signal drives which side (dual threshold, one good side) | the good side's signal drives both | (d) | HIGH | ADAPT-PD CIP v5.0 p. 65; FDA SSED p. 16 | "the clinician should configure adaptive therapy in both hemispheres, using sensing from the hemisphere with LFP Alpha - Beta signal >=1.2μVp." |
| Patient can pause adaptive therapy from the handset | — | (b) | HIGH | FDA SSED p. 6 | "the Model A620 PPA can be used by patients to 'pause' their aDBS therapy. Pausing Adaptive Therapy is not the same as turning stimulation off." |
| Parameters the trial's statistical plan lists as the recorded "aDBS Method parameters" | decreasing ramp rate, increasing ramp rate, lower stimulation limit, upper stimulation limit | — | HIGH | ADAPT-PD Statistical Analysis Plan rev 4.0, 19 Oct 2023, https://cdn.clinicaltrials.gov/large-docs/12/NCT04547712/SAP_001.pdf, §7.9.3.11 p. 34–35 | "aDBS Method parameters by visit — o Decreasing ramp rate — o Increasing ramp rate — o Lower stimulation limit — o Upper stimulation limit" |
| What the investigational programmer let the clinician set (list, no ranges) | signal of interest, electrode configuration, LFP thresholds, upper and lower stimulation limits, transition durations, suspend amplitude | — | HIGH | ADAPT-PD CIP v5.0 p. 40 | "The investigational aDBS feature allows the physician to program aDBS on the Percept PC INS, including selecting an LFP signal of interest (Alpha -Beta for this study), programming electrode configuration, capturing LFP thresholds, setting upper and lower stimulation limits, transition durations and suspend amplitude." |

---

## 12. JSON field names found in the toolkits and in real exports

**Where they come from.** The `neuromodulation/perceive` toolbox ships four mock session reports
(`MockData/Report_Json_Session_Report_MOCK3.json`, `MOCK4.json`, and the two `_GroupHistory`
files). Its generator script (`MockData/generateMOCK.m`, function `replaceDigitsOnly`) **replaces
every digit in the file with a random digit**, so the field names and the enumeration strings are
real device output but **every number in the mock files is meaningless** (e.g. a lower limit of
8.6 mA above an upper limit of 1.4 mA, a transition of 965,951 ms). Two real exports on public
GitHub (2022, 2024) from devices where adaptive was never configured, and the upstream BRAVO
parser, confirm the names. No toolkit asserts or validates a range for any of these fields.

| Field (JSON path) | What it holds | Range asserted by any toolkit | Seen in |
|---|---|---|---|
| `Groups.*[].ProgramSettings.SensingChannel[].AdaptiveTherapyStatus` | `ADBSStatusDef.NOT_CONFIGURED` or `ADBSStatusDef.RUNNING` | none | perceive mock; upstream BRAVO `Percept.py`; ALFA-toolbox `getGroupInfo.m` |
| `...SensingChannel[].Mode` | `AdaptiveModeDef.DUAL_THRESHOLD_DIRECT` (the only value seen; a single-threshold enum name was not found in any public file) | none | perceive mock; upstream BRAVO reads it only when status is not NOT_CONFIGURED |
| `...SensingChannel[].AdaptiveTherapy.UpperThresholdOnsetInMilliSeconds` | upper onset timer, ms | none | perceive mock; upstream BRAVO BIDS docs |
| `...SensingChannel[].AdaptiveTherapy.LowerThresholdOnsetInMilliSeconds` | lower onset timer, ms | none | same |
| `...SensingChannel[].AdaptiveTherapy.DetectionBlankingDurationInMilliSeconds` | detection blanking, ms | none | same |
| `...SensingChannel[].AdaptiveTherapy.AdaptiveStartupDelayInMilliSeconds` | startup delay, ms; **meaning undocumented** | none | perceive mock; upstream BRAVO `Database.py` |
| `...SensingChannel[].TransitionUpInMilliSeconds`, `TransitionDownInMilliSeconds` | ramp durations, ms; upstream BRAVO renames them `RampUpTime` / `RampDownTime` | none | perceive mock; upstream BRAVO `Percept.py` lines 1248–1249 |
| `...SensingChannel[].UpperLfpThreshold`, `LowerLfpThreshold` | the two thresholds | none (upstream BRAVO treats 20/30 as "disabled") | all four toolkits |
| `...SensingChannel[].UpperLimitInMilliAmps`, `LowerLimitInMilliAmps` | adaptive current limits | none | perceive mock; ALFA; upstream BRAVO (read only when `Mode == "LimitModeDef.AdvanceEdit"`) |
| `...SensingChannel[].SuspendAmplitudeInMilliAmps` | fixed current used when adaptive is paused | none | real 2024 export (4.2 mA); upstream BRAVO |
| `...SensingChannel[].UpperCaptureAmplitudeInMilliAmps`, `LowerCaptureAmplitudeInMilliAmps`, `MeasuredUpperLfp`, `MeasuredLowerLfp` | the two currents at which the thresholds were captured and the power measured at each | none | real 2024 export (all 0 when never configured); upstream BRAVO |
| `...SensingChannel[].SensingSetup.FrequencyInHertz`, `AveragingDurationInMilliSeconds` | band centre; averaging window | none | perceive `perceive_extract_bsl.m`; real exports (3000 ms) |
| `...SensingChannel[].GangedToHemisphere` | which side's signal drives this side (upstream BRAVO calls it "Bypass") | none | upstream BRAVO `Percept.py` line 1251 |
| `Groups.*[].GroupSettings.SensingBlankingDurationInMicroseconds` | amplifier blanking around each pulse, µs (not an adaptive setting) | none | real exports (2000, 1320) |
| `BrainSenseLfp[].TherapySnapshot.<Left/Right>.StreamingAdaptiveMode` | `StreamingAdaptiveModeDef.DUAL_THRESHOLD_DIRECT` | none | perceive mock |
| `BrainSenseLfp[].TherapySnapshot.<side>.{UpperLfpThreshold, LowerLfpThreshold, AveragingDurationInMilliSeconds, DetectionBlankingDurationInMilliSeconds, UpperThresholdOnsetInMilliSeconds, LowerThresholdOnsetInMilliSeconds, AdaptiveStartupDelayInMilliSeconds, TransitionUpInMilliSeconds, TransitionDownInMilliSeconds, LowerLimitInMilliAmps, UpperLimitInMilliAmps, FrequencyInHertz, FrequencyIndex}` | the same settings, as they stood during one streaming recording | none | perceive mock; the 2022 real export carries the first four of these |
| `EventSummary.LfpAndAmplitudeSummary[].TimeAdaptiveRunningPercent`, `AdaptiveAmplitudeReductionPercent` | how much of the time adaptive was running; how much lower the average current was | none | perceive mock only |

Toolkits searched and what they hold: **neuromodulation/perceive** (master, 102 source and data
files fetched) — reads only `FrequencyInHertz`, `LowerLfpThreshold`, `UpperLfpThreshold`,
`AveragingDurationInMilliSeconds` from `TherapySnapshot` to label a recording; the adaptive fields
appear only in its mock data. **jgvhabets/PyPerceive** (main, 32 files) — no adaptive field at
all. **YohannThenaisie/PerceptToolbox** (main, 13 files) — none. **sange019/Percept-Analysis** —
none. **openmind-consortium/Analysis-percept-data-** — a copy of an older perceive.m, same four
fields. **Data-Driven-Brain-Stimulation/ALFA-toolbox** (`get/getGroupInfo.m`) — reads
`AdaptiveTherapyStatus`, the two thresholds and the two limits. **Fixel-Institute/BRAVO** (the
upstream of this repository; `BRAVO/modules/MedtronicPercept/Percept.py`,
`BRAVO/modules/BIDSExport/docs/DATA_INVENTORY.md` and `BIDS_MAPPING.md`) — the fullest parser, and
its BIDS documentation names every field in the table above. A "Report_Json_Session_Report" schema
document from Medtronic was **not found** anywhere online.

---

## 13. Device confusion: which sources are about a different device

| Source | Device | Why it matters |
|---|---|---|
| Oehrn et al. 2024, Nature Medicine, doi:10.1038/s41591-024-03196-z (PMC11826929) | **Summit RC+S, model B35300R** — an investigational device, not Percept | Its parameters are RC+S ones: "onset and termination period=0", "update rate=1.5 s" in clinic and 10–15 s at home, ramp 0.5–1.0 mA/s, "detector blanking period exceeding the update rate by one second", 1 s FFT windows. None of these transfer to Percept. |
| Gilron et al. 2021, Nature Biotechnology, doi:10.1038/s41587-021-00897-5 | Summit RC+S | RC+S linear-discriminant detector; onset/termination are counted in "update rate" units, not milliseconds. |
| Gilron et al. 2021, Frontiers in Neuroscience, doi:10.3389/fnins.2021.732499 (PMC8558614), "Sleep-aware adaptive DBS" | Summit RC+S | Gives the RC+S definitions that the word "onset" comes from: "Onset 0 — Number of detector counts must be above threshold to change to state. A value of 0 means that as soon as the threshold is crossed stimulation ramps to the target state."; "Termination 4 — Number of detector counts must be below threshold ... (update rate × 4; = 4 min in this case)"; "State change blank 30 — In units of FFT interval." **Percept has no "termination duration"; its equivalent is the lower-threshold onset duration.** |
| Brain Communications 2025, doi:10.1093/braincomms/fcaf266 (PMC12268161), beta-burst aDBS for gait | Summit RC+S with a computer in the loop | Not embedded control; not Percept. |
| Cagle / Nakajima et al. 2021, Frontiers in Human Neuroscience, doi:10.3389/fnhum.2021.702961 (PMC8414587), "Case Report: Chronic Adaptive DBS Personalizing Therapy Based on Parkinsonian State" | **Percept PC** (Japan, where adaptive was released first). Gives no timing parameters. | Listed because the task named "Cagle 2021"; it is not an RC+S paper. |
| Thenaisie et al. 2021, J Neural Eng, doi:10.1088/1741-2552/ac1d5b | Percept PC, sensing only; adaptive not yet available | Good for 250 Hz sampling and the 5 Hz band; says nothing about onset, ramp or blanking. |
| Busch et al. 2024, Brain Stimulation, doi:10.1016/j.brs.2024.01.007 | Percept PC, single threshold, acute post-operative, research firmware | Varied onset time and smoothing; full text not reachable (three sites returned a bot-check page). |
| **"CLIO"** | **Not found.** The string "CLIO" does not occur, in any DBS sense, in any Medtronic document, FDA document, paper, toolkit or repository searched, nor in this project's own record. The older research device is the **Summit RC+S** (and before it the Activa PC+S with the Nexus-D telemetry). If "CLIO" is a lab shorthand, it does not correspond to a published Medtronic product or software name that this search could find; treat it as unresolved rather than as a synonym for Summit. |

---

## 14. Not found anywhere online

1. **A step size (resolution) for any adaptive timing parameter** — onset, transition, blanking,
   startup delay. The FDA gives ranges only.
2. **A step size for the LFP thresholds.**
3. **Any numeric default from a Medtronic or FDA document** — the FDA says "Each mode has a set of
   default settings" and gives none. The only defaults are the trial paper's (2.5 min / 5 min /
   250 ms ramps, 550 ms blanking, single threshold at 75 %).
4. **The adaptive startup delay**: no meaning, no range, no default; field name only.
5. **The adjustable range of the averaging window and of the detection blanking**; only defaults
   (100 ms compute interval; 550 ms blanking) and file values (3000 ms; 2000 ms) exist.
6. **The band-centre grid** (which frequencies the 5 Hz band can be centred on).
7. **A single-threshold mode enumeration string** in any public JSON; only
   `DUAL_THRESHOLD_DIRECT` was seen.
8. **A Medtronic clinician programming guide for BrainSense Adaptive**. manuals.medtronic.com
   returns only landing pages to search; no adaptive programming guide surfaced on the public web.
   The document the task calls "the BrainSense Adaptive DBS white paper (Medtronic, 2025)" was not
   found under that name; the two public Medtronic documents are the *ADAPT-PD clinical trial
   overview* and the *Scientific compendium*, both ©2025, and neither gives a range.
9. **A Medtronic JSON schema document** for the session report.
10. **The values tested in Busch et al. 2024** for onset time and smoothing (full text blocked).
11. **"CLIO"** — see §13.

---

## 15. Sources, with what each was used for

Medtronic and FDA
- FDA, SSED PMA P960009/S478, Percept PC / Percept RC aDBS software, approval 20 Feb 2025. https://www.accessdata.fda.gov/cdrh_docs/pdf/P960009S478B.pdf — Table 2 (p. 8); mode descriptions (p. 6–7); trial criteria (p. 16–17).
- Medtronic, *BrainSense Adaptive DBS (aDBS) ADAPT-PD clinical trial overview*, ©2025, code 2025-adapt-pd-clinical-trial-overview-en-gb-emea-18797073. https://www.medtronic.com/content/dam/medtronic-wide/public/western-europe/products/neurological/deep-brain-stimulation/adbs-clinical-trial-overview.pdf — "How does it work"; "Choose between two threshold modes"; inclusion criteria.
- Medtronic, *Scientific compendium, BrainSense Adaptive Deep Brain Stimulation (aDBS)*, ©2025. https://www.medtronic.com/content/dam/medtronic-wide/public/western-europe/products/neurological/deep-brain-stimulation/adbs-scientific-compendium.pdf — "Introduction to aDBS Modes".
- ADAPT-PD Clinical Investigation Plan v5.0, 11 Sep 2023 (NCT04547712). https://cdn.clinicaltrials.gov/large-docs/12/NCT04547712/Prot_000.pdf — p. 39–40, 65–66.
- ADAPT-PD Statistical Analysis Plan rev 4.0, 19 Oct 2023. https://cdn.clinicaltrials.gov/large-docs/12/NCT04547712/SAP_001.pdf — §7.9.3.11.
- Medtronic patents US12036410B2 and US11571576B2 (Google Patents) — checked; no numeric ranges for these parameters.

Peer-reviewed, Percept
- Stanslaski S, Summers RLS, Tonder L, et al. npj Parkinson's Disease 2024;10:174. doi:10.1038/s41531-024-00772-5. Full text via Europe PMC (PMC11408616).
- Cascino S, Luiso F, Caffi L, Palmisano C, Contaldi E, Pezzoli G, Isaias IU, Bonvegna S. npj Parkinson's Disease 2026. doi:10.1038/s41531-026-01269-z (PMC13056985); preprint doi:10.1101/2025.09.25.25336275.
- Bronte-Stewart HM et al. JAMA Neurology 2025. doi:10.1001/jamaneurol.2025.2781 (PMC12455485).
- Busch JL et al. npj Parkinson's Disease 2025. doi:10.1038/s41531-025-01124-7 (PMC12397205).
- Busch JL et al. Brain Stimulation 2024;17:125–133. doi:10.1016/j.brs.2024.01.007 (abstract only).
- Brain Stimulation 2026, doi:10.1016/j.brs.2026.103028 (PMC13218403).
- Thenaisie Y et al. J Neural Eng 2021. doi:10.1088/1741-2552/ac1d5b.
- Nakajima/Cagle et al. Front Hum Neurosci 2021. doi:10.3389/fnhum.2021.702961 (PMC8414587).

Peer-reviewed, Summit RC+S (for the confusion section only)
- Oehrn CR et al. Nature Medicine 2024. doi:10.1038/s41591-024-03196-z (PMC11826929).
- Gilron R et al. Nature Biotechnology 2021. doi:10.1038/s41587-021-00897-5.
- Gilron R et al. Front Neurosci 2021. doi:10.3389/fnins.2021.732499 (PMC8558614).
- Brain Communications 2025. doi:10.1093/braincomms/fcaf266 (PMC12268161).

Code and data
- https://github.com/neuromodulation/perceive (master): `MockData/Report_Json_Session_Report_MOCK3.json`, `MOCK4.json`, `MOCK3_GroupHistory.json`, `MOCK4_GroupHistory.json`, `MockData/generateMOCK.m`, `toolbox/perceive_extract_bsl.m`, `toolbox/perceive_test_BIDS.m`.
- https://github.com/jgvhabets/PyPerceive (main); https://github.com/YohannThenaisie/PerceptToolbox (main); https://github.com/sange019/Percept-Analysis (main); https://github.com/openmind-consortium/Analysis-percept-data- (`perceive.m`).
- https://github.com/Fixel-Institute/BRAVO: `BRAVO/modules/MedtronicPercept/Percept.py`, `BRAVO/modules/BIDSExport/docs/BIDS_MAPPING.md`, `BRAVO/modules/BIDSExport/docs/DATA_INVENTORY.md`, `Client/src/views/Reports/TherapyHistory/index.js`.
- https://github.com/Data-Driven-Brain-Stimulation/ALFA-toolbox: `get/getGroupInfo.m`.
- https://github.com/Le-bruit-de-nos-pas/brain_sense_dbs_tests_2022: `stn_dbs_lfp_dec_2022.py` (a pasted real `TherapySnapshot` from a 2022 export).
- https://github.com/Al-Borno-Lab/Vibrotactile_Clinic_Source_Code_2026: `Dataset Processing/data/Patient_4_Data/Report_Json_Session_Report_20240701T131601.json` (a real 2024 export, adaptive never configured).
- GitHub code search (via `gh api search/code`) for each field name: hits only in the repositories above.
