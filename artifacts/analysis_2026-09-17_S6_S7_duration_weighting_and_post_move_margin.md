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
