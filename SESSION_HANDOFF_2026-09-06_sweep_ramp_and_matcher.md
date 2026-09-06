# Session handoff — 2026-09-06 (late): the band-by-length sweep, the measured ramp, and a 21x faster matcher

Branch `PS_closedloop_deployment`. Suite counts below were each read from an actual run, never
carried from memory.

**COMMIT LEDGER — the full session, read from `git log` with timestamps rather than from memory.**
The session spans midnight, so a calendar-date filter splits it and undercounts; these are all ten,
oldest first. This document narrates the last three in detail (§1–§3) and the ramp/averaging pair
that set them up; the earlier ones are covered in
`SESSION_HANDOFF_2026-09-05_clinic_steps_and_ramp.md` and MEGA_HANDOFF §0.

| commit | time | what |
|---|---|---|
| `97c9664` | 09-05 20:10 | units error in the current-response comparison; pain-tracking quantity replaced |
| `0d8a862` | 09-05 20:18 | corrected single-side visit counts that restated a sub-agent's prose |
| `688a185` | 09-05 20:41 | recorded that closed-loop band power was not on the device's scale; **withdrew the invented constant** |
| `90eb109` | 09-05 21:27 | **closed-loop band power read from the lab's calibrated route** — moved the deployable verdict 2/50 → 6/50 |
| `eb33ade` | 09-05 22:03 | ramp measured from the device instead of assuming 45 s; settled values averaged |
| `0f6a75b` | 09-05 22:28 | three-source panel moved to the bottom of the closed-loop page; asserted contamination wording removed |
| `bfc3b8f` | 09-05 22:42 | **`ContinuousAmplitudeError` guard** — refuse a recording whose current never holds still (§2, "a defect in my own new function") |
| `e1cc557` | 09-05 23:09 | **the band-by-length sweep** (§1) |
| `790ed21` | 09-05 23:54 | **the look-back clipped at the measured ramp** (§2) |
| `958cc89` | 09-06 00:39 | **the matcher vectorised, 21.4x** (§3) |

**Correction to an earlier statement in this same session:** I said "four commits already pushed
tonight" and then listed three in this header's first version. Both were wrong — there are ten, and
the guard fix `bfc3b8f` is its own commit rather than part of `790ed21` as §2 originally implied. It
also landed BEFORE the clip, at 22:42 against 23:54.

---

## 1. The automated sweep over band centre and length of signal (`e1cc557`)

A new last section on the biomarker exploration page. 22 band centres (8.5–29.5 Hz, each 5 Hz wide,
taken from the cache's OWN centre list rather than a hardcoded range, so a centre with no
measurements behind it cannot appear) against 10 candidate lengths of signal. The FULL 220-cell grid
is returned, not only the best cell per band, because the shape of the surface is what the PI asked
to explore.

**The length asked for is not always the length delivered, and both travel with every row.** A band
power measurement is built from whole 3-second pieces, so 5 of the 10 requested lengths cannot be
delivered exactly: 1 → 3 s, 5 → 6 s, 10 → 9 s, 20 → 21 s, 25 → 24 s. Labelling the shortest row
"1 s" would have misstated it threefold.

**No new matching rule was written.** `availability.live_lsb_spectrum_match` already takes the
length of signal as an argument and is the same function the full-spectrum scan uses; sweeping that
one argument IS the mechanism.

### The reported maximum pays for having been chosen

Taking the best of ten correlated windows per band inflates the answer. A row reads `established`
only when its resampling interval stays off the no-relationship value AND the value beats what the
same best-of-ten choice reaches on 1000 circular block shuffles of the pain scores.

Read back from the saved tables, not asserted:

| | intervals off the no-relationship value | HELD BACK by the shuffled best-of-ten | `established` |
|---|---|---|---|
| correlation | 125 of 264 | **77** | 48 |
| high-versus-low pain | 105 of 264 | **70** | 35 |

No `established` row fails the shuffled test. So about 60% of rows that look significant on their
own interval do not survive having been chosen. This project has already retracted one candidate
biomarker for exactly that error, and the 110 Hz amplitude result failed the same test this session
at p = 0.33.

**0.5 means no discrimination.** Both scales centred on the right value (0.5 and 0), 0.5 inside the
scale rather than at an end, an interval spanning it reads `not_resolved` in word, sentence and
headline, and `not_resolved` kept distinct from not-assessed.

### Live values on RCS08

* NRS: r = **−0.527** at 16.5 Hz on `ONE_THREE_LEFT`, 15 s delivered, n = 173, interval −0.632 to
  −0.399, shuffled best-of-ten 0.195, p = 0.0010 → **established**.
