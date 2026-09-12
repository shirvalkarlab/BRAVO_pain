# Test audit, 2026-09-12 -- what the 1,619 tests actually test, and what can go

Four read-only investigators, one per module group, classified every test by reading its body and
the production code it calls (caller search across BRAVO/modules and BRAVO/Server, the decision
log, the quoted assertion). Per-module reports, each with the evidence on every line:
`test_audit_2026-09-12_Biomarkers.md`, `_ClosedLoopDeployment.md`, `_StimOptimizer.md`,
`_CacheStore_DecodeCommon.md`. Two of the boldest claims were re-checked by the orchestrator
(the two-stage Stim Optimizer path has no caller outside itself and a scratch script; `torch` is
absent from the container). NOTHING HAS BEEN DELETED. This is the list for the PI to decide on.

| Module | Tests | Keep | Safe to delete | Rewrite, do not delete | Notes |
|---|---|---|---|---|---|
| Biomarkers | 519 | 448 | 26 | 29 | 7 tests test a copy of a formula written inside the test file; `test_process_redcap.py`'s test is named `main` and has never run |
| Closed-Loop Deployment | 487 | 443 | 20 | 18 | one test could start a real cache rebuild from the live record (fixed today, uncommitted until this landing) |
| Stim Optimizer | 501 | 200 | 75 stand-alone + **211 in one subsystem** | 18 | the two-stage open-loop / gate / closed-loop path and its PyTorch backend: no production caller; 40 of its tests need PyTorch, which the container does not have -- they are most of the "42 skipped" every host run reports |
| Cache store + decoded form | 112 | 103 | 1 | 4 | the two deliberate guards (one-store count, constructed provenance cycle) confirmed keep |
| **Total** | **1,619** | **1,194** | **122 + 211** | **69** | |

## Safe to delete now (122 tests, per-module lists carry the evidence)
- Dead targets with 0 callers and no protecting decision: e.g. the exported band-pain tables
  (Biomarkers, 7), `estimate_lsb` (7), the `PSD_SOURCE_TAXONOMY` dictionary nothing reads (4),
  `amplitude_response_cached` (Closed-Loop, 10; decisions 85/100/101 name it as uncalled),
  `settled_window` (3), the registry nothing imports (2), Stim Optimizer's `select_batch_between_visit`,
  `device_band_power`, all of `test_separation_span.py` (10), 17 of 19 `test_percept_adaptive.py`
  tests whose live equivalents are the Closed-Loop rule table.
- Superseded rules: the D30 "frequency search closed" framing rejected 2026-09-05 (1); eight Stim
  Optimizer tests pinning the frozen 2026-09-02 RCS08 numbers (nrs at 3.9215 Hz, "3 of 15 cells")
  that decisions 59, 62-64 and 124 moved past.
- Duplicates: 6.

## The subsystem decision (211 tests)
Stim Optimizer's two-stage path (`stage1_openloop`, `stage2_closedloop`, `routines/stage_gate`,
`session_analysis`, `schedule`) and its PyTorch research backend (`surrogate_torch`,
`safety_ordinal`). `pipeline.run_two_stage_live`'s own docstring says its only callers were tests;
`BOTORCH_REFACTOR.md` says not to add PyTorch to the production container. Keep as research code
with its tests moved out of the production suite, or delete -- the PI's call, not a per-test one.
Either way the 40 PyTorch-gated tests should leave the production suite: they cannot run there.

## Rewrite, do not delete (69)
- Shape-only (asserts a type, a length, a key set, or "no exception"): 26.
- Misnamed (the name asserts what the body does not check): 23, including seven Biomarkers tests
  that call no production code and compare a formula in the test file against itself.
- Superseded assertion still passing by accident: `test_deployment_summary_carries_temporal_validity_block`
  asserts threshold drift is "not yet computed" when `deployment_summary` now computes it.
- `test_process_redcap.py::main` -- a real value test the container has never collected; rename.
- Four Closed-Loop tests that exercise the pre-2026-09-05 one-spectrum-per-row frame branch of
  `joined_table`, deliberately retained; the PI's call whether the branch stays.

## Hazards found on the way (not tests)
1. `three_source_response.py:844` never passes `ramp_end_t`, so the ramp clip of commit `790ed21` is not wired.
2. Two rate floors: 55 Hz reported on the Stim Optimizer page, 30 Hz enforced on the Closed-Loop ledger (D44).
3. `StimOptimizer/__init__.py` lists a `routines/design.py` that does not exist.
4. `pipeline.run` (Stim Optimizer) hands the stopping rule a one-item history, so its plateau / stop / ceiling branches can never fire on the page.
5. Three container-only guard tests in `test_one_store.py` return PASS on any import failure.
6. `test_locks.py` imports only because an alphabetically earlier file inserted the root on `sys.path`.
7. `test_availability.py` replaces `redcap_client` with a stand-in if it is not already imported; harmless today only because `test_analytics.py` sorts earlier.
8. The one-store guard scans 3 files; 7 production files import the store now (none carries a forbidden construct today).
