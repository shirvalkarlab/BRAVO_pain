# ADR — a family-wise corrected label for the calibrated 22-point grid, 8-30 Hz only

**Written 2026-09-08 for the Biomarkers heat-map redesign. Not yet approved — see the open
question at the end.**

## Context

The calibrated correlation-and-AUC grid checks 22 fixed frequency points against ten lengths of
signal. Its existing per-point answer (established, not settled, not assessed) comes from comparing
the best of the ten lengths against a shuffled reference built the same way — a correction for
having picked the best length, confirmed in the code as covering exactly that and nothing more.
**Nothing today corrects for having also tested 22 different frequency points at once.**

The older, separate routine already corrects across its own, much wider set of frequency points
(roughly a hundred, spanning 0 to 100 Hz) using Benjamini-Hochberg, a method that controls the
expected share of false positives among everything called significant, applied after a separate fix
for pain ratings being related to each other over time. That method lives in one shared function
this project already has (`stats_utils.bh_fdr`) and only that function; nothing else offers this
kind of correction anywhere in the codebase today.

The PI's own reasoning for wanting a second, narrower correction rather than one shared one: testing
fewer things at once makes a correction less conservative, so restricting the family being corrected
for to the calibrated grid's own 22 points — already confined to 8 to 30 Hz by what the implanted
device can use, not by a new choice made here — should find real relationships this correction
would otherwise wash out if it were pooled with the older routine's much wider range.

## Decision

**Add a second, independent family-wise correction to the calibrated grid, using the same
Benjamini-Hochberg method the older routine already uses, applied only across the calibrated grid's
own 22 frequency points per sensing contact pair — never pooled with the older routine's wider
range.** This sits alongside the grid's existing best-of-ten-lengths answer, not in place of it: a
frequency point's full label becomes the combination of both — for example, "established, and
survives testing 22 points at once" versus "established on its own length, but not once 22 points
are accounted for."

**This label is informational, never a gate.** A point that fails the new correction remains fully
visible, browsable, and exportable to Closed-Loop Deployment exactly as before. Nothing about
whether a point can be selected, drilled into, or sent onward changes; only how it is labelled does.

## What this does not decide

**Whether the same autocorrelation fix the older routine applies (a correction for pain ratings
being related to each other over time, separate from correcting for testing many points) also
belongs on the calibrated grid.** The investigation behind this document found no such adjustment
exists for the calibrated grid today, with or without this new correction. Adding the family-wise
correction on top of an uncorrected-for-autocorrelation p-value would be applying one honest fix
without the other; leaving both out matches what exists today but leaves a known gap unaddressed.
**This is a separate, open question this document surfaces and does not resolve** — it needs its
own explicit decision, the same way the June zero-fill fix (decision 4) and this one each got their
own record rather than being decided in passing.

## Why this method and not another

Benjamini-Hochberg is proposed because it is the one correction method this project already has
built, tested, and uses elsewhere for exactly this kind of problem — many tests, one target rate of
false positives among the ones called significant. A stricter, single-error-rate method (the
Bonferroni family) was not chosen because it is more conservative than this project's own precedent
without a stated reason to prefer it here, and introducing a second method alongside the one already
in use would need its own justification this document does not have grounds to make.

## Consequences

- One more field appears on every one of the grid's 22×N cells (N = number of sensing contact
  pairs): whether that point survives the 22-point correction, alongside its existing best-of-ten
  answer.
- A point that is "established" alone but not "established" once the 22 points are jointly
  corrected for will now say so plainly, rather than only carrying its narrower label.
- This changes what a reader sees as significant on the grid, on live data, the first time it runs —
  it must be proven live on RCS08 (field count and difference count, per `ARCHITECTURE_cache_store.md`
  §7) before shipping, not merely tested on constructed data.
- No stored number that already exists changes; this adds a new field, it does not alter the grid's
  existing correlation or AUC values.

## Resolved 2026-09-08

**Method confirmed: Benjamini-Hochberg**, exactly as proposed above. **The autocorrelation
adjustment is explicitly NOT part of this correction** — the calibrated grid's new family-wise
label is computed from the grid's own p-values as they stand today, with no adjustment for pain
ratings being related to each other over time. The gap this document surfaced (§"What this does
not decide") stands as a separately known, separately open question about the calibrated grid's
statistics generally — it is not folded into this decision and not blocking it.

## Built and proven, 2026-09-08

Implemented as `analytics._apply_family_wise_correction`, fed by the per-band `p_selection_aware`
value the grid already computed (the permutation-based p-value correcting for choosing the best of
ten lengths), run through `stats_utils.bh_fdr`, called once for the correlation rows and once for
the AUC rows — two independent 22-test families, never pooled with each other or with the older
routine's range.

**A real caching bug was found and fixed while proving this live.** The grid's stored response is
keyed on its user-facing settings plus a code-version constant; this change added two fields to
every row without changing any setting, and the version constant was not bumped, so the first live
check showed zero new fields — an unchanged request was replaying a response computed before this
code existed. Fixed by bumping `_BAND_SWEEP_RULE_VERSION`. Re-proven correctly after the fix, on
RCS08 through the bridge: 27,337 fields in the response before this change, 27,865 after; all 528
new fields are exactly the two new fields per row; of the 27,337 fields both responses have in
common, 22 differ, all of them either a timing field or a store key that correctly changed because
the version did — zero scientific values moved.

**On the live grid, 47 of 264 band-centre rows (across both the correlation and the AUC measures,
all six sensing contact pairs) clear the correction.** A synthetic-data test built during this work
found the correction is considerably stricter than it might look: even an extreme, artificially
strong planted relationship (in a constructed 80-report fixture) corrected to a q-value of 0.32,
not under 0.05, because the existing best-of-ten-lengths selection effect alone already produces a
wide null distribution before the 22-centre correction is even applied on top of it. The real
result on RCS08 is healthier than the synthetic worst case, but the correction is doing genuine,
non-trivial work rather than passing everything through.