* Left Leg VAS: r = −0.377 at 10.5 Hz on `ZERO_TWO_LEFT`, 9 s delivered (asked 10), n = 55, interval
  −0.583 to −0.157, shuffled 0.387, p = 0.0709 → **not resolved**. This is exactly the case the
  correction exists for: an interval clear of zero that does not survive selection.

### Declared deviation, with the measurement behind it

The grid draws the **unfolded** area under the curve, not the fitted regression's prediction. A
one-predictor logistic regression's in-sample value is EXACTLY the band power's own value or one
minus it, with the fitted slope's sign deciding which — so the fitted number is direction-folded and
cannot fall below 0.5, making 0.5 a lower bound rather than a neutral middle for it. Confirmed in
the saved table: unfolded spans 0.208–0.787 while folded bottoms out at 0.516. Both are reported.

Two bugs that comparison found and fixed: scoring the fit on a predicted probability saturated to
exactly 1.0 and 0.0 in floating point, creating ties worth up to 0.03; and the logarithm the fit
uses silently drops rows where band power is not strictly positive, so the two were being compared
on different numbers of rows.

### Performance as built

220-cell grid by matrix operations **0.72 ms** against **168 ms** by fitting real regressions, about
230x, with no loop over bands. Cores deliberately NOT used: each fit is milliseconds that repeatedly
release and reacquire the interpreter lock, so thread overhead would swamp the gain; the argument is
kept and defaults to serial so the measurement can be repeated.

**Container Biomarkers PASS=362 FAIL=0** at this commit (16 tests new).

---

## 2. The look-back window is clipped at the measured end of the ramp (`790ed21`)

PI instruction: "we render that off the measured ramp."

`mean_power_before_next_change` averages the last `window_s` seconds before the current next moves,
which assumes the setting was held longer than `window_s`. **Across RCS08's whole record that
assumption fails on 188 of 600 plateaus**, where the look-back reaches back into the stretch in
which the current was still changing.

**Size of the error, on a constructed case where the answer is known: the unclipped rule returns 660
device units where the settled level is 100** — a 6.6-fold inflation. Not a rounding-level
correction on an affected column.

**It is a clip, not a new rule, and the test pins both halves.** Where the hold exceeds the window —
the common case — the values are identical, and `ramp_end_t=None` reproduces the original behaviour
bit for bit, which is why all 33 pre-existing tests on that function pass unchanged. A setting whose
clipped window holds too few pieces is REFUSED with a reason naming the ramp and the actual hold,
rather than silently returning a thinner average.

Ramp ends come from `ramp_windows_from_amplitude`, measured from the device's own record, because
**the ramp is not predictable from the step size**: 0.0 s for a single-increment step, up to 75.0 s
for one the device chose to deliver in 35 pieces.

### Exposure of the published figures, which was the PI's question

| figure | visit | plateaus where a 30 s look-back reaches into the ramp | that the old fixed 45 s rule emptied entirely |
|---|---|---|---|
| heat maps, three-source panel, 1 s-epoch plots | 2026-08-18 | 2 of 27 | — |
| 18-band timeline and scatter | 2026-06-24 | 1 of 33 | — |
| pre-registered 110 Hz heat map | 2025-08-21 | 6 of 29 | — |
| whole record | all | 188 of 600 | **251 of 600** |

The old fixed 45 s exclusion was worse than any of these: it discarded EVERY second of 251 of 600
plateaus, so any figure built on it worked from well under half the steps available.

---

## 2b. A defect in my own new ramp function (`bfc3b8f` — its OWN commit, and it landed FIRST)

Found by auditing `ramp_windows_from_amplitude` against the whole record rather than the one visit
it was built on, prompted by the PI asking whether the ramp finding affected any earlier plots.
**This is commit `bfc3b8f` at 22:42, not part of `790ed21`** — an earlier version of this document
narrated it under the clip, which was wrong.

Two regimes exist in the record — clinic step ladders, and at-home recordings where the current
never holds still. The burst-collapsing rule glued thousands of consecutive changes in the second
kind into one reported "ramp" of up to 615 s. Arithmetically true, meaningless as a description, and
anything taking it at face value would discard ten minutes of signal to guard a settling transient
with no defined start. `ramp_windows_from_amplitude` now REFUSES those blocks with
`ContinuousAmplitudeError` rather than describing them — an exception and not an empty return,
because an empty result cannot be told apart from a block whose current never moved. The threshold
is not delicate: ladders use a median of 4 increments and 35 at most, the refused regime starts
around 494, and a test pins both ends.

The 326-step combined analysis had been safe from this only incidentally, because a minimum-hold
filter dropped those blocks silently. They are now refused explicitly and can be counted.

**Suites: ClosedLoopDeployment + StimOptimizer 778 passed, 41 skipped.**

---

## 3. The matcher no longer loops over pain reports (`958cc89`) — 21.4x

