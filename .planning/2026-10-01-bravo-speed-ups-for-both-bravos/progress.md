# Progress Log

## Session: 2026-10-01

### Current Status
- **Phase:** 1 - Requirements & Discovery
- **Started:** 2026-10-01

### Actions Taken
-

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|

### Errors
| Error | Resolution |
|-------|------------|

## 2026-10-01
- Step 1 (Jetstream2 settings): pages served from Client/build; REDCap + Google secrets; database, session files, clinic sheets (35/35) and _pro_dump (43/43) checksum-equal to local; clinic table key d728c6b5 on both.
- Step 2 (decision 352): main bundle 6,581,540 -> 726,653 bytes; jest 1,026/1,026 (119 suites); offline report fetches Plotly chunk 7055 on demand, no console errors.
- Step 3 (decision 353, commit 3db6fc35): one maths thread; local workers reloaded (18 threads each, OpenBLAS loaded). C3-C5 (decision 354, commit 3f7a289f): 1,031/1,031 page tests; commit message says "8 new tests", truly 5 (logs corrected).
- Jetstream2 pulled 3f7a289f. Its saved band-power chunks were from 2026-09-27, so every request rebuilt them: re-copied the database (backup bravo_db_before_resync2_2026-10-01.sql.gz) and the chunk entry (sha256 7292f709... both). Heat-map grid 48 -> 21.6 s, Closed-Loop 111 -> 75.9 s, two-stage 102 -> 74.5 s (Mac about 9 / 27 / 24 s; Jetstream2 cores 1.3-3x slower per core).
- Database: 45 of 46 tables checksum-equal; Server_scalerecord 15 of 720,448 rows differ by one last binary digit in JSON numbers (~1e-15, 2e-12): Jetstream2's x86 MySQL reads the dump text to the neighbouring double. Not fixable by a text dump.
- A1: Jetstream2 at 16 web workers; page 200, main.83d40060.js.
- Step 4 (decision 355): plan requested with the page's own; Jetstream2 plan 106.4-106.8 -> 73.5 s, Mac 35.4-37.5 -> 25.9-27.9 s; so 0 / so2 1 (timing) differences. 1,033/1,033 page tests.
