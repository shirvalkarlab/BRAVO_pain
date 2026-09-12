# The Medtronic Percept RC — every device fact this platform depends on

**This document replaces the device sections of the mega handoff, the design ledger, the
calibration handoff and the module README.** Where those four disagreed, the newer result was
taken; the resolution of each disagreement is recorded in
`.planning/2026-09-06-cache-store-and-record-consolidation/findings.md` §1.

**Every constant below was read from the working tree at commit `705bdb0`, and the line number
beside it is where it is defined today.** Line numbers drift with every edit. Search for the name
rather than trusting the number, and never trust a line number quoted in an archived document —
all of them have moved.

**Sources.** The firmware timing table comes from the Medtronic white paper UC202012929dEN, and
the copy is at `.../ADMIN/Equipment/Percept RC/Medtronic_PerceptAdaptive_WhitePaper_032025.pdf`
on the shared drive, alongside the DBS software manual, the recharger guide and the SenSight lead
specification. The stream facts were verified against this participant's own exported device
files. The calibration was measured in the session recorded in
`HANDOFF_TD_LSB_calibration_2026-06-27.md`, now archived.

---

## 1. Which device, and what that changes

The target is the **Medtronic Percept RC**. The **Summit RC+S** is a different device — it is the
research-only stimulator the earlier trial deployed on, and its controller is not the one this
platform must produce settings for. Two consequences that have each cost time before:

1. **The Summit RC+S allowed a multi-feature linear classifier with a sign that could be
   inverted. The Percept RC does not.** It takes one power band in and one or two switching
   values out. Any design that assumes a weighted combination of features is designing for the
   wrong device.
2. A figure headline reading "RC+S device sensing overview" is naming the wrong device. Every
   figure title on this platform says Percept RC.

**Firmware permission, confirmed.** This participant is configured in **Parkinson's adaptive
mode** under investigational permission. So the full adaptive engine is available, but the
platform is bound to that mode's parameter ranges, its fixed per-mode timing, and its **8 to
30 Hz limit on where an adaptive sensing band may sit.**

**There is no interface that writes a setting to the device.** The platform produces a
configuration for a clinician to program by hand on the tablet. Searching every Python and
JavaScript file in the repository for a deployment endpoint or a device credential returns
nothing. An archived version of the module README described such an endpoint and two environment
variables; **none of it exists**, and it is not carried here.

---

## 2. The three threshold modes, and their fixed timing

Defined in code at `analytics.py:3351`, tabulated from the white paper's Table 1. **The timing is
fixed per mode and is not adjustable.**

| What | Dual Threshold | Single Threshold | Single Threshold Inverse |
|---|---|---|---|
| Drives stimulation? | yes | yes | **no — sensing only** |
| FFT size | **256 point** | **64 point** | 256 point |
| Spectrum update rate, adaptive / sensing-only | 5 Hz / 2 Hz | 20 Hz / 2 Hz | 2 Hz / 2 Hz |
| Averaging, adaptive / sensing-only | 1200 ms / 3000 ms | 100 ms / 1000 ms | 3000 ms / 3000 ms |
| Onset | 1200 ms | 200 ms | not applicable |
| **Blanking** | **2000 ms** | 550 ms | not applicable |
| Transition up / down | 2.5 min / 5 min | 250 ms / 250 ms | not applicable |
| Where the band may sit | 8 to 30 Hz | 8 to 30 Hz | 1 to 96 Hz (sensing) |
| Reaction | minutes | milliseconds | not applicable |

**The FFT size is the load-bearing field, not the timing.** The device's power reading is the sum
of squared spectrum magnitude over the sensed band, and bin width is the sampling rate divided by
the FFT size. So a 64-point spectrum integrates a **different set of frequency bins** than a
256-point one, and the same conversion constant cannot serve both.

- `CONVERSION_FFT_SIZE = 256` at `analytics.py:3389`.
- `COMPATIBLE_THRESHOLD_MODES` at `analytics.py:3390` resolves to **Dual and Single Inverse**.
- **Single Threshold, at 64 points, is not translatable** and the deployment path refuses to
  convert a microvolt-squared value into it. This is a guard, not an inconvenience.

**Two device behaviours worth stating on their own.**

1. **Under Dual Threshold the device blanks its own sensing for 2000 ms around a stimulation
   change.** This is a device-level reason not to trust signal measured immediately after a
   current change, and it is independent of any settling argument about the brain.
2. **The chronic record is averaged over 10 minutes while the crossing decision is made on 1200
   or 100 ms.** So a fast switching value cannot be validated against the chronic record alone.

### Polarity — the correction that matters

The white paper's "high power means low stimulation" is the **equilibrium correlation**, meaning
stimulation suppresses the biomarker. **It is not the control law.** The control law ramps
stimulation **up** when the power reading rises above the upper switching value. A biomarker whose
power **rises with pain** therefore maps directly onto Dual or Single adaptive mode with no sign
inversion — the inversion the Summit RC+S needed does not apply here.

### The assumption the device makes, and where it fails

**Percept adaptive mode assumes negative feedback: that delivering stimulation drives the
biomarker back across the switching value.** That holds for the Parkinson's beta band it was
designed around. For a pain biomarker it holds only if **stimulation actually moves that
biomarker**, not merely the pain. A biomarker that tracks the pain state but does not respond to
stimulation can leave the loop stuck on. That is why the three-state Dual configuration and the
blanking interval exist, and it is why offline emulation against the ambulatory record is required
before anything is programmed.

### The unresolved control problem on this record

**A band whose power rises with current and then falls breaks the two-point logic.** The device
places its switching value between two power readings. A band that rises to about 2.1 mA and then
falls satisfies the same switching value on **both sides of its peak** at different currents, so
the control law cannot tell "not enough stimulation" from "too much". This is measured, not
hypothetical: see §9. **It is an open decision for the PI**, recorded in
`DECISIONS_and_open_items.md`.