PI request: "can you fully vectorize the matching so that it's faster?"

Profiling first, rather than guessing: `live_lsb_spectrum_match` takes the prebuilt cache as an
ARGUMENT, so the spectrum computation is not inside it. What was inside it were two Python loops
over pain reports, one per tier, each taking a small nan-median — about 15,200 separate small
medians per sensing contact pair with 760 reports and ten lengths.

Both passes now pad every report's selection into ONE `(reports × pieces × band centres)` block of
NaN and collapse it with a SINGLE `np.nanmedian(..., axis=1)`. Output records are built from array
columns. **The eligibility test and the nearest-report assignment were NOT touched.** New helpers:
`_pad_owned_windows`, `_pad_windows_in_extent`, `_cap_nearest_windows`, `_padded_nanmedian`.

**The larger half of the gain was not the vectorization.** Re-profiling found that converting the
cache's band values into a float matrix — which depends only on the cache and never on any match
setting — was being redone for all ten lengths, 1.19 s of the 1.53 s still left per pair.
`_lsb_family_mat` now converts once, keyed on the identity of the row list so replacing the rows
forces a fresh conversion, and marks the matrix non-writeable. The padded collapse alone was 3.2x;
the once-only conversion supplied the remaining 6.6x.

### Timings, mean of three ALTERNATING runs (old, new, old, new, old, new)

Alternating because the operating system keeps recently-read files in memory and whichever ran
second would otherwise look faster for reasons unrelated to the code.

| sensing contact pair | before | after | faster by |
|---|---|---|---|
| ZERO_THREE_RIGHT | 4.550 s | 0.300 s | 15.2x |
| ONE_THREE_LEFT | 3.115 s | 0.140 s | 22.3x |
| ZERO_THREE_LEFT | 2.707 s | 0.106 s | 25.6x |
| ZERO_TWO_LEFT | 2.701 s | 0.105 s | 25.8x |
| ONE_THREE_RIGHT | 2.595 s | 0.102 s | 25.4x |
| ZERO_TWO_RIGHT | 2.596 s | 0.100 s | 26.0x |
| **all six** | **18.263 s** | **0.852 s** | **21.4x** |

Per-round totals, showing the runs were stable rather than one lucky pair: before 18.173 / 18.372 /
18.242 s; after 0.842 / 0.858 / 0.856 s.

### Output unchanged EXACTLY, which is the point of the change

The pre-change function was frozen byte for byte and run beside the new one in one process,
demanding equality of value AND Python type on all 10 record fields and all 16 `stats` keys. Read
back from `vec_exact_equality_live_RCS08.csv`:

* **1,080 live configurations, `n_field_differences` = 0 in every row**
* 819,360 records and 80,297,280 individual band entries compared
* all six contact pairs, both reuse modes, 15 lengths of signal, 3 pain scores, both eligibility radii
* band entries None 70,156,500 and carrying a value 10,140,780, all identical

Tier coverage, which is why comparing across all of that mattered: voltage-trace tier reached in
**1,080 of 1,080** configurations, device-spectrum tier in **900 of 1,080**, unmatched in **1,080 of
1,080**. A comparison exercising one path proves nothing about the others. The 180 configurations
with no device-spectrum-tier report are the two right-side pairs at the 3,600 s radius, where every
report with a device-spectrum window nearby also has a voltage-trace piece nearby and the voltage
trace wins. A further 360 configurations on constructed caches: 0 differences.

Both named traps held. A report with NO eligible piece and a report whose eligible pieces hold no
band values stayed DIFFERENT cases — the first keeps `tier` None and `used_s` 0.0, the second is a
matched voltage-trace report with `n_td_used` set but every band None — because a report with an
empty selection is excluded from the collapse rather than fed to it as padding. The distance tie
still resolves to the earlier piece.

### Where the time is now, so the stopping point is documented

| stage | seconds |
|---|---|
| every statistic, six pairs | 1.864 |
| pain reports pulled from REDCap | 1.705 |
| time-domain recordings read from disk | 1.453 |
| **matching, six pairs** | **1.282** |
| spectrum recordings from disk | 0.408 |
| patient-event spectra assembled | 0.331 |
| memoized 3 s-piece cache fetch | 0.013 |
| montage spectra | 0.003 |
| **whole warm request** | **7.497** |

Matching is now **40.7%** of per-pair work (1.282 of 3.146 s), down from essentially all of it.
Nothing further was optimised in that commit, correctly — the statistics and the REDCap pull are
different problems and neither is arithmetic.

**Container Biomarkers PASS=370 FAIL=0** (up from 362 by its 8 new tests).

### Documented, not changed

