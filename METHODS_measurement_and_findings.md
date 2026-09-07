# How the measurements are made, what has been found, and the limit on each finding

**This document replaces the statistics, methods and results content of the mega handoff, the
design ledger, the session handoffs, the audit reports and the two validation reports.** Where
those disagreed, the newer result was taken; each resolution is recorded in
`.planning/2026-09-06-cache-store-and-record-consolidation/findings.md` §1.

**Two standing rules from the PI govern every statement in this document.**

1. **A claim about a result appears only where the result itself appears.** No anticipatory
   phrasing, and no assertion about a check that was not run.
2. **Never conclude that a band does not respond to stimulation from a narrow range of tested
   currents.** State instead the smallest movement the design could have detected, and how many
   currents were tested and over what range.

---

## 1. How a band power measurement is defined

**A band named X Hz means X plus or minus 2.5 Hz, a total width of 5 Hz.** The PI's rule of
2026-09-06: *"the band centers should reflect plus or minus 2.5 Hz for a total 5 Hz band centered
at the frequency that it is named for."* Set at `availability.py:706`, `848`, `1008` and `1158` as
`band_half_hz=2.5`.

**A stored column named 12.5 Hz already is the band from 10.0 to 15.0 Hz.** So neighbouring
columns must **never be summed or averaged** to build a 5 Hz band — they overlap heavily, and
combining them double-counts the shared frequencies and inflates every value. Read the column,
label its span, and read the stored half-width rather than assuming it.

The grid is 98 centres from 2.5 to 99.5 Hz on a one-hertz spacing. The 22 centres used for the
biomarker work are 8.5 to 29.5 Hz, **read from the store's own centre list rather than a hardcoded
range, so a centre with no measurements behind it cannot appear.**

**The length asked for is not always the length delivered, and both travel with every row.** A
band power measurement is built from whole 3-second pieces, so five of the ten candidate lengths
cannot be delivered exactly: 1 becomes 3 s, 5 becomes 6 s, 10 becomes 9 s, 20 becomes 21 s, 25
becomes 24 s. **Labelling the shortest row "1 s" would misstate it threefold.**

---

## 2. Matching a pain report to a recording

**Two windows, and they do different jobs.** Decided by the PI on 2026-06-28.

1. **The eligibility radius** — the main tolerance slider, `MatchToleranceMin`, in minutes —
   decides which recordings are near enough in time to a pain report to be considered at all. It
   applies to both the voltage-trace route and the spectrum route. **The frontend sends 60 minutes
   by default; the backend has no default and refuses a request without the field**
   (`bravo_service.py:3295`).
2. **The length of signal** — `MatchExtentSec`, 3 to 300 s, default 30 s — caps how much recording
   goes into one band power measurement.

**One recording matches at most one pain report** by default, so pieces of signal are not reused
across reports. `AllowWindowReuse` trades that independence for sample size and is off by default.
Within the eligibility radius, an unclaimed voltage trace is always preferred over a closer
spectrum, because the voltage trace is the calibrated route.

**Two pain reports filed at the identical second are partitioned between neighbours rather than
double-counted.** The search compares a piece of recording against its two neighbours in time, and
two identical times are one neighbour twice. **This record contains such pairs**, so the rule is
load-bearing rather than defensive.

**One section of the exploration page deliberately ignores the length-of-signal slider**, because
sweeping that length is the whole point of it. Stated in the code at
`bravo_service.py:6075-6077`. **A reader who moves the slider and sees that section unchanged
would otherwise reasonably think something was broken.**

---

## 3. Correcting for having chosen — two different corrections for two different questions

**One method described as the method is the inaccurate picture, and an archived README made
exactly that error.**

**The older spectral scan corrects with Benjamini-Hochberg.** `bh_fdr` at `stats_utils.py:20`,
called at `analytics.py:944`, `947` and `954`, and at `pipeline.py:576` and `844`.

**The band-by-length sweep corrects for selection over lengths by permutation instead.** For each
band the pain scores are shuffled, the same best-of-ten-lengths search is rerun, and the 95th
percentile of the shuffled best is the reference. Keys at `analytics.py:6866` and `7204`; the
verdict constant at `4871`.

