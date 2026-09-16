# Progress Log: Rendered-text and referent audit of the three pages

## Session 2026-09-15 (evening)
- Plan written at the PI's request after decisions 172-173 (two stale-text slips he caught by eye). The two swarm
  briefs are in findings.md §1 and §2; he calls the swarms himself. Nothing run yet.
- The PI called /swarm-review with the §1 brief. Four worker-reviewer agents dispatched in parallel, read-only, probes
  allowed under `_agent_bridge/_referent_{inv,stale,dup,bnd}_*.py`. Waiting; nothing verified yet.
- Duplicates report in (`report_dup_adjacent_duplicates.md`, 2051 words, 6 items + 4 deliberate). Verified so far: DUP-1
  the backend snapshot note is still appended (`analytics.py:6141-6146`) -- keep; DUP-4 `timing_recommendation.py:64`
  types "36-90 s" against the live 27-30 s -- keep, High (drifted); DUP-2 headline count a third copy -- keep, narrow.
  Three reviewers still running.
- Inventory report in (`report_inv_inventory.md`, 3236 words). Verified: INV-1 `Biomarkers/index.js:985-1003` reads
  `spectral_feature_importance`, deleted from the backend at decision 77 (0 hits in bravo_service.py) -- the "Matched
  samples per channel" block never draws; INV-2 `BiomarkerAnalytics.js` `chPanels` pushed 6x, read nowhere. Both dead
  display code (frontend cleanup, no clinician impact). Backend-vs-display reviewer resumed for write-up; stale-referent
  reviewer still running.
- Stale-referent report in (`report_stale_referents.md`, 1603 words, 3 items + a clean list). All three verified:
  STALE-1 `BandSweepGridPanel.js:276` literal "best of 10 lengths" on every AUC hover (line 270 reads the field, 276
  does not) -- ON SCREEN, Closed-Loop "Choose a band"; STALE-2 its fold line 377 "ten lengths"; STALE-3
  `analytics.py:6754` per-row `why` says "9 lengths" then "best-of-ten" in one sentence -- not drawn (no live reader
  of `.why`), backend consistency. Waiting on the backend-vs-display write-up.
- Backend-vs-display report in (`report_bnd_backend_vs_display.md`, 2204 words; partial coverage stated by the
  reviewer). Verified: BND-2 `ThreeSourceResponsePanel.js:280-288` reads only `footer`/`absent_reason` -- the
  per-comparison headline/caption/label/subtitle/axis text is unread; BND-4 `what_it_means` unread (component
  hard-codes its own fold). Phase 2 done: 12 items ranked in findings §3 (0 dropped, 2 deliberate), three fixtures
  captured and read back from disk (§4). Committing; the PI runs /swarm-execute next.

## 2026-09-15 evening -- Phase 3, /swarm-execute (the PI's call)
- Re-read findings §2-§4 from disk. Fixtures present (716,889 / 477,708 / 1,436,191 bytes). Bridge heartbeat 0.9 s.
  `@testing-library/react` 12.1.2 is installed, so the render tests can mount components.
- Order chosen: the "before" capture (`_review_fix_capture.py before`) runs FIRST because /usr/src/BRAVO is a live
  mount and a backend edit would reach the capture; the QA worker writes the RED tests in parallel (frontend only);
  the backend builder starts only after the capture job reports done.
- "Before" capture done: job 20260915-200320-fc212b1c, rc 0, SO 1.61 s (served), CL 24.57 s, BM 1.23 s (served);
  `_agent_bridge/_review_fix_before.pkl` 1,193,850 bytes. QA worker (RED render tests) and backend builder dispatched.
- Browser check for the walk: the in-app browser at http://localhost has no signed-in session (the home page shows a
  Login link); the Chrome extension reports "not connected". The password is never typed. Unless the PI signs in to
  the in-app pane during this run, the browser walk is reported as not done.
