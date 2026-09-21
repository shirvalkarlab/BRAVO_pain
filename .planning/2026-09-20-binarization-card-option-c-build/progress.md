# Progress

## 2026-09-21
- Plan created.
- Part 1 done: sentence trimmed; align_pros takes max_per_rating/refractory_min/match_direction from the request; warning names the cap. Live: 2 min 14/14 no sharing, 1 field differing; 60 min 303 -> 161 sessions, cap 3, band moves. Suites 1434 / 2 / 0 and 699 / 0; jest 64. Commit (see git log).

## 2026-09-21, option C built and the review
- Timing histogram: 6 jest tests RED (2) -> GREEN 6 after the last bin's right edge was made inclusive; the file-name case clash fixed (TimingHistogram.js is the one tracked name; timingHistogramModel.js holds the pure functions).
- Card laid out as option C (MatchWindowBand.js: sentence, window + split + direction, histogram; left column restyled; preview untouched apart from the two blocks that moved out). jest under Biomarkers: 71 passed (was 64). Bundle chunk 482.af03041e; served bundle checked by string.
- Backend review: `pro_lsb` (30 channels, 18,330 points, 2.5 MB, 0.35 s per Compute, read by no page) deleted with `_pro_lsb_by_channel`, `_native_lsb_tolerance_param`, the `native_lsb_tolerance_s` field; the cap/gap parse made one helper. Container test RED 1 -> GREEN; the wiring test for the deleted helper deleted. Suites: host 1434 / 2 / 0; container 699 / 0. Live RCS08 Compute before / after: 249,322 fields in common, 0 differing, 128,311 only-before (all `availability.pro_lsb` + `native_lsb_tolerance_s`). Wall-clock rounds (16.7 / 65.1 s before, 38.3 / 58.5 s after) were taken while the daily band-sweep precompute ran (load 58 on 16 cores) and prove nothing about speed; the 0.35 s is the in-process timer.
- Decision 223 recorded (digest, full log, CLAUDE.md §4); plan mode inject-smart autonomous, attested.
