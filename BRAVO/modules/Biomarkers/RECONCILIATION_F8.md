# F8 part 2 — reconciling the permutation family with the selection family

Date: 2026-09-02. Code: `BRAVO/modules/Biomarkers/pipeline.py`. Participant: RCS08
(`2e3c75c00d7f4f37b53a048d195f11da`), source `timedomain`, both outcome metrics.

## 1. The defect

The biomarker band is chosen by searching a grid of correlations between a transformed band-power
feature and a pain rating, one cell per (contact pair, frequency). Because the band is chosen by
searching, the correlation at the winning cell is biased upward, and the only honest significance
statement about it is a permutation p-value computed over the same family the search ran on. The
module computed two such p-values: `perm_p` for the family maximum of |r|, and `perm_selection_p`
for the statistic the selection rule actually maximises, which is the largest |r| among the cells
that survive a Benjamini-Hochberg screen.

Neither was a selection-corrected p-value for the reported cell, because the family the permutation
ran on was not the family the band was selected from. The proof needs no simulation. For the
`left_leg_vas` outcome the selected cell's |r| was 0.6343 while the permutation family's own
observed maximum was 0.5743, and a value drawn from a family cannot exceed that family's maximum.

A guard called `perm_family_matches_selection` was published to flag this. It compared the reported
|r| against the permuted family's own selection statistic, and it read `True` for `nrs` and `False`
for `left_leg_vas`. The guard told a reader that the p-value could not be trusted; it did not make
the p-value trustworthy.

## 2. What actually differed between the two families

Three things differed, all of them measured on the live participant before any change was made.

The first and largest is the sample from which the outlier rule's centre and scale are estimated.
Both paths apply the identical rule, `|v - median| > 5 * MAD`, from
`routines/stats_utils.mad_keep_mask`. The correlation spectrum in
`routines/streaming_psd.pearson_corr_psd_label` estimates that rule on the **full epoch stack** —
all 372 epochs, including those whose pain label is missing — and then applies the label keep-mask
and the per-column feature keep-mask together as a per-cell mask. The permutation block in
`_band_inference` did the opposite: it subset the epochs to the label-valid rows first, dropped the
label outliers as rows, and only then estimated each feature column's rule on what was left. A
median and a MAD estimated from 294 rows are not the median and MAD estimated from 372 rows, so the
two paths flagged different rows and therefore correlated different samples. At the selected cell
this changed the number of surviving pairs from 116 to 126 for `nrs`, and from 24 to 22 for
`left_leg_vas`.

The second is the family's membership floor. `pearson_corr_psd_label` admits a cell once three
surviving pairs remain; the permutation family required four. Any three-pair cell was therefore
selectable but absent from the permuted family.

The third is the FDR threshold replayed inside the null. `select_biomarker_band` screens at
q < 0.05, but `_selection_statistic` was being called with `q_threshold=0.10`. The screen decides
which cells are survivors, so replaying it at a different threshold replays a different selection
rule over a differently-defined family.

One candidate cause was checked and **ruled out**. The permutation restricts to rows carrying a
pain-report identity, because the exchangeable unit of the null is the rating rather than the epoch
(audit F3) and a row with no report has no unit to permute. On this cohort that restriction removes
nothing at all: every label-valid row carries a report identity, for both metrics (0 rows dropped
for `nrs`, 0 for `left_leg_vas`). Re-running the family maximum with the rating restriction applied
and nothing else changed gave 0.5303 for `nrs` and 0.6343 for `left_leg_vas`, identical to the
unrestricted values. The rating requirement was not the cause of the mismatch.

## 3. The option chosen, and what the other one would have cost

Two repairs were available.

**Option 1, chosen.** Compute the permutation correlations on exactly the rows and per-cell masks
the selection grid used. This leaves the reported band and its correlation untouched and changes
only the null.

**Option 2, not chosen.** Recompute the selection on the permutation's row set, so the reported cell
is a member of the permuted family by construction.

