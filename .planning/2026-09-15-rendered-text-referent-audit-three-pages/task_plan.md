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
Nothing queued. Phase 6 done (decisions 179, 180): the margin is off again, the pair comes from the record. The
Google Sheets service-account key is blocked by his organisation's policy; the OAuth-user route is the way round
and needs his go-ahead (a small code change plus a one-time consent on his Mac).
(Phase 5 done, decision 178; Phase 4 done, decision 176): the four leftovers of decision 174 fixed test-first, plus the second
copy of the gate count the live proof exposed. Open item 29 closed the same night (decision 177). Still his: decision 139's threshold
re-centring, decision 144's post-ramp switch, the Google Sheets key (decision 163), the titration session (item 30).

## Current Phase
Phase 5

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
- [x] Browser walk: one screenshot per card with the PI signed in or the Chrome extension connected; not claimed if not done -- DONE 2026-09-15 evening, the PI signed in to the in-app browser himself; every card on the ranked list read as decision 174 states
- **Status:** complete

### Phase 4: The four leftovers of decision 174 (the PI's go-ahead 2026-09-15)
- [x] Reliable-change fold sentence opens with a capital (Closed-Loop page, "How big a change..." card)
- [x] Two stale comments in `Biomarkers/index.js` (lines 40, 202) describe a commit button decision 80 deleted
- [x] The two dead "best-of-ten" headline builders in `analytics.py` deleted, with the one test that called them
- [x] The server gate verdict string no longer counts a not-assessed condition as blocking (`stage_gate.py`) -- BOTH copies: `describe()` and the response's `gate.verdict`, the second found by the live proof
- [x] Suites, rebuild where a Client file changes, decision-log entry, push
- **Status:** complete

### Phase 5: Decision 144's switch, on (the PI's "do 144", 2026-09-15 late)
- [x] "Before" capture with the margin off: the Closed-Loop report on L 0-2+ and L 1-3+ at 24.5 Hz
- [x] Tests RED: the default is ON; the three "never flips the switch" tests pin "unchanged", not "False"; the titration card's sentence for on-but-no-session
- [x] `USE_POST_RAMP_MARGIN = True`; GREEN; both suites
- [x] "After" capture; field count and difference count per band; the verdict, E1, D19 and the thresholds named
- [x] Workers reloaded; decision-log entry; push
- **Status:** complete

### Phase 6: Reverse 144; place the thresholds from the record (the PI's ruling, 2026-09-16)
- [x] 144 reversed test-first (default OFF; ON state under a monkeypatch); decision 179
- [x] Placement tests RED: median, pair, refusals, apply, rows, key, adapter step, hook order, idempotence
- [x] `threshold_placement.py`, `pipeline.run(place_thresholds=)`, midpoint-keyed design rule, rows' wording
- [x] Live before/after on L 0-2+ and L 1-3+ at 24.5 Hz; two defects found by it and fixed (rows built before the hook; a second application)
- [x] Both suites; workers reloaded; decision 180; open item 31 closed; push
- **Status:** complete

## Decisions Made
| Decision | Reason |
|----------|--------|
| Own plan directory | CLAUDE.md §4: an independent task gets its own plan; the review plan of 2026-09-15 is complete (7/7) |
| The PI calls the swarms himself | His instruction 2026-09-15; the briefs are written here so they can be pasted |
| Referent, not wording, is the unit of review | Decision 172: a sentence compressed for length in isolation kept describing a retired table |
| Fixture render tests are the deliverable, not a report | Decision 167 §5 named them; decisions 172-173 show why a report alone would not hold |
| Phase 4: a sentence that reaches the response gets ONE home (`reliable_change.what_it_means`, `GateResult.headline`) | The live proof showed `describe()` fixed and `gate.verdict` still wrong: two copies of one sentence drift, decision 30's lesson |
| Phase 4: item 2 removes the dead handler, not only the comments | A comment about a commit button cannot be made true while the page still passes a commit handler nothing reads |

## Errors Encountered
| Error | Attempt | Resolution |
| Phase 4: a JSX `{/* */}` comment placed inside `cond ? (` broke the build (`Unexpected token`, index.js:1080) | 1 | folded into the neighbouring JSX comment above the ternary |
| Phase 4: `test_surface_serialization.py`'s hand-made `_FakeGate` had no `headline` after the property was added | 1 | the stub gained the field; the test's assertions unchanged |
|-------|---------|------------|
| Container suite 642/1 on the first run: the pin holding `_BAND_SWEEP_RULE_VERSION` still read v16 after the backend builder bumped to v17 | 1 | The pin moved to v17 (its purpose is to move with every deliberate bump); re-run PASS=643 FAIL=0 |
| Item-3 fixture-state pin read `true` for the pre-fix fixture by design; the re-captured fixture made it fail | 1 | Flipped to `false` with the reason in its comment -- the intended visible change |
