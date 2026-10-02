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
- 2026-10-02: commits 739857f1 (tests on every core; container 95 -> 60 s on Jetstream2), a5430ba1 (decision 356, batched band power identical on Jetstream2), 4b7bbdca (decision 357, Closed-Loop segments in workers, warm 42.4 -> 38.4 s), 442be489 (decision 358, Stim Optimizer blocks in threads, warm 52.4 -> 45.6 s). Dropped: Stim Optimizer groups in workers (slower: 66.6 / 55.2 s vs 52.6). Warm profiles replace cold ones as the basis for ranking work.
- 2026-10-02 (cont.): df879579 (359, recording cache, off until BRAVO_RECORDING_CACHE_MB set), 298ee5af (360, band checks in workers, agent), fe2f557e (361, threshold-rule fit skips padding, agent), 1d097c95 (362, heat-map pairs in threads), d6455ea5 (363, clinic day conversion once). Jetstream2 both test sets at 1d097c95: host 1,903 passed, container 954 passed, 0 failed. Pending: start-up agent, page agent (C5-C9), test-consolidation agent; then enable the cache on Jetstream2 (container recreate) and Phase 9.
- 2026-10-02 (cont.): 54c1bb5b (364, one pool size). Jetstream2 both test sets at 54c1bb5b: host 1,907 passed, container 956 passed, 0 failed (209 s wall, was 145: 48 test processes each starting a 63-worker pool). Test-time pool cap of 2 tried and dropped on the PI's word (the test-consolidation agent owns test speed; the suites already pass). 14c80751 (365, page items C5/C6/C8 by the page agent): page tests 1,035 passed, 16 new pass, rebuild byte-identical; Jetstream2 pulled, chunk 941.8bf9fde7 served. Held for the PI: Closed-Loop endless redraw (resultCache read time), fix + test in scratchpad/held/. C7 not done (needs the two-R-requests safety test). Carry 365 + its Part 2 item into the compressed digest.