Option 1 was chosen because the divergence was never a disagreement about which rows are outliers
in principle. Both paths run the same rule; they differed only in which sample the rule's centre and
scale were estimated from, and the selection grid's choice — the full epoch stack — is the base that
the reported correlation, the displayed correlation spectrum, the FDR family and the clinician-facing
plate all already use. Option 2 would have changed a published band and a published correlation in
order to repair a defect in a p-value. That is the wrong direction of repair when the p-value is the
quantity that was computed on the wrong sample. Concretely, option 2 would have moved the `nrs`
correlation from 0.5303 to 0.5692 and the `left_leg_vas` correlation from 0.6343 to 0.5083 (the
values those cells take on the permutation's old row set), and it would have had to re-run the
Benjamini-Hochberg screen on the new grid, so the winning band itself could have changed. It would
also have made the reported number depend on a rule estimated from fewer rows than the spectrum a
clinician looks at, which is harder to explain and no more defensible.

Neither option required changing a published number. The reported band, correlation, per-cell p,
FDR q and effective sample size are byte-for-byte unchanged for both metrics; only the permutation
p-values and the new diagnostics moved.

## 4. How the fix is verified

The fix is not verified by the argument above. It is verified by a measurement that the code
publishes on every run. `_block_perm_maxcorr_pvalue` now returns its observed per-cell |r| vector,
and `_band_inference` compares that vector against the selection grid's own correlations, cell for
cell, over the same 300 cells in the same order. Three fields carry the result:

* `perm_family_max_abs_dev_from_corr` — the largest cell-for-cell disagreement. Measured:
  6.63e-13 for `nrs` and 5.00e-13 for `left_leg_vas`, which is floating-point noise.
* `perm_family_cells_in_selection_only` — cells the selection could choose that the permuted family
  does not contain. Measured: 0 for both metrics.
* `perm_rows_dropped_unrated` — the one row-set difference that cannot be removed, because a row
  with no pain-report identity cannot take part in a rating-level null. Measured: 0 for both.

There is a second, independent check. Once the family is the selection grid, `_selection_statistic`
applied to the observed family must return exactly the |r| that `select_biomarker_band` chose.
Measured: 0.5302802685841238 against a selected r of -0.5302802685837144 for `nrs`, and
0.6342879386047172 against -0.6342879386043144 for `left_leg_vas`. Both agree to about 4e-13. Before
the reconciliation this equality did not hold for either metric.

## 5. Before and after

The selected band and the descriptive statistics about it are unchanged by the fix. The band index,
r, FDR q, pair count, effective n, permuted row count and rating count were all captured on the
live participant both before and after the change and are identical. The per-cell p was not
captured before the change; it is produced by `select_biomarker_band` and `_autocorr_adjusted_pgrid`,
neither of which the fix modifies, so it cannot have moved.

| | `nrs` | `left_leg_vas` |
|---|---|---|
| Selected band | L 1⁻3⁺, 3.9215 Hz | L 0⁻2⁺, 14.817 Hz |
| r | -0.5303 | -0.6343 |
| Per-cell p | 1.28e-04 | 1.69e-03 |
| FDR q | 0.0193, survives at q < 0.05 | 0.5055, does not survive |
| n pairs / effective n | 116 / 46.9 | 24 / 21.6 |
| Permuted rows / ratings | 294 / 72 | 232 / 43 |

The permutation statistics moved as follows. All p-values are on 1000 permutations, reported as
(exceedances + 1) / (permutations + 1).

| | `nrs` before | `nrs` after | `left_leg_vas` before | `left_leg_vas` after |
|---|---|---|---|---|
| Observed family max \|r\| | 0.5692 | **0.5303** | 0.5743 | **0.6343** |
| `perm_p` (family max) | 0.0500 | **0.0809** | 0.6074 | **0.4166** |
| `perm_selection_p` | 0.0500 | **0.0809** | 0.5764 | **0.3516** |
| Guard `perm_family_matches_selection` | True | **True** | **False** | **True** |

The guard now passes for both metrics, which is the point of the exercise: the family the null runs
on is the family the band was selected from, so `perm_p` and `perm_selection_p` are now
selection-corrected p-values for the reported cell rather than for a neighbouring statistic.

**Neither band is significant after reconciliation.** The `nrs` band, which previously sat just
under the conventional threshold at `perm_p` = 0.0500, is now at 0.0809. The `left_leg_vas` band
moved from 0.6074 to 0.4166 and remains far from significance. The winner's-curse summaries agree
with that reading: the mean of the null family maximum is 0.4325 for `nrs` against an observed
0.5303, and 0.6077 for `left_leg_vas` against an observed 0.6343, and the observed value fails to
exceed the null's 95th percentile for both metrics (0.5314 and 0.6845 respectively). For
`left_leg_vas` in particular, searching 300 cells with no real effect produces a maximum |r| of
about 0.61 on average, so the 0.6343 that was selected is very close to what the search alone
delivers.

This result is provisional. Two earlier corrections to this same statistic each reversed which
metric appeared significant, and this is the third. What this correction does is remove the nominal
significance of the `nrs` band without changing the ordering of the two metrics. It should be
treated as the current best estimate, not as a settled finding, and it should be re-checked whenever
anything upstream of the correlation grid changes.

## 6. Sensitivity check on the one change that enlarges the family

Of the three alignments, only the membership floor can add cells to the family, and adding sparsely
sampled cells could inflate the null and so inflate the p-value. That was measured rather than
assumed. Re-running the reconciled pipeline with the floor put back at four surviving pairs gives
p-values identical to the digit for both metrics and both statistics (`nrs` 0.0809, `left_leg_vas`
0.4166 and 0.3516), because no cell on this participant sits in the affected range: the sparsest
cell has 52 surviving pairs for `nrs` and 18 for `left_leg_vas`, and zero cells fall below four.
The floor change is a correctness alignment with no effect on this dataset, and it exists so that a
future dataset with sparser cells cannot reintroduce the defect.

The contributions of the other two alignments were not separated from each other. The
estimation-base change and the FDR-threshold change were applied together, so the reported
before-and-after difference is their joint effect. Separating them would require two further live
runs and would not change any reported number.

## 7. What remains open

* The block length chosen for the rating-level circular-block permutation came out as 1 for both
  metrics, which means successive pain reports showed too little serial dependence at the rating
  level for the block structure to bind, and the null is effectively an unrestricted rating
  permutation. Whether that is the right block length for these visit-structured reports has not
  been assessed here.
* The figures quoted in the docstring of `_rating_level_perm_matrix` for the epoch-level versus
  rating-level null (p = 0.0729 against 0.233) were measured on the pre-reconciliation family. They
  have not been re-measured on the reconciled family. The argument for permuting ratings rather
  than epochs does not depend on the size of that gap, but the two numbers should not be quoted as
  current.
* `_autocorr_adjusted_pgrid` recomputes each cell's p from the selection grid's r and an
  autocorrelation-adjusted effective N. The effective N is computed on a keep-mask built with
  `adapter.mad_outlier_mask`, which is the same rule as the correlation spectrum's, so the two are
  consistent; but the effective-N adjustment itself is documented as an upper bound on the
  independent information in irregularly-spaced sessions, and that bound was not revisited here.
* Only RCS08 was measured. The reconciliation is structural and does not depend on the participant,
  but the specific claim that the rating-identity restriction drops no rows is a property of this
  cohort's data and is published per run as `perm_rows_dropped_unrated` so it can be checked
  elsewhere.
