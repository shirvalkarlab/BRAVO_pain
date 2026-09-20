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
- Open item 29 closed (2026-09-15, late): on the PI's "go ahead", GitHub default branch v3.1.0 -> PS_closedloop_deployment
  (`gh repo edit`, read back), upstream set, origin/HEAD refreshed, CLAUDE.md §4 and AGENTS.md corrected. Decision 177.
- Phase 5 (2026-09-15, late): "do 144". Before capture (switch off) on L 0-2+ / L 1-3+ 24.5 Hz; 2 tests RED
  (default ON; titration sentence's on-but-no-session case), 3 "never flips" tests re-pinned to "unchanged"; switch
  ON; GREEN 83/83; after capture (tables rebuilt under _20s). L 0-2+: 48,092 -> 47,508, 2,898 diff (2,848 pooled
  panel), verdict/thresholds/ledger 0 diff. L 1-3+: E1 -3.79 (13 pts, 4 runs) -> +17.31 (11 pts, 3 runs, p 0.074),
  D19 blocks, verdict supported(provisional) -> blocked. Suites host 1298/2/0, container 645/0. Workers HUP'd.
  Decision 178; open item 31 written (139 vs Kalman: no interference, but the capture rule still owns the pair).
- Phase 6 (2026-09-16): 144 reversed (decision 179). (b) built test-first: 16 RED tests, `threshold_placement.py`,
  `pipeline.run(place_thresholds=)`, design-rule key on the midpoint. Live proof found two defects: rows built inside
  the run before the first (post-run) placement, and a leftover second application overwriting the capture pair;
  both fixed with tests. After: L 0-2+ 196.13/190.89 -> 186.12/176.12 (median 181.12, +-5), L 1-3+ 210.58/161.90 ->
  242.27/192.27 (median 217.27, +-25); verdicts and ledgers 0 diff. Host 1314/2/0, container 645/0. Decision 180.
  The Google service-account key is blocked by org policy (iam.disableServiceAccountKeyCreation); OAuth-user route proposed.
- Google Sheets (2026-09-16 evening): service-account key made (org policy lifted) but cannot create in My Drive
  (quota); Internal audience refused Gmail; audience made External + published; consent completed through his Chrome;
  user token preferred by `google_sheets_client`. Apps Script fallback built then removed. Notation `L C+2- / R C+1-2-`
  read off the 09_16_26 sheet; written rows centred. Live export 12_30_26 read back. Host 1322/2/0, container 645/0.
  Build clean. Decision 181.
- Phase 7 (2026-09-16, late): T4 (decision 182): `clinic_sheet_sync.py`, Drive read methods, `sync_clinic_sheets`, the daily
  loop's first pass; 6 tests RED then GREEN; live 30 downloaded / 3 excluded / 0 failed, ingest 30 files 524 steps
  (was 29 / 472), 29 files identical row for row, second run 0 down / nothing written. B6 (183): `block_bootstrap_picks`,
  both headline builders, v18; 3 tests; live 264 rows, 248 block 1 / 16 block 2, r/AUC/verdict 0 diff, 39 intervals
  moved. S4 (184): `rating_days` on both epoch builders, coverage needs 2 days per pair, schedule credits hold days;
  6 tests + 4 fixtures given real days; live 15,419 -> 15,431, 6 differ (1 timing, 1 wording, 4 new day fields).
  B3 (185): `DecodeCommon/stability_answer.py` one home, `attach_stored_stability_answers` on both sweep returns under
  the grid's own key, symbols + hover + caption on the grid; 3 container + 5 jest tests; live 132 points 28/232/4.
  Build main.b872af0d. Suites: see the commit.
- Phase 8 (2026-09-16, night): B5 (186): `sheet_ratings.py`, `IncludeClinicSheetRatings` switch (off), v19; 5 container + 3 jest
  tests; live off = 0 scientific diffs, on adds 235/145/87/71/64/61 NRS sheet ratings per contact. T1 (187): conceded;
  `analytics.powerdomain` block deleted from `_compute_analytics` (112 lines); live 1,028,318 -> 939,233 fields, 89,085
  only-before all under that key, 0 differing. Hover (188): backend `p_grid` (Pearson, scipy t) and `auc_p_grid`
  (scipy `mannwhitneyu` asymptotic, vectorised per length), v20; hover "X ratings, q = Y" / "p = Y"; browser t-test and
  incomplete-beta code deleted; panels read the grid. Live: 6 contacts x 198 cells, every p finite. Host 1335/2/0;
  container 664/0 (one run with the live probe beside it tripped the timing-sensitive lock test, 663/1; alone 664/0).
  Jest Biomarkers 34/34. Build main.7930421b, chunk 753.26f2d196.


## 2026-09-17 evening (autonomous, the PI away): decision 199, the one-band rule
- RED: `StimOptimizer/tests/test_one_band_rule.py` (14) failed on import (`pain_relationship` missing); jest `SensingEvidenceTable.oneBand.test.js` (4) failed on the old headers.
- GREEN: host 1353 passed / 2 skipped / 0 failed; container PASS=664 FAIL=0; jest under StimOptimizer 18 passed; frontend build clean (chunk 100.e12fdafa).
- Live RCS08 before/after (`_agent_bridge/_d199_capture.py`, `_d199_diff.py`; only the stored response bypassed): 23,715 → 24,130 fields, 868 differing (2 timing), 62 only-before, 477 only-after, 0 differences outside the readiness table, the gate's band condition, the titration pick and the key. Usable 6 → 4 (R 1-3+ @110/@55, R 0-2+ Left @55, R 0-2+ @110), all on 26.5/27.5 Hz = stimulator harmonics.
- Workers reloaded (`kill -HUP 1`, four fresh).

## 2026-09-17 night (the PI: "do the c3 c4 etc"): decision 200
- OrbStack found STOPPED (docker daemon unreachable, bridge heartbeat 3,373 s); `orb start`, three containers up, bridge alive in a minute.
- RED: 9 pytest (`test_review_leftovers_c3_c4_c7_t2_t3.py`), 4 of 5 jest (`ReviewLeftovers.c3_c4_c6.test.js`; the fifth a green control).
- GREEN: host 1362 / 2 / 0; container 664 / 0; jest ClosedLoopSim 47 passed + the known 2.
- Live RCS08 (`_d200_capture.py`, `_d200_diff.py`): L 0-2+ 56,386 -> 56,428 fields, 16 differing (2 timing, 3 the range source, the rest rebuilt-table bookkeeping), 49 added; L 1-3+ 56,395 -> 56,438, 8 differing, 47 added; verdicts, thresholds, E1/E2 estimates identical. Device runs 3 s averaging on the Left today, so the two occupancy clocks agree.
- Frontend chunk 576.9ecf18fe. Workers reloaded.

## 2026-09-19 (the PI: "Remove C6"): decision 201
- Jest C6 test flipped to assert absence, RED (line rendered), then the line removed from `DeploySignoffCard.js`, GREEN; ClosedLoopSim 47 passed + the known 2.
- Frontend rebuilt (chunk 576.fde69d26); "approved indication" in 0 chunks. No backend change; no suite run; no live proof applies.
- T2 question (random intercept per run, shared slope) answered in chat from `within_visit.amplitude_response_shape_pooled`; no code changed for it.

## 2026-09-19 (the PI: "go on 1, 2 and 8, tests first"): decision 202, no log power on the E1 path
- Premise checked first: the pooled E1 slope was already raw (probe reproduced −7.904 on L 1-3+); the log sat in the readiness screen's era-blocked slope, the amplitude-effect table's slope, and two dead joined-table columns.
- RED: 10 new tests (4 StimOptimizer, 6 ClosedLoopDeployment) failed on the old names/values; 13 existing tests rewritten in device units (gamma scatter, no log even in fixtures).
- GREEN: host 1372 / 2 / 0; container 664 / 0. Two of my own slips on the way: the new rule version dropped the `post_ramp_margin` token decision 144's guard requires; the linear fixture let power go negative at the old log-scale noise -- both fixed and re-measured.
- Live RCS08 (`_d199_capture.py`/`_d200_capture.py` before202/after202, `_d202_diff.py`): Closed-Loop verdict/E1/thresholds identical on both bands; Stim Optimizer usable cells 4 -> 6, gate verdict unchanged, every qualifying band still on a harmonic.
- Workers reloaded. No Client/src change.

## 2026-09-19 (the PI: "go on the stability test, tests first, then db pain correlation tests"): decision 204
- Map first: the stability test's log(2) margin is on the odds-ratio scale, not power; the log power sat in the assembled matrix (`logX`, decibels) that every pooled reader stands on, and in `compute_psd_pain_correlation(transform="log")`, live on every Recompute.
- RED: 11 container tests (`test_no_log_power_pooled_spectra.py`), 5 StimOptimizer (`test_no_log_power_matrix_frame.py`), 2 Closed-Loop; two of my fixtures wrong first (four-bin minimum; a stream the Welch filter rejected, which passed one refusal test falsely), fixed and re-run RED.
- GREEN: host 1379 / 2 / 0 (was 1372); container 675 / 0 (was 664); 14 existing tests rewritten in raw power.
- Live RCS08 (`_d204_capture.py` before204 on the stashed tree / after204, `_d204_diff.py`): Biomarkers response 952,637 fields both, 11,695 differing (10,672 the per-row r/p copies on 5,975 timeline rows, 1,000 the permutation null), chosen band unchanged (L 1-3+, 0.95 Hz), r −0.495 → −0.463, n 106 → 93 (the correlation's MAD rule on raw power; item 3). Stability grid 5,148 fields both, 1,914 differing, 10 of 132 verdicts moved (inconclusive 115→113, stable 1→2, stim-dependent 16→17).
- Workers reloaded (four fresh). No Client/src change.

## 2026-09-19 (the PI: "go on item 3, tests first; MAD threshold to MAD 5, if still exists"): decision 205
- The threshold was already 5 MAD everywhere (`stats_utils.MAD_N_DEFAULT`, his consolidation of 2026-08-30); the change is the scale. Four rules took log10 first (scalar, keep-mask, vectorised sweep fallback, chronic per-recording filter) and the heat map's logistic cross-check fitted on log; all raw now, `"log"` refused, `OUTLIER_SCALE = "raw"`, `_BAND_SWEEP_RULE_VERSION` v21.
- RED 8 of 9 (the 5-MAD pin passed already), GREEN 9 of 9; 4 tests rewritten; `OutlierScale` dropped from the background whitelist after the whitelist test caught it as dead weight.
- Suites: host 1379 / 2 / 0; container 684 / 0 (was 675).
- Live RCS08 (`_d205_capture.py`, `_d205_diff.py`): sweep 33,889 fields both, 219 differing (183 the cross-check blocks; grids 0 differing, the ceilings apply live). Biomarkers response: chronic detector sample set moves (L 0-2 4,555 → 4,683, L 0-3 4,748 → 4,580, L 1-3 4,853 → 4,790), AUC 0.5536 → 0.5554, threshold 90.8 → 99.0; time-domain band summary identical.
- Workers reloaded (four fresh). No Client/src change.

## 2026-09-19 (the PI: "delete it, tests first"): decision 206, the aperiodic fit
- `remove_aperiodic` reached by nothing but `transform="fooof"`, which no page or request could select; deleted with the branch and the runner's choice. RED 3 of 3, GREEN 3 of 3 (one reword of my own comment, which still named the library).
- Suites: host 1379 / 2 / 0; container 687 / 0 (was 684). No live proof applies: zero callers, so no served field can change.
