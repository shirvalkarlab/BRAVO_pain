# Task Plan: The Closed-Loop page, step 7 of the panels' build order

## Goal
The Closed-Loop page states one verdict, says what band stability would change, lists every number
it prints without an uncertainty interval, prints the stability answer inside the coherence note,
and reports the band-power-to-pain reading with the stimulation current taken out beside the plain
one (panel D items 1, 2, 3, 5, 4).

## Next Step
Step 8 of the build order (the Stim Optimizer page), on the PI's go-ahead.

### Phase 1: Backend (items 3, 5, 4)
- [x] Item 4: `band_pain_auc_from_table(covariate_column=)`, the partial correlation beside it,
      both resampling whole pain reports; `state_edge(adjust_for_column=)` on `EdgeEstimate.adjusted`;
      `pipeline.run` passes the candidate's own side's current column (10 tests, RED first)
- [x] Item 5: `consistency.note_with_stability`, appended by the adapter where the answer exists,
      idempotent (4 tests, RED first)
- [x] Item 3: `adapter.caveats_for_report`, assembled per request, stored nowhere (7 tests, RED first)
- **Status:** complete

### Phase 2: Page (items 1, 2, and the caveats list's two readers)
- [x] Item 1: the statistical-gate endpoint's "Summary verdict" sentence gone from the sign-off
      sheet; its gate rows and counts kept
- [x] Item 2: "What would change this answer" ranks the band-stability answer at 4.5
- [x] The caveats list on the sign-off sheet (`ReportCaveats`), counted in the decision header
- [x] Item 4's page half: the adjusted reading under the second edge, replacing decision 235's
      interim sentence when it exists
- [x] Bundle rebuilt (732.487c2ca2, main.c09d6d73); the four new sentences found in the chunk
- **Status:** complete

### Phase 3: Proof and record
- [x] Host suite; jest on this page; the estimator's cost and the plain answer's field count on a
      constructed table of the live record's shape
- [x] Decision 242 in the digest and the full log
- [x] The live before-and-after on RCS08, run on the PI's machine: L 60,189 fields in common,
      5 differing (3 timing, 2 notes that only gain a sentence), 47 added, 0 removed; R 60,203 /
      5 / 44 / 0; about +10 s per report build; container 702 / 0, host 1450 / 2 / 0; workers reloaded
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The adjusted band-power-to-pain reading uses the straight-line removal on the per-sample current, default off | one estimator, and decision 241 keeps the straight line for every published number until someone asks otherwise |
| The stability sentence is appended to the coherence note by one function called from the adapter, not by a parameter on `coherence_report` | an unread parameter is what hid the clinic-stream site defect (decision 238) |
| The plain answer keeps its own rows; the adjusted one states its own sample | dropping rows with no current before the plain answer would silently move a published number |
| The decision header's own "Summary verdict" line stays | it is labelled as coming from a separate summary and as evidence, not permission; panel D scoped item 1 to the sign-off sheet |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Two constructed fixtures were too clean: the current-driven band hit the 98% refusal, and the pain-carrying band separated perfectly so its interval collapsed | 1 | more scatter on both; 86% of the band's movement is the current, and the adjusted interval has width |
| A jest assertion looked for "mean the same thing about pain" where the card says "means" | 1 | the assertion was wrong, not the card; fixed the assertion |
| The host suite's two Google Sheets credential tests failed | 1 | a package missing from this session's virtual environment, not a code fault: they pass once it is installed |
