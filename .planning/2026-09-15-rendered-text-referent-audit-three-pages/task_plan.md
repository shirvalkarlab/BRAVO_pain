# Task Plan: Rendered-text and referent audit of the three pages

## Goal
Fix every on-screen sentence on the three pages that describes something no longer there or repeats a
fact inside one visual block, and pin each card with a fixture render test (decisions 172-174).

## Next Step
Nothing queued; phases 1-9 complete (decisions 174-202; the last: no log power on the E1 path). Waiting
on the PI: the remaining log-power sites (202), pulse-width pooling (189), `max_per_rating` (118), the
zero-caller chronic routines (187), item 15's niceties; not code: the titration session (open item 30).
Context compaction of the reference documents landed 2026-09-19 (decision 203).

## Current Phase
Phase 9

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

### Phase 7: T4, B3, B6, S4 of the 2026-09-15 review (the PI, 2026-09-16: "Do T4 ... then B3, B6, and S4")
- [x] T4: the clinic sheets pulled from Drive by the daily pass (`clinic_sheet_sync.py`, `sync_clinic_sheets`); live 30 down, 09_16_26 in, 29 unchanged file for file
- [x] B6: the headline interval is a block bootstrap sized as the p-value's shuffle is (v18); live 16 rows at block 2, verdicts 0 changed
- [x] S4: coverage counts occasions -- 2 calendar days per current pair; live 6 fields differ, none a verdict
- [x] B3: the stability answer on the Biomarkers grid's winning cells, one home for the words (`DecodeCommon/stability_answer.py`); live 132 points, 28/232/4
- [x] Suites, rebuild, decisions 182-185, one commit, push
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

### Phase 8: B5, T1 and the hover (the PI, 2026-09-16)
- [x] B5: sheet scores in the heat maps behind a default-off switch, tests first, live counts per contact (decision 186)
- [x] T1: conceded as a misinterpretation; the leftover chronic-detector analytics deleted, 89,085 fields, 0 differing (decision 187)
- [x] Hover: "X ratings, q = Y" / "p = Y"; p-values on the backend (Pearson, scipy's Mann-Whitney, vectorised); browser t-test code deleted (decision 188)
- [x] Both suites, rebuild, decision-log rows, one commit, push
- **Status:** complete

### Phase 9: The current map, S5-S7 and the run rule (the PI, 2026-09-17)
- [x] S5 folded with the pairing line; absolute predicted ratings, colour centred on today (189, 192)
- [x] S6 measured; the age penalty and the time input both removed on his ruling (190, 193, 194, 196)
- [x] S7 measured on the record's long holds and the 2026-09-16 session: margin 0 s, no data excluded (191, 196)
- [x] Runs accepted with the other side held at any current; the 2026-09-16 session enters every table (197)
- **Status:** complete