**Why the second correction exists: a false-discovery q-value does not account for having taken
the maximum over ten correlated integration times.** It is a stricter and differently shaped
correction, for a differently shaped question.

**The reported best-of-ten is optimistic by construction, and the sweep says so on its own face.**
Measured on this record: the median gap between the best of ten lengths and the median of the ten
is **0.088 in correlation and 0.081 in discrimination**, so that is roughly what taking the
maximum buys before any real effect. Every row carries the median across lengths beside the best,
and the count of lengths that individually clear the reference. **A band whose best clears while
one of ten lengths clears is a different object from a band where eight of ten clear.**

**A discrimination value is compared against 0.5, never against 0.** And the unfolded value is
what the grid reports: on the live record it spans 0.208 to 0.787 while the folded version bottoms
out at 0.516. **For a folded value 0.5 is a lower bound rather than a neutral middle**, which is
why the two cannot share a colour scale.

**A gate on a discrimination value above 0.60 does not exist** anywhere in the biomarker path,
though an archived README described one. Verified: the only surviving 0.60 is a separation
threshold in a different pipeline at `pipeline.py:1475`.

---

## 4. Independence, and how much of it there is

Pieces of signal three seconds apart are not independent. The effective count is estimated from
the autocorrelation of the series, and the reference distribution is built by moving blocks of that
length rather than by shuffling single pieces. Implemented in `stats_utils.py`.

**Statistical rigour rules for this project.** Use the established implementation with its
conventional settings rather than writing the routine again. Where repeated measurements come from
the same visit day, the same session or the same contact, the standard error must account for the
grouping — a naive fit that treats 2,985 measurements sharing 230 underlying values as 2,985
independent observations produces a significant result from nothing, and that exact error is why
an impedance term was rejected from the frozen conversion model (p = 0.26 once clustered, against
significance when naive).

---

## 5. What has been found on RCS08, and the limit on each finding

**Every figure below is from a run on the live record. No figure here is carried from an earlier
document without its limit.**

### The band-by-length sweep

Twenty-two centres against ten candidate lengths, the **full 220-cell grid returned** rather than
only the best cell per band, because the shape of the surface is what was asked for. Across the
grid, correlation runs **−0.516 to +0.223** and discrimination **0.208 to 0.787**.

### The amplitude response, and the shape that matters

Measured within visits, from the device's own current record, with the window taken from the
settled part of each held setting and the look-back clipped at the measured ramp.

- **The bands from 25 to 28 Hz rise with current and then fall**, curvature p between 0.014 and
  0.025, peaking near 2.1 mA.
- **The peak position drifts smoothly with frequency**: 2.120, 2.089, 2.071 and 2.063 mA across
  25, 26, 27 and 28 Hz.
- At 27 Hz **a straight line explains 10 percent of the variation and a curve explains 76
  percent.**

**Why this is not the stimulator, and this was the PI's argument.** A stimulation artefact grows
with current and keeps growing. On the same visit **the bands containing 55 Hz itself rise
monotonically to 18.2 times their starting value** — that is what the stimulator looks like — while
these bands come back down. A folded landing sits at one frequency, 25.0 Hz, **and cannot produce a
peak that moves across four frequencies.** And the apparent clean split of curvature along the
landings turned out to be a 0.05 cutoff crossing a smooth gradient, not a categorical divider.

**So the landing flag means only that a folded multiple lies inside the band and its amplitude
response deserves care. Nothing stronger.** The earlier wording calling such a band
"stimulator-contaminated" was rejected by the PI and the inference behind it is not carried.

**The decision this raises is the one that matters, and it is open.** The device places its
switching value between two power readings. **A band that rises to about 2.1 mA and then falls
satisfies the same switching value on both sides of its peak, so the control law cannot tell "not
enough stimulation" from "too much".** Open: fit one straight line across 1 to 4.8 mA, or something
admitting curvature? **The earlier retraction of the 55 Hz candidate does not settle this** — it
was a statement about a straight line, a linear test has almost no power against a rise-then-fall,
and a curvature test on the one clean day gives p = 0.125. **Neither is significant, and both rest
on 8 steps from a single visit day.**

