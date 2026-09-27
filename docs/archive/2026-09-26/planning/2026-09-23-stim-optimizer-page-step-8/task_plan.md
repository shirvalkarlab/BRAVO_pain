# Task Plan: The Stim Optimizer page, step 8 of the panels' build order

## Goal
The Stim Optimizer page reads in the order a decision is made, says what its numbers rest on, and
names what only research reaches (panel C items 5, 6, 4, 7, 8).

## Next Step
None: the panels' build order is finished; what comes next is the PI's to choose.

### Phase 1: Backend
- [x] Item 4: `resolution.exposure`, on `stage1.audit.resolution_exposure` (5 tests, RED first)
- [x] Item 6: `pain_relationship.still_positive_without_current`, `adapter.stored_current_adjusted_grid` (read-only), the grid sidecar records the switch, the response key carries the adjusted grid's key (11 tests, RED first)
- [x] Item 5's one backend field: `sensing_rule_block` on the readiness payload (5 tests, RED first)
- [x] Item 7: `OBJECTIVE_SPEC.md` amendment; `stage1.audit.frequency_length_scale` (1 test, written after the code)
- [x] Item 8: README table of what the page reaches; two stale README statements corrected
- **Status:** complete

### Phase 2: Page
- [x] Order: readiness, decision, current map, next session and home schedule, plan card; evidence base a one-line footer (3 jest, RED on the old page)
- [x] Computed decision title; "resolved" defined once; exposure line; plain check label; the two readiness cards point at each other; the sensing rule first; still-positive line; stale "established" wording (13 jest, RED first)
- [x] Bundle rebuilt (100.ce250192, main.6e8e2714)
- **Status:** complete

### Phase 3: Proof and record
- [x] Host suite; jest on the page; decision 243
- [x] The live before-and-after on RCS08, on the PI's machine: main request 10,788 fields in
      common, 1 differing (the response key, which carries the module's code digest), 82 added,
      0 removed; two-stage request 39,694 / 2 / 102 / 0; no build-time cost; container 709 / 0
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The still-positive field reads a STORED current-adjusted grid and never builds one | a grid build on every Stim Optimizer request would put minutes in front of the page |
| The current-map legend stays folded | the PI's ruling of 2026-09-17 (S5) folded every description on that card; the report's proposal to open it is his to take |
| The stopping rule is labelled "computed, not read", not "unreached" | it runs on the live path every request; panel C's claim was wrong |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| The page-order test's Plotly stand-in returned nothing, then lacked `.on` | 1, 2 | the test runner resets `jest.fn` implementations; the current-map card stands in as its own title instead |
