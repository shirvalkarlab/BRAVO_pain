# Task Plan: Rendered-text and referent audit of the three pages

## Goal
Find and fix, across the Biomarkers, Stim Optimizer and Closed-Loop Deployment pages, every piece of
on-screen text that (a) describes something no longer on the page (a retired table, a dash marker, a
length that was dropped, a range that was superseded, "check on device" where a range now exists), or
(b) says a fact twice within one visual block (a count on two adjacent lines, a caveat in a caption and
again in a drawer). Then pin the corrected pages with fixture render tests so the class cannot recur.
This is the class the PI caught twice on 2026-09-15 (decisions 172, 173) after the earlier review had
found its mirror image ("computed, stored, tested, not on the page", decision 167 §5).

## Next Step
Done (decision 174, pushed). The one unchecked box is the browser walk, which needs the PI signed in to the in-app browser
or the Chrome extension connected; everything else is proven by the fixture render tests, both suites and the live
RCS08 field-count proof. Open for his call: the four things decision 174 lists under "found on the way, not fixed".

## Current Phase
Phase 3

### Phase 1: Review (the PI calls /swarm-review with findings.md §1)
- [x] Rendered-text inventory per page: every string a card draws, its panel, the element beside it, its referent
- [x] Stale-referent list: strings whose referent is not on the page today, with the decision that retired it
- [x] Adjacent-duplicate list: facts printed twice inside one visual block
- [x] Backend-note-vs-display list: response sentences (`notes`, `why`, `human_text`, `detail`, `*_note`) that describe a display other than the one drawing them
- **Status:** complete

### Phase 2: Verify and rank
- [x] Every item re-checked against the served page or the component source before it is kept (never the reviewer's word)
- [x] Items ranked; each carries file:line, the fix (frontend / backend / both), and the test that will pin it
- [x] Two missing fixtures captured from the live RCS08 responses: Biomarkers sweep, Stim Optimizer two-stage (plus a dated Closed-Loop one)
- **Status:** complete

### Phase 3: Execute (the PI calls /swarm-execute with findings.md §2)
- [x] Fixture render test per card on all three pages, asserting the strings a clinician must read and the retired words' absence, RED first
- [x] The fixes, test-first, with `ps-scientific-writing` §6a applied per panel with the referent list in hand
- [x] Both suites, live field-count proof on RCS08, frontend rebuild, decision-log entry, push
- [ ] Browser walk: one screenshot per card with the PI signed in or the Chrome extension connected; not claimed if not done -- NOT DONE 2026-09-15: no signed-in in-app session, Chrome extension not connected
- **Status:** complete

## Decisions Made
| Decision | Reason |
|----------|--------|
| Own plan directory | CLAUDE.md §4: an independent task gets its own plan; the review plan of 2026-09-15 is complete (7/7) |
| The PI calls the swarms himself | His instruction 2026-09-15; the briefs are written here so they can be pasted |
| Referent, not wording, is the unit of review | Decision 172: a sentence compressed for length in isolation kept describing a retired table |
| Fixture render tests are the deliverable, not a report | Decision 167 §5 named them; decisions 172-173 show why a report alone would not hold |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Container suite 642/1 on the first run: the pin holding `_BAND_SWEEP_RULE_VERSION` still read v16 after the backend builder bumped to v17 | 1 | The pin moved to v17 (its purpose is to move with every deliberate bump); re-run PASS=643 FAIL=0 |
| Item-3 fixture-state pin read `true` for the pre-fix fixture by design; the re-captured fixture made it fail | 1 | Flipped to `false` with the reason in its comment -- the intended visible change |