### Attributing an effect to one side

**Of six visit days with 55 Hz recordings on the left 1-3 contact, exactly one has the right
stimulator held at zero** (2026-08-18, 8 steps). The other five ramped both sides together, so
nothing on them can be attributed to the left current. **There is no cross-day replication at 55 Hz
at all.** At 110 Hz two of three days have the right side at exactly 0.0 mA, which is why that rate
is the one with a replicated result. **This is a protocol gap, not an analysis choice.**

**The pooled correlation is not the evidence.** An earlier claim that a pooled figure of −0.11
licensed the left attribution at 110 Hz was superseded: the basis is the two clean days, and
pooling them with a lockstep day produces a low number partly by cancellation. Dropping the
confounded day moved the family-wise result from **p = 0.330 to p = 0.064.** Still not called
established.

**One pre-registered figure cannot be side-attributed at all**: on 2025-08-21 the two sides'
currents correlate at 1.0 and the longest single-side stretch is zero steps. **That figure must be
replaced rather than re-rendered**, because no version of it can support a claim about one side.

### Two windows that fail for opposite reasons

Measured across all 18 bands of the best 55 Hz configuration. Over the full record of eight
stimulation epochs, the direction check fails in **all 18** bands while the separation clears any
plausible requirement, 1.01 to 4.88. Over the five most recent epochs, the direction check passes
in **15 of 18** but separation collapses to 0.41 to 0.93. **So the long window fails on direction
and the short window fails on separation, and neither yields a deployable configuration.** Relaxing
the separation requirement to 0.5 does not rescue the short window: only 4 of 18 bands reach even
that, and those four have p between 0.07 and 0.35.

### The stability conclusion is reported with four values and no pass-or-fail

The routine returns four values and **no true-or-false about its own conclusion**; the only
true-or-false key reports whether the test ran at all. The reason is a collapse on this
participant's own record, where a two-valued flag read as a pass **because the test failed to
reject**, while the interval on the largest difference was far wider than the declared margin.
**A gate that goes green on absence of evidence is unsafe for a readiness claim.**

---

## 6. The three-source comparison of how current moves band power

Three ways to reach the same quantity, rendered side by side per band and per setting.

| Source | What it is | Coverage |
|---|---|---|
| **The voltage trace, calibrated** | 250 samples per second, transform recipe, times 352.62 | all 98 bands, tens of thousands of windows |
| **The device's own spectrum, composed** | the onboard spectrum summed in band, times 73.63 | all 98 bands in principle; **zero windows in every rendered current ladder** |
| **The device's own band power** | native device units, no conversion | **the single programmed band only**, a few hundred windows |

**The five honesty constraints, all five accepted by the PI on 2026-09-06.**

1. **The three sources are not independent.** The device computes its own reading on board from the
   same signal the voltage trace records, and the composed constant is literally 352.62 ÷ 4.789. **So
   agreement between them is a check on the conversion, never replication of a physiological
   effect.** Every figure says so.
2. **The middle source is empty during current ladders, and that is a protocol fact.** The device
   computes its own spectrum only on a patient button press or a contact survey with stimulation
   off, and neither happens during a ladder. **Populating it needs a button press at each held
   setting, which is a visit-protocol change and not a code change.** The column is drawn empty
   rather than hidden, so the gap is visible.
3. **The bottom row is restricted to 7.5 to 30 Hz**, for two reasons. Nothing above 30 Hz can be
   acted on. And the full spectrum will not fit on one linear axis: across four rendered runs the
   whole-spectrum span ran from 4,616-fold to 4,242,165-fold, while the same values inside the drawn
   range spanned only 4.4-fold to 10.7-fold.
4. **The ladder of currents is read from the device's own record, not from the clinic sheet**,
   because the device writes the current on the same clock as the power it reports.
5. **The panel gates nothing.** It is a comparison, and no verdict anywhere depends on it.