- QA worker done: three jest files written and each watched RED for its intended reason (`ClosedLoopSim.referent.test.js`
  5 RED / 2 pins; `Biomarkers.referent.test.js` 4 RED / 2 pins; `StimOptimizer.referent.test.js` 4 pins, green).
  Combined run with the neighbouring existing suites: 9 failed, 36 passed, 45 total -- the 9 are exactly the RED
  items 1, 3 (two tests), 4, 5, 6, 7, 8, 11. Two test-only traps met: react-scripts runs jest with `resetMocks:
  true`, so a `jest.fn(impl)` Plotly stand-in lost its implementation (the grid then threw `el.on is not a
  function`) -- plain functions instead; and a jest.mock factory may not reference `document`, only
  `global.document`. Not on the ranked list: the Stim Optimizer card's headline reads "1 of 4 checks block, 1 not
  assessed" while the server's `gate.verdict` says "2 of 4 conditions block" (the card never prints the server
  string, by its own design) -- the pin is on the card's wording.
- Wave 2 dispatched: the frontend builder (Client/src only) is making items 1, 4, 5, 7, 8, 11 green against the QA
  tests; items 3 and 6 stay RED until the backend fix lands and the verifier re-captures the two fixtures. The backend
  builder is still running (items 2, 3, 6, 9, 10).
- Backend builder done (items 2, 3, 6, 9, 10; 10 files under BRAVO/modules; each test watched RED then GREEN;
  ClosedLoopDeployment host directory 640 passed, 1 skipped). Spot-checked by the orchestrator: no "36-90" left in
  `timing_recommendation.py` outside a comment; `_BAND_SWEEP_RULE_VERSION` v17; "best-of-ten" survives only in
  comments/docstrings and in `_sweep_headline_*` (no callers since decision 145); `DEVICE_SPECTRUM_AXIS_NOTE` is read
  by no component (grep of Client/src, excluding the fixture JSON and tests).
