# S6 and S7 of the 2026-09-15 review, measured on RCS08 (2026-09-17)

Both are measurements the PI asked for, not changes to the platform. Probes: `BRAVO/_agent_bridge/_s6_duration_weight.py`,
`_s7_margin_sweep.py`, `_s7_transient.py`, `_s7_plot.py` (gitignored scratch). Figures and the slope table:
`artifacts/figures_2026-09-17_s7_margin/`.

## S6 -- weighting a rating by how long its setting was held

**What the noise model does today.** Each epoch's variance is `s²/n + 0.25·max(0, 1 − hold/ref)² + age term`, with
`ref` = one week. The 259 clinic-stream epochs are held 10 s to 10,470 s (median 70 s), so at a one-week reference
the duration penalty is at its maximum (0.97–1.00) on every one of them: a 10-minute step and a 60 s step carry the
same weight. The REDCap stream's epochs are held hours to weeks, where the term does discriminate.

**What changes when the reference is shortened, or the term is switched off** (the whole two-stage request re-run,
stored answer bypassed; the clinic stream's three fitted strata; the recommendation on every row stays "none"):

| reference | 55 Hz 60/160 µs (24 epochs): best cell, score, not-flat range vs scatter, gain vs scatter | 110 Hz 100/100 µs (15): best cell, score | 55 Hz 100/150 µs (10, in force): best cell, score, not-flat |
|---|---|---|---|
| one week (as is) | L 3.5 / R 3.5, 1.017, 0.906 vs 0.427 pass, 0.648 vs 0.552 pass | L 3.75 / R 1.00, 1.219 | L 2.5 / R 3.0, −0.683, 0.174 vs 0.226 FAIL |
| 24 h | same cell, 1.007, 0.920 vs 0.431, 0.660 vs 0.557 | same, 1.218 | same, −0.688, 0.181 vs 0.230 FAIL |
| 1 h | same cell, 0.766, 1.264 vs 0.494, 0.982 vs 0.580 | same, 1.198 | same, −0.814, 0.341 vs 0.320 pass |
| 10 min | same cell, 0.581, 1.466 vs 0.693, 1.037 vs 0.628 | L 3.75 / R 0.75, 1.110 | same, −1.014, 0.586 vs 0.521 pass |
| 2 min | same cell, 0.581, 1.461 vs 0.676, 1.028 vs 0.603 | L 3.75 / R 0.75, 1.035 | same, −1.181, 0.806 vs 0.523 pass |
| term off | same cell, 0.581, 1.464 vs 0.675, 1.031 vs 0.601 | L 3.75 / R 0.75, 1.037 | same, −1.181, 0.806 vs 0.523 pass |

- The **coverage check** (at least 6 current pairs with 5 ratings each on 2 days) is what refuses every clinic
  stratum today -- 2, 1 and 1 qualifying pairs -- and it does not read the weights at all, so **no recommendation
  changes under any weighting**.
- Shortening the reference makes the surface *more* confidently "not flat" (55 Hz: range 0.91 → 1.46 against a
  scatter of 0.43 → 0.68) and the gain over the incumbent larger (0.65 → 1.03), because the long-held steps stop being
  penalised as short. The best cell moves by at most one grid step (110 Hz: right 1.00 → 0.75 mA).
- The 55 Hz 100/150 µs stratum (the setting in force; 10 epochs from the 09_16 sheet) flips from "flat" to "not flat"
  once the reference is 1 h or shorter.
- Below a 10-minute reference the answers stop moving: the term is then effectively off for this stream.
- Side effect noticed: the same reference also reweights the REDCap stream, whose 55 Hz best cell moves from L 3.5 /
  R 3.5 to L 1.5 / R 1.0 at 1 h and shorter, and whose 110 Hz stratum's not-flat range goes 0.009 → 0.436 at 24 h; the
  sklearn fits print convergence warnings at their bounds throughout, so those surfaces are not stable to reweighting.
  A clinic-stream-specific reference (minutes) with the REDCap reference left at a week would be the way to apply
  this, if he wants it.

## S7 -- how the post-move exclusion margin changes the current-to-power curve

**The rule being varied.** A setting's "settled" band power is the mean of the 3 s pieces in the LAST 30 s before the
next current move, at least 10 pieces; the margin says pieces earlier than `t0 + margin` do not count. So the margin
can only change a value when a setting was held for less than 30 s + margin, and it can only *remove* pieces.

**Sweep.** Margins 0, 2, 4, ..., 20 s (11 windows), every single-side run of rising current on the record (11 runs),
the time-domain route at the stored centre 24.5 Hz. The host re-implementation of the rule matched the container's
own build on all 57 shared settled values to 1.1e-13.

**Result 1: the margin never changes a settled value; it only deletes settings.** Against margin 0: 0 of 30 values
changed at any margin; 1 setting dropped from 8 s, 2 from 16 s, 3 from 18 s. Hold lengths are 12 s to minutes
(median 78 s); 22 of the 96 (contact, setting) combinations are held under 50 s, so those are the ones a 20 s margin
can touch.

**Result 2: the pooled slope (one baseline per run) per contact and stimulation rate, by margin** -- identical across
margins except where a setting drops out (`s7_slopes.csv`; device units per mA):

| contact · rate | 0–4 s | 6 s | 8–14 s | 16 s | 18–20 s |
|---|---|---|---|---|---|
| L 1-3+ · 55 Hz (10 settings, 2 runs) | +14.2 ± 19.2 | same | same | same | +38.2 ± 19.7 (9) |
| L 1-3+ · 110 Hz (10, 3 runs) | +0.6 ± 5.1 | same | same | −1.0 ± 4.5 (9) | same |
| L 1-3+ · 145 Hz (5, 1 run) | −19.8 ± 7.6 | same | −16.2 ± 6.9 (4) | same | same |
| L 0-3+ · 110 Hz (8, 4 runs) | −1.7 | +15.3 (7) | same | +36.7 (6) | same |
| L 0-2+ · 110 Hz (6, 1 run) | −10.2 | same | same | same | same |
| R 0-3+ · 55 / 110 / 145 Hz | +3.3 / −5.3 / +9.8 | +3.3 / +0.8 / +9.8 | +3.3 / +0.8 / +13.4 | +3.3 / −0.2 / +13.4 | +2.8 / −0.2 / +13.4 |

L 0-3+ has no run in the page's three-source comparison (the build picks one contact per run, the one with the
device's own band power), but it streamed during 4 runs, so its curve is drawn from the tiles here; L 1-3+ at 55 Hz
is the 2026-08-18 visit alone.

**Result 3: the transient itself** (`s7_transient_*.png`): every piece's power divided by its own setting's
last-30 s level, against seconds since the move, mean ± SE per 3 s bin. On L 1-3+ the first 0–12 s sit at 1.0–1.1 of
the settled level at 55 and 110 Hz with a hump at 15–20 s (1.2–1.35) that is inside ±1 SE of the neighbouring bins;
at 145 Hz the first 10 s sit at 1.1–1.3. Nothing in the data marks a settling time: the piece-to-piece scatter
(±20–30 %) is larger than any early-versus-late difference.

**What this says about the margin.** With the last-30 s settled rule, a margin is not a transient exclusion at all
on this record; it is a minimum-hold-length filter (a setting must be held ≥ 30 s + margin to count), and the
slope changes it causes come from losing 1–3 short-held settings, which is exactly what decisions 144/178/179 saw
(the L 1-3+ 55 Hz slope +14 → +38 when one setting goes). An empirically motivated margin needs settings held long
enough that the first N seconds and the last 30 s are both measurable in the same setting -- the titration session's
60 s holds (open item 30) give that; today's record does not.

## S6 follow-up (2026-09-17, afternoon): the age penalty -- log drift is not raw drift, and the term cannot be fitted

**Two different quantities, two different units.** The age term acts on the PAIN RATING (0-10 after rescaling).
Decision 16's "-0.078 per month in the logarithm" is BAND POWER on one contact -- a different quantity -- and a
log slope is a proportional (multiplicative) change, which raw device-unit thresholds do not see the same way.
Re-measured on the right-hemisphere chronic samples near 8.8 Hz (3,652 samples, 2025-08-27 to 2025-11-18 -- the
only stretch the device recorded at that centre; the device's own centre moved on 2025-12-05, so the stretch
decision 16 named is not in the chronic record at 8.8 Hz):
- log slope **+0.206 per month (SE 0.016), i.e. +23 % per month multiplicative** -- clearly non-zero;
- raw slope **+33,117 device units per month (SE 31,587)** -- not distinguishable from zero, because raw band
  power is heavy-tailed: the October mean is 74,691 units against a median of 1,475 (spikes), the other months'
  means 1,295-1,607 against medians 727-1,318. The log slope is driven by the proportional change of the bulk;
  the raw slope is driven by a handful of spikes. A threshold in device units sits on the median, which moved
  727 -> 805 -> 1,475 -> 1,318 over the four months.
So decision 16's finding is real in its own units and says nothing about the pain rating's drift.

**The rating itself does drift, in raw units.** Report-weighted straight line of the epoch-mean left-leg VAS on
calendar time over 75 epochs and 11.5 months: **-1.48 VAS points per month (SE 0.34) = -0.15 per month on the 0-10
scale**, about -1.7 points over the record. The longest-held settings: 55 Hz L 1.6 / R 1.2 mA held 43 days, mean
60.3 (SD 14.3, n 105); the same setting 16 days, 57.9; L 3.5 / R 3.0 held 21 days, 56.5; L 4.5 / R 4.5 held 15 days, 46.1.

**(b) fitting the age weight by hold-out.** Stage 1 fitted on the epochs older than a cutoff, the held-out newer
epochs' ratings predicted at their own (rate, left, right, pulse widths), error on the 0-10 scale, report-weighted;
`c_age` from 0 (off) to 4 (16 x today's); three cutoffs. Only held-out epochs at a fitted pulse-width pairing can be
predicted (7 of 14, 11 of 18, 14 of 21).

| held out | c_age 0 | 0.25 (today) | 4 | baseline: mean of all training epochs | baseline: mean of the last 90 training days |
|---|---|---|---|---|---|
| last 90 days (7 epochs) | RMSE 1.332, bias +1.20 | 1.332, +1.20 | 1.331, +1.20 | 1.544 | **0.920** |
| last 120 days (11) | 1.403, +1.28 | 1.403, +1.28 | 1.403, +1.28 | 1.479 | 1.472 |
| last 180 days (14) | 1.822, +1.73 | 1.822, +1.73 | 1.822, +1.73 | **1.468** | 1.588 |

- **The age weight makes no measurable difference**: the error is identical to three decimals from "off" to sixteen
  times today's value. The term adds at most 0.25 x (1.2 years)² = 0.36 to an observation's variance, and the fit is
  dominated by the other terms and the model's own noise level, so it cannot be fitted from this record -- there is
  nothing for it to explain.
- **The model over-predicts recent pain by 1.2-1.7 points** (positive bias at every cutoff): her ratings have fallen
  over the record and the model, anchored on the whole history, does not follow. An additive uncertainty on old
  epochs cannot fix a bias -- it can only widen the interval. What would: a time term in the model (the "time-varying
  kernel" the spec deferred) or a trend removed before fitting.
- For the 90-day hold-out, the plain mean of the previous 90 days predicts better (0.92) than the fitted surface
  (1.33): recency matters more on this record than the surface's shape does.

Probes: `_agent_bridge/_s6_age_fit.py`, `_d16_units.py`. Recommendation: drop the age term (it is inert) and, if
drift is to be handled, do it as a time input to the model, fitted, not as a variance penalty.

## S7 follow-up (2026-09-17, afternoon): the transient measured inside the long holds the record already has

The PI: "the 60-second holds in the titration session would give that -- so measure that." 58 of the 96 settings
were held 60 s or longer and 36 of them 90 s or longer, so both the first seconds and the last 30 s are inside one
hold. For each such setting: the mean band power (24.5 Hz, time-domain route) over the first N seconds after the
current moved, divided by the same setting's own last-30-s mean; pooled as a geometric mean; p from a one-sample
t-test on the log ratio (probe `_agent_bridge/_s7_long_holds.py`).

**All contacts and rates pooled, 56 settings held ≥ 60 s** (two of the 58 had fewer than 5 settled pieces):

| first N s | ratio to the settled level | 95 % interval | p |
|---|---|---|---|
| 3 s | 0.979 | 0.903–1.062 | 0.62 |
| 6 s | 0.992 | 0.936–1.051 | 0.79 |
| 9 s | 0.990 | 0.937–1.045 | 0.71 |
| 12 s | 0.990 | 0.940–1.044 | 0.72 |
| 15 s | 0.984 | 0.934–1.037 | 0.55 |
| 20 s | 1.013 | 0.960–1.070 | 0.64 |
| 30 s | 1.016 | 0.968–1.066 | 0.53 |

Per contact and rate (≥ 60 s): L 1-3+ 110 Hz (9 settings) 0.99–1.10, no p below 0.14; L 0-3+ 110 Hz (6) 0.90–0.99,
no p below 0.29; R 0-3+ 110 Hz (21) 0.93–1.00, no p below 0.14; L 0-2+ 110 Hz (6) 1.04–1.07, no p below 0.32.
The one exception: **R 0-3+ at 55 Hz, 4 settings from the single 2026-08-18 run**, where the first 3–15 s read
0.79–0.87 of the settled level (p 0.00–0.09) -- one visit, four settings, not a finding by this project's own rule
(never call a result established on one visit day). At ≥ 90 s (36 settings) the picture is the same: ratios 0.95–1.22,
the only p under 0.05 being L 1-3+ 110 Hz at 9 s and 30 s in the direction of the early window being HIGHER (1.12–1.13).

**Reading.** Inside the holds this record already has, the band power in the first 3 seconds after a current move
is within 2 % of the level it holds 30–60 s later, with a 95 % interval of ±6–8 %. There is no transient to exclude
at the 3 s resolution of the pieces: any settling happens inside the first piece. A margin of 0 s is the measured
answer for this contact set at 110 Hz; the 55 Hz evidence is one visit and cannot decide it. The titration session
(open item 30) would add 55 Hz holds at 60 s, which is where the record is thin.

## S7 settled (2026-09-17, evening): the 2026-09-16 titration session at 55 Hz

The PI: "you should have access to the 9-16 clinic session, which already did the 55 Hz stim titration session."
It is on the server (6 time-domain and 4 streaming recordings that day). The device's own current record shows
the session as designed in decision 160: the left ladder 0.5 → 4.5 mA in 0.5 mA steps held 107–120 s each, down
in 1.0 mA drops, with the RIGHT held at 2.5 mA throughout; then a right ladder with the left held. **The page's
run finder does not see it**, because `find_single_side_runs_from_device` requires the other side to be at ZERO
(the rule written for the 2025 visits); holding the other side at its in-force current, which decision 160 chose
on purpose, fails that rule. That is a separate fix (accept a constant other side, record what it was held at),
named here and not made: it changes which runs enter the pooled slope, E1 and every table downstream.

Measured directly from the tiles (probe `_agent_bridge/_s7_0916.py`): 31 settings held ≥ 60 s on 2026-09-16 (14
left moves, 13 right moves, 4 both), settled values on L 1-3+ (31) and R 0-3+ (30).

| first N s / last 30 s | L 1-3+ (31 settings) | R 0-3+ (30 settings) |
|---|---|---|
| 3 s | **1.000** (95 % 0.86–1.16, p 1.00) | 0.929 (0.81–1.07, p 0.31) |
| 6 s | 0.972 (0.87–1.09, p 0.62) | 1.038 (0.92–1.17, p 0.55) |
| 9 s | 0.971 (0.88–1.07, p 0.56) | 1.053 (0.96–1.16, p 0.28) |
| 12 s | 0.969 (0.89–1.06, p 0.49) | 1.028 (0.94–1.12, p 0.55) |
| 15 s | 1.011 (0.92–1.12, p 0.83) | 1.046 (0.98–1.12, p 0.22) |
| 20 s | 1.033 (0.94–1.13, p 0.50) | 1.060 (1.00–1.13, p 0.07) |
| 30 s | 1.045 (0.96–1.14, p 0.33) | 1.064 (1.00–1.13, p 0.06) |

On the contact the titration was run for (L 1-3+), the first 3 s after a move are 1.000 of the settled level; no
window differs from the settled level; the two R 0-3+ windows nearest p 0.05 are in the direction of the early
window being HIGHER, i.e. no transient to exclude. **Settled: the margin is 0 s, no piece of recording is
excluded, the switch stays off and the titration card says so.** The 55 Hz left-ladder curve itself (L 1-3+,
right held at 2.5 mA): 0.0 mA 293, 0.5 mA 223, 1.0 mA 279 / 230, 1.5 mA 287 / 491, 2.5 mA 302 / 439, 3.0 mA 276,
3.5 mA 265 / 292, 4.0 mA 247 / 222, 4.5 mA 244 device units (two values where the up and the down leg both held
that current).
