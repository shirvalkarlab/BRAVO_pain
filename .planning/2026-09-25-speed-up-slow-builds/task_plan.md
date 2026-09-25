# Task Plan: Speed up the slow builds, every value unchanged

## Goal
The five speed-ups the grant session handed over (the PI: "go on all"), each its own commit with a
live equality proof (field count, 0 differing) and alternating timings.

## Next Step
None: items 1, 2, 4, 5 committed; item 3 waits on the PI (a compiled dependency, or accept changed digits).

## Current Phase
Phase 4

## Phases

### Phase 1: Item 1, the tiles in batches
- [x] Profile one tile build (47.8 s: 25.6 s transform, 18.2 s loop)
- [x] Batched transform, the FFT kept one call per piece (container FFT rounds by row grouping)
- [x] Live: 32,310,237 fields, 0 differing; 35.8 / 12.4 / 37.0 / 12.5 s
- [x] Commit (decision 266)
- **Status:** complete

### Phase 2: Items 2 and 4, duplicate work inside one Closed-Loop request
- [x] Time the request with writes to a scratch store root (live-like), count the duplicates
- [x] Remove the real duplicates (tile key, recordings, REDCap) within one request
- [x] Proof and commit (decision 267; item 2 was the probe's blocked writes)
- **Status:** complete

### Phase 3: Item 5, the E2 bootstrap vectorized
- [x] One BLAS thread for the bootstrap's fits (decision 268); batching changes arithmetic
- **Status:** complete

### Phase 4: Item 3, the design-rule fit
- [x] Measured: 29 ms a filter call, about 1,600 calls a fit; numpy dispatch-bound (30 small ops a step)
- [x] Candidate (shared covariance recursion) not exact: stretches have gaps; 0 of 60 draws identical
- [ ] Blocked on the PI: an exact 10x needs a compiled loop (numba or C) that reproduces numpy's log and summation; none installed
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The FFT stays one call per 3 s piece | numpy 2.1.3 on aarch64 rounds a row differently depending on which rows share a call |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| batched tiles differed in the container, not on the Mac | 1 | the FFT's row grouping; one call per piece keeps the grouping |