---

## 3. The recording products — what the device actually exports

Five products carry signal, plus the chronic record. **Verified against this participant's own
exported files.** The device's own power reading exists in the programmed products only.

| Product | JSON key | Raw voltage trace | Spectrum | Device's own power reading | Stimulation | Channels | Span |
|---|---|---|---|---|---|---|---|
| **Indefinite Streaming** | `IndefiniteStreaming` | yes, 250 samples/s | no | no | **off** | up to **6 at once** (0-3, 1-3, 0-2 each side) | about 280 s |
| **Montage Survey** | `LFPMontage`, with `LfpMontageTimeDomain` | yes | **yes, 0 to 96.7 Hz** | no | **off** | all 6 pairs per side, plus `PeakFrequencyInHertz` and `ArtifactStatus` | one shot |
| **BrainSense Streaming, on demand** | `BrainSenseLfp`, with `BrainSenseTimeDomain` | yes, 250 samples/s | derive it | **yes** | on or off | 1 to 2, the programmed band | about 100 to 500 s |
| **Events / snapshots** | `DiagnosticData.LfpFrequencySnapshotEvents[i]…[side].FFTBinData` | no | **yes, 0 to 96.7 Hz** | no | either | 1 per side | 30 s, beginning **30 s after** the button press |
| **Chronic record** | `DiagnosticData.LFPTrendLogs[side]` | no | no, in-band only | **yes** | either | 1, the programmed band | **600 s average**, up to about 35 days |

`BrainSenseSurveys` and `ElectrodeSurvey` are a related electrode-survey variant of the montage.

### What each product is for

- **Indefinite Streaming is the only product that records all six contacts at once, with
  stimulation off.** It is the broadest substrate for scanning frequency against pain, and it
  carries no pain label of its own.
- **The Montage Survey is the device's own opinion about which band matters**, plus quality
  control: it reports a peak frequency per contact and an artefact flag. Agreement between the
  platform's scan and the device's own peak is free corroboration; a contact the device flags is
  dropped.
- **Events are corroboration only.** Their spectrum feeds band discovery, where the time-locked
  label is their strength. **They never define the pain label and never set the switching
  value**, because they are noisy at the single-snapshot level (§4).
- **On-demand streaming is the calibration bridge.** It is the **only** product carrying the raw
  voltage trace and the device's own power reading for the same signal at the same time, which is
  why every conversion measured on simultaneous recordings was measured there.
- **The chronic record is where a deployed switching value is anchored**, because it is the only
  stream the device adapts on in the wild.

### Which discovery streams carry a full spectrum

The device's programmed power reading and the chronic record are **locked to the programmed
band**. But the on-demand stream's 250 samples per second voltage trace yields the whole
0 to 125 Hz spectrum, so **on-demand streaming is not band-locked for discovery** — a fact that
was confirmed on the exported files and that an earlier panel label got wrong. Together with the
event snapshots and the montage survey, three products expose a full spectrum, and **a band where
they agree is a high-confidence candidate.**

### The bonuses in the export that make the analysis possible

1. **The on-demand stream carries the delivered current per sample**, at about 2 samples per
   second, as `<CONTACT> Stimulation` columns beside `<CONTACT> Power`. So the current does not
   have to be inherited from a hand-written clinic sheet. **The decisive reason to prefer it is
   not availability but the clock: the device writes the current on the same clock as the power it
   reports, so a setting and the power measured during it cannot be misaligned by clock drift.**
2. **The chronic record carries `AmplitudeInMilliAmps` per trend point**, so stimulation can be
   tagged there too — but on-off within a cycling program must be forward-calculated from the
   cycling settings and the ramp. The streaming products need no such calculation.
3. **`TherapySnapshot` carries the full adaptive configuration** — the switching values, the
   averaging, the onset, the transitions, the active electrodes, and the sensing centre as
   `TherapySnapshot.{Left,Right}.FrequencyInHertz`.
4. **`EventName` confirms the scheduled-prompt protocol**: "Higher Pain", "High Pain", "Lower
   Pain", "Feeling Good", "Tingly/Burning" and others. The snapshot timestamp is the press plus
   30 s.

### The JSON keys, spelled exactly

**Every archived document referred to these by name.** The parser in
`modules/MedtronicPercept/` is authoritative; these are the spellings.

