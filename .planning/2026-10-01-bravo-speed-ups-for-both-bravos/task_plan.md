# Task Plan: Speed-ups for both BRAVOs (local and Jetstream2)

## Goal
Steps 2-7 of the combined speed-up list (the PI's go-ahead, 2026-10-01): every value unchanged, each fix its own commit with proof, pulled onto the Jetstream2 BRAVO.

## Next Step
Commit the four Sonnet agents' results as they land (C7 ROC/month caching, heat-map per-pair statistics in workers, tile build in workers, the per-grid correction test), each with a decision row and a Jetstream2 equality proof; then Phase 9 final re-proof and plan close.

## Current Phase
Phase 9

## Scope and rules
- Code lands on the Mac checkout (the local BRAVO runs it live), pushed, then `git pull` on the Jetstream2 BRAVO.
- Jetstream2-only settings stay as uncommitted edits in its docker-compose.override.yml (backed up first).
- Proof per server-side fix: RCS08 field count + difference count (0), alternating timings. Page fixes: jest, rebuild, string found in the served chunk.
- A fix that would change a number or what a page shows is reported and held, not shipped.
- C2 and C7 need a test that two simultaneous R-using requests are safe first; stop and report if not.

## Phases

### Phase 1: Step 1 (done before this plan)
- [x] Jetstream2: pages served from Client/build via bravo_nginx.dev.conf; REDCap and Google secrets present
- [x] Jetstream2: database, session files, clinic sheets and _pro_dump match the local BRAVO
- **Status:** complete

### Phase 2: Step 2, C1 (Plotly out of the main bundle)
- [x] Delete the unused `experimentalRoutes` import in routes.js; App.js's offline report + survey pages lazy too (decision 352)
- [x] Jest 1,026/1,026; main 6,581,540 -> 726,653 bytes (1,879 -> 214 KB gz); Plotly chunk 7055 on demand
- [x] Commit 526ef6c4, pushed; Jetstream2 pulled, serves main 726,653 bytes, Plotly chunk separate
- **Status:** complete

### Phase 3: Step 3, A1/A2 (settings)
- [x] One maths thread by default (OPENBLAS/OMP/MKL=1) for both BRAVOs; proof on RCS08 + timings (decision 353; BRAVO/maths_threads.py so the test needs no Django)
- [x] Jetstream2 only: 16 web workers (override `command`, backup in backups/); heaviest request peaks 10.2 GB
- **Status:** complete

### Phase 4: Step 4, B2 + C2
- [x] B2 DROPPED: the 3.5 s 'sleep' is the main thread waiting in joblib's _retrieve for the parallel leave-one-out workers (profile callers: threading.wait 1.44 s, selectors 1.16 s, joblib _retrieve) -- the parallel work's own time, not idle polling
- [ ] Test two simultaneous Stim Optimizer requests are safe with R; then start the TwoStage request with the first
- **Status:** complete

### Phase 5: Step 5, B1/B3/B4 (parallel processes)
- [x] B1 dropped (groups in workers slower, 358); held-out folds + band checks in workers (360)
- [ ] B3 tile table in parallel: with an agent (2026-10-02)
- [x] B4 recording cache per web worker (359), on at 3,000 MB on Jetstream2 (369)
- **Status:** in progress (B3)

### Phase 6: Step 6, C3-C6 (pages)
- [ ] C3 Biomarkers composite preview memoised; C4 timeline dependency
- [ ] C5 folded figures drawn on open (Stim Optimizer) / after first paint (Closed-Loop, snapshots wait)
- [x] C6 memoised heavy cards, stable props (with C5 Closed-Loop folds and C8: decision 365, 14c80751)
- **Status:** complete

### Phase 7: Step 7, B5-B9 + C7-C9
- [ ] B5 numba prange (simulation, design rule); B6 readiness fits; B7 grid cells; B8 DB queries; B9 background pool
- [x] B5 numba loops cached on disk (369); B6 threshold-rule fit (361); B8 clinic days once (363); B9 warm web workers (369)
- [x] C8 research checks on open (365); [ ] C7 ROC/by-month caching: with an agent; B7 heat-map pairs (362), per-pair statistics in workers: with an agent
- **Status:** in progress (C7, B7)

### Phase 8: Test consolidation (the PI, 2026-10-01: ONLY after Phase 7)
- [x] Done directly on the PI's word, no proposal (367): both Python sets 145 -> 66 s; 30 + 14 tests removed, each named against its cover
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Code changes go to both BRAVOs; worker count only on Jetstream2 | the Mac ran out of memory at 16 workers (base compose comment); Jetstream2 has 245 GB |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|

### Phase 9: Production parallel budget for the Jetstream2 BRAVO (PI, 2026-10-02)
- [x] Both test sets uncapped on Jetstream2 at 369: host 1,910 / container 949 passed (one test fixed)
- [x] Measured: pool process median 220 MB (shared libraries counted once by the machine); 62 GB of 245 in use with 16 pools of 31 started
- [x] Budget set and documented (runbook 3a): pool 31, kept a day, recording cache 3,000 MB
- [ ] Final re-proof after the four agents' commits
- **Status:** in progress
