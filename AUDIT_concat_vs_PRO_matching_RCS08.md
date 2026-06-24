# Audit — does across-time concatenation cause MISSED PRO→neural matches? (RCS08)

**Your question:** when `FixBreaking` concatenates a later TD recording into an earlier one's
`StartTime`, can a pain report (PRO) that occurs minutes later end up with **no neural match** —
because the recording that would have covered it was absorbed/shortened out of the PRO's matching
window?

**Answer: No. On the real RCS08 data, concatenation does not cause, and cannot plausibly cause, a
missed PRO→neural match.** Verified three independent ways below. Implementing fix A (Welch dilution)
is therefore safe to proceed.

## How the matcher actually addresses time (the mechanism that decides this)

PRO→neural matching (`bravo_service._welch_rows_into`, lines 519-587; tolerance in
`_match_tolerance_param`) works in two layers:

1. **Rating-centered (primary).** For each PRO that falls inside a recording's actual coverage
   `[t0, t0+dur]`, a Welch window is cut **centered on the PRO's own timestamp** and the PSD is
   stamped at the PRO time (offset ~0). **Concatenation EXTENDS `dur`, so this layer can only ADD
   coverage, never remove it** — a PRO inside the merged span is still inside it.
2. **Nearest-fallback (secondary).** A recording with no in-span PRO emits one PSD at its `StartTime`,
   matched to the nearest PRO within tolerance.
   **`DEFAULT_MATCH_TOLERANCE_MIN = 60 min`** (raised from 15 — "pain reports anchor neural data on a
   minutes-to-hours scale"). The largest single concatenation gap bridged in RCS08 is **29.5 s**;
   even a fully chained merge moves a `StartTime` by ~20 min, well inside the 60-min window.

So the only way concatenation could *drop* a match is if it moved a recording's emission point >60
min away from a PRO that was previously ≤60 min from a now-absorbed recording. The data show this
never happens.

## Evidence

**The deployed cache:** 224 `MedtronicBrainSenseTimeDomain` recordings ingested from 499 source
files, spanning 2025-07-17 → 2026-06-10. **678 PRO reports** (processed chronic table), spanning
2025-07-20 → 2026-06-16. The "concatenate" checkbox was ON at ingest, so the live recordings are
already in the concatenated state.

**Test 1 — re-decode every source file both ways, compare PRO matches.** Decoded all Medtronic
source files with `FixBreaking=False` (no concat) and `=True` (concat), replicated the exact emission
+ 60-min matcher against the 678 real PRO times:
- 25 source files yield TD streams; concatenation merges occurred in 8 of them.
- PROs matched within 60 min: **2 (no-concat) vs 2 (concat) — identical.**
- PROs that LOSE a match due to concat: **0.** PROs that GAIN a spurious match: **0.**
- PROs whose match status changed at all: **0.**

**Test 2 — direct against the 224 live ingested recordings.** Only **2 of 678 PROs** fall within
60 min of *any* ingested TD recording start at all:
- PRO 2025-09-18 18:05:27 → nearest TD 18:08:31 (3.1 min)
- PRO 2026-06-10 19:14:31 → nearest TD 20:01:14 (46.7 min)

**Test 3 — mechanism of those 2 matches, both ways.** For each matched PRO, identified the matching
recording and path under concat on/off:
- 2025-09-18 PRO: matches via **nearest-fallback**, dist **3.07 min** under BOTH settings. Concat
  changed the matched recording's duration (64 s → 952 s) but **not** the match distance or outcome.
- 2026-06-10 PRO: matches via nearest-fallback, dist **46.73 min**, **identical** both ways (that
  file had no qualifying merge).

## Why the structural risk is real but the empirical risk is nil

The structural failure mode you described is real in principle — the nearest-fallback layer keys on a
single `StartTime`, and concatenation moves that point earlier. It does not bite **here** because:
1. RCS08 streaming sessions and pain reports are almost entirely **disjoint in time** — only 2/678
   PROs land within an hour of any TD recording. The patient rates pain on a daily-ish cadence;
   BrainSense streaming happens in discrete clinic/research sessions. They rarely coincide.
2. The 60-min tolerance dominates the ≤30 s merge gaps by two orders of magnitude.
3. The rating-centered layer makes in-session PROs concat-immune by construction.

**Caveat / monitoring:** this is a property of the *current* RCS08 data, not a theorem. If a future
protocol streams TD **continuously around pain ratings** (e.g. closed-loop sensing with frequent
in-session PROs), chained concatenation that moves a `StartTime` >60 min could begin to matter for
the nearest-fallback layer. A cheap guard worth adding later: in the fallback emission, stamp the PSD
at the recording's *midpoint* or emit the un-merged sub-segment boundaries, rather than the merged
`StartTime`. Not needed for the current dataset.

## Conclusion

Neural matching is **robust to time-domain concatenation** on RCS08 — confirmed. The remaining,
genuine issue is concern #2 (Welch dilution from zero-filled gap samples entering the PSD unmasked),
which is independent of matching and is addressed by **fix A** (Missing-aware TD Welch epochs),
implemented separately. Reproduction was run inside the live container against the real ingested
cache and PRO table; no patient data left the container or entered the repo.
