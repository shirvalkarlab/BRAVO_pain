# Task Plan: Speed up the slow builds, every value unchanged

## Goal
The five speed-ups the grant session handed over (the PI: "go on all"), each its own commit with a
live equality proof (field count, 0 differing) and alternating timings.

## Next Step
Item 2/4: time the Closed-Loop request with store writes going to a scratch root, to see which duplicates are real.

## Current Phase
Phase 2

## Phases

### Phase 1: Item 1, the tiles in batches
- [x] Profile one tile build (47.8 s: 25.6 s transform, 18.2 s loop)
- [x] Batched transform, the FFT kept one call per piece (container FFT rounds by row grouping)
- [x] Live: 32,310,237 fields, 0 differing; 35.8 / 12.4 / 37.0 / 12.5 s
- [x] Commit (decision 266)
- **Status:** complete

### Phase 2: Items 2 and 4, duplicate work inside one Closed-Loop request
- [ ] Time the request with writes to a scratch store root (live-like), count the duplicates
- [ ] Remove the real duplicates (tile key, recordings, REDCap) within one request
- [ ] Proof and commit
- **Status:** in_progress

### Phase 3: Item 5, the E2 bootstrap vectorized
- [ ] Batched partial correlations, bit-for-bit or a stated reason
- **Status:** pending

### Phase 4: Item 3, the design-rule fit
- [ ] Vectorize the filter inside `fit_design_model`
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The FFT stays one call per 3 s piece | numpy 2.1.3 on aarch64 rounds a row differently depending on which rows share a call |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| batched tiles differed in the container, not on the Mac | 1 | the FFT's row grouping; one call per piece keeps the grouping |
