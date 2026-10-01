# Progress: Contact-aware Stim Optimizer

## 2026-09-30
- Visit plan for 2026-09-30 shipped earlier (commit b60042d8): L and R C+1-2-, max L 2.5 / R 3 mA,
  sense L 0-3 and R 0-3. Host 1816 passed / 2 skipped / 0 failed; container PASS=945 FAIL=0.
- Proposed steps A-D to the PI; answers recorded in task_plan.md "Scope and authority".
- Plan created. Nothing of Phases 1-4 started.

## 2026-10-01
- The PI asked for a separate session to try Jev's choice / score modes for ranking stimulation
  settings from the pain scores. Offered as a session chip (task_c1e0ec77); it asks him before any
  RCS08 value goes to Codiv (local OpenJev or his approval), and is read-only against
  StimOptimizer/*.py. Phase 1 here waits for his go-ahead.
- He then approved, verbatim: "I explicitly approve sending de-identified RCS08 settings and
  ratings to CODIv". Chip replaced (task_f065e731) with the approval and its limits (settings and
  ratings only; no names, notes or uid) and the main-checkout path for container scripts.
- Phase 1 complete: VISIT_PLAN_BY_UID emptied; test watched RED then GREEN; host 1817 passed / 2 skipped / 0 failed, container PASS=945 FAIL=0. Phase 2 started.
- Phase 2 complete (findings.md): groups keyed on the pulse-width pair; the clinic epoch frame ignores contacts; no prior ruling on contacts in the model; 4 groups of >= 8 before and after adding Left contact. Waiting on the PI: share 0 mA stretches across contact groups?
- Phase 3: moved stim_contacts_short into DecodeCommon.sensing_rule.contacts_short (bravo_service keeps the old names as aliases) so Stage 1 can label stretches without a circular import. Suite run stalled: the container bridge stopped polling at 00:54; asked the PI for an OrbStack restart.
- Phase 3: step A in stage1_openloop (groups keyed (pwL, pwR, Left contact), 0 mA shared, reference = configuration in force, pooled fit = contact in force + off); bravo_service readers updated; clinic contact reader for 6 sheet formats (28 tests pass). Next: clinic epoch frame keys on contact.
- Server side of step A done: stage1 groups + reference + pooled fit; bravo_service readers; clinic frame keys on Left contact; next-visit check counts only the contact in force + 0 mA (35 tests pass in the two files).
- Page done for step A (171 page tests). Decisions 344-346 written. Suites + build running.
- Phase 3 complete. Suites: host 1849 passed / 2 skipped / 0 failed; container PASS=945 FAIL=0. Build compiled (with warnings, not inspected); chunk 999.0bfca705 carries 'Home surveys by Left contact'. Final live diff: 26,919 common, 9,004 differ, 28,891 added, 33,981 removed, all inside two_stage.
