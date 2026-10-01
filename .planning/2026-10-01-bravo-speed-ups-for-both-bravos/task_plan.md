# Task Plan: Speed-ups for both BRAVOs (local and Jetstream2)

## Goal
Steps 2-7 of the combined speed-up list (the PI's go-ahead, 2026-10-01): every value unchanged, each fix its own commit with proof, pulled onto the Jetstream2 BRAVO.

## Next Step
Phase 5: B1 -- fit the Stim Optimizer's (pulse width, contact) groups in parallel processes; equality on so/so2, alternating timings.

## Current Phase
Phase 5

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
- [ ] B1 Stim Optimizer GP fits in parallel processes
- [ ] B3 tile table per sensing pair/recording in parallel (FFT one call per piece)
- [ ] B4 recording decode/decrypt in processes, once per request
- **Status:** pending

### Phase 6: Step 6, C3-C6 (pages)
- [ ] C3 Biomarkers composite preview memoised; C4 timeline dependency
- [ ] C5 folded figures drawn on open (Stim Optimizer) / after first paint (Closed-Loop, snapshots wait)
- [ ] C6 memoised heavy cards, stable props
- **Status:** pending

### Phase 7: Step 7, B5-B9 + C7-C9
- [ ] B5 numba prange (simulation, design rule); B6 readiness fits; B7 grid cells; B8 DB queries; B9 background pool
- [ ] C7 warm ROC/by-month cache; C8 control analyses on open; C9 small items
- **Status:** pending

### Phase 8: Test consolidation (the PI, 2026-10-01: ONLY after Phase 7)
- [ ] Inventory every test (container suite, host pytest, jest): runtime, overlap, what each pins
- [ ] Propose merges and removals to the PI as a list first (CLAUDE.md s.6: some tests are kept on purpose, e.g. test_one_store.py's grandfathered count)
- [ ] Consolidate and speed up after his go-ahead; suites green before and after, same behaviour pinned
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Code changes go to both BRAVOs; worker count only on Jetstream2 | the Mac ran out of memory at 16 workers (base compose comment); Jetstream2 has 245 GB |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
