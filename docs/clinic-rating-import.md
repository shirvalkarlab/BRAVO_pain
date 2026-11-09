# Timed clinic ratings with unknown current

The full clinic stream retains a directly timed verbal pain rating even when the
workbook does not specify a scalar stimulation amplitude, including an adaptive
range or a pre-stimulation baseline. It preserves the workbook row, source hash,
measured time and recorded rating. It neither chooses an endpoint of a range nor
infers the time for these previously excluded rows.

Both unknown amplitude fields remain missing. The fixed-setting epoch builder
continues to exclude rows without a known current; legacy callers requesting
only fixed-setting ratings retain their prior behavior. The clinic sheet does
not supply MPQ ratings. Its verbal ratings retain their existing explicit
conversion to the 0–100 VAS display scale.

Parser version `v4_clinic_pain_2026-11-09` invalidates the previous clinic product
signature. Re-import the existing source snapshots through the normal clinic
pipeline after installing this version; refreshing a browser alone does not
rebuild the stored product. Check individual source/import receipts when a
combined sync reports a failed stream: other independently completed streams
can still be current.

Validation uses constructed XLSX workbooks, checks explicit Pacific-to-UTC times,
missing-time exclusion, unchanged legacy behavior, VAS scaling, absent MPQ, and
exclusion from fixed-setting models. Real source-to-output acceptance remains
private deployment evidence. The inherited parser is larger than this narrow
correction; changed decision paths are exercised, without claiming a new 95%
branch-coverage guarantee for the entire legacy module. Reassess that module
when undertaking a broader parser refactor.
