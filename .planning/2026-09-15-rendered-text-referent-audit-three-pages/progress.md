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
