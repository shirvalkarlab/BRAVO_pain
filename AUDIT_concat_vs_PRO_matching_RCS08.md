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

## Timezone correction (important — first pass was wrong)

The PRO timestamp column `date_time_s1_daily` is REDCap **California local wall-clock**, not UTC. The
service localizes it to `America/Los_Angeles` then converts to UTC (`bravo_service._pro_timestamps_utc`,
documented in FIXHANDOUT_pro_timezone_mismatch) — a +7 h (PDT) / +8 h (PST) shift. The device side
(TD `StartTime`) is already UTC per the Medtronic white paper. A first pass here parsed the PRO
column with `utc=True`, placing every pain score 7-8 h too early — exactly the historical bug the
service guards against — which collapsed the apparent overlap to a spurious 2/678. **All numbers
below use the service's own CA→UTC conversion.** The conclusion (matching robust to concat) is
unchanged, but the match pool is an order of magnitude larger, so the test is far more meaningful.

## Evidence

**The deployed cache:** 224 `MedtronicBrainSenseTimeDomain` + 108 `MedtronicIndefiniteStream`
recordings (BOTH are `TIMEDOMAIN_TYPES` → both feed the Welch matcher), from 499 source files.
IndefiniteStreams are long (median 16 min, up to 90 min) and carry most matches. **678 PRO reports**,
spanning 2025-07-20 → 2026-06-16. The "concatenate" checkbox was ON at ingest. **Only
`MedtronicBrainSenseTimeDomain` is subject to FixBreaking concatenation** — IndefiniteStreams group
strictly by `FirstPacketDateTime` (`saveIndefiniteStreams`), no cross-time merge, so their emissions
are identical regardless of the flag.

**Match census (correct tz, both TD sources, live concatenated cache):**
- **67 of 678 PROs** have a neural match within the 60-min tolerance (23 via BrainSenseTD, 51 via
  IndefiniteStream; overlapping).
- **16 of 678 PROs fall INSIDE a recording's `[t0, t0+dur]` span** → matched via the rating-centered
  path, which is concat-immune by construction (concatenation only extends spans).

**Decisive test — re-decode the at-risk source (BrainSenseTD) both ways, match against the FULL pool
(BrainSenseTD re-decoded + the fixed IndefiniteStream pool), correct tz:**
- 25 source files yield BrainSenseTD streams; concatenation merges occurred in 8 of them.
- PROs matched within 60 min: **67 (no-concat) vs 67 (concat) — identical.**
- PROs that LOSE a match due to concat: **0.** PROs that GAIN a spurious match: **0.** Status
  changes: **0.**
- inside-span (rating-centered) PROs from BrainSenseTD: **3 vs 3, none lost from inside.**
- Among all 67 matched-both PROs, **max match-distance change = 0.00 min** (BrainSenseTD-only
  emission run gave a max of 0.88 min before adding the IndefiniteStream pool; with the full pool the
  nearest match is unchanged to the second).

## Why the structural risk is real but the empirical risk is nil

The structural failure mode you described is real in principle — the nearest-fallback layer keys on a
single `StartTime`, and concatenation moves that point earlier. It does not bite **here** because:
1. The merges that fire are short (gaps ≤30 s) and the match tolerance is 60 min, so a `StartTime`
   shift from concatenation (≤~20 min even for a fully chained merge) stays well inside the window —
   the 60-min tolerance dominates the merge gaps by two orders of magnitude.
2. Most matches (51/67) come from IndefiniteStream, which is **not** subject to FixBreaking at all.
3. The rating-centered layer makes in-session PROs (16/678) concat-immune by construction.
4. Empirically, across all 8 files where merges fired, not one of the 67 matched PROs changed status
   and the nearest-match distance was unchanged.

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