### The ground-truth rule — decided 2026-09-07

**The PI left this open on the ground that it is a scientific choice rather than an engineering
one.** Decided as follows. The precedence:

1. **The device's own band power is ground truth wherever it exists and passes its ceiling check**,
   because it is the exact quantity the control law compares against a switching value typed in
   those units. Anything else is an estimate of it.
2. **The calibrated voltage-trace route** where the device's own reading does not exist. Its
   constant was measured on 131 genuinely simultaneous paired recordings, r = 0.9927.
3. **The device's own spectrum route ranks below the voltage-trace route, not above it**, and is
   tagged as composed rather than measured, because its constant was obtained by chaining and
   inherits both errors. It is kept for the one case where a pain report has a spectrum snapshot
   nearby and no voltage trace.
4. **Never** the route that exponentiates an assembled decibel density and integrates it with no
   scale factor. That recipe was never calibrated.

**The four conditions, which the proposal lacked.**

1. **The device's own reading counts as ground truth only after a per-channel saturation ceiling
   check.** About 1 percent of simultaneous windows are device-side spikes where the reading jumps
   to ten thousand or a hundred thousand while the simultaneous voltage trace stays flat. **A rule
   that adopts the unfiltered reading adopts those spikes as truth**, and they are exactly what a
   detector keyed on that stream would misfire on. Failing windows are excluded **and counted**, and
   a setting left with too few falls through to the voltage-trace route with that reason recorded.
2. **Where both routes exist for the same band and setting, both values and the fold ratio between
   them are written.** The device reading wins the ground-truth field, but **that ratio is the
   platform's only continuous check on whether the calibration serving the other 97 bands still
   holds.** On the two runs where both existed the two agreed to within 1.10 and 1.39 fold.
3. **The one-band coverage must never read as coverage.** Every row carries its route and its window
   count, and the exploration queue can be sorted by route as well as by effect size, because **a
   band whose only evidence is the modelled route is a band where more device-native measurement is
   the most valuable clinic time available.**
4. **The checked conversion span is stated on every row.** The voltage-trace calibration is checked
   only from 7.8 to 28.3 Hz; outside it the route extrapolates and the row says so. The 30 Hz figure
   is the firmware's adaptive limit and is a different number.

**The honest limit on this record.** On the 2026-08-18 visit this rule yields ground truth for
exactly one band per side — 23.44 Hz left and 7.81 Hz right — and the right side's nearest stored
band at 7.5 Hz falls outside the checked span. **The rule is defensible and thin, and the thinness
is a protocol gap rather than a flaw in the rule.**

---

## 7. What must never be claimed

1. **Never conclude a band does not respond to stimulation from a narrow range of tested
   currents.** Two separate statements were once collapsed into one. Testing currents that sit close
   together and observing little movement supports only *"no movement was detectable across the
   currents we tested"*. **State the smallest movement the design could have detected, and the
   number and range of currents tested.**
2. **Never call a result established on one visit day.** Eight steps from a single day is the basis
   of both the curvature result and its retraction, and neither is significant.
3. **Never present a figure that pools both stimulators' currents as evidence about one side.**
4. **Never quote a test-suite count without a traceable run behind it.** Counts in the archived
   documents went stale within single sessions, and one reached a pushed commit message that cannot
   be edited.
5. **Never state that an area under a curve is above chance by comparing it to zero.** The
   no-discrimination reference is 0.5.
6. **Never mix the two senses of "fold".** Fold error is a multiplicative factor, always at least
   1.0, computable on a single fit with no cross-validation. Write "median fold error" in full.
7. **Never describe the composed conversion constant as measured.** Say composed, and name what it
   was composed from.
8. **A test whose name asserts something untrue is worse than no test.** When a calculation is
   removed, split the test rather than relabelling its assertion.

---

## 8. The pre-registration

A pre-registration is on file for the amplitude-response work, and **one amendment has been
filed**: an earlier version labelled the brain side wrongly, and the correction was recorded as an
amendment rather than by editing the original. **That is the required handling** — the filed
document is the record, and a silent edit destroys what pre-registration is for.