| Key or class name | What it holds |
|---|---|
| `BrainSenseTimeDomain` | the on-demand voltage trace, with `TimeDomainData`, `TicksInMses`, `GlobalSequences`, `GlobalPacketSizes`, `SampleRateInHz`, `FirstPacketDateTime`, `Channel` |
| `BrainSenseLfp` → `LfpData` | the device's own band power per point, each with `TicksInMs`, and per-side `<CONTACT> Power` and `<CONTACT> Stimulation` |
| `IndefiniteStreaming` | the stimulation-off six-contact voltage trace |
| `LFPMontage` → `LfpMontageTimeDomain` | the montage survey, with `PeakFrequencyInHertz`, `ArtifactStatus`, `SensingElectrodes` |
| `BrainSenseSurveys`, `ElectrodeSurvey` | the electrode-survey variant of the montage |
| `DiagnosticData.LfpFrequencySnapshotEvents[i][side].FFTBinData` | the patient-event spectrum, in linear microvolt magnitude, with `EventName`, `EventID`, `DateTime`, `Cycling` |
| `DiagnosticData.LFPTrendLogs[side]` | the chronic record, with `LFP` (the device's own power), `AmplitudeInMilliAmps`, `DateTime` |
| `TherapySnapshot.{Left,Right}` | the programmed configuration, with `FrequencyInHertz` (the sensing centre), the switching values, the timing and the active electrodes |
| `Groups`, `GroupHistory`, `TherapyHistory` | the therapy configuration over time |
| `StartTime`, `SessionDate`, `SamplingRate`, `SourceFile`, `ParticipantId`, `LeftHemisphere`, `RightHemisphere` | the platform's own decoded fields |
| `MedtronicBrainSenseTimeDomain`, `MedtronicIndefiniteStream`, `MedtronicBrainSenseSurvey`, `ChronicBrainSense`, `PatientControllerEvent`, `NeuralActivitySnapshot`, `TimeFrequencyAnalysis`, `TimeDomainRecordings` | the platform's recording-type labels, which is what decides at-home against in-clinic |

**`TIMEDOMAIN_TYPES` is the list of recording types that count as carrying a voltage trace.** A
filter that hardcodes one type instead silently drops the others.

**Montage channel labels differ from streaming labels** — the montage writes `ZERO_AND_THREE`
where streaming writes `ZERO_THREE`.

### Parsing traps in the exported files

1. **`TicksInMses` is a single comma-joined string, not an array.** So are `GlobalSequences` and
   `GlobalPacketSizes`. Meanwhile `TimeDomainData` is a real array and each power point's
   `TicksInMs` is a scalar integer. Reading the first as an array raises a conversion error on a
   string like `'840500,840750,…'`. Split on the comma when it is a string and treat it as an
   array otherwise.
2. **The tick clock needs a reversal correction**, already implemented in
   `modules/MedtronicPercept/Percept.py`. Reuse that parser rather than writing another.
3. **The device writes a sentinel for an invalid power reading.** The unsigned 32-bit maximum,
   4,294,967,295, means "invalid" and is not a measurement. Reject it.
4. **Montage channel labels differ from streaming labels** — the montage writes
   `ZERO_AND_THREE` where streaming writes `ZERO_THREE`. A filter written for one silently drops
   every record of the other; that mistake once dropped all 113 montage timestamps.

---

## 4. How precise each stream is, and why that answers the weighting question

Measured on this participant, left side, the band centred near 8.8 Hz. The precision available
from integration alone follows a coefficient of variation of about one over the square root of the
integration time multiplied by the bandwidth, with the bandwidth 5 Hz.

| Stream | Integration time | Time × bandwidth | Best possible spread | Spread observed |
|---|---|---|---|---|
| Chronic record | 600 s | 3000 | 1.8% | 32.5% |
| Events | 30 s | 150 | 8.2% | 62.4%, across pain states |
| On-demand streaming | 3 s | 15 | 25.8% | 30.8% |

**The observed spread exceeds the best possible spread everywhere, so what is being seen is real
physiological and pain-related fluctuation rather than measurement noise.** The chronic record's
10-minute averaging has already removed nearly all of the measurement noise.

**Why events corroborate rather than define.** The 62.4% figure is across pain states, so it
overstates the within-state noise — but the within-state spread is heterogeneous rather than
uniformly tight. **The largest pain class, with 26 snapshots, is at 60.4%**; "Feeling Good" is
32.8% and "Feeling Off" 56.3%. Only the small classes are tight (10 snapshots at 5.2%, 10 at
4.6%, 4 at 0%), and those may be a single session or a single burst, so they do not generalise.
**Events are therefore noisy at the single-snapshot level.** The pain label comes from the
patient-reported scores in REDCap.

**How the streams are weighted, which was the original open question.**

- For **discovery**, weight by integration time multiplied by bandwidth, so the chronic record
  dominates point stability.
- For **setting a switching value**, anchor to the **stream the device actually adapts on** — the
  chronic record, in the device's own units. On-demand streaming, at 1 to 3 s and closer to the
  device's own 1200 or 100 ms decision window, calibrates the expected crossing rate. Events
  corroborate the band choice and set nothing.
- The unifying form is a model with pain as a fixed effect on band power and the stream, the
  session, the sensing centre and the stimulation context as random effects, with a separate
  residual spread per stream.

---

## 5. The two different quantities both written "LSB", and why conflating them is expensive

**These are different physical quantities. They are not two estimates of one thing.**

1. **The time-domain sample scale: `ADC_NV_PER_LSB = 146.0` nanovolts per count**, at
   `analytics.py:3339`. **Exact**, per Medtronic. It converts one raw sample of the voltage trace
   into microvolts. It says nothing about power.
2. **The power-domain reading**, which the device reports as "LFP Power" in its own
   least-significant-bit units. This is the sum of squared spectrum magnitude over the sensed
   band, computed on board. **Its relationship to microvolts squared is normalisation-dependent
   and had to be measured.**

A tutorial figure of 146 nanovolts per count is sometimes quoted as if it resolved the second
quantity. It does not. The two are separated in the code and must stay separated in prose.

**The rule of thumb, and the warning that travels with it.** The Medtronic programming guide
prints roughly 0.01 microvolts squared per device unit. Two constants in this repository record
that figure — `LSB_RULE_OF_THUMB` at `bravo_service.py:4429` and `LFP_POWER_LSB_TO_UV2` at
`ClosedLoopDeployment/constraints.py:161` — and **neither is used by any production code path.**
The only reference to the second is one test asserting its value. **Reading it as a working
conversion is what once left the closed-loop page's numbers unscaled**, so it is recorded here as
a documentation fact and nothing else.

---

## 6. The calibrated conversions — from what, to what, measured or composed

**The PI's standing rule, 2026-09-06: every mention of a calibration states what it converts
from, what it converts to, which recipe produced its input, and whether it was measured on
simultaneous recordings of the same signal or composed by chaining other constants.** A constant
measured on genuinely simultaneous recordings is evidence. One obtained by chaining inherits both
its parents' errors.

| Constant | Value | From | To | Recipe behind the input | Measured or composed |
|---|---|---|---|---|---|
| `LSB_PER_UV2_TRANSFORM`<br>`analytics.py:3439` | **352.62** | band power in microvolts squared | the device's own power units | the transform recipe, §7 | **MEASURED**, on 131 simultaneous paired blocks |
| `LSB_PER_UV2_DEVICE_PSD_TD_RATIO`<br>`analytics.py:3476` | **4.789** | transform band power | device-spectrum band power | both, on the same signal | **MEASURED**, geometric mean, r = 0.987, n = 10,476 |
| `LSB_PER_DEVICE_PSD`<br>`analytics.py:3477` | **≈73.63** | the device's own onboard spectrum, summed in band | the device's own power units | `device_psd_band_power`, `analytics.py:3679` | **COMPOSED** — the code literally defines it as 352.62 ÷ 4.789 |
| `MODELED_LSB_SIGMA_FOLD`<br>`analytics.py:3409` | **1.26** | — | — | — | the one-standard-deviation multiplicative spread on a modelled estimate |

**The three constants are not independent.** 352.62 divided by 4.789 is 73.63 exactly, so the
device-spectrum route is composed from the voltage-trace route rather than calibrated against the
device separately. **It inherits both errors, and any agreement between those two routes is a
check on the conversion rather than replication of a physiological effect.**

### Where the conversion is checked, and where it is not

**Two frequency limits exist and they mean different things. Do not substitute one for the other.**

- **`LSB_VALIDATED_HZ_LO = 7.8` and `LSB_VALIDATED_HZ_HI = 28.3`**, at `analytics.py:3418-3419`.
  This is **where paired ground truth exists** — nine discrete sensing centres, being whatever
  the device happened to sense during this participant's streaming sessions. Outside it, any
  constant is untested extrapolation, and the code flags such an estimate.
- **`LSB_DEPLOYABLE_HZ_HI = 30.0`**, at `analytics.py:3448`. This is the **firmware's hard limit**
  on where an adaptive sensing band may sit.

**Using 30 Hz as the checked range claims a validation that was never run.** The code's own
comment says not to collapse them: 28.3 is a coverage fact, 30.0 is a device-capability fact.

Within the checked span the constant is approximately flat but not constant: it ranges from 258
to 317 device units per microvolt squared, a 1.23-fold span, with the trend against log frequency
positive but not significant (p = 0.17). **26.4 Hz sits at 317, about 18 percent above the pooled
value**, and 26.4 Hz is the most-sensed centre on this record — so a band near 26 Hz is both the
best covered and the furthest from the pooled constant. Below 8 Hz and above 28 Hz there is **no
paired ground truth at all**, so a high-gamma band would need its own streaming session to
calibrate. That is not clinically restrictive, because the adaptive modes are firmware-restricted
to 8 to 30 Hz and the checked span covers the actionable range almost exactly.

### Why the conversion barely matters for the exploration panels, and decides the deployment

The per-band feature is a **logarithm** of band power, so a multiplicative constant becomes an
additive offset and **cancels inside a correlation and inside an area under the curve.** Those
panels are numerically identical whether the constant is 269, 352.62 or 1. The constant matters
in exactly two places: **the absolute values displayed**, and **the deployable switching value.**

**The scope limit on that argument, and it is a real one.** Cancellation holds only when every
point in a single panel carries the **same** constant. A panel that pools the device's own
readings, which carry no constant, with modelled points, which carry 352.62, has two subgroups on
different scales, and moving one subgroup's constant shifts it relative to the other by the
logarithm of the ratio. **That can move both the correlation and the area under the curve.** The
code keeps the two apart: modelled points are masked out of the deployable switching value and
out of the measured-correlation path, and two named tests pin both halves.

### Why back-translation is unnecessary

An earlier recollection was that the spectrum had to be converted to a time series and then
forward-transformed. **It does not.** The device's power reading **is** the band integral of the
spectrum, and a band integral is phase-independent, so reconstructing a time series — which
requires inventing the phase — can neither add nor remove band-power information. Tested directly
on all 113 paired blocks: band power from a phase-randomised reconstruction matched the direct
integral to within 0.8 percent, with a median ratio of 1.008 and r = 0.999. **The composition is
spectrum, then band integral, then scale.**

---

## 7. The transform recipe, exactly as it must be computed

**Decided by the PI on 2026-06-27 and marked as having no open option.** This is the primary way
band power in the device's own units is computed, for **both** the exploration panels and the
deployment fallback. It is one recipe with one constant, not a second signal-processing chain to
maintain. The helper is `analytics.py:3655` `td_to_lsb`, over
`analytics.py:3515` `td_transform_band_power`.

Per one second of the voltage trace:

1. **Remove the mean** of the window.
2. **Apply the RC+S Hann taper** over one second of nonzero samples.
3. **Zero-pad to 256 points** and take the real FFT. `TRANSFORM_N_FFT = 256`,
   `TRANSFORM_WIN_SECONDS = 1.0`, `TRANSFORM_STEP_SECONDS = 0.5`, at `analytics.py:3502-3504`.
4. **Scale to peak amplitude.**
5. **Sum the squared magnitudes across the in-band frequency bins** — a sum over the roughly five
   bins inside the 5 Hz band, not a mean over them and not an integral of a density. Implemented as
   the band-mask multiplication at `analytics.py:3583`, and stated in the routine's own description
   as "band power = sum of squared magnitudes".
6. **Take the median across the sliding windows.** The reference reproduction slides the
   one-second window non-overlapping, one window per second. The deployed per-report sweep slides
   it at `TRANSFORM_STEP_SECONDS = 0.5`, so half-overlapping, across a roughly 30-second extent
   centred on the pain report, **and takes the median of the per-window band powers.** Overlapping
   only reduces the spread of the estimate; it does not change what is being estimated, so it stays
   inside the same calibration. A mean across windows is available and is not what is deployed.
7. **Multiply by 352.62.**

**A terminology clash that will otherwise cost someone an afternoon.** A shorthand comment beside
the constant describes this recipe as "mean-magnitude band power". **That phrase refers to step 6,
the aggregation across windows, not to step 5, the aggregation across frequency bins.** Across the
bins it is a sum. **Reading "mean" as the band-axis operation would average the roughly five
in-band bins instead of summing them, leaving every value low by about the bin count, and then
multiplying by 352.62 would not put it in the device's units.** Take the implementation and its
docstring as authoritative over the shorthand.

**Use 352.62 exactly. Do not round it to 353, and do not substitute the stimulation-off variant
356.61**, which is recorded for provenance only and is not deployed.

**A band named X Hz means X plus or minus 2.5 Hz, a total width of 5 Hz.** The stored grid is
already built at that half-width on a one-hertz centre grid — `_LSB_SPECTRUM_CENTERS` at
`bravo_service.py:755` gives **98 centres from 2.5 to 99.5 Hz** — so **a stored column named
12.5 Hz already is the band from 10.0 to 15.0 Hz.** Neighbouring columns must therefore **never
be summed or averaged** to build a 5 Hz band: they overlap heavily and combining them
double-counts the shared frequencies and inflates every value. Read the column and label its
span, and read the stored half-width rather than assuming it is 2.5.

**Finer time resolution costs nothing in calibration validity.** The recipe's native window is
**one second**; the 3-second tile is a median of three such values. So asking the same helper for
one value per second per centre, and multiplying by the same constant, stays inside the existing
calibration. `RAW_LSB_WINDOW_SECONDS = 3.0` at `analytics.py:3609` is the tile width, and **the
3-second choice is the PI's own arbitrary one**, taken because it was roughly equivalent to a
one-second step, not because the recordings require it. The floor is the 250 samples per second
sampling interval.

**But changing the recipe is not free.** Every constant in this project is specific to its recipe,
so values computed at a different window length are **not in the device's units** until their own
conversion is established. Compare against the 3-second tiles on the same recordings before
letting a different window feed anything downstream.

### The calibration's quality, and the diagnostic that is worth more than the number

Measured on **131 paired blocks** of this participant's Stage-1 recordings:

| Quantity | Value |
|---|---|
| Correlation | **r = 0.9927** |
| Root-mean-square error | 60.6 device units |
| Median fold error | **1.092** |
| Blocks within a factor of 1.5 | 93.9% |

**"Median fold error" is not a cross-validation quantity and the two senses of the word must not
be mixed.** Fold error is the multiplicative factor, the larger of predicted over observed and
observed over predicted, so it is always at least 1.0 and is symmetric: a two-fold over-prediction
and a two-fold under-prediction both score 2.0 and do not cancel. It is computable on a single fit
with no cross-validation at all. Always write "median fold error" in full.

**THE DIAGNOSTIC: if a pairing does not reproduce 352.62 with r = 0.9927, the pairing is wrong,
not the recipe.** Non-coincident pairing, or pairing against the wrong device product, collapses
the correlation to about **0.13**. This single check overturned an invented constant of about 215
that had been measured by pairing rows between two representations of the signal; its median fold
error was 2.70 against the calibration's 1.092, and by this diagnostic that meant the pairing was
wrong rather than that the device had a new constant.

### The pairing rules the calibration depends on

**Never match or try to predict any device power reading that does not come from an exactly
simultaneous voltage-trace recording.** The PI stated this explicitly.

- The target is the **on-demand stream's selected-band power reading**, paired one-to-one with
  **its own voltage trace** through the shared `FirstPacketDateTime`, with the channel set used to
  disambiguate. It is **not** the chronic record, which is a different product with a different
  normalisation and a different range: the chronic reading reached 10,660 and even the invalid
  sentinel, while the in-clinic reading tops out near 3,014.
- **A tolerant time window admits non-simultaneous pairs and destroys the correlation.** A ±10 s
  window pairs a voltage segment with a power reading from a different moment; when the power
  spikes but the matched voltage is from a calm moment, the resulting inversions collapse the fit.
- For alignment **within** a stream, use the shared device tick clock: voltage packets carry
  `TicksInMses` and each power point carries `TicksInMs`. Map sample index to milliseconds and
  select the power points falling inside the window.
- Gate on stimulation being off **per point**, and reject the invalid sentinel.
- **The unit of analysis is one record per report, per power stream, per side.** On this record
  that is **131 blocks**. Grouping by the contact instead collapses it to **26**, because a
  contact is reused across many separate sessions and grouping by it silently merges distinct
  streams. The block count is a property of the pairing, not of the signal processing.

### Which streams can be recorded at the same time, which decides what is measurable at all

- **The voltage trace and the device's own power reading are simultaneous** on on-demand
  streaming. They share `FirstPacketDateTime`, so every power block has a byte-identical voltage
  twin with no time-matching slop. On this record: 28 streaming sessions, **113 paired blocks**,
  52 of them with stimulation off, 50 surviving the fit filter.
- **The voltage trace and the device's own spectrum are simultaneous** on the montage survey.
- **The device's own spectrum and the device's own power reading are not.** Events and montage
  carry no power reading, and the chronic record and the on-demand reading cannot be paired
  point-to-point.

**OPEN QUESTION, and do not assert it either way without the device documentation: whether the
Percept RC can stream its own power reading and its own onboard spectrum simultaneously.** The PI
recalls it cannot, and that this is why the calibration was built by pairing the voltage trace
with each of the other two separately and then composing. Two pieces of indirect evidence are
consistent with that — a pain report in this codebase resolves to either the voltage-trace route
or the spectrum route and never both, verified as zero on all six channels; and the catalogued
first error of the calibration session was pairing a voltage trace against a non-simultaneous
power stream. **Neither is the documentation.** This decides which conversions are directly
measurable and which can only be composed.

---

## 8. Every recipe has its own constant — the catalogue, and what was removed

**Conflating two recipes' constants is catalogued as the third error of the calibration session.**
All of these were fitted in one session on the same 131 blocks, so **finding a new number for an
uncalibrated recipe is expected, not a discovery.**

| Recipe | Constant | Status today |
|---|---|---|
| Transform, all stimulation states | **352.62** | **live and primary** — `analytics.py:3439` |
| Transform, stimulation off only | 356.61 | provenance only, never deployed |
| Welch, 256 samples per segment | 270.22 | **REMOVED** from the code on 2026-06-28, commit `fa2c416` |
| Welch, 250 samples per segment | 265.17 | never in the code |
| Per-window 3-second variant | 326 | not deployed; r on logarithms 0.82, median fold error 1.36 |
| The device's own onboard spectrum | **73.63** | **live** — composed, `analytics.py:3477` |

**About the removal, because an archived document still describes the removed constant as
current.** `LSB_PER_UV2_VALIDATED = 269` was the Welch-256 constant. It was demoted to a
spectrum-to-device-units backup and then **deleted outright on 2026-06-28**, together with the
helpers `psd_band_to_lsb` and `welch256_density`. Verified this session: `analytics.py:3401-3403`
carries only a comment recording the removal, and no definition survives anywhere.
**The archived calibration handoff's §3.2 describes a Welch-256 backup that no longer exists.**
The surviving backup is the device-spectrum route at 73.63.

**The deployment fallback also changed, and the reason is a units error worth remembering.** An
earlier design converted the switching value through a frozen per-participant model. **That was
wrong: the switching value is a z-scored logarithm of power, not a linear microvolts squared, so
a value at or below zero came out as a device reading near zero.** The live path is
`availability.py:705` `modeled_lsb_at_center`, which models the device's power line off the raw
voltage trace at the switching value's own centre frequency and anchors by rank, with no
conversion of the switching value at all. The frozen model remains a real asset for its own
conversion panel; **it is no longer the deployment fallback.**

### The invariant that protects the deployed number

**The device's own reading is strictly preferred, and a modelled value never sets the number.**

- On the timeline, modelled points are drawn as hollow diamonds, held out of the axis scaler so a
  modelled outlier cannot rescale the sensed trace, and held out of the chronic line.
- In the deployment path, the modelled tier is a fallback used only when the band was never
  natively sensed. **The switching value stays anchored on a percentile of the device's own
  chronic reading**, and it is never reassigned from a modelled value when a native one exists.
- **The absolute conversion constant never sets the deployed number**, precisely because it is
  normalisation-dependent. It is used only when the device never sensed the band and there is
  therefore no anchor, and then it is flagged with its 1.26-fold one-standard-deviation spread
  and a note to confirm live before deploying.

### How thin the native coverage is, which is the real limit here

Measured on this participant. The voltage-trace route holds tens of thousands of 3-second tiles
per sensing contact; **the device's own power reading holds only a few hundred windows each.**

| Sensing contact | 3-second tiles, voltage-trace route | Windows, device's own reading |
|---|---|---|
| ZERO_THREE_RIGHT | 62,784 | 797 |
| ONE_THREE_LEFT | 49,267 | 384 |
| ZERO_THREE_LEFT | 45,586 | 258 |
| ZERO_TWO_LEFT | 44,277 | 294 |
| ZERO_TWO_RIGHT | 43,558 | 251 |
| ONE_THREE_RIGHT | 43,444 | 282 |

**A native reading exists for well under 2 percent of the record**, so almost every value must
come from the calibrated model of what the device would have reported. **That matters most for
the one operation where the absolute scale is load-bearing — setting a switching value in the
device's own units — and it is exactly where the modelled route is weakest.**

The most-sensed centre is **26.4 Hz, in 145 paired blocks**, then 8.8 (53), 9.8 (44), 7.8 (38),
28.3 (33), 10.7 (21), 24.4 (18) and 11.7 (10). So a band near 26 Hz has real device-reported
power rather than only a modelled estimate.

### The device's own reading saturates, and this is the failure mode of using it as truth

**About 1 percent of simultaneous windows are device-side saturation events**, where the device's
power reading jumps to ten thousand or a hundred thousand while the simultaneous voltage trace
stays flat. Taking a median over a block absorbs them; a per-window analysis does not.

**These are exactly the false spikes a detector keyed on the device's own reading would fire on.**
The advisory quality-control flag is the count and rate of readings above a per-channel
physiologic ceiling — above the channel's own stimulation-off 99th percentile, or above roughly
3,000 for the in-clinic reading. It is advisory and does not drop anything automatically, but it
tells a clinician how artefact-prone a candidate band is before deployment. `PRO_LSB_SATURATION_UV
= 4000.0` at `availability.py:845` is the separate saturation gate on the voltage side.

**This is why the ground-truth rule decided on 2026-09-07 makes the device's own reading truth
only after its ceiling check passes.** See `DECISIONS_and_open_items.md`.

---

## 9. Stimulation, and the things about it that are device facts

### Where the stimulator reappears in the spectrum

At 250 samples per second, multiples of the stimulation rate fold back below the Nyquist limit
and land inside the analysis range. Computed by `analytics.py:5884` `harmonic_landings_hz`, with
`DEVICE_TD_FS_HZ = 250.0` at `analytics.py:5853`. Landings inside 5 to 32.5 Hz:

| Rate | Where it lands | The 23 to 27 Hz candidate range |
|---|---|---|
| **55 Hz** | 5, 25, 30 Hz | **lands inside it** |
| 60 Hz | 10, 20 Hz | clean |
| 110 Hz | 10, 20, 30 Hz | clean |
| 130 Hz | 10, 20, 30 Hz | clean |
| **145 Hz** | 15, 25 Hz | **lands inside it** |
| 165 Hz | 5, 10, 15 Hz | clean |

**The consequence the PI reached independently: 60 Hz is a better control for 55 Hz than 110 Hz
is**, because 110 Hz also changes the rate by a factor of two, while 60 Hz changes almost nothing
except where the stimulator lands.

At 55 Hz the landings contaminate 33 of the 98 bands, including eight centres from 22.5 to
29.5 Hz **inside the adaptive range**. On one visit the two bands containing 55 Hz itself reached
7,544 and 23,121 device units — **the stimulator, not the brain** — and before those bands were
marked, the largest apparent effect on a heat map of this record reached 45,506 device units and
18.2 times its starting value and looked like a spectacular biomarker.

**But the marking means only that a folded landing lies inside the band.** It is a label, not a
verdict, and the stronger inference was tried and refuted — see
`METHODS_measurement_and_findings.md`.

### How long the current takes to arrive

Measured across **all 326 amplitude steps on 24 visit days**, from the device's own current record
at 2 samples per second.

| Quantity | Value |
|---|---|
| Median ramp | **2.0 s** |
| 90th percentile | 17.0 s |
| Longest | **75.0 s** |

**Duration tracks how many small increments the device chose, not the current stepped to**:
r = +0.69 (p = 0.0001) against the increment count, versus r = +0.33 (p = 0.108) against the
amplitude. By increment count: 1 increment (139 steps) gives 0.0 s, 5 increments (60 steps) give
9.0 s, 16 give 32.5 s, 30 give 62.5 s, and 35 increments (12 steps) give a median of 50.0 s and a
maximum of 75.0 s.

**So the clinic sheet's printed "30 to 45 seconds to ramp up" is too long for small steps and too
short for long multi-increment ramps**, which is why the analysis measures the ramp per step from
the device's own record rather than assuming a fixed exclusion. `RAMP_EXCLUDE_S = 20.0` at
`StimOptimizer/routines/within_visit.py:67` is the flat margin added after the measured ramp.

**Two regimes exist in the record and one of them has no ramp to measure.** Clinic step ladders
use a median of 4 increments and 35 at most. In at-home recordings the current never holds still,
and a rule that collapsed consecutive changes into one reported ramp produced ramps of up to
615 s — arithmetically true and meaningless as a description. Those blocks are now **refused with
an explicit error** rather than described, because an empty result cannot be told apart from a
block whose current never moved.

### The device's log stops when streaming stops

This shortens runs rather than lengthening them. On 2026-08-18 the clinician kept stepping the
right side to 3.0 mA but streaming ended after 2.0 mA, so the reported run ends at 2.0 mA. Nothing
is lost, because the voltage trace is the same session and stopped at the same moment. **A run is
never joined across such a gap.**

### The clinic sheet against the device's own record

Cross-checked on 2026-08-18 across the eleven settings of the two single-side runs: **the two
agree on every setting and its order**, but the moment each setting begins differs by −4 s to
+22 s on the device's clock, with a median of +6 s, **in both directions** — so it is spread
rather than a correctable offset. It is small against the roughly 60 s holds and against a 30 s
window taken from the end of each setting, so it moves no reported number.

**The parsed clinic sheets are not an input to the running platform.** There is no Sheets access
anywhere in the codebase; they were parsed offline and live only in the analysis folder, and three
code comments state the server has no copy. At-home versus in-clinic is decided from the Medtronic
recording type, not from any sheet.

### Stimulation context changes across the record

The active contact, the stimulation rate and the amplitude all changed over the trial's history.
The volume of tissue activated and the artefact spectrum differ, so **a sample recorded under one
therapy configuration is not interchangeable with one recorded under another at the same
milliamps.** Reconstruct the configuration per epoch from `Groups`, `GroupHistory` and
`TherapySnapshot`, then either standardise within configuration or restrict the switching value to
stimulation-off samples and carry the configuration as a modelled covariate. **Whether the remote
past needs correcting at all is empirically testable — does the biomarker's separation differ by
era? — and should be tested rather than assumed.**

---

## 10. The frozen per-participant conversion model — keep these numbers verbatim

`BRAVO/modules/Biomarkers/data/psd_lsb_models/RCS08.json`, schema `psd_lsb_conversion/v1`,
generated 2026-06-25. **It is a frozen asset: loaded, never refitted on request**, so the reviewed
cleaning decisions stay fixed. **These figures are marked sacred in the archived record and are
reproduced here unchanged.**

**Form, per channel:** the base-ten logarithm of the device reading equals a per-frequency
intercept plus a per-channel common slope times the base-ten logarithm of microvolts squared. The
on-board power gain falls as sensing frequency rises, and **that frequency dependence lives
entirely in the intercept, not in the slope** — per-frequency slope differences are statistically
unsupported. The frequency effect is a gain shift, not a slope change.

**What is baked into the freeze:** the nearest device reading per offline spectrum epoch, each
spectrum used once per channel; a ±30 minute match window; fixed 10-minute bin averaging; robust
outlier omission per band on the logarithm of the ratio; and a hard floor of at least 6 per band.
The fit basis is 685 clusters with 33 outliers excluded.

| Channel | Fittable | Common slope | R² | Pooled constant | Clusters |
|---|---|---|---|---|---|
| **ZERO_THREE_RIGHT** | yes | **0.8545** | **0.841** | 81.35 | 524 |
| **ZERO_THREE_LEFT** | yes | 0.5164 | 0.253 | 278.76 | 81 |
| ONE_THREE_LEFT | no | — | — | 198.67, pooled only | 28 |
| ZERO_TWO_RIGHT | no | — | — | 646.27, pooled only | 9 |
| ZERO_TWO_LEFT | no | — | — | 333.98, pooled only | 8 |
| ONE_THREE_RIGHT | no | — | — | **none** | 2 |

**Per-band intercepts for ZERO_THREE_RIGHT**, the deployed channel of record:

| Centre | n | Intercept | Interval | Device reading at 1 µV² |
|---|---|---|---|---|
| **8.8** | 42 | **1.7695** | 1.7152 to 1.8452 | 58.8 |
| 9.8 | 40 | 2.5995 | 2.4604 to 2.6808 | 397.7 |
| 10.7 | 13 | 2.5841 | 2.5527 to 2.7342 | 383.8 |
| 11.7 | 8 | 2.5673 | 2.5386 to 2.6214 | 369.3 |
| 24.4 | 37 | 1.9275 | 1.9140 to 1.9403 | 84.6 |
| 26.4 | 202 | 1.8544 | 1.8356 to 1.8675 | 71.5 |

ZERO_THREE_LEFT fits bands at 8.8, 9.8, 10.7, 11.7 and 22.5 Hz, but at R² = 0.25 and mostly from
streaming-only readings — treat it as unreliable.

**The two frozen exclusions, and the reasoning behind the first one is worth keeping.**

1. **ZERO_THREE_RIGHT at 8.8 Hz is restricted to on or after 2026-03-01.** Chronic sensing on that
   contact was reassigned off 8.8 Hz on 2025-12-05, then moved across 28, 24.4 and 26.4 Hz before
   settling. The 8.8 Hz gain falls through a **settling transient** over December to February
   (within-regime trend −0.078 per month in the logarithm, p = 0.039) and only reaches
   stationarity from about 2026-02-15 (p rising to 0.91 by 03-01). **Using the configuration-change
   date instead would inject the higher-gain declining transient and bias the deployable switching
   value.**
2. **ZERO_THREE_RIGHT at 23.4 Hz is excluded** as noisy and inconsistent with its 24.4 and 26.4 Hz
   neighbours.

**An impedance term of 1.02 was tested and rejected.** It was significant only under a naive fit,
because 2,985 epochs share 230 impedance measurements; with a cluster-robust standard error it is
not significant (p = 0.26). It is a slow-time proxy rather than a physical gain, and its effect on
the switching value, 1.22-fold, is smaller than the model's own spread. **The frozen fit is
unchanged.**

---

## 11. Where the pain label comes from, and what it is not

**The label is defined by the patient-reported scores in REDCap**, never by the device's own event
snapshots. Six metrics are selectable: the numeric rating scale, the visual analogue scale, two
region-specific visual analogue scales, the McGill questionnaire total, and a composite of the
McGill total with the left-leg visual analogue scale formed by standardising each part and
averaging whichever are available. Resolved at `bravo_service.py:280-289`.

Every candidate is stamped with which metric and which split it was built against, **so two
candidates are comparable only within the same metric.**

**The timestamp trap, and it is the kind that silently smears every match.** The REDCap field
`date_time_s1_daily` is **California local wall-clock time, not universal time**, while the
device's start times are already universal. Parsing the pain report as universal time smears
every match by seven to eight hours. Always convert through
`bravo_service._pro_timestamps_utc`, which handles daylight saving.

**Pain reports are filed continuously, and this governs how they may be cached.** They are fetched
fresh on every request and matched live. A cache of them that outlived a request would eventually
serve an analysis silently missing the newest reports, **with every correlation and every verdict
wrong while the page looked completely normal.** A cross-request cache was made conditional on
finding a freshness check cheaper than the fetch; measured twice on the live record, **there is
none** — the record-edit-log check costs the same few tenths of a second as an outright fresh
narrowed fetch. The speedup came from asking REDCap for fewer columns, not from remembering
anything.

---

## 12. The interface between the two modules

The biomarker module owns discovery, committing to a band, and setting a switching value. It emits
**one serializable band-candidate object**, and the closed-loop module consumes it. The full schema
is in the design ledger, artifact `f9b3d791-7e95-44bb-bd81-8aebcf9e1b3b`. The rules the schema
encodes:

1. **The pain metric and its split are first-class fields**, so candidates compare only within the
   same label.
2. **Event snapshots appear only under corroboration** — never in the label and never in the
   switching value.
3. **The switching value is carried in the deployment stream's own units**, so it can be typed
   into the tablet.
4. **The conversion check is advisory and confidence-rated, never a silent calibration.**
5. **The selection-bias flag is hard-coded true** until a balanced candidate pool exists. The pool
   is non-uniform by construction: intuition favoured the right 0-3 contact near 26.4 Hz, so more
   signal exists there, and the right 0-3 contact has four times the coverage of the left. **The
   schema refuses to pretend the candidate set is unbiased.**
6. **A validity flag gates whether a candidate can run adaptive at all**, against the 8 to 30 Hz
   firmware limit, and carries the reason when it cannot.

---

## 13. Reference papers

- **The trial, medRxiv 2025.08.11.25333010** — deployed on the **Summit RC+S**, one power channel
  and one switching value, a sign that could be inverted, onset and offset from offline emulation,
  and a second classifier to deactivate during sleep.
- **Frontiers in Neuroscience, fnins.2021.762097, Prosky and Shirvalkar** — the closed-loop
  principles: onset, termination, blanking and ramp; setting the switching value by percentile;
  negative feedback to avoid a stuck-on loop; and that zero milliamps is not the same as
  stimulation off.
- **Journal of Neural Engineering, ad1dc3** — the Percept signal-processing tutorial: the 146
  nanovolt per count time-domain scale, the filter response, and aliasing. **It explains why the
  absolute power conversion is normalisation-dependent**, and it is the source of the figure that
  is repeatedly mistaken for a power conversion.
- **Nature Neuroscience 2023, 26(5):1090-1099, PMID 37217725, Shirvalkar and colleagues** — the
  first-in-human prediction of a chronic pain state from intracranial signal.
