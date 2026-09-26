# Findings & Decisions

## Requirements
-

## Research Findings
-

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-

## 2026-09-25 night: the shared tile copy was short (read-only investigation)
- The saved three-second tile copy is keyed on all database rows + constants, NOT on the recordings a caller passes. The Stim Optimizer (`_calibrated_lsb_cache`) passes 393 TD recordings only (others pass +457 survey/montage) and builds event PSDs without the sensing-pair index (730 of 4,512).
- After the daily ingest (19:44 UTC), the Stim Optimizer built first and wrote a short copy at 20:03:32 UTC: 293,108 tiles vs 303,321 from scratch; L 1-3+ matched 161/108 vs 201/187 (30/60 s), R 0-3+ 304/205 vs 459/439.
- Same failure in the ledger: 2026-09-11 20:08 -> 09-12 05:15; 2026-09-17 20:06 -> 09-20 08:12 (key b0f199733d at two sizes).
- On the short copy (absolute numbers to re-measure; before/after equality proofs stay valid): Biomarkers grids/stability/timeline/matrix rebuilt 20:17-20:19 UTC, Closed-Loop reports since 20:03, the P-19 document, P-03's per-state odds ratios, the TD/PSD example line, the band-detector runs, the stepped-current run (check).
- Fix in progress: canonical inputs for the Stim Optimizer + passed-recordings digest in the tile key.

## 2026-09-26: E2's pain join was off by one settings period (confirmed from timestamps, fixed, uncommitted)
- Closed-Loop joined table matched the chunk's 0-based period position against the ratings' 1-based period number since 8fbe11ba (2026-09-03; calibrated path f01a0320). RCS08 L 1-3+ 24.5 Hz: 42,568 of 42,568 rated chunks carried the previous period's ratings. Only E2 and its current-removed reading read them.
- Fixed in `adapter._attach_setting_pain`. Short-tile numbers: NRS 0.562 -> 0.564; LLVAS 0.773 (p 0.004, established) -> 0.641 (p 0.072, not established).
- To correct after re-measuring on full tiles: decisions 242, 260, 268; full-log 147, 175, 200; artifacts established_point_sign_2026-09-13.md, research_2026-09-22_D_*. Right lead not yet re-measured.