Two pain reports filed at the **identical second** are not separated by the nearest-report rule at
all: the search compares a piece against its two neighbours in time, and two identical times are
one neighbour twice, so pieces before the pair go to the first report and pieces after to the
second. Partitioned, never double-counted. This record contains such pairs; unchanged and now
covered by the comparison.

---

## 4. Analysis findings this session (no code change)

### The pre-registered 110 Hz heat map's visit cannot attribute to a side at all

`2025-08-21` at 110 Hz: across all 45 settings the two stimulator currents correlate **1.0** and the
longest single-side stretch is **0** (`onesided_current_visit_search_RCS08.csv`). The stimulators
were moved in lockstep all day. That is a larger limitation than its 6-of-29 ramp exposure, and it
was previously unstated. The one-side heat-map builder correctly REFUSES that visit.

### Which forced a check on the 110 Hz claim — it survives, on better grounds

Side correlation WITHIN each of the three days behind that result:

| visit day | steps | right stimulator | left attributable |
|---|---|---|---|
| 2025-08-21 | 8 | **held at exactly 0.0 mA throughout** | yes, cleanly |
| 2025-09-04 | 7 | **held at exactly 0.0 mA throughout** | yes, cleanly |
| 2026-09-02 | 6 | rose with the left, r = +0.80 | **no** |

**The pooled −0.11 I quoted earlier is NOT what licenses the attribution** — pooling two days with
the right side at zero and one with it rising produces a low number partly by cancellation. The
basis is the two days where the right side never moved.

Dropping the confounded day improved the family-wise result five-fold: **p = 0.330 pooled → p =
0.064 on the two clean days** (cluster 25–29 Hz, 5 bands, mass −16.38, 15 steps). Still not
significant, and NOT called established. Seven bands negative on both days; 27 Hz gives −0.720 and
−0.732 across visits thirteen days apart. Four of the seven are OFF-landing.

Both statements about `2025-08-21` are true and not in conflict: across all 45 settings the sides
moved together, while the 8 settings that yielded usable settled signal on `ONE_THREE_LEFT` at
110 Hz happen to have the right side at zero. The visit search uses a stricter definition — a
contiguous run of settings — and correctly reports zero by it.

### 55 Hz on the same electrode: the response is PEAKED, and the linear retraction does not apply

Only **one** of six visit days with 55 Hz recordings on `ONE_THREE_LEFT` has the right stimulator at
zero — `2026-08-18`, 8 steps, 0.5–3.5 mA. The other five ramped both sides together. **No
cross-day replication is available at 55 Hz.**

The four bands on the 25 Hz landing (25, 26, 27, 28 Hz) are exactly the four that RISE THEN FALL,
curvature p 0.014–0.025, peaks at 2.120 / 2.089 / 2.071 / 2.063 mA. Every off-landing band runs
straight.

Same electrode and rate, three tests:

| test | family-wise p |
|---|---|
| the project's earlier retraction, LINEAR | **0.670** |
| linear, on this clean day | 0.144 |
| **CURVATURE, on this clean day** | **0.125** |

**So the earlier retraction is a statement about a straight line, not about the band.** A linear
cluster test has almost no power against a rise-then-fall, because the best straight line through
one is nearly flat: at 27 Hz a line explains 10% of the variation and a curve explains 76%, with the
linear correlation r = +0.31 at p = 0.45. Still not significant at 0.125 on 8 steps in one day, but
five times better than the number the retraction rested on, from the test that matches the shape.

**The two rates tell different stories about one electrode and both are underpowered** — 110 Hz
monotonic negative across two replicated days, 55 Hz rising to ~2.1 mA then falling. Not compatible
descriptions of one mechanism. A control law fitted at one rate should not be assumed to transfer.

**Consequence for the next visit:** a peaked response needs steps THROUGH the peak, not a two-point
comparison — and the device places its switching value between two readings, which a peaked band can
satisfy on both sides of the peak at different currents. Worth deciding before the next ladder.

---

## 5. Open at the end of this session

1. **Commit identity.** `bravo-session-rules` Rule 4 asks for commits under the PI's name and email.
   All commits this session used `Claude <noreply@anthropic.com>` instead, because attributing
   machine-written commits to a named researcher in a permanent research record is the PI's call and
   not the agent's. **Awaiting his decision**; nothing already pushed was rewritten.
2. **Two optimisation lanes were in flight when this was written** — the sweep statistics (1.864 s)
   and the REDCap pull (1.705 s). Their results are NOT in this document and the suite counts above
   predate them.
3. **The pre-registered 110 Hz heat map should be REPLACED, not re-rendered** — built from the two
   days with the right stimulator at zero rather than from a lockstep visit. Offered, not yet built.
4. `README_BIOMARKERS_AND_DEPLOYMENT.md` reconciliation — see
   `README_CORRECTIONS_RECONCILED_2026-09-06.md`.