- "After" capture: job 20260915-201552-5d88300b, rc 0, SO 1.61 s (served), CL 24.16 s, BM 11.30 s (fresh under v17).
  **Live proof, field count and difference count, never a tolerance** (`_review_fix_compare.py`, job
  20260915-201641-8bd4d266, re-classified from the pickles on the host):
  * Stim Optimizer two-stage: 22,535 fields before and after, 0 differing, 0 only one side; gate verdict unchanged.
  * Closed-Loop (L 0-2+ 24.5 Hz): 48,144 -> 48,096; 48,096 in common, **7 differing, 0 timing** -- the four
    `design_rule_note` copies (item 6: "at this timing (3 s averaging / 30 s onset)" -> "at the timing shown on this
    card") and the three onset-row `why` copies (item 2: the typed "36-90 s" sentence gone); **48 only-before, all
    `three_source_response.comparisons[0..3].{headline,subtitle,amp_axis_label,power_axis_label,band_axis_label,
    columns[0..2].caption,notes[0..3]}`** (item 9, 12 fields x 4 comparisons); verdict unchanged, E1.source unchanged.
  * Biomarkers sweep: 25,664 -> 25,659; 25,659 in common, 291 differing = **264 row `why` sentences** (6 contacts x
    22 rows x 2 grids, "9 lengths ... best-of-ten" -> "nine lengths ... best-of-nine", item 10) + 19 timing fields +
    8 bookkeeping (the store keys and signature under v17, served_from_store True -> False, the background stability
    launch); **5 only-before: `notes[8]` on the four contacts that carry snapshot-served reports (item 3) and
    `stored_utc`**. No correlation, AUC, p, q or n moved.
- Both suites submitted as one bridge job, 20260915-201707-47d2eef0 (`run_both_suites.sh`).
- Container suite first run PASS=642 FAIL=1: the `_BAND_SWEEP_RULE_VERSION` pin (v16) the backend builder missed;
  moved to v17, re-run PASS=643 FAIL=0. Host 1291 passed, 2 skipped, 0 failed.
- Frontend builder done (items 1, 4, 5, 7, 8, 11; also deleted `binPanels`, a seventh unrendered array beside the
  six -- verified by the orchestrator: the old `return` drew `tdPanels` only). Fixtures re-captured from the fixed
  backend (job 20260915-201908-ffcdbc24: band sweep 716,222 B, no note with "FFT snapshots", row `why` says
  "best-of-nine"; CL payload 1,427,982 B, design_rule_note "at the timing shown on this card", comparison dicts carry
  `footer` and no `headline`; SO unchanged 477,708 B). The QA pin that recorded the PRE-fix fixture state flipped to
  the post-fix state. Jest `src/views/Reports`: 62 passed, 2 failed (the known `panels.payload.test.js` pair).
- Build main.b487b9b6 post-dates every touched source file; owned strings checked in the chunks (present: the new
  headline, the field-driven hover; absent: "10 lengths", "ten lengths", "Matched samples per channel", the deleted
  panel titles, "answered from the device"). Workers reloaded, four fresh. Decision 174 written. Browser walk NOT
  done (no session). Committing and pushing.
- Browser walk DONE (the PI signed in to the in-app browser himself, 2026-09-15 evening). RCS08, L 0-2+ 24.5 Hz
  committed via the grid's radio. Biomarkers: caption carries the snapshot count once; drawer 10 bullets, no snapshot
  bullet, "nine lengths"/"best-of-nine". Closed-Loop: all grid hover titles "best of 9 lengths" (0 with "10"/"ten"),
  fold "nine lengths", header "(provisional -- see below)" + two count boxes, design-rule line "at the timing shown on
  this card" above the occupancy line, no "36-90" with the onset fold open, robustness 27-30 s, reliable-change fold
  prints `what_it_means` (opens lowercase -- cosmetic, for the PI). Stim Optimizer: "1 of 4 checks block, 1 not
  assessed", history line, Spearman n = 15, no "2 of 4 conditions block". Decision 174 amended; committing.
- Follow-ons from the PI after the walk (decision 175): the "What would change this answer" item no longer restates the
  header's count (now "The interval spans zero on E1 and E2: a point sign, not yet an established one"); the two-stage
  card's "What to test at the next visit" queue (25 rows, all 0.950/0.951 +-1.111, improvement 0.444 -- noise) is off
  the page, one line points at the titration card. Two RED-then-GREEN render tests; jest 64/2 (known pair); build
  main.1ab6286e clean; watched live after a forced reload. Left for him: the sign-off sheet prints the count twice.
- Sign-off sheet duplicate fixed on the PI's instruction (decision 175 amended): `ProvisionalNote` gained a
  `headline` switch, off on the sheet; the verbatim verdict line is the headline, the box keeps the per-edge intervals.
  Two RED-then-GREEN tests; jest 66/2 (known pair); build main.00efb7be; watched live -- the sheet carries the count
  once, the page four times (header x2, parameter card, sheet).
- Landing (2026-09-15 late evening). PR #12 opened against v3.1.0 (29 commits, decisions 157-175). CI -- which does
  exist, `.github/workflows/ci.yml`, three jobs -- failed its secret scan on the three fixture JSONs: gitleaks'
  generic rule matched the cache-store keys (`<kind>/<uid>/<40-hex digest>`), labels not secrets; every flagged value
  read before deciding; the three fingerprints added to `.gitleaksignore` with the reason (372fbfff). CLAUDE.md §1 and
  §7 corrected to say the three CI jobs exist and what they leave out (22288091). All six checks green on the head;
  merged as a2dd109a with the branch kept, as #9-#11 were. Open item 29's gap reopens with the next commit here.
- Phase 4 (2026-09-15, late). The PI: "do items 1-4 now, tests first". Ten tests written and watched RED (6 pytest
  in the container, 2 jest; a control in `test_stage_gate.py` green by design), then: `reliable_change.what_it_means()`
  (capital, one home, adapter calls it); `index.js` comments corrected and the dead `onBandCommitted` handler + nine
  unread props + `markClosedLoopFamilyStale` import removed; `_sweep_headline_*` deleted (58 lines) with the three
  test lines that called one, seven "best-of-ten" comments -> "best-of-lengths"; `GateResult.headline` read by
  `describe()`. Live proof p4_before (backend stashed) / p4_after: SO 22,534/22,534, 5 diff (3 timing + the two
  describe strings) -- and `gate.verdict` UNCHANGED, a second copy in `bravo_service.two_stage_block`; fixed with a
  further RED test (one home), re-captured: 6 diff, all the count sentence. CL 48,092/48,092, 1 diff
  (`what_it_means`). BM 25,660 -> 25,655, 4 diff + 5 only-before, all background-launch bookkeeping. Suites: host 1297
  / 2 / 0 (a `_FakeGate` stub needed the field), container 645 / 0; jest Reports 68 / 2 (known pair). Build
  main.308939e8, same three index.js warnings shifted two lines. Workers HUP'd, four fresh. Decision 176.
